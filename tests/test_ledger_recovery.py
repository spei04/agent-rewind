"""Fresh recovery classification and actual SQLite transaction uncertainty."""

import sqlite3
from contextlib import closing
from copy import deepcopy

import pytest
from ledger_provisioning_fixture import (
    assert_stage,
    build_case,
    digest,
    identity,
    initial_manifest,
    invoke,
    next_manifest,
    snapshot,
)
from ledger_recovery_fixture import fresh_reentry, observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning
from agent_rewind.migrations.schema import MigrationRefused


@pytest.fixture
def legacy(tmp_path):
    fixture = build_case(tmp_path / "recovery.sqlite")
    try:
        yield fixture
    finally:
        fixture.close()


def completed(fixture, *, later=False):
    manifests = [initial_manifest(fixture)]
    receipts = [invoke(fixture, manifests[0])]
    if later:
        manifests.append(next_manifest(manifests[0]))
        receipts.append(invoke(fixture, manifests[-1]))
    assert_stage(fixture, manifests, receipts)
    return manifests, receipts


def pending(fixture, operation):
    if operation == "initialize":
        return initial_manifest(fixture), [], []
    manifests, receipts = completed(fixture)
    return next_manifest(manifests[0]), manifests, receipts


def assert_staged_native_write(watch):
    marker = next(item for item in watch.markers if item[0] == "progress.insert.return")
    assert marker[1] == id(watch.work._raw)
    prefix = watch.trace.events[: marker[2]]
    insert_positions = [
        index
        for index, item in enumerate(prefix)
        if item[0] == "sql"
        and item[2] == marker[1]
        and item[3].lstrip().startswith("INSERT INTO migration_progress")
    ]
    assert insert_positions
    assert any(
        item[0] == "c_return" and item[2:] == (marker[1], "execute")
        for item in prefix[insert_positions[-1] + 1 :]
    )
    assert watch.faults.count("body.after_progress") == 1


def assert_recovered_stage(fixture, manifests, receipts, target, recovered):
    # Adapt an independently recovered persisted receipt for the existing state
    # oracle; the failed writer call never returned a successful provisioning.
    persisted = LedgerProvisioning(**recovered.model_dump(mode="json"), outcome="complete")
    assert_stage(fixture, [*manifests, target], [*receipts, persisted])


@pytest.mark.parametrize("selected", [0, 1], ids=["old-M0", "completed-M1"])
def test_fresh_reentry_recovers_original_receipt_after_actual_s2(
    legacy, monkeypatch, record_property, selected
):
    manifests, receipts = completed(legacy, later=True)
    recovered, watch = fresh_reentry(legacy, manifests[selected], monkeypatch, record_property)
    assert recovered.model_dump(mode="json") == receipts[selected].model_dump(
        mode="json", exclude={"outcome"}
    )
    assert recovered.sequence == selected
    assert recovered.initialized_at == receipts[selected].initialized_at
    assert watch.outcome.commit_acknowledged
    assert_stage(legacy, manifests, receipts)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_fresh_reentry_proves_absence_at_exact_parent_without_retry(
    legacy, monkeypatch, record_property, operation
):
    target, _, _ = pending(legacy, operation)
    recovered, watch = fresh_reentry(legacy, target, monkeypatch, record_property)
    assert recovered is None
    assert watch.outcome.commit_acknowledged


