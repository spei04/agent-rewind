"""Ledger caller lifecycle faults with independent native and control traces."""

import json
import sqlite3

import pytest
from ledger_operator_fixture import (
    assert_closed,
    assert_pool_released,
    ledger_case,
    proof_rows,
)
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.pool.base import _ConnectionFairy

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["ledger_case"]


@pytest.fixture
def lifecycle(ledger_case, monkeypatch, record_property):
    """Observe caller boundaries without adding factory event hooks."""
    calls = []
    receipts = []
    original_connect = transaction.connect_owned
    original_cleanup = ownership._cleanup
    original_finish = transaction.finish_owned

    def connect(*args, **kwargs):
        calls.append("connect")
        return original_connect(*args, **kwargs)

    def cleanup(receipt, connection, *args, **kwargs):
        calls.append("acquisition_cleanup" if connection is None else "connection_cleanup")
        receipts.append(
            {
                "receipt": id(receipt),
                "raw": receipt.raw is not None,
                "proxy": receipt.proxy is not None,
                "connection": connection is not None,
            }
        )
        return original_cleanup(receipt, connection, *args, **kwargs)

    def finish(*args, **kwargs):
        calls.append("finish")
        return original_finish(*args, **kwargs)

    monkeypatch.setattr(transaction, "connect_owned", connect)
    monkeypatch.setattr(ownership, "_cleanup", cleanup)
    monkeypatch.setattr(transaction, "finish_owned", finish)
    yield calls, receipts
    record_property("caller_controls", json.dumps(calls))
    record_property("acquisition_receipts", json.dumps(receipts))
    record_property("native_trace", json.dumps(ledger_case.trace.events))


