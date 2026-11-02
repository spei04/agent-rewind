"""P2 native-money and complete-state refusal boundaries, independently observed."""

from dataclasses import fields

import pytest
from reservation_fixture import build_reservation_case
from reservation_qe_fixture import (
    assert_released,
    assert_reservation,
    build_prior_hold_case,
    claim,
    coordinator,
    intent,
    one,
    remaining_capacity,
    rows,
    same,
    snapshot,
)
from sqlalchemy import text

from agent_rewind.reservation_types import ReservationRefusal
from agent_rewind.sqlite_ownership import owned_begin

MAX_MONEY = 2**63 - 1


@pytest.fixture
def case(tmp_path, monkeypatch, fresh_sqlite_ar6_template):
    value = build_reservation_case(
        tmp_path, monkeypatch, fresh_ar6_template=fresh_sqlite_ar6_template
    )
    yield value
    value.close()


@pytest.mark.parametrize("amount", [0, 7], ids=["zero", "positive"])
def test_reservation_keeps_exact_native_integers(case, amount):
    fence = claim(case)
    value = intent(case, fence, amount=amount)
    before = snapshot(case.engine)
    decision = coordinator(case).reserve(case.principal, case.context, fence, value)
    assert decision.kind == "created"
    assert type(decision.record.identity.reserved_microusd) is int
    assert decision.record.identity.reserved_microusd == amount
    assert_reservation(before, snapshot(case.engine), value, case.organization_id)
    assert_released(case.engine)


@pytest.mark.parametrize(
    "amount", [2**53 + 1, MAX_MONEY], ids=["above_float_precision", "signed64_max"]
)
def test_wide_integer_never_bypasses_the_real_admitted_job_cap(
    tmp_path, monkeypatch, amount, fresh_sqlite_ar6_template
):
    # Actual admission caps this budget at 200M; wider financial inputs must not
    # be made successful by fabricating an unsupported admitted association.
    case = build_reservation_case(
        tmp_path,
        monkeypatch,
        budget=200_000_000,
        account_limit=MAX_MONEY,
        fresh_ar6_template=fresh_sqlite_ar6_template,
    )
    try:
        fence = claim(case)
        value = intent(case, fence, amount=amount)
        before = snapshot(case.engine)
        operation = coordinator(case)
        with pytest.raises(ReservationRefusal) as caught:
            operation.reserve(case.principal, case.context, fence, value)
        assert caught.value.reason == "budget_exceeded"
        assert operation.outcome.confirmed_precommit_rollback
        same(before, snapshot(case.engine))
        assert_released(case.engine)
    finally:
        case.close()


