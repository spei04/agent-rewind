"""Focused author regressions for the private coordinator corrections."""

from copy import deepcopy
from dataclasses import replace

import pytest
from ledger_eligibility_fixture import rows
from test_reservation_service import _claimed, _intent, reservation_case

from agent_rewind.admission_transaction import TransactionOutcome, admission_transaction
from agent_rewind.operation_work import OperationWork
from agent_rewind.reservation_checks import utc_microseconds
from agent_rewind.reservation_rows import ReservationRows
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import (
    MAX_MONEY,
    CallConflict,
    CallNotRequested,
    JobFence,
    ReservationRefusal,
    ReservationScope,
)

__all__ = ["reservation_case"]


def _projection(case):
    scope = ReservationScope(case.principal, case.context, case.job_id)
    with admission_transaction(
        case.engine, TransactionOutcome(), work=OperationWork()
    ) as connection:
        # Capture exact real guarded rows/provenance. The following synthetic
        # arithmetic vectors test retained projection semantics, not native state.
        result = ReservationRows.capture(connection, scope, connection.info["operation_work"])
    return replace(result, work=OperationWork())


@pytest.mark.parametrize("route", ["reserve", "inspect"], ids=["fence-job", "inspection-project"])
def test_mismatched_identity_refuses_before_checkout(reservation_case, route):
    from sqlalchemy import event

    case = reservation_case
    intent = _intent(case)
    observed = []
    event.listen(case.engine, "checkout", lambda *_: observed.append(True))
    owner = ReservationCoordinator(case.engine, case.authority)
    with pytest.raises(ReservationRefusal) as caught:
        if route == "reserve":
            owner.reserve(case.principal, case.context, JobFence("f" * 32, "a" * 32, 1), intent)
        else:
            owner.inspect_original(
                case.principal, case.context, case.job_id, replace(intent, project_id="f" * 32)
            )
    assert caught.value.reason == "invalid_intent"
    assert not owner.outcome.begun and observed == []


def test_historical_mismatch_is_classified_before_record_construction(
    reservation_case, monkeypatch
):
    from agent_rewind import reservation_rows

    case = reservation_case
    fence = _claimed(case)
    intent = _intent(case)
    ReservationCoordinator(case.engine, case.authority).reserve(
        case.principal, case.context, fence, intent
    )
    before = case.snapshot()
    original = reservation_rows.read_financial_projection

    def supplied_historical(connection, revision, work):
        projection = original(connection, revision, work)
        # Inject one native-valid historical scalar after the genuine bounded
        # read. No SQL/catalog data is changed, and this is not restore evidence.
        for call in projection.rows["call"]:
            if call["id"] == intent.call_id:
                call["price_version"] = "historical-control-\x01"
        return projection

    monkeypatch.setattr(reservation_rows, "read_financial_projection", supplied_historical)
    inspection = ReservationCoordinator(case.engine, case.authority).inspect_original(
        case.principal, case.context, case.job_id, intent
    )
    assert isinstance(inspection.call, CallConflict)
    absent_intent = ReservationCoordinator(case.engine, case.authority).inspect_original(
        case.principal, case.context, case.job_id
    )
    assert isinstance(absent_intent.call, CallNotRequested)
    owner = ReservationCoordinator(case.engine, case.authority)
    with pytest.raises(ReservationRefusal) as caught:
        owner.reserve(case.principal, case.context, fence, intent)
    assert caught.value.reason == "identity_conflict"
    assert owner.outcome.confirmed_precommit_rollback and case.snapshot() == before


