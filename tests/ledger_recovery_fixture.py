"""Test-owned physical SQLite observations for recovery; no production fault hooks."""

import json
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import asdict

from ledger_operator_fixture import SQLiteTrace
from ledger_provisioning_fixture import assert_no_writes, snapshot
from sqlalchemy.engine import Connection

from agent_rewind import sqlite_ownership
from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest


class RecoveryWatch:
    def __init__(self, engine):
        self.engine = engine
        self.trace = SQLiteTrace()
        self.actions = []
        self.works = []
        self.outcomes = []
        self.markers = []
        self.faults = []
        self.command_boundary = None

    @property
    def work(self):
        assert len(self.works) == 1
        return self.works[0]

    @property
    def outcome(self):
        assert len(self.outcomes) == 1
        return self.outcomes[0]

    def owns(self, raw):
        return bool(self.works) and self.works[0]._raw is raw

    def mark(self, name, raw):
        self.markers.append((name, id(raw), len(self.trace.events)))

    def capture_command_exit(self):
        """Observe returned ownership before any caller disposal changes it."""
        raw = self.work._raw
        state = raw._ownership
        try:
            in_transaction = raw.in_transaction
        except sqlite3.ProgrammingError:
            raw_closed, in_transaction = True, None
        else:
            raw_closed = False
        receipt = state.receipt
        verdict = sqlite_ownership.cleanup_snapshot(receipt)
        self.mark("command.exit", raw)
        self.command_boundary = {
            "trace_end": len(self.trace.events),
            "raw_id": id(raw),
            "connection_closed": self.work._connection.closed,
            "checkedout": self.engine.pool.checkedout(),
            "raw_closed": raw_closed,
            "in_transaction": in_transaction,
            "ownership_closed": state.closed,
            "borrowed": state.borrowed,
            "tainted": state.tainted,
            "native_busy": state.native_busy,
            "unknown_callback": state.unknown_callback,
            "lease_present": state.lease is not None,
            "receipt_completed": receipt.completed,
            "receipt": asdict(verdict),
            "receipt_clean": verdict.clean,
        }

    def assert_single_attempt(self):
        assert len(self.works) == len(self.outcomes) == len(self.trace.raws) == 1
        assert self.work._raw is self.trace.raws[0]
        assert self.trace.sql().count("BEGIN EXCLUSIVE") == 1
        assert self.work.prepaid_bootstrap == 12 and self.work.prepaid_cleanup == 8
        assert 0 < self.work.observed_ordinary <= 2028
        boundary = self.command_boundary
        assert boundary["raw_id"] == id(self.work._raw)
        assert boundary["connection_closed"] and boundary["checkedout"] == 0
        assert not boundary["native_busy"] and not boundary["unknown_callback"]
        assert not boundary["lease_present"]
        if self.outcome.cleanup_failed:
            # Cleanup-fault cases must be quarantined and physically closed by
            # the service itself, before the harness's always-run disposal.
            assert boundary["tainted"] and boundary["raw_closed"]
            assert boundary["ownership_closed"] and boundary["receipt"]["failed"]
            assert any(
                name == "raw.close.native_ack" and position <= boundary["trace_end"]
                for name, _, position in self.markers
            )
        else:
            assert boundary["receipt_completed"] and boundary["receipt_clean"]
            if not boundary["raw_closed"]:
                # A clean QueuePool return intentionally keeps an idle handle.
                assert boundary["in_transaction"] is False
                assert not boundary["borrowed"] and not boundary["tainted"]
        assert not any(sql.startswith(("SAVEPOINT", "ROLLBACK TO")) for sql in self.trace.sql())
        # This final closure is a separate harness-cleanup postcondition.
        for raw in self.trace.raws:
            try:
                raw.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                pass
            else:
                raise AssertionError("owned physical connection remained open")

    def record(self, record_property, label):
        record_property(
            label,
            json.dumps(
                {
                    "outcomes": [asdict(item) for item in self.outcomes],
                    "work": [
                        {
                            "ordinary": item.observed_ordinary,
                            "timeout_seconds": item.timeout_seconds,
                            "cleanup": item.cleanup_observations,
                        }
                        for item in self.works
                    ],
                    "markers": self.markers,
                    "faults": self.faults,
                    "native_trace": self.trace.events,
                    "native_authorizer": self.actions,
                    "command_boundary": self.command_boundary,
                }
            ),
        )


