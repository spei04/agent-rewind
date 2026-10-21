"""Real pooled SQLite budgets and cleanup; PostgreSQL proof remains separate."""

import sqlite3

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from test_admission_transaction import engine, rows

from agent_rewind import operation_work
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.request_authority import ActionForbidden
from agent_rewind.request_identity import IdentityInvalid
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["engine"]


@pytest.fixture
def clock(monkeypatch):
    value = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: value[0])
    return value


def test_setup_native_refresh_and_cleanup_are_counted_with_original_timeout(engine):
    work = OperationWork()
    outcome = TransactionOutcome()
    with admission_transaction(engine, outcome, work=work) as connection:
        assert work.statements == 4  # FK read, original timeout, setter, BEGIN
        connection.execute(text("INSERT INTO proof VALUES(1)"))
        assert work.statements == 6  # raw native setter plus actual INSERT
    assert outcome.commit_acknowledged
    assert work.statements == 10  # commit setter + commit + restore + close
    assert rows(engine) == [1]
    # Fresh disclosure shares the same total, with no listeners leaked in pool.
    with operation_connection(engine, work) as connection:
        assert connection.exec_driver_sql("SELECT id FROM proof").scalar_one() == 1
    assert work.statements == 20
    before = work.statements
    assert rows(engine) == [1]
    assert work.statements == before


@pytest.mark.parametrize("phase", ["body", "setup_complete", "precommit"])
def test_exhaustion_before_commit_rolls_back_and_restores_pool(engine, clock, monkeypatch, phase):
    work = OperationWork()
    outcome = TransactionOutcome()
    if phase == "setup_complete":

        def fail():
            clock[0] = 11
            work.check()

        monkeypatch.setattr(work, "setup_complete", fail)
    original = work.control_attempt
    if phase == "precommit":

        def expire(kind):
            if kind == "commit":
                clock[0] = 11
            original(kind)

        monkeypatch.setattr(work, "control_attempt", expire)
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, outcome, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        if phase == "body":
            clock[0] = 11
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert rows(engine) == []
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("phase", ["commit", "close", "finish"])
def test_late_deadline_is_uncertain_after_ack_not_retryable(engine, clock, monkeypatch, phase):
    work = OperationWork()
    outcome = TransactionOutcome()
    if phase in ("commit", "close"):
        original = getattr(Connection, phase)

        def late(connection):
            original(connection)
            clock[0] = 11

        monkeypatch.setattr(Connection, phase, late)
    else:
        original = work.finish

        def late_finish():
            clock[0] = 11
            original()

        monkeypatch.setattr(work, "finish", late_finish)
    with (
        pytest.raises(AdmissionError, match="^outcome_uncertain$"),
        admission_transaction(engine, outcome, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
    assert outcome.commit_acknowledged
    assert rows(engine) == [1]
    assert work.seconds == 11


@pytest.mark.parametrize("denial", [IdentityInvalid, ResourceNotFound, ActionForbidden])
def test_denial_survives_expired_work_and_detach_failure(engine, clock, monkeypatch, denial):
    original = event.remove

    def broken(target, name, callback):
        original(target, name, callback)
        raise RuntimeError("PRIVATE-DETACH")

    monkeypatch.setattr(event, "remove", broken)
    state = TransactionOutcome()
    expected = denial()
    with (
        pytest.raises(denial) as caught,
        admission_transaction(engine, state, work=OperationWork()) as connection,
    ):
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        clock[0] = 11
        raise expected
    assert caught.value is expected and caught.value.__suppress_context__
    assert state.cleanup_failed and not state.commit_attempted
    assert rows(engine) == []
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")


def test_partial_attach_removes_owned_hooks_and_closes(engine, monkeypatch):
    original = event.listen

    def partial(target, name, callback, *args, **kwargs):
        original(target, name, callback, *args, **kwargs)
        if name == "after_cursor_execute":
            raise RuntimeError("PRIVATE-ATTACH")

    monkeypatch.setattr(event, "listen", partial)
    work = OperationWork()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, TransactionOutcome(), work=work),
    ):
        pytest.fail("body")
    assert engine.pool.checkedout() == 0 and work.statements == 2
    assert rows(engine) == []
    assert work.statements == 2


