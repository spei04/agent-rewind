"""Observe disposable PostgreSQL test sessions without becoming a target writer."""

import json
import math
import time
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from agent_rewind.migrations.schema import MigrationRefused


def wait_for_database_drain(control: Engine, database: str, *, timeout: float = 5) -> None:
    """Wait for observed server-side exit, never retry a migration or terminate a session.

    The control connection uses a different database and fresh autocommit snapshots.
    This bounds polling on the responsive synthetic CI server, not arbitrary network I/O.
    """
    if control.url.database == database or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Invalid synthetic database drain observation")
    deadline = time.monotonic() + timeout
    with control.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("SET statement_timeout = '1s'")
        while True:
            sessions = connection.execute(
                text("SELECT pid FROM pg_stat_activity WHERE datname=:database LIMIT 65"),
                {"database": database},
            ).all()
            if not sessions:
                return
            if len(sessions) > 64:
                raise AssertionError("Synthetic database session observation exceeds its bound")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("Synthetic database sessions did not drain before deadline")
            # A polling interval controls load; only observed absence establishes drain.
            time.sleep(min(0.01, remaining))


_BACKEND_TYPES = frozenset(
    {"client backend", "parallel worker", "autovacuum worker", "logical replication worker"}
)
_BACKEND_STATES = frozenset(
    {
        "active",
        "idle",
        "idle in transaction",
        "idle in transaction (aborted)",
        "fastpath function call",
        "disabled",
    }
)


def _safe_backend_value(value: object, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and value in allowed else "other"


def observe_exclusion_failure(
    check: Callable[[Connection, list[str]], None], connection: Connection, tables: list[str]
) -> None:
    """Add bounded synthetic-test evidence without changing a migration decision.

    This later observation is not the snapshot that caused refusal. It runs on
    the same still-open transaction, only after the production check has refused.
    A local statement timeout bounds responsive-server work, not network I/O.
    """
    try:
        check(connection, tables)
    except MigrationRefused as refused:
        if refused.code == "writers_not_drained":
            try:
                connection.exec_driver_sql("SET LOCAL statement_timeout = '1s'")
                connection.exec_driver_sql("SELECT pg_catalog.pg_stat_clear_snapshot()").close()
                rows = connection.execute(
                    text(
                        "SELECT backend_type,state FROM pg_catalog.pg_stat_activity "
                        "WHERE datname=pg_catalog.current_database() "
                        "AND pid<>pg_catalog.pg_backend_pid() LIMIT 9"
                    )
                ).fetchmany(9)
                observation = {
                    "rows": [
                        {
                            "backend_type": _safe_backend_value(row[0], _BACKEND_TYPES),
                            "state": _safe_backend_value(row[1], _BACKEND_STATES),
                        }
                        for row in rows[:8]
                    ],
                    "more_than_eight": len(rows) > 8,
                }
                note = "post_refusal_backend_observation=" + json.dumps(
                    observation, sort_keys=True, separators=(",", ":")
                )
            except Exception:
                # Diagnostic errors must never replace or expose details beyond
                # the production refusal, including an interrupted transaction.
                note = "post_refusal_backend_observation=unavailable"
            refused.add_note(note)
        raise
