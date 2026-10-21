"""Adapter-local native SQL work limits and read-only connection cleanup."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .errors import Fault
from .sqlite_ownership import (
    CheckoutReceipt,
    ProgressLease,
    close_owned,
    connect_owned,
    finish_owned,
    optional_progress,
    quarantine_owned,
)

MAX_STATEMENTS = 4096
MAX_SQL_SECONDS = 2.0
MAX_VM_INSTRUCTIONS = 20_000_000
VM_INTERVAL = 1000


@dataclass
class SQLWork:
    """Cumulative across this request's connections; never installed globally."""

    statements: int = 0
    seconds: float = 0.0
    instructions: int = 0
    started: float | None = None

    def remaining(self) -> float:
        active = 0.0 if self.started is None else time.monotonic() - self.started
        return MAX_SQL_SECONDS - self.seconds - active

    def before(self, *args: Any) -> None:
        self.statements += 1
        if self.statements > MAX_STATEMENTS or self.remaining() <= 0:
            raise Fault("dependency_unavailable")
        if self.started is None:
            self.started = time.monotonic()

    def after(self, *args: Any) -> None:
        # Keep the phase clock running through fetch/parse and subsequent SQL.
        # Counting non-I/O Python work conservatively avoids an unmetered lazy
        # SQLite fetch interval after after_cursor_execute.
        if self.remaining() <= 0:
            raise Fault("dependency_unavailable")

    def progress(self) -> int:
        self.instructions += VM_INTERVAL
        return int(self.instructions > MAX_VM_INSTRUCTIONS or self.remaining() <= 0)


@contextmanager
def listing_connection(engine: Engine, work: SQLWork) -> Iterator[Connection]:
    """Fresh READ COMMITTED statements, not a long snapshot or writer transaction.

    Native limits bound server/SQLite work, not arbitrary connect/network stalls.
    The existing engine owns connection/pool bounds. No background timeout thread.
    """
    connection: Connection | None = None
    raw: Any = None
    receipt: CheckoutReceipt | None = None
    lease: ProgressLease | None = None
    progress = False
    primary: BaseException | None = None
    cleanup_interruption: BaseException | None = None
    failed = False
    previous: tuple[int, int] | None = None
    listeners: list[tuple[str, Any]] = []
    entered = False
    broken = False
    dialect = engine.dialect.name

    def before(conn: Any, cursor: Any, *args: Any) -> None:
        work.before()
        remaining_ms = max(1, int(work.remaining() * 1000))
        if dialect == "sqlite":
            cursor.execute(f"PRAGMA busy_timeout={min(250, remaining_ms)}")
        if dialect == "postgresql":
            remaining_ms = max(1, int(work.remaining() * 1000))
            # Trusted integers only; use this owned cursor to avoid recursively
            # invoking SQLAlchemy's before_cursor_execute event.
            cursor.execute(f"SET LOCAL statement_timeout = {remaining_ms}")
            cursor.execute(f"SET LOCAL lock_timeout = {min(250, remaining_ms)}")

    try:
        connection, receipt = connect_owned(engine)
        lease = optional_progress(connection, owner=work)
        raw = connection.connection.driver_connection
        if dialect == "sqlite":
            if (
                not isinstance(raw, sqlite3.Connection)
                or getattr(raw, "autocommit", -1) != -1
                or raw.isolation_level is None
                or raw.in_transaction
                or sqlite3.sqlite_version_info < (3, 35, 0)
            ):
                connection.invalidate()
                raise Fault("dependency_unavailable")
            previous = (
                int(raw.execute("PRAGMA query_only").fetchone()[0]),
                int(raw.execute("PRAGMA busy_timeout").fetchone()[0]),
            )
            raw.execute("PRAGMA query_only=ON")
            raw.execute("PRAGMA busy_timeout=250")
            progress = True
            if lease is None:
                raw.set_progress_handler(work.progress, VM_INTERVAL)
            else:
                lease.install(work.progress, VM_INTERVAL)
        elif dialect == "postgresql" and engine.dialect.driver == "psycopg":
            if getattr(raw, "autocommit", None) is not False:
                connection.invalidate()
                raise Fault("dependency_unavailable")
            connection = connection.execution_options(isolation_level="READ COMMITTED")
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        else:
            connection.invalidate()
            raise Fault("dependency_unavailable")
        for name, callback in (
            ("before_cursor_execute", before),
            ("after_cursor_execute", work.after),
        ):
            # Track before registration: an injected/driver failure may happen
            # after a listener has already been attached.
            listeners.append((name, callback))
            event.listen(connection, name, callback)
        entered = True
        yield connection
    except BaseException as error:
        primary = error
        broken = isinstance(error, SQLAlchemyError | sqlite3.Error) or (
            not entered and isinstance(error, Exception) and not isinstance(error, Fault)
        )
    finally:

        def failure(error: BaseException) -> None:
            nonlocal failed, cleanup_interruption
            failed = True
            if cleanup_interruption is None and not isinstance(error, Exception):
                cleanup_interruption = error

        if connection is not None:
            # Acquire precedes effects; detach every installed owner before any
            # rollback/restore. Accounting or hook failure cannot skip close.
            for name, callback in listeners:
                try:
                    if event.contains(connection, name, callback):
                        event.remove(connection, name, callback)
                except BaseException as error:
                    failure(error)
            try:
                if lease is not None:
                    lease.release()
                elif progress:
                    raw.set_progress_handler(None, 0)
            except BaseException as error:
                failure(error)
            try:
                if not connection.invalidated:
                    connection.rollback()
                    if dialect == "sqlite" and previous is not None and not failed:
                        if raw.in_transaction:
                            raise Fault("dependency_unavailable")
                        raw.execute(f"PRAGMA query_only={previous[0]}")
                        raw.execute(f"PRAGMA busy_timeout={previous[1]}")
            except BaseException as error:
                failure(error)
            if broken or failed:
                if receipt is not None:
                    quarantine_owned(receipt)
                else:
                    try:
                        connection.invalidate()
                    except BaseException as error:
                        failure(error)
            try:
                close_owned(connection, receipt)
            except BaseException as error:
                failure(error)
                if receipt is None:
                    for action in (connection.invalidate, connection.close):
                        try:
                            action()
                        except BaseException as error:
                            failure(error)
            try:
                finish_owned(connection, receipt)
            except BaseException as error:
                failure(error)
        if work.started is not None:
            work.seconds += time.monotonic() - work.started
            work.started = None
    if primary is not None:
        if isinstance(primary, Fault) or not isinstance(primary, Exception):
            raise primary from None
        if broken:
            raise Fault("dependency_unavailable") from None
        raise primary from None
    if cleanup_interruption is not None:
        raise cleanup_interruption from None
    if failed or work.remaining() <= 0:
        raise Fault("dependency_unavailable") from None
