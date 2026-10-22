"""Native SQLite traces without extra SQLAlchemy or cursor-factory hooks."""

import json
import sqlite3

import pytest
from sqlalchemy.engine import Connection

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused


class SQLiteTrace:
    def __init__(self, monkeypatch):
        self.events = []
        self.handles = []
        self.phase = "bootstrap"
        connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            self.events.append(("bootstrap", "connect", None))
            raw = connect(*args, **kwargs)
            self.handles.append(raw)
            raw.set_trace_callback(lambda sql: self.events.append((self.phase, "sql", sql)))
            return raw

        monkeypatch.setattr(ownership.sqlite3, "connect", traced_connect)
        owned = transaction.connect_owned

        def acquired(*args, **kwargs):
            self.phase = "bootstrap"
            result = owned(*args, **kwargs)
            self.phase = "ordinary"
            self.events.append(("ordinary", "acquired", None))
            return result

        monkeypatch.setattr(transaction, "connect_owned", acquired)

    def statements(self, phase):
        return [value for stage, kind, value in self.events if stage == phase and kind == "sql"]


@pytest.fixture
def native_trace(monkeypatch, request, record_property):
    trace = SQLiteTrace(monkeypatch)
    request.addfinalizer(lambda: record_property("native_trace", json.dumps(trace.events)))
    return trace


@pytest.fixture
def engine(tmp_path):
    value = create_ledger_engine(f"sqlite:///{tmp_path}/native.sqlite")
    yield value
    assert value.pool.checkedout() == 0
    value.dispose()


def test_cold_and_warm_startup_sql_envelope(engine, native_trace, record_property):
    trace = native_trace
    for expected_startup in (["PRAGMA read_uncommitted"], []):
        trace.events.clear()
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            assert connection.exec_driver_sql("SELECT 23").scalar_one() == 23
        assert trace.statements("bootstrap") == expected_startup
        assert sum(kind == "connect" for _, kind, _ in trace.events) == bool(expected_startup)
        assert trace.statements("ordinary").count("COMMIT") == 1
        record_property(
            "cold_trace" if expected_startup else "warm_trace", json.dumps(trace.events)
        )


@pytest.mark.parametrize("after_native", [False, True])
def test_initialization_failure_has_no_second_acquisition(
    engine, monkeypatch, after_native, native_trace
):
    trace = native_trace
    dialect_type = type(engine.dialect)
    original = dialect_type.get_isolation_level

    def fail(self, raw):
        if after_native:
            original(self, raw)
        raise RuntimeError("synthetic-init")

    monkeypatch.setattr(dialect_type, "get_isolation_level", fail)
    with (
        pytest.raises(MigrationRefused),
        ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("failed initialization must not yield")
    assert len(trace.handles) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        trace.handles[0].execute("SELECT 1")
    before = len(trace.events)
    with (
        pytest.raises(MigrationRefused, match="schema_incompatible"),
        ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("failed engine must stay poisoned")
    assert len(trace.events) == before


def test_after_native_begin_failure_rolls_back_before_disposal(engine, monkeypatch, native_trace):
    trace = native_trace
    original = ownership._TrackedSQLite.execute

    def fail(self, statement, *args, **kwargs):
        value = original(self, statement, *args, **kwargs)
        if statement == "BEGIN EXCLUSIVE":
            value.close()
            raise RuntimeError("synthetic-after-begin")
        return value

    monkeypatch.setattr(ownership._TrackedSQLite, "execute", fail)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="migration_database_failure"),
        ledger_transaction(engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("the body must not execute")
    assert outcome.begin_attempted and not outcome.begun
    assert outcome.rollback_attempted and outcome.rollback_acknowledged
    assert not outcome.commit_attempted
    assert "ROLLBACK" in trace.statements("ordinary")
    assert not trace.handles[0].in_transaction


@pytest.mark.parametrize("after_clear", [False, True])
def test_failed_release_skips_restore_and_reaches_recovery_retry(
    engine, monkeypatch, after_clear, native_trace
):
    trace = native_trace
    progress = ownership._TrackedSQLite._native_progress
    close = ownership._TrackedSQLite._native_close
    clears = []
    closes = []

    def fail_release(self, callback, interval):
        if callback is None:
            clears.append(self)
            if len(clears) == 1:
                if after_clear:
                    progress(self, callback, interval)
                raise RuntimeError("synthetic-release")
        return progress(self, callback, interval)

    def fail_close(self):
        closes.append(self)
        if len(closes) == 1:
            raise RuntimeError("synthetic-first-close")
        return close(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_progress", fail_release)
    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", fail_close)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="ledger_outcome_uncertain"),
        ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
    ):
        assert connection.exec_driver_sql("SELECT 29").scalar_one() == 29
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert len(clears) == 2 and clears[0] is clears[1]
    assert len(closes) >= 2
    assert "PRAGMA busy_timeout=3000" not in trace.statements("ordinary")
    with pytest.raises(sqlite3.ProgrammingError):
        trace.handles[0].execute("SELECT 1")


@pytest.mark.parametrize("count,complete", [(1010, True), (1011, False)])
def test_real_sql_reaches_last_complete_bundle(engine, native_trace, count, complete):
    trace = native_trace
    outcome = LedgerOutcome()

    def run():
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            for _ in range(count):
                assert connection.exec_driver_sql("SELECT 31").scalar_one() == 31

    if complete:
        run()
    else:
        with pytest.raises(MigrationRefused, match="ledger_limit_exceeded"):
            run()
    sql = trace.statements("ordinary")
    assert sql.count("SELECT 31") == count
    assert sql.count("COMMIT") == int(complete)
    # Independent native trace: restore is cleanup; the callback install is one
    # conservative non-SQL ordinary unit. No LedgerWork counters are the oracle.
    targets = [s for s in sql if s not in {"ROLLBACK", "PRAGMA busy_timeout=3000"}]
    assert len(targets) + 1 == 2028
    assert outcome.commit_acknowledged is complete


def test_commit_then_raise_is_uncertain_despite_rollback(engine, monkeypatch):
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="ledger_outcome_uncertain"),
        ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
    ):
        assert connection.exec_driver_sql("SELECT 37").scalar_one() == 37
        commit = connection.commit

        def commit_then_raise():
            commit()
            raise RuntimeError("synthetic-lost-ack")

        monkeypatch.setattr(connection, "commit", commit_then_raise)
    assert outcome.commit_attempted and not outcome.commit_acknowledged
    assert outcome.rollback_acknowledged
    assert not outcome.confirmed_precommit_rollback


