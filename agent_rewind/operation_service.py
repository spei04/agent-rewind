"""Bounded named-project Operation reads and cancellation; no HTTP or failure producer."""

from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from typing import Literal, TypedDict, cast

from sqlalchemy import and_, literal, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .admission_records import OPERATIONS, AdmissionStorageError, hexadecimal
from .admission_request import AdmissionPreparationError, bounded_canonical
from .admission_transaction import AdmissionError, TransactionOutcome, admission_transaction
from .artifact_graph import _pairs
from .artifact_metadata import ArtifactError, ArtifactObject
from .errors import Fault
from .migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from .operation_cancellation import CancellationPhase, CancellationReceipts
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
from .scoped_actions import ScopedActions
from .scoped_artifacts import ArtifactLoader
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_locks import lock_authority, lock_resource
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


class CancellationView(TypedDict):
    operation_id: str
    cancel_requested: Literal[True]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]


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
        self._actions = ScopedActions(engine, authority)

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

    def cancel_operation(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> CancellationView:
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
            return self._cancel(principal, context, operation_id)
        except (AdmissionError, RepositoryUnavailable, SQLAlchemyError) as error:
            # Normal mutation failures are classified below after cleanup.
            # This also retains uncertainty if an existing boundary supplies it.
            raise Fault(
                "outcome_uncertain"
                if isinstance(error, AdmissionError) and error.code == "outcome_uncertain"
                else "dependency_unavailable"
            ) from None

    def _cancel(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> CancellationView:
        work = OperationWork()
        try:
            operation_id = identifier(operation_id)
        except ResourceNotFound:
            # Only pure malformed identifiers take this authority-only branch.
            # A visible viewer still gets 404, not a premature cancel denial.
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
            raise ResourceNotFound() from None

        owner = CancellationReceipts(work, context, operation_id)
        outcome = TransactionOutcome()
        original_job_id: str | None = None
        try:
            with owner.phase() as phase, operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                operation, original = read_operation(connection, context, operation_id, phase.book)
                original_job_id = operation.job_id
                job = read_job(connection, context, original_job_id, phase.book)
                _primary_visible(connection, context, operation_id, original_job_id)
                self.authority.check(connection, principal, context, "cancel")
                _, config = read_descriptor(
                    connection, context, original_job_id, "admission_config", phase.book
                )
                phase.associate(original, job, config)
                cohort = read_run_cohort(connection, context, job, phase.book)
                phase.verify(connection, cohort)
                self.authority.check(connection, principal, context, "cancel")
            # Do not retain mutable phase bodies through commit/disclosure.
            del operation, original, job, config, cohort, phase
            response = self._cancel_mutate(
                principal, context, owner, original_job_id, outcome, uuid.uuid4().hex
            )
            self._cancel_disclose(principal, context, owner, original_job_id)
            return response
        except (
            AdmissionError,
            AdmissionStorageError,
            AdmissionPreparationError,
            RepositoryUnavailable,
            SQLAlchemyError,
        ) as error:
            uncertain = (
                outcome.commit_attempted
                or (outcome.rollback_attempted and not outcome.rollback_acknowledged)
                or isinstance(error, AdmissionError)
                and error.code == "outcome_uncertain"
            )
            # The failed owner may be poisoned: use only separately retained
            # identities, one existing work budget, and independent visibility.
            try:
                with operation_connection(self.engine, work) as connection:
                    self.authority.check(connection, principal, context, "read")
                    if original_job_id is not None:
                        _primary_visible(connection, context, operation_id, original_job_id)
                        self.authority.check(connection, principal, context, "cancel")
            except (AdmissionError, RepositoryUnavailable, SQLAlchemyError):
                # No remaining capacity/clean acquisition cannot manufacture
                # visibility, or turn a possible commit into a retry promise.
                pass
            raise Fault("outcome_uncertain" if uncertain else "dependency_unavailable") from None

    def _cancel_snapshot(
        self,
        connection: Connection,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        owner: CancellationReceipts,
        phase: CancellationPhase,
        original_job_id: str,
    ) -> tuple[RawReceipt, RunCohort]:
        _, operation = read_operation(connection, context, owner.operation_id, phase.book)
        job = read_job(connection, context, original_job_id, phase.book)
        _, config = read_descriptor(
            connection, context, original_job_id, "admission_config", phase.book
        )
        phase.associate(operation, job, config)
        cohort = read_run_cohort(connection, context, job, phase.book)
        phase.verify(connection, cohort)
        return job, cohort

    def _cancel_mutate(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        owner: CancellationReceipts,
        original_job_id: str,
        outcome: TransactionOutcome,
        audit_id: str,
    ) -> CancellationView:
        with (
            owner.phase() as phase,
            admission_transaction(self.engine, outcome, work=owner.work) as connection,
        ):
            lock_authority(self.authority, connection, principal, context, None, None)
            lock_resource(connection, context, "job", original_job_id, shared=False)
            # Do not join through a mutable job association. A changed job_id
            # fails original receipts, rather than becoming a missing target.
            if (
                connection.execute(
                    select(OPERATIONS.c.id)
                    .where(
                        OPERATIONS.c.id == owner.operation_id,
                        OPERATIONS.c.project_id == context.project_id,
                    )
                    .with_for_update(read=True)
                ).first()
                is None
            ):
                raise ResourceNotFound()
            job, cohort = self._cancel_snapshot(
                connection, principal, context, owner, phase, original_job_id
            )
            self.authority.check(connection, principal, context, "cancel")
            if 256 - owner.source_visits < 1 + len(cohort.records) or 512 - owner.edges < 2 * len(
                cohort.records
            ):
                # Feasibility only: no charge/reservation/refund. Later growth
                # can still prevent disclosure after this single effect.
                raise invalid()
            status = self._actions._cancel_effect(
                connection, principal, original_job_id, cast(str, job.row()["status"]), audit_id
            )
            response: CancellationView = {
                "operation_id": owner.operation_id,
                "cancel_requested": True,
                "status": cast(
                    Literal["queued", "running", "succeeded", "failed", "cancelled"], status
                ),
            }
            bounded_canonical(response, limit=2048, limit_code="admission_body_limit")
        return response

    def _cancel_disclose(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        owner: CancellationReceipts,
        original_job_id: str,
    ) -> None:
        with owner.phase() as phase, operation_connection(self.engine, owner.work) as connection:
            self.authority.check(connection, principal, context, "read")
            _primary_visible(connection, context, owner.operation_id, original_job_id)
            self._cancel_snapshot(connection, principal, context, owner, phase, original_job_id)
            self.authority.check(connection, principal, context, "cancel")

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
