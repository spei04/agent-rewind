"""Fixed private ar8 paid transitions; every new effect excludes failure evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import and_, case, column, select, table, text
from sqlalchemy.engine import Connection

from .admission_configuration import NativeConfiguration
from .admission_transaction import admission_transaction
from .failure_catalog import _ProducerAuthority, _refresh_producer_authority
from .failure_evidence import FailureRefusal
from .migrations.schema import MigrationRefused
from .operation_work import OperationWork
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .reservation import (
    _clock,
    _dialect,
    _fence,
    _insert,
    _intent,
    _live,
    _original,
    _prepare_claim,
    flush_constraints,
)
from .reservation_checks import money_total, require_budget, require_window, window_on_grid
from .reservation_connection import issued_connection, require_body, require_engine
from .reservation_rows import ReservationRows
from .reservation_types import (
    CallConflict,
    CallMatching,
    ClaimIntent,
    CreatedReservation,
    JobFence,
    JobObservation,
    OriginalReservation,
    ReservationDecision,
    ReservationIntent,
    ReservationRecord,
    ReservationRefusal,
    ReservationScope,
    TransactionFacts,
)
from .scoped_locks import lock_authority
from .scoped_repositories import ProjectContext, _byte_length

if TYPE_CHECKING:
    from .reservation_service import ReservationCoordinator


@dataclass(frozen=True)
class _PaidResult:
    value: JobFence | ReservationDecision
    principal: _ProducerAuthority


def _result(rows: ReservationRows, value: JobFence | ReservationDecision) -> _PaidResult:
    if rows.failure_authority is None:
        raise ReservationRefusal("ledger_state_invalid")
    return _PaidResult(value, rows.failure_authority)


def _absence(connection: Connection, scope: ReservationScope) -> None:
    require_body(connection, scope)
    with connection.execute(
        text("SELECT 1 FROM job_failure_evidence WHERE job_id=:job LIMIT 2"),
        {"job": scope.job_id},
    ) as result:
        if result.all():
            raise FailureRefusal("not_eligible")


def _insert_call(connection: Connection, values: dict[str, Any]) -> None:
    # Same fixed18 fields as the original insertion; no caller SQL/column names.
    statement = """INSERT INTO provider_calls (
      created_at,id,job_account_id,job_id,job_resource_kind,lease_generation,
      logical_call_id,organization_account_id,organization_id,price_version,
      project_account_id,project_id,provider_request_id,purpose,request_digest,
      reserved_microusd,state,usage_estimate_microusd)
    SELECT :created_at,:id,:job_account_id,:job_id,:job_resource_kind,:lease_generation,
      :logical_call_id,:organization_account_id,:organization_id,:price_version,
      :project_account_id,:project_id,:provider_request_id,:purpose,:request_digest,
      :reserved_microusd,:state,:usage_estimate_microusd
    WHERE NOT EXISTS (SELECT 1 FROM job_failure_evidence WHERE job_id=:job_id)"""
    if connection.execute(text(statement), values).rowcount != 1:
        raise ReservationRefusal("job_not_live")


def claim_generation(
    connection: Connection, scope: ReservationScope, intent: ClaimIntent
) -> _PaidResult:
    body = require_body(connection, scope)
    if type(intent) is not ClaimIntent:
        raise ReservationRefusal("invalid_intent")
    intent.__post_init__()
    if intent.job_id != scope.job_id:
        raise ReservationRefusal("invalid_intent")
    rows = ReservationRows._capture_failure(connection, scope, body.work)
    _absence(connection, scope)
    fence, after, lease = _prepare_claim(connection, scope, intent, rows)
    require_body(connection, scope)
    changed = connection.execute(
        text(
            "UPDATE jobs SET status='running', owner=:owner, lease_until=:lease, "
            "lease_generation=:generation "
            "WHERE id=:job AND status='queued' AND owner IS NULL AND lease_until IS NULL "
            "AND cancel=:cancel AND lease_generation=:expected "
            "AND NOT EXISTS (SELECT 1 FROM job_failure_evidence WHERE job_id=:job)"
        ),
        {
            "owner": intent.owner_uuid,
            "lease": lease,
            "generation": fence.generation,
            "job": scope.job_id,
            "cancel": False,
            "expected": intent.expected_generation,
        },
    )
    if changed.rowcount != 1:
        raise ReservationRefusal("job_not_live")
    rows.confirm(connection, after)
    return _result(rows, fence)


def reserve(
    connection: Connection,
    scope: ReservationScope,
    fence: JobFence,
    intent: ReservationIntent,
    *,
    configuration: NativeConfiguration | None = None,
) -> _PaidResult:
    body = require_body(connection, scope)
    _fence(scope, fence)
    _intent(scope, intent)
    rows = ReservationRows._capture_failure(connection, scope, body.work)
    rows.lock_accounts(connection)
    now = _clock(connection)
    rows.reconcile(now)
    if configuration is not None:
        if type(configuration) is not NativeConfiguration:
            raise ReservationRefusal("invalid_intent")
        configuration = NativeConfiguration(
            configuration.canonical_bytes, expected_digest=configuration.digest
        )
        if (
            rows.job["execution_config_digest"] != configuration.digest
            or rows.job["execution_config_ref"] != configuration.digest
            or intent.price_version != json.loads(configuration.canonical_bytes)["price_version"]
        ):
            raise ReservationRefusal("unsupported_job")
    original = _original(rows, intent)
    if isinstance(original, CallMatching):
        return _result(rows, OriginalReservation(original.record))
    if isinstance(original, CallConflict):
        raise ReservationRefusal("identity_conflict")
    _absence(connection, scope)
    if fence.generation != intent.lease_generation:
        raise ReservationRefusal("invalid_intent")
    _live(rows.job, fence, now)
    selected = []
    for family in ("organization", "project", "job"):
        current = []
        for account in rows.affected().values():
            if account["scope"] == family:
                start, end = window_on_grid(
                    account["period_start"], account["period_end"], _dialect(connection)
                )
                if start <= now < end:
                    current.append(account)
        if len(current) != 1:
            raise ReservationRefusal("job_not_live")
        account = current[0]
        if account["id"] != getattr(intent, family + "_account_id"):
            raise ReservationRefusal("invalid_intent")
        prior = [
            row["held_microusd"]
            for row in rows.affected().values()
            if row["scope"] == family and row["period_end"] <= account["period_start"]
        ]
        used = money_total([account["held_microusd"], account["accounted_microusd"], *prior])
        require_budget(used, intent.reserved_microusd, account["limit_microusd"])
        selected.append(account)
    require_budget(rows.job["reserved"], intent.reserved_microusd, rows.job["budget"])
    created = datetime.fromtimestamp(now // 1_000_000, UTC).replace(microsecond=now % 1_000_000)
    stamp = created.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    call = {
        "id": intent.call_id,
        "project_id": intent.project_id,
        "job_id": intent.job_id,
        "logical_call_id": intent.logical_call_id,
        "purpose": intent.purpose,
        "request_digest": intent.request_digest,
        "price_version": intent.price_version,
        "state": "reserved",
        "reserved_microusd": intent.reserved_microusd,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": stamp,
        "organization_id": scope.context.organization_id,
        "job_resource_kind": "job",
        "lease_generation": intent.lease_generation,
        "organization_account_id": intent.organization_account_id,
        "project_account_id": intent.project_account_id,
        "job_account_id": intent.job_account_id,
    }
    entries = [
        {
            "call_id": intent.call_id,
            "account_id": account["id"],
            "entry_kind": "reserve",
            "amount_microusd": intent.reserved_microusd,
            "evidence_ref": None,
            "created_at": stamp,
            "project_id": intent.project_id,
            "evidence_owner_kind": "provider_call",
            "evidence_role": "budget_evidence",
        }
        for account in selected
    ]
    scope_row = {
        "resource_kind": "provider_call",
        "resource_id": intent.call_id,
        "project_id": intent.project_id,
    }
    after = rows.after_image()
    after["call"].append(call)
    after["scope"].append(scope_row)
    after["entry"].extend(entries)
    changes = {
        account["id"]: money_total([account["held_microusd"], intent.reserved_microusd])
        for account in selected
    }
    for account in after["account"]:
        if account["id"] in changes:
            account["held_microusd"] = changes[account["id"]]
    gross = money_total([rows.job["reserved"], intent.reserved_microusd])
    next(row for row in after["job"] if row["id"] == scope.job_id)["reserved"] = gross
    rows.require_headroom(after)
    require_body(connection, scope)
    native_time = created if connection.dialect.name == "postgresql" else stamp
    _insert_call(connection, {**call, "created_at": native_time})
    _insert(connection, "resource_scopes", scope_row)
    for entry in entries:
        _insert(connection, "budget_entries", {**entry, "created_at": native_time})
    for account in sorted(selected, key=lambda value: value["id"]):
        changed = connection.execute(
            text(
                "UPDATE budget_accounts SET held_microusd=:held WHERE id=:id "
                "AND held_microusd=:old AND accounted_microusd=:accounted"
            ),
            {
                "held": changes[account["id"]],
                "id": account["id"],
                "old": account["held_microusd"],
                "accounted": account["accounted_microusd"],
            },
        )
        if changed.rowcount != 1:
            raise ReservationRefusal("ledger_state_invalid")
    changed = connection.execute(
        text(
            "UPDATE jobs SET reserved=:gross WHERE id=:job AND reserved=:old AND owner=:owner "
            "AND lease_generation=:generation AND status='running' AND cancel=:cancel "
            "AND NOT EXISTS (SELECT 1 FROM job_failure_evidence WHERE job_id=:job)"
        ),
        {
            "gross": gross,
            "job": scope.job_id,
            "old": rows.job["reserved"],
            "owner": fence.owner_uuid,
            "generation": fence.generation,
            "cancel": False,
        },
    )
    if changed.rowcount != 1:
        raise ReservationRefusal("job_not_live")
    rows.confirm(connection, after)
    return _result(rows, CreatedReservation(ReservationRecord(intent, "reserved", 0, 0)))


def final_fence(
    connection: Connection,
    scope: ReservationScope,
    fence: JobFence,
    identity: ReservationIntent | None,
) -> None:
    require_body(connection, scope)
    _fence(scope, fence)
    if identity is not None:
        _intent(scope, identity)
        if identity.lease_generation != fence.generation:
            raise ReservationRefusal("invalid_intent")
    # Account windows are immutable after accepted P1; the original selection is
    # rechecked at the final fresh database tick, never rolled to another period.
    job = table(
        "jobs",
        *(
            column(name)
            for name in ("id", "owner", "status", "cancel", "lease_until", "lease_generation")
        ),
    )
    account = table(
        "budget_accounts",
        *(
            column(name)
            for name in ("id", "organization_id", "scope", "job_id", "period_start", "period_end")
        ),
    )
    values = {
        "owner": job.c.owner,
        "status": job.c.status,
        "cancel": job.c.cancel,
        "lease_until": job.c.lease_until,
        "lease_generation": job.c.lease_generation,
        "account_id": account.c.id,
        "period_start": account.c.period_start,
        "period_end": account.c.period_end,
    }
    limits = {
        "owner": 32,
        "status": 10,
        "cancel": 5,
        "lease_until": 64,
        "lease_generation": 20,
        "account_id": 32,
        "period_start": 40,
        "period_end": 40,
    }
    safe = and_(
        *(
            value.is_(None) | (_byte_length(connection, value) <= limits[name])
            for name, value in values.items()
        )
    )
    evidence = table("job_failure_evidence", column("job_id"))
    present = select(evidence.c.job_id).where(evidence.c.job_id == scope.job_id).exists()
    statement = (
        select(
            safe.label("valid"),
            present.label("failure_present"),
            *(case((safe, value), else_=None).label(name) for name, value in values.items()),
        )
        .select_from(job.join(account, account.c.organization_id == scope.context.organization_id))
        .where(job.c.id == scope.job_id)
    )
    if identity is None:
        statement = statement.where(
            account.c.scope == "job", account.c.job_id == scope.job_id
        ).limit(2)
    else:
        statement = (
            statement.where(
                account.c.id.in_(
                    [
                        identity.organization_account_id,
                        identity.project_account_id,
                        identity.job_account_id,
                    ]
                )
            )
            .order_by(account.c.id)
            .limit(4)
        )
    observed = [dict(row) for row in connection.execute(statement).mappings()]
    for row in observed:
        failure_present = row.pop("failure_present")
        if type(failure_present) not in (bool, int) or failure_present not in (False, 0):
            raise FailureRefusal("not_eligible")
        if row.pop("valid") not in (True, 1):
            raise ReservationRefusal("ledger_state_invalid")
        try:
            JobObservation(
                scope.job_id,
                row["owner"],
                row["lease_generation"],
                row["status"],
                row["lease_until"],
            )
        except ReservationRefusal:
            raise ReservationRefusal("ledger_state_invalid") from None
    if len(observed) != (1 if identity is None else 3):
        raise ReservationRefusal("ledger_state_invalid")
    require_body(connection, scope)
    now = _clock(connection)
    for row in observed:
        _live(row, fence, now)
        for name in ("period_start", "period_end"):
            value = row[name]
            if isinstance(value, datetime):
                row[name] = value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        require_window(now, row["period_start"], row["period_end"], _dialect(connection))


def run_successor(
    coordinator: ReservationCoordinator,
    mode: Literal["claim", "reserve"],
    principal: VerifiedPrincipal,
    context: ProjectContext,
    *,
    claim: ClaimIntent | None = None,
    fence: JobFence | None = None,
    identity: ReservationIntent | None = None,
    job_id: str | None = None,
    configuration: NativeConfiguration | None = None,
) -> JobFence | ReservationDecision:
    work = OperationWork(include_acquisition=True)
    if mode not in ("claim", "reserve"):
        raise ReservationRefusal("invalid_intent")
    with coordinator._lock:
        if coordinator._consumed:
            raise ReservationRefusal("invocation_reused")
        coordinator._consumed = True
        coordinator._work = work
    try:
        if (
            not isinstance(coordinator.authority, RequestAuthority)
            or coordinator.authority.engine is not coordinator.engine
        ):
            raise ReservationRefusal("invalid_intent")
        coordinator.authority._principal(principal)
        require_engine(coordinator.engine)
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
        action: Literal["record"] = "record"
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
                job_id,
                exclusive_organization=True,
            )
            coordinator.authority.check(
                connection,
                principal,
                context,
                action,
                resource_kind="job",
                resource_id=job_id,
            )
            try:
                tentative: _PaidResult
                if mode == "claim" and claim is not None:
                    tentative = claim_generation(connection, scope, claim)
                elif mode == "reserve" and fence is not None and identity is not None:
                    tentative = reserve(
                        connection, scope, fence, identity, configuration=configuration
                    )
                else:
                    raise ReservationRefusal("invalid_intent")
                result = tentative.value
                # Deferred/FK work precedes the final authority and DB-time
                # fence. A later COMMIT may still cross a wall-clock expiry.
                if isinstance(result, JobFence | CreatedReservation):
                    flush_constraints(connection, scope)
                else:
                    require_body(connection, scope)
                coordinator.authority.check(
                    connection,
                    principal,
                    context,
                    action if isinstance(result, JobFence | CreatedReservation) else "read",
                    resource_kind="job",
                    resource_id=job_id,
                )
                _refresh_producer_authority(connection, scope, tentative.principal)
                if isinstance(result, JobFence):
                    final_fence(connection, scope, result, None)
                elif (
                    isinstance(result, CreatedReservation)
                    and fence is not None
                    and identity is not None
                ):
                    final_fence(connection, scope, fence, identity)
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
        with coordinator._lock:
            coordinator._outcome = TransactionFacts.observe(coordinator._transaction)
