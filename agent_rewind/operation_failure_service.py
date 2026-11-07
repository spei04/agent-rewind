"""Fixed private ar8 operation consumers; public readiness stays unchanged."""

from __future__ import annotations

import uuid
from typing import Literal, TypedDict, cast

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from .admission_records import OPERATIONS, AdmissionStorageError
from .admission_request import AdmissionPreparationError, bounded_canonical
from .admission_transaction import AdmissionError, TransactionOutcome, admission_transaction
from .artifact_metadata import ArtifactError
from .errors import Fault
from .migrations.failure_consumer import (
    ConsumerPrincipal,
    refresh_consumer_principal,
    validated_consumer_history,
)
from .migrations.schema import MigrationRefused
from .operation_failure_cancellation import (
    SuccessorCancellationPhase,
    SuccessorCancellationReceipts,
)
from .operation_failure_reads import (
    FailureError,
    SuccessorReceiptBook,
    observe_failure_result_absence,
    read_successor_cancel_job,
    read_successor_job,
    successor_error,
)
from .operation_failure_sources import verify_successor_snapshot
from .operation_reads import (
    RawReceipt,
    invalid,
    observe_result,
    read_descriptor,
    read_operation,
    validate_association,
)
from .operation_service import CancellationView, OperationService, _primary_visible
from .operation_sources import RunCohort, read_run_cohort
from .operation_work import OperationWork, operation_connection
from .request_identity import VerifiedPrincipal
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_locks import lock_authority, lock_resource
from .scoped_repositories import ProjectContext, RepositoryUnavailable
from .sqlite_ownership import require_owned_sqlite

SuccessorStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class SuccessorOperationView(TypedDict):
    id: str
    project_id: str
    job_id: str
    client_operation_id: str
    status: SuccessorStatus
    cancel_requested: bool
    result_run_id: str | None
    budget_microusd: int
    reserved_microusd: int
    error: FailureError | None


