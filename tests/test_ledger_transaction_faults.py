"""Actual transaction effects and failure truth, separate from provisioning."""

import sqlite3

import pytest
from ledger_operator_fixture import (
    _CONNECT,
    assert_closed,
    assert_pool_released,
    ledger_case,
    proof_rows,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["ledger_case"]


def test_commit_and_typed_rollback_have_independent_sql_visibility(ledger_case):
    case = ledger_case
    success = LedgerOutcome()
    with ledger_transaction(case.engine, success, work=LedgerWork()) as connection:
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
    assert success.begin_attempted and success.begun
    assert success.commit_attempted and success.commit_acknowledged
    assert not success.cleanup_failed and not success.confirmed_precommit_rollback
    assert proof_rows(case.path) == [1]

    refusal = MigrationRefused("schema_incompatible")
    rollback = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(case.engine, rollback, work=LedgerWork()) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES (2)")
        raise refusal
    assert caught.value is refusal
    assert rollback.confirmed_precommit_rollback and not rollback.commit_attempted
    assert not rollback.cleanup_failed
    assert proof_rows(case.path) == [1]
    assert_pool_released(case)
    assert len(case.trace.raws) == 1  # Clean sequential invocations reuse the native handle.


@pytest.mark.parametrize("after_commit", [False, True])
def test_lost_commit_ack_is_uncertain_even_if_later_rollback_returns(
    ledger_case, monkeypatch, after_commit
):
    case = ledger_case
    outcome = LedgerOutcome()
    original = Connection.commit
    target = []
    calls = []

    def lose_ack(connection):
        if target and connection is target[0]:
            calls.append(connection)
            if after_commit:
                original(connection)
            raise RuntimeError("private-commit-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "commit", lose_ack)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (7)")
    assert len(calls) == 1
    assert outcome.commit_attempted and not outcome.commit_acknowledged
    assert not outcome.confirmed_precommit_rollback
    assert proof_rows(case.path) == ([7] if after_commit else [])
    assert_pool_released(case)


@pytest.mark.parametrize("after_close", [False, True])
def test_acknowledged_commit_with_close_fault_never_returns_completion(
    ledger_case, monkeypatch, after_close
):
    case = ledger_case
    outcome = LedgerOutcome()
    original = Connection.close
    target = []
    failures = []

    def close_once(connection):
        if target and connection is target[0] and not failures:
            failures.append(connection)
            if after_close:
                original(connection)
            raise RuntimeError("private-close-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "close", close_once)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection)
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (8)")
    assert len(failures) == 1
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert proof_rows(case.path) == [8]
    assert_closed(raw)
    assert_pool_released(case)


def test_unacknowledged_rollback_is_not_reported_as_certain_absence(ledger_case, monkeypatch):
    case = ledger_case
    outcome = LedgerOutcome()
    original = Connection.rollback
    target = []
    calls = []

    def fail_rollback(connection):
        if target and connection is target[0]:
            calls.append(connection)
            raise RuntimeError("private-rollback-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "rollback", fail_rollback)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection)
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (9)")
        raise MigrationRefused("schema_incompatible")
    assert len(calls) == 1
    assert outcome.rollback_attempted and not outcome.rollback_acknowledged
    assert not outcome.commit_attempted and not outcome.confirmed_precommit_rollback
    assert outcome.cleanup_failed
    assert proof_rows(case.path) == []
    assert_closed(raw)
    assert_pool_released(case)


def test_fault_after_real_begin_keeps_attempt_without_fabricating_begin_return(
    ledger_case, monkeypatch
):
    case = ledger_case
    outcome = LedgerOutcome()
    original = Connection.exec_driver_sql
    native_begun = []
    body = []

    def after_begin(connection, statement, *args, **kwargs):
        result = original(connection, statement, *args, **kwargs)
        if statement == "BEGIN EXCLUSIVE":
            raw = connection.connection.driver_connection
            native_begun.append(raw.in_transaction)
            raise RuntimeError("private-after-native-begin")
        return result

    monkeypatch.setattr(Connection, "exec_driver_sql", after_begin)
    with (
        pytest.raises(MigrationRefused, match="^migration_database_failure$"),
        ledger_transaction(case.engine, outcome, work=LedgerWork()),
    ):
        body.append(True)
    assert native_begun == [True] and body == []
    assert outcome.begin_attempted and not outcome.begun
    assert outcome.rollback_attempted and outcome.rollback_acknowledged
    assert not outcome.confirmed_precommit_rollback
    assert not outcome.commit_attempted
    assert proof_rows(case.path) == []
    assert_pool_released(case)


def test_unaffordable_begin_bundle_does_not_claim_native_begin_attempt(ledger_case, monkeypatch):
    case = ledger_case
    outcome = LedgerOutcome()
    work = LedgerWork()
    original = Connection.exec_driver_sql
    before_begin = []

    def use_remaining_after_foreign_key_setup(connection, statement, *args, **kwargs):
        result = original(connection, statement, *args, **kwargs)
        if statement == "PRAGMA foreign_keys=ON":
            before_begin.append(connection.connection.driver_connection.in_transaction)
            work.reserve_ordinary(2028 - work.observed_ordinary)
        return result

    monkeypatch.setattr(Connection, "exec_driver_sql", use_remaining_after_foreign_key_setup)
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("body entered without an affordable native BEGIN")
    assert before_begin == [False]
    assert "BEGIN EXCLUSIVE" not in case.trace.sql()
    assert not outcome.begin_attempted and not outcome.begun
    assert not outcome.commit_attempted
    assert proof_rows(case.path) == []
    assert_pool_released(case)
    assert str(caught.value) == "ledger_limit_exceeded"


def test_generic_integrity_failure_is_not_an_immutable_manifest_conflict(ledger_case):
    case = ledger_case
    outcome = LedgerOutcome()
    error = IntegrityError("private-statement-canary", {}, ValueError("private-driver-canary"))
    with (
        pytest.raises(MigrationRefused, match="^migration_database_failure$") as caught,
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES (11)")
        raise error
    assert "private" not in str(caught.value)
    assert outcome.confirmed_precommit_rollback
    assert proof_rows(case.path) == []
    assert_pool_released(case)


def test_first_interruption_survives_a_distinct_cleanup_interruption(ledger_case, monkeypatch):
    case = ledger_case
    outcome = LedgerOutcome()
    first = KeyboardInterrupt("first-private-interruption")
    second = SystemExit("second-private-interruption")
    original = Connection.close
    target = []
    failures = []

    def fail_close_once(connection):
        if target and connection is target[0] and not failures:
            failures.append(True)
            raise second
        return original(connection)

    monkeypatch.setattr(Connection, "close", fail_close_once)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection)
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (12)")
        raise first
    assert caught.value is first and failures == [True]
    assert outcome.cleanup_failed and outcome.rollback_acknowledged
    assert not outcome.commit_attempted
    assert proof_rows(case.path) == []
    assert_closed(raw)
    assert_pool_released(case)


@pytest.mark.parametrize("after_release", [False, True])
def test_failed_lease_release_skips_restore_and_keeps_bounded_disposal(
    ledger_case, monkeypatch, after_release
):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    original = ownership.ProgressLease.release
    failed = []
    calls = []
    boundary = []
    target = []
    close_failures = []
    original_close = Connection.close

    def fail_once(lease):
        calls.append(lease)
        if not failed:
            failed.append(lease)
            boundary.append(len(case.trace.events))
            if after_release:
                original(lease)
            raise RuntimeError("private-lease-release")
        return original(lease)

    def fail_initial_close(connection):
        if target and connection is target[0] and not close_failures:
            close_failures.append(True)
            raise RuntimeError("private-initial-logical-close")
        return original_close(connection)

    monkeypatch.setattr(Connection, "close", fail_initial_close)
    monkeypatch.setattr(ownership.ProgressLease, "release", fail_once)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        target.append(connection)
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (13)")
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert len(failed) == 1 and close_failures == [True]
    assert len(calls) == (1 if after_release else 2)
    assert all("busy_timeout" not in sql.lower() for sql in case.trace.sql(boundary[0]))
    assert len(work.cleanup_observations) <= 8
    assert proof_rows(case.path) == [13]
    assert_closed(raw)
    assert_pool_released(case)


def test_accounting_interruption_precedes_later_lease_release_interruption(
    ledger_case, monkeypatch
):
    case = ledger_case
    work = LedgerWork()
    outcome = LedgerOutcome()
    first = KeyboardInterrupt("first-detach-accounting")
    second = KeyboardInterrupt("second-lease-release")
    original_observe = work.observe_cleanup
    original_release = ownership.ProgressLease.release
    calls = []

    def observe_then_interrupt(kind):
        original_observe(kind)
        if kind == "detach":
            calls.append("observed-detach")
            raise first

    def release_then_interrupt(lease):
        original_release(lease)
        if "released-lease" not in calls:
            calls.append("released-lease")
            raise second

    monkeypatch.setattr(work, "observe_cleanup", observe_then_interrupt)
    monkeypatch.setattr(ownership.ProgressLease, "release", release_then_interrupt)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("INSERT INTO proof VALUES (14)")
    assert calls == ["observed-detach", "released-lease"]
    assert caught.value is first
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert proof_rows(case.path) == [14]
    assert_closed(raw)
    assert_pool_released(case)


def test_native_busy_from_commit_setter_preserves_certain_busy_classification(
    ledger_case, monkeypatch
):
    case = ledger_case
    outcome = LedgerOutcome()
    original = ownership._TrackedSQLite.execute
    target = []
    armed = [False]
    observed_codes = []

    def busy_after_real_setter(raw, statement, *args, **kwargs):
        result = original(raw, statement, *args, **kwargs)
        if (
            target
            and raw is target[0]
            and armed[0]
            and statement.startswith("PRAGMA busy_timeout=")
        ):
            armed[0] = False
            contender = _CONNECT(case.path, timeout=0)
            try:
                contender.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError as error:
                observed_codes.append(error.sqlite_errorcode)
                raise
            finally:
                contender.close()
            pytest.fail("independent contender did not observe the held exclusive lock")
        return result

    monkeypatch.setattr(ownership._TrackedSQLite, "execute", busy_after_real_setter)
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(case.engine, outcome, work=LedgerWork()) as connection,
    ):
        target.append(connection.connection.driver_connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (15)")
        armed[0] = True
    assert observed_codes == [sqlite3.SQLITE_BUSY]
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    assert_pool_released(case)
    assert str(caught.value) == "migration_busy"
