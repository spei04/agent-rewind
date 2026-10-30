"""Independent P2 effects and failure oracles through the actual one-use owner."""

from dataclasses import replace

import pytest
from reservation_fixture import build_reservation_case
from reservation_qe_fixture import (
    assert_claim,
    assert_released,
    assert_reservation,
    claim,
    coordinator,
    fail_after_write,
    identity,
    intent,
    same,
    snapshot,
)
from sqlalchemy import event, text
from sqlalchemy.engine import Connection

from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.request_authority import ActionForbidden
from agent_rewind.request_identity import IdentityInvalid
from agent_rewind.reservation_types import ClaimIntent, ReservationRefusal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.sqlite_ownership import owned_begin


@pytest.fixture
def case(tmp_path, monkeypatch):
    value = build_reservation_case(tmp_path, monkeypatch)
    yield value
    value.close()


def reserve(case, fence, value, *, owner=None):
    operation = coordinator(case) if owner is None else owner
    return operation.reserve(case.principal, case.context, fence, value)


def test_claim_and_reservation_have_only_the_contractual_state_deltas(case):
    queued = snapshot(case.engine)
    fence = claim(case)
    running = snapshot(case.engine)
    assert_claim(queued, running, fence)
    value = intent(case, fence)
    operation = coordinator(case)
    decision = reserve(case, fence, value, owner=operation)
    assert decision.kind == "created" and decision.record.identity == value
    assert decision.record.state == "reserved"
    assert decision.record.settled_microusd == decision.record.released_microusd == 0
    assert operation.outcome.commit_acknowledged and not operation.outcome.cleanup_failed
    assert_reservation(running, snapshot(case.engine), value, case.organization_id)
    assert_released(case.engine)


def test_claim_does_not_reclaim_or_advance_an_already_running_job(case):
    fence = claim(case)
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.claim_generation(
            case.principal,
            case.context,
            ClaimIntent(case.job_id, identity(90002), fence.generation, 60),
        )
    assert caught.value.reason == "job_not_live"
    assert operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_successful_owner_is_consumed_without_a_second_transaction(case):
    operation = coordinator(case)
    first = ClaimIntent(case.job_id, identity(90001), 0, 60)
    operation.claim_generation(case.principal, case.context, first)
    outcome = operation.outcome
    before = snapshot(case.engine)
    with pytest.raises(ReservationRefusal) as caught:
        operation.claim_generation(case.principal, case.context, first)
    assert caught.value.reason == "invocation_reused"
    assert operation.outcome == outcome
    same(before, snapshot(case.engine))


def test_exact_repeat_retains_original_identity_after_cancel_generation_and_lease_change(case):
    fence = claim(case)
    value = intent(case, fence)
    original = reserve(case, fence, value)
    with owned_begin(case.engine) as connection:
        connection.execute(
            text(
                "UPDATE jobs SET cancel=true,lease_generation=lease_generation+1,"
                "lease_until=1 WHERE id=:id"
            ),
            {"id": case.job_id},
        )
    before = snapshot(case.engine)
    repeated = reserve(case, fence, value)
    assert repeated.kind == "original" and repeated.record == original.record
    seen = coordinator(case).inspect_original(case.principal, case.context, case.job_id, value)
    assert seen.job.generation == fence.generation + 1
    assert seen.call.kind == "matching" and seen.call.record == original.record
    same(before, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("call_id", identity(92000)),
        ("logical_call_id", identity(92001)),
        ("request_digest", "c" * 64),
        ("purpose", "discovery"),
        ("price_version", "different-price"),
        ("reserved_microusd", 8),
        ("organization_account_id", identity(92002)),
        ("project_account_id", identity(92003)),
        ("job_account_id", identity(92004)),
    ],
    ids=["uuid", "logical", "request", "purpose", "price", "amount", "org", "project", "job"],
)
def test_immutable_repeat_conflicts_do_not_charge_or_reselect_accounts(case, field, changed):
    fence = claim(case)
    value = intent(case, fence)
    reserve(case, fence, value)
    before = snapshot(case.engine)
    conflict = replace(value, **{field: changed})
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        reserve(case, fence, conflict, owner=operation)
    assert caught.value.reason == "identity_conflict"
    assert caught.value.code == "idempotency_conflict"
    assert operation.outcome.confirmed_precommit_rollback
    seen = coordinator(case).inspect_original(case.principal, case.context, case.job_id, conflict)
    assert seen.call.kind == "conflict"
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_inspection_distinguishes_not_requested_absent_and_matching_without_mutation(case):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    operation = coordinator(case)
    seen = operation.inspect_original(case.principal, case.context, case.job_id)
    assert seen.job.owner_uuid == fence.owner_uuid and seen.job.generation == fence.generation
    assert seen.call.kind == "not_requested"
    seen = coordinator(case).inspect_original(case.principal, case.context, case.job_id, value)
    assert seen.call.kind == "absent"
    same(before, snapshot(case.engine))
    reserve(case, fence, value)
    after = snapshot(case.engine)
    seen = coordinator(case).inspect_original(case.principal, case.context, case.job_id, value)
    assert seen.call.kind == "matching" and seen.call.record.identity == value
    same(after, snapshot(case.engine))