@pytest.mark.parametrize(
    "stage", ["no_raw", "raw_without_proxy", "proxy_without_connection", "attestation"]
)
def test_acquisition_failure_uses_one_cleanup_and_no_returned_finish(
    ledger_case, lifecycle, monkeypatch, stage
):
    case = ledger_case
    calls, receipts = lifecycle
    failure = RuntimeError("acquisition-fault")
    faults = []
    if stage == "no_raw":

        def fail_connect(*args, **kwargs):
            faults.append(stage)
            raise failure

        monkeypatch.setattr(sqlite3, "connect", fail_connect)
    elif stage == "raw_without_proxy":
        dialect = type(case.engine.dialect)

        def fail_isolation(self, raw):
            faults.append(stage)
            raise failure

        monkeypatch.setattr(dialect, "get_isolation_level", fail_isolation)
    elif stage == "proxy_without_connection":
        initialize = Connection.__init__

        def fail_constructor(instance, *args, **kwargs):
            initialize(instance, *args, **kwargs)
            if instance.engine is case.engine and kwargs.get("_has_events") is not False:
                faults.append(stage)
                raise failure

        monkeypatch.setattr(Connection, "__init__", fail_constructor)
    else:
        attest = ownership._attest_checkout

        def fail_attestation(engine, connection, receipt, **kwargs):
            attest(engine, connection, receipt, **kwargs)
            if engine is case.engine:
                faults.append(stage)
                raise failure

        monkeypatch.setattr(ownership, "_attest_checkout", fail_attestation)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused),
        ledger_transaction(case.engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("partial acquisition yielded the body")
    assert faults == [stage]
    assert calls.count("connect") == 1 and calls.count("finish") == 0
    assert len(receipts) == 1
    assert receipts[0]["raw"] is (stage != "no_raw")
    assert receipts[0]["proxy"] is (stage in {"proxy_without_connection", "attestation"})
    assert receipts[0]["connection"] is (stage == "attestation")
    assert not outcome.begin_attempted and not outcome.commit_attempted
    assert "BEGIN EXCLUSIVE" not in case.trace.sql()
    for raw in case.trace.raws:
        assert_closed(raw)
    assert proof_rows(case.path) == []
    assert_pool_released(case)


@pytest.mark.parametrize("after_native", [False, True])
def test_partial_native_install_retains_first_interruption_and_disposes(
    ledger_case, lifecycle, monkeypatch, after_native
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    first = KeyboardInterrupt("native-install-fault")
    progress = ownership._TrackedSQLite._native_progress
    installs = []

    def fail_install(raw, callback, interval):
        if callback is not None and not installs:
            installs.append(raw)
            if after_native:
                progress(raw, callback, interval)
            raise first
        return progress(raw, callback, interval)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_progress", fail_install)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("partial native installation yielded the body")
    assert caught.value is first and len(installs) == 1
    assert lifecycle[0].count("finish") == 1
    assert not outcome.begin_attempted and not outcome.commit_attempted
    assert "BEGIN EXCLUSIVE" not in case.trace.sql()
    assert installs[0]._ownership.lease is None
    assert_closed(installs[0])
    assert_pool_released(case)


@pytest.mark.parametrize("name", ["before_cursor_execute", "after_cursor_execute"])
@pytest.mark.parametrize("after_action", [False, True])
@pytest.mark.parametrize("phase", ["registration", "removal"])
def test_partial_listener_fault_removes_or_disposes_owned_hooks(
    ledger_case, lifecycle, monkeypatch, name, after_action, phase
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    first = KeyboardInterrupt("owned-listener-fault")
    original = event.listen if phase == "registration" else event.remove
    attempts = []

    def fail_once(connection, identifier, callback, *args, **kwargs):
        ours = isinstance(connection, Connection) and getattr(callback, "__self__", None) is work
        if ours:
            attempts.append(identifier)
        if ours and identifier == name:
            if after_action:
                original(connection, identifier, callback, *args, **kwargs)
            raise first
        return original(connection, identifier, callback, *args, **kwargs)

    monkeypatch.setattr(event, "listen" if phase == "registration" else "remove", fail_once)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES (31)")
    assert caught.value is first and attempts.count(name) == 1
    assert lifecycle[0].count("finish") == 1
    assert work._connection.closed
    assert work._raw._ownership.lease is None
    if phase == "registration":
        assert not outcome.begin_attempted and not outcome.commit_attempted
        assert proof_rows(case.path) == []
        assert all(not event.contains(work._connection, key, fn) for key, fn in work._listeners)
        assert not outcome.cleanup_failed and not work._raw.in_transaction
        with ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()) as reused:
            assert reused.connection.driver_connection is work._raw
            assert reused.exec_driver_sql("SELECT 1").scalar_one() == 1
    else:
        assert_closed(work._raw)
        assert outcome.commit_acknowledged and outcome.cleanup_failed
        assert proof_rows(case.path) == [31]
        assert sorted(attempts) == ["after_cursor_execute", "before_cursor_execute"]
        for key, callback in work._listeners:
            assert event.contains(work._connection, key, callback) is (
                key == name and not after_action
            )
    assert_pool_released(case)


@pytest.mark.parametrize("failed_release", [False, True])
@pytest.mark.parametrize("observation", ["normal", "raises", "exhausted"])
def test_cleanup_outer_controls_fit_both_prepaid_branches_without_suppressing_actions(
    ledger_case, lifecycle, monkeypatch, record_property, failed_release, observation
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    controls, native_failures = [], []
    depth = [0]
    cleaning = [False]
    targets = []
    counts = {}
    detach = work._detach
    original_observe = work.observe_cleanup
    observe_calls = []
    lease_calls = []

    def observed(kind):
        observe_calls.append(kind)
        if observation == "raises":
            raise RuntimeError("cleanup-observer-fault")
        if observation == "exhausted":
            raise MigrationRefused("ledger_limit_exceeded")
        return original_observe(kind)

    def detached():
        cleaning[0] = True
        controls.append("detach")
        depth[0] += 1
        try:
            return detach()
        finally:
            depth[0] -= 1

    def watch(owner, name, label):
        original = getattr(owner, name)

        def action(target, *args, **kwargs):
            active = cleaning[0] and (
                target in targets
                or (isinstance(target, ownership.ProgressLease) and target._raw in case.trace.raws)
            )
            if not active:
                return original(target, *args, **kwargs)
            outer = depth[0] == 0
            if outer:
                controls.append(label)
            depth[0] += 1
            counts[label] = counts.get(label, 0) + 1
            try:
                if label == "lease_release":
                    lease_calls.append(target)
                    if failed_release and len(lease_calls) == 1:
                        raise RuntimeError("initial-release-fault")
                if label == "logical_close" and counts[label] <= 2:
                    raise RuntimeError("logical-close-fault")
                if label == "logical_invalidate":
                    raise RuntimeError("logical-invalidate-fault")
                return original(target, *args, **kwargs)
            finally:
                depth[0] -= 1

        monkeypatch.setattr(owner, name, action)

    for owner, name, label in [
        (Connection, "rollback", "rollback"),
        (Connection, "close", "logical_close"),
        (Connection, "invalidate", "logical_invalidate"),
        (_ConnectionFairy, "invalidate", "proxy_invalidate"),
        (_ConnectionFairy, "close", "proxy_close"),
        (ownership._TrackedSQLite, "close", "raw_close"),
        (ownership.ProgressLease, "release", "lease_release"),
    ]:
        watch(owner, name, label)

    native_close = ownership._TrackedSQLite._native_close

    def fail_first_physical_close(raw):
        if cleaning[0] and raw in targets and not native_failures:
            native_failures.append(raw)
            raise RuntimeError("physical-close-fault")
        return native_close(raw)

    execute = ownership._TrackedSQLite.execute

    def restoration(raw, sql, *args, **kwargs):
        if cleaning[0] and raw in targets and sql.startswith("PRAGMA busy_timeout="):
            controls.append("restore")
        return execute(raw, sql, *args, **kwargs)

    monkeypatch.setattr(work, "_detach", detached)
    monkeypatch.setattr(work, "observe_cleanup", observed)
    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", fail_first_physical_close)
    monkeypatch.setattr(ownership._TrackedSQLite, "execute", restoration)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        targets.extend([connection, connection.connection, raw])
        connection.exec_driver_sql("INSERT INTO proof VALUES (32)")
        work.reserve_ordinary(2028 - work.observed_ordinary)
        raise MigrationRefused("bounded-body-refusal")
    record_property("outer_controls", json.dumps(controls))
    record_property("observer_calls", json.dumps(observe_calls))
    record_property("release_identities", json.dumps([id(lease) for lease in lease_calls]))
    assert work.observed_ordinary == 2028
    assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
    expected = ["detach", "rollback"]
    if not failed_release and observation == "normal":
        expected.append("restore")
    expected.append("logical_close")
    if failed_release:
        expected.append("lease_release")
    expected += ["logical_invalidate", "logical_close", "proxy_invalidate", "raw_close"]
    assert controls == expected and len(controls) <= 8
    if observation == "normal":
        assert len(controls) == 8
    assert len(lease_calls) == (2 if failed_release else 1)
    assert all(lease is lease_calls[0] for lease in lease_calls)
    assert len(native_failures) == 1
    assert lifecycle[0].count("finish") == 1
    # An uncleared lease must block native rollback; disposal proves SQL absence.
    assert outcome.rollback_attempted and outcome.cleanup_failed
    assert outcome.rollback_acknowledged is (not failed_release)
    assert ("ROLLBACK" in case.trace.sql()) is (not failed_release)
    assert not outcome.commit_attempted and proof_rows(case.path) == []
    assert_closed(raw)
    assert_pool_released(case)


def test_stale_ledger_generation_cannot_clear_new_callback_or_invalidate_borrower(
    ledger_case, lifecycle, monkeypatch, record_property
):
    case = ledger_case
    old_work = LedgerWork()
    old_outcome = LedgerOutcome()
    with ledger_transaction(case.engine, old_outcome, work=old_work) as first:
        old_raw = first.connection.driver_connection
        old_receipt = old_raw._ownership.receipt
        old_lease = old_work._lease
        first.exec_driver_sql("INSERT INTO proof VALUES (33)")
    prior = ownership.cleanup_snapshot(old_receipt)
    assert old_outcome.commit_acknowledged and prior.clean
    new_work, outcome = LedgerWork(), LedgerOutcome()
    callbacks = []

    def progress():
        callbacks.append(True)
        return 0

    monkeypatch.setattr(new_work, "_progress", progress)
    with ledger_transaction(case.engine, outcome, work=new_work) as second:
        new_raw = second.connection.driver_connection
        new_receipt = new_raw._ownership.receipt
        assert new_raw is old_raw and new_receipt.generation > old_receipt.generation
        boundary = len(case.trace.events)
        old_lease.release()
        ownership._cleanup(old_receipt, first)
        ownership.close_owned(first, old_receipt)
        with pytest.raises(MigrationRefused, match="^migration_database_failure$"):
            old_work._detach()
        assert case.trace.events[boundary:] == []
        assert ownership.cleanup_snapshot(old_receipt) == prior
        assert new_raw._ownership.lease is new_work._lease
        before = len(callbacks)
        assert (
            second.exec_driver_sql(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000) "
                "SELECT sum(x) FROM n"
            ).scalar_one()
            == 2001000
        )
        assert len(callbacks) > before and new_raw.in_transaction
        second.exec_driver_sql("INSERT INTO proof VALUES (34)")
    record_property("generations", json.dumps([old_receipt.generation, new_receipt.generation]))
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert proof_rows(case.path) == [33, 34]
    assert_pool_released(case)