def test_budget_exhaustion_never_skips_cleanup(engine):
    work = OperationWork()
    work.statements = 496
    state = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, state, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        connection.exec_driver_sql("SELECT 1")
    assert state.confirmed_precommit_rollback
    assert work.statements <= 512
    assert rows(engine) == []


def test_submillisecond_remaining_refuses_without_zero_timeout(engine, clock):
    work = OperationWork()
    state = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, state, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        clock[0] = 9.9995
        connection.exec_driver_sql("SELECT 1")
    assert state.confirmed_precommit_rollback
    assert raw.execute("PRAGMA busy_timeout").fetchone() == (741,)
    assert rows(engine) == []


def test_real_vm_ceiling_interrupts_statement_and_releases_callback(engine):
    work = OperationWork()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        operation_connection(engine, work) as connection,
    ):
        connection.exec_driver_sql(
            "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000000)"
            " SELECT sum(x) FROM n"
        ).scalar_one()
    assert work.instructions == 20_000_000
    assert engine.pool.checkedout() == 0
    assert rows(engine) == []
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO proof VALUES(1)",
        "CREATE TABLE forbidden(id INTEGER)",
    ],
)
def test_read_scope_is_natively_read_only_on_dml_capable_role(engine, statement):
    work = OperationWork()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        operation_connection(engine, work) as connection,
    ):
        connection.exec_driver_sql(statement)
    assert rows(engine) == []
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO proof VALUES(2)")
    assert rows(engine) == [2]


def test_fetch_parse_and_final_disclosure_share_deadline(engine, clock):
    work = OperationWork()
    with operation_connection(engine, work) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        clock[0] = 6
    clock[0] = 100  # outside-SQL storage time is not charged
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        operation_connection(engine, work) as connection,
    ):
        connection.exec_driver_sql("SELECT 1")
        clock[0] = 104.1
    assert work.seconds == pytest.approx(10.1)
    assert rows(engine) == []


def test_failure_during_timeout_mutation_discards_without_reconnecting(engine):
    created = []

    def connect(raw, _):
        created.append(raw)

    event.listen(engine, "connect", connect)
    fired = False

    def fault(_c, _cursor, statement, *_args):
        nonlocal fired
        if statement == "PRAGMA busy_timeout=3000" and not fired:
            fired = True
            raise RuntimeError("PRIVATE-SETUP")

    event.listen(engine, "after_cursor_execute", fault)
    try:
        with (
            pytest.raises(AdmissionError, match="^dependency_unavailable$"),
            admission_transaction(engine, TransactionOutcome(), work=OperationWork()),
        ):
            pytest.fail("body")
        assert fired and created == []  # cleanup must not open a replacement
        assert engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "after_cursor_execute", fault)
        event.remove(engine, "connect", connect)
    assert rows(engine) == []