def test_first_interruption_survives_cleanup(engine):
    error = KeyboardInterrupt("synthetic-interruption")
    outcome = LedgerOutcome()
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
    ):
        assert connection.exec_driver_sql("SELECT 41").scalar_one() == 41
        raise error
    assert caught.value is error
    assert outcome.confirmed_precommit_rollback


def test_begin_reservation_refuses_before_attempt_flag(engine, monkeypatch, native_trace):
    work, outcome = LedgerWork(), LedgerOutcome()
    execute = Connection.exec_driver_sql

    def exhaust_after_foreign_keys(self, statement, *args, **kwargs):
        result = execute(self, statement, *args, **kwargs)
        if statement == "PRAGMA foreign_keys=ON":
            work.reserve_ordinary(2028 - work.observed_ordinary)
        return result

    monkeypatch.setattr(Connection, "exec_driver_sql", exhaust_after_foreign_keys)
    with (
        pytest.raises(MigrationRefused, match="ledger_limit_exceeded"),
        ledger_transaction(engine, outcome, work=work),
    ):
        pytest.fail("exhausted BEGIN reservation must not yield")
    assert "BEGIN EXCLUSIVE" not in native_trace.statements("ordinary")
    assert not outcome.begin_attempted
    assert not outcome.begun
    assert not outcome.commit_attempted
    assert not outcome.cleanup_failed


@pytest.mark.parametrize(
    "target,ordinal", [("BEGIN EXCLUSIVE", 2), ("SELECT 23", 3), ("COMMIT", 4)]
)
@pytest.mark.parametrize("elapsed", [0, 121])
def test_deadline_between_native_setter_and_target(
    engine, monkeypatch, native_trace, target, ordinal, elapsed
):
    from agent_rewind.migrations import ledger_work

    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    original = ownership._TrackedSQLite.execute
    setters = []

    def elapsed_setter(raw, sql, *args, **kwargs):
        result = original(raw, sql, *args, **kwargs)
        if sql.startswith("PRAGMA busy_timeout="):
            setters.append(sql)
            if len(setters) == ordinal:
                now[0] += elapsed
        return result

    monkeypatch.setattr(ownership._TrackedSQLite, "execute", elapsed_setter)
    outcome = LedgerOutcome()

    def run():
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            assert connection.exec_driver_sql("SELECT 23").scalar_one() == 23

    if elapsed:
        with pytest.raises(MigrationRefused, match="migration_busy"):
            run()
        assert target not in native_trace.statements("ordinary")
        assert not outcome.commit_attempted
        assert not outcome.cleanup_failed
    else:
        run()
        assert target in native_trace.statements("ordinary")
        assert outcome.commit_acknowledged
