"""Bounded metadata selection and same-Connection admission publication.

The coordinator owns current exclusion, actual storage calls/receipts, rollback
and acknowledgment. No connection, journal, storage, provider or retry is owned
here. The old 13-column jobs Table remains unchanged for historical hashing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from .admission_envelope import ArtifactBinding, PreparedAdmission
from .admission_journal_state import MetadataCollision
from .admission_records import StoredOperation, write_transaction
from .admission_repository import AdmissionRepository
from .admission_transaction import AdmissionError
from .artifact_metadata import (
    ArtifactError,
    ArtifactObject,
    find_object_candidate,
    object_locator,
    record_verified,
    register_ref,
)
from .artifact_storage import ObjectWriteResult
from .database import audit
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_repositories import ProjectContext


class PublicationCollision(AdmissionError):
    """Only a compared valid metadata-stage mismatch, never generic IntegrityError.

    A retry still needs acknowledged rollback, successful SQL release, fresh
    dual-identity lookup and the same unique winner proven again on fresh SQL.
    """

    def __init__(self, expected: ArtifactObject, winner: ArtifactObject):
        super().__init__("dependency_unavailable")
        self.expected, self.winner = expected, winner


def compatible(expected: ArtifactObject, candidate: ArtifactObject) -> None:
    candidate.__post_init__()
    if (
        candidate.project_id != expected.project_id
        or candidate.digest != expected.digest
        or candidate.format_version != 1
        or candidate.byte_count != expected.byte_count
        or candidate.locator != object_locator(expected.project_id, expected.digest)
    ):
        raise AdmissionError("dependency_unavailable")


def select_descriptor(connection: Connection, prospective: ArtifactObject) -> ArtifactObject:
    """After caller authorization; prospective ID collisions cannot hide by digest."""
    candidate = find_object_candidate(connection, prospective)
    if candidate is None:
        return prospective
    compatible(prospective, candidate)
    return candidate


def _record(connection: Connection, descriptor: ArtifactObject) -> None:
    try:
        record_verified(connection, descriptor)
    except ArtifactError as error:
        if str(error) != "artifact_metadata_conflict":
            raise
        candidate = find_object_candidate(connection, descriptor)
        if candidate is None or candidate == descriptor:
            raise AdmissionError("dependency_unavailable") from None
        compatible(descriptor, candidate)
        raise PublicationCollision(descriptor, candidate) from None


def prove_replacement(
    connection: Connection,
    prepared: PreparedAdmission,
    payload: ArtifactBinding,
    collision: PublicationCollision,
) -> tuple[PreparedAdmission, ArtifactBinding, MetadataCollision]:
    """Fresh scoped SQL proof after clean rollback and an absent dual identity.

    Every changed descriptor comes from the bounded candidate query. The original
    actual metadata-stage winner must still be exact; malformed/two-row/foreign
    candidates and unrelated driver failures can never authorize another attempt.
    """
    bindings = (prepared.task_binding, prepared.configuration_binding, payload)
    if collision.expected not in tuple(item.descriptor for item in bindings):
        raise AdmissionError("dependency_unavailable")
    winner = find_object_candidate(connection, collision.expected)
    if winner != collision.winner or winner == collision.expected:
        raise AdmissionError("dependency_unavailable")
    compatible(collision.expected, winner)
    replacements = [
        ArtifactBinding(
            project_id=item.project_id,
            job_id=item.job_id,
            role=item.role,
            descriptor=select_descriptor(connection, item.descriptor),
            plaintext=item.plaintext,
        )
        for item in bindings
    ]
    result = PreparedAdmission(
        prepared.intent,
        prepared.configuration,
        project_id=prepared.project_id,
        job_id=prepared.job_id,
        origin=prepared.origin,
        task_binding=replacements[0],
        configuration_binding=replacements[1],
    )
    return (
        result,
        result.bind_payload(replacements[2].descriptor),
        MetadataCollision(collision.expected, winner),
    )


def validate_receipts(
    bindings: tuple[ArtifactBinding, ...], receipts: tuple[ObjectWriteResult, ...]
) -> None:
    """Validate exact freshly returned adapter receipts before journaling or SQL."""
    if len(bindings) != len(receipts) or not 1 <= len(bindings) <= 3:
        raise AdmissionError("dependency_unavailable")
    for binding, receipt in zip(bindings, receipts, strict=True):
        if (
            type(receipt) is not ObjectWriteResult
            or receipt.object != binding.descriptor
            or receipt.logical_writes != 1
            or receipt.plaintext_bytes != binding.descriptor.byte_count
            or type(receipt.cache_hit) is not bool
            or any(
                type(count) is not int or not 0 <= count <= 2**63 - 1
                for count in (
                    receipt.logical_writes,
                    receipt.write_requests,
                    receipt.read_requests,
                    receipt.plaintext_bytes,
                    receipt.ciphertext_bytes,
                )
            )
        ):
            raise AdmissionError("dependency_unavailable")


def publish_rows(
    connection: Connection,
    authority: RequestAuthority,
    repository: AdmissionRepository,
    principal: VerifiedPrincipal,
    context: ProjectContext,
    *,
    operation_id: str,
    key_hash: str,
    prepared: PreparedAdmission,
    payload: ArtifactBinding,
    receipts: tuple[ObjectWriteResult, ...],
    created_at: datetime,
) -> StoredOperation:
    """One atomic queued job/scope/refs/operation/alias/fixed audit transaction."""
    write_transaction(connection)
    authority.check(connection, principal, context, "record")
    bindings = (prepared.task_binding, prepared.configuration_binding, payload)
    if prepared.project_id != context.project_id or payload != prepared.bind_payload(
        payload.descriptor
    ):
        raise AdmissionError("dependency_unavailable")
    if len(receipts) != 3:
        raise AdmissionError("dependency_unavailable")
    validate_receipts(bindings, receipts)
    at = created_at.astimezone(UTC)
    # Explicit ar6 insert, including every old and new field. No legacy enqueue,
    # config UPDATE, budget reservation, sequence allocation or dispatch occurs.
    connection.execute(
        text("""
        INSERT INTO jobs
          (id,kind,created,payload,status,owner,lease_until,cancel,budget,reserved,
           result,error,actor,payload_version,execution_config_ref,execution_config_digest)
        VALUES (:id,'run',:created,:payload,'queued',NULL,NULL,false,:budget,0,
                NULL,NULL,:actor,2,:config,:config)
        """),
        dict(
            id=prepared.job_id,
            created=at.timestamp(),
            payload=prepared.envelope_digest,
            budget=prepared.intent.budget_microusd,
            actor=principal.principal_id,
            config=prepared.configuration.digest,
        ),
    )
    connection.execute(
        text(
            "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
            "VALUES('job',:id,:project)"
        ),
        dict(id=prepared.job_id, project=context.project_id),
    )
    for binding in bindings:
        _record(connection, binding.descriptor)
        register_ref(
            connection,
            project_id=context.project_id,
            owner_kind="job",
            owner_id=prepared.job_id,
            role=binding.role,
            artifact_id=binding.descriptor.id,
        )
    operation = repository.insert_operation(
        connection,
        principal,
        context,
        operation_id=operation_id,
        prepared=prepared,
        payload_binding=payload,
        created_at=at,
        retain_until=at + timedelta(days=90),
    )
    repository.bind_alias(
        connection,
        principal,
        context,
        operation_id=operation_id,
        key_hash=key_hash,
        request_digest=prepared.intent.request_digest,
    )
    authority.check(
        connection, principal, context, "record", resource_kind="job", resource_id=prepared.job_id
    )
    connection.execute(
        insert(audit).values(
            id=uuid.uuid4().hex,
            created=at.timestamp(),
            actor=principal.principal_id,
            action="job.create",
            target=prepared.job_id,
        )
    )
    return operation
