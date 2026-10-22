"""Independent native work conservation and request-deadline controls."""

import sqlite3
from dataclasses import fields

import pytest
from ledger_operator_fixture import assert_pool_released, ledger_case, proof_rows
from sqlalchemy.engine import Connection

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.migrations import ledger_work
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.projection_source import QueryBudget

__all__ = ["ledger_case"]


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    return now


@pytest.mark.parametrize("value", [True, False, 0, 31, -1, 5.0, "5", None])
def test_timeout_requires_an_exact_bounded_integer(value):
    with pytest.raises(MigrationRefused, match="^invalid_lock_timeout$"):
        LedgerWork(timeout_seconds=value)


@pytest.mark.parametrize("seconds", [1, 5, 30])
def test_remaining_native_caps_only_tighten(clock, seconds):
    work = LedgerWork(timeout_seconds=seconds)
    assert work.remaining_timeouts_ms() == (4000 * seconds, 1000 * seconds)
    clock[0] += 119.0
    assert work.remaining_timeouts_ms() == (1000, 1000)
    clock[0] += 0.9995
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        work.remaining_timeouts_ms()


def test_outcome_constructor_has_exact_public_boolean_fields():
    expected = [
        "begun",
        "commit_attempted",
        "commit_acknowledged",
        "rollback_attempted",
        "rollback_acknowledged",
        "cleanup_failed",
        "begin_attempted",
    ]
    outcome = LedgerOutcome()
    assert [item.name for item in fields(outcome) if item.init] == expected
    assert all(getattr(outcome, name) is False for name in expected)
    outcome.begun = outcome.rollback_acknowledged = True
    assert outcome.confirmed_precommit_rollback
    outcome.commit_attempted = True
    assert not outcome.confirmed_precommit_rollback


def test_fixed_allowances_are_recorded_before_the_native_connect(ledger_case, monkeypatch):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    observed = []
    original = case.trace.connect

    def connect(*args, **kwargs):
        observed.append((work.prepaid_bootstrap, work.prepaid_cleanup, work.observed_ordinary))
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    assert (work.prepaid_bootstrap, work.prepaid_cleanup, work.observed_ordinary) == (0, 0, 0)
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert observed == [(12, 8, 0)]
    assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
    assert outcome.commit_acknowledged
    assert_pool_released(case)


def test_reservation_refuses_ordinary_unit_2029_without_refund(ledger_case):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
        ledger_transaction(case.engine, outcome, work=work),
    ):
        work.reserve_ordinary(2028 - work.observed_ordinary)
        assert work.observed_ordinary == 2028
        work.reserve_ordinary(1)
    assert work.observed_ordinary == 2028
    assert work.prepaid_bootstrap + work.prepaid_cleanup + work.observed_ordinary == 2048
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert_pool_released(case)


def test_genuine_sql_reaches_last_complete_commit_bundle(ledger_case):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        events = case.trace.events
        start = next(
            index
            for index, event in enumerate(events)
            if event[0] == "c_call" and event[3] == "set_progress_handler"
        )
        setup_units = sum(
            event[0] == "c_call" and event[3] in {"execute", "set_progress_handler"}
            for event in events[start:]
        )
        # SQLite SELECT and COMMIT each need one native setter plus their target.
        available_pairs = (2028 - setup_units) // 2
        assert setup_units + 2 * available_pairs == 2028
        for _ in range(available_pairs - 1):
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        before_commit = len(events)
    end = next(
        index + 1
        for index, event in enumerate(events[before_commit:], before_commit)
        if event[0] == "c_return" and event[3] == "commit"
    )
    observed_units = sum(
        event[0] == "c_call" and event[3] in {"execute", "set_progress_handler", "commit"}
        for event in events[start:end]
    )
    assert observed_units == 2028
    assert work.observed_ordinary == observed_units
    assert work.prepaid_bootstrap + work.prepaid_cleanup + observed_units == 2048
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert_pool_released(case)