class _SuccessorService:
    def __init__(self, service: OperationService) -> None:
        self.service = service
        self.engine, self.authority = service.engine, service.authority
        self._actions = service._actions

    def _observe(
        self, connection: Connection, work: OperationWork, context: ProjectContext
    ) -> ConsumerPrincipal | None:
        if work._connection is not connection or self.authority.engine is not self.engine:
            raise AdmissionError("dependency_unavailable")
        work.check()
        # Complete history/projection is checked before operation observations.
        # Retain only the small native identity tuple across later phases.
        inspected = validated_consumer_history(connection, work)
        if inspected.history.ownership.organization_id != context.organization_id:
            raise MigrationRefused("schema_incompatible")
        return inspected.principal

    def read(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> SuccessorOperationView:
        work = OperationWork(include_acquisition=True)
        book = SuccessorReceiptBook(check=work.check)
        self.authority._principal(principal)
        if self.engine.dialect.name == "sqlite":
            require_owned_sqlite(self.engine)
        original_job_id: str | None = None
        try:
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                operation_id = identifier(operation_id)
                original_principal = self._observe(connection, work, context)
                operation, op_receipt = read_operation(connection, context, operation_id, book)
                original_job_id = operation.job_id
                job = read_successor_job(connection, context, original_job_id, book)
                _, configuration = read_descriptor(
                    connection, context, original_job_id, "admission_config", book
                )
                validate_association(op_receipt, job, configuration)
                result = observe_result(connection, context, original_job_id, book)
                observed = book.job_observation(original_job_id)
                if observed.evidence is not None and observed.evidence[1] == "verified_failure":
                    observe_failure_result_absence(connection, context, original_job_id, book)
                error_value = successor_error(
                    connection.dialect.name, context, op_receipt, job, configuration, book
                )
                cohort = read_run_cohort(connection, context, job, book)
                _primary_visible(connection, context, operation_id, original_job_id)
                self.authority.check(connection, principal, context, "read")

            run_id = self.service._load_result(job, result[0] if result else None, cohort)

            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                _primary_visible(connection, context, operation_id, original_job_id)
                row = job.row()
                response: SuccessorOperationView = {
                    "id": operation.id,
                    "project_id": operation.project_id,
                    "job_id": operation.job_id,
                    "client_operation_id": operation.client_operation_id,
                    "status": cast(SuccessorStatus, row["status"]),
                    "cancel_requested": bool(row["cancel"]),
                    "result_run_id": run_id,
                    "budget_microusd": cast(int, row["budget"]),
                    "reserved_microusd": cast(int, row["reserved"]),
                    "error": error_value,
                }
                bounded_canonical(response, limit=2048, limit_code="admission_body_limit")
                verify_successor_snapshot(connection, context, book, cohort)
                refresh_consumer_principal(connection, work, original_principal)
                self.authority.check(connection, principal, context, "read")
            work.check()
            return response
        except (AdmissionStorageError, AdmissionPreparationError, ArtifactError):
            # Never query an aborted transaction or reset work to classify a
            # secondary proof. A primary typed denial bypasses this handler.
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                if original_job_id is not None:
                    _primary_visible(connection, context, operation_id, original_job_id)
            raise Fault("dependency_unavailable") from None
        except MigrationRefused:
            raise Fault("schema_incompatible") from None
        except (AdmissionError, RepositoryUnavailable, SQLAlchemyError):
            raise Fault("dependency_unavailable") from None

    def cancel(
        self, principal: VerifiedPrincipal, context: ProjectContext, operation_id: str
    ) -> CancellationView:
        work = OperationWork(include_acquisition=True)
        self.authority._principal(principal)
        if self.engine.dialect.name == "sqlite":
            require_owned_sqlite(self.engine)
        try:
            operation_id = identifier(operation_id)
        except ResourceNotFound:
            # Only pure malformed identifiers take this authority-only branch.
            # A visible viewer still gets 404, not a premature cancel denial.
            with operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
            raise ResourceNotFound() from None

        owner = SuccessorCancellationReceipts(work, context, operation_id)
        outcome = TransactionOutcome()
        original_job_id: str | None = None
        try:
            with owner.phase() as phase, operation_connection(self.engine, work) as connection:
                self.authority.check(connection, principal, context, "read")
                original_principal = self._observe(connection, work, context)
                operation, original = read_operation(connection, context, operation_id, phase.book)
                original_job_id = operation.job_id
                job = read_successor_cancel_job(connection, context, original_job_id, phase.book)
                _primary_visible(connection, context, operation_id, original_job_id)
                self.authority.check(connection, principal, context, "cancel")
                _, config = read_descriptor(
                    connection, context, original_job_id, "admission_config", phase.book
                )
                phase.associate(connection, original, job, config)
                cohort = read_run_cohort(connection, context, job, phase.book)
                phase.verify(connection, cohort)
                refresh_consumer_principal(connection, work, original_principal)
                self.authority.check(connection, principal, context, "cancel")
            # Do not retain mutable phase bodies through commit/disclosure.
            del operation, original, job, config, cohort, phase
            response = self._cancel_mutate(
                principal,
                context,
                owner,
                original_job_id,
                outcome,
                uuid.uuid4().hex,
                original_principal,
            )
            self._cancel_disclose(principal, context, owner, original_job_id, original_principal)
            work.check()
            return response
        except (
            AdmissionError,
            AdmissionStorageError,
            AdmissionPreparationError,
            RepositoryUnavailable,
            SQLAlchemyError,
            MigrationRefused,
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
        owner: SuccessorCancellationReceipts,
        phase: SuccessorCancellationPhase,
        original_job_id: str,
    ) -> tuple[RawReceipt, RunCohort]:
        _, operation = read_operation(connection, context, owner.operation_id, phase.book)
        job = read_successor_cancel_job(connection, context, original_job_id, phase.book)
        _, config = read_descriptor(
            connection, context, original_job_id, "admission_config", phase.book
        )
        phase.associate(connection, operation, job, config)
        cohort = read_run_cohort(connection, context, job, phase.book)
        phase.verify(connection, cohort)
        return job, cohort

    def _cancel_mutate(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        owner: SuccessorCancellationReceipts,
        original_job_id: str,
        outcome: TransactionOutcome,
        audit_id: str,
        original_principal: ConsumerPrincipal | None,
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
            refresh_consumer_principal(connection, owner.work, original_principal)
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
        owner: SuccessorCancellationReceipts,
        original_job_id: str,
        original_principal: ConsumerPrincipal | None,
    ) -> None:
        with owner.phase() as phase, operation_connection(self.engine, owner.work) as connection:
            self.authority.check(connection, principal, context, "read")
            _primary_visible(connection, context, owner.operation_id, original_job_id)
            self._cancel_snapshot(connection, principal, context, owner, phase, original_job_id)
            refresh_consumer_principal(connection, owner.work, original_principal)
            self.authority.check(connection, principal, context, "cancel")
