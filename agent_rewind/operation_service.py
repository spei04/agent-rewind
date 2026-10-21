"""Bounded named-project Operation reads; no HTTP, cancellation or failure producer."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Literal, TypedDict, cast

from sqlalchemy import and_, literal, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .admission_records import OPERATIONS, AdmissionStorageError, hexadecimal
from .admission_request import AdmissionPreparationError, bounded_canonical
from .admission_transaction import AdmissionError
from .artifact_graph import _pairs
from .artifact_metadata import ArtifactError, ArtifactObject
from .errors import Fault
from .migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from .operation_reads import (
    JOBS,
    RawReceipt,
    ReceiptBook,
    invalid,
    observe_result,
    read_descriptor,
    read_job,
    read_operation,
    validate_association,
)
from .operation_sources import (
    RunCohort,
    read_run_cohort,
    validate_result_member,
    verify_read_snapshot,
)
from .operation_work import OperationWork, operation_connection
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .scoped_artifacts import ArtifactLoader
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_repositories import ProjectContext, RepositoryUnavailable, scopes
from .sqlite_ownership import require_owned_sqlite

Status = Literal["queued", "running", "succeeded", "cancelled"]


class OperationView(TypedDict):
    id: str
    project_id: str
    job_id: str
    client_operation_id: str
    status: Status
    cancel_requested: bool
    result_run_id: str | None
    budget_microusd: int
    reserved_microusd: int
    error: None


def _primary_visible(
    connection: Connection, context: ProjectContext, operation_id: str, original_job_id: str
) -> None:
    # Reassociation is a receipt mismatch, not a missing primary resource:
    # deliberately do not join the operation's current job_id here.
    operation = (
        select(literal(1))
        .select_from(OPERATIONS)
        .where(OPERATIONS.c.project_id == context.project_id, OPERATIONS.c.id == operation_id)
        .exists()
    )
    job = (
        select(literal(1))
        .select_from(
            JOBS.join(
                scopes,
                and_(
                    scopes.c.project_id == context.project_id,
                    scopes.c.resource_kind == "job",
                    scopes.c.resource_id == JOBS.c.id,
                ),
            )
        )
        .where(JOBS.c.id == original_job_id)
        .exists()
    )
    if connection.execute(select(literal(1)).where(operation, job)).scalar_one_or_none() != 1:
        raise ResourceNotFound()


def _supported(job: RawReceipt) -> None:
    row = job.row()  # Native types/status were validated by read_job.
    if row["status"] == "failed" or row["error"] is not None:
        raise invalid()


def _result_id(data: bytes, descriptor: ArtifactObject, cohort: RunCohort) -> str:
    if (
        type(data) is not bytes
        or len(data) > 4096
        or len(data) != descriptor.byte_count
        or hashlib.sha256(data).hexdigest() != descriptor.digest
    ):
        raise invalid()
    try:
        # Parsing a string prevents json.loads(bytes)' UTF-16/32 autodetection.
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
        if not isinstance(value, dict) or set(value) != {"run_id"}:
            raise invalid()
        run_id = hexadecimal(value["run_id"], 32)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise invalid() from None
    validate_result_member(cohort, run_id)
    return run_id


class OperationService:
    def __init__(
        self,
        engine: Engine,
        authority: RequestAuthority,
        *,
        artifact_loader: ArtifactLoader | None = None,
    ) -> None:
        self.engine, self.authority, self.artifact_loader = engine, authority, artifact_loader

    def schema_compatibility(self) -> CompatibilityResult:
        return runtime_schema_compatibility(self.engine)

    def read_operation(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> OperationView:
        self.authority._principal(principal)
        try:
            if self.engine.dialect.name == "sqlite":
                require_owned_sqlite(self.engine)
            schema = self.schema_compatibility()
            if schema.status != "ready":
                raise Fault(
                    "dependency_unavailable"
                    if schema.status == "unavailable"
                    else "schema_incompatible"
                ) from None
            return self._read(principal, context, operation_id)
        except (AdmissionError, RepositoryUnavailable, SQLAlchemyError):
            # This service has no mutation/commit outcome to reconcile.
            raise Fault("dependency_unavailable") from None

    def _read(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> OperationView:
        work, book = OperationWork(), ReceiptBook()
        original_job_id: str | None = None
        try:
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                operation_id = identifier(operation_id)
                operation, op_receipt = read_operation(connection, context, operation_id, book)
                original_job_id = operation.job_id
                job = read_job(connection, context, original_job_id, book)
                _, configuration = read_descriptor(
                    connection, context, original_job_id, "admission_config", book
                )
                validate_association(op_receipt, job, configuration)
                _supported(job)
                result = observe_result(connection, context, original_job_id, book)
                cohort = read_run_cohort(connection, context, job, book)
                _primary_visible(connection, context, operation_id, original_job_id)
                self.authority.check(connection, principal, context, "read")

            run_id = self._load_result(job, result[0] if result else None, cohort)

            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                _primary_visible(connection, context, operation_id, original_job_id)
                row = job.row()
                response: OperationView = {
                    "id": operation.id,
                    "project_id": operation.project_id,
                    "job_id": operation.job_id,
                    "client_operation_id": operation.client_operation_id,
                    "status": cast(Status, row["status"]),
                    "cancel_requested": bool(row["cancel"]),
                    "result_run_id": run_id,
                    "budget_microusd": cast(int, row["budget"]),
                    "reserved_microusd": cast(int, row["reserved"]),
                    "error": None,
                }
                bounded_canonical(response, limit=2048, limit_code="admission_body_limit")
                verify_read_snapshot(connection, context, book, cohort)
                self.authority.check(connection, principal, context, "read")
            return response
        except (AdmissionStorageError, AdmissionPreparationError, ArtifactError):
            # Never query an aborted transaction or reset work to classify a
            # secondary proof. A primary typed denial bypasses this handler.
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                if original_job_id is not None:
                    _primary_visible(connection, context, operation_id, original_job_id)
            raise Fault("dependency_unavailable") from None

    def _load_result(
        self, job: RawReceipt, descriptor: ArtifactObject | None, cohort: RunCohort
    ) -> str | None:
        digest = job.row()["result"]
        if digest is None:
            return None
        if (
            descriptor is None
            or descriptor.digest != digest
            or descriptor.format_version != 1
            or descriptor.byte_count > 4096
            or self.artifact_loader is None
        ):
            raise invalid()
        try:
            data = self.artifact_loader(descriptor)
        except (OSError, ResourceNotFound):
            # Missing secondary storage is not a primary visibility denial.
            raise invalid() from None
        # Malformed async adapters are refused, not run on an event-loop bridge.
        if inspect.iscoroutine(data):
            data.close()
            raise invalid()
        return _result_id(data, descriptor, cohort)
