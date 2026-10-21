"""Dormant, cooperative SQLite checkout and progress ownership.

Only this factory creates capabilities. No application factory is changed here.
This is not a sandbox against base-class calls, native extensions or arbitrary
retained raw SQL. Lifecycle guards do no SQL; callers still restore their own
settings and own transaction/authorization decisions.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from weakref import WeakKeyDictionary, WeakSet

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.pool import ConnectionPoolEntry, Pool, PoolProxiedConnection, QueuePool

ProgressCallback = Callable[[], int | None]
_REGISTRY_LOCK = RLock()
_CAPABILITIES: WeakKeyDictionary[Engine, SQLiteCapability] = WeakKeyDictionary()
_POOLS: WeakKeyDictionary[Pool, SQLiteCapability] = WeakKeyDictionary()
_ATTEMPT: ContextVar[CheckoutReceipt | None] = ContextVar("sqlite_checkout", default=None)


@dataclass(frozen=True)
class CleanupVerdict:
    generation: int
    returned: bool
    close_acknowledged: bool
    disposal_required: bool
    disposal_acknowledged: bool
    failed: bool
    commit_attempted: bool
    commit_acknowledged: bool

    @property
    def clean(self) -> bool:
        return (
            self.returned
            and self.close_acknowledged
            and not self.failed
            and (not self.disposal_required or self.disposal_acknowledged)
        )


class SQLiteOwnershipError(SQLAlchemyError):
    """Fixed private connection failure; callers retain their outcome mapping."""

    def __init__(self, verdict: CleanupVerdict | None = None) -> None:
        self.verdict = verdict
        super().__init__("Owned SQLite connection unavailable.")


@dataclass(eq=False)
class SQLiteCapability:
    """Private factory identity, never an authority grant or caller assertion."""

    lock: RLock = field(default_factory=RLock, repr=False)
    records: WeakSet[ConnectionPoolEntry] = field(default_factory=WeakSet, repr=False)


@dataclass(eq=False)
class CheckoutReceipt:
    capability: SQLiteCapability
    pool: Pool = field(repr=False)
    lock: RLock = field(default_factory=RLock, repr=False)
    record: ConnectionPoolEntry | None = field(default=None, repr=False)
    raw: _TrackedSQLite | None = field(default=None, repr=False)
    proxy: PoolProxiedConnection | None = field(default=None, repr=False)
    connection: Connection | None = field(default=None, repr=False)
    new_record: bool | None = None
    generation: int = 0
    returned: bool = False
    close_acknowledged: bool = False
    disposal_required: bool = False
    disposal_acknowledged: bool = False
    failed: bool = False
    completed: bool = False
    commit_attempted: bool = False
    commit_acknowledged: bool = False
    interruption: BaseException | None = field(default=None, repr=False)

    def fail(self, error: BaseException | None = None) -> None:
        with self.lock:
            self.failed = True
            if error is not None and not isinstance(error, Exception) and self.interruption is None:
                self.interruption = error


@dataclass(eq=False)
class _Physical:
    capability: SQLiteCapability
    lock: RLock = field(default_factory=RLock, repr=False)
    receipt: CheckoutReceipt | None = field(default=None, repr=False)
    generation: int = 0
    borrowed: bool = False
    tainted: bool = False
    unknown_callback: bool = False
    closed: bool = False
    native_busy: bool = False
    lease: ProgressLease | None = field(default=None, repr=False)

    def fail(self, error: BaseException | None = None) -> None:
        self.tainted = True
        if self.receipt is not None and not self.receipt.completed:
            self.receipt.fail(error)


class _TrackedSQLite(sqlite3.Connection):
    _ownership: _Physical

    def set_progress_handler(self, progress_handler: ProgressCallback | None, n: int) -> None:
        state = self._ownership
        with state.lock:
            state.fail()
        # Even a direct clear is foreign. The existing native callback stays put.
        raise SQLiteOwnershipError() from None

    def _native_progress(self, callback: ProgressCallback | None, interval: int) -> None:
        super().set_progress_handler(callback, interval)

    def _native_close(self) -> None:
        super().close()

    def close(self) -> None:
        state = self._ownership
        with state.lock:
            if state.closed:
                return
            if state.native_busy:
                state.fail()
                raise SQLiteOwnershipError()
            if state.lease is not None or state.unknown_callback:
                state.fail()
            state.native_busy = True
            receipt = state.receipt
            if receipt is not None and not receipt.completed:
                receipt.disposal_required = True
        try:
            self._native_close()
        except BaseException as error:
            with state.lock:
                state.fail(error)
            # SQLAlchemy can suppress native-close errors. Retain an interruption
            # separately so an owning scope can raise it after remaining cleanup.
            raise SQLiteOwnershipError() from None
        else:
            with state.lock:
                state.closed = True
                state.unknown_callback = False
                if state.lease is not None:
                    state.lease._released = True
                    state.lease = None
                if receipt is not None and not receipt.completed:
                    receipt.disposal_acknowledged = True
        finally:
            with state.lock:
                state.native_busy = False

    def _native_rollback(self) -> None:
        super().rollback()

    def rollback(self) -> None:
        state = self._ownership
        with state.lock:
            if state.lease is not None or state.unknown_callback or state.native_busy:
                state.fail()
                raise SQLiteOwnershipError() from None
            state.native_busy = True
        try:
            self._native_rollback()
        except BaseException as error:
            with state.lock:
                state.fail(error)
            raise
        finally:
            with state.lock:
                state.native_busy = False


class ProgressLease:
    def __init__(self, raw: _TrackedSQLite, receipt: CheckoutReceipt, owner: object) -> None:
        self._raw, self._receipt, self._owner = raw, receipt, owner
        self._generation = receipt.generation
        self._released = False

    def install(self, callback: ProgressCallback, instruction_interval: int) -> None:
        if (
            not callable(callback)
            or type(instruction_interval) is not int
            or instruction_interval < 1
        ):
            raise SQLiteOwnershipError()
        state = self._raw._ownership
        with state.lock:
            if (
                self._released
                or state.lease is not self
                or state.generation != self._generation
                or state.closed
                or state.tainted
                or state.native_busy
            ):
                raise SQLiteOwnershipError()
            state.unknown_callback = True
            state.native_busy = True
        try:
            self._raw._native_progress(callback, instruction_interval)
        except BaseException as error:
            with state.lock:
                state.fail(error)
            raise
        else:
            with state.lock:
                state.unknown_callback = False
        finally:
            with state.lock:
                state.native_busy = False

    def release(self) -> None:
        state = self._raw._ownership
        with state.lock:
            if self._released:
                return
            if state.lease is not self or state.generation != self._generation:
                raise SQLiteOwnershipError()
            if state.native_busy:
                raise SQLiteOwnershipError()
            state.unknown_callback = True
            state.native_busy = True
        try:
            self._raw._native_progress(None, 0)
        except BaseException as error:
            with state.lock:
                state.fail(error)
            raise
        else:
            with state.lock:
                state.unknown_callback = False
                state.lease = None
                self._released = True
        finally:
            with state.lock:
                state.native_busy = False


class _OwnedQueuePool(QueuePool):
    def recreate(self) -> QueuePool:
        with _REGISTRY_LOCK:
            capability = _POOLS.get(self)
        if capability is None:
            raise SQLiteOwnershipError()
        # Only an already-owned predecessor can authorize a successor. Merely
        # disposing an unrelated replacement pool must not grant ownership.
        # Public recreation (and any native work) stays outside registry locks.
        successor = super().recreate()
        with _REGISTRY_LOCK:
            _POOLS[successor] = capability
        return successor


def require_owned_sqlite(engine: Engine) -> SQLiteCapability:
    capability = _capability(engine)
    if capability is None:
        raise SQLiteOwnershipError()
    return capability


def _capability(engine: Engine) -> SQLiteCapability | None:
    with _REGISTRY_LOCK:
        capability = _CAPABILITIES.get(engine)
        if capability is not None and _POOLS.get(engine.pool) is not capability:
            raise SQLiteOwnershipError()
        return capability


def _attempt(capability: SQLiteCapability, record: ConnectionPoolEntry) -> CheckoutReceipt:
    receipt = _ATTEMPT.get()
    if receipt is None or receipt.capability is not capability:
        raise SQLiteOwnershipError()
    with receipt.lock:
        if receipt.record is not None and receipt.record is not record:
            raise SQLiteOwnershipError()
        if receipt.proxy is not None:
            raise SQLiteOwnershipError()
        if receipt.record is None:
            with capability.lock:
                receipt.new_record = record not in capability.records
        receipt.record = record
    return receipt


def _native_idle(raw: _TrackedSQLite) -> bool:
    state = raw._ownership
    with state.lock:
        return (
            not state.closed
            and not state.tainted
            and not state.unknown_callback
            and not state.native_busy
            and state.lease is None
            and not raw.in_transaction
        )


def create_owned_sqlite_engine(
    url: str,
    *,
    connect_timeout: float = 3,
    pool_timeout: float = 1,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> Engine:
    try:
        if type(url) is not str:
            raise SQLiteOwnershipError()
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        raise SQLiteOwnershipError() from None
    if (
        parsed.drivername not in {"sqlite", "sqlite+pysqlite"}
        or not parsed.database
        or parsed.database == ":memory:"
        or parsed.database.startswith("file:")
        or parsed.query
        or parsed.username is not None
        or parsed.host is not None
        or any(
            type(value) not in {int, float} or not math.isfinite(value) or value <= 0
            for value in (connect_timeout, pool_timeout)
        )
        or type(pool_size) is not int
        or not 1 <= pool_size <= 32
        or type(max_overflow) is not int
        or not 0 <= max_overflow <= 32
    ):
        raise SQLiteOwnershipError()
    capability = SQLiteCapability()
    engine = create_engine(
        parsed,
        poolclass=_OwnedQueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=False,
        pool_reset_on_return=None,
        connect_args={"check_same_thread": False, "timeout": connect_timeout},
    )

    def do_connect(
        dialect: Any, record: ConnectionPoolEntry, args: Any, params: Any
    ) -> _TrackedSQLite:
        receipt = _attempt(capability, record)
        raw = sqlite3.connect(*args, **params, factory=_TrackedSQLite)
        raw._ownership = _Physical(capability, receipt=receipt)
        receipt.raw = raw
        return raw

    def checkout(raw: Any, record: ConnectionPoolEntry, proxy: PoolProxiedConnection) -> None:
        receipt = _attempt(capability, record)
        if not isinstance(raw, _TrackedSQLite) or raw._ownership.capability is not capability:
            raise SQLiteOwnershipError()
        with capability.lock:
            capability.records.add(record)
        receipt.raw, receipt.proxy = raw, proxy
        state = raw._ownership
        with state.lock:
            state.generation += 1
            receipt.generation = state.generation
            state.receipt = receipt
            if not _native_idle(raw):
                state.fail()
                raise SQLiteOwnershipError()
            state.borrowed = True

    def returning(raw: Any, record: ConnectionPoolEntry, reset_state: Any = None) -> None:
        # Never raise before QueuePool returns/retires its record, or perform
        # native cleanup while holding the physical-state lock.
        if not isinstance(raw, _TrackedSQLite):
            return
        state = raw._ownership
        receipt = state.receipt
        dirty = False
        try:
            with state.lock:
                dirty = not _native_idle(raw)
                if dirty:
                    state.fail()
        except BaseException as error:
            dirty = True
            with state.lock:
                state.fail(error)
        if dirty:
            if receipt is not None:
                receipt.disposal_required = True
            try:
                record.invalidate()
            except BaseException as error:
                if receipt is not None:
                    receipt.fail(error)
                try:
                    raw.close()
                except BaseException as close_error:
                    if receipt is not None:
                        receipt.fail(close_error)

    def checkin(raw: Any, record: ConnectionPoolEntry) -> None:
        returning(raw, record)
        # None means invalidated; the attempt may be outside its connect scope.
        receipt = None
        if isinstance(raw, _TrackedSQLite):
            with raw._ownership.lock:
                receipt = raw._ownership.receipt
                raw._ownership.borrowed = False
        else:
            candidate = _ATTEMPT.get()
            if candidate is not None and candidate.record is record:
                receipt = candidate
        if receipt is not None:
            with receipt.lock:
                receipt.returned = True

    event.listen(engine, "do_connect", do_connect)
    event.listen(engine, "checkout", checkout)
    event.listen(engine, "reset", returning)
    event.listen(engine, "checkin", checkin)
    with _REGISTRY_LOCK:
        _CAPABILITIES[engine] = capability
        _POOLS[engine.pool] = capability
    return engine


def acquire_progress(connection: Connection, *, owner: object) -> ProgressLease:
    capability = require_owned_sqlite(connection.engine)
    raw = connection.connection.driver_connection
    if not isinstance(raw, _TrackedSQLite) or raw._ownership.capability is not capability:
        raise SQLiteOwnershipError()
    state = raw._ownership
    with state.lock:
        if state.lease is not None:
            # A failed borrower owns nothing; do not poison or clean the owner.
            raise SQLiteOwnershipError()
        receipt = state.receipt
        if (
            receipt is None
            or receipt.completed
            or not state.borrowed
            or state.closed
            or state.tainted
            or state.native_busy
            or state.unknown_callback
        ):
            raise SQLiteOwnershipError()
        lease = ProgressLease(raw, receipt, owner)
        state.lease = lease
        return lease


def cleanup_snapshot(receipt: CheckoutReceipt | None) -> CleanupVerdict | None:
    if receipt is None:
        return None
    with receipt.lock:
        return CleanupVerdict(
            receipt.generation,
            receipt.returned,
            receipt.close_acknowledged,
            receipt.disposal_required,
            receipt.disposal_acknowledged,
            receipt.failed,
            receipt.commit_attempted,
            receipt.commit_acknowledged,
        )


def require_clean(verdict: CleanupVerdict | None) -> None:
    if verdict is not None and not verdict.clean:
        raise SQLiteOwnershipError(verdict) from None


def _cleanup(receipt: CheckoutReceipt, connection: Connection | None) -> None:
    """Bounded best effort; recording failure never gates the next native action."""
    raw = receipt.raw
    if raw is not None:
        state = raw._ownership
        with state.lock:
            if state.receipt is not receipt:
                # A completed old scope never touches a new generation.
                return
            # Reserve quarantine before dropping the state lock. A concurrent
            # checkout may not obtain a clean generation while disposal begins.
            state.tainted = True
            receipt.completed = False
            lease = state.lease
        if lease is not None:
            receipt.fail()
            try:
                lease.release()
            except BaseException as error:
                receipt.fail(error)
    for _ in range(2):
        try:
            if connection is not None:
                connection.invalidate()
            elif receipt.proxy is not None and receipt.proxy.is_valid:
                receipt.proxy.invalidate()
        except BaseException as error:
            receipt.fail(error)
        try:
            if connection is not None:
                close_owned(connection, receipt)
            elif receipt.proxy is not None:
                receipt.proxy.close()
                receipt.returned = True
                receipt.close_acknowledged = True
        except BaseException as error:
            receipt.fail(error)
        # Initial record construction can fail before its public methods are
        # usable. Never invalidate/checkin that partial record ourselves.
        if raw is not None and not raw._ownership.closed:
            try:
                raw.close()
            except BaseException as error:
                receipt.fail(error)
    if raw is not None:
        with raw._ownership.lock:
            if raw._ownership.receipt is receipt and raw._ownership.closed:
                # A retained-raw retry may finish after logical close marked the
                # receipt complete. Keep its actual same-generation close ACK.
                receipt.disposal_acknowledged = True
    receipt.completed = True


def _attest_checkout(engine: Engine, connection: Connection, receipt: CheckoutReceipt) -> None:
    with _REGISTRY_LOCK:
        trusted = (
            _CAPABILITIES.get(engine) is receipt.capability
            and engine.pool is receipt.pool
            and _POOLS.get(receipt.pool) is receipt.capability
        )
    if (
        not trusted
        or connection.engine is not engine
        or connection.closed
        or connection.invalidated
        or receipt.record is None
        or receipt.raw is None
        or receipt.proxy is None
        or receipt.generation < 1
        or receipt.failed
        or receipt.completed
        or receipt.returned
    ):
        raise SQLiteOwnershipError()
    with receipt.capability.lock:
        known = receipt.record in receipt.capability.records
    if (
        not known
        or connection.connection is not receipt.proxy
        or receipt.proxy.driver_connection is not receipt.raw
        or receipt.record.driver_connection is not receipt.raw
    ):
        raise SQLiteOwnershipError()
    state = receipt.raw._ownership
    with state.lock:
        if (
            state.capability is not receipt.capability
            or state.receipt is not receipt
            or state.generation != receipt.generation
            or not state.borrowed
            or not _native_idle(receipt.raw)
        ):
            raise SQLiteOwnershipError()


def connect_owned(engine: Engine) -> tuple[Connection, CheckoutReceipt | None]:
    capability = _capability(engine)
    if capability is None:
        return engine.connect(), None
    receipt = CheckoutReceipt(capability, engine.pool)
    token = _ATTEMPT.set(receipt)
    connection = None
    try:
        connection = engine.connect()
        receipt.connection = connection
        _attest_checkout(engine, connection, receipt)
    except BaseException as error:
        receipt.fail(error)
        _cleanup(receipt, connection)
        # No proxy: the supported QueuePool call has unwound its initial
        # allocation or returned the existing record. Physical close is separate.
        if receipt.proxy is None and (receipt.record is None or receipt.new_record):
            # QueuePool has completed its no-acquisition/new-allocation unwind;
            # no checkin or Connection.close acknowledgment is fabricated.
            receipt.returned = True
        receipt.completed = True
        if not isinstance(error, Exception):
            raise
        raise SQLiteOwnershipError(cleanup_snapshot(receipt)) from None
    finally:
        _ATTEMPT.reset(token)
    return connection, receipt


def close_owned(connection: Connection, receipt: CheckoutReceipt | None) -> None:
    if receipt is None:
        connection.close()
        return
    # Only the original proxy may be closed. A stale receipt cannot target a
    # new borrower; an already closed Connection remains an idempotent no-op.
    if receipt.connection is not connection:
        receipt.fail()
        raise SQLiteOwnershipError(cleanup_snapshot(receipt))
    if connection.closed:
        if receipt.close_acknowledged:
            return
    elif not connection.invalidated and connection.connection is not receipt.proxy:
        receipt.fail()
        raise SQLiteOwnershipError(cleanup_snapshot(receipt))
    try:
        connection.close()
    except BaseException as error:
        receipt.fail(error)
        raise
    else:
        if not connection.closed or (receipt.proxy is not None and receipt.proxy.is_valid):
            receipt.fail()
            raise SQLiteOwnershipError(cleanup_snapshot(receipt))
        with receipt.lock:
            receipt.close_acknowledged = True
            # close returned after the supported pool's checkin/overflow path.
            receipt.returned = True
            receipt.completed = True


@contextmanager
def owned_connect(engine: Engine) -> Iterator[Connection]:
    connection, receipt = connect_owned(engine)
    if receipt is None:
        with connection:
            yield connection
        return
    primary: BaseException | None = None
    try:
        yield connection
    except BaseException as error:
        primary = error
    try:
        close_owned(connection, receipt)
    except BaseException as error:
        receipt.fail(error)
    verdict = cleanup_snapshot(receipt)
    if verdict is None or not verdict.clean:
        _cleanup(receipt, connection)
    if primary is not None:
        raise primary from None
    if receipt.interruption is not None:
        raise receipt.interruption from None
    require_clean(cleanup_snapshot(receipt))


@contextmanager
def owned_begin(engine: Engine) -> Iterator[Connection]:
    if _capability(engine) is None:
        with engine.begin() as connection:
            yield connection
        return
    with owned_connect(engine) as connection:
        raw = connection.connection.driver_connection
        if not isinstance(raw, _TrackedSQLite):
            raise SQLiteOwnershipError()
        receipt = raw._ownership.receipt
        if receipt is None:
            raise SQLiteOwnershipError()
        transaction = connection.begin()
        try:
            yield connection
        except BaseException:
            # Preserve the body failure; final context cleanup remains mandatory.
            try:
                if transaction.is_active:
                    transaction.rollback()
            except BaseException as error:
                receipt.fail(error)
            raise
        else:
            receipt.commit_attempted = True
            transaction.commit()
            receipt.commit_acknowledged = True
