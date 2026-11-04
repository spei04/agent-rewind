"""Successor response semantics, released-snapshot drift, and effect rollback."""

import json
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from ledger_restore_authority import typed
from operation_failure_paid_oracle import (
    assert_reservation_delta,
    claim_intent,
    reservation_intent,
)
from operation_failure_service_oracle import (
    add_roots,
    assert_cancel_delta,
    assert_service_released,
    canonical,
    expected_get,
    observe_service,
    one,
    publish_result,
    service_case,
)
from sqlalchemy import event, text
from test_failure_persistence_native_oracle import (
    assert_same_state,
    native_clock,
    whole_state,
)

from agent_rewind import operation_failure_service
from agent_rewind.errors import Fault
from agent_rewind.request_authority import ActionForbidden
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["pg"]


@pytest.fixture(params=[
    "sqlite",
    pytest.param("postgresql", marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(
            not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 service races"
        ),
    )),
])
def dialect(request):
    return request.param


def read(fixture, operation_id=None):
    return fixture.service._read_successor(
        fixture.principal, fixture.context, operation_id or fixture.operation_id
    )


def cancel(fixture, operation_id=None):
    return fixture.service._cancel_successor(
        fixture.principal, fixture.context, operation_id or fixture.operation_id
    )


def dependency(call):
    with pytest.raises(Fault) as caught:
        call()
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    return caught.value


def transaction_observer(monkeypatch):
    facts = []
    original = operation_failure_service.admission_transaction

    @contextmanager
    def transaction(engine, outcome, **kwargs):
        try:
            with original(engine, outcome, **kwargs) as connection:
                yield connection
        finally:
            facts.append(asdict(outcome))

    monkeypatch.setattr(operation_failure_service, "admission_transaction", transaction)
    return facts


@pytest.mark.parametrize("state", ["evaluator_false", "already_cancelled"])
def test_supported_non_failure_outcomes_keep_null_error(
    request, tmp_path, monkeypatch, record_property, dialect, state
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect,
        cancel=state == "already_cancelled",
    ) as fixture:
        result_id = None
        if state == "evaluator_false":
            # These are the Engine's established evaluator-result fields.
            # The consumer test does not run an evaluator or invent a terminal error.
            result_id = add_roots(
                fixture, 1, update={"status": "complete", "success": False}
            )[0]
            publish_result(fixture, result_id)
        else:
            before_cancel = whole_state(fixture.case)
            first = time.time()
            with observe_service(fixture, monkeypatch, record_property) as cancelled:
                assert cancel(fixture) == {
                    "operation_id": fixture.operation_id,
                    "cancel_requested": True,
                    "status": "cancelled",
                }
            last = time.time()
            assert_service_released(cancelled)
            assert_cancel_delta(
                fixture, before_cancel, whole_state(fixture.case), (first, last)
            )
        before = whole_state(fixture.case)
        assert before["tables"]["job_failure_evidence"]["rows"] == []
        with observe_service(fixture, monkeypatch, record_property) as observed:
            response = read(fixture)
        assert response == expected_get(fixture, before, result_run_id=result_id)
        assert response["error"] is None and len(canonical(response)) <= 2048
        assert_service_released(observed)
        assert_same_state(before, whole_state(fixture.case))


@pytest.mark.parametrize("entry", ["get", "cancel"])
@pytest.mark.parametrize("visible", [False, True], ids=["absent-target", "visible-target"])
@pytest.mark.parametrize("failed_without_evidence", [False, True])
def test_current_viewer_visibility_precedes_action_and_unsupported_failure_disclosure(
    request, tmp_path, monkeypatch, record_property, dialect,
    entry, visible, failed_without_evidence,
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect,
        key=True, cancel=entry == "cancel",
    ) as fixture:
        with fixture.engine.begin() as connection:
            changed = connection.execute(
                text("UPDATE project_memberships SET role='viewer' "
                     "WHERE project_id=:project AND principal_id=:principal"),
                {"project": fixture.context.project_id,
                 "principal": fixture.principal.principal_id},
            )
            assert changed.rowcount == 1
            if failed_without_evidence:
                changed = connection.execute(
                    text("UPDATE jobs SET status='failed' WHERE id=:job"),
                    {"job": fixture.case.job_id},
                )
                assert changed.rowcount == 1
        before = whole_state(fixture.case)
        authority = fixture.service.authority.check
        checks, evidence_gates = [], []
        error_gate = operation_failure_service.successor_error

        def checked(connection, principal, context, action, **kwargs):
            checks.append(action)
            return authority(connection, principal, context, action, **kwargs)

        def observed_error(*args, **kwargs):
            evidence_gates.append(True)
            return error_gate(*args, **kwargs)

        monkeypatch.setattr(fixture.service.authority, "check", checked)
        monkeypatch.setattr(operation_failure_service, "successor_error", observed_error)
        target = fixture.operation_id if visible else "f" * 32
        with observe_service(fixture, monkeypatch, record_property) as observed:
            def invoke():
                return read(fixture, target) if entry == "get" else cancel(fixture, target)

            if not visible:
                with pytest.raises(ResourceNotFound):
                    invoke()
            elif entry == "cancel":
                with pytest.raises(ActionForbidden):
                    invoke()
            elif failed_without_evidence:
                dependency(invoke)
            else:
                assert invoke() == expected_get(fixture, before)
        assert checks and checks[0] == "read"
        if visible and entry == "cancel":
            assert checks[-1] == "cancel" and evidence_gates == []
        else:
            assert "cancel" not in checks
            assert len(evidence_gates) == int(visible and entry == "get")
        assert_service_released(observed)
        assert not any(kind == "commit" for _, kind, _, _ in observed.controls)
        assert_same_state(before, whole_state(fixture.case))


