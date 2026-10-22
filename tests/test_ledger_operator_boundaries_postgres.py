"""Independent native PostgreSQL outcome and deadline deltas."""

import json
from types import SimpleNamespace

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from postgres_control import wait_for_database_drain
from sqlalchemy.engine import Connection
from test_ledger_operator_postgres import PostgresTrace

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations import ledger_work
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL operator boundaries"
)


@pytest.fixture
def pg_case(pg):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("CREATE TABLE proof (id INTEGER PRIMARY KEY)")
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    engine = create_ledger_engine(pg["owner"].url.render_as_string(hide_password=False))
    try:
        yield SimpleNamespace(engine=engine, verifier=pg["owner"], control=pg["control"])
    finally:
        engine.dispose()
        wait_for_database_drain(pg["control"], pg["owner"].url.database)


@pytest.fixture
def pg_trace(pg_case, monkeypatch, request, record_property):
    trace = PostgresTrace(monkeypatch)

    def finish():
        trace.stop()
        record_property("native_trace", json.dumps(trace.events))

    request.addfinalizer(finish)
    return trace


def visible_rows(case, trace):
    trace.phase = "verification"
    with case.verifier.connect() as connection:
        rows = list(connection.exec_driver_sql("SELECT id FROM proof ORDER BY id").scalars())
    wait_for_database_drain(case.control, case.verifier.url.database)
    return rows


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    return now


def test_committed_and_typed_rollback_effects_are_independently_visible(pg_case, pg_trace):
    case = pg_case
    first = LedgerOutcome()
    with ledger_transaction(case.engine, first, work=LedgerWork()) as connection:
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
    assert first.commit_acknowledged and not first.cleanup_failed and raw.closed
    assert visible_rows(case, pg_trace) == [1]
    refusal = MigrationRefused("schema_incompatible")
    second = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(case.engine, second, work=LedgerWork()) as connection,
    ):
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (2)")
        raise refusal
    assert caught.value is refusal
    assert second.confirmed_precommit_rollback and not second.cleanup_failed and raw.closed
    assert visible_rows(case, pg_trace) == [1]


@pytest.mark.parametrize(
    "stage,elapsed",
    [
        ("reservation", 0.0),
        ("reservation", 119.5),
        ("reservation", 121.0),
        ("statement_setter", 119.5),
    ],
)
def test_pg_setter_caps_use_time_remaining_after_each_boundary(
    pg_case, pg_trace, clock, monkeypatch, stage, elapsed
):
    work, outcome = LedgerWork(), LedgerOutcome()
    reserve = work.reserve_ordinary
    execute = psycopg.Cursor.execute
    armed = [False]
    delayed = []
    interval = []
    caught = []

    def reserve_then_delay(count):
        reserve(count)
        if stage == "reservation" and armed[0]:
            armed[0] = False
            delayed.append(count)
            clock[0] += elapsed

    def setter_then_delay(cursor, query, *args, **kwargs):
        result = execute(cursor, query, *args, **kwargs)
        if (
            stage == "statement_setter"
            and armed[0]
            and str(query).startswith("SET LOCAL statement_timeout")
        ):
            armed[0] = False
            delayed.append(str(query))
            clock[0] += elapsed
        return result

    monkeypatch.setattr(work, "reserve_ordinary", reserve_then_delay)
    monkeypatch.setattr(psycopg.Cursor, "execute", setter_then_delay)
    try:
        with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
            raw = connection.connection.driver_connection
            armed[0] = True
            interval.append(len(pg_trace.events))
            try:
                assert connection.exec_driver_sql("SELECT 83").scalar_one() == 83
            finally:
                interval.append(len(pg_trace.events))
    except MigrationRefused as error:
        caught.append(str(error))
    assert len(delayed) == 1 and len(interval) == 2 and raw.closed
    sql = [event[3] for event in pg_trace.events[slice(*interval)] if event[1] == "sql-call"]
    if elapsed >= 120:
        assert sql == [] and caught == ["migration_busy"]
        assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    else:
        assert len(sql) == 3 and sql[-1] == "SELECT 83"
        statement_cap = int(sql[0].split("'")[1].removesuffix("ms"))
        lock_cap = int(sql[1].split("'")[1].removesuffix("ms"))
        assert sql[0].startswith("SET LOCAL statement_timeout")
        assert sql[1].startswith("SET LOCAL lock_timeout")
        assert statement_cap == (500 if stage == "reservation" and elapsed else 20000)
        assert lock_cap == (500 if elapsed else 5000)
        assert caught == [] and outcome.commit_acknowledged and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []


