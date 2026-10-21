"""Owned bounded admission transactions with explicit observed outcomes.

A rollback acknowledgment never erases a prior commit attempt. This state is
in-memory evidence only; after restart durable commit_pending always requires
SQL-only reconciliation. No automatic retry or publication policy lives here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.engine import Connection, Engine

from .request_authority import ActionForbidden
from .request_identity import IdentityInvalid
from .scoped_lineage import ResourceNotFound
from .sqlite_ownership import (
    CheckoutReceipt,
    close_owned,
    connect_owned,
    finish_owned,
    quarantine_owned,
)

AdmissionCode = Literal[
    "invalid_request",
    "idempotency_conflict",
    "dependency_unavailable",
    "schema_incompatible",
    "outcome_uncertain",
]


class AdmissionError(RuntimeError):
    """Finite public vocabulary; never retain driver or submitted text."""

    def __init__(self, code: AdmissionCode):
        self.code = code
        super().__init__(code)


class TransactionWork(Protocol):
    """Optional request-owned accounting; no engine/global listeners.

    Cleanup accounting must never prevent native cleanup. detach removes only
    owned hooks; finish checks elapsed time after native close. A failed detach
    requires physical discard. Existing admission callers pass no work object.
    """

    def attach(self, connection: Connection) -> None: ...
    def setup_complete(self) -> None: ...
    def remaining_timeouts_ms(self) -> tuple[int, int]: ...
    def check(self) -> None: ...
    def control_attempt(
        self, kind: Literal["begin", "commit", "rollback", "close", "discard", "restore"]
    ) -> None: ...
    def detach(self) -> None: ...
    def finish(self) -> None: ...


@dataclass
class TransactionOutcome:
    begun: bool = False
    commit_attempted: bool = False
    commit_acknowledged: bool = False
    rollback_attempted: bool = False
    rollback_acknowledged: bool = False
    cleanup_failed: bool = False

    @property
    def confirmed_precommit_rollback(self) -> bool:
        return self.begun and not self.commit_attempted and self.rollback_acknowledged


def _discard(connection: Connection) -> None:
    # The original fixed failure remains primary. A close is still attempted.
    with suppress(Exception):
        connection.invalidate()


def _begin(connection: Connection, work: TransactionWork | None = None) -> int | None:
    def discard_setup() -> None:
        # The work owner detaches first, then records/discards in its finally.
        # Do not let a setup disposal fault replace the original setup error.
        if work is None:
            _discard(connection)

    raw = connection.connection.driver_connection
    dialect = connection.dialect.name
    supported = (
        dialect == "postgresql"
        and getattr(raw, "autocommit", None) is False
        and getattr(getattr(raw, "info", None), "transaction_status", None) == 0
    ) or (
        dialect == "sqlite"
        and getattr(raw, "isolation_level", None) is not None
        and getattr(raw, "autocommit", -1) == -1
        and getattr(raw, "in_transaction", True) is False
    )
    if connection.in_transaction() or not supported:
        discard_setup()
        raise AdmissionError("dependency_unavailable")
    if dialect == "sqlite":
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            discard_setup()
            raise AdmissionError("dependency_unavailable")
        previous: object = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        if type(previous) is not int or previous < 0:
            discard_setup()
            raise AdmissionError("dependency_unavailable")
        try:
            lock_ms = work.remaining_timeouts_ms()[1] if work is not None else 3000
            connection.exec_driver_sql(f"PRAGMA busy_timeout={lock_ms}")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        except BaseException:
            discard_setup()
            raise
        return previous
    if work is not None:
        work.control_attempt("begin")
    connection.begin()
    connection.exec_driver_sql("SET LOCAL search_path TO public,pg_temp")
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    if work is None:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
    else:
        statement_ms, lock_ms = work.remaining_timeouts_ms()
        connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{lock_ms}ms'")
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
    return None


@contextmanager
def admission_transaction(
    engine: Engine, outcome: TransactionOutcome, *, work: TransactionWork | None = None
) -> Iterator[Connection]:
    """Preserve typed denial/primary failure through bounded rollback and cleanup."""
    if type(outcome) is not TransactionOutcome or outcome != TransactionOutcome():
        raise AdmissionError("dependency_unavailable")
    connection = None
    receipt: CheckoutReceipt | None = None
    previous_timeout = None
    primary: BaseException | None = None
    attached = False
    cleanup_interruption: BaseException | None = None
    discard_retry_used = False

    def cleanup_failure(error: BaseException) -> None:
        nonlocal primary, cleanup_interruption
        outcome.cleanup_failed = True
        if cleanup_interruption is None and not isinstance(error, Exception):
            cleanup_interruption = error
        if primary is None:
            primary = error

    def cleanup_attempt(kind: Literal["rollback", "close", "discard", "restore"]) -> None:
        # Accounting is an observation, never permission to omit native cleanup.
        if work is not None:
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
            # One extra native discard attempt per phase, not per failure.
            if not discard_retry_used:
                discard_retry_used = True
                cleanup_attempt("discard")
                try:
                    connection.invalidate()
                except BaseException as error:
                    cleanup_failure(error)

    try:
        if work is not None:
            work.check()
        connection, receipt = connect_owned(
            engine, control_attempt=work.control_attempt if work is not None else None
        )
        if work is not None:
            attached = True  # partial attach still owns mandatory detach/finish
            work.attach(connection)
        previous_timeout = _begin(connection, work)
        outcome.begun = True
        if work is not None:
            work.setup_complete()
        yield connection
        if work is not None:
            work.check()
            work.control_attempt("commit")  # fresh native caps, before attempted
        outcome.commit_attempted = True
        connection.commit()
        outcome.commit_acknowledged = True
        if work is not None:
            work.check()
    except BaseException as error:
        primary = error
    finally:
        had_primary = primary is not None
        # Every phase remains bounded and independent, even after interruption.
        # The first body/setup failure stays primary through disposal failures.
        if attached and work is not None:
            try:
                work.detach()
            except BaseException as error:
                cleanup_failure(error)
                if receipt is None:
                    discard()
                else:
                    quarantine_owned(receipt)
        if connection is not None and receipt is not None:
            if primary is not None and outcome.begun and not outcome.commit_acknowledged:
                outcome.rollback_attempted = True
                cleanup_attempt("rollback")
                try:
                    if connection.invalidated:
                        raise AdmissionError("outcome_uncertain")
                    connection.rollback()
                    outcome.rollback_acknowledged = True
                except BaseException as error:
                    cleanup_failure(error)
            if previous_timeout is not None and not outcome.cleanup_failed:
                cleanup_attempt("restore")
                try:
                    raw = connection.connection.driver_connection
                    if raw is None:
                        raise AdmissionError("outcome_uncertain")
                    raw.execute(f"PRAGMA busy_timeout={previous_timeout}")
                except BaseException as error:
                    cleanup_failure(error)
            if outcome.cleanup_failed or not outcome.begun:
                quarantine_owned(receipt)
            cleanup_attempt("close")
            try:
                close_owned(connection, receipt)
            except BaseException as error:
                cleanup_failure(error)
            try:
                finish_owned(
                    connection,
                    receipt,
                    control_attempt=work.control_attempt if work is not None else None,
                )
            except BaseException as error:
                cleanup_failure(error)
        elif connection is not None:
            if work is not None and not outcome.begun and not connection.invalidated:
                discard()
            if primary is not None and outcome.begun and not outcome.commit_acknowledged:
                outcome.rollback_attempted = True
                cleanup_attempt("rollback")
                try:
                    if connection.invalidated:
                        raise AdmissionError("outcome_uncertain")
                    connection.rollback()
                    outcome.rollback_acknowledged = True
                except BaseException as error:
                    cleanup_failure(error)
                    discard()
            if previous_timeout is not None and not connection.invalidated:
                cleanup_attempt("restore")
                try:
                    raw = connection.connection.driver_connection
                    if raw is None:
                        raise AdmissionError("outcome_uncertain")
                    raw.execute(f"PRAGMA busy_timeout={previous_timeout}")
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
        if attached and work is not None:
            try:
                work.finish()
            except BaseException as error:
                cleanup_failure(error)
    if not had_primary and cleanup_interruption is not None:
        raise cleanup_interruption from None
    if primary is not None and (
        not isinstance(primary, Exception)
        or isinstance(primary, IdentityInvalid | ResourceNotFound | ActionForbidden)
    ):
        raise primary from None
    uncertain = outcome.commit_attempted or (
        outcome.rollback_attempted and not outcome.rollback_acknowledged
    )
    if primary is not None:
        # Known authority and conflict decisions survive secondary cleanup faults;
        # dependency failures cannot erase an ambiguous transaction.
        if isinstance(primary, AdmissionError) and (
            primary.code != "dependency_unavailable" or not uncertain
        ):
            raise primary from None
        raise AdmissionError(
            "outcome_uncertain" if uncertain else "dependency_unavailable"
        ) from None
    if outcome.cleanup_failed:
        raise AdmissionError(
            "outcome_uncertain" if outcome.commit_attempted else "dependency_unavailable"
        ) from None
