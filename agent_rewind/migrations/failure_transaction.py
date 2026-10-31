"""Owned offline transaction for the dormant failure-evidence migration.

This boundary excludes writers and accepts only the physical predecessor or
successor table inventory. It does not establish a revision, validate the full
catalog, rewrite adoption history, or activate a producer.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Connection, Engine

from .ledger_transaction import LedgerOutcome, _begin_native, _owned_transaction
from .ledger_work import LedgerWork
from .schema import LEDGER, MigrationRefused, installed_profile
from .service import _postgres_exclusion


def _begin(connection: Connection, outcome: LedgerOutcome, work: LedgerWork) -> None:
    _begin_native(connection, outcome, work)
    name = connection.dialect.name
    predecessor = sorted(
        table for table in installed_profile(name, LEDGER) if not table.startswith("$")
    )
    if len(predecessor) != 20 or "job_failure_evidence" in predecessor:
        raise MigrationRefused("schema_incompatible")
    # Native length gating precedes driver transfer. The 22nd row is an
    # overflow witness; no unknown table is removed before exact comparison.
    query = (
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 22"
        if name == "postgresql"
        else (
            "SELECT CASE WHEN length(CAST(name AS BLOB))<=128 THEN name END "
            "FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' "
            "ORDER BY name LIMIT 22"
        )
    )
    rows = connection.exec_driver_sql(query).all()
    if len(rows) not in (20, 21) or any(type(row[0]) is not str for row in rows):
        raise MigrationRefused("schema_incompatible")
    tables = [row[0] for row in rows]
    if tables != predecessor and tables != sorted([*predecessor, "job_failure_evidence"]):
        raise MigrationRefused("schema_incompatible")
    if name == "postgresql":
        _postgres_exclusion(connection, tables)
    work.check()


@contextmanager
def failure_transaction(
    engine: Engine, outcome: LedgerOutcome, *, work: LedgerWork
) -> Iterator[Connection]:
    """Yield only the same owned, excluded body; retain exact ACK/cleanup truth."""
    with _owned_transaction(engine, outcome, work=work, begin=_begin) as connection:
        yield connection
