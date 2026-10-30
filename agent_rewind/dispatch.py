"""Internal one-use dispatch, after a durable ledger transition.

This component does not activate admission or the worker. The server composition
must supply an immutable adapter which checks its installed configuration and
request bounds. A dispatching row is uncertainty, never charge/response evidence.
"""

from __future__ import annotations

import hashlib
import json
from threading import Lock
from typing import Generic, Protocol, TypeVar, cast

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from . import reservation
from .admission_adapters import completed, synchronous
from .admission_configuration import NativeConfiguration
from .admission_request import MAX_TASK_BYTES
from .admission_transaction import AdmissionError, TransactionOutcome, admission_transaction
from .migrations.schema import MigrationRefused
from .operation_work import OperationWork
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .reservation_connection import issued_connection, require_body, require_engine
from .reservation_rows import ReservationRows
from .reservation_service import ReservationCoordinator
from .reservation_types import (
    CallMatching,
    CreatedReservation,
    JobFence,
    ReservationIntent,
    ReservationRefusal,
    ReservationScope,
    TransactionFacts,
)
from .scoped_locks import lock_authority
from .scoped_repositories import ProjectContext

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class DispatchAdapter(Protocol[T_co]):
    """Trusted server-owned adapter; never selected from submitted request data.

    configuration and send must identify the same immutable installed adapter,
    image and endpoint mapping. validate_request checks those identities, exact
    request bytes, token/price bounds and processor permission without paid I/O.
    It must refuse drift; send must not retry or reinterpret the supplied bytes.
    There is deliberately no default provider implementation.
    """

    @property
    def configuration(self) -> NativeConfiguration: ...

    def validate_request(self, request: bytes, reserved_microusd: int) -> None: ...

    def send(self, request: bytes) -> T_co: ...


def _transition(
    connection: Connection,
    scope: ReservationScope,
    fence: JobFence,
    identity: ReservationIntent,
    configuration: NativeConfiguration,
) -> None:
    body = require_body(connection, scope)
    reservation._fence(scope, fence)
    reservation._intent(scope, identity)
    if fence.generation != identity.lease_generation:
        raise ReservationRefusal("invalid_intent")
    rows = ReservationRows.capture(connection, scope, body.work)
    rows.lock_accounts(connection)
    now = reservation._clock(connection)
    rows.reconcile(now)
    reservation._live(rows.job, fence, now)
    # capture validates the actual same-project operation/config descriptor and
    # scoped job reference. Matching submitted hashes alone is insufficient.
    if (
        rows.job["execution_config_digest"] != configuration.digest
        or rows.job["execution_config_ref"] != configuration.digest
    ):
        raise ReservationRefusal("unsupported_job")
    original = reservation._original(rows, identity)
    if not isinstance(original, CallMatching):
        raise ReservationRefusal("identity_conflict")
    if (
        original.record.state != "reserved"
        or original.record.settled_microusd != 0
        or original.record.released_microusd != 0
    ):
        raise AdmissionError("outcome_uncertain")
    after = rows.after_image()
    next(row for row in after["call"] if row["id"] == identity.call_id)["state"] = "dispatching"
    rows.require_headroom(after)
    require_body(connection, scope)
    changed = connection.execute(
        text(
            "UPDATE provider_calls SET state='dispatching' "
            "WHERE id=:call AND project_id=:project AND job_id=:job "
            "AND logical_call_id=:logical AND request_digest=:request "
            "AND lease_generation=:generation AND state='reserved' "
            "AND price_version=:price AND reserved_microusd=:amount "
            "AND organization_account_id=:organization_account "
            "AND project_account_id=:project_account AND job_account_id=:job_account "
            "AND EXISTS (SELECT 1 FROM jobs WHERE jobs.id=:job "
            "AND jobs.owner=:owner AND jobs.lease_generation=:generation "
            "AND jobs.status='running' AND jobs.cancel=:cancel "
            "AND jobs.execution_config_digest=:configuration "
            "AND jobs.execution_config_ref=:configuration)"
        ),
        {
            "call": identity.call_id,
            "project": scope.context.project_id,
            "job": scope.job_id,
            "logical": identity.logical_call_id,
            "request": identity.request_digest,
            "generation": fence.generation,
            "price": identity.price_version,
            "amount": identity.reserved_microusd,
            "organization_account": identity.organization_account_id,
            "project_account": identity.project_account_id,
            "job_account": identity.job_account_id,
            "owner": fence.owner_uuid,
            "cancel": False,
            "configuration": configuration.digest,
        },
    )
    if changed.rowcount != 1:
        raise ReservationRefusal("job_not_live")
    rows.confirm(connection, after)