def test_unaffordable_commit_bundle_does_no_partial_native_work(ledger_case):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        events = case.trace.events
        start = next(
            index
            for index, event in enumerate(events)
            if event[0] == "c_call" and event[3] == "set_progress_handler"
        )
        setup_units = sum(
            event[0] == "c_call" and event[3] in {"execute", "set_progress_handler"}
            for event in events[start:]
        )
        for _ in range((2028 - setup_units) // 2):
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        before_commit = len(events)
    first_cleanup = next(
        index
        for index, event in enumerate(events[before_commit:], before_commit)
        if event[0] == "c_call" and event[3] == "set_progress_handler"
    )
    assert not any(
        event[0] == "c_call" and event[3] in {"execute", "commit"}
        for event in events[before_commit:first_cleanup]
    )
    assert not outcome.commit_attempted and outcome.confirmed_precommit_rollback
    assert work.observed_ordinary == 2028
    assert_pool_released(case)


@pytest.mark.parametrize("many", [False, True])
def test_bind17_and_executemany_refuse_before_a_native_setter(ledger_case, many):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        boundary = len(case.trace.events)
        try:
            if many:
                connection.exec_driver_sql("INSERT INTO proof VALUES (?)", [(1,), (2,)])
            else:
                connection.exec_driver_sql("SELECT " + ",".join(["?"] * 17), tuple(range(17)))
        finally:
            target_end = len(case.trace.events)
    assert not any(
        event[0] == "c_call" and event[3] in {"execute", "executemany"}
        for event in case.trace.events[boundary:target_end]
    )
    assert proof_rows(case.path) == []
    assert outcome.confirmed_precommit_rollback
    assert_pool_released(case)


def test_nested_query_budget_neither_resets_global_work_nor_owns_callback(ledger_case):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    budget = QueryBudget()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        before = work.observed_ordinary
        with budget.observe(connection):
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        between = work.observed_ordinary
        with budget.observe(connection):
            assert connection.exec_driver_sql("SELECT 2").scalar_one() == 2
        after = work.observed_ordinary
    assert budget.used == 2
    assert before < between < after
    assert between - before == after - between == 2
    assert outcome.commit_acknowledged
    assert_pool_released(case)


def test_deadline_exhaustion_before_commit_rolls_back(clock, ledger_case):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^migration_busy$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES (21)")
        clock[0] += 121
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert proof_rows(case.path) == []
    assert_pool_released(case)


def test_deadline_after_real_commit_is_uncertain(clock, ledger_case, monkeypatch):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    original = Connection.commit
    target = []

    def commit_then_expire(connection):
        result = original(connection)
        if target and connection is target[0]:
            clock[0] += 121
        return result

    monkeypatch.setattr(Connection, "commit", commit_then_expire)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        target.append(connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (22)")
    assert outcome.commit_attempted and outcome.commit_acknowledged
    assert proof_rows(case.path) == [22]
    assert_pool_released(case)


@pytest.mark.parametrize("reuse", ["work", "outcome"])
def test_consumed_invocation_records_cannot_issue_more_sql(ledger_case, reuse):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    boundary = len(case.trace.events)
    with (
        pytest.raises(MigrationRefused, match="^migration_database_failure$"),
        ledger_transaction(
            case.engine,
            outcome if reuse == "outcome" else LedgerOutcome(),
            work=work if reuse == "work" else LedgerWork(),
        ),
    ):
        pytest.fail("consumed invocation entered twice")
    assert case.trace.events[boundary:] == []
    assert_pool_released(case)


@pytest.mark.parametrize(
    "field,value",
    [
        ("begun", True),
        ("commit_attempted", True),
        ("begin_attempted", 1),
        ("cleanup_failed", None),
    ],
)
def test_forged_outcome_refuses_before_acquisition(ledger_case, field, value):
    case = ledger_case
    outcome = LedgerOutcome()
    setattr(outcome, field, value)
    with (
        pytest.raises(MigrationRefused, match="^migration_database_failure$"),
        ledger_transaction(case.engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("forged outcome entered")
    assert case.trace.raws == []


@pytest.mark.parametrize("target", ["begin", "statement", "commit"])
@pytest.mark.parametrize("expire", [False, True])
def test_setter_return_rechecks_deadline_before_native_target(
    clock, ledger_case, monkeypatch, target, expire
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    original_raw = ownership._TrackedSQLite.execute
    original_sql = Connection.exec_driver_sql
    armed = [False]
    boundaries = []
    body = []
    caught = []

    def setter(raw, statement, *args, **kwargs):
        result = original_raw(raw, statement, *args, **kwargs)
        if armed[0] and statement.startswith("PRAGMA busy_timeout="):
            armed[0] = False
            boundaries.append(len(case.trace.events))
            if expire:
                clock[0] += 121
        return result

    def after_foreign_keys(connection, statement, *args, **kwargs):
        result = original_sql(connection, statement, *args, **kwargs)
        if target == "begin" and statement == "PRAGMA foreign_keys=ON":
            armed[0] = True
        return result

    monkeypatch.setattr(ownership._TrackedSQLite, "execute", setter)
    monkeypatch.setattr(Connection, "exec_driver_sql", after_foreign_keys)
    try:
        with ledger_transaction(case.engine, outcome, work=work) as connection:
            body.append(True)
            if target == "statement":
                armed[0] = True
                assert connection.exec_driver_sql("SELECT 23").scalar_one() == 23
            else:
                connection.exec_driver_sql("INSERT INTO proof VALUES (23)")
                if target == "commit":
                    armed[0] = True
    except MigrationRefused as error:
        caught.append(str(error))
    assert len(boundaries) == 1
    attempted_sql = {"begin": "BEGIN EXCLUSIVE", "statement": "SELECT 23", "commit": "COMMIT"}[
        target
    ]
    target_seen = attempted_sql in case.trace.sql(boundaries[0])
    if expire:
        assert not target_seen, "deadline expired at setter return, before the native target"
        if target == "begin":
            assert not outcome.begin_attempted and not outcome.begun and body == []
        assert not outcome.commit_attempted and not outcome.commit_acknowledged
        assert caught == ["migration_busy"]
        assert proof_rows(case.path) == []
    else:
        assert target_seen and caught == []
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert proof_rows(case.path) == ([] if target == "statement" else [23])
    assert_pool_released(case)
