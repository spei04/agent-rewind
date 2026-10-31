"""Detached failure values and refusal boundaries; no native success or registration."""

from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from agent_rewind.failure_evidence import (
    Absent,
    CompletionEvent,
    Conflict,
    CreatedFailure,
    FailureRecord,
    FailureRefusal,
    IssuedTerminalScope,
    MatchingOriginal,
    OriginalFailureIntent,
    TentativeCreated,
    _AcknowledgedClaim,
)
from agent_rewind.reservation_types import JobFence


@pytest.mark.parametrize("value", ["private secret canary", True, None, [], object()])
def test_unknown_failure_reason_never_becomes_an_error_payload(value):
    with pytest.raises(ValueError, match="^invalid_refusal_reason$"):
        FailureRefusal(value)


def test_acknowledged_claim_cannot_be_constructed_from_caller_values():
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        _AcknowledgedClaim()
    assert caught.value.reason == "capability_not_issued"
    forged = object.__new__(_AcknowledgedClaim)
    with pytest.raises(AttributeError):
        forged.job_id = "a" * 32


def _record(**changes):
    # These are detached example values, never a claimed native row or an event.
    values = {
        "schema_version": 1,
        "kind": "verified_failure",
        "project_id": "a" * 32,
        "job_resource_kind": "job",
        "job_id": "b" * 32,
        "operation_id": "c" * 32,
        "lease_generation": 1,
        "job_status": "failed",
        "cause": "dependency_failed",
        "phase": "outcome_unknown",
        "origin_kind": "admission",
        "correlation_id": "d" * 32,
        "association_sha256": "e" * 64,
        "source_sha256": "f" * 64,
        "created_at_micros": 123456,
    }
    values.update(changes)
    return FailureRecord(**values)


def _original(record=None):
    record = _record() if record is None else record
    return OriginalFailureIntent(
        "0" * 32, JobFence(record.job_id, "1" * 32, record.lease_generation), record
    )


class _IntegerSubclass(int):
    pass


class _StringSubclass(str):
    pass


@pytest.mark.parametrize(
    ("generation", "timestamp"),
    [(1, 0), (2**63 - 1, 253402300799999999)],
    ids=["minimum", "maximum"],
)
def test_detached_original_retains_exact_native_integer_endpoints(generation, timestamp):
    record = _record(
        lease_generation=generation, created_at_micros=timestamp, cause="lease_expired"
    )
    original = _original(record)
    assert original.record is record
    assert original.record.lease_generation == original.fence.generation == generation
    assert original.record.created_at_micros == timestamp


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("lease_generation", 1.0),
        ("lease_generation", _IntegerSubclass(1)),
        ("lease_generation", 0),
        ("lease_generation", 2**63),
        ("created_at_micros", False),
        ("created_at_micros", -1),
        ("created_at_micros", 253402300800000000),
        ("project_id", "A" * 32),
        ("job_id", "b" * 31),
        ("operation_id", None),
        ("correlation_id", "é" * 32),
        ("association_sha256", "e" * 63),
        ("source_sha256", b"f" * 64),
    ],
    ids=[
        "boolean-schema",
        "future-schema",
        "float-generation",
        "integer-subclass",
        "zero-generation",
        "generation-over",
        "boolean-time",
        "negative-time",
        "time-over",
        "uppercase-project",
        "short-job",
        "null-operation",
        "unicode-correlation",
        "short-digest",
        "bytes-digest",
    ],
)
def test_failure_record_refuses_type_range_and_identifier_confusion(field, value):
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        _record(**{field: value})
    assert caught.value.reason == "invalid_intent"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "historical_marker"),
        ("job_resource_kind", "run"),
        ("job_status", "running"),
        ("cause", "private-terminal-secret"),
        ("phase", "pre_dispatch"),
        ("origin_kind", "migration_marker"),
        ("cause", _StringSubclass("dependency_failed")),
    ],
    ids=[
        "marker",
        "resource",
        "live-status",
        "foreign-cause",
        "unissued-phase",
        "origin",
        "string-subclass",
    ],
)
def test_failure_record_refuses_unissued_variants_without_disclosing_values(field, value):
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        _record(**{field: value})
    assert caught.value.reason == "invalid_intent"
    assert caught.value.args == ("invalid_request",)
    assert "private-terminal-secret" not in repr(caught.value)