def test_exact_remaining_three_level_capacity_then_one_more_refuses(case):
    fence = claim(case)
    before = snapshot(case.engine)
    remaining = remaining_capacity(before, case)
    assert remaining > 0
    value = intent(case, fence, amount=remaining)
    assert coordinator(case).reserve(case.principal, case.context, fence, value).kind == "created"
    full = snapshot(case.engine)
    assert_reservation(before, full, value, case.organization_id)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.reserve(
            case.principal, case.context, fence, intent(case, fence, amount=1, number=93000)
        )
    assert caught.value.reason == "budget_exceeded"
    assert operation.outcome.confirmed_precommit_rollback
    same(full, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize(
    "amount",
    [True, False, 7.0, "7", -1, MAX_MONEY + 1],
    ids=["true", "false", "float", "text", "negative", "overflow"],
)
def test_owner_revalidates_native_money_even_if_dataclass_initialization_was_bypassed(case, amount):
    fence = claim(case)
    valid = intent(case, fence)
    invalid = object.__new__(type(valid))
    for field in fields(valid):
        object.__setattr__(invalid, field.name, getattr(valid, field.name))
    object.__setattr__(invalid, "reserved_microusd", amount)
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.reserve(case.principal, case.context, fence, invalid)
    assert caught.value.reason == "invalid_intent"
    assert not operation.outcome.commit_attempted
    same(before, snapshot(case.engine))
    # Invalid input consumes the owner too; correcting the object cannot restart it.
    with pytest.raises(ReservationRefusal) as reused:
        operation.reserve(case.principal, case.context, fence, valid)
    assert reused.value.reason == "invocation_reused"
    assert_released(case.engine)


@pytest.mark.parametrize("target", ["balance", "gross"], ids=str)
def test_native_valid_counters_are_not_trusted_without_complete_history(case, target):
    fence = claim(case)
    with owned_begin(case.engine) as connection:
        if target == "balance":
            connection.execute(
                text("UPDATE budget_accounts SET held_microusd=held_microusd+1 WHERE id=:id"),
                {"id": case.account_ids[2]},
            )
        else:
            connection.execute(
                text("UPDATE jobs SET reserved=reserved+1 WHERE id=:id"), {"id": case.job_id}
            )
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.reserve(case.principal, case.context, fence, intent(case, fence))
    assert caught.value.reason == "ledger_state_invalid"
    assert operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert_released(case.engine)


@pytest.mark.parametrize(
    "opening",
    [2**53 + 1, MAX_MONEY - 7, MAX_MONEY],
    ids=["above_float_precision", "seven_remaining", "at_maximum"],
)
def test_wide_legacy_setup_retains_real_admitted_job_and_immutable_opening(
    tmp_path, monkeypatch, opening
):
    value = build_prior_hold_case(tmp_path, monkeypatch, opening=opening)
    try:
        state = snapshot(value.engine)
        admitted = one(state, "jobs", id=value.job_id)
        assert type(admitted["budget"]) is type(admitted["reserved"]) is int
        assert admitted["payload_version"] == 2 and admitted["budget"] == 1_000_000
        assert admitted["reserved"] == admitted["legacy_reserved_microusd"] == 0
        legacy = [row for row in rows(state, "jobs") if row["id"] != value.job_id]
        assert len(legacy) == 3 and all(row["payload_version"] == 1 for row in legacy)
        assert sum(row["legacy_reserved_microusd"] for row in legacy) == opening
        assert all(row["reserved"] == row["legacy_reserved_microusd"] for row in legacy)
        for account_id in value.account_ids[:2]:
            account = one(state, "budget_accounts", id=account_id)
            assert type(account["held_microusd"]) is type(account["limit_microusd"]) is int
            assert account["opening_held_microusd"] == account["held_microusd"] == opening
            assert account["limit_microusd"] == MAX_MONEY and account["accounted_microusd"] == 0
        assert rows(state, "provider_calls") == rows(state, "budget_entries") == []
        assert_released(value.engine)
    finally:
        value.close()


@pytest.mark.parametrize(
    "opening", [2**53 + 1, MAX_MONEY - 7], ids=["wide_opening", "exact_signed64_boundary"]
)
def test_new_small_reservation_counts_exact_prior_holds_without_float_loss(
    tmp_path, monkeypatch, opening
):
    value = build_prior_hold_case(tmp_path, monkeypatch, opening=opening)
    try:
        fence = claim(value)
        before = snapshot(value.engine)
        request = intent(value, fence, amount=7)
        result = coordinator(value).reserve(value.principal, value.context, fence, request)
        assert result.kind == "created"
        after = snapshot(value.engine)
        assert_reservation(before, after, request, value.organization_id)
        for account_id in value.account_ids[:2]:
            assert one(after, "budget_accounts", id=account_id)["held_microusd"] == opening + 7
        if opening == MAX_MONEY - 7:
            operation = coordinator(value)
            with pytest.raises(ReservationRefusal) as caught:
                operation.reserve(
                    value.principal,
                    value.context,
                    fence,
                    intent(value, fence, amount=1, number=97000),
                )
            assert caught.value.reason == "budget_exceeded"
            assert operation.outcome.confirmed_precommit_rollback
            same(after, snapshot(value.engine))
        assert_released(value.engine)
    finally:
        value.close()


def test_prior_holds_at_signed64_max_refuse_positive_amount_without_overflow(tmp_path, monkeypatch):
    value = build_prior_hold_case(tmp_path, monkeypatch, opening=MAX_MONEY)
    try:
        fence = claim(value)
        before = snapshot(value.engine)
        operation = coordinator(value)
        with pytest.raises(ReservationRefusal) as caught:
            operation.reserve(value.principal, value.context, fence, intent(value, fence, amount=1))
        assert caught.value.reason == "budget_exceeded"
        assert operation.outcome.confirmed_precommit_rollback
        same(before, snapshot(value.engine))
        assert_released(value.engine)
    finally:
        value.close()


def test_actual_original_source_row_exceeding_canonical_headroom_refuses_before_reserve(case):
    fence = claim(case)
    # SQLite's original unversioned VARCHAR cells are not length-enforced.
    # This actual synthetic source row stays below the native 16 MiB bound,
    # but cannot prove conservative canonical headroom under the same bound.
    with owned_begin(case.engine) as connection:
        connection.execute(
            text(
                "INSERT INTO audit(id,created,actor,action,target) "
                "VALUES(:id,0.0,'synthetic-qe',:action,'source-capacity')"
            ),
            {"id": "f" * 32, "action": "x" * 524_288},
        )
        native = connection.execute(
            text("SELECT length(CAST(action AS BLOB)) FROM audit WHERE id=:id"),
            {"id": "f" * 32},
        ).scalar_one()
        assert type(native) is int and native == 524_288 < 16 * 1024 * 1024
    before = snapshot(case.engine)
    operation = coordinator(case)
    with pytest.raises(ReservationRefusal) as caught:
        operation.reserve(case.principal, case.context, fence, intent(case, fence))
    assert caught.value.reason == "capacity_exceeded"
    assert operation.outcome.confirmed_precommit_rollback
    same(before, snapshot(case.engine))
    assert_released(case.engine)


def test_two_released_legacy_job_grosses_can_exceed_signed64_account_lifetime(
    tmp_path, monkeypatch
):
    from reservation_qe_fixture import build_released_legacy_history_case

    case = build_released_legacy_history_case(tmp_path, monkeypatch)
    try:
        fence = claim(case)
        before = snapshot(case.engine)
        value = intent(case, fence, amount=7)
        operation = coordinator(case)
        result = operation.reserve(case.principal, case.context, fence, value)
        assert result.kind == "created" and operation.outcome.commit_acknowledged
        assert_reservation(before, snapshot(case.engine), value, case.organization_id)
        assert_released(case.engine)
    finally:
        case.close()
