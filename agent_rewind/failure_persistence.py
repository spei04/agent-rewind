"""Private acknowledged-claim ownership for F3; no worker or terminal writer yet."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from . import reservation
from .admission_configuration import NativeConfiguration
from .admission_transaction import admission_transaction
from .dispatch import DispatchAdapter
from .failure_evidence import ClaimedFailureSource, FailureRefusal, _AcknowledgedClaim
from .migrations.schema import MigrationRefused
from .operation_reads import (
    IMMUTABLE_JOB_FIELDS,
    RawReceipt,
    ReceiptBook,
    observe_result,
    read_descriptor,
    read_job,
    read_operation,
    validate_association,
)
from .operation_work import OperationWork
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .reservation_connection import issued_connection, require_body, require_engine
from .reservation_rows import ReservationRows
from .reservation_service import ReservationCoordinator
from .reservation_types import (
    ClaimIntent,
    JobFence,
    ReservationRefusal,
    ReservationScope,
    TransactionFacts,
)
from .scoped_locks import lock_authority
from .scoped_repositories import ProjectContext

_LOCK = RLock()


@dataclass(frozen=True)
class _ClaimRecord:
    token: _AcknowledgedClaim
    principal: VerifiedPrincipal
    context: ProjectContext
    configuration: NativeConfiguration
    source: ClaimedFailureSource


@dataclass
class _OwnerState:
    coordinator: ReservationCoordinator
    adapter_id: int
    invoked: bool = False
    work: OperationWork | None = None
    source: ClaimedFailureSource | None = None


# Values never retain their weak key. In particular, a claim record holds no
# coordinator/owner/connection, and an owner state holds no adapter or owner.
_CLAIMS: WeakKeyDictionary[ReservationCoordinator, _ClaimRecord] = WeakKeyDictionary()
_OWNERS: WeakKeyDictionary[_FailureExecutionOwner, _OwnerState] = WeakKeyDictionary()


def _configuration(value: NativeConfiguration) -> NativeConfiguration:
    if type(value) is not NativeConfiguration:
        raise FailureRefusal("invalid_intent")
    try:
        return NativeConfiguration(value.canonical_bytes, expected_digest=value.digest)
    except (ValueError, TypeError, RuntimeError):
        raise FailureRefusal("invalid_intent") from None


def _installed_configuration(adapter: DispatchAdapter[Any]) -> NativeConfiguration:
    try:
        return _configuration(adapter.configuration)
    except Exception:
        raise FailureRefusal("stale_source") from None


def _owned_state(owner: _FailureExecutionOwner, coordinator: ReservationCoordinator) -> _OwnerState:
    if type(owner) is not _FailureExecutionOwner or type(coordinator) is not ReservationCoordinator:
        raise FailureRefusal("capability_not_issued")
    with _LOCK:
        state = _OWNERS.get(owner)
        if (
            state is None
            or state.coordinator is not coordinator
            or not state.invoked
            or type(state.work) is not OperationWork
            or coordinator._work is not state.work
        ):
            raise FailureRefusal("capability_not_issued")
        if id(owner._adapter) != state.adapter_id:
            raise FailureRefusal("stale_source")
        return state


def _observe_installed(
    owner: _FailureExecutionOwner, coordinator: ReservationCoordinator
) -> NativeConfiguration:
    state = _owned_state(owner, coordinator)
    adapter = owner._adapter
    configuration = _installed_configuration(adapter)
    # Property evaluation is not authority: it may replace/close its own owner.
    if _owned_state(owner, coordinator) is not state or owner._adapter is not adapter:
        raise FailureRefusal("stale_source")
    return configuration


def _absence(connection: Connection, scope: ReservationScope) -> None:
    require_body(connection, scope)
    # Select candidates only by job identity. No malformed/tag/project/generation
    # predicate can filter existing evidence into apparent absence.
    with connection.execute(
        text("SELECT 1 FROM job_failure_evidence WHERE job_id=:job LIMIT 2"),
        {"job": scope.job_id},
    ) as result:
        if result.all():
            raise FailureRefusal("not_eligible")


def _association(
    connection: Connection,
    scope: ReservationScope,
    operation_id: str,
    configuration: NativeConfiguration,
) -> tuple[RawReceipt, RawReceipt, RawReceipt]:
    body = require_body(connection, scope)
    book = ReceiptBook()
    operation, op = read_operation(connection, scope.context, operation_id, book)
    job = read_job(connection, scope.context, scope.job_id, book)
    descriptor, config = read_descriptor(
        connection, scope.context, scope.job_id, "admission_config", book
    )
    validate_association(op, job, config)
    values = job.row()
    if (
        operation.failure_correlation_id is None
        or operation.execution_config_digest != configuration.digest
        or values["execution_config_ref"] != configuration.digest
        or values["execution_config_digest"] != configuration.digest
        or descriptor.byte_count != len(configuration.canonical_bytes)
        or values["error"] is not None
        or values["result"] is not None
        or observe_result(connection, scope.context, scope.job_id, book) is not None
    ):
        raise FailureRefusal("origin_unproved")
    body.work.check()
    return op, job, config


def _same_association(
    original: tuple[RawReceipt, RawReceipt, RawReceipt],
    current: tuple[RawReceipt, RawReceipt, RawReceipt],
) -> None:
    for before, after in zip(original, current, strict=True):
        if before.domain == "job":
            left, right = before.row(), after.row()
            old = tuple(left[name] for name in IMMUTABLE_JOB_FIELDS)
            new = tuple(right[name] for name in IMMUTABLE_JOB_FIELDS)
        else:
            if (before.domain, before.identity, before.fields) != (
                after.domain,
                after.identity,
                after.fields,
            ):
                raise FailureRefusal("stale_source")
            old, new = before.values, after.values
        if old != new or tuple(map(type, old)) != tuple(map(type, new)):
            raise FailureRefusal("stale_source")


def _claim_for_failure_execution(
    coordinator: ReservationCoordinator,
    principal: VerifiedPrincipal,
    context: ProjectContext,
    intent: ClaimIntent,
    *,
    owner: _FailureExecutionOwner,
    configuration: NativeConfiguration,
) -> _AcknowledgedClaim:
    """Fixed ar8 producer path; no caller-selected profile or mutation callback."""
    if type(coordinator) is not ReservationCoordinator:
        raise FailureRefusal("invalid_intent")
    state = _owned_state(owner, coordinator)
    work = state.work
    if work is None:
        raise FailureRefusal("capability_not_issued")
    with coordinator._lock:
        if coordinator._consumed:
            raise FailureRefusal("invocation_reused")
        coordinator._consumed = True
        coordinator._work = work
    try:
        if (
            type(coordinator.authority) is not RequestAuthority
            or coordinator.authority.engine is not coordinator.engine
            or type(intent) is not ClaimIntent
        ):
            raise FailureRefusal("invalid_intent")
        intent.__post_init__()
        configuration = _configuration(configuration)
        coordinator.authority._principal(principal)
        require_engine(coordinator.engine)
        scope = ReservationScope(principal, context, intent.job_id)
        with (
            admission_transaction(
                coordinator.engine, coordinator._transaction, work=work
            ) as connection,
            issued_connection(connection, scope, work),
        ):
            lock_authority(
                coordinator.authority,
                connection,
                principal,
                context,
                "job",
                intent.job_id,
                exclusive_organization=True,
            )
            coordinator.authority.check(
                connection,
                principal,
                context,
                "record",
                resource_kind="job",
                resource_id=intent.job_id,
            )
            try:
                rows = ReservationRows._capture_failure(connection, scope, work)
                operations = [
                    row for row in rows.data["operation"] if row["job_id"] == intent.job_id
                ]
                if len(operations) != 1:
                    raise FailureRefusal("origin_unproved")
                operation_id = operations[0]["id"]
                _absence(connection, scope)
                original = _association(connection, scope, operation_id, configuration)
                fence, after, lease = reservation._prepare_claim(connection, scope, intent, rows)
                if _observe_installed(owner, coordinator) != configuration:
                    raise FailureRefusal("stale_source")
                work.check()
                require_body(connection, scope)
                changed = connection.execute(
                    text(
                        "UPDATE jobs SET status='running', owner=:owner, lease_until=:lease, "
                        "lease_generation=:generation "
                        "WHERE id=:job AND status='queued' AND owner IS NULL "
                        "AND lease_until IS NULL "
                        "AND cancel=:cancel AND lease_generation=:expected "
                        "AND payload_version=2 AND kind='run' "
                        "AND execution_config_ref=:configuration "
                        "AND execution_config_digest=:configuration "
                        "AND error IS NULL AND result IS NULL "
                        "AND NOT EXISTS (SELECT 1 FROM job_failure_evidence WHERE job_id=:job) "
                        "AND EXISTS (SELECT 1 FROM operations WHERE id=:operation AND job_id=:job "
                        "AND project_id=:project AND failure_correlation_id=:origin "
                        "AND execution_config_digest=:configuration AND payload_version=2 "
                        "AND job_resource_kind='job')"
                    ),
                    {
                        "owner": intent.owner_uuid,
                        "lease": lease,
                        "generation": fence.generation,
                        "job": intent.job_id,
                        "cancel": False,
                        "expected": intent.expected_generation,
                        "configuration": configuration.digest,
                        "operation": operation_id,
                        "project": context.project_id,
                        "origin": original[0].row()["failure_correlation_id"],
                    },
                )
                if changed.rowcount != 1:
                    raise FailureRefusal("stale_source")
                reservation.flush_constraints(connection, scope)
                coordinator.authority.check(
                    connection,
                    principal,
                    context,
                    "record",
                    resource_kind="job",
                    resource_id=intent.job_id,
                )
                rows.confirm(connection, after)
                current = _association(connection, scope, operation_id, configuration)
                _same_association(original, current)
                _absence(connection, scope)
                source = ClaimedFailureSource(
                    context.organization_id,
                    context.project_id,
                    fence,
                    *current,
                    configuration.digest,
                    len(configuration.canonical_bytes),
                )
                # Final native body/clock fence; only inherited commit controls follow.
                reservation.require_live_job(connection, scope, fence)
            except MigrationRefused as error:
                raise FailureRefusal(
                    "capacity_exceeded"
                    if error.code in {"ledger_limit_exceeded", "source_limit_exceeded"}
                    else "unsupported_profile"
                ) from None
        facts = TransactionFacts.observe(coordinator._transaction)
        if not facts.commit_acknowledged or facts.cleanup_failed:
            raise FailureRefusal("capability_not_issued")
        token = object.__new__(_AcknowledgedClaim)
        with _LOCK:
            if coordinator in _CLAIMS:
                raise FailureRefusal("invocation_reused")
            _CLAIMS[coordinator] = _ClaimRecord(token, principal, context, configuration, source)
        return token
    except MigrationRefused as error:
        raise FailureRefusal(
            "capacity_exceeded"
            if error.code in {"ledger_limit_exceeded", "source_limit_exceeded"}
            else "unsupported_profile"
        ) from None
    except ReservationRefusal as error:
        raise FailureRefusal(
            "invalid_intent"
            if error.reason == "invalid_intent"
            else "not_eligible"
            if error.reason == "job_not_live"
            else "capacity_exceeded"
            if error.reason == "capacity_exceeded"
            else "unsupported_profile"
            if error.reason == "schema_or_provenance_invalid"
            else "invalid_native_state"
        ) from None
    finally:
        with coordinator._lock:
            coordinator._outcome = TransactionFacts.observe(coordinator._transaction)


class _FailureExecutionOwner:
    """Fixed private owner of a genuine claim; P2 does not install it yet."""

    __slots__ = ("_adapter", "_facts", "__weakref__")

    def __init__(
        self, engine: Engine, authority: RequestAuthority, adapter: DispatchAdapter[Any]
    ) -> None:
        if (
            type(self) is not _FailureExecutionOwner
            or type(authority) is not RequestAuthority
            or authority.engine is not engine
        ):
            raise FailureRefusal("invalid_intent")
        self._adapter = adapter
        self._facts = TransactionFacts(False, False, False, False, False, False)
        with _LOCK:
            _OWNERS[self] = _OwnerState(ReservationCoordinator(engine, authority), id(adapter))

    @property
    def outcome(self) -> TransactionFacts:
        with _LOCK:
            state = _OWNERS.get(self)
            if state is None:
                return self._facts
            return state.coordinator.outcome

    def claim(
        self, principal: VerifiedPrincipal, context: ProjectContext, intent: ClaimIntent
    ) -> JobFence:
        with _LOCK:
            state = _OWNERS.get(self)
            if state is None:
                raise FailureRefusal("capability_not_issued")
            if state.invoked:
                raise FailureRefusal("invocation_reused")
            state.invoked = True
            work = OperationWork(include_acquisition=True)
            state.work = work
            state.coordinator._work = work
        try:
            configuration = _observe_installed(self, state.coordinator)
            work.check()
            token = state.coordinator._claim_for_failure_execution(
                principal,
                context,
                intent,
                owner=self,
                configuration=configuration,
            )
            # The native transaction has already exited. Drift here cannot be
            # relabeled as a post-registration failure or permission to re-claim.
            if _observe_installed(self, state.coordinator) != configuration:
                raise FailureRefusal("stale_source")
            with _LOCK:
                record = _CLAIMS.pop(state.coordinator, None)
                if (
                    _OWNERS.get(self) is not state
                    or record is None
                    or record.token is not token
                    or record.principal is not principal
                    or record.context is not context
                    or record.configuration != configuration
                ):
                    raise FailureRefusal("capability_not_issued")
                record.source.__post_init__()
                # Cleanup is already charged. Keep the same invocation clock and
                # total allowance through registration without new native work.
                work._limits(cleanup=True)
                work.remaining_timeouts_ms()
                state.source = record.source
                return record.source.fence
        finally:
            self._facts = state.coordinator.outcome
            with _LOCK:
                _CLAIMS.pop(state.coordinator, None)

    def close(self) -> None:
        with _LOCK:
            state = _OWNERS.pop(self, None)
            if state is not None:
                _CLAIMS.pop(state.coordinator, None)
                state.source = None
