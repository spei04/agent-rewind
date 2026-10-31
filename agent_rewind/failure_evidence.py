"""Strict F3 claim values; none of these values confers execution authority."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
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
