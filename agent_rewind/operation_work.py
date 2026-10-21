"""Request-local SQL work for operation adapters; no service or authorization.

One request shares 512 SQL/control attempts, ten seconds while a connection is
owned, and 20 million SQLite VM instructions across every phase. Connection
acquisition and storage I/O are outside this clock. Eight attempts are reserved
before ordinary work for rollback, restoration, discard and bounded reclose.
Native timeouts bound server waits; cleanup is always attempted, not promised a
hard real-time bound. Engines must yield exclusive native connections without
another owner's SQLite progress handler.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Literal

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .admission_transaction import AdmissionError
from .request_authority import ActionForbidden
from .request_identity import IdentityInvalid
from .scoped_lineage import ResourceNotFound

MAX_STATEMENTS = 512
MAX_SECONDS = 10.0
MAX_VM_INSTRUCTIONS = 20_000_000
VM_INTERVAL = 1000
CLEANUP_RESERVE = 8


class OperationWork:
    """A single request's counters, reused sequentially, never concurrently."""

    def __init__(self) -> None:
        self.statements = 0
        self.seconds = 0.0
        self.instructions = 0
        self._started: float | None = None
        self._connection: Connection | None = None
        self._raw: Any = None
        self._info: dict[str, Any] | None = None
        self._listeners: list[tuple[str, Any]] = []
        self._progress = False
        self._ready = False
        self._detached = True
        self._failed = False

    def _elapsed(self) -> float:
        return self.seconds + (0.0 if self._started is None else perf_counter() - self._started)

    def _limits(self, *, cleanup: bool = False) -> None:
        elapsed = self._elapsed()
        ceiling = MAX_STATEMENTS if cleanup else MAX_STATEMENTS - CLEANUP_RESERVE
        if (
            self.statements > ceiling
            or self.instructions >= MAX_VM_INSTRUCTIONS
            or not math.isfinite(elapsed)
            or elapsed >= MAX_SECONDS
        ):
            raise AdmissionError("dependency_unavailable")

    def check(self) -> None:
        if self._failed:
            raise AdmissionError("dependency_unavailable")
        self._limits()
        self.remaining_timeouts_ms()

    def remaining_timeouts_ms(self) -> tuple[int, int]:
        remaining = MAX_SECONDS - self._elapsed()
        if not math.isfinite(remaining) or remaining < 0.001:
            raise AdmissionError("dependency_unavailable")
        milliseconds = int(remaining * 1000)
        return min(5000, milliseconds), min(3000, milliseconds)

    def _charge(self) -> None:
        # Charge before executing, never exceed the ordinary-work allowance.
        self.check()
        if self.statements >= MAX_STATEMENTS - CLEANUP_RESERVE:
            raise AdmissionError("dependency_unavailable")
        self.statements += 1

    def _native_limits(self) -> None:
        connection = self._connection
        if connection is None or connection.invalidated:
            raise AdmissionError("dependency_unavailable")
        statement_ms, lock_ms = self.remaining_timeouts_ms()
        raw = connection.connection.driver_connection
        if raw is None:
            raise AdmissionError("dependency_unavailable")
        # These bypass SQLAlchemy cursor events and must be charged explicitly.
        if connection.dialect.name == "sqlite":
            self._charge()
            raw.execute(f"PRAGMA busy_timeout={lock_ms}")
        elif connection.dialect.name == "postgresql":
            with raw.cursor() as cursor:
                self._charge()
                cursor.execute(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
                self._charge()
                cursor.execute(f"SET LOCAL lock_timeout = '{lock_ms}ms'")
        else:
            raise AdmissionError("dependency_unavailable")

    def _before(
        self,
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        _context: Any,
        many: bool,
    ) -> None:
        if many:
            # Operation adapters issue bounded individual statements, not an
            # opaque batch whose work could evade the per-request counter.
            raise AdmissionError("dependency_unavailable")
        if self._ready:
            self._native_limits()
        self._charge()

    def _after(self, *_args: Any) -> None:
        self.check()

    def _step(self) -> int:
        self.instructions += VM_INTERVAL
        try:
            self.check()
        except AdmissionError:
            return 1
        return 0

    def attach(self, connection: Connection) -> None:
        self.check()
        if self._connection is not None or connection.info.get("operation_work") is not None:
            raise AdmissionError("dependency_unavailable")
        self._connection = connection
        self._raw = connection.connection.driver_connection
        self._info = connection.info
        self._started = perf_counter()
        self._detached = False
        connection.info["operation_work"] = self
        # Record ownership before each potentially partially successful attach.
        for name, callback in (
            ("before_cursor_execute", self._before),
            ("after_cursor_execute", self._after),
        ):
            self._listeners.append((name, callback))
            event.listen(connection, name, callback)
        if connection.dialect.name == "sqlite":
            self._progress = True
            self._raw.set_progress_handler(self._step, VM_INTERVAL)

    def setup_complete(self) -> None:
        self.check()
        if self._connection is None or self._detached:
            raise AdmissionError("dependency_unavailable")
        # Setup has saved the original native timeout before any refresh.
        self._ready = True

    def control_attempt(
        self, kind: Literal["begin", "commit", "rollback", "close", "discard", "restore"]
    ) -> None:
        if kind == "begin":
            self._charge()
        elif kind == "commit":
            self.check()
            self._native_limits()
            self._charge()
        else:
            # Cleanup is unconditional even if timing/instruction work expired.
            self.statements += 1

    def detach(self) -> None:
        self._ready = False
        connection = self._connection
        failed = False
        interruption: BaseException | None = None
        if connection is not None:
            if self._progress:
                try:
                    self._raw.set_progress_handler(None, 0)
                except BaseException as error:
                    failed = True
                    if interruption is None and not isinstance(error, Exception):
                        interruption = error
                self._progress = False
            for name, callback in self._listeners:
                try:
                    if event.contains(connection, name, callback):
                        event.remove(connection, name, callback)
                except BaseException as error:
                    failed = True
                    if interruption is None and not isinstance(error, Exception):
                        interruption = error
            self._listeners.clear()
            try:
                if self._info is not None and self._info.get("operation_work") is self:
                    del self._info["operation_work"]
            except BaseException as error:
                failed = True
                if interruption is None and not isinstance(error, Exception):
                    interruption = error
        self._detached = not failed
        if failed:
            self._failed = True
            if interruption is not None:
                raise interruption
            raise AdmissionError("dependency_unavailable")

    def finish(self) -> None:
        if self._started is not None:
            self.seconds += perf_counter() - self._started
        self._started = None
        self._connection = None
        self._raw = None
        self._info = None
        if not self._detached:
            raise AdmissionError("dependency_unavailable")
        try:
            self._limits(cleanup=True)
            self.remaining_timeouts_ms()
        except AdmissionError:
            self._failed = True
            raise


@contextmanager
def operation_connection(engine: Engine, work: OperationWork) -> Iterator[Connection]:
    """Owned native read-only phase using the same request's work object.

    No transaction is retained across storage. This is READ COMMITTED optimistic
    validation, not response linearizability. No fault-to-HTTP translation here.
    """
    work.check()
    connection: Connection | None = None
    original: tuple[int, int] | None = None
    primary: BaseException | None = None
    attached = False
    cleanup_failed = False
    setup_ok = False
    cleanup_interruption: BaseException | None = None
    discard_retry_used = False

    def cleanup_failure(error: BaseException) -> None:
        nonlocal cleanup_failed, cleanup_interruption
        cleanup_failed = True
        if cleanup_interruption is None and not isinstance(error, Exception):
            cleanup_interruption = error

    def cleanup_attempt(kind: Literal["rollback", "close", "discard", "restore"]) -> None:
        try:
            work.control_attempt(kind)
        except BaseException as error:
            cleanup_failure(error)

    def discard() -> None:
        nonlocal discard_retry_used
        if connection is None:
            return
        cleanup_attempt("discard")
        try:
            connection.invalidate()
        except BaseException as error:
            cleanup_failure(error)
            if not discard_retry_used:
                discard_retry_used = True
                cleanup_attempt("discard")
                try:
                    connection.invalidate()
                except BaseException as error:
                    cleanup_failure(error)

    try:
        connection = engine.connect()
        attached = True
        work.attach(connection)
        raw = connection.connection.driver_connection
        if connection.in_transaction():
            raise AdmissionError("dependency_unavailable")
        if connection.dialect.name == "sqlite":
            if (
                not isinstance(raw, sqlite3.Connection)
                or raw.isolation_level is None
                or getattr(raw, "autocommit", -1) != -1
                or raw.in_transaction
                or sqlite3.sqlite_version_info < (3, 35, 0)
            ):
                raise AdmissionError("dependency_unavailable")
            query_only: Any = connection.exec_driver_sql("PRAGMA query_only").scalar_one()
            timeout: Any = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
            if type(query_only) is not int or query_only not in (0, 1):
                raise AdmissionError("dependency_unavailable")
            if type(timeout) is not int or timeout < 0:
                raise AdmissionError("dependency_unavailable")
            original = query_only, timeout
            connection.exec_driver_sql("PRAGMA query_only=ON")
            lock_ms = work.remaining_timeouts_ms()[1]
            connection.exec_driver_sql(f"PRAGMA busy_timeout={lock_ms}")
        elif connection.dialect.name == "postgresql":
            if (
                getattr(raw, "autocommit", None) is not False
                or getattr(getattr(raw, "info", None), "transaction_status", None) != 0
            ):
                raise AdmissionError("dependency_unavailable")
            work.control_attempt("begin")
            connection.begin()
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY")
            connection.exec_driver_sql("SET LOCAL search_path TO public,pg_temp")
            statement_ms, lock_ms = work.remaining_timeouts_ms()
            connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
            connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{lock_ms}ms'")
        else:
            raise AdmissionError("dependency_unavailable")
        work.setup_complete()
        setup_ok = True
        yield connection
        work.check()  # includes fetch/parse/user work after the last SQL event
    except BaseException as error:
        primary = error
    finally:
        if attached:
            try:
                work.detach()
            except BaseException as error:
                cleanup_failure(error)
        if connection is not None:
            # Failed accounting cannot skip the native action. Failed native
            # cleanup cannot skip later discard, close, reclose or finish.
            cleanup_attempt("rollback")
            try:
                connection.rollback()
            except BaseException as error:
                cleanup_failure(error)
            if cleanup_failed or not setup_ok:
                discard()
            elif original is not None and not connection.invalidated:
                try:
                    raw = connection.connection.driver_connection
                    if raw is None:
                        raise AdmissionError("dependency_unavailable")
                    cleanup_attempt("restore")
                    raw.execute(f"PRAGMA query_only={original[0]}")
                    cleanup_attempt("restore")
                    raw.execute(f"PRAGMA busy_timeout={original[1]}")
                except BaseException as error:
                    cleanup_failure(error)
                    discard()
            cleanup_attempt("close")
            try:
                connection.close()
            except BaseException as error:
                cleanup_failure(error)
                discard()
                cleanup_attempt("close")
                try:
                    connection.close()
                except BaseException as error:
                    cleanup_failure(error)
        if attached:
            try:
                work.finish()
            except BaseException as error:
                cleanup_failure(error)
    if primary is None and cleanup_interruption is not None:
        # No body failure exists: delay the first cleanup interruption until
        # every owned cleanup stage has been attempted.
        raise cleanup_interruption from None
    if primary is not None and (
        not isinstance(primary, Exception)
        or isinstance(primary, IdentityInvalid | ResourceNotFound | ActionForbidden)
    ):
        raise primary from None
    if (
        primary is not None
        and setup_ok
        and not isinstance(primary, AdmissionError | SQLAlchemyError | sqlite3.Error)
    ):
        # Caller parser/programming errors are not classified as driver failures.
        raise primary from None
    if primary is not None or cleanup_failed:
        raise AdmissionError("dependency_unavailable") from None
