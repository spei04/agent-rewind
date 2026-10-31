"""Fixed adopted D3 digest frames; integrity equality never grants authority."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from .admission_records import AdmissionStorageError
from .admission_request import AdmissionPreparationError, bounded_canonical
from .artifact_metadata import ArtifactError
from .failure_evidence import FailureRecord, FailureRefusal, _identifier, _receipt
from .operation_reads import (
    IMMUTABLE_JOB_FIELDS,
    JOB_LIMITS,
    MAX_RECEIPT_BYTES,
    RawReceipt,
    validate_association,
    validate_job_row,
)

_SCOPE_FIELDS = ("organization_id", "project_id", "resource_kind", "resource_id")
_TERMINAL_FIELDS = tuple(name for name in JOB_LIMITS if name != "cancel")
_CORE_FIELDS = (
    "schema_version",
    "kind",
    "project_id",
    "job_resource_kind",
    "job_id",
    "operation_id",
    "lease_generation",
    "job_status",
    "cause",
    "phase",
    "origin_kind",
    "correlation_id",
    "created_at_micros",
)


def _tag(value: object) -> list[Any]:
    if value is None:
        return ["n"]
    if type(value) is bool:
        return ["b", int(value)]
    if type(value) is int and -(2**63) <= value < 2**63:
        return ["i", str(value)]
    if type(value) is float and math.isfinite(value):
        # This is the sole adopted normalization; native timestamp Text is exact.
        return ["f", (0.0 if value == 0 else value).hex()]
    if type(value) is str:
        try:
            if len(value) <= 4096 and len(value.encode("utf-8")) <= 4096:
                return ["s", value]
        except UnicodeError:
            pass
    raise FailureRefusal("invalid_intent")


def _row(label: str, fields: tuple[str, ...], values: dict[str, Any]) -> list[Any]:
    if set(values) != set(fields):
        raise FailureRefusal("invalid_intent")
    return [label, [[name, _tag(values[name])] for name in fields]]


def _digest(frame: list[Any], remaining: int) -> tuple[str, int]:
    if type(remaining) is not int or not 0 <= remaining <= MAX_RECEIPT_BYTES:
        raise FailureRefusal("invalid_intent")
    try:
        # The existing encoder measures escaping and complete byte length before
        # allocating output. Only this active frame uses the supplied remaining
        # allowance; its buffer is released before the next observation/frame.
        encoded = bounded_canonical(
            frame, limit=min(4096, remaining), limit_code="admission_body_limit"
        )
    except AdmissionPreparationError as error:
        raise FailureRefusal(
            "capacity_exceeded" if error.code == "admission_body_limit" else "invalid_intent"
        ) from None
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _dialect(value: str) -> None:
    if type(value) is not str or value not in ("sqlite", "postgresql"):
        raise FailureRefusal("invalid_intent")


def association_digest(
    dialect: str,
    organization_id: str,
    project_id: str,
    operation: RawReceipt,
    job: RawReceipt,
    configuration: RawReceipt,
    *,
    remaining: int,
) -> tuple[str, int]:
    """Hash only the adopted scope/op14/immutable-job9/config8 representation."""
    _dialect(dialect)
    _identifier(organization_id)
    _identifier(project_id)
    for receipt in (operation, job, configuration):
        _receipt(receipt)
    try:
        validate_association(operation, job, configuration)
    except (AdmissionStorageError, ArtifactError, ValueError, TypeError, KeyError):
        raise FailureRefusal("invalid_intent") from None
    op, values, config = operation.row(), job.row(), configuration.row()
    if op["project_id"] != project_id:
        raise FailureRefusal("invalid_intent")
    scope = {
        "organization_id": organization_id,
        "project_id": project_id,
        "resource_kind": "job",
        "resource_id": job.identity,
    }
    return _digest(
        [
            "ar-failure-association",
            1,
            dialect,
            _row("scope", _SCOPE_FIELDS, scope),
            _row("operation", operation.fields, op),
            _row(
                "job_immutable",
                IMMUTABLE_JOB_FIELDS,
                {name: values[name] for name in IMMUTABLE_JOB_FIELDS},
            ),
            _row("admission_config", configuration.fields, config),
        ],
        remaining,
    )


def source_digest(
    dialect: str,
    association_sha256: str,
    job: RawReceipt,
    generation: int,
    any_provider_call: bool,
    record: FailureRecord,
    *,
    remaining: int,
) -> tuple[str, int]:
    """Hash the tag2 terminal after-image, excluding cancel and both digests."""
    _dialect(dialect)
    _identifier(association_sha256, 64)
    _receipt(job)
    if (
        type(record) is not FailureRecord
        or type(generation) is not int
        or not 1 <= generation < 2**63
        or type(any_provider_call) is not bool
    ):
        raise FailureRefusal("invalid_intent")
    record.__post_init__()
    try:
        if job.domain != "job" or job.fields != tuple(JOB_LIMITS):
            raise FailureRefusal("invalid_intent")
        values = validate_job_row(job.row(), job.identity).row()
    except (AdmissionStorageError, ValueError, TypeError, KeyError):
        raise FailureRefusal("invalid_intent") from None
    if (
        record.job_id != job.identity
        or record.lease_generation != generation
        or record.job_status != values["status"]
        or record.association_sha256 != association_sha256
        or values["error"] is not None
        or values["result"] is not None
        or values["payload_version"] != 2
        or values["status"] == "cancelled"
        and values["cancel"] not in (True, 1)
    ):
        raise FailureRefusal("invalid_intent")
    core = {name: getattr(record, name) for name in _CORE_FIELDS}
    return _digest(
        [
            "ar-failure-source",
            2,
            dialect,
            association_sha256,
            _row(
                "job_terminal", _TERMINAL_FIELDS, {name: values[name] for name in _TERMINAL_FIELDS}
            ),
            ["generation", _tag(generation)],
            ["any_provider_call_for_job", _tag(any_provider_call)],
            _row("evidence_core", _CORE_FIELDS, core),
        ],
        remaining,
    )
