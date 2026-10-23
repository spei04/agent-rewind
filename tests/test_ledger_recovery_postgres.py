"""Native recovery classification and real PostgreSQL transaction uncertainty."""

import json
from copy import deepcopy

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from ledger_provisioning_fixture import digest, identity, initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    build_postgres_case,
    invoke,
    native_snapshot,
)
from ledger_recovery_postgres_fixture import fresh_reentry, observe_command
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in actual PostgreSQL ledger recovery"
)


@pytest.fixture
def legacy(pg, observed_reader):
    fixture = build_postgres_case(pg)
    try:
        yield fixture
    finally:
        fixture.close()


def completed(fixture, pg, record_property, *, later=False):
    manifests = [initial_manifest(fixture)]
    receipts = [invoke(fixture, pg, manifests[0])]
    if later:
        manifests.append(next_manifest(manifests[0]))
        receipts.append(invoke(fixture, pg, manifests[-1]))
    assert_stage(
        fixture, pg, manifests, receipts, record_property=record_property, observation="setup"
    )
    return manifests, receipts


def pending(fixture, pg, record_property, operation):
    if operation == "initialize":
        return initial_manifest(fixture), [], []
    manifests, receipts = completed(fixture, pg, record_property)
    return next_manifest(manifests[0]), manifests, receipts


def assert_recovered_stage(fixture, pg, manifests, receipts, target, recovered, record_property):
    # Adapt an independently recovered persisted receipt only for the existing
    # state oracle. The uncertain writer never returned successful provisioning.
    persisted = LedgerProvisioning(**recovered.model_dump(mode="json"), outcome="complete")
    assert_stage(
        fixture,
        pg,
        [*manifests, target],
        [*receipts, persisted],
        record_property=record_property,
        observation="recovered",
    )


def assert_staged_native_write(watch):
    marker = next(row for row in watch.markers if row[0] == "progress.insert.return")
    assert marker[1] == id(watch.work._raw)
    prefix = watch.trace.events[: marker[2]]
    positions = [
        i
        for i, (_, kind, raw, sql) in enumerate(prefix)
        if kind == "sql-call"
        and raw == marker[1]
        and sql.lstrip().startswith("INSERT INTO migration_progress")
    ]
    assert positions
    _, _, raw, sql = prefix[positions[-1]]
    assert any(
        kind == "sql-return" and actual_raw == raw and actual_sql == sql
        for _, kind, actual_raw, actual_sql in prefix[positions[-1] + 1 :]
    )
    assert watch.faults.count("body.after_progress") == 1


