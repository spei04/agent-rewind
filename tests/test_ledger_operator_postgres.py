"""Opt-in native traces for the ledger-only pinned PostgreSQL factory."""

import json
import os
import sys

import psycopg
import pytest
import test_migrations_postgres as migration_tests

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not os.getenv("REWIND_TEST_POSTGRES_URL"), reason="Opt-in synthetic PostgreSQL integration"
)


class PostgresTrace:
    def __init__(self, monkeypatch):
        self.events = []
        self.handles = []
        self.phase = "bootstrap"
        self.frames = set()
        connect = psycopg.connect
        cursor_execute = psycopg.Cursor.execute
        command = psycopg.Connection._exec_command
        owned = transaction.connect_owned
        detach = LedgerWork._detach

        def traced_connect(*args, **kwargs):
            self.events.append((self.phase, "connect-call", None, None))
            raw = connect(*args, **kwargs)
            self.handles.append(raw)
            self.events.append((self.phase, "connect-return", id(raw), None))
            return raw

        def execute(cursor, query, *args, **kwargs):
            sql = query.decode() if isinstance(query, bytes) else str(query)
            self.events.append((self.phase, "sql-call", id(cursor.connection), sql))
            try:
                result = cursor_execute(cursor, query, *args, **kwargs)
            except BaseException:
                self.events.append((self.phase, "sql-raise", id(cursor.connection), sql))
                raise
            self.events.append((self.phase, "sql-return", id(cursor.connection), sql))
            return result

        def exec_command(raw, query, *args, **kwargs):
            sql = query.decode() if isinstance(query, bytes) else str(query)
            self.events.append((self.phase, "command", id(raw), sql))
            return command(raw, query, *args, **kwargs)

        def acquired(*args, **kwargs):
            self.phase = "bootstrap"
            try:
                result = owned(*args, **kwargs)
            except BaseException:
                self.phase = "cleanup"
                raise
            self.phase = "ordinary"
            return result

        def detached(work):
            self.phase = "cleanup"
            return detach(work)

        monkeypatch.setattr(psycopg, "connect", traced_connect)
        monkeypatch.setattr(psycopg.Cursor, "execute", execute)
        monkeypatch.setattr(psycopg.Connection, "_exec_command", exec_command)
        monkeypatch.setattr(transaction, "connect_owned", acquired)
        monkeypatch.setattr(LedgerWork, "_detach", detached)
        for name in ("commit", "rollback", "close"):
            original = getattr(psycopg.Connection, name)

            def action(raw, _name=name, _original=original):
                self.events.append((self.phase, _name + "-call", id(raw), None))
                try:
                    result = _original(raw)
                except BaseException:
                    self.events.append((self.phase, _name + "-raise", id(raw), None))
                    raise
                self.events.append((self.phase, _name + "-return", id(raw), None))
                return result

            monkeypatch.setattr(psycopg.Connection, name, action)

        self.previous_profile = sys.getprofile()
        code = psycopg.Connection._connect_gen.__func__.__code__

        def profile(frame, event, arg):
            if event == "call" and frame.f_code is code and frame not in self.frames:
                self.frames.add(frame)
                self.events.append((self.phase, "internal-connect", None, None))
            if self.previous_profile is not None:
                self.previous_profile(frame, event, arg)

        sys.setprofile(profile)

    def sql(self, phase):
        return [sql for stage, kind, _, sql in self.events if stage == phase and kind == "sql-call"]

    def count(self, phase, kind):
        return sum(stage == phase and event == kind for stage, event, _, _ in self.events)

    def stop(self):
        sys.setprofile(self.previous_profile)
        self.frames.clear()


@pytest.fixture
def engine(pg):
    value = create_ledger_engine(pg["owner"].url.render_as_string(hide_password=False))
    yield value
    value.dispose()


@pytest.fixture
def native_trace(monkeypatch, request, record_property):
    trace = PostgresTrace(monkeypatch)

    def finish():
        trace.stop()
        record_property("native_trace", json.dumps(trace.events))

    request.addfinalizer(finish)
    return trace


def assert_bootstrap_bound(trace):
    sql = trace.sql("bootstrap")
    starts = sum(
        stage == "bootstrap" and kind == "command" and value == "BEGIN"
        for stage, kind, _, value in trace.events
    )
    assert len(sql) <= 4
    assert starts <= 2
    assert trace.count("bootstrap", "rollback-call") <= 2
    assert trace.count("bootstrap", "close-call") <= 1
    assert trace.count("bootstrap", "connect-call") == 1
    assert trace.count("bootstrap", "internal-connect") == 1
    observed = (
        len(sql)
        + starts
        + sum(
            trace.count("bootstrap", kind)
            for kind in ("rollback-call", "close-call", "connect-call")
        )
    )
    assert observed <= 12


