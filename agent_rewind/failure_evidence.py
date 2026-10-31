"""Strict F3 claim values; none of these values confers execution authority."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from .admission_records import AdmissionStorageError, operation_value
from .admission_transaction import AdmissionCode, AdmissionError
from .artifact_metadata import ArtifactError
from .operation_reads import RawReceipt, validate_association
from .reservation_types import JobFence, ReservationRefusal

FailureReason = Literal[
    "invalid_intent",
    "capability_not_issued",
    "invocation_reused",
    "original_identity_conflict",
    "unsupported_profile",
    "stale_source",
    "not_eligible",
    "origin_unproved",
    "capacity_exceeded",
    "invalid_native_state",
]
_REASONS: dict[str, AdmissionCode] = {
    "invalid_intent": "invalid_request",
    "capability_not_issued": "invalid_request",
    "invocation_reused": "invalid_request",
    "original_identity_conflict": "idempotency_conflict",
    "unsupported_profile": "schema_incompatible",
    "stale_source": "dependency_unavailable",
    "not_eligible": "dependency_unavailable",
    "origin_unproved": "dependency_unavailable",
    "capacity_exceeded": "dependency_unavailable",
    "invalid_native_state": "dependency_unavailable",
}


class FailureRefusal(AdmissionError):
    """A closed reason, never evidence of rollback or permission to retry."""

    def __init__(self, reason: FailureReason):
        if type(reason) is not str or reason not in _REASONS:
            raise ValueError("invalid_refusal_reason")
        self.reason = reason
        super().__init__(_REASONS[reason])


def _identifier(value: object, width: int = 32) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value) is None:
        raise FailureRefusal("invalid_intent")


def _receipt(value: RawReceipt) -> None:
    # Validate exact containers before invoking any field/property on an object.
    if (
        type(value) is not RawReceipt
        or type(value.domain) is not str
        or type(value.identity) is not str
        or type(value.fields) is not tuple
        or type(value.values) is not tuple
        or not 1 <= len(value.fields) <= 16
        or len(value.fields) != len(value.values)
        or any(type(name) is not str or len(name) > 64 for name in value.fields)
        or len(set(value.fields)) != len(value.fields)
    ):
        raise FailureRefusal("invalid_intent")
    for scalar in value.values:
        if type(scalar) not in (str, int, float, bool, type(None)):
            raise FailureRefusal("invalid_intent")
        if type(scalar) is str:
            try:
                if len(scalar) > 4096 or len(scalar.encode("utf-8")) > 4096:
                    raise FailureRefusal("invalid_intent")
            except UnicodeError:
                raise FailureRefusal("invalid_intent") from None
        elif (
            type(scalar) is int
            and not -(2**63) <= scalar < 2**63
            or type(scalar) is float
            and not math.isfinite(scalar)
        ):
            raise FailureRefusal("invalid_intent")


@dataclass(frozen=True)
class ClaimedFailureSource:
    """Detached bounded native claim observations, explicitly not a capability."""

    organization_id: str
    project_id: str
    fence: JobFence
    operation: RawReceipt
    job: RawReceipt
    configuration: RawReceipt
    configuration_digest: str
    configuration_size: int

    def __post_init__(self) -> None:
        _identifier(self.organization_id)
        _identifier(self.project_id)
        _identifier(self.configuration_digest, 64)
        if type(self.fence) is not JobFence:
            raise FailureRefusal("invalid_intent")
        try:
            self.fence.__post_init__()
        except ReservationRefusal:
            raise FailureRefusal("invalid_intent") from None
        if type(self.configuration_size) is not int or not 1 <= self.configuration_size <= 65536:
            raise FailureRefusal("invalid_intent")
        for receipt in (self.operation, self.job, self.configuration):
            _receipt(receipt)
        try:
            validate_association(self.operation, self.job, self.configuration)
            operation = operation_value(self.operation.row())
            job, configuration = self.job.row(), self.configuration.row()
            _identifier(operation.failure_correlation_id)
            if (
                self.operation.identity != operation.id
                or operation.project_id != self.project_id
                or operation.job_id != self.fence.job_id
                or job["owner"] != self.fence.owner_uuid
                or job["status"] != "running"
                or job["cancel"] not in (False, 0)
                or job["lease_until"] is None
                or job["error"] is not None
                or job["result"] is not None
                or operation.execution_config_digest != self.configuration_digest
                or configuration["byte_count"] != self.configuration_size
            ):
                raise FailureRefusal("invalid_intent")
        except (AdmissionStorageError, ArtifactError, ValueError, TypeError, KeyError):
            raise FailureRefusal("invalid_intent") from None


class _AcknowledgedClaim:
    """Only exact instances retained by the issuing coordinator can be consumed."""

    __slots__ = ()

    def __new__(cls) -> _AcknowledgedClaim:
        raise FailureRefusal("capability_not_issued")


FailureCause = Literal[
    "budget_refused", "dependency_failed", "internal_fault", "dispatch_uncertain", "lease_expired"
]


def _choice(value: object, allowed: tuple[str, ...]) -> None:
    if type(value) is not str or value not in allowed:
        raise FailureRefusal("invalid_intent")


@dataclass(frozen=True)
class FailureRecord:
    """The exact verified native row; detached data grants no write authority."""

    schema_version: int
    kind: Literal["verified_failure"]
    project_id: str
    job_resource_kind: Literal["job"]
    job_id: str
    operation_id: str
    lease_generation: int
    job_status: Literal["failed", "cancelled"]
    cause: FailureCause
    phase: Literal["outcome_unknown"]
    origin_kind: Literal["admission"]
    correlation_id: str
    association_sha256: str
    source_sha256: str
    created_at_micros: int

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise FailureRefusal("invalid_intent")
        for value in (self.project_id, self.job_id, self.operation_id, self.correlation_id):
            _identifier(value)
        for value in (self.association_sha256, self.source_sha256):
            _identifier(value, 64)
        if (
            type(self.lease_generation) is not int
            or not 1 <= self.lease_generation < 2**63
            or type(self.created_at_micros) is not int
            or not 0 <= self.created_at_micros <= 253402300799999999
        ):
            raise FailureRefusal("invalid_intent")
        _choice(self.kind, ("verified_failure",))
        _choice(self.job_resource_kind, ("job",))
        _choice(self.job_status, ("failed", "cancelled"))
        _choice(
            self.cause,
            (
                "budget_refused",
                "dependency_failed",
                "internal_fault",
                "dispatch_uncertain",
                "lease_expired",
            ),
        )
        _choice(self.phase, ("outcome_unknown",))
        _choice(self.origin_kind, ("admission",))
        if self.cause == "lease_expired" and self.job_status != "failed":
            raise FailureRefusal("invalid_intent")


@dataclass(frozen=True)
class OriginalFailureIntent:
    """Original native identity/timestamp for inspection, never a retry token."""

    organization_id: str
    fence: JobFence
    record: FailureRecord

    def __post_init__(self) -> None:
        _identifier(self.organization_id)
        if type(self.fence) is not JobFence or type(self.record) is not FailureRecord:
            raise FailureRefusal("invalid_intent")
        try:
            self.fence.__post_init__()
        except ReservationRefusal:
            raise FailureRefusal("invalid_intent") from None
        self.record.__post_init__()
        if (
            self.fence.job_id != self.record.job_id
            or self.fence.generation != self.record.lease_generation
        ):
            raise FailureRefusal("invalid_intent")


def _original(value: OriginalFailureIntent) -> None:
    if type(value) is not OriginalFailureIntent:
        raise FailureRefusal("invalid_intent")
    value.__post_init__()


@dataclass(frozen=True)
class CreatedFailure:
    original: OriginalFailureIntent
    kind: Literal["created"] = field(default="created", init=False)

    def __post_init__(self) -> None:
        _original(self.original)


@dataclass(frozen=True)
class MatchingOriginal:
    original: OriginalFailureIntent
    kind: Literal["matching"] = field(default="matching", init=False)

    def __post_init__(self) -> None:
        _original(self.original)


@dataclass(frozen=True)
class Absent:
    kind: Literal["absent"] = field(default="absent", init=False)


@dataclass(frozen=True)
class Conflict:
    kind: Literal["conflict"] = field(default="conflict", init=False)


@dataclass(frozen=True)
class TentativeCreated:
    """Private in-transaction value; only the coordinator can publish success."""

    original: OriginalFailureIntent

    def __post_init__(self) -> None:
        _original(self.original)


class CompletionEvent:
    """Exact identity is consumed once; instances carry no authority payload."""

    __slots__ = ("__weakref__",)

    def __new__(cls) -> CompletionEvent:
        raise FailureRefusal("capability_not_issued")


class IssuedTerminalScope:
    """Only the live coordinator's exact connection-bound scope is accepted."""

    __slots__ = ()

    def __new__(cls) -> IssuedTerminalScope:
        raise FailureRefusal("capability_not_issued")
