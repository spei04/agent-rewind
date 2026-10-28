"""Real period publication/consumers; controlled-clock logic, no live activation."""

import json

import pytest
from ledger_eligibility_fixture import file_hashes, refreshed
from ledger_provisioning_fixture import assert_no_writes, inspect, native_actions
from reservation_period_qe_fixture import build_period_case
from reservation_qe_fixture import (
    assert_released,
    assert_reservation,
    coordinator,
    intent,
    one,
    same,
    snapshot,
)

from agent_rewind.migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_service import initialize_ledger
from agent_rewind.reservation_types import ReservationRefusal


def record_clock(record_property, value):
    record_property(
        "clock_boundary_logic",
        json.dumps(
            {
                "native_sql_invoked_once_per_sample": True,
                "returned_values_substituted": True,
                "native_elapsed_rollover_claim": False,
                "samples": value.samples,
            }
        ),
    )


def assert_saved_triple(value):
    case = value.case
    before = snapshot(case.engine)
    repeated = coordinator(case).reserve(case.principal, case.context, value.fence, value.original)
    assert repeated.kind == "original" and repeated.record.identity == value.original
    assert repeated.record.state == ("reconciled" if value.evidence is not None else "reserved")
    assert repeated.record.identity.organization_account_id != case.account_ids[0]
    assert repeated.record.identity.project_account_id != case.account_ids[1]
    assert repeated.record.identity.job_account_id == case.account_ids[2]
    same(before, snapshot(case.engine))


def test_real_rollover_preserves_original_triple_and_counts_retired_held(
    tmp_path, monkeypatch, record_property
):
    value = build_period_case(tmp_path, monkeypatch, stage="rolled-held")
    case = value.case
    try:
        assert_saved_triple(value)
        before = snapshot(case.engine)
        oversized = intent(case, value.fence, amount=4, number=130300)
        operation = coordinator(case)
        with pytest.raises(ReservationRefusal) as rejected:
            operation.reserve(case.principal, case.context, value.fence, oversized)
        assert rejected.value.reason == "budget_exceeded"
        assert operation.outcome.confirmed_precommit_rollback
        same(before, snapshot(case.engine))
        exact = intent(case, value.fence, amount=3, number=130302)
        result = coordinator(case).reserve(case.principal, case.context, value.fence, exact)
        assert result.kind == "created"
        after = snapshot(case.engine)
        assert_reservation(before, after, exact, case.organization_id)
        assert (
            one(after, "budget_accounts", id=value.original.organization_account_id)[
                "held_microusd"
            ]
            == 7
        )
        assert one(after, "budget_accounts", id=case.account_ids[0])["held_microusd"] == 3
        assert_released(case.engine)
        record_clock(record_property, value)
    finally:
        case.close()


def test_real_rollover_leaves_retired_accounted_outside_new_period_limit(
    tmp_path, monkeypatch, record_property
):
    value = build_period_case(tmp_path, monkeypatch, stage="rolled-accounted")
    case = value.case
    try:
        assert_saved_triple(value)
        before = snapshot(case.engine)
        old = one(before, "budget_accounts", id=value.original.organization_account_id)
        assert old["held_microusd"] == 0 and old["accounted_microusd"] == 7
        exact = intent(case, value.fence, amount=10, number=130304)
        result = coordinator(case).reserve(case.principal, case.context, value.fence, exact)
        assert result.kind == "created"
        after = snapshot(case.engine)
        assert_reservation(before, after, exact, case.organization_id)
        assert one(after, "budget_accounts", id=old["id"]) == old
        assert one(after, "budget_accounts", id=case.account_ids[0])["held_microusd"] == 10
        assert (
            value.evidence.storage.read_verified(value.evidence.descriptor)
            == value.evidence.content
        )
        assert file_hashes(value.evidence.root) == value.evidence.hashes
        assert_released(case.engine)
        record_clock(record_property, value)
    finally:
        case.close()


@pytest.mark.parametrize("stage", ["reserved", "rolled-held", "rolled-accounted"])
def test_retained_p1_consumers_accept_p2_history(tmp_path, monkeypatch, record_property, stage):
    value = build_period_case(tmp_path, monkeypatch, stage=stage)
    case = value.case
    try:
        before = snapshot(case.engine)
        with native_actions(monkeypatch) as actions:
            state = inspect(refreshed(case.provisioning))
        assert_no_writes(actions)
        assert state.manifest_count == len(value.manifests)
        assert state.account_count == (3 if stage == "reserved" else 5)
        same(before, snapshot(case.engine))
        for manifest, original in zip(value.manifests, value.receipts, strict=True):
            engine = case.provisioning.case.operator_engine()
            try:
                with native_actions(monkeypatch) as actions:
                    replay = initialize_ledger(engine, validate_ledger_manifest(manifest))
                assert_no_writes(actions)
                assert replay.model_dump(mode="json") == original.model_dump(mode="json")
                assert engine.pool.checkedout() == 0
            finally:
                engine.dispose()
            same(before, snapshot(case.engine))
        assert runtime_schema_compatibility(case.engine) == CompatibilityResult(
            "incompatible", "migration_only"
        )
        same(before, snapshot(case.engine))
        if value.evidence is not None:
            assert (
                value.evidence.storage.read_verified(value.evidence.descriptor)
                == value.evidence.content
            )
            assert file_hashes(value.evidence.root) == value.evidence.hashes
        assert_released(case.engine)
        record_clock(record_property, value)
    finally:
        case.close()