@pytest.mark.parametrize(
    "reduction",
    ["release", "none", "settle"],
    ids=["released-lifetime-gross", "held-overflow", "accounted-overflow"],
)
def test_account_reduces_each_cohort_before_summing_native_balances(reservation_case, reduction):
    case = reservation_case
    retained = _projection(case)
    data = deepcopy(retained.data)
    target = next(row for row in data["job"] if row["id"] == case.job_id)
    original_job = deepcopy(target)
    base_account = next(row for row in data["account"] if row["id"] == case.account_ids[2])
    config = data["object"][0]
    for account in data["account"]:
        if account["scope"] in {"organization", "project"}:
            account["limit_microusd"] = MAX_MONEY
    for number in (1, 2):
        job_id, call_id, account_id = (
            f"{value:032x}" for value in (10000 + number, 20000 + number, 30000 + number)
        )
        job = {
            **original_job,
            "id": job_id,
            "payload": "{}",
            "payload_version": 1,
            "execution_config_ref": None,
            "execution_config_digest": None,
            "budget": MAX_MONEY,
            "reserved": MAX_MONEY,
            "lease_generation": 1,
            "legacy_reserved_microusd": 0,
        }
        data["job"].append(job)
        data["scope"].extend(
            [
                {"resource_kind": "job", "resource_id": job_id, "project_id": case.project_id},
                {
                    "resource_kind": "provider_call",
                    "resource_id": call_id,
                    "project_id": case.project_id,
                },
            ]
        )
        data["account"].append(
            {
                **base_account,
                "id": account_id,
                "scope_id": job_id,
                "job_id": job_id,
                "limit_microusd": MAX_MONEY,
                "held_microusd": MAX_MONEY if reduction == "none" else 0,
                "accounted_microusd": MAX_MONEY if reduction == "settle" else 0,
            }
        )
        call = {
            "id": call_id,
            "project_id": case.project_id,
            "job_id": job_id,
            "logical_call_id": call_id,
            "purpose": "continuation",
            "request_digest": "d" * 64,
            "price_version": case.price_version,
            "state": "reconciled",
            "reserved_microusd": MAX_MONEY,
            "usage_estimate_microusd": None,
            "provider_request_id": None,
            "created_at": "2026-01-01T00:00:00.000000Z",
            "organization_id": case.organization_id,
            "job_resource_kind": "job",
            "lease_generation": 1,
            "organization_account_id": case.account_ids[0],
            "project_account_id": case.account_ids[1],
            "job_account_id": account_id,
        }
        data["call"].append(call)
        data["ref"].append(
            {
                "project_id": case.project_id,
                "owner_kind": "provider_call",
                "owner_id": call_id,
                "artifact_id": config["id"],
                "role": "budget_evidence",
            }
        )
        for identity in (case.account_ids[0], case.account_ids[1], account_id):
            for kind in ("reserve", reduction) if reduction != "none" else ("reserve",):
                data["entry"].append(
                    {
                        "call_id": call_id,
                        "account_id": identity,
                        "entry_kind": kind,
                        "amount_microusd": MAX_MONEY,
                        "evidence_ref": None if kind == "reserve" else config["id"],
                        "created_at": call["created_at"],
                        "project_id": case.project_id,
                        "evidence_owner_kind": "provider_call",
                        "evidence_role": "budget_evidence",
                    }
                )
    assert sum(call["reserved_microusd"] for call in data["call"]) == 2 * MAX_MONEY
    assert all(job["reserved"] <= MAX_MONEY for job in data["job"])
    value = replace(retained, projection=replace(retained.projection, rows=data))
    now = utc_microseconds("2026-06-01T00:00:00.000000Z")
    if reduction == "release":
        value.reconcile(now)
        assert target["reserved"] == 0
    else:
        with pytest.raises(ReservationRefusal) as caught:
            value.reconcile(now)
        assert caught.value.reason == "ledger_state_invalid"
    assert rows(case.snapshot(), "provider_calls") == []


def test_nonopening_target_cannot_invent_legacy_gross(reservation_case):
    from agent_rewind.migrations.schema import checksum

    case = reservation_case
    retained = _projection(case)
    opening = retained.history.opening
    assert opening is not None
    later_opening = opening.model_copy(
        update={
            "jobs": (),
            "job_count": 0,
            "jobs_digest": checksum([]),
            "project_totals": (),
            "organization_opening_microusd": 0,
        }
    )
    data = deepcopy(retained.data)
    target = next(row for row in data["job"] if row["id"] == case.job_id)
    target.update(legacy_reserved_microusd=1, reserved=1)
    value = replace(
        retained,
        history=replace(retained.history, opening=later_opening),
        projection=replace(retained.projection, rows=data),
    )
    with pytest.raises(ReservationRefusal) as caught:
        value.reconcile(utc_microseconds("2026-06-01T00:00:00.000000Z"))
    assert caught.value.reason == "ledger_state_invalid"
    assert (
        next(row for row in rows(case.snapshot(), "jobs") if row["id"] == case.job_id)["reserved"]
        == 0
    )