def test_postgres_cold_warm_startup_and_disposal(
    engine, native_trace, record_property, monkeypatch
):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("socket routing must not resolve DNS")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    trace = native_trace
    for expected in (4, 0):
        trace.events.clear()
        outcome = LedgerOutcome()
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            assert connection.exec_driver_sql("SELECT 53").scalar_one() == 53
            assert connection.in_transaction()
            assert connection.dialect.server_version_info[:1] == (16,)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert len(trace.sql("bootstrap")) == expected
        assert_bootstrap_bound(trace)
        assert all(raw.closed for raw in trace.handles)
        record_property("cold" if expected else "warm", json.dumps(trace.events))


@pytest.mark.parametrize("ordinal", [1, 2, 3, 4])
@pytest.mark.parametrize("after_native", [False, True])
def test_each_postgres_initialization_statement_failure_disposes_raw(
    engine, native_trace, monkeypatch, ordinal, after_native
):
    trace = native_trace
    original = psycopg.Cursor.execute
    calls = []

    def failed(cursor, query, *args, **kwargs):
        calls.append(True)
        if len(calls) == ordinal:
            if after_native:
                original(cursor, query, *args, **kwargs)
            raise RuntimeError("synthetic-initialization")
        return original(cursor, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", failed)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="migration_database_failure"),
        ledger_transaction(engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("failed initialization must not yield")
    assert len(calls) == ordinal
    assert not outcome.begin_attempted and not outcome.commit_attempted
    assert len(trace.handles) == 1 and trace.handles[0].closed
    assert_bootstrap_bound(trace)


@pytest.mark.parametrize("after_native", [False, True])
def test_postgres_suppressed_logical_close_still_requires_raw_ack(
    engine, native_trace, monkeypatch, after_native
):
    original = psycopg.Connection.close
    calls = []

    def failed(raw):
        calls.append(raw)
        if len(calls) == 1:
            if after_native:
                original(raw)
            raise RuntimeError("synthetic-swallowed-close")
        return original(raw)

    monkeypatch.setattr(psycopg.Connection, "close", failed)
    outcome = LedgerOutcome()
    with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
        assert connection.exec_driver_sql("SELECT 59").scalar_one() == 59
    assert len(calls) == 2 and calls[0] is calls[1]
    assert calls[0].closed and outcome.commit_acknowledged
    assert not outcome.cleanup_failed


def test_postgres_persistent_retained_close_failure_is_uncertain(engine, native_trace, monkeypatch):
    original = psycopg.Connection.close
    calls = []

    def failed(raw):
        calls.append(raw)
        raise RuntimeError("synthetic-persistent-close")

    monkeypatch.setattr(psycopg.Connection, "close", failed)
    try:
        outcome = LedgerOutcome()
        with (
            pytest.raises(MigrationRefused, match="ledger_outcome_uncertain"),
            ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            assert connection.exec_driver_sql("SELECT 61").scalar_one() == 61
        assert len(calls) == 3 and all(raw is calls[0] for raw in calls)
        assert outcome.commit_acknowledged and outcome.cleanup_failed
        assert not calls[0].closed
        native_trace.events.append(
            ("verification", "pre-rescue-closed", id(calls[0]), calls[0].closed)
        )
        before = len(native_trace.events)
        with (
            pytest.raises(MigrationRefused, match="schema_incompatible"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("uncertain engine must stay poisoned")
        assert len(native_trace.events) == before
    finally:
        native_trace.phase = "test-rescue"
        for raw in native_trace.handles:
            original(raw)
            native_trace.events.append(("test-rescue", "closed", id(raw), raw.closed))


@pytest.mark.parametrize("reported", [(15, 9), (17, 1), None])
def test_postgres_actual_server_major_gate_before_body(engine, native_trace, monkeypatch, reported):
    initialize = engine.dialect.initialize

    def initialized(connection):
        initialize(connection)
        engine.dialect.server_version_info = reported

    monkeypatch.setattr(engine.dialect, "initialize", initialized)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="schema_incompatible"),
        ledger_transaction(engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("unsupported server must not yield")
    assert not outcome.begin_attempted and not outcome.commit_attempted
    assert all(raw.closed for raw in native_trace.handles)


@pytest.mark.parametrize("count,complete", [(666, True), (667, False)])
def test_postgres_last_complete_native_bundle(engine, native_trace, count, complete):
    outcome = LedgerOutcome()

    def run():
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            for _ in range(count):
                assert connection.exec_driver_sql("SELECT 67").scalar_one() == 67

    if complete:
        run()
    else:
        with pytest.raises(MigrationRefused, match="ledger_limit_exceeded"):
            run()
    sql = native_trace.sql("ordinary")
    commits = native_trace.count("ordinary", "commit-call")
    assert sql.count("SELECT 67") == count
    assert commits == int(complete)
    # PostgreSQL spends one logical BEGIN unit, then indivisible triples.
    # The last usable total is2026; the next triple exceeds2028.
    assert len(sql) + commits + 1 == 2026
    assert outcome.commit_acknowledged is complete
    assert all(raw.closed for raw in native_trace.handles)


@pytest.mark.parametrize("setter", ["statement_timeout", "lock_timeout"])
@pytest.mark.parametrize("elapsed", [0, 121])
def test_postgres_expiry_between_setters_and_body_target(
    engine, native_trace, monkeypatch, setter, elapsed
):
    from agent_rewind.migrations import ledger_work

    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    original = psycopg.Cursor.execute
    armed = [False]

    def elapsed_setter(cursor, query, *args, **kwargs):
        result = original(cursor, query, *args, **kwargs)
        if armed[0] and str(query).startswith("SET LOCAL " + setter):
            armed[0] = False
            now[0] += elapsed
        return result

    monkeypatch.setattr(psycopg.Cursor, "execute", elapsed_setter)
    outcome = LedgerOutcome()
    before = []

    def run():
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            before.extend(native_trace.sql("ordinary"))
            armed[0] = True
            assert connection.exec_driver_sql("SELECT 71").scalar_one() == 71

    if elapsed:
        with pytest.raises(MigrationRefused, match="migration_busy"):
            run()
        added = native_trace.sql("ordinary")[len(before) :]
        assert "SELECT 71" not in added
        assert len(added) == (1 if setter == "statement_timeout" else 2)
        assert not outcome.commit_attempted and outcome.rollback_acknowledged
    else:
        run()
        assert "SELECT 71" in native_trace.sql("ordinary")
        assert outcome.commit_acknowledged
    assert all(raw.closed for raw in native_trace.handles)


@pytest.mark.parametrize(
    "routing",
    [
        "host=127.0.0.1&port=1",
        "host=localhost&hostaddr=127.0.0.1&port=1&sslmode=verify-full",
    ],
)
def test_numeric_routing_one_failed_attempt_without_dns(monkeypatch, native_trace, routing):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("numeric routing must not resolve DNS")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    value = create_ledger_engine(f"postgresql+psycopg://postgres@/postgres?{routing}")
    try:
        with (
            pytest.raises(MigrationRefused, match="migration_database_failure"),
            ledger_transaction(value, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("closed local port must not yield")
        assert native_trace.count("bootstrap", "internal-connect") == 1
        assert native_trace.count("bootstrap", "connect-call") == 1
        assert not native_trace.handles
    finally:
        value.dispose()


@pytest.mark.parametrize(
    "routing",
    [
        "host=unreviewed.invalid",
        "host=127.0.0.1,127.0.0.2",
        "service=unreviewed",
        "host=/tmp&target_session_attrs=prefer-standby",
    ],
)
def test_unreviewed_routing_refuses_before_internal_connect(native_trace, routing):
    with pytest.raises(MigrationRefused):
        create_ledger_engine(f"postgresql+psycopg://postgres@/postgres?{routing}")
    assert not native_trace.events


@pytest.mark.parametrize("inherited", ["prefer-standby", "read-write"])
def test_inherited_routing_policy_refuses_before_native_connect(
    monkeypatch, native_trace, inherited
):
    monkeypatch.setenv("PGTARGETSESSIONATTRS", inherited)
    with pytest.raises(MigrationRefused, match="unsupported_runtime_endpoint"):
        create_ledger_engine("postgresql+psycopg://postgres@/postgres?host=/tmp")
    assert not native_trace.events


@pytest.mark.parametrize("policy", ["explicit", "inherited"])
def test_any_policy_allows_one_native_socket_attempt(pg, monkeypatch, native_trace, policy):
    url = pg["owner"].url
    if policy == "explicit":
        url = url.update_query_dict({"target_session_attrs": "any"})
    else:
        monkeypatch.setenv("PGTARGETSESSIONATTRS", "any")
    value = create_ledger_engine(url.render_as_string(hide_password=False))
    try:
        with ledger_transaction(value, LedgerOutcome(), work=LedgerWork()) as connection:
            assert connection.exec_driver_sql("SELECT 73").scalar_one() == 73
        assert native_trace.count("bootstrap", "internal-connect") == 1
        assert all(raw.closed for raw in native_trace.handles)
    finally:
        value.dispose()
