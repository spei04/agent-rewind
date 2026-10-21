"""Pure schema-2 admission envelope and prospective scoped artifact bindings.

No binding here is an upload receipt, permission, committed job or operation.
P3 must verify real storage receipts and the same-project job/ref associations in
its one publication transaction. Neither content hashes nor these types replace
fresh authority, both operation identities, or commit acknowledgment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal, NoReturn

from .admission_configuration import NativeConfiguration, NativeRegistry
from .admission_request import (
    MAX_CONFIG_BYTES,
    MAX_TASK_BYTES,
    AdmissionPreparationError,
    CanonicalIntent,
    bounded_canonical,
)
from .artifact_metadata import ArtifactError, ArtifactObject, identifier, object_locator

MAX_ENVELOPE_BYTES = 4096
BindingRole = Literal["task", "admission_config", "payload"]
_LIMITS: dict[str, int] = {
    "task": MAX_TASK_BYTES,
    "admission_config": MAX_CONFIG_BYTES,
    "payload": MAX_ENVELOPE_BYTES,
}


def _invalid() -> NoReturn:
    raise AdmissionPreparationError("admission_binding_invalid") from None


def _id(value: str) -> None:
    try:
        identifier(value)
    except ArtifactError:
        _invalid()


@dataclass(frozen=True)
class OriginCorrelation:
    """Server-generated first-attempt ID supplied by a trusted internal caller.

    Shape validation cannot establish provenance. HTTP/P3 must never build this
    value from client input and must retain the first committed operation's
    origin on replay. A later GET/error still has its own fresh request ID.
    """

    correlation_id: str

    def __post_init__(self) -> None:
        _id(self.correlation_id)


@dataclass(frozen=True, init=False)
class ArtifactBinding:
    """Frozen intended job-owned metadata/plaintext association; no I/O evidence.

    New admission objects use a project-scoped format-1 locator. Object IDs are
    32 hex characters; content references/digests are 64. Existing immutable
    object descriptors may be reused, but callers cannot relabel project/owner
    or role and treat that as a persisted scoped reference.
    """

    project_id: str
    job_id: str
    role: BindingRole
    descriptor: ArtifactObject
    plaintext: bytes = field(repr=False)

    def __init__(
        self,
        *,
        project_id: str,
        job_id: str,
        role: BindingRole,
        descriptor: ArtifactObject,
        plaintext: bytes,
    ):
        _id(project_id)
        _id(job_id)
        if (
            type(role) is not str
            or role not in _LIMITS
            or type(descriptor) is not ArtifactObject
            or type(plaintext) is not bytes
            or len(plaintext) > _LIMITS[role]
        ):
            _invalid()
        try:
            # Revalidate/copy all seven metadata fields; never retain mutable
            # structural descriptors or claim a descriptor is enduring authority.
            frozen = ArtifactObject(
                descriptor.id,
                descriptor.project_id,
                descriptor.digest,
                descriptor.locator,
                descriptor.format_version,
                descriptor.byte_count,
                descriptor.created_at,
            )
        except (ArtifactError, TypeError, ValueError):
            _invalid()
        if (
            frozen.project_id != project_id
            or frozen.locator != object_locator(project_id, frozen.digest)
            or frozen.byte_count != len(plaintext)
            or frozen.digest != hashlib.sha256(plaintext).hexdigest()
        ):
            _invalid()
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "job_id", job_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "descriptor", frozen)
        object.__setattr__(self, "plaintext", plaintext)


@dataclass(frozen=True, init=False)
class PreparedAdmission:
    """Consistent new-operation intent/envelope, awaiting P3's real publication."""

    project_id: str
    job_id: str
    origin: OriginCorrelation
    intent: CanonicalIntent
    configuration: NativeConfiguration
    task_binding: ArtifactBinding
    configuration_binding: ArtifactBinding
    envelope_bytes: bytes = field(repr=False)

    def __init__(
        self,
        intent: CanonicalIntent,
        registry: NativeRegistry,
        *,
        project_id: str,
        job_id: str,
        origin: OriginCorrelation,
        task_binding: ArtifactBinding,
        configuration_binding: ArtifactBinding,
        permitted_processor_profile: str | None,
    ):
        _id(project_id)
        _id(job_id)
        if (
            type(intent) is not CanonicalIntent
            or type(registry) is not NativeRegistry
            or type(origin) is not OriginCorrelation
            or type(task_binding) is not ArtifactBinding
            or type(configuration_binding) is not ArtifactBinding
        ):
            _invalid()
        # This entry point is only for a genuinely new identity, after P3 has
        # checked both authorized recovery keys. Registry lookup is pure.
        task = json.loads(intent.task_bytes)
        configuration = registry.resolve_new(
            intent.adapter_config_id,
            task["image"],
            permitted_processor_profile=permitted_processor_profile,
        )
        for binding, role, content in (
            (task_binding, "task", intent.task_bytes),
            (configuration_binding, "admission_config", configuration.canonical_bytes),
        ):
            if (
                binding.project_id != project_id
                or binding.job_id != job_id
                or binding.role != role
                or binding.plaintext != content
            ):
                _invalid()
        if (
            task_binding.descriptor.digest != intent.task_digest
            or configuration_binding.descriptor.digest != configuration.digest
            or task_binding.descriptor.id == configuration_binding.descriptor.id
        ):
            _invalid()
        envelope = {
            "schema": 2,
            "kind": "native-run",
            "project_id": project_id,
            "client_operation_id": intent.client_operation_id,
            "request_digest": intent.request_digest,
            "task_ref": task_binding.descriptor.digest,
            "task_digest": intent.task_digest,
            "seed": intent.seed,
            "budget_microusd": intent.budget_microusd,
            "execution_config_ref": configuration_binding.descriptor.digest,
            "execution_config_digest": configuration.digest,
        }
        encoded = bounded_canonical(
            envelope, limit=MAX_ENVELOPE_BYTES, limit_code="admission_binding_invalid"
        )
        for name, value in (
            ("project_id", project_id),
            ("job_id", job_id),
            ("origin", origin),
            ("intent", intent),
            ("configuration", configuration),
            ("task_binding", task_binding),
            ("configuration_binding", configuration_binding),
            ("envelope_bytes", encoded),
        ):
            object.__setattr__(self, name, value)

    @property
    def envelope_digest(self) -> str:
        return hashlib.sha256(self.envelope_bytes).hexdigest()

    def bind_payload(self, descriptor: ArtifactObject) -> ArtifactBinding:
        """Check the intended payload descriptor without uploading/publishing it."""
        if type(descriptor) is not ArtifactObject:
            _invalid()
        if descriptor.id in {
            self.task_binding.descriptor.id,
            self.configuration_binding.descriptor.id,
        }:
            _invalid()
        return ArtifactBinding(
            project_id=self.project_id,
            job_id=self.job_id,
            role="payload",
            descriptor=descriptor,
            plaintext=self.envelope_bytes,
        )


def prepare_admission(
    intent: CanonicalIntent,
    registry: NativeRegistry,
    *,
    project_id: str,
    job_id: str,
    origin: OriginCorrelation,
    task_binding: ArtifactBinding,
    configuration_binding: ArtifactBinding,
    permitted_processor_profile: str | None,
) -> PreparedAdmission:
    return PreparedAdmission(
        intent,
        registry,
        project_id=project_id,
        job_id=job_id,
        origin=origin,
        task_binding=task_binding,
        configuration_binding=configuration_binding,
        permitted_processor_profile=permitted_processor_profile,
    )
