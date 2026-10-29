"""Strict P2 intent boundaries and inherited failure/outcome semantics."""

from dataclasses import FrozenInstanceError, replace

import pytest
from test_admission_transaction import engine

from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.reservation_types import (
    MAX_MONEY,
    ClaimIntent,
    JobFence,
    JobObservation,
    ReservationIntent,
    ReservationRecord,
    ReservationRefusal,
    TransactionFacts,
)

__all__ = ["engine"]


def intent():
    return ReservationIntent(
        call_id="1" * 32,
        project_id="2" * 32,
        job_id="3" * 32,
        logical_call_id="4" * 32,
        request_digest="5" * 64,
        purpose="continuation",
        price_version="prices-1",
        reserved_microusd=2**53 + 1,
        lease_generation=1,
        organization_account_id="6" * 32,
        project_account_id="7" * 32,
        job_account_id="8" * 32,
    )


@pytest.mark.parametrize("amount", [0, 2**53 + 1, MAX_MONEY], ids=["zero", "wide", "max"])
def test_integer_money_is_exact_and_record_is_frozen(amount):
    value = replace(intent(), reserved_microusd=amount)
    assert value.reserved_microusd == amount and type(value.reserved_microusd) is int
    with pytest.raises(FrozenInstanceError):
        value.reserved_microusd = 1
    record = ReservationRecord(value, "reserved", 0, 0)
    assert record.identity == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("reserved_microusd", True),
        ("reserved_microusd", 1.0),
        ("reserved_microusd", -1),
        ("reserved_microusd", MAX_MONEY + 1),
        ("lease_generation", 0),
        ("lease_generation", False),
        ("call_id", "A" * 32),
        ("request_digest", "x" * 64),
        ("price_version", ""),
        ("price_version", "bad\n"),
        ("purpose", "dispatch"),
        ("job_account_id", "6" * 32),
    ],
    ids=[
        "bool",
        "float",
        "negative",
        "overflow",
        "zero-generation",
        "bool-generation",
        "uppercase-id",
        "bad-digest",
        "empty-price",
        "control-price",
        "purpose",
        "same-account",
    ],
)
def test_invalid_intent_refuses_before_any_connection(field, value):
    with pytest.raises(ReservationRefusal) as caught:
        replace(intent(), **{field: value})
    assert caught.value.reason == "invalid_intent" and caught.value.code == "invalid_request"


def test_price_utf8_limit_and_unknown_fields_refuse():
    assert replace(intent(), price_version="é" * 64).price_version == "é" * 64
    with pytest.raises(ReservationRefusal):
        replace(intent(), price_version="é" * 65)
    with pytest.raises(TypeError):
        replace(intent(), unknown=True)


def test_claim_generation_and_fence_are_strict_and_do_not_renew():
    claim = ClaimIntent("1" * 32, "2" * 32, MAX_MONEY - 1, 60)
    assert (
        JobFence(claim.job_id, claim.owner_uuid, claim.expected_generation + 1).generation
        == MAX_MONEY
    )
    for changed in (
        {"expected_generation": MAX_MONEY},
        {"lease_seconds": 0},
        {"lease_seconds": True},
    ):
        with pytest.raises(ReservationRefusal):
            replace(claim, **changed)
    with pytest.raises(ReservationRefusal):
        JobFence(claim.job_id, claim.owner_uuid, 0)


def test_settlement_and_release_cannot_exceed_the_original_integer_reserve():
    value = replace(intent(), reserved_microusd=10)
    assert ReservationRecord(value, "reconciled", 7, 3).released_microusd == 3
    with pytest.raises(ReservationRefusal):
        ReservationRecord(value, "reconciled", 7, 4)


def test_known_refusal_retains_identity_after_acknowledged_rollback(engine):
    expected = ReservationRefusal("budget_exceeded")
    outcome = TransactionOutcome()
    with (
        pytest.raises(ReservationRefusal) as caught,
        admission_transaction(engine, outcome) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        raise expected
    assert caught.value is expected and isinstance(expected, AdmissionError)
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted


def test_outcome_snapshot_is_detached_and_never_erases_commit_attempt():
    outcome = TransactionOutcome(
        begun=True, commit_attempted=True, commit_acknowledged=True, cleanup_failed=True
    )
    observed = TransactionFacts.observe(outcome)
    outcome.cleanup_failed = False
    assert observed.commit_acknowledged and observed.cleanup_failed
    assert not observed.confirmed_precommit_rollback
    with pytest.raises(FrozenInstanceError):
        observed.commit_acknowledged = False


def test_refusal_constructor_never_accepts_a_free_form_code_or_reason():
    with pytest.raises(ValueError, match="^invalid_refusal_reason$"):
        ReservationRefusal("PRIVATE-TEXT")


def test_oversized_price_is_a_closed_refusal():
    with pytest.raises(ReservationRefusal) as caught:
        replace(intent(), price_version="x" * 1_000_000)
    assert caught.value.reason == "invalid_intent"


def test_lease_observation_keeps_native_integer_precision_and_refuses_huge_values():
    value = JobObservation("1" * 32, None, 0, "queued", MAX_MONEY)
    assert value.lease_until == MAX_MONEY and type(value.lease_until) is int
    with pytest.raises(ReservationRefusal) as caught:
        replace(value, lease_until=10**1000)
    assert caught.value.reason == "invalid_intent"