def marker_values(fixture, before):
    job = one(before, "jobs", id=fixture.case.job_id)
    return {
        "schema_version": 1, "kind": "historical_marker",
        "project_id": fixture.context.project_id, "job_resource_kind": "job",
        "job_id": fixture.case.job_id, "operation_id": fixture.operation_id,
        "lease_generation": job["lease_generation"], "job_status": job["status"],
        "cause": None, "phase": None, "origin_kind": "migration_marker",
        "correlation_id": "e" * 32, "association_sha256": "a" * 64,
        "source_sha256": "b" * 64, "created_at_micros": 0,
    }


@pytest.mark.parametrize("change", [
    "generation", "evidence", "any_call", "run_scope", "configuration",
    "configuration_ref", "cohort",
])
def test_final_get_rejects_actual_separate_transaction_snapshot_drift(
    request, tmp_path, monkeypatch, record_property, dialect, change
):
    with service_case(request, tmp_path, monkeypatch, record_property, dialect) as fixture:
        first_root = add_roots(fixture, 1)[0]
        fence = None
        if change == "evidence":
            # A dormant historical association is supported without evidence.
            # The later valid marker INSERT needs no disabled constraint/trigger.
            with fixture.engine.begin() as connection:
                assert connection.execute(
                    text("UPDATE operations SET failure_correlation_id=NULL WHERE id=:id"),
                    {"id": fixture.operation_id},
                ).rowcount == 1
        elif change == "any_call":
            owner = ReservationCoordinator(fixture.case.engine, fixture.case.authority)
            fence = owner._claim_successor(
                fixture.case.principal, fixture.case.context, claim_intent(fixture.case)
            )
            assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        before = whole_state(fixture.case)
        expected = deepcopy(before)
        original_load = fixture.service._load_result
        original_verify = operation_failure_service.verify_successor_snapshot
        changes, gates, paid = [], [], []
        observed_ref = []

        def mutate():
            observed = observed_ref[0]
            assert len(changes) == 0
            assert all(connection.closed for connection in observed.connections)
            assert observed.works[0]._connection is None
            if change == "any_call":
                assert fence is not None
                intent = reservation_intent(fixture.case, fence, amount=0, number=982001)
                writer = ReservationCoordinator(fixture.case.engine, fixture.case.authority)
                first = native_clock(fixture.case)
                decision = writer._reserve_successor(
                    fixture.case.principal, fixture.case.context, fence, intent
                )
                last = native_clock(fixture.case)
                assert decision.kind == "created"
                assert writer.outcome.commit_acknowledged and not writer.outcome.cleanup_failed
                paid.append((intent, first, last, asdict(writer.outcome)))
            elif change == "cohort":
                identifier = add_roots(fixture, 1, start=10001)[0]
                body = {
                    "job_id": fixture.case.job_id, "parent_id": None, "source": "preserved"
                }
                expected["tables"]["records"]["rows"].append({
                    "id": identifier, "kind": "run", "created": 1700000000.125,
                    "data": body if fixture.pg is not None else json.dumps(body),
                })
                expected["tables"]["resource_scopes"]["rows"].append({
                    "resource_kind": "run", "resource_id": identifier,
                    "project_id": fixture.context.project_id,
                })
            else:
                with fixture.engine.begin() as connection:
                    if change == "generation":
                        sql = "UPDATE jobs SET lease_generation=lease_generation+1 WHERE id=:id"
                        values = {"id": fixture.case.job_id}
                        one(expected, "jobs", id=fixture.case.job_id)["lease_generation"] += 1
                    elif change == "evidence":
                        marker = marker_values(fixture, before)
                        sql = (
                            "INSERT INTO job_failure_evidence "
                            "(schema_version,kind,project_id,job_resource_kind,job_id,operation_id,"
                            "lease_generation,job_status,cause,phase,origin_kind,correlation_id,"
                            "association_sha256,source_sha256,created_at_micros) VALUES "
                            "(:schema_version,:kind,:project_id,:job_resource_kind,:job_id,"
                            ":operation_id,:lease_generation,:job_status,:cause,:phase,"
                            ":origin_kind,"
                            ":correlation_id,:association_sha256,:source_sha256,:created_at_micros)"
                        )
                        values = marker
                        expected["tables"]["job_failure_evidence"]["rows"].append(marker)
                    elif change == "run_scope":
                        sql = (
                            "DELETE FROM resource_scopes WHERE resource_kind='run' "
                            "AND resource_id=:id AND project_id=:project"
                        )
                        values = {"id": first_root, "project": fixture.context.project_id}
                        rows = expected["tables"]["resource_scopes"]["rows"]
                        original = one(
                            expected, "resource_scopes", resource_kind="run",
                            resource_id=first_root, project_id=fixture.context.project_id,
                        )
                        rows.remove(original)
                    elif change == "configuration":
                        sql = (
                            "UPDATE jobs SET execution_config_ref=:value,"
                            "execution_config_digest=:value WHERE id=:id"
                        )
                        values = {"id": fixture.case.job_id, "value": "e" * 64}
                        one(expected, "jobs", id=fixture.case.job_id).update(
                            execution_config_ref="e" * 64, execution_config_digest="e" * 64
                        )
                    else:
                        assert change == "configuration_ref"
                        sql = (
                            "DELETE FROM artifact_refs WHERE owner_kind='job' AND "
                            "owner_id=:id AND role='admission_config'"
                        )
                        values = {"id": fixture.case.job_id}
                        original = one(expected, "artifact_refs", owner_kind="job",
                                       owner_id=fixture.case.job_id, role="admission_config")
                        expected["tables"]["artifact_refs"]["rows"].remove(original)
                    assert connection.execute(text(sql), values).rowcount == 1
            for table in expected["tables"].values():
                table["rows"].sort(key=lambda row: repr(typed(row)))
            changes.append(change)

        def load(*args, **kwargs):
            value = original_load(*args, **kwargs)
            mutate()
            return value

        def verify(*args, **kwargs):
            gates.append(True)
            return original_verify(*args, **kwargs)

        monkeypatch.setattr(fixture.service, "_load_result", load)
        monkeypatch.setattr(operation_failure_service, "verify_successor_snapshot", verify)
        with observe_service(fixture, monkeypatch, record_property) as observed:
            observed_ref.append(observed)
            dependency(lambda: read(fixture))
        assert changes == [change] and gates == [True]
        assert_service_released(observed)
        after = whole_state(fixture.case)
        if paid:
            intent, first, last, facts = paid[0]
            assert_reservation_delta(fixture.case, before, after, intent, (first, last))
        else:
            facts = None
            assert_same_state(expected, after)
        assert not any(kind == "commit" and work is observed.works[0]
                       for work, kind, _, _ in observed.controls)
        record_property("f4_successor_snapshot_drift", json.dumps({
            "change": change, "final_match_gate_visits": len(gates),
            "writer_transaction_committed": True,
            "paid_writer_facts": facts,
        }, sort_keys=True))


