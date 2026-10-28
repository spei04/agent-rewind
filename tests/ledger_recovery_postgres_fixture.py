"""Actual PostgreSQL transaction boundaries for recovery; no product fault hooks."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict

import psycopg
from ledger_provisioning_postgres_fixture import native_snapshot
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool
from test_ledger_operator_postgres import PostgresTrace
from test_ledger_reader_native import (
    NativeParameterWatch,
    _assert_reviewed_ctes,
    _transaction_write_counters,
    _tuple_write_delta,
)
from test_run_projection_postgres import drain

from agent_rewind.migrations import ledger_engine, ledger_service, ledger_transaction
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest


class NativeRecoveryWatch:
    def __init__(self, engine, patch):
        self.engine = engine
        self.trace = PostgresTrace(patch)
        self.parameters = NativeParameterWatch(patch, self.trace)
        self.works, self.outcomes, self.claims = [], [], []
        self.markers, self.faults, self.physical, self.xids = [], [], [], []
        self.counters, self.observer_units = [], []
        self.command_boundary = None
        work_type, outcome_type = ledger_service.LedgerWork, ledger_service.LedgerOutcome
        claim_delegate = ledger_transaction.claim_ledger_engine

        def work(timeout):
            value = work_type(timeout)
            self.works.append(value)
            return value

        def outcome():
            value = outcome_type()
            self.outcomes.append(value)
            return value

        def claim(actual_engine, actual_work):
            value = claim_delegate(actual_engine, actual_work)
            if actual_engine is engine:
                self.claims.append(value)
            return value

        patch.setattr(ledger_service, "LedgerWork", work)
        patch.setattr(ledger_service, "LedgerOutcome", outcome)
        patch.setattr(ledger_transaction, "claim_ledger_engine", claim)

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
        raw = self.work._raw
        assert len(self.claims) == 1
        state = ledger_engine._REGISTRY[self.engine]
        self.mark("command.exit", raw)
        self.command_boundary = {
            "trace_end": len(self.trace.events),
            "raw_id": id(raw),
            "raw_closed": raw.closed,
            "connection_closed": self.work._connection.closed,
            "claim_released": self.claims[0].released,
            "claim_absent": state.claim is None,
            "engine_poisoned": state.poisoned,
        }

    def assert_single_attempt(self):
        assert len(self.works) == len(self.outcomes) == len(self.claims) == 1
        assert len(self.trace.handles) == 1
        raw = self.work._raw
        assert self.trace.handles[0] is self.claims[0].raw is raw
        assert isinstance(self.engine.pool, NullPool)
        assert self.claims[0].checked_out and self.claims[0].physical_attempted
        boundary = self.command_boundary
        assert boundary["raw_id"] == id(raw)
        assert boundary["raw_closed"] and boundary["connection_closed"]
        assert boundary["claim_released"] and boundary["claim_absent"]
        assert boundary["engine_poisoned"] is self.outcome.cleanup_failed
        # The actual physical close completed before caller disposal, including
        # cleanup failures. Closing an already-closed handle is not this witness.
        assert any(
            row["action"] == "close"
            and not row["closed_before"]
            and row["closed_after"]
            and row["trace_end"] <= boundary["trace_end"]
            for row in self.physical
        )
        assert all(
            phase != "harness-dispose" for phase, *_ in self.trace.events[: boundary["trace_end"]]
        )
        assert raw.closed and self.work._detached
        assert all(row["raw_id"] == id(raw) for row in self.physical)
        assert all(row[1] == id(raw) for row in self.markers)
        events = [event for event in self.trace.events if event[2] == id(raw)]
        assert sorted(event[1] for event in self.trace.events if event[2] is None) == [
            "connect-call",
            "internal-connect",
        ]
        assert sum(event[1] == "connect-return" for event in events) == 1
        commands = [
            sql.strip().upper()
            for phase, kind, _, sql in events
            if kind == "command" and phase != "bootstrap"
        ]
        assert commands.count("BEGIN") == 1
        assert not any(sql.startswith(("SAVEPOINT", "ROLLBACK TO")) for sql in commands)
        assert [
            sql.strip().upper()
            for phase, kind, _, sql in events
            if kind == "command" and phase == "bootstrap"
        ] == ["BEGIN", "ROLLBACK"]
        calls = [
            (phase, raw_id, hashlib.sha256(sql.encode()).hexdigest())
            for phase, kind, raw_id, sql in events
            if kind == "sql-call"
        ]
        receipts = self.parameters.receipts
        assert (
            calls
            and [(row["phase"], row["raw_id"], row["sql_sha256"]) for row in receipts] == calls
        )
        assert all(row["outcome"] == "return" for row in receipts)
        assert all(
            type(row["parameter_count"]) is int and 0 <= row["parameter_count"] <= 16
            for row in receipts
        )
        ordinary = [
            sql for phase, kind, _, sql in events if phase == "ordinary" and kind == "sql-call"
        ]
        body = ordinary[:-2] if self.outcome.commit_attempted else ordinary
        assert len(body) % 3 == 0
        for offset in range(0, len(body), 3):
            assert body[offset].startswith("SET LOCAL statement_timeout = '")
            assert body[offset + 1].startswith("SET LOCAL lock_timeout = '")
            assert not body[offset + 2].startswith("SET LOCAL statement_timeout = '")
        if self.outcome.commit_attempted:
            assert ordinary[-2].startswith("SET LOCAL statement_timeout = '")
            assert ordinary[-1].startswith("SET LOCAL lock_timeout = '")
        assert self.work.observed_ordinary == 1 + len(ordinary) + int(self.outcome.commit_attempted)
        assert self.work.prepaid_bootstrap == 12 and self.work.prepaid_cleanup == 8
        assert 0 < self.work.observed_ordinary <= 2028
        assert len(self.work.cleanup_observations) <= 8
        assert self.xids and {row[0] for row in self.xids} == {id(raw)}
        assert len({row[1] for row in self.xids}) == 1
        assert all(
            type(row[1]) is str and row[1].isascii() and row[1].isdecimal() for row in self.xids
        )
        assert all(row[2] < boundary["trace_end"] for row in self.xids)

    def assert_no_writes(self):
        assert self.observer_units == [6, 3]
        assert self.counters == [{}], "native tuple writes observed"
        commands = self.trace.sql("ordinary")
        _assert_reviewed_ctes(commands)
        assert commands and all(
            sql.lstrip().upper().startswith(("SELECT", "WITH", "SET", "SHOW", "LOCK"))
            for sql in commands
        ), "native write-capable statement observed"

    def record(self, record_property, label):
        record_property(
            label,
            json.dumps(
                {
                    "outcomes": [asdict(row) for row in self.outcomes],
                    "work": [
                        {
                            "ordinary": row.observed_ordinary,
                            "timeout_seconds": row.timeout_seconds,
                            "cleanup": row.cleanup_observations,
                        }
                        for row in self.works
                    ],
                    "markers": self.markers,
                    "faults": self.faults,
                    "physical": self.physical,
                    "xids": self.xids,
                    "native_trace": self.trace.events,
                    "native_parameters": self.parameters.receipts,
                    "observer_units": self.observer_units,
                    "tuple_deltas": [
                        [
                            {"relation": list(key), "delta": list(value)}
                            for key, value in sorted(delta.items())
                        ]
                        for delta in self.counters
                    ],
                    "command_boundary": self.command_boundary,
                }
            ),
        )


@contextmanager
def observe_command(
    fixture,
    pg,
    monkeypatch,
    record_property,
    *,
    label,
    commit_fault=None,
    rollback_fault=None,
    body_error=None,
    close_error=None,
    observe_writes=False,
    injected_update=None,
):
    engine = fixture.case.operator_engine()
    try:
        with monkeypatch.context() as patch:
            watch = NativeRecoveryWatch(engine, patch)
            delegates = {
                name: getattr(psycopg.Connection, name) for name in ("commit", "rollback", "close")
            }
            close_delegate = Connection.close
            write_delegate = ledger_service._write
            transaction_delegate = ledger_service.ledger_transaction
            execute_delegate, fetch_delegate = psycopg.Cursor.execute, psycopg.Cursor.fetchone
            queries = {}

            def execute(cursor, query, *args, **kwargs):
                queries[id(cursor)] = query.decode() if isinstance(query, bytes) else str(query)
                return execute_delegate(cursor, query, *args, **kwargs)

            def fetchone(cursor):
                row = fetch_delegate(cursor)
                if (
                    queries.get(id(cursor), "").strip() == "SELECT pg_current_xact_id()::text"
                    and row is not None
                ):
                    assert len(row) == 1
                    watch.xids.append((id(cursor.connection), row[0], len(watch.trace.events)))
                return row

            def action(raw, name):
                if not watch.owns(raw):
                    return delegates[name](raw)
                selected = name == "commit" or (
                    name == "rollback" and watch.outcome.rollback_attempted
                )
                fault = (
                    commit_fault
                    if name == "commit"
                    else rollback_fault
                    if name == "rollback"
                    else None
                )
                prefix = "raw.close" if name == "close" else name
                watch.mark(prefix + ".before_native", raw)
                if selected and fault == "before" and name + ".before" not in watch.faults:
                    watch.faults.append(name + ".before")
                    raise RuntimeError("controlled pre-delegation " + name + " failure")
                before = {
                    "action": name,
                    "raw_id": id(raw),
                    "closed_before": raw.closed,
                    "status_before": None if raw.closed else int(raw.info.transaction_status),
                }
                result = delegates[name](raw)
                watch.mark(prefix + ".native_ack", raw)
                watch.physical.append(
                    {
                        **before,
                        "closed_after": raw.closed,
                        "status_after": None if raw.closed else int(raw.info.transaction_status),
                        "trace_end": len(watch.trace.events),
                    }
                )
                if selected and fault == "after" and name + ".after" not in watch.faults:
                    watch.faults.append(name + ".after")
                    raise RuntimeError("controlled lost " + name + " acknowledgement")
                return result

            def close(connection):
                selected = connection.engine is engine
                raw = watch.work._raw if selected else None
                if selected:
                    watch.mark("connection.close.before", raw)
                result = close_delegate(connection)
                if selected:
                    watch.mark("connection.close.return", raw)
                    if close_error is not None and "close.after" not in watch.faults:
                        # Raise from the owned service delegate after its physical
                        # close. NullPool may swallow a driver-only close exception.
                        watch.faults.append("close.after")
                        raise close_error
                return result

            def write(connection, name, values):
                result = write_delegate(connection, name, values)
                if (
                    connection.engine is engine
                    and name == "progress.insert"
                    and body_error is not None
                ):
                    watch.mark("progress.insert.return", connection.connection.driver_connection)
                    watch.faults.append("body.after_progress")
                    raise body_error
                return result

            @contextmanager
            def transaction(actual_engine, outcome, *, work):
                with transaction_delegate(actual_engine, outcome, work=work) as connection:
                    if actual_engine is not engine or not observe_writes:
                        yield connection
                        return
                    start = work.observed_ordinary
                    assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
                    first = _transaction_write_counters(connection)
                    watch.observer_units.append(work.observed_ordinary - start)
                    if injected_update is not None:
                        connection.exec_driver_sql(injected_update)
                    try:
                        yield connection
                    finally:
                        start = work.observed_ordinary
                        last = _transaction_write_counters(connection)
                        watch.observer_units.append(work.observed_ordinary - start)
                        watch.counters.append(_tuple_write_delta(first, last))

            for name in delegates:
                patch.setattr(
                    psycopg.Connection, name, lambda raw, selected=name: action(raw, selected)
                )
            patch.setattr(psycopg.Cursor, "execute", execute)
            patch.setattr(psycopg.Cursor, "fetchone", fetchone)
            patch.setattr(Connection, "close", close)
            patch.setattr(ledger_service, "_write", write)
            patch.setattr(ledger_service, "ledger_transaction", transaction)
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
                    watch.trace.stop()
                    watch.record(record_property, label)
    finally:
        drain(pg)


def fresh_reentry(
    fixture, pg, manifest, monkeypatch, record_property, *, previous=None, injected_update=None
):
    """Full classification through a distinct owned connection, with zero DML."""
    before = native_snapshot(fixture.case, pg)
    watch = None

    def forbidden(*args, **kwargs):
        raise AssertionError("fresh classification attempted writer work")

    try:
        with (
            observe_command(
                fixture,
                pg,
                monkeypatch,
                record_property,
                label="fresh_reentry",
                observe_writes=True,
                injected_update=injected_update,
            ) as watch,
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
        try:
            if watch is not None:
                watch.assert_single_attempt()
                assert not watch.outcome.cleanup_failed
                if previous is not None:
                    assert watch.work._raw is not previous.work._raw
                watch.assert_no_writes()
        finally:
            drain(pg)
            assert native_snapshot(fixture.case, pg) == before
    return result, watch
