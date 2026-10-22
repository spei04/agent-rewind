"""Offline ledger transaction ownership; no provisioning or CLI activation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from ..sqlite_ownership import (
    CheckoutReceipt,
    SQLiteOwnershipError,
    close_owned,
    connect_owned,
    finish_owned,
    quarantine_owned,
)
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


def _begin(connection: Connection, outcome: LedgerOutcome, work: LedgerWork) -> None:
    raw = connection.connection.driver_connection
    if connection.dialect.name == "sqlite":
        if getattr(raw, "autocommit", -1) != -1 or getattr(raw, "isolation_level", None) is None:
            raise MigrationRefused("transactional_connection_required")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        outcome.begin_attempted = True
        connection.exec_driver_sql("BEGIN EXCLUSIVE")
        outcome.begun = True
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
    if isinstance(error, DBAPIError):
        if getattr(error.orig, "sqlstate", None) in {"55P03", "57014"} or getattr(
            error.orig, "sqlite_errorcode", None
        ) in {5, 6, 9}:
            return MigrationRefused("migration_busy")
        if isinstance(error.orig, MigrationRefused):
            return error.orig
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
        attached = True
        work._attach(connection)
        _begin(connection, outcome, work)
        yield connection
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
                if outcome.cleanup_failed or not outcome.begun:
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
        if claim is not None:
            # A typed body refusal with clean disposal does not poison the engine.
            try:
                release_ledger_engine(claim, clean=not resource_failure)
            except BaseException as error:
                cleanup_failure(error)
        if primary is None:
            try:
                work.check()
            except BaseException as error:
                outcome.cleanup_failed = True
                primary = error
                if not isinstance(error, Exception):
                    interruption = error
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