@pytest.mark.parametrize(
    "case,code",
    [
        ("changed-M0", "ledger_manifest_conflict"),
        ("changed-M1", "ledger_manifest_conflict"),
        ("advanced-parent", "ledger_manifest_conflict"),
        ("partial-account-id", "ledger_manifest_conflict"),
        ("partial-scope-start", "ledger_manifest_conflict"),
        ("corrupt-progress", "ledger_progress_invalid"),
        ("corrupt-current-job", "ledger_history_unsupported"),
    ],
)
def test_fresh_reentry_refuses_conflicting_or_incomplete_current_state(
    legacy, monkeypatch, record_property, case, code
):
    manifests, _ = completed(legacy, later=case in {"changed-M0", "changed-M1", "advanced-parent"})
    target = next_manifest(manifests[0])
    if case == "changed-M0":
        target = deepcopy(manifests[0])
        target["accounts"][0]["limit_microusd"] += 1
    elif case == "changed-M1":
        target = deepcopy(manifests[1])
        target["parent_manifest_digest"] = "f" * 64
    elif case == "advanced-parent":
        target["manifest_id"] = identity(1002)
        # Both requested identities are absent; the stale parent alone refuses.
        for index, row in enumerate(target["accounts"]):
            row["id"] = identity(500 + index)
            row["period_start"] = "2200-01-01T00:00:00.000000Z"
            row["period_end"] = "2300-01-01T00:00:00.000000Z"
    elif case == "partial-account-id":
        target["accounts"][0]["id"] = manifests[0]["accounts"][0]["id"]
    elif case == "partial-scope-start":
        target["accounts"][0]["period_start"] = manifests[0]["accounts"][0]["period_start"]
        target["accounts"][0]["period_end"] = manifests[0]["accounts"][0]["period_end"]
    else:
        # Explicit malformed native fixtures. They are not writer-produced states.
        with closing(sqlite3.connect(legacy.case.path)) as connection, connection:
            if case == "corrupt-progress":
                connection.execute(
                    "UPDATE migration_progress SET cursor='{}' WHERE phase=?",
                    ("ledger_manifest_" + manifests[0]["manifest_id"],),
                )
            else:
                connection.execute(
                    "UPDATE jobs SET legacy_reserved_microusd=legacy_reserved_microusd+1 "
                    "WHERE id=?",
                    (legacy.jobs[0]["id"],),
                )
    validate_ledger_manifest(target)
    if case in {"partial-account-id", "partial-scope-start"}:
        assert target["parent_manifest_digest"] == digest(manifests[0])
    with pytest.raises(MigrationRefused, match="^" + code + "$"):
        fresh_reentry(legacy, target, monkeypatch, record_property)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_physical_commit_uncertainty_requires_fresh_reentry(
    legacy, monkeypatch, record_property, operation, boundary
):
    target, manifests, receipts = pending(legacy, operation)
    before = snapshot(legacy.case.path)
    with (
        observe_command(
            legacy, monkeypatch, record_property, label="uncertain_commit", commit_fault=boundary
        ) as watch,
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
    ):
        ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(target))
    watch.assert_single_attempt()
    assert watch.faults == ["commit." + boundary]
    assert watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
    assert not watch.outcome.confirmed_precommit_rollback
    assert [item[0] for item in watch.markers].count("commit.before_native") == 1
    assert watch.trace.sql().count("COMMIT") == int(boundary == "after")
    assert len(watch.trace.calls("commit")) == int(boundary == "after")
    assert sum(
        item[0] == "c_return" and item[2:] == (id(watch.work._raw), "commit")
        for item in watch.trace.events
    ) == int(boundary == "after")
    assert all(item[1] == id(watch.work._raw) for item in watch.markers)
    recovered, _ = fresh_reentry(legacy, target, monkeypatch, record_property, previous=watch)
    if boundary == "before":
        assert recovered is None
        assert snapshot(legacy.case.path) == before
    else:
        assert recovered.manifest_digest == digest(target)
        assert_recovered_stage(legacy, manifests, receipts, target, recovered)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_commit_ack_then_delegated_close_failure_never_returns_success(
    legacy, monkeypatch, record_property, operation
):
    target, manifests, receipts = pending(legacy, operation)
    with (
        observe_command(
            legacy,
            monkeypatch,
            record_property,
            label="uncertain_close",
            close_error=RuntimeError("controlled post-close acknowledgement loss"),
        ) as watch,
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
    ):
        ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(target))
    watch.assert_single_attempt()
    assert watch.faults == ["close.after"]
    assert watch.outcome.commit_acknowledged and watch.outcome.cleanup_failed
    assert not watch.outcome.rollback_attempted
    names = [item[0] for item in watch.markers]
    assert names.index("commit.native_ack") < names.index("connection.close.return")
    assert watch.trace.sql().count("COMMIT") == 1
    assert watch.trace.sql().count("ROLLBACK") == 0
    assert names.index("connection.close.return") < names.index("raw.close.native_ack")
    recovered, _ = fresh_reentry(legacy, target, monkeypatch, record_property, previous=watch)
    assert_recovered_stage(legacy, manifests, receipts, target, recovered)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_physical_rollback_failure_reports_uncertainty_but_fresh_state_is_absent(
    legacy, monkeypatch, record_property, operation, boundary
):
    target, _, _ = pending(legacy, operation)
    before = snapshot(legacy.case.path)
    with (
        observe_command(
            legacy,
            monkeypatch,
            record_property,
            label="uncertain_rollback",
            body_error=RuntimeError("controlled failure after actual progress INSERT"),
            rollback_fault=boundary,
        ) as watch,
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
    ):
        ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(target))
    watch.assert_single_attempt()
    assert_staged_native_write(watch)
    assert watch.faults == ["body.after_progress", "rollback." + boundary]
    assert not watch.outcome.commit_attempted
    assert watch.outcome.rollback_attempted and not watch.outcome.rollback_acknowledged
    assert watch.outcome.cleanup_failed and not watch.outcome.confirmed_precommit_rollback
    assert watch.trace.sql().count("COMMIT") == 0
    assert watch.trace.sql().count("ROLLBACK") == int(boundary == "after")
    assert snapshot(legacy.case.path) == before
    recovered, _ = fresh_reentry(legacy, target, monkeypatch, record_property, previous=watch)
    assert recovered is None


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_first_base_exception_identity_survives_later_cleanup_interruption(
    legacy, monkeypatch, record_property, operation
):
    target, _, _ = pending(legacy, operation)
    before = snapshot(legacy.case.path)
    first = KeyboardInterrupt("first physical progress-write interruption")
    later = SystemExit("later delegated-close interruption")
    with (
        observe_command(
            legacy,
            monkeypatch,
            record_property,
            label="first_interruption",
            body_error=first,
            close_error=later,
        ) as watch,
        pytest.raises(KeyboardInterrupt) as raised,
    ):
        ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(target))
    assert raised.value is first
    watch.assert_single_attempt()
    assert_staged_native_write(watch)
    assert watch.faults == ["body.after_progress", "close.after"]
    assert not watch.outcome.commit_attempted
    assert watch.outcome.rollback_acknowledged and watch.outcome.cleanup_failed
    assert watch.trace.sql().count("ROLLBACK") == 1
    assert snapshot(legacy.case.path) == before
    recovered, _ = fresh_reentry(legacy, target, monkeypatch, record_property, previous=watch)
    assert recovered is None