class DispatchCoordinator(Generic[T]):
    """One invocation owns one transition and immediate adapter call.

    No result or detached transaction facts can be exchanged for a permit.
    A fresh coordinator refuses any already-dispatching call after a restart.
    Cancellation/expiry can race after the final database check; the hold remains.
    """

    def __init__(
        self, engine: Engine, authority: RequestAuthority, adapter: DispatchAdapter[T]
    ) -> None:
        self.engine, self.authority, self._adapter = engine, authority, adapter
        try:
            candidate = adapter.configuration
            if type(candidate) is not NativeConfiguration:
                raise ValueError
            self._configuration = NativeConfiguration(
                candidate.canonical_bytes, expected_digest=candidate.digest
            )
        except Exception:
            raise AdmissionError("dependency_unavailable") from None
        self._lock = Lock()
        self._consumed = False
        self._transaction = TransactionOutcome()
        self._outcome = TransactionFacts.observe(self._transaction)
        self._work: OperationWork | None = None
        self._reservation: ReservationCoordinator | None = None

    @property
    def outcome(self) -> TransactionFacts:
        with self._lock:
            return self._outcome

    @property
    def reservation_outcome(self) -> TransactionFacts | None:
        owner = self._reservation
        return None if owner is None else owner.outcome

    def _adapter_check(self, request: bytes, identity: ReservationIntent) -> None:
        if self._adapter.configuration != self._configuration:
            raise AdmissionError("dependency_unavailable")
        if (
            identity.price_version
            != json.loads(self._configuration.canonical_bytes)["price_version"]
        ):
            raise ReservationRefusal("invalid_intent")
        completed(self._adapter.validate_request, request, identity.reserved_microusd)

    def dispatch(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        fence: JobFence,
        identity: ReservationIntent,
        request: bytes,
    ) -> T:
        with self._lock:
            if self._consumed:
                raise ReservationRefusal("invocation_reused")
            self._consumed = True
        try:
            if (
                not isinstance(self.authority, RequestAuthority)
                or self.authority.engine is not self.engine
                or type(fence) is not JobFence
                or type(identity) is not ReservationIntent
            ):
                raise ReservationRefusal("invalid_intent")
            self.authority._principal(principal)
            require_engine(self.engine)
            fence.__post_init__()
            identity.__post_init__()
            scope = ReservationScope(principal, context, fence.job_id)
            if (
                identity.job_id != fence.job_id
                or identity.project_id != context.project_id
                or identity.lease_generation != fence.generation
                or type(request) is not bytes
                or not 0 < len(request) <= MAX_TASK_BYTES
                or hashlib.sha256(request).hexdigest() != identity.request_digest
            ):
                raise ReservationRefusal("invalid_intent")
            try:
                self._adapter_check(request, identity)
            except Exception:
                raise AdmissionError("dependency_unavailable") from None
            # This invocation alone owns its acknowledged new reservation.
            # Existing/recovered rows are historical, never fresh dispatch rights.
            self._reservation = ReservationCoordinator(self.engine, self.authority)
            created = self._reservation.reserve(
                principal, context, fence, identity, configuration=self._configuration
            )
            facts = self._reservation.outcome
            if (
                type(created) is not CreatedReservation
                or not facts.commit_acknowledged
                or facts.cleanup_failed
            ):
                raise AdmissionError("outcome_uncertain")
            work = OperationWork(include_acquisition=True)
            self._work = work
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
                    fence.job_id,
                    exclusive_organization=True,
                )
                self.authority.check(
                    connection,
                    principal,
                    context,
                    "record",
                    resource_kind="job",
                    resource_id=fence.job_id,
                )
                try:
                    _transition(connection, scope, fence, identity, self._configuration)
                    reservation.flush_constraints(connection, scope)
                    self.authority.check(
                        connection,
                        principal,
                        context,
                        "record",
                        resource_kind="job",
                        resource_id=fence.job_id,
                    )
                    reservation.final_fence(connection, scope, fence, identity)
                except MigrationRefused as error:
                    raise ReservationRefusal(
                        "capacity_exceeded"
                        if error.code in {"ledger_limit_exceeded", "source_limit_exceeded"}
                        else "ledger_state_invalid"
                    ) from None
        finally:
            with self._lock:
                self._outcome = TransactionFacts.observe(self._transaction)
        if not self.outcome.commit_acknowledged or self.outcome.cleanup_failed:
            raise AdmissionError("outcome_uncertain")
        # No SQL connection or lock is held for external I/O. Refusal here also
        # retains the dispatching row: absence of a response is not refund proof.
        try:
            self._adapter_check(request, identity)
            return cast(T, synchronous(self._adapter.send(request)))
        except Exception:
            raise AdmissionError("outcome_uncertain") from None