def assert_commit_boundary(watch, boundary):
    marker = next(row for row in watch.markers if row[0] == "commit.before_native")
    prefix = watch.trace.events[: marker[2]]
    assert any(
        kind == "sql-return" and raw == marker[1] and sql.strip() == "SET CONSTRAINTS ALL IMMEDIATE"
        for _, kind, raw, sql in prefix
    )
    assert any(raw == marker[1] and position < marker[2] for raw, _, position in watch.xids)
    commits = [row for row in watch.physical if row["action"] == "commit"]
    assert len(commits) == int(boundary == "after")
    events = [row for row in watch.trace.events if row[2] == id(watch.work._raw)]
    assert sum(kind == "commit-call" for _, kind, _, _ in events) == int(boundary == "after")
    assert sum(kind == "commit-return" for _, kind, _, _ in events) == int(boundary == "after")
    assert sum(kind == "command" and sql.strip() == "COMMIT" for _, kind, _, sql in events) == int(
        boundary == "after"
    )
    if commits:
        assert commits[0]["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
        assert commits[0]["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)


def assert_rollback_boundary(watch, boundary):
    # Inspect the first attempted rollback before fallback cleanup. A later pool
    # reset may legitimately delegate another rollback after the injected fault.
    close = next(row for row in watch.markers if row[0] == "connection.close.before")
    prefix = watch.trace.events[: close[2]]
    rollbacks = [
        row
        for row in watch.physical
        if row["action"] == "rollback" and row["trace_end"] <= close[2]
    ]
    assert len(rollbacks) == int(boundary == "after")
    commands = [
        sql.strip().upper()
        for phase, kind, raw, sql in prefix
        if phase != "bootstrap" and kind == "command" and raw == id(watch.work._raw)
    ]
    assert commands.count("ROLLBACK") == int(boundary == "after")
    if rollbacks:
        assert rollbacks[0]["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
        assert rollbacks[0]["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)


def corrupt_fixture(fixture, pg, manifest, kind, record_property):
    """An explicit malformed native fixture, never a writer-produced state."""
    before = native_snapshot(fixture.case, pg)
    try:
        with pg["admin"].connect() as connection:
            raw = connection.connection.driver_connection
            with connection.begin():
                assert (
                    connection.exec_driver_sql("SELECT current_database()").scalar_one()
                    == fixture.case.engine.url.database
                )
                assert (
                    connection.exec_driver_sql("SHOW session_replication_role").scalar_one()
                    == "origin"
                )
                # Only this fixture transaction bypasses its trigger enforcement.
                # SET LOCAL restores the session mode on commit or rollback.
                connection.exec_driver_sql("SET LOCAL session_replication_role=replica")
                if kind == "corrupt-progress":
                    result = connection.exec_driver_sql(
                        "UPDATE migration_progress SET cursor='{}' WHERE phase=%s",
                        ("ledger_manifest_" + manifest["manifest_id"],),
                    )
                else:
                    result = connection.exec_driver_sql(
                        "UPDATE jobs SET legacy_reserved_microusd=legacy_reserved_microusd+1 "
                        "WHERE id=%s",
                        (fixture.jobs[0]["id"],),
                    )
                assert result.rowcount == 1
            # Observe restoration on the same physical session after COMMIT.
            assert connection.connection.driver_connection is raw and not raw.closed
            assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            assert (
                connection.exec_driver_sql("SHOW session_replication_role").scalar_one() == "origin"
            )
    finally:
        drain(pg)
    after = native_snapshot(fixture.case, pg)
    assert after["catalog"] == before["catalog"]
    assert after["authority"] == before["authority"]
    record_property(
        "malformed_fixture",
        json.dumps(
            {
                "case": kind,
                "trigger_bypass": (
                    "SET LOCAL session_replication_role=replica in fixture-only transaction"
                ),
                "catalog_and_authority_restored": True,
                "writer_produced": False,
            }
        ),
    )


@pytest.mark.parametrize("selected", [0, 1], ids=["old-M0", "completed-M1"])
def test_postgres_fresh_reentry_recovers_original_receipt_after_actual_s2(
    legacy, pg, monkeypatch, record_property, selected
):
    manifests, receipts = completed(legacy, pg, record_property, later=True)
    recovered, watch = fresh_reentry(legacy, pg, manifests[selected], monkeypatch, record_property)
    assert recovered.model_dump(mode="json") == receipts[selected].model_dump(
        mode="json", exclude={"outcome"}
    )
    assert recovered.sequence == selected
    assert recovered.initialized_at == receipts[selected].initialized_at
    assert watch.outcome.commit_acknowledged
    assert_stage(
        legacy,
        pg,
        manifests,
        receipts,
        record_property=record_property,
        observation="after_reentry",
    )


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_postgres_fresh_reentry_proves_absence_at_exact_parent_without_retry(
    legacy, pg, monkeypatch, record_property, operation
):
    target, _, _ = pending(legacy, pg, record_property, operation)
    recovered, watch = fresh_reentry(legacy, pg, target, monkeypatch, record_property)
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
def test_postgres_fresh_reentry_refuses_conflicting_or_incomplete_current_state(
    legacy, pg, monkeypatch, record_property, case, code
):
    manifests, _ = completed(
        legacy, pg, record_property, later=case in {"changed-M0", "changed-M1", "advanced-parent"}
    )
    target = next_manifest(manifests[0])
    if case == "changed-M0":
        target = deepcopy(manifests[0])
        target["accounts"][0]["limit_microusd"] += 1
    elif case == "changed-M1":
        target = deepcopy(manifests[1])
        target["parent_manifest_digest"] = "f" * 64
    elif case == "advanced-parent":
        target["manifest_id"] = identity(1002)
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
        corrupt_fixture(legacy, pg, manifests[0], case, record_property)
    validate_ledger_manifest(target)
    if case in {"partial-account-id", "partial-scope-start"}:
        assert target["parent_manifest_digest"] == digest(manifests[0])
    with pytest.raises(MigrationRefused, match="^" + code + "$"):
        fresh_reentry(legacy, pg, target, monkeypatch, record_property)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_postgres_physical_commit_uncertainty_requires_fresh_reentry(
    legacy, pg, monkeypatch, record_property, operation, boundary
):
    target, manifests, receipts = pending(legacy, pg, record_property, operation)
    before = native_snapshot(legacy.case, pg)
    with (
        observe_command(
            legacy,
            pg,
            monkeypatch,
            record_property,
            label="uncertain_commit",
            commit_fault=boundary,
        ) as watch,
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
    ):
        ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(target))
    watch.assert_single_attempt()
    assert watch.faults == ["commit." + boundary]
    assert watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
    assert not watch.outcome.confirmed_precommit_rollback
    assert [row[0] for row in watch.markers].count("commit.before_native") == 1
    assert_commit_boundary(watch, boundary)
    recovered, _ = fresh_reentry(legacy, pg, target, monkeypatch, record_property, previous=watch)
    if boundary == "before":
        assert recovered is None
        assert native_snapshot(legacy.case, pg) == before
    else:
        assert recovered.manifest_digest == digest(target)
        assert_recovered_stage(legacy, pg, manifests, receipts, target, recovered, record_property)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_postgres_commit_ack_then_delegated_close_failure_never_returns_success(
    legacy, pg, monkeypatch, record_property, operation
):
    target, manifests, receipts = pending(legacy, pg, record_property, operation)
    with (
        observe_command(
            legacy,
            pg,
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
    names = [row[0] for row in watch.markers]
    assert (
        names.index("commit.native_ack")
        < names.index("raw.close.native_ack")
        < names.index("connection.close.return")
    )
    assert_commit_boundary(watch, "after")
    recovered, _ = fresh_reentry(legacy, pg, target, monkeypatch, record_property, previous=watch)
    assert_recovered_stage(legacy, pg, manifests, receipts, target, recovered, record_property)


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_postgres_physical_rollback_failure_reports_uncertainty_but_fresh_state_is_absent(
    legacy, pg, monkeypatch, record_property, operation, boundary
):
    target, _, _ = pending(legacy, pg, record_property, operation)
    before = native_snapshot(legacy.case, pg)
    with (
        observe_command(
            legacy,
            pg,
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
    assert_rollback_boundary(watch, boundary)
    assert native_snapshot(legacy.case, pg) == before
    recovered, _ = fresh_reentry(legacy, pg, target, monkeypatch, record_property, previous=watch)
    assert recovered is None


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_postgres_first_base_exception_identity_survives_later_cleanup_interruption(
    legacy, pg, monkeypatch, record_property, operation
):
    target, _, _ = pending(legacy, pg, record_property, operation)
    before = native_snapshot(legacy.case, pg)
    first = KeyboardInterrupt("first physical progress-write interruption")
    later = SystemExit("later delegated-close interruption")
    with (
        observe_command(
            legacy,
            pg,
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
    assert_rollback_boundary(watch, "after")
    assert native_snapshot(legacy.case, pg) == before
    recovered, _ = fresh_reentry(legacy, pg, target, monkeypatch, record_property, previous=watch)
    assert recovered is None


@pytest.mark.parametrize("predicate", ["true", "false"])
def test_postgres_fresh_reentry_observer_rejects_same_value_and_zero_row_writes(
    legacy, pg, monkeypatch, record_property, predicate
):
    manifests, _ = completed(legacy, pg, record_property)
    expected = (
        "native tuple writes observed"
        if predicate == "true"
        else "native write-capable statement observed"
    )
    with pytest.raises(AssertionError, match=expected):
        fresh_reentry(
            legacy,
            pg,
            manifests[0],
            monkeypatch,
            record_property,
            injected_update="UPDATE api_keys SET name=name WHERE " + predicate,
        )
