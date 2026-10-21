"""Connection-bound admission identity primitives, not a publication coordinator.

The caller owns the transaction, current project/grant/key/job lock hierarchy,
real upload receipts and commit acknowledgment. These methods never commit,
open another connection, resolve configuration, perform I/O or retry a race.
P3 must resolve BOTH identities before any new preparation/upload, then recheck
under its exclusion before atomically publishing jobs, refs, identities and audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, and_, cast, insert, literal, select
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import ColumnElement

from .admission_envelope import ArtifactBinding, PreparedAdmission
from .admission_records import (
    ALIAS_LIMITS,
    ALIASES,
    OPERATION_LIMITS,
    OPERATIONS,
    AdmissionStorageError,
    StoredOperation,
    bounded_columns,
    hexadecimal,
    operation_value,
    principal_value,
    retention,
    storage_errors,
    verify_binding,
    verify_job_configuration,
    write_transaction,
)
from .models import canonical
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import ProjectContext


class AdmissionIdentityConflict(AdmissionStorageError):
    """A compared scoped SQL identity disagrees; not a generic constraint error."""

    def __init__(self) -> None:
        super().__init__("admission_conflict")


@dataclass(frozen=True)
class IdentityResolution:
    operation: StoredOperation | None
    needs_alias: bool


class AdmissionRepository:
    """Fresh same-Connection authority, with no claim of durable authorization.

    get_operation is a named-project read usable by an authorized viewer.
    resolve_identities/bind_alias are creator-principal-bound record actions;
    status reads can never bind aliases or recover another principal's admission.
    """

    def __init__(self, authority: RequestAuthority):
        self.authority = authority

    def _operation(
        self,
        connection: Connection,
        context: ProjectContext,
        predicate: ColumnElement[bool],
    ) -> StoredOperation | None:
        rows = (
            connection.execute(
                select(*bounded_columns(connection, OPERATIONS, OPERATION_LIMITS))
                .where(
                    OPERATIONS.c.project_id == context.project_id,
                    OPERATIONS.c.kind == "run",
                    predicate,
                )
                .limit(2)
            )
            .mappings()
            .all()
        )
        if len(rows) > 1:
            raise AdmissionStorageError("admission_metadata_invalid")
        return operation_value(dict(rows[0])) if rows else None

    def _verify(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        operation: StoredOperation,
        action: str,
    ) -> None:
        self.authority.check(
            connection,
            principal,
            context,
            action,
            resource_kind="job",
            resource_id=operation.job_id,
        )
        configuration = verify_job_configuration(
            connection,
            context=context,
            job_id=operation.job_id,
            payload_version=2,
        )
        if (
            operation.project_id != context.project_id
            or configuration.kind != "run"
            or configuration.digest != operation.execution_config_digest
            or configuration.actor != operation.principal_id
        ):
            raise AdmissionStorageError("admission_metadata_invalid")

    def _alias(
        self,
        connection: Connection,
        context: ProjectContext,
        key_hash: str,
    ) -> dict[str, Any] | None:
        rows = (
            connection.execute(
                select(*bounded_columns(connection, ALIASES, ALIAS_LIMITS))
                .where(
                    ALIASES.c.project_id == context.project_id,
                    ALIASES.c.principal_id == context.principal_id,
                    ALIASES.c.kind == "run",
                    ALIASES.c.key_hash == key_hash,
                )
                .limit(2)
            )
            .mappings()
            .all()
        )
        if len(rows) > 1:
            raise AdmissionStorageError("admission_metadata_invalid")
        if not rows:
            return None
        row = dict(rows[0])
        for name in ("project_id", "operation_id"):
            hexadecimal(row[name], 32)
        for name in ("key_hash", "request_digest"):
            hexadecimal(row[name], 64)
        principal_value(row["principal_id"])
        if (row["project_id"], row["principal_id"], row["kind"], row["key_hash"]) != (
            context.project_id,
            context.principal_id,
            "run",
            key_hash,
        ):
            raise AdmissionStorageError("admission_metadata_invalid")
        return row

    def get_operation(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        *,
        operation_id: str,
    ) -> StoredOperation:
        """Read original accepted identity, not a rendered result or alias capability."""
        hexadecimal(operation_id, 32, input_value=True)
        with storage_errors():
            self.authority.check(connection, principal, context, "read")
            operation = self._operation(connection, context, OPERATIONS.c.id == operation_id)
            if operation is None:
                raise ResourceNotFound()
            self._verify(connection, principal, context, operation, "read")
            self.authority.check(connection, principal, context, "read")
            return operation

    def resolve_identities(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        *,
        client_operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> IdentityResolution:
        """SQL-only original-identity lookup before current config/readiness/storage.

        This preparatory read does not lock a winner or declare a missing identity
        safe to publish. P3 repeats it under its owned publication exclusion.
        """
        hexadecimal(client_operation_id, 32, input_value=True)
        hexadecimal(key_hash, 64, input_value=True)
        hexadecimal(request_digest, 64, input_value=True)
        with storage_errors():
            self.authority.check(connection, principal, context, "record")
            owner = OPERATIONS.c.principal_id == context.principal_id
            by_client = self._operation(
                connection,
                context,
                and_(owner, OPERATIONS.c.client_operation_id == client_operation_id),
            )
            alias = self._alias(connection, context, key_hash)
            by_key = None
            if alias is not None:
                by_key = self._operation(
                    connection,
                    context,
                    and_(owner, OPERATIONS.c.id == alias["operation_id"]),
                )
                if by_key is None or alias["request_digest"] != by_key.request_digest:
                    raise AdmissionStorageError("admission_metadata_invalid")
            if by_client is not None and by_key is not None and by_client != by_key:
                raise AdmissionIdentityConflict()
            operation = by_client or by_key
            if operation is not None:
                if (
                    operation.client_operation_id != client_operation_id
                    or operation.request_digest != request_digest
                    or operation.principal_id != context.principal_id
                ):
                    raise AdmissionIdentityConflict()
                self._verify(connection, principal, context, operation, "record")
            self.authority.check(connection, principal, context, "record")
            return IdentityResolution(operation, operation is not None and alias is None)

    def insert_operation(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        *,
        operation_id: str,
        prepared: PreparedAdmission,
        payload_binding: ArtifactBinding,
        created_at: datetime,
        retain_until: datetime,
    ) -> StoredOperation:
        """Insert after caller-published job/scope/refs in the SAME transaction.

        Bindings are prospective evidence. P3 must have verified actual uploads;
        this primitive only verifies their persisted scoped SQL associations.
        """
        hexadecimal(operation_id, 32, input_value=True)
        created, until = retention(created_at, retain_until, input_value=True)
        if (
            type(prepared) is not PreparedAdmission
            or type(payload_binding) is not ArtifactBinding
            or prepared.project_id != context.project_id
        ):
            raise AdmissionStorageError("admission_input_invalid")
        with storage_errors():
            write_transaction(connection)
            self.authority.check(
                connection,
                principal,
                context,
                "record",
                resource_kind="job",
                resource_id=prepared.job_id,
            )
            expected_payload = prepared.bind_payload(payload_binding.descriptor)
            if payload_binding != expected_payload:
                raise AdmissionStorageError("admission_metadata_invalid")
            configuration = verify_job_configuration(
                connection,
                context=context,
                job_id=prepared.job_id,
                payload_version=2,
                expected_descriptor=prepared.configuration_binding.descriptor,
            )
            if (
                configuration.payload != prepared.envelope_digest
                or configuration.kind != "run"
                or configuration.budget_microusd != prepared.intent.budget_microusd
                or configuration.actor != principal.principal_id
                or configuration.digest != prepared.configuration.digest
            ):
                raise AdmissionStorageError("admission_metadata_invalid")
            for binding in (prepared.task_binding, payload_binding):
                verify_binding(connection, context, binding)
            hexadecimal(prepared.origin.correlation_id, 32)
            self.authority.check(
                connection,
                principal,
                context,
                "record",
                resource_kind="job",
                resource_id=prepared.job_id,
            )
            connection.execute(
                insert(OPERATIONS).values(
                    id=operation_id,
                    project_id=context.project_id,
                    principal_id=principal.principal_id,
                    kind="run",
                    client_operation_id=prepared.intent.client_operation_id,
                    request_digest=prepared.intent.request_digest,
                    job_id=prepared.job_id,
                    accepted_response=canonical(
                        {"operation_id": operation_id, "job_id": prepared.job_id}
                    ).decode(),
                    created_at=(
                        cast(literal(created.isoformat()), DateTime(timezone=True))
                        if connection.dialect.name == "postgresql"
                        else created.isoformat()
                    ),
                    retain_until=(
                        cast(literal(until.isoformat()), DateTime(timezone=True))
                        if connection.dialect.name == "postgresql"
                        else until.isoformat()
                    ),
                    job_resource_kind="job",
                    execution_config_digest=configuration.digest,
                    payload_version=2,
                    failure_correlation_id=prepared.origin.correlation_id,
                )
            )
            operation = self._operation(connection, context, OPERATIONS.c.id == operation_id)
            if operation is None:
                raise AdmissionStorageError("admission_metadata_invalid")
            return operation

    def bind_alias(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        *,
        operation_id: str,
        key_hash: str,
        request_digest: str,
    ) -> bool:
        """Add only an exact creator-bound alias; never replace origin or identities."""
        hexadecimal(operation_id, 32, input_value=True)
        hexadecimal(key_hash, 64, input_value=True)
        hexadecimal(request_digest, 64, input_value=True)
        with storage_errors():
            write_transaction(connection)
            self.authority.check(connection, principal, context, "record")
            operation = self._operation(
                connection,
                context,
                and_(
                    OPERATIONS.c.id == operation_id,
                    OPERATIONS.c.principal_id == context.principal_id,
                ),
            )
            if operation is None:
                raise ResourceNotFound()
            self._verify(connection, principal, context, operation, "record")
            if operation.request_digest != request_digest:
                raise AdmissionStorageError("admission_conflict")
            existing = self._alias(connection, context, key_hash)
            if existing is not None:
                if (existing["operation_id"], existing["request_digest"]) != (
                    operation_id,
                    request_digest,
                ):
                    raise AdmissionStorageError("admission_conflict")
                self.authority.check(connection, principal, context, "record")
                return False
            self.authority.check(connection, principal, context, "record")
            connection.execute(
                insert(ALIASES).values(
                    project_id=context.project_id,
                    principal_id=context.principal_id,
                    kind="run",
                    key_hash=key_hash,
                    operation_id=operation_id,
                    request_digest=request_digest,
                )
            )
            return True
