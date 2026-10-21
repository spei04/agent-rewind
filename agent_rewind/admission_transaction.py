"""Owned bounded admission transactions with explicit observed outcomes.

A rollback acknowledgment never erases a prior commit attempt. This state is
in-memory evidence only; after restart durable commit_pending always requires
SQL-only reconciliation. No automatic retry or publication policy lives here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.engine import Connection, Engine

from .request_authority import ActionForbidden
from .request_identity import IdentityInvalid
from .scoped_lineage import ResourceNotFound

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


def _begin(connection: Connection) -> int | None:
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
        _discard(connection)
        raise AdmissionError("dependency_unavailable")
    if dialect == "sqlite":
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            _discard(connection)
            raise AdmissionError("dependency_unavailable")
        previous: object = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        if type(previous) is not int or previous < 0:
            _discard(connection)
            raise AdmissionError("dependency_unavailable")
        try:
            connection.exec_driver_sql("PRAGMA busy_timeout=3000")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        except BaseException:
            _discard(connection)
            raise
        return previous
    connection.begin()
    connection.exec_driver_sql("SET LOCAL search_path TO public,pg_temp")
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    connection.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
    return None


@contextmanager
def admission_transaction(engine: Engine, outcome: TransactionOutcome) -> Iterator[Connection]:
    """Preserve typed denial/primary failure through bounded rollback and cleanup."""
    if type(outcome) is not TransactionOutcome or outcome != TransactionOutcome():
        raise AdmissionError("dependency_unavailable")
    connection = None
    previous_timeout = None
    primary: BaseException | None = None
    try:
        connection = engine.connect()
        previous_timeout = _begin(connection)
        outcome.begun = True
        yield connection
        outcome.commit_attempted = True
        connection.commit()
        outcome.commit_acknowledged = True
    except BaseException as error:
        primary = error
        if connection is not None and outcome.begun and not outcome.commit_acknowledged:
            outcome.rollback_attempted = True
            try:
                if connection.invalidated:
                    raise AdmissionError("outcome_uncertain")
                connection.rollback()
                outcome.rollback_acknowledged = True
            except Exception:
                _discard(connection)
    finally:
        if connection is not None:
            try:
                if previous_timeout is not None and not connection.invalidated:
                    raw = connection.connection.driver_connection
                    if raw is None:
                        raise AdmissionError("outcome_uncertain")
                    raw.execute(f"PRAGMA busy_timeout={previous_timeout}")
                connection.close()
            except Exception:
                outcome.cleanup_failed = True
                _discard(connection)
                with suppress(Exception):
                    connection.close()
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
