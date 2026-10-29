"""Offline public-candidate declarations; no rights service or native admission.

The caller owns current approval, revocation and clock authority. Validated
metadata never authorizes acquisition, inference, recording or publication.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from .corpus import (
    MAX_MANIFEST_BYTES,
    AdmissionPolicy,
    EvaluatorIdentity,
    Identifier,
    ManifestTimestamp,
    Permission,
    PrivateObject,
    PublicationRules,
    Purpose,
    Retention,
    SourceIdentity,
)
from .models import StrictModel

PublicDeclarationCode = Literal[
    "invalid-validation-time",
    "invalid-policy",
    "manifest-too-large",
    "invalid-manifest",
    "unsupported-version",
    "unsupported-record-kind",
    "duplicate-candidate-id",
    "duplicate-row-identity",
    "declaration-not-reviewed",
    "policy-not-current",
    "rights-missing",
    "rights-revoked",
    "manifest-from-future",
    "processor-not-approved",
    "storage-not-approved",
    "purpose-mismatch",
    "retention-expired",
    "retention-review-overdue",
    "permission-not-active",
    "permission-expired",
    "retention-exceeds-permission",
    "processor-not-permitted",
    "purpose-not-permitted",
]
RightsStatus = Literal["current", "revoked", "missing"]
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PURPOSES = frozenset({"debugging", "intervention-screening", "independent-confirmation"})


class PublicCandidate(StrictModel):
    candidate_id: Identifier
    workflow_id: Literal["manual-action-recovery", "automatic-intervention-evaluation"]
    dataset: SourceIdentity
    row: PrivateObject
    source: SourceIdentity
    evaluator: EvaluatorIdentity
    source_policy: PrivateObject
    permission: Permission


class PublicCandidateManifest(StrictModel):
    schema_version: Literal[2]
    record_kind: Literal["pre-recording-candidates"]
    phase: Literal["offline-preparation"]
    corpus_id: Identifier
    created_at: ManifestTimestamp
    evidence_class: Literal["synthetic", "public-derived-declaration"]
    storage_profile_id: Identifier
    storage_owner_id: Identifier
    purpose: Purpose
    retention: Retention
    publication: PublicationRules
    candidates: list[PublicCandidate] = Field(min_length=1, max_length=1000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer.")
        return value


@dataclass(frozen=True)
class PublicDeclarationPolicy:
    """Independent caller configuration, never parsed from declaration JSON.

    The reference and digest identify an independently reviewed decision, not
    its authenticity. The caller must supply actual current rights and time.
    """

    admission: AdmissionPolicy
    reviewed_manifest_sha256: str
    approval_reference: PrivateObject
    rights_status: RightsStatus
    checked_at: datetime


class PublicDeclarationError(ValueError):
    """Only a fixed safe code crosses the public validation boundary."""

    def __init__(self, code: PublicDeclarationCode):
        self.code = code
        super().__init__(code)


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware representable instant is required.")
    return value.astimezone(UTC)


def _identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER.fullmatch(value) is not None


def _approved_ids(value: object) -> bool:
    return (
        type(value) is frozenset
        and 1 <= len(value) <= 32
        and all(_identifier(item) for item in value)
    )


def _current_policy(policy: PublicDeclarationPolicy) -> PublicDeclarationPolicy:
    """Revalidate current values, including mutable Pydantic reference fields."""
    try:
        if type(policy) is not PublicDeclarationPolicy:
            raise ValueError("Invalid policy record.")
        admission = policy.admission
        if type(admission) is not AdmissionPolicy:
            raise ValueError("Invalid admission record.")
        processor = admission.processor_id
        processors = admission.approved_processors
        storage = admission.approved_storage_profiles
        purpose = admission.purpose
        digest = policy.reviewed_manifest_sha256
        status = policy.rights_status
        if (
            not _identifier(processor)
            or not _approved_ids(processors)
            or not _approved_ids(storage)
            or type(purpose) is not str
            or purpose not in _PURPOSES
            or type(digest) is not str
            or _SHA256.fullmatch(digest) is None
            or type(status) is not str
            or status not in {"current", "revoked", "missing"}
            or type(policy.approval_reference) is not PrivateObject
        ):
            raise ValueError("Invalid policy values.")
        # Passing an existing model directly would bypass instance revalidation.
        # A fresh mapping retains missing/extra/current fields for strict checking.
        reference = PrivateObject.model_validate(dict(policy.approval_reference))
        checked = _utc(policy.checked_at)
        return PublicDeclarationPolicy(
            admission=AdmissionPolicy(processor, processors, storage, purpose),
            reviewed_manifest_sha256=digest,
            approval_reference=reference,
            rights_status=status,
            checked_at=checked,
        )
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise PublicDeclarationError("invalid-policy") from None


def _unique_members(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON member.")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("Nonfinite JSON value.")


def _decode(raw: bytes | str) -> tuple[bytes, PublicCandidateManifest]:
    if type(raw) not in {bytes, str}:
        raise PublicDeclarationError("invalid-manifest")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise PublicDeclarationError("manifest-too-large")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    except UnicodeError:
        raise PublicDeclarationError("invalid-manifest") from None
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise PublicDeclarationError("manifest-too-large")
    try:
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_members,
            parse_constant=_nonfinite,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise PublicDeclarationError("invalid-manifest") from None
    if type(value) is not dict or type(value.get("schema_version")) is not int:
        raise PublicDeclarationError("invalid-manifest")
    if value["schema_version"] != 2:
        raise PublicDeclarationError("unsupported-version")
    if type(value.get("record_kind")) is not str:
        raise PublicDeclarationError("invalid-manifest")
    if value["record_kind"] != "pre-recording-candidates":
        raise PublicDeclarationError("unsupported-record-kind")
    try:
        manifest = PublicCandidateManifest.model_validate(value)
        # UTC conversion also rejects otherwise parseable offset/year overflow.
        _utc(manifest.created_at)
        _utc(manifest.retention.review_at)
        _utc(manifest.retention.delete_after)
        for candidate in manifest.candidates:
            for instant in (
                candidate.permission.approved_at,
                candidate.permission.valid_from,
                candidate.permission.valid_until,
            ):
                _utc(instant)
    except (ValidationError, ValueError, TypeError, OverflowError, RecursionError):
        raise PublicDeclarationError("invalid-manifest") from None
    return encoded, manifest


def _unique_candidates(manifest: PublicCandidateManifest) -> None:
    ids: set[str] = set()
    rows: set[tuple[str, str, str, str]] = set()
    for candidate in manifest.candidates:
        if candidate.candidate_id in ids:
            raise PublicDeclarationError("duplicate-candidate-id")
        ids.add(candidate.candidate_id)
        row = (
            candidate.dataset.source_id,
            candidate.dataset.revision,
            candidate.dataset.artifact.sha256,
            candidate.row.sha256,
        )
        if row in rows:
            raise PublicDeclarationError("duplicate-row-identity")
        rows.add(row)


def _permission_checks(
    manifest: PublicCandidateManifest, admission: AdmissionPolicy, now: datetime
) -> None:
    if _utc(manifest.created_at) > now:
        raise PublicDeclarationError("manifest-from-future")
    if admission.processor_id not in admission.approved_processors:
        raise PublicDeclarationError("processor-not-approved")
    if manifest.storage_profile_id not in admission.approved_storage_profiles:
        raise PublicDeclarationError("storage-not-approved")
    if manifest.purpose != admission.purpose:
        raise PublicDeclarationError("purpose-mismatch")
    if _utc(manifest.retention.delete_after) <= now:
        raise PublicDeclarationError("retention-expired")
    if _utc(manifest.retention.review_at) <= now:
        raise PublicDeclarationError("retention-review-overdue")
    for candidate in manifest.candidates:
        permission = candidate.permission
        if _utc(permission.approved_at) > now or _utc(permission.valid_from) > now:
            raise PublicDeclarationError("permission-not-active")
        if _utc(permission.valid_until) <= now:
            raise PublicDeclarationError("permission-expired")
        if _utc(manifest.retention.delete_after) > _utc(permission.valid_until):
            raise PublicDeclarationError("retention-exceeds-permission")
        if admission.processor_id not in permission.allowed_processors:
            raise PublicDeclarationError("processor-not-permitted")
        if admission.purpose not in permission.allowed_purposes:
            raise PublicDeclarationError("purpose-not-permitted")


def validate_public_candidate_manifest(
    raw: bytes | str, *, policy: PublicDeclarationPolicy, now: datetime
) -> PublicCandidateManifest:
    """Validate supplied metadata only; no reference resolution or external I/O.

    The caller independently authorizes current rights, storage and processors.
    Reuse requires a fresh authoritative snapshot; this result is not a token.
    """
    try:
        current = _utc(now)
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise PublicDeclarationError("invalid-validation-time") from None
    trusted = _current_policy(policy)
    encoded, manifest = _decode(raw)
    _unique_candidates(manifest)
    if hashlib.sha256(encoded).hexdigest() != trusted.reviewed_manifest_sha256:
        raise PublicDeclarationError("declaration-not-reviewed")
    if trusted.checked_at != current:
        raise PublicDeclarationError("policy-not-current")
    if trusted.rights_status == "missing":
        raise PublicDeclarationError("rights-missing")
    if trusted.rights_status == "revoked":
        raise PublicDeclarationError("rights-revoked")
    _permission_checks(manifest, trusted.admission, current)
    return manifest
