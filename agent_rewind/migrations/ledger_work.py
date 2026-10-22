"""Bounded work for the explicit ledger operator, without runtime activation."""

from __future__ import annotations

import math
from time import monotonic
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection

from ..sqlite_ownership import ProgressLease, acquire_progress
from .schema import MigrationRefused

BOOTSTRAP_ALLOWANCE = 12
CLEANUP_ALLOWANCE = 8
MAX_ORDINARY = 2028
MAX_SECONDS = 120
_CLEANUP_KINDS = {"detach", "rollback", "restore", "close", "discard", "raw_close"}


class LedgerWork:
    """One invocation: prepaid lifecycle units and separately reserved SQL units."""

    def __init__(self, timeout_seconds: int = 5) -> None:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
            raise MigrationRefused("invalid_lock_timeout")
        self.timeout_seconds = timeout_seconds
        self.prepaid_bootstrap = 0
        self.prepaid_cleanup = 0
        self.observed_ordinary = 0
        self.cleanup_observations: list[str] = []
        self._deadline = monotonic() + MAX_SECONDS
        self._used = False
        self._claimed = False
        self._connection: Connection | None = None
        self._raw: Any = None
        self._lease: ProgressLease | None = None
        self._listeners: list[tuple[str, Any]] = []
        self._attached = False
        self._detached = False
        self.previous_timeout: int | None = None

    def check(self) -> None:
        if (
            type(self.observed_ordinary) is not int
            or not 0 <= self.observed_ordinary <= MAX_ORDINARY
            or (self.prepaid_bootstrap, self.prepaid_cleanup)
            != ((BOOTSTRAP_ALLOWANCE, CLEANUP_ALLOWANCE) if self._claimed else (0, 0))
        ):
            raise MigrationRefused("ledger_limit_exceeded")
        self.remaining_timeouts_ms()

    def remaining_timeouts_ms(self) -> tuple[int, int]:
        remaining = self._deadline - monotonic()
        if not math.isfinite(remaining) or remaining < 0.001:
            raise MigrationRefused("migration_busy")
        milliseconds = math.floor(remaining * 1000)
        return (
            min(self.timeout_seconds * 4000, milliseconds),
            min(self.timeout_seconds * 1000, milliseconds),
        )

    def reserve_ordinary(self, count: int) -> None:
        self.check()
        if type(count) is not int or count < 1 or self.observed_ordinary + count > MAX_ORDINARY:
            raise MigrationRefused("ledger_limit_exceeded")
        self.observed_ordinary += count

    def observe_cleanup(self, kind: str) -> None:
        if kind not in _CLEANUP_KINDS or len(self.cleanup_observations) >= CLEANUP_ALLOWANCE:
            raise MigrationRefused("ledger_limit_exceeded")
        self.cleanup_observations.append(kind)

    def _consume(self) -> None:
        if self._used:
            raise MigrationRefused("migration_database_failure")
        self._used = True
        self.check()

    def _prepay(self) -> None:
        if not self._used or self._claimed:
            raise MigrationRefused("migration_database_failure")
        self.check()
        self.prepaid_bootstrap = BOOTSTRAP_ALLOWANCE
        self.prepaid_cleanup = CLEANUP_ALLOWANCE
        self._claimed = True

    def _prepare_target(self) -> None:
        """Reserve setters and target together; failures never refund work."""
        connection = self._connection
        if connection is None or connection.invalidated or connection.closed or self._detached:
            raise MigrationRefused("migration_database_failure")
        statement_ms, lock_ms = self.remaining_timeouts_ms()
        if connection.dialect.name == "sqlite":
            self.reserve_ordinary(2)
            self._raw.execute(f"PRAGMA busy_timeout={lock_ms}")
        else:
            self.reserve_ordinary(3)
            with self._raw.cursor() as cursor:
                cursor.execute(f"SET LOCAL statement_timeout = '{statement_ms}ms'")
                cursor.execute(f"SET LOCAL lock_timeout = '{lock_ms}ms'")

    def _before(
        self,
        connection: Connection,
        _cursor: Any,
        _statement: str,
        parameters: Any,
        _context: Any,
        many: bool,
    ) -> None:
        if connection is not self._connection or many:
            raise MigrationRefused("ledger_limit_exceeded")
        if not isinstance(parameters, tuple | list | dict) or len(parameters) > 16:
            raise MigrationRefused("ledger_limit_exceeded")
        self._prepare_target()

    def _after(self, *_args: Any) -> None:
        self.check()

    def _progress(self) -> int:
        try:
            self.check()
        except MigrationRefused:
            return 1
        return 0

    def _attach(self, connection: Connection) -> None:
        if self._attached or not self._claimed:
            raise MigrationRefused("migration_database_failure")
        self._attached = True  # partial installation still owns cleanup
        self._connection = connection
        if connection.invalidated or connection.closed:
            raise MigrationRefused("migration_database_failure")
        self._raw = connection.connection.driver_connection
        if connection.dialect.name == "sqlite":
            self._lease = acquire_progress(connection, owner=self)
            self.reserve_ordinary(1)
            self._lease.install(self._progress, 1000)
            # Read the value we must restore before applying our first setter.
            self.reserve_ordinary(1)
            cursor = self._raw.execute("PRAGMA busy_timeout")
            try:
                row = cursor.fetchone()
            finally:
                cursor.close()
            if row is None or len(row) != 1 or type(row[0]) is not int or row[0] < 0:
                raise MigrationRefused("migration_database_failure")
            self.previous_timeout = row[0]
        for name, callback in (
            ("before_cursor_execute", self._before),
            ("after_cursor_execute", self._after),
        ):
            self._listeners.append((name, callback))
            event.listen(connection, name, callback)
        self.check()

    def _detach(self) -> None:
        if self._detached:
            raise MigrationRefused("migration_database_failure")
        self._detached = True
        first: BaseException | None = None
        interruption: BaseException | None = None
        if self._attached:
            try:
                self.observe_cleanup("detach")
            except BaseException as error:
                first = error
            if self._lease is not None:
                try:
                    self._lease.release()
                except BaseException as error:
                    if first is None:
                        first = error
                    if not isinstance(error, Exception):
                        interruption = error
            for name, callback in self._listeners:
                try:
                    if self._connection is not None and event.contains(
                        self._connection, name, callback
                    ):
                        event.remove(self._connection, name, callback)
                except BaseException as error:
                    if first is None:
                        first = error
                    if interruption is None and not isinstance(error, Exception):
                        interruption = error
        if interruption is not None:
            raise interruption
        if first is not None:
            raise first