def test_expiry_cannot_be_relabelled_as_cancellation():
    cancelled = _record(job_status="cancelled")
    assert cancelled.cause == "dependency_failed"
    with pytest.raises(FailureRefusal, match="^invalid_request$"):
        replace(cancelled, cause="lease_expired")


@pytest.mark.parametrize("difference", ["organization", "job", "generation"])
def test_original_intent_refuses_cross_fence_identity(difference):
    original = _original()
    before = asdict(original)
    changes = {
        "organization": {"organization_id": True},
        "job": {"fence": replace(original.fence, job_id="2" * 32)},
        "generation": {"fence": replace(original.fence, generation=2)},
    }
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        replace(original, **changes[difference])
    assert caught.value.reason == "invalid_intent"
    assert asdict(original) == before


@pytest.mark.parametrize("field", ["fence", "record"])
def test_original_intent_rejects_foreign_nested_type_before_observing_it(field):
    class ForeignValue:
        def __getattribute__(self, name):
            raise AssertionError("private-property-canary")

    original = _original()
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        replace(original, **{field: ForeignValue()})
    assert caught.value.reason == "invalid_intent"
    assert "private-property-canary" not in repr(caught.value)


@pytest.mark.parametrize(
    ("result_type", "field"),
    [(CreatedFailure, "record"), (MatchingOriginal, "fence"), (TentativeCreated, "record")],
)
def test_result_revalidates_corrupted_detached_original(result_type, field):
    original = _original()
    # Simulate foreign construction of detached data, never issued capability state.
    target = getattr(original, field)
    object.__setattr__(target, "lease_generation" if field == "record" else "generation", True)
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        result_type(original)
    assert caught.value.reason == "invalid_intent"


def test_detached_results_preserve_original_identity_and_fixed_immutable_kinds():
    original = _original()
    before = asdict(original)
    created, matching, tentative = (
        CreatedFailure(original),
        MatchingOriginal(original),
        TentativeCreated(original),
    )
    assert created.original is matching.original is tentative.original is original
    assert (created.kind, matching.kind, Absent().kind, Conflict().kind) == (
        "created",
        "matching",
        "absent",
        "conflict",
    )
    for value, field, replacement in (
        (original.record, "created_at_micros", 0),
        (original.fence, "generation", 2),
        (original, "record", _record(created_at_micros=0)),
        (created, "kind", "matching"),
        (matching, "original", _original()),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)
    assert asdict(original) == before
    with pytest.raises(TypeError):
        CreatedFailure(original, kind="matching")
    with pytest.raises(TypeError):
        MatchingOriginal(original, kind="created")


@pytest.mark.parametrize("token_type", [CompletionEvent, IssuedTerminalScope])
def test_detached_values_cannot_construct_terminal_authority(token_type):
    _original()  # A valid detached intent does not change constructor authority.
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        token_type()
    assert caught.value.reason == "capability_not_issued"


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("invalid_intent", "invalid_request"),
        ("capability_not_issued", "invalid_request"),
        ("invocation_reused", "invalid_request"),
        ("original_identity_conflict", "idempotency_conflict"),
        ("unsupported_profile", "schema_incompatible"),
        ("stale_source", "dependency_unavailable"),
        ("not_eligible", "dependency_unavailable"),
        ("origin_unproved", "dependency_unavailable"),
        ("capacity_exceeded", "dependency_unavailable"),
        ("invalid_native_state", "dependency_unavailable"),
    ],
)
def test_failure_refusal_has_the_adopted_literal_public_code(reason, code):
    error = FailureRefusal(reason)
    assert error.reason == reason
    assert error.code == code
    assert error.args == (code,) and str(error) == code
