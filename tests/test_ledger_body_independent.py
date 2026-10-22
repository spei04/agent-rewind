"""Independent native checks for the excluded ledger-body capability."""

import json
import sqlite3

import pytest
from ledger_operator_fixture import (
    _CONNECT,
    assert_pool_released,
    ledger_case,
    proof_rows,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations import ledger_work
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["ledger_case"]


def _refused_without_native_work(case, connection):
    boundary = len(case.trace.events)
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        transaction._require_ledger_body(connection)
    assert case.trace.events[boundary:] == []


@pytest.fixture
def guard_trace(ledger_case, record_property):
    records = []
    yield records
    record_property("guard_boundaries", json.dumps(records))
    record_property("native_trace", json.dumps(ledger_case.trace.events))


@pytest.fixture
def guard_clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    return now


def test_live_guard_preserves_native_exclusion_and_owns_no_new_hooks(ledger_case, guard_trace):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        raw = connection.connection.driver_connection
        assert raw.in_transaction and connection.in_transaction()
        assert "BEGIN EXCLUSIVE" in case.trace.sql()
        lease = raw._ownership.lease
        listeners = tuple(work._listeners)
        ordinary = work.observed_ordinary
        boundary = len(case.trace.events)
        for _ in range(3):
            assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert work.observed_ordinary == ordinary
        assert raw._ownership.lease is lease and tuple(work._listeners) == listeners
        contender = _CONNECT(case.path, timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError) as caught:
                contender.execute("INSERT INTO proof VALUES (71)")
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        finally:
            contender.close()
        guard_trace.append({"live": True, "ordinary": ordinary, "contender": "SQLITE_BUSY"})
        connection.exec_driver_sql("INSERT INTO proof VALUES (70)")
    _refused_without_native_work(case, connection)
    with _CONNECT(case.path, timeout=0) as contender:
        contender.execute("INSERT INTO proof VALUES (71)")
    contender.close()
    assert proof_rows(case.path) == [70, 71]
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert_pool_released(case)


@pytest.mark.parametrize("state", ["unbegun", "logical", "native_exclusive"])
def test_unissued_connection_and_forged_info_never_grant_body(ledger_case, guard_trace, state):
    case = ledger_case
    engine = create_engine(f"sqlite:///{case.path}", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            if state == "logical":
                connection.begin()
            elif state == "native_exclusive":
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
            connection.info.update(
                {"ledger_body": True, "ledger_work": LedgerWork(), "excluded": True}
            )
            raw = connection.connection.driver_connection
            before = (connection.in_transaction(), raw.in_transaction)
            _refused_without_native_work(case, connection)
            assert (connection.in_transaction(), raw.in_transaction) == before
            guard_trace.append({"unissued_state": state, "native_transaction": before[1]})
    finally:
        engine.dispose()
    assert proof_rows(case.path) == []


@pytest.mark.parametrize("after_exclusion", [False, True])
def test_failed_begin_has_no_live_body_before_or_after_native_exclusion(
    ledger_case, guard_trace, monkeypatch, after_exclusion
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    original = transaction._begin
    seen = []

    def begin(connection, result, budget):
        seen.append(connection)
        _refused_without_native_work(case, connection)
        if after_exclusion:
            original(connection, result, budget)
            assert connection.connection.driver_connection.in_transaction
            _refused_without_native_work(case, connection)
        guard_trace.append({"begin_failure_after_exclusion": after_exclusion})
        raise MigrationRefused("schema_incompatible")

    monkeypatch.setattr(transaction, "_begin", begin)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("failed exclusion yielded a body")
    assert len(seen) == 1
    _refused_without_native_work(case, seen[0])
    assert ("BEGIN EXCLUSIVE" in case.trace.sql()) is after_exclusion
    assert ("ROLLBACK" in case.trace.sql()) is after_exclusion
    assert not outcome.commit_attempted and not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    assert_pool_released(case)


@pytest.mark.parametrize("after_publication", [False, True])
def test_partial_publication_is_revoked_before_cleanup(
    ledger_case, guard_trace, monkeypatch, after_publication
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    original = transaction._register_ledger_body
    detach = work._detach
    seen = []
    cleanup = []

    def register(connection, claim, budget, receipt):
        seen.append(connection)
        _refused_without_native_work(case, connection)
        if after_publication:
            original(connection, claim, budget, receipt)
            assert transaction._require_ledger_body(connection) is budget
        raise MigrationRefused("schema_incompatible")

    def detached():
        _refused_without_native_work(case, seen[0])
        cleanup.append("detached_after_revocation")
        return detach()

    monkeypatch.setattr(transaction, "_register_ledger_body", register)
    monkeypatch.setattr(work, "_detach", detached)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("partial publication yielded a body")
    assert cleanup == ["detached_after_revocation"] and len(seen) == 1
    _refused_without_native_work(case, seen[0])
    assert "BEGIN EXCLUSIVE" in case.trace.sql() and "ROLLBACK" in case.trace.sql()
    assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    guard_trace.append({"after_publication": after_publication, "cleanup": cleanup})
    assert_pool_released(case)


@pytest.mark.parametrize("exit_kind", ["normal", "typed", "error", "interrupt", "close"])
def test_every_body_exit_revokes_before_commit_preparation_detach_and_close(
    ledger_case, guard_trace, monkeypatch, exit_kind
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    prepare, detach, close = work._prepare_target, work._detach, Connection.close
    target = []
    ending = [False]
    checks = []

    def check(stage):
        if ending[0]:
            _refused_without_native_work(case, target[0])
            checks.append(stage)

    def prepared():
        check("commit_prepare")
        return prepare()

    def detached():
        check("detach")
        return detach()

    def closed(connection):
        if target and connection is target[0]:
            check("close")
        return close(connection)

    monkeypatch.setattr(work, "_prepare_target", prepared)
    monkeypatch.setattr(work, "_detach", detached)
    monkeypatch.setattr(Connection, "close", closed)
    context = ledger_transaction(case.engine, outcome, work=work)
    connection = context.__enter__()
    target.append(connection)
    assert transaction._require_ledger_body(connection) is work
    connection.exec_driver_sql("INSERT INTO proof VALUES (72)")
    ending[0] = True
    if exit_kind == "normal":
        context.__exit__(None, None, None)
    elif exit_kind == "close":
        context.gen.close()
    else:
        error = {
            "typed": MigrationRefused("schema_incompatible"),
            "error": RuntimeError("body-fault"),
            "interrupt": KeyboardInterrupt("first-body-interruption"),
        }[exit_kind]
        if exit_kind == "error":
            with pytest.raises(MigrationRefused, match="^migration_database_failure$"):
                context.__exit__(type(error), error, error.__traceback__)
        else:
            # contextlib suppresses the identical exception at this explicit boundary.
            assert context.__exit__(type(error), error, error.__traceback__) is False
    assert checks == (
        ["commit_prepare", "detach", "close"] if exit_kind == "normal" else ["detach", "close"]
    )
    _refused_without_native_work(case, connection)
    assert outcome.commit_acknowledged is (exit_kind == "normal")
    assert not outcome.cleanup_failed
    assert proof_rows(case.path) == ([72] if exit_kind == "normal" else [])
    guard_trace.append({"exit_kind": exit_kind, "revoked_at": checks})
    assert_pool_released(case)


@pytest.mark.parametrize("mutation", ["rollback", "commit", "close", "invalidate", "new_root"])
def test_changed_native_or_logical_transaction_refuses_without_reconnect(
    ledger_case, guard_trace, mutation
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    observed = []
    try:
        with ledger_transaction(case.engine, outcome, work=work) as connection:
            assert transaction._require_ledger_body(connection) is work
            if mutation == "new_root":
                connection.rollback()
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
                assert connection.connection.driver_connection.in_transaction
            else:
                getattr(connection, mutation)()
            _refused_without_native_work(case, connection)
            observed.append(mutation)
            raise MigrationRefused("schema_incompatible")
    except MigrationRefused as error:
        assert str(error) in {"schema_incompatible", "ledger_outcome_uncertain"}
    assert observed == [mutation]
    assert not outcome.commit_attempted and proof_rows(case.path) == []
    guard_trace.append({"changed_transaction": mutation, "cleanup_failed": outcome.cleanup_failed})
    assert_pool_released(case)


def test_active_savepoint_refuses_and_restored_outer_body_stays_valid(ledger_case, guard_trace):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert transaction._require_ledger_body(connection) is work
        with connection.begin_nested():
            assert connection.in_nested_transaction()
            _refused_without_native_work(case, connection)
        assert transaction._require_ledger_body(connection) is work
        connection.exec_driver_sql("INSERT INTO proof VALUES (73)")
    assert any(sql.startswith("SAVEPOINT") for sql in case.trace.sql())
    assert outcome.commit_acknowledged and proof_rows(case.path) == [73]
    guard_trace.append({"nested_refused": True, "original_outer_restored": True})
    assert_pool_released(case)


def test_stale_connection_cannot_use_or_revoke_a_new_checkout_body(
    ledger_case, guard_trace, monkeypatch
):
    case = ledger_case
    old_work = LedgerWork()
    with ledger_transaction(case.engine, LedgerOutcome(), work=old_work) as old:
        raw = old.connection.driver_connection
        old_receipt = raw._ownership.receipt
        assert transaction._require_ledger_body(old) is old_work
    work, outcome = LedgerWork(), LedgerOutcome()
    callbacks = []

    def progress():
        callbacks.append(True)
        return 0

    monkeypatch.setattr(work, "_progress", progress)
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        receipt = raw._ownership.receipt
        assert connection.connection.driver_connection is raw
        assert receipt.generation > old_receipt.generation
        boundary = len(case.trace.events)
        _refused_without_native_work(case, old)
        transaction._revoke_ledger_body(old)
        assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert raw._ownership.lease is work._lease
        assert (
            connection.exec_driver_sql(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000) "
                "SELECT sum(x) FROM n"
            ).scalar_one()
            == 2001000
        )
        assert callbacks
        connection.exec_driver_sql("INSERT INTO proof VALUES (74)")
        guard_trace.append({"generations": [old_receipt.generation, receipt.generation]})
    assert outcome.commit_acknowledged and proof_rows(case.path) == [74]
    assert_pool_released(case)


def test_property_only_guard_does_not_refund_or_reset_full_ordinary_budget(
    ledger_case, guard_trace
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        work.reserve_ordinary(2028 - work.observed_ordinary)
        boundary = len(case.trace.events)
        for _ in range(3):
            assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert (work.prepaid_bootstrap, work.prepaid_cleanup, work.observed_ordinary) == (
            12,
            8,
            2028,
        )
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert "COMMIT" not in case.trace.sql()
    assert proof_rows(case.path) == []
    guard_trace.append({"ordinary": 2028, "prepaid": 20, "commit_refused": True})
    assert_pool_released(case)


def test_expired_live_body_refuses_before_native_work(ledger_case, guard_trace, guard_clock):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^migration_busy$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        assert transaction._require_ledger_body(connection) is work
        guard_clock[0] += 121
        boundary = len(case.trace.events)
        ordinary = work.observed_ordinary
        try:
            transaction._require_ledger_body(connection)
        finally:
            assert case.trace.events[boundary:] == [] and work.observed_ordinary == ordinary
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    guard_trace.append({"expired": True, "ordinary_unchanged": ordinary})
    assert_pool_released(case)


def test_committed_cleanup_fault_leaves_no_live_guard_or_reusable_engine(
    ledger_case, guard_trace, monkeypatch
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    close = Connection.close
    target, faults = [], []

    def failed_close(connection):
        if target and connection is target[0] and not faults:
            _refused_without_native_work(case, connection)
            faults.append(True)
            raise RuntimeError("first-close-fault")
        return close(connection)

    monkeypatch.setattr(Connection, "close", failed_close)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        target.append(connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (75)")
    assert faults == [True]
    _refused_without_native_work(case, connection)
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert proof_rows(case.path) == [75]
    boundary = len(case.trace.events)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("uncertain cleanup published a reusable engine")
    assert case.trace.events[boundary:] == []
    guard_trace.append({"commit_visible": True, "cleanup_failed": True, "guard_revoked": True})
    assert_pool_released(case)
