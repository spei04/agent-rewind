"""One-use internal P2 owner; no live worker, provider or public route wiring."""

from __future__ import annotations

from threading import Lock
from typing import Literal

from sqlalchemy.engine import Engine

from . import reservation
from .admission_transaction import TransactionOutcome, admission_transaction
from .migrations.schema import MigrationRefused
from .operation_work import OperationWork
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .reservation_connection import issued_connection, require_body, require_engine
from .reservation_types import (
    ClaimIntent,
    CreatedReservation,
    InspectionResult,
    JobFence,
    ReservationDecision,
    ReservationIntent,
    ReservationRefusal,
    ReservationScope,
    TransactionFacts,
)
from .scoped_locks import lock_authority
from .scoped_repositories import ProjectContext


class ReservationCoordinator:
    """Every result is historical; transaction facts remain available on failure."""

    def __init__(self, engine: Engine, authority: RequestAuthority):
        self.engine, self.authority = engine, authority
        self._lock = Lock()
        self._consumed = False
        self._transaction = TransactionOutcome()
        self._outcome = TransactionFacts.observe(self._transaction)
        self._work: OperationWork | None = None

    @property
    def outcome(self) -> TransactionFacts:
        with self._lock:
            return self._outcome

    def claim_generation(
        self, principal: VerifiedPrincipal, context: ProjectContext, intent: ClaimIntent
    ) -> JobFence:
        result = self._run("claim", principal, context, claim=intent)
        if not isinstance(result, JobFence):
            raise ReservationRefusal("ledger_state_invalid")
        return result

    def reserve(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        fence: JobFence,
        intent: ReservationIntent,
    ) -> ReservationDecision:
        result = self._run("reserve", principal, context, fence=fence, identity=intent)
        if isinstance(result, JobFence | InspectionResult):
            raise ReservationRefusal("ledger_state_invalid")
        return result

    def inspect_original(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        job_id: str,
        identity: ReservationIntent | None = None,
    ) -> InspectionResult:
        result = self._run("inspect", principal, context, job_id=job_id, identity=identity)
        if not isinstance(result, InspectionResult):
            raise ReservationRefusal("ledger_state_invalid")
        return result

    def _run(
        self,
        mode: Literal["claim", "reserve", "inspect"],
        principal: VerifiedPrincipal,
        context: ProjectContext,
        *,
        claim: ClaimIntent | None = None,
        fence: JobFence | None = None,
        identity: ReservationIntent | None = None,
        job_id: str | None = None,
    ) -> JobFence | ReservationDecision | InspectionResult:
        work = OperationWork(include_acquisition=True)
        with self._lock:
            if self._consumed:
                raise ReservationRefusal("invocation_reused")
            self._consumed = True
            self._work = work
        try:
            if (
                not isinstance(self.authority, RequestAuthority)
                or self.authority.engine is not self.engine
            ):
                raise ReservationRefusal("invalid_intent")
            self.authority._principal(principal)
            require_engine(self.engine)
            if mode == "claim":
                if type(claim) is not ClaimIntent:
                    raise ReservationRefusal("invalid_intent")
                claim.__post_init__()
                job_id = claim.job_id
            elif mode == "reserve":
                if type(fence) is not JobFence or type(identity) is not ReservationIntent:
                    raise ReservationRefusal("invalid_intent")
                fence.__post_init__()
                identity.__post_init__()
                job_id = fence.job_id
            if job_id is None:
                raise ReservationRefusal("invalid_intent")
            scope = ReservationScope(principal, context, job_id)
            if identity is not None:
                if type(identity) is not ReservationIntent:
                    raise ReservationRefusal("invalid_intent")
                identity.__post_init__()
                if (
                    identity.job_id != scope.job_id
                    or identity.project_id != scope.context.project_id
                ):
                    raise ReservationRefusal("invalid_intent")
            action = "read" if mode == "inspect" else "record"
            with (
                admission_transaction(self.engine, self._transaction, work=work) as connection,
                issued_connection(connection, scope, work),
            ):
                lock_authority(
                    self.authority,
                    connection,
                    principal,
                    context,
                    "job",
                    job_id,
                    exclusive_organization=True,
                )
                self.authority.check(
                    connection,
                    principal,
                    context,
                    action,
                    resource_kind="job",
                    resource_id=job_id,
                )
                try:
                    result: JobFence | ReservationDecision | InspectionResult
                    if mode == "claim" and claim is not None:
                        result = reservation.claim_generation(connection, scope, claim)
                    elif mode == "reserve" and fence is not None and identity is not None:
                        result = reservation.reserve(connection, scope, fence, identity)
                    else:
                        result = reservation.inspect_original(connection, scope, identity)
                    # Deferred/FK work precedes the final authority and DB-time
                    # fence. A later COMMIT may still cross a wall-clock expiry.
                    if isinstance(result, JobFence | CreatedReservation):
                        reservation.flush_constraints(connection, scope)
                    else:
                        require_body(connection, scope)
                    self.authority.check(
                        connection,
                        principal,
                        context,
                        action if isinstance(result, JobFence | CreatedReservation) else "read",
                        resource_kind="job",
                        resource_id=job_id,
                    )
                    if isinstance(result, JobFence):
                        reservation.require_live_job(connection, scope, result)
                    elif (
                        isinstance(result, CreatedReservation)
                        and fence is not None
                        and identity is not None
                    ):
                        reservation.final_fence(connection, scope, fence, identity)
                except MigrationRefused as error:
                    raise ReservationRefusal(
                        "capacity_exceeded"
                        if error.code in {"ledger_limit_exceeded", "source_limit_exceeded"}
                        else "ledger_state_invalid"
                    ) from None
            return result
        finally:
            # A failed concurrent reuse never enters this finally and therefore
            # cannot replace the first attempt's retained transaction facts.
            with self._lock:
                self._outcome = TransactionFacts.observe(self._transaction)
