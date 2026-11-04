"""Real private successor claim/reserve controls; no dispatch or provider requests."""

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_paid_oracle import (
    assert_reservation_delta,
    claim_intent,
    observe_paid,
    reservation_intent,
)
from operation_failure_service_oracle import complete_failure, service_key
from sqlalchemy import text
from test_failure_persistence_native_oracle import (
    assert_only_claim_changed,
    assert_same_state,
    genuine_failure_case,
    native_clock,
    whole_state,
)

from agent_rewind import reservation_successor
from agent_rewind.failure_evidence import FailureRefusal
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ReservationRefusal

__all__ = ["pg"]


@pytest.fixture(params=[
    "sqlite",
    pytest.param("postgresql", marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(
            not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 paid paths"
        ),
    )),
])
def case(request, tmp_path, monkeypatch, record_property):
    selected_pg = request.getfixturevalue("pg") if request.param == "postgresql" else None
    template = (
        request.getfixturevalue("fresh_sqlite_ar6_template") if selected_pg is None else None
    )
    with genuine_failure_case(
        tmp_path, monkeypatch, record_property, pg=selected_pg, fresh_ar6_template=template
    ) as fixture:
        yield fixture.case


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
@pytest.mark.parametrize("amount", [0, 7])
def test_successor_claim_reserve_and_original_readback_have_exact_native_deltas(
    case, monkeypatch, record_property, key, amount
):
    principal, context = service_key(case, case.engine) if key else (case.principal, case.context)
    before = whole_state(case)
    claim = ReservationCoordinator(case.engine, case.authority)
    first = native_clock(case)
    with observe_paid(case, monkeypatch, record_property, claim):
        fence = claim._claim_successor(principal, context, claim_intent(case))
    last = native_clock(case)
    claimed = whole_state(case)
    assert_only_claim_changed(before, claimed, claim_intent(case), (first, last))
    assert claim.outcome.commit_acknowledged and not claim.outcome.cleanup_failed
    intent = reservation_intent(case, fence, amount=amount)
    reserve = ReservationCoordinator(case.engine, case.authority)
    first = native_clock(case)
    with observe_paid(case, monkeypatch, record_property, reserve):
        created = reserve._reserve_successor(principal, context, fence, intent)
    last = native_clock(case)
    assert created.kind == "created" and created.record.identity == intent
    assert created.record.state == "reserved"
    assert created.record.settled_microusd == created.record.released_microusd == 0
    assert reserve.outcome.commit_acknowledged and not reserve.outcome.cleanup_failed
    reserved = whole_state(case)
    assert_reservation_delta(case, claimed, reserved, intent, (first, last))
    repeated = ReservationCoordinator(case.engine, case.authority)
    with observe_paid(case, monkeypatch, record_property, repeated) as statements:
        original = repeated._reserve_successor(principal, context, fence, intent)
    assert original.kind == "original" and original.record == created.record
    assert not any(sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
                   for sql, _ in statements)
    assert_same_state(reserved, whole_state(case))


@pytest.mark.parametrize("key", [False, True], ids=["principal", "service-key"])
@pytest.mark.parametrize("entry", ["claim", "reserve"])
def test_existing_verified_evidence_denies_new_paid_work_at_unfiltered_job_check(
    case, monkeypatch, record_property, key, entry
):
    original_failure = complete_failure(case, monkeypatch, record_property)
    principal, context = service_key(case, case.engine) if key else (case.principal, case.context)
    before = whole_state(case)
    assert len(before["tables"]["job_failure_evidence"]["rows"]) == 1
    visits = []
    original_absence = reservation_successor._absence

    def absence(connection, scope):
        visits.append((connection, scope.job_id))
        return original_absence(connection, scope)

    monkeypatch.setattr(reservation_successor, "_absence", absence)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    with observe_paid(case, monkeypatch, record_property, coordinator) as statements:
        with pytest.raises(FailureRefusal) as caught:
            if entry == "claim":
                coordinator._claim_successor(principal, context, claim_intent(case))
            else:
                coordinator._reserve_successor(
                    principal, context, original_failure.fence,
                    reservation_intent(case, original_failure.fence),
                )
    assert caught.value.reason == "not_eligible"
    assert len(visits) == 1 and visits[0][1] == case.job_id
    assert visits[0][0].closed
    assert coordinator.outcome.rollback_acknowledged and not coordinator.outcome.commit_attempted
    assert not any(sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
                   for sql, _ in statements)
    assert_same_state(before, whole_state(case))


@pytest.mark.parametrize("entry", ["claim", "reserve"])
@pytest.mark.parametrize("change", ["cancel", "generation", "expiry"])
def test_final_paid_fence_refuses_real_same_body_native_drift_and_rolls_back(
    case, monkeypatch, record_property, entry, change
):
    """The injected writer shares the actual body; this is not a concurrency test."""
    fence = None
    if entry == "reserve":
        claim = ReservationCoordinator(case.engine, case.authority)
        with observe_paid(case, monkeypatch, record_property, claim):
            fence = claim._claim_successor(case.principal, case.context, claim_intent(case))
    before = whole_state(case)
    original_refresh = reservation_successor._refresh_producer_authority
    visits = []

    def drift(connection, scope, original):
        result = original_refresh(connection, scope, original)
        assert scope.job_id == case.job_id
        sql = {
            "cancel": "UPDATE jobs SET cancel=:value WHERE id=:job",
            "generation": "UPDATE jobs SET lease_generation=lease_generation+1 WHERE id=:job",
            "expiry": "UPDATE jobs SET lease_until=0 WHERE id=:job",
        }[change]
        connection.execute(text(sql), {"value": True, "job": case.job_id})
        visits.append(True)
        return result

    monkeypatch.setattr(reservation_successor, "_refresh_producer_authority", drift)
    coordinator = ReservationCoordinator(case.engine, case.authority)
    with observe_paid(case, monkeypatch, record_property, coordinator):
        with pytest.raises(ReservationRefusal) as caught:
            if entry == "claim":
                coordinator._claim_successor(case.principal, case.context, claim_intent(case))
            else:
                assert fence is not None
                coordinator._reserve_successor(
                    case.principal, case.context, fence, reservation_intent(case, fence)
                )
    assert visits == [True] and caught.value.reason == "job_not_live"
    assert coordinator.outcome.rollback_acknowledged and not coordinator.outcome.commit_attempted
    assert_same_state(before, whole_state(case))