@contextmanager
def observe_command(
    fixture,
    monkeypatch,
    record_property,
    *,
    label,
    commit_fault=None,
    rollback_fault=None,
    body_error=None,
    close_error=None,
):
    """Scope every injection to one command engine/raw, then restore all delegates."""
    engine = fixture.case.operator_engine()
    watch = RecoveryWatch(engine)
    original_work, original_outcome = ledger_service.LedgerWork, ledger_service.LedgerOutcome
    original_commit = sqlite_ownership._TrackedSQLite.commit
    original_rollback = sqlite_ownership._TrackedSQLite._native_rollback
    original_close = Connection.close
    original_native_close = sqlite_ownership._TrackedSQLite._native_close
    original_write = ledger_service._write

    def work(timeout):
        item = original_work(timeout)
        watch.works.append(item)
        return item

    def outcome():
        item = original_outcome()
        watch.outcomes.append(item)
        return item

    def connect(*args, **kwargs):
        raw = watch.trace.connect(*args, **kwargs)

        def authorize(action, first, second, database, trigger):
            watch.actions.append((action, first, second, database, trigger))
            return sqlite3.SQLITE_OK

        raw.set_authorizer(authorize)
        return raw

    def commit(raw):
        if not watch.owns(raw):
            return original_commit(raw)
        watch.mark("commit.before_native", raw)
        if commit_fault == "before":
            watch.faults.append("commit.before")
            raise RuntimeError("controlled pre-delegation COMMIT failure")
        result = original_commit(raw)
        watch.mark("commit.native_ack", raw)
        if commit_fault == "after":
            watch.faults.append("commit.after")
            raise RuntimeError("controlled lost COMMIT acknowledgement")
        return result

    def rollback(raw):
        selected = watch.owns(raw) and watch.outcome.rollback_attempted
        if selected:
            watch.mark("rollback.before_native", raw)
            if rollback_fault == "before" and "rollback.before" not in watch.faults:
                watch.faults.append("rollback.before")
                raise RuntimeError("controlled pre-delegation ROLLBACK failure")
        result = original_rollback(raw)
        if selected:
            watch.mark("rollback.native_ack", raw)
            if rollback_fault == "after" and "rollback.after" not in watch.faults:
                watch.faults.append("rollback.after")
                raise RuntimeError("controlled lost ROLLBACK acknowledgement")
        return result

    def native_close(raw):
        selected = watch.owns(raw)
        if selected:
            watch.mark("raw.close.before_native", raw)
        result = original_native_close(raw)
        if selected:
            watch.mark("raw.close.native_ack", raw)
        return result

    def close(connection):
        selected = connection.engine is engine
        raw = watch.work._raw if selected else None
        if selected:
            watch.mark("connection.close.before", raw)
        result = original_close(connection)
        if selected:
            watch.mark("connection.close.return", raw)
            if close_error is not None and "close.after" not in watch.faults:
                watch.faults.append("close.after")
                raise close_error
        return result

    def write(connection, name, values):
        result = original_write(connection, name, values)
        if connection.engine is engine and name == "progress.insert" and body_error is not None:
            # The trace must independently contain the native INSERT before this marker.
            watch.mark("progress.insert.return", connection.connection.driver_connection)
            watch.faults.append("body.after_progress")
            raise body_error
        return result

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        patch.setattr(ledger_service, "LedgerWork", work)
        patch.setattr(ledger_service, "LedgerOutcome", outcome)
        patch.setattr(ledger_service, "_write", write)
        patch.setattr(sqlite_ownership._TrackedSQLite, "commit", commit)
        patch.setattr(sqlite_ownership._TrackedSQLite, "_native_rollback", rollback)
        patch.setattr(sqlite_ownership._TrackedSQLite, "_native_close", native_close)
        patch.setattr(Connection, "close", close)
        watch.trace.previous_profile = sys.getprofile()
        sys.setprofile(watch.trace.profile)
        try:
            yield watch
        finally:
            try:
                try:
                    watch.capture_command_exit()
                finally:
                    watch.trace.phase = "harness-dispose"
                    engine.dispose()
            finally:
                sys.setprofile(watch.trace.previous_profile)
                watch.record(record_property, label)


def fresh_reentry(fixture, manifest, monkeypatch, record_property, *, previous=None):
    """Inspect through a distinct engine with a real zero-DML observer."""
    before = snapshot(fixture.case.path)
    watch = None

    def forbidden(*args, **kwargs):
        raise AssertionError("fresh classification attempted writer work")

    try:
        with (
            observe_command(fixture, monkeypatch, record_property, label="fresh_reentry") as watch,
            monkeypatch.context() as patch,
        ):
            if previous is not None:
                assert watch.engine is not previous.engine
            for name in (
                "initialize_ledger",
                "_upgrade",
                "_prepare_ledger",
                "_provenance",
                "_write",
            ):
                patch.setattr(ledger_service, name, forbidden)
            result = ledger_service._inspect_ledger_reentry(
                watch.engine, validate_ledger_manifest(manifest)
            )
    finally:
        if watch is not None:
            watch.assert_single_attempt()
            assert_no_writes(watch.actions)
            assert not watch.outcome.cleanup_failed
            if previous is not None:
                assert watch.work._raw is not previous.work._raw
        assert snapshot(fixture.case.path) == before
    return result, watch
