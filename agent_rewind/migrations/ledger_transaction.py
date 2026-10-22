"""Offline ledger transaction ownership; no provisioning or CLI activation."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, replace
from typing import Any

import psycopg
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine, RootTransaction
from sqlalchemy.exc import DBAPIError

from ..sqlite_ownership import (
    CheckoutReceipt,
    SQLiteOwnershipError,
    close_owned,
    connect_owned,
    finish_owned,
    quarantine_owned,
)
from . import ledger_engine
from .ledger_engine import LedgerEngineClaim, claim_ledger_engine, release_ledger_engine
from .ledger_work import LedgerWork
from .schema import MigrationRefused, schema_table_names
from .service import MIGRATOR_LOCK, _postgres_exclusion


@dataclass
class LedgerOutcome:
    begun: bool = False
    commit_attempted: bool = False
    commit_acknowledged: bool = False
    rollback_attempted: bool = False
    rollback_acknowledged: bool = False
    cleanup_failed: bool = False
    begin_attempted: bool = False
    _used: bool = field(default=False, init=False, repr=False, compare=False)

    @property
    def confirmed_precommit_rollback(self) -> bool:
        return self.begun and not self.commit_attempted and self.rollback_acknowledged


@dataclass(frozen=True)
class _LedgerBody:
    connection: Connection
    root: RootTransaction
    raw: Any
    proxy: Any
    claim: LedgerEngineClaim
    work: LedgerWork
    receipt: CheckoutReceipt | None
    generation: int | None
    lease: Any
    xid: str | None = None


_BODIES: dict[Connection, _LedgerBody] = {}


def _body_live(body: _LedgerBody) -> None:
    connection, claim, work = body.connection, body.claim, body.work
    with ledger_engine._LOCK:
        state = ledger_engine._REGISTRY.get(claim.engine)
        if (
            state is None
            or state.claim is not claim
            or state.poisoned
            or claim.released
            or claim.work is not work
            or not claim.checked_out
            or connection.engine is not claim.engine
            or claim.engine.pool is not state.pool
            or claim.engine.dialect is not state.dialect
        ):
            raise MigrationRefused("transactional_connection_required")
    if (
        connection.closed
        or connection.invalidated
        or connection.get_transaction() is not body.root
        or not body.root.is_active
        or connection.in_nested_transaction()
        or connection.connection is not body.proxy
        or body.proxy.driver_connection is not body.raw
        or not work._used
        or not work._claimed
        or not work._attached
        or work._detached
        or work._connection is not connection
        or work._raw is not body.raw
        or len(work._listeners) != 2
        or any(not event.contains(connection, name, callback) for name, callback in work._listeners)
    ):
        raise MigrationRefused("transactional_connection_required")
    receipt, lease = body.receipt, body.lease
    if connection.dialect.name == "sqlite":
        if receipt is None or lease is None:
            raise MigrationRefused("transactional_connection_required")
        physical = body.raw._ownership
        if (
            receipt.connection is not connection
            or receipt.raw is not body.raw
            or receipt.proxy is not body.proxy
            or receipt.pool is not claim.engine.pool
            or receipt.record is None
            or receipt.record.dbapi_connection is not body.raw
            or receipt.record not in receipt.capability.records
            or receipt.capability is not physical.capability
            or receipt.generation != body.generation
            or receipt.failed
            or receipt.completed
            or receipt.returned
            or physical.receipt is not receipt
            or physical.generation != body.generation
            or not physical.borrowed
            or physical.tainted
            or physical.closed
            or physical.unknown_callback
            or physical.native_busy
            or physical.lease is not lease
            or work._lease is not lease
            or lease._released
            or lease._raw is not body.raw
            or lease._receipt is not receipt
            or lease._owner is not work
            or lease._generation != body.generation
            or not body.raw.in_transaction
        ):
            raise MigrationRefused("transactional_connection_required")
    elif (
        connection.dialect.name != "postgresql"
        or receipt is not None
        or claim.raw is not body.raw
        or body.raw.closed
        or body.raw.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise MigrationRefused("transactional_connection_required")
    work.check()


def _body_xid(body: _LedgerBody) -> str:
    # The existing connection observer reserves both timeout setters and this
    # target. Liveness must be checked first: querying an idle handle starts a tx.
    _body_live(body)
    xid: Any = body.connection.exec_driver_sql("SELECT pg_current_xact_id()::text").scalar_one()
    _body_live(body)
    if type(xid) is not str or not xid.isascii() or not xid.isdecimal() or not 1 <= len(xid) <= 20:
        raise MigrationRefused("transactional_connection_required")
    return xid


def _register_ledger_body(
    connection: Connection,
    claim: LedgerEngineClaim,
    work: LedgerWork,
    receipt: CheckoutReceipt | None,
) -> None:
    root = connection.get_transaction()
    if connection in _BODIES or root is None or connection.closed or connection.invalidated:
        raise MigrationRefused("transactional_connection_required")
    body = _LedgerBody(
        connection,
        root,
        work._raw,
        connection.connection,
        claim,
        work,
        receipt,
        receipt.generation if receipt is not None else None,
        work._lease,
    )
    _body_live(body)
    if connection.dialect.name == "postgresql":
        body = replace(body, xid=_body_xid(body))
    _BODIES[connection] = body


def _revoke_ledger_body(connection: Connection) -> None:
    _BODIES.pop(connection, None)


def _require_ledger_body(connection: Connection) -> LedgerWork:
    """Require the same excluded body; this is cooperative, not authentication.

    SQLite cannot detect raw ROLLBACK/BEGIN on the same native handle. Supported
    callers must not issue raw transaction control, release locks, change
    role/search_path or use the connection concurrently.
    """
    if type(connection) is not Connection:
        raise MigrationRefused("transactional_connection_required")
    body = _BODIES.get(connection)
    if body is None:
        raise MigrationRefused("transactional_connection_required")
    _body_live(body)
    if body.xid is not None and _body_xid(body) != body.xid:
        raise MigrationRefused("transactional_connection_required")
    if _BODIES.get(connection) is not body:
        raise MigrationRefused("transactional_connection_required")
    return body.work


def _begin(connection: Connection, outcome: LedgerOutcome, work: LedgerWork) -> None:
    raw = connection.connection.driver_connection
    if raw is None:
        raise MigrationRefused("migration_database_failure")
    if connection.dialect.name == "sqlite":
        if getattr(raw, "autocommit", -1) != -1 or getattr(raw, "isolation_level", None) is None:
            raise MigrationRefused("transactional_connection_required")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        # FK setup already established SQLAlchemy's logical transaction. Reserve
        # before recording a native BEGIN attempt, including setter failures.
        work._prepare_target()
        outcome.begin_attempted = True
        cursor = raw.execute("BEGIN EXCLUSIVE")
        outcome.begun = True
        cursor.close()
        work.check()
        return
    if getattr(raw, "autocommit", None) is not False:
        raise MigrationRefused("transactional_connection_required")
    work.reserve_ordinary(1)
    outcome.begin_attempted = True
    connection.begin()
    outcome.begun = True
    connection.exec_driver_sql("SET LOCAL search_path TO public,pg_temp")
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    acquired: bool = connection.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATOR_LOCK}
    ).scalar_one()
    if acquired is not True:
        raise MigrationRefused("migration_busy")
    tables: list[str] = list(
        connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "ORDER BY tablename LIMIT 21"
            )
        ).scalars()
    )
    if len(tables) > 20:
        raise MigrationRefused("schema_incompatible")
    _postgres_exclusion(connection, tables)
    if len(tables) > 17:
        schema_table_names(connection)


def _ordinary_error(error: BaseException) -> MigrationRefused:
    if isinstance(error, MigrationRefused):
        return error
    native = error.orig if isinstance(error, DBAPIError) else error
    if (isinstance(native, psycopg.Error) and native.sqlstate in {"55P03", "57014"}) or (
        isinstance(native, sqlite3.Error) and getattr(native, "sqlite_errorcode", None) in {5, 6, 9}
    ):
        return MigrationRefused("migration_busy")
    if isinstance(native, MigrationRefused):
        return native
    return MigrationRefused("migration_database_failure")


@contextmanager
def ledger_transaction(
    engine: Engine, outcome: LedgerOutcome, *, work: LedgerWork
) -> Iterator[Connection]:
    """Commit once; return only after acknowledgment and bounded owned cleanup."""
    if (
        type(outcome) is not LedgerOutcome
        or type(work) is not LedgerWork
        or outcome._used
        or any(
            type(getattr(outcome, item.name)) is not bool or getattr(outcome, item.name)
            for item in fields(outcome)
            if item.init
        )
    ):
        raise MigrationRefused("migration_database_failure")
    outcome._used = True
    work._consume()
    claim: LedgerEngineClaim | None = None
    connection: Connection | None = None
    receipt: CheckoutReceipt | None = None
    primary: BaseException | None = None
    interruption: BaseException | None = None
    resource_failure = False
    attached = False

    def cleanup_failure(error: BaseException) -> None:
        nonlocal primary, interruption, resource_failure
        resource_failure = True
        outcome.cleanup_failed = True
        if primary is None:
            primary = error
        if interruption is None and not isinstance(error, Exception):
            interruption = error

    def cleanup(kind: str, action: Callable[[], Any]) -> bool:
        try:
            work.observe_cleanup(kind)
        except BaseException as error:
            cleanup_failure(error)
        try:
            action()
        except BaseException as error:
            cleanup_failure(error)
            return False
        return True

    try:
        claim = claim_ledger_engine(engine, work)
        claim._begin_connect()
        connection, receipt = connect_owned(engine, control_attempt=work.observe_cleanup)
        work.check()
        if connection.dialect.name == "postgresql" and (
            connection.dialect.server_version_info or ()
        )[:1] != (16,):
            raise MigrationRefused("schema_incompatible")
        attached = True
        work._attach(connection)
        _begin(connection, outcome, work)
        try:
            _register_ledger_body(connection, claim, work, receipt)
            yield connection
        finally:
            _revoke_ledger_body(connection)
        work._prepare_target()
        outcome.commit_attempted = True
        connection.commit()
        outcome.commit_acknowledged = True
        work.check()
    except BaseException as error:
        primary = error
        if not isinstance(error, Exception):
            interruption = error
        if isinstance(error, SQLiteOwnershipError) and connection is None:
            verdict = error.verdict
            if verdict is not None and not verdict.clean:
                resource_failure = True
                outcome.cleanup_failed = True
    finally:
        if attached:
            try:
                work._detach()
            except BaseException as error:
                cleanup_failure(error)
                quarantine_owned(receipt)
        if connection is not None:
            if not outcome.commit_acknowledged and (
                outcome.begin_attempted or connection.in_transaction()
            ):
                outcome.rollback_attempted = True

                def rollback() -> None:
                    if connection is None or connection.invalidated:
                        raise MigrationRefused("ledger_outcome_uncertain")
                    connection.rollback()
                    outcome.rollback_acknowledged = True

                cleanup("rollback", rollback)
            if receipt is not None:
                # The skipped restore slot covers _cleanup's possible lease retry.
                if work.previous_timeout is not None and not outcome.cleanup_failed:
                    cleanup(
                        "restore",
                        lambda: work._raw.execute(f"PRAGMA busy_timeout={work.previous_timeout}"),
                    )
                if outcome.cleanup_failed:
                    quarantine_owned(receipt)
                cleanup("close", lambda: close_owned(connection, receipt))
                try:
                    finish_owned(connection, receipt, control_attempt=work.observe_cleanup)
                except BaseException as error:
                    cleanup_failure(error)
            else:
                closed = cleanup("close", connection.close)
                if not closed:
                    cleanup("discard", connection.invalidate)
                    cleanup("close", connection.close)
        # Retained PG raw identity survives failure before SQLAlchemy returns.
        if claim is not None and claim.raw is not None:

            def raw_close() -> None:
                claim.raw.close()
                if not claim.raw.closed:
                    raise MigrationRefused("ledger_outcome_uncertain")

            if not cleanup("raw_close", raw_close):
                cleanup("raw_close", raw_close)
        if primary is None:
            try:
                work.check()
            except BaseException as error:
                cleanup_failure(error)
        if claim is not None:
            # Decide cleanup truth while ownership is still held.
            try:
                release_ledger_engine(claim, clean=not resource_failure)
            except BaseException as error:
                cleanup_failure(error)
    if interruption is not None:
        raise interruption from None
    uncertain = (
        outcome.cleanup_failed
        or (outcome.commit_attempted and (primary is not None or not outcome.commit_acknowledged))
        or (outcome.rollback_attempted and not outcome.rollback_acknowledged)
    )
    if uncertain:
        raise MigrationRefused("ledger_outcome_uncertain") from None
    if primary is not None:
        raise _ordinary_error(primary) from None