@pytest.mark.parametrize("phase", ["rollback", "close", "accounting"])
def test_cleanup_faults_still_release_and_preserve_classification(engine, monkeypatch, phase):
    work = OperationWork()
    state = TransactionOutcome()
    if phase == "accounting":
        original = work.control_attempt

        def fault(kind):
            original(kind)
            if kind == "rollback":
                raise RuntimeError("PRIVATE-ACCOUNTING")

        monkeypatch.setattr(work, "control_attempt", fault)
    else:
        original = getattr(Connection, phase)
        fired = False

        def fault(connection):
            nonlocal fired
            if not fired:
                fired = True
                raise RuntimeError("PRIVATE-CONTROL")
            return original(connection)

        monkeypatch.setattr(Connection, phase, fault)
    expected = "dependency_unavailable" if phase == "accounting" else "outcome_uncertain"
    with (
        pytest.raises(AdmissionError, match=f"^{expected}$"),
        admission_transaction(engine, state, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        if phase != "close":
            raise RuntimeError("PRIMARY")
    assert engine.pool.checkedout() == 0
    assert rows(engine) == ([1] if phase == "close" else [])
    if phase == "accounting":
        assert state.cleanup_failed and state.confirmed_precommit_rollback


def test_baseexception_identity_preserved_after_cleanup(engine):
    stop = KeyboardInterrupt()
    state = TransactionOutcome()
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        admission_transaction(engine, state, work=OperationWork()) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        raise stop
    assert caught.value is stop and state.confirmed_precommit_rollback
    assert rows(engine) == []


def test_checkout_delay_is_excluded_and_phase_counters_are_not_reset(engine, clock, monkeypatch):
    work = OperationWork()
    with operation_connection(engine, work) as connection:
        connection.exec_driver_sql("SELECT 1")
        clock[0] = 2
    before = work.statements
    connect = engine.connect

    def slow():
        clock[0] += 50
        return connect()

    monkeypatch.setattr(engine, "connect", slow)
    with operation_connection(engine, work) as connection:
        connection.exec_driver_sql("SELECT 1")
        clock[0] += 1
    assert work.seconds == 3 and work.statements > before


def test_read_scope_does_not_reclassify_caller_programming_failure(engine):
    failure = RuntimeError("PRIVATE-CALLER")
    with pytest.raises(RuntimeError) as caught, operation_connection(engine, OperationWork()):
        raise failure
    assert caught.value is failure and caught.value.__suppress_context__
    assert rows(engine) == []


@pytest.mark.parametrize("method", ["read", "transaction"])
def test_known_foreign_progress_owner_is_not_replaced(engine, method):
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        connection.info["operation_work"] = object()
    work = OperationWork()
    scope = (
        operation_connection(engine, work)
        if method == "read"
        else admission_transaction(engine, TransactionOutcome(), work=work)
    )
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"), scope:
        pytest.fail("body")
    assert engine.pool.checkedout() == 0
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    assert rows(engine) == []


def test_opaque_executemany_cannot_bypass_statement_budget(engine):
    work = OperationWork()
    state = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, state, work=work) as connection,
    ):
        connection.execute(text("INSERT INTO proof VALUES(:id)"), [{"id": 1}, {"id": 2}])
    assert state.confirmed_precommit_rollback
    assert rows(engine) == []


@pytest.mark.parametrize("stage", ["before_cursor_execute", "after_cursor_execute"])
def test_partial_registration_fault_preserves_baseexception_and_replaces_connection(
    engine, monkeypatch, stage
):
    original = event.listen

    def broken(connection, name, callback):
        original(connection, name, callback)
        if name == stage:
            raise KeyboardInterrupt()

    monkeypatch.setattr(event, "listen", broken)
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
    with (
        pytest.raises(KeyboardInterrupt),
        admission_transaction(engine, TransactionOutcome(), work=OperationWork()),
    ):
        pytest.fail("body")
    assert rows(engine) == []
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")


def test_detach_interruption_still_discards_and_releases(engine, monkeypatch):
    original = event.remove
    interruption = KeyboardInterrupt()
    calls = []

    def interrupted(target, name, callback):
        calls.append(name)
        original(target, name, callback)
        if name == "before_cursor_execute":
            raise interruption

    monkeypatch.setattr(event, "remove", interrupted)
    state = TransactionOutcome()
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        admission_transaction(engine, state, work=OperationWork()) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        raw = connection.connection.driver_connection
    assert caught.value is interruption and state.commit_acknowledged
    assert state.cleanup_failed and len(calls) == 2
    assert engine.pool.checkedout() == 0 and rows(engine) == [1]
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")


def test_worst_cleanup_chain_stays_inside_reserved_attempts(engine, monkeypatch):
    work = OperationWork()
    state = TransactionOutcome()
    original_remove, original_close = event.remove, Connection.close

    def bad_remove(target, name, callback):
        original_remove(target, name, callback)
        raise RuntimeError("PRIVATE-DETACH")

    closes = 0

    def bad_close(connection):
        nonlocal closes
        closes += 1
        if closes == 1:
            raise RuntimeError("PRIVATE-CLOSE")
        original_close(connection)

    monkeypatch.setattr(event, "remove", bad_remove)
    monkeypatch.setattr(Connection, "close", bad_close)
    # Reach the ordinary ceiling after real setup/SQL, then force cleanup faults.
    work.statements = 498
    expected = ResourceNotFound()
    with (
        pytest.raises(ResourceNotFound) as caught,
        admission_transaction(engine, state, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        assert work.statements == 504
        raise expected
    assert caught.value is expected and state.cleanup_failed
    # discard for detach, rollback attempt, discard for invalidated rollback,
    # first close, discard for close, second close: six cleanup attempts.
    assert work.statements == 510 and closes == 2
    assert engine.pool.checkedout() == 0 and rows(engine) == []