@pytest.mark.parametrize("stage", ["UPDATE jobs", "INSERT INTO audit"])
def test_successor_cancel_native_effect_failure_rolls_back_job_and_audit_together(
    request, tmp_path, monkeypatch, record_property, dialect, stage
):
    with service_case(
        request, tmp_path, monkeypatch, record_property, dialect, cancel=True
    ) as fixture:
        before = whole_state(fixture.case)
        facts = transaction_observer(monkeypatch)
        writes = []
        canary = "synthetic private F4 effect fault"

        def fail_after(connection, cursor, sql, _parameters, _context, _many):
            if connection.engine is fixture.reader_engine and sql.lstrip().startswith(stage):
                writes.append({"stage": stage, "rowcount": cursor.rowcount})
                assert len(writes) == 1 and cursor.rowcount == 1
                raise RuntimeError(canary)

        event.listen(fixture.reader_engine, "after_cursor_execute", fail_after)
        try:
            with observe_service(fixture, monkeypatch, record_property) as observed:
                error = dependency(lambda: cancel(fixture))
        finally:
            event.remove(fixture.reader_engine, "after_cursor_execute", fail_after)
        assert canary not in str(error) and len(writes) == len(facts) == 1
        assert facts[0]["begun"] and facts[0]["rollback_acknowledged"]
        assert not facts[0]["commit_attempted"] and not facts[0]["cleanup_failed"]
        assert_service_released(observed)
        assert_same_state(before, whole_state(fixture.case))
        record_property("f4_successor_cancel_rollback", json.dumps({
            "native_writes_before_failure": writes,
            "transaction_facts": facts[0],
            "exact_original_restored": True,
        }, sort_keys=True))
