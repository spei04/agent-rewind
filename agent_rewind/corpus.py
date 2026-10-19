"""Offline, fail-closed contracts for private corpus admission.

Validation checks declared permissions against caller-owned policy. It neither
establishes legal authority nor reads, uploads, executes or publishes content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, ValidationError, field_validator, model_validator

from .models import StrictModel, valid_path

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")]
RunIdentifier = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
Purpose = Literal["debugging", "intervention-screening", "independent-confirmation"]
MAX_MANIFEST_BYTES = 1024 * 1024


class PrivateObject(StrictModel):
    """A relative key within the separately approved storage profile; never a URL."""

    path: str = Field(min_length=1, max_length=512)
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def normalized_path(cls, value: str) -> str:
        if re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("Object paths cannot contain control characters.")
        return valid_path(value)


class Permission(StrictModel):
    status: Literal["approved"]
    rights_owner_id: Identifier
    approved_by: Identifier
    approved_at: AwareDatetime
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    evidence: PrivateObject
    allowed_processors: list[Identifier] = Field(min_length=1, max_length=32)
    allowed_purposes: list[Purpose] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def coherent_permission(self) -> Permission:
        if self.valid_from >= self.valid_until:
            raise ValueError("Permission interval must be positive.")
        if len(set(self.allowed_processors)) != len(self.allowed_processors):
            raise ValueError("Duplicate allowed processors.")
        if len(set(self.allowed_purposes)) != len(self.allowed_purposes):
            raise ValueError("Duplicate allowed purposes.")
        return self


class SourceIdentity(StrictModel):
    source_id: Identifier
    revision: Revision
    artifact: PrivateObject


class EvaluatorIdentity(StrictModel):
    evaluator_id: Identifier
    revision: Revision
    artifact: PrivateObject
    command_sha256: Sha256
    image_digest: Sha256


class CorpusTask(StrictModel):
    task_id: Identifier
    workflow_id: Literal["manual-action-recovery", "automatic-intervention-evaluation"]
    run_ids: list[RunIdentifier] = Field(min_length=1, max_length=100)
    source: SourceIdentity
    evaluator: EvaluatorIdentity
    permission: Permission


class Retention(StrictModel):
    owner_id: Identifier
    review_at: AwareDatetime
    delete_after: AwareDatetime

    @model_validator(mode="after")
    def review_before_deletion(self) -> Retention:
        if self.review_at >= self.delete_after:
            raise ValueError("Retention review must precede deletion.")
        return self


class PublicationRules(StrictModel):
    raw_content: Literal["forbidden"]
    aggregates: Literal["separate-review-required"]
    redaction_policy: PrivateObject


class CorpusManifest(StrictModel):
    schema_version: Literal[1]
    corpus_id: Identifier
    created_at: AwareDatetime
    evidence_class: Literal["synthetic", "customer-permitted"]
    storage_profile_id: Identifier
    storage_owner_id: Identifier
    purpose: Purpose
    retention: Retention
    publication: PublicationRules
    tasks: list[CorpusTask] = Field(min_length=1, max_length=1000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer.")
        return value


@dataclass(frozen=True)
class AdmissionPolicy:
    """Trusted caller configuration, never an allowlist taken from the manifest.

    Processor IDs identify approved account/region/retention configurations, not
    merely a vendor name. Storage profiles identify reviewed private locations.
    """

    processor_id: str
    approved_processors: frozenset[str]
    approved_storage_profiles: frozenset[str]
    purpose: Purpose


class CorpusManifestError(ValueError):
    """Stable safe code without private field values or document contents."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _unique_json_members(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in values:
        if name in result:
            raise ValueError("Duplicate JSON member.")
        result[name] = value
    return result


def validate_corpus_manifest(
    raw: bytes | str, *, policy: AdmissionPolicy, now: datetime
) -> CorpusManifest:
    """Validate immediately before admission or reuse; no external side effects.

    This function is not connected to current run APIs. Consumers must obtain
    authoritative policy and approval records separately and enforce them when
    they load content or dispatch a model call.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise CorpusManifestError("invalid-validation-time")
    try:
        size = len(raw if isinstance(raw, bytes) else raw.encode())
    except UnicodeError:
        raise CorpusManifestError("invalid-manifest") from None
    if size > MAX_MANIFEST_BYTES:
        raise CorpusManifestError("manifest-too-large")
    try:
        json.loads(raw, object_pairs_hook=_unique_json_members)
        manifest = CorpusManifest.model_validate_json(raw)
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise CorpusManifestError("invalid-manifest") from None
    if manifest.created_at > now:
        raise CorpusManifestError("manifest-from-future")
    if policy.processor_id not in policy.approved_processors:
        raise CorpusManifestError("processor-not-approved")
    if manifest.storage_profile_id not in policy.approved_storage_profiles:
        raise CorpusManifestError("storage-not-approved")
    if manifest.purpose != policy.purpose:
        raise CorpusManifestError("purpose-mismatch")
    if manifest.retention.delete_after <= now:
        raise CorpusManifestError("retention-expired")
    if manifest.retention.review_at <= now:
        raise CorpusManifestError("retention-review-overdue")
    task_ids: set[str] = set()
    run_ids: set[str] = set()
    for task in manifest.tasks:
        if task.task_id in task_ids:
            raise CorpusManifestError("duplicate-task-id")
        task_ids.add(task.task_id)
        for run_id in task.run_ids:
            if run_id in run_ids:
                raise CorpusManifestError("duplicate-run-id")
            run_ids.add(run_id)
        permission = task.permission
        if permission.approved_at > now or permission.valid_from > now:
            raise CorpusManifestError("permission-not-active")
        if permission.valid_until <= now:
            raise CorpusManifestError("permission-expired")
        if manifest.retention.delete_after > permission.valid_until:
            raise CorpusManifestError("retention-exceeds-permission")
        if policy.processor_id not in permission.allowed_processors:
            raise CorpusManifestError("processor-not-permitted")
        if policy.purpose not in permission.allowed_purposes:
            raise CorpusManifestError("purpose-not-permitted")
    return manifest