@pytest.mark.parametrize("after_commit", [False, True])
def test_pg_lost_commit_ack_remains_uncertain_after_later_rollback(
    pg_case, pg_trace, monkeypatch, after_commit
):
    outcome = LedgerOutcome()
    original = psycopg.Connection.commit
    target = []
    calls = []

    def lose_ack(raw):
        if target and raw is target[0]:
            calls.append(raw)
            if after_commit:
                original(raw)
            raise RuntimeError("synthetic-commit-ack")
        return original(raw)

    monkeypatch.setattr(psycopg.Connection, "commit", lose_ack)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(pg_case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection.connection.driver_connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (7)")
    assert calls == target and target[0].closed
    assert outcome.commit_attempted and not outcome.commit_acknowledged
    assert not outcome.confirmed_precommit_rollback
    assert visible_rows(pg_case, pg_trace) == ([7] if after_commit else [])


@pytest.mark.parametrize("after_rollback", [False, True])
def test_pg_rollback_ack_failure_never_claims_certain_absence(
    pg_case, pg_trace, monkeypatch, after_rollback
):
    outcome = LedgerOutcome()
    original = psycopg.Connection.rollback
    target = []
    failed = []

    def lose_ack(raw):
        if target and raw is target[0] and not failed:
            failed.append(raw)
            if after_rollback:
                original(raw)
            raise RuntimeError("synthetic-rollback-ack")
        return original(raw)

    monkeypatch.setattr(psycopg.Connection, "rollback", lose_ack)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(pg_case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection.connection.driver_connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (8)")
        raise MigrationRefused("schema_incompatible")
    assert failed == target and target[0].closed
    assert outcome.rollback_attempted and not outcome.rollback_acknowledged
    assert not outcome.commit_attempted and not outcome.confirmed_precommit_rollback
    assert outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []


@pytest.mark.parametrize("first_stage", ["body", "cleanup"])
def test_pg_first_interruption_survives_a_later_cleanup_interruption(
    pg_case, pg_trace, monkeypatch, first_stage
):
    work, outcome = LedgerWork(), LedgerOutcome()
    first = KeyboardInterrupt("first-synthetic-interruption")
    second = SystemExit("second-synthetic-interruption")
    observe = work.observe_cleanup
    close = psycopg.Connection.close
    target = []
    observations = []
    second_close = []

    def observe_close(kind):
        observe(kind)
        if kind == "close" and not observations:
            observations.append(kind)
            raise first if first_stage == "cleanup" else second

    def close_then_interrupt(raw):
        result = close(raw)
        if first_stage == "cleanup" and target and raw is target[0] and not second_close:
            second_close.append(raw)
            raise second
        return result

    monkeypatch.setattr(work, "observe_cleanup", observe_close)
    monkeypatch.setattr(psycopg.Connection, "close", close_then_interrupt)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(pg_case.engine, outcome, work=work) as connection,
    ):
        target.append(connection.connection.driver_connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (9)")
        if first_stage == "body":
            raise first
    assert caught.value is first and observations == ["close"]
    assert target[0].closed and outcome.cleanup_failed
    assert outcome.commit_acknowledged is (first_stage == "cleanup")
    assert second_close == (target if first_stage == "cleanup" else [])
    assert visible_rows(pg_case, pg_trace) == ([9] if first_stage == "cleanup" else [])


@pytest.mark.parametrize("expire", [False, True])
def test_pg_final_cleanup_deadline_cannot_publish_clean_factory_reuse(
    pg_case, pg_trace, clock, monkeypatch, expire
):
    work, outcome = LedgerWork(), LedgerOutcome()
    close = psycopg.Connection.close
    release = transaction.release_ledger_engine
    target = []
    elapsed = []
    released = []
    caught = []

    def close_then_expire(raw):
        result = close(raw)
        if target and raw is target[0] and expire and not elapsed:
            elapsed.append(True)
            clock[0] += 121
        return result

    def release_observed(claim, *, clean):
        released.append((clean, outcome.cleanup_failed))
        return release(claim, clean=clean)

    monkeypatch.setattr(psycopg.Connection, "close", close_then_expire)
    monkeypatch.setattr(transaction, "release_ledger_engine", release_observed)
    try:
        with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
            target.append(connection.connection.driver_connection)
            connection.exec_driver_sql("INSERT INTO proof VALUES (10)")
    except MigrationRefused as error:
        caught.append(str(error))
    assert target[0].closed and outcome.commit_acknowledged
    assert released == ([(False, True)] if expire else [(True, False)])
    assert caught == (["ledger_outcome_uncertain"] if expire else [])
    assert visible_rows(pg_case, pg_trace) == [10]
    before = len(pg_trace.events)
    if expire:
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ledger_transaction(pg_case.engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("failed final deadline published a reusable factory")
        assert len(pg_trace.events) == before
    else:
        with ledger_transaction(pg_case.engine, LedgerOutcome(), work=LedgerWork()) as connection:
            assert connection.exec_driver_sql("SELECT 89").scalar_one() == 89


@pytest.mark.parametrize(
    "boundary", ["reservation", "setter", "before_native", "after_native", "positive"]
)
def test_pg_logical_begin_ack_is_distinct_from_first_physical_begin(
    pg_case, pg_trace, monkeypatch, record_property, boundary
):
    work, outcome = LedgerWork(), LedgerOutcome()
    begin = Connection.begin
    execute = psycopg.Cursor.execute
    command = psycopg.Connection._exec_command
    logical = []
    physical = []
    targets = []
    body = []
    armed = [False]
    caught = []

    def logical_begin(connection):
        result = begin(connection)
        if connection is work._connection:
            raw = connection.connection.driver_connection
            targets.append(raw)
            logical.append((work.observed_ordinary, raw.info.transaction_status.name))
            armed[0] = True
            if boundary == "reservation":
                work.reserve_ordinary(2028 - work.observed_ordinary)
        return result

    def setter(cursor, query, *args, **kwargs):
        if (
            boundary == "setter"
            and armed[0]
            and cursor.connection is targets[0]
            and str(query).startswith("SET LOCAL statement_timeout")
        ):
            armed[0] = False
            physical.append(("setter-refused", cursor.connection.info.transaction_status.name))
            raise MigrationRefused("migration_busy")
        return execute(cursor, query, *args, **kwargs)

    def physical_begin(raw, query, *args, **kwargs):
        sql = query.decode() if isinstance(query, bytes) else str(query)
        if not (armed[0] and targets and raw is targets[0] and sql == "BEGIN"):
            return command(raw, query, *args, **kwargs)

        def observed():
            armed[0] = False
            physical.append(("before-native", raw.info.transaction_status.name))
            if boundary == "before_native":
                raise RuntimeError("synthetic-before-native-begin")
            result = yield from command(raw, query, *args, **kwargs)
            physical.append(("after-native", raw.info.transaction_status.name))
            if boundary == "after_native":
                raise RuntimeError("synthetic-after-native-begin")
            return result

        return observed()

    monkeypatch.setattr(Connection, "begin", logical_begin)
    monkeypatch.setattr(psycopg.Cursor, "execute", setter)
    monkeypatch.setattr(psycopg.Connection, "_exec_command", physical_begin)
    try:
        with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
            body.append(True)
            connection.exec_driver_sql("INSERT INTO proof VALUES (33)")
    except MigrationRefused as error:
        caught.append(str(error))
    record_property(
        "begin_boundary",
        json.dumps(
            {
                "boundary": boundary,
                "logical": logical,
                "physical": physical,
                "body_entered": bool(body),
                "begin_attempted": outcome.begin_attempted,
                "begun": outcome.begun,
                "rollback_acknowledged": outcome.rollback_acknowledged,
            }
        ),
    )
    assert logical == [(1, "IDLE")]
    # PostgreSQL's acknowledged wrapper is logical; native evidence below must
    # neither erase that acknowledgment nor manufacture a physical BEGIN.
    assert outcome.begin_attempted and outcome.begun and targets[0].closed
    if boundary == "reservation":
        assert physical == [] and work.observed_ordinary == 2028
        assert caught == ["ledger_limit_exceeded"]
    elif boundary == "setter":
        assert physical == [("setter-refused", "IDLE")]
        assert caught == ["migration_busy"]
    elif boundary == "before_native":
        assert physical == [("before-native", "IDLE")]
        assert caught == ["migration_database_failure"]
    else:
        assert physical == [("before-native", "IDLE"), ("after-native", "INTRANS")]
        assert caught == ([] if boundary == "positive" else ["migration_database_failure"])
    if boundary == "positive":
        assert body == [True] and outcome.commit_acknowledged and not outcome.cleanup_failed
        assert visible_rows(pg_case, pg_trace) == [33]
    else:
        assert body == [] and outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert visible_rows(pg_case, pg_trace) == []