@pytest.mark.parametrize("wrong", ["owner", "generation", "intent_generation", "job"], ids=str)
def test_new_reservation_requires_the_retained_fence_not_the_database_owner(case, wrong):
    fence = claim(case)
    value = intent(case, fence)
    if wrong == "owner":
        fence = replace(fence, owner_uuid=identity(94000))
    elif wrong == "generation":
        fence = replace(fence, generation=fence.generation + 1)
        value = replace(value, lease_generation=fence.generation)
    elif wrong == "intent_generation":
        value = replace(value, lease_generation=fence.generation + 1)
    else:
        fence = replace(fence, job_id=identity(94001))
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        reserve(case, fence, value, owner=operation)
    assert caught.value.reason == (
        "job_not_live" if wrong in {"owner", "generation"} else "invalid_intent"
    )
    assert not operation.outcome.commit_attempted
    same(before, snapshot(case.engine))


@pytest.mark.parametrize(
    ("table", "occurrence"),
    [
        ("provider_calls", 1),
        ("resource_scopes", 1),
        *[("budget_entries", i) for i in (1, 2, 3)],
        *[("budget_accounts", i) for i in (1, 2, 3)],
        ("jobs", 1),
    ],
    ids=[
        "call",
        "scope",
        "entry1",
        "entry2",
        "entry3",
        "balance1",
        "balance2",
        "balance3",
        "gross",
    ],
)
def test_every_returned_publication_write_rolls_back_as_one_unit(case, table, occurrence):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    operation = coordinator(case)
    with (
        fail_after_write(case.engine, table, occurrence) as observed,
        pytest.raises(AdmissionError) as caught,
    ):
        reserve(case, fence, value, owner=operation)
    assert len(observed) == occurrence
    assert caught.value.code == "dependency_unavailable"
    assert operation.outcome.confirmed_precommit_rollback
    assert not operation.outcome.commit_attempted and not operation.outcome.cleanup_failed
    same(before, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize("persisted", [False, True], ids=["before_commit", "after_commit"])
def test_lost_ack_is_uncertain_even_when_a_later_read_finds_the_original_call(
    case, monkeypatch, persisted
):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    operation = coordinator(case)
    original = Connection.commit
    attempted = []

    def lose_ack(connection):
        if connection.engine is case.engine:
            attempted.append(connection)
            if persisted:
                original(connection)
            raise RuntimeError("synthetic P2 lost commit acknowledgment")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", lose_ack)
        with pytest.raises(AdmissionError) as caught:
            reserve(case, fence, value, owner=operation)
    assert len(attempted) == 1 and caught.value.code == "outcome_uncertain"
    assert operation.outcome.commit_attempted and not operation.outcome.commit_acknowledged
    assert not operation.outcome.confirmed_precommit_rollback
    after = snapshot(case.engine)
    if persisted:
        assert_reservation(before, after, value, case.organization_id)
    else:
        same(before, after)
    seen = coordinator(case).inspect_original(case.principal, case.context, case.job_id, value)
    assert seen.call.kind == ("matching" if persisted else "absent")
    same(after, snapshot(case.engine))
    assert_released(case.engine)


def test_acknowledged_commit_with_cleanup_fault_retains_effect_and_withholds_result(
    case, monkeypatch
):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    operation = coordinator(case)
    original = Connection.close
    failed = []

    def fail_close(connection):
        if connection.engine is case.engine and not failed:
            failed.append(connection)
            raise RuntimeError("synthetic P2 cleanup failure")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", fail_close)
        with pytest.raises(AdmissionError) as caught:
            reserve(case, fence, value, owner=operation)
    assert len(failed) == 1 and caught.value.code == "outcome_uncertain"
    assert operation.outcome.commit_acknowledged and operation.outcome.cleanup_failed
    assert not operation.outcome.confirmed_precommit_rollback
    assert_reservation(before, snapshot(case.engine), value, case.organization_id)
    assert_released(case.engine)


@pytest.mark.parametrize("kind", ["branch", "unknown"], ids=str)
def test_named_claim_refuses_unsupported_job_kinds_without_queue_fallback(case, kind):
    with owned_begin(case.engine) as connection:
        connection.execute(
            text("UPDATE jobs SET kind=:kind WHERE id=:id"), {"kind": kind, "id": case.job_id}
        )
    before = snapshot(case.engine)
    operation = coordinator(case)
    # Unknown kinds are invisible through the existing lineage authority;
    # a recognized branch reaches the narrower internal run-only policy.
    refused = ResourceNotFound if kind == "unknown" else ReservationRefusal
    with pytest.raises(refused) as caught:
        operation.claim_generation(
            case.principal, case.context, ClaimIntent(case.job_id, identity(90001), 0, 60)
        )
    if kind == "branch":
        assert caught.value.reason == "unsupported_job"
    assert operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert not operation.outcome.commit_attempted


def test_unrecognized_schema_refuses_before_any_claim_effect(case):
    with owned_begin(case.engine) as connection:
        connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN unexpected_p2_column INTEGER")
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.claim_generation(
            case.principal, case.context, ClaimIntent(case.job_id, identity(90001), 0, 60)
        )
    assert caught.value.reason == "schema_or_provenance_invalid"
    assert caught.value.code == "schema_incompatible"
    same(before, snapshot(case.engine))
    assert not operation.outcome.commit_attempted


@pytest.mark.parametrize("error_type", [IdentityInvalid, ResourceNotFound, ActionForbidden])
def test_authority_denial_keeps_the_original_exception_and_all_state(case, monkeypatch, error_type):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    denial = error_type()
    calls = []

    def deny(*args, **kwargs):
        calls.append((args, kwargs))
        raise denial

    operation = coordinator(case)
    with monkeypatch.context() as patch:
        patch.setattr(case.authority, "check", deny)
        with pytest.raises(error_type) as caught:
            reserve(case, fence, value, owner=operation)
    assert calls and caught.value is denial
    assert not operation.outcome.commit_attempted
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_original_interruption_after_a_real_write_is_not_translated_or_retried(case):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    interruption = KeyboardInterrupt("synthetic P2 interruption")
    returned = []

    def interrupt(connection, cursor, statement, parameters, context, many):
        del connection, cursor, parameters, context, many
        if statement.lstrip().upper().startswith("INSERT INTO PROVIDER_CALLS"):
            returned.append(statement)
            raise interruption

    operation = coordinator(case)
    event.listen(case.engine, "after_cursor_execute", interrupt)
    try:
        with pytest.raises(KeyboardInterrupt) as caught:
            reserve(case, fence, value, owner=operation)
    finally:
        event.remove(case.engine, "after_cursor_execute", interrupt)
    assert caught.value is interruption and len(returned) == 1
    # SQLAlchemy treats a cursor-event BaseException as a disconnect. A later
    # empty read proves durable absence, never an acknowledgment that was lost.
    assert operation.outcome.begun and not operation.outcome.commit_acknowledged
    assert operation.outcome.rollback_attempted and not operation.outcome.rollback_acknowledged
    assert operation.outcome.cleanup_failed and not operation.outcome.confirmed_precommit_rollback
    assert not operation.outcome.commit_attempted
    same(before, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize("family", ["organization", "project"], ids=str)
@pytest.mark.parametrize("offset", [-1000, 0], ids=["last_sqlite_tick", "exact_expiry"])
def test_final_fence_rechecks_shorter_selected_window_while_job_lease_is_live(
    tmp_path, monkeypatch, family, offset
):
    from datetime import UTC, datetime

    import reservation_fixture as shared
    from ledger_eligibility_fixture import refreshed
    from ledger_provisioning_fixture import digest, invoke
    from reservation_qe_fixture import one

    from agent_rewind import reservation

    base = int(datetime(2030, 1, 1, tzinfo=UTC).timestamp()) * 1_000_000
    expiry = base + 20_000_000
    original_manifest = shared.initial_manifest

    def bounded_window(fixture):
        manifest = original_manifest(fixture)
        for account in manifest["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["period_end"] = "2029-01-01T00:00:00.000000Z"
        return manifest

    with monkeypatch.context() as setup:
        setup.setattr(shared, "initial_manifest", bounded_window)
        case = shared.build_reservation_case(tmp_path, setup)
    try:
        # Opening organization/project periods must match. A real subsequent
        # provision supplies the asymmetric selected windows under test.
        fixture = refreshed(case.provisioning)
        initial = case.admission.manifest
        selected = []
        for number, scope in ((98001, "organization"), (98002, "project")):
            original = next(row for row in initial["accounts"] if row["scope"] == scope)
            selected.append(
                {
                    **original,
                    "id": identity(number),
                    "period_start": "2029-01-01T00:00:00.000000Z",
                    "period_end": (
                        "2030-01-01T00:00:20.000000Z"
                        if scope == family
                        else "2100-01-01T00:00:00.000000Z"
                    ),
                }
            )
        provision = {
            **initial,
            "manifest_id": identity(98000),
            "operation": "provision",
            "source_digest": fixture.source,
            "parent_manifest_digest": digest(initial),
            "opening_accounts": None,
            "accounts": selected,
        }
        receipt = invoke(fixture, provision)
        assert receipt.sequence == 1 and receipt.account_rows == 2
        case.account_ids = (selected[0]["id"], selected[1]["id"], case.account_ids[2])
        original_clock = reservation._clock
        samples = []
        phase = {"published": False}

        def controlled_clock(connection):
            native = original_clock(connection)
            assert type(native) is int and native % 1000 == 0
            chosen = expiry + offset if phase["published"] else base
            samples.append((native, chosen, phase["published"]))
            return chosen

        # This is an explicit boundary-logic oracle, not elapsed-time evidence.
        # The native SQL still runs once per original sample, with its work cost.
        with monkeypatch.context() as clock:
            clock.setattr(reservation, "_clock", controlled_clock)
            fence = claim(case)
            before = snapshot(case.engine)
            lease = one(before, "jobs", id=case.job_id)["lease_until"]
            numerator, denominator = lease.as_integer_ratio()
            assert numerator * 1_000_000 > expiry * denominator
            samples.clear()

            def published(_connection, _cursor, statement, _parameters, _context, _many):
                if statement.upper().startswith("UPDATE JOBS SET RESERVED="):
                    phase["published"] = True

            event.listen(case.engine, "after_cursor_execute", published)
            operation = coordinator(case)
            value = intent(case, fence)
            try:
                if offset < 0:
                    result = reserve(case, fence, value, owner=operation)
                    assert result.kind == "created" and operation.outcome.commit_acknowledged
                    assert_reservation(before, snapshot(case.engine), value, case.organization_id)
                else:
                    with pytest.raises(ReservationRefusal) as caught:
                        reserve(case, fence, value, owner=operation)
                    assert caught.value.reason == "job_not_live"
                    assert operation.outcome.confirmed_precommit_rollback
                    same(before, snapshot(case.engine))
            finally:
                event.remove(case.engine, "after_cursor_execute", published)
            assert phase["published"] and any(not row[2] for row in samples)
            assert samples[-1][1:] == (expiry + offset, True)
        assert_released(case.engine)
    finally:
        case.close()


@pytest.mark.parametrize(
    "name", ["claim_generation", "require_live_job", "reserve", "inspect_original"], ids=str
)
def test_each_primitive_refuses_a_bare_connection_before_any_sql(case, name):
    from agent_rewind import reservation
    from agent_rewind.reservation_types import JobFence, ReservationScope
    from agent_rewind.sqlite_ownership import owned_connect

    scope = ReservationScope(case.principal, case.context, case.job_id)
    fence = JobFence(case.job_id, identity(90001), 1)
    arguments = {
        "claim_generation": (ClaimIntent(case.job_id, identity(90001), 0, 60),),
        "require_live_job": (fence,),
        "reserve": (fence, intent(case, fence)),
        "inspect_original": (None,),
    }
    before = snapshot(case.engine)
    statements = []
    with owned_connect(case.engine) as connection:
        event.listen(connection, "before_cursor_execute", lambda *args: statements.append(args[2]))
        with pytest.raises(ReservationRefusal) as caught:
            getattr(reservation, name)(connection, scope, *arguments[name])
        assert caught.value.reason == "transaction_not_owned"
        assert statements == [] and not connection.in_transaction()
    same(before, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize("field", ["job_id", "project_id"], ids=str)
def test_inconsistent_intent_consumes_owner_before_connection_acquisition(case, field):
    fence = claim(case)
    value = replace(intent(case, fence), **{field: identity(98000)})
    before = snapshot(case.engine)
    acquired = []
    operation = coordinator(case)

    def checkout(*args):
        acquired.append(args)

    event.listen(case.engine, "checkout", checkout)
    try:
        with pytest.raises(ReservationRefusal) as caught:
            reserve(case, fence, value, owner=operation)
        assert caught.value.reason == "invalid_intent"
        assert not operation.outcome.begun and acquired == []
        with pytest.raises(ReservationRefusal) as reused:
            reserve(case, fence, intent(case, fence), owner=operation)
        assert reused.value.reason == "invocation_reused" and acquired == []
    finally:
        event.remove(case.engine, "checkout", checkout)
    same(before, snapshot(case.engine))


def test_original_repeat_requires_current_record_permission_but_inspection_only_read(case):
    fence = claim(case)
    value = intent(case, fence)
    original = reserve(case, fence, value)
    with owned_begin(case.engine) as connection:
        changed = connection.execute(
            text(
                "UPDATE project_memberships SET role='viewer' "
                "WHERE project_id=:project AND principal_id=:principal"
            ),
            {"project": case.project_id, "principal": case.principal.principal_id},
        )
        assert changed.rowcount == 1
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ActionForbidden):
        reserve(case, fence, value, owner=operation)
    assert operation.outcome.confirmed_precommit_rollback
    observed = coordinator(case).inspect_original(case.principal, case.context, case.job_id, value)
    assert observed.call.kind == "matching" and observed.call.record == original.record
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_known_budget_refusal_does_not_claim_rollback_when_acknowledgment_is_lost(
    case, monkeypatch
):
    from reservation_qe_fixture import remaining_capacity

    from agent_rewind import reservation

    fence = claim(case)
    before = snapshot(case.engine)
    value = intent(case, fence, amount=remaining_capacity(before, case) + 1)
    operation = coordinator(case)
    original_reserve = reservation.reserve
    original_rollback = Connection.rollback
    failures, attempts = [], []

    def observe_refusal(*args, **kwargs):
        try:
            return original_reserve(*args, **kwargs)
        except ReservationRefusal as error:
            failures.append(error)
            raise

    def lose_rollback_ack(connection):
        if connection.engine is case.engine:
            attempts.append(connection)
            raise RuntimeError("synthetic rollback acknowledgment loss")
        return original_rollback(connection)

    with monkeypatch.context() as patch:
        patch.setattr(reservation, "reserve", observe_refusal)
        patch.setattr(Connection, "rollback", lose_rollback_ack)
        with pytest.raises(ReservationRefusal) as caught:
            reserve(case, fence, value, owner=operation)
    assert failures == [caught.value] and caught.value.reason == "budget_exceeded"
    assert caught.value.code == "invalid_request" and len(attempts) == 1
    assert operation.outcome.rollback_attempted and not operation.outcome.rollback_acknowledged
    assert operation.outcome.cleanup_failed and not operation.outcome.commit_attempted
    assert not operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_unexpected_write_failure_with_lost_rollback_ack_remains_uncertain(case, monkeypatch):
    fence = claim(case)
    value = intent(case, fence)
    before = snapshot(case.engine)
    operation = coordinator(case)
    original = Connection.rollback
    attempts = []

    def lose_ack(connection):
        if connection.engine is case.engine:
            attempts.append(connection)
            raise RuntimeError("synthetic rollback acknowledgment loss")
        return original(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "rollback", lose_ack)
        with (
            fail_after_write(case.engine, "provider_calls") as writes,
            pytest.raises(AdmissionError) as caught,
        ):
            reserve(case, fence, value, owner=operation)
    assert len(writes) == len(attempts) == 1
    assert caught.value.code == "outcome_uncertain"
    assert operation.outcome.rollback_attempted and not operation.outcome.rollback_acknowledged
    assert operation.outcome.cleanup_failed and not operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert_released(case.engine)
