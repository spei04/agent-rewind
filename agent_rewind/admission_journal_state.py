"""Bounded admission journal identities, immutable snapshots and phase grammar.

These values are diagnostic evidence, never SQL authority or an upload receipt.
The retried task is required to restore a snapshot through the shared validator.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

from .admission_configuration import NativeConfiguration
from .admission_envelope import (
    ArtifactBinding,
    OriginCorrelation,
    PreparedAdmission,
    restore_admission,
)
from .admission_request import (
    MAX_CONFIG_BYTES,
    AdmissionPreparationError,
    CanonicalIntent,
    bounded_canonical,
    decode_object,
)
from .artifact_metadata import (
    ArtifactError,
    ArtifactObject,
    digest_value,
    identifier,
    object_locator,
)
from .models import canonical
from .request_identity import VerifiedPrincipal

MAX_BINDING_BYTES = 4096
MAX_CHILD_BYTES = 128 * 1024
MAX_POLICY_BYTES = 16 * 1024
MAX_ATTEMPT_RECORDS = 64
ROLES = ("task", "admission_config", "payload")


def invalid() -> NoReturn:
    raise ArtifactError("admission_journal_invalid") from None


def encode(value: Any, limit: int) -> bytes:
    try:
        encoded = bounded_canonical(value, limit=limit, limit_code="admission_binding_invalid")
        # The strict decoder excludes duplicate/float/nonfinite/oversized integers.
        decode_object(encoded, limit=limit, limit_code="admission_binding_invalid")
        return encoded
    except AdmissionPreparationError:
        invalid()


@dataclass(frozen=True)
class JournalIdentity:
    organization_id: str
    project_id: str
    principal_id: str
    client_operation_id: str
    key_hash: str
    request_digest: str

    def __post_init__(self) -> None:
        identifier(self.organization_id)
        identifier(self.project_id)
        identifier(self.client_operation_id)
        VerifiedPrincipal(self.principal_id)
        digest_value(self.key_hash)
        digest_value(self.request_digest)
        names = (*self.locators, *self.children)
        if len(set(names)) != 4:
            invalid()

    @property
    def scope(self) -> dict[str, str]:
        return dict(
            organization_id=self.organization_id,
            project_id=self.project_id,
            principal_id=self.principal_id,
            kind="run",
        )

    @property
    def client(self) -> dict[str, Any]:
        return dict(
            schema=1,
            purpose="admission-client",
            scope=self.scope,
            client_operation_id=self.client_operation_id,
        )

    @property
    def key(self) -> dict[str, Any]:
        return dict(schema=1, purpose="admission-key", scope=self.scope, key_hash=self.key_hash)

    @staticmethod
    def _name(value: dict[str, Any]) -> str:
        return hashlib.sha256(canonical(value)).hexdigest()[:32]

    @property
    def locators(self) -> tuple[str, str]:
        return self._name(self.client), self._name(self.key)

    @property
    def children(self) -> tuple[str, str]:
        def attempt(index: int) -> str:
            return self._name(
                dict(schema=1, purpose="admission-attempt", client=self.client, attempt=index)
            )

        return attempt(0), attempt(1)

    def binding(self, origin: OriginCorrelation) -> dict[str, Any]:
        if type(origin) is not OriginCorrelation:
            invalid()
        return dict(
            schema=1,
            purpose="admission-binding",
            client=self.client,
            key=self.key,
            request_digest=self.request_digest,
            origin=origin.correlation_id,
            locators=list(self.locators),
            children=list(self.children),
        )

    def validate_binding(self, value: dict[str, Any]) -> bytes:
        encoded = encode(value, MAX_BINDING_BYTES)
        try:
            origin = OriginCorrelation(value["origin"])
        except (KeyError, ValueError, TypeError):
            invalid()
        if encoded != encode(self.binding(origin), MAX_BINDING_BYTES):
            invalid()
        return encoded


def descriptor(value: ArtifactObject) -> dict[str, Any]:
    if type(value) is not ArtifactObject:
        invalid()
    value.__post_init__()
    return dict(
        id=value.id,
        project_id=value.project_id,
        digest=value.digest,
        locator=value.locator,
        format_version=value.format_version,
        byte_count=value.byte_count,
        created_at=value.created_at.isoformat(),
    )


def metadata(value: Any) -> ArtifactObject:
    if type(value) is not dict or set(value) != {
        "id",
        "project_id",
        "digest",
        "locator",
        "format_version",
        "byte_count",
        "created_at",
    }:
        invalid()
    try:
        created = value["created_at"]
        if type(created) is not str or len(created) > 40:
            invalid()
        result = ArtifactObject(**{**value, "created_at": datetime.fromisoformat(created)})
        if result.locator != object_locator(result.project_id, result.digest):
            invalid()
        if descriptor(result) != value:
            invalid()
        return result
    except (ValueError, TypeError):
        invalid()


@dataclass(frozen=True)
class MetadataCollision:
    """Exact observed same-content descriptor mismatch; not a generic SQL error.

    The coordinator must obtain winner from fresh bounded scoped SQL after an
    acknowledged rollback. Constructing this value alone does not prove that.
    """

    expected: ArtifactObject
    winner: ArtifactObject

    def __post_init__(self) -> None:
        metadata(descriptor(self.expected))
        metadata(descriptor(self.winner))
        if self.expected == self.winner or (
            self.expected.project_id,
            self.expected.digest,
            self.expected.format_version,
        ) != (self.winner.project_id, self.winner.digest, self.winner.format_version):
            invalid()

    def record(self) -> dict[str, Any]:
        return dict(expected=descriptor(self.expected), winner=descriptor(self.winner))


def validate_policy(
    policy: dict[str, Any],
    identity: JournalIdentity,
    task_digest: str,
    configuration: NativeConfiguration,
) -> dict[str, Any]:
    """Validate and detach policy shape/bindings; never establishes actual permission."""
    encode(policy, MAX_POLICY_BYTES)
    if type(policy) is not dict or set(policy) != {
        "schema",
        "organization_id",
        "project_id",
        "principal_id",
        "request_digest",
        "task_digest",
        "configuration_digest",
        "permitted_processor_profile",
        "version",
        "state",
    }:
        invalid()
    expected = dict(
        schema=1,
        organization_id=identity.organization_id,
        project_id=identity.project_id,
        principal_id=identity.principal_id,
        request_digest=identity.request_digest,
        task_digest=task_digest,
        configuration_digest=configuration.digest,
        permitted_processor_profile=configuration.processor_profile,
    )
    if (
        type(policy["schema"]) is not int
        or any(policy[k] != v for k, v in expected.items())
        or type(policy["version"]) is not str
        or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", policy["version"]) is None
        or type(policy["state"]) is not dict
    ):
        invalid()
    return decode_object(
        encode(policy, MAX_POLICY_BYTES),
        limit=MAX_POLICY_BYTES,
        limit_code="admission_binding_invalid",
    )


@dataclass(frozen=True)
class AttemptSnapshot:
    encoded: bytes

    def data(self) -> dict[str, Any]:
        return decode_object(
            self.encoded, limit=MAX_CHILD_BYTES, limit_code="admission_binding_invalid"
        )

    @classmethod
    def validate(
        cls, value: dict[str, Any], identity: JournalIdentity, binding: bytes, index: int
    ) -> AttemptSnapshot:
        encoded = encode(value, MAX_CHILD_BYTES)
        value = json.loads(encoded)
        if set(value) != {
            "schema",
            "purpose",
            "binding",
            "index",
            "predecessor",
            "operation_id",
            "job_id",
            "task_digest",
            "configuration_digest",
            "envelope_digest",
            "configuration",
            "policy",
            "descriptors",
        }:
            invalid()
        if (
            type(value["schema"]) is not int
            or value["schema"] != 1
            or value["purpose"] != "admission-attempt"
            or type(value["index"]) is not int
            or value["index"] != index
            or canonical(value["binding"]) != binding
        ):
            invalid()
        identifier(value["operation_id"])
        identifier(value["job_id"])
        for name in ("task_digest", "configuration_digest", "envelope_digest"):
            digest_value(value[name])
        config_bytes = encode(value["configuration"], MAX_CONFIG_BYTES)
        config = NativeConfiguration(config_bytes, expected_digest=value["configuration_digest"])
        validate_policy(value["policy"], identity, value["task_digest"], config)
        items = value["descriptors"]
        if type(items) is not dict or set(items) != set(ROLES):
            invalid()
        objects = {role: metadata(items[role]) for role in ROLES}
        if len({obj.id for obj in objects.values()}) != 3:
            invalid()
        for role, digest, limit in (
            ("task", value["task_digest"], 8 * 1024 * 1024),
            ("admission_config", config.digest, MAX_CONFIG_BYTES),
            ("payload", value["envelope_digest"], 4096),
        ):
            obj = objects[role]
            if (
                obj.project_id != identity.project_id
                or obj.digest != digest
                or obj.byte_count > limit
            ):
                invalid()
        if objects["admission_config"].byte_count != len(config_bytes):
            invalid()
        predecessor = value["predecessor"]
        if index == 0:
            if predecessor is not None:
                invalid()
        elif (
            type(predecessor) is not dict
            or set(predecessor) != {"attempt_id", "rollback_acknowledged", "collision"}
            or predecessor["attempt_id"] != identity.children[0]
            or predecessor["rollback_acknowledged"] is not True
        ):
            invalid()
        else:
            collision = predecessor["collision"]
            if type(collision) is not dict or set(collision) != {"expected", "winner"}:
                invalid()
            MetadataCollision(metadata(collision["expected"]), metadata(collision["winner"]))
        return cls(encoded)

    def restore(self, identity: JournalIdentity, intent: CanonicalIntent) -> PreparedAdmission:
        value = self.data()
        if (
            type(intent) is not CanonicalIntent
            or intent.client_operation_id != identity.client_operation_id
            or intent.request_digest != identity.request_digest
            or intent.task_digest != value["task_digest"]
        ):
            invalid()
        config_bytes = canonical(value["configuration"])
        kwargs = dict(project_id=identity.project_id, job_id=value["job_id"])
        prepared = restore_admission(
            intent,
            frozen_configuration=config_bytes,
            expected_configuration_digest=value["configuration_digest"],
            expected_envelope_digest=value["envelope_digest"],
            origin=OriginCorrelation(value["binding"]["origin"]),
            task_binding=ArtifactBinding(
                **kwargs,
                role="task",
                descriptor=metadata(value["descriptors"]["task"]),
                plaintext=intent.task_bytes,
            ),
            configuration_binding=ArtifactBinding(
                **kwargs,
                role="admission_config",
                descriptor=metadata(value["descriptors"]["admission_config"]),
                plaintext=config_bytes,
            ),
            **kwargs,
        )
        prepared.bind_payload(metadata(value["descriptors"]["payload"]))
        return prepared


@dataclass(frozen=True)
class WorkState:
    verified: tuple[str, ...]
    pending_role: str | None
    unknown_work: bool
    write_requests: int
    read_requests: int
    logical_writes: int
    commit_pending: bool
    commit_status: str | None


def work_state(snapshot: AttemptSnapshot, records: list[dict[str, Any]]) -> WorkState:
    if len(records) > MAX_ATTEMPT_RECORDS:
        invalid()
    value = snapshot.data()
    verified: set[str] = set()
    pending = None
    unknown = False
    reads = writes = logical = 0
    commit = False
    status = None
    for sequence, record in enumerate(records):
        if (
            type(record) is not dict
            or set(record) != {"sequence", "kind", "data"}
            or type(record["sequence"]) is not int
            or record["sequence"] != sequence
        ):
            invalid()
        kind, data = record["kind"], record["data"]
        if type(kind) is not str or type(data) is not dict:
            invalid()
        if kind.startswith("upload_"):
            if commit or data.get("role") not in ROLES:
                invalid()
            role = data["role"]
            if kind in {"upload_started", "upload_unknown"}:
                if (
                    set(data) != {"role", "object_id", "backend_work"}
                    or data["object_id"] != value["descriptors"][role]["id"]
                    or data["backend_work"] != "UNKNOWN"
                ):
                    invalid()
                if kind == "upload_started":
                    unknown = unknown or pending is not None
                    pending = role
                    verified.discard(role)
                else:
                    if pending != role:
                        invalid()
                    unknown, pending = True, None
            elif kind == "upload_verified":
                if (
                    pending != role
                    or set(data)
                    != {
                        "role",
                        "object",
                        "logical_writes",
                        "write_requests",
                        "read_requests",
                        "plaintext_bytes",
                        "ciphertext_bytes",
                        "cache_hit",
                    }
                    or data["object"] != value["descriptors"][role]
                    or type(data["cache_hit"]) is not bool
                ):
                    invalid()
                for name in (
                    "logical_writes",
                    "write_requests",
                    "read_requests",
                    "plaintext_bytes",
                    "ciphertext_bytes",
                ):
                    if type(data[name]) is not int or not 0 <= data[name] <= 2**63 - 1:
                        invalid()
                if (
                    data["logical_writes"] != 1
                    or data["plaintext_bytes"] != value["descriptors"][role]["byte_count"]
                ):
                    invalid()
                metadata(data["object"])
                writes += data["write_requests"]
                reads += data["read_requests"]
                logical += data["logical_writes"]
                if max(writes, reads, logical) > 2**63 - 1:
                    invalid()
                verified.add(role)
                pending = None
            else:
                invalid()
        else:
            expected = dict(
                operation_id=value["operation_id"],
                job_id=value["job_id"],
                sql_commit="CONFIRMED" if kind == "commit_confirmed" else "UNKNOWN",
            )
            if data != expected:
                invalid()
            if kind == "commit_pending":
                if commit or pending is not None or verified != set(ROLES):
                    invalid()
                commit, status = True, "PENDING"
            elif kind in {"commit_unknown", "commit_confirmed"}:
                if (
                    not commit
                    or status == "CONFIRMED"
                    or (kind == "commit_unknown" and status == "UNKNOWN")
                ):
                    invalid()
                status = "CONFIRMED" if kind == "commit_confirmed" else "UNKNOWN"
            else:
                invalid()
    return WorkState(
        tuple(sorted(verified)),
        pending,
        unknown or pending is not None,
        writes,
        reads,
        logical,
        commit,
        status,
    )
