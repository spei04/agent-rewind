"""Observe disposable PostgreSQL test sessions without becoming a target writer."""

import math
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine


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
