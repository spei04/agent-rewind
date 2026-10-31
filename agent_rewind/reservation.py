"""Connection-bound P2 transitions; tentative results never permit dispatch."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, column, select, table, text
from sqlalchemy.engine import Connection

from .admission_configuration import NativeConfiguration
from .migrations.ledger_schema import TRIGGERS
from .reservation_checks import (
    Dialect,
    database_tick,
    lease_live,
    money_total,
    new_lease,
    require_budget,
    require_window,
    window_on_grid,
)
from .reservation_connection import require_body
from .reservation_rows import ReservationRows
from .reservation_types import (
    CallAbsent,
    CallConflict,
    CallMatching,
    CallNotRequested,
    CallObservation,
    ClaimIntent,
    CreatedReservation,
    InspectionResult,
    JobFence,
    JobObservation,
    OriginalReservation,
    ReservationDecision,
    ReservationIntent,
    ReservationRecord,
    ReservationRefusal,
    ReservationScope,
)
from .scoped_repositories import _byte_length


def _clock(connection: Connection) -> int:
    if connection.dialect.name == "postgresql":
        value: Any = connection.exec_driver_sql(
            """SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')"""
        ).scalar_one()
        return database_tick(value, "postgresql")
    value = connection.exec_driver_sql("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").scalar_one()
    return database_tick(value, "sqlite")


def _dialect(connection: Connection) -> Dialect:
    if connection.dialect.name == "sqlite":
        return "sqlite"
    if connection.dialect.name == "postgresql":
        return "postgresql"
    raise ReservationRefusal("transaction_not_owned")


def _intent(scope: ReservationScope, intent: ReservationIntent) -> None:
    if type(intent) is not ReservationIntent:
        raise ReservationRefusal("invalid_intent")
    intent.__post_init__()
    if intent.job_id != scope.job_id or intent.project_id != scope.context.project_id:
        raise ReservationRefusal("invalid_intent")


def _fence(scope: ReservationScope, fence: JobFence) -> None:
    if type(fence) is not JobFence:
        raise ReservationRefusal("invalid_intent")
    fence.__post_init__()
    if fence.job_id != scope.job_id:
        raise ReservationRefusal("invalid_intent")


def _live(job: dict[str, Any], fence: JobFence, now: int) -> None:
    if (
        job["status"] != "running"
        or job["cancel"] not in (False, 0)
        or type(job["cancel"]) not in (bool, int)
        or job["owner"] != fence.owner_uuid
        or job["lease_generation"] != fence.generation
        or not lease_live(job["lease_until"], now)
    ):
        raise ReservationRefusal("job_not_live")


def _job_account(rows: ReservationRows) -> dict[str, Any]:
    accounts = [row for row in rows.affected().values() if row["scope"] == "job"]
    if len(accounts) != 1:
        raise ReservationRefusal("ledger_state_invalid")
    return accounts[0]


def _prepare_claim(
    connection: Connection, scope: ReservationScope, intent: ClaimIntent, rows: ReservationRows
) -> tuple[JobFence, dict[str, list[dict[str, Any]]], float]:
    rows.lock_accounts(connection)
    now = _clock(connection)
    rows.reconcile(now)
    job, account = rows.job, _job_account(rows)
    if (
        job["status"] != "queued"
        or job["owner"] is not None
        or job["lease_until"] is not None
        or job["cancel"] not in (False, 0)
        or type(job["cancel"]) not in (bool, int)
        or job["lease_generation"] != intent.expected_generation
    ):
        raise ReservationRefusal("job_not_live")
    require_window(now, account["period_start"], account["period_end"], _dialect(connection))
    _, end = window_on_grid(account["period_start"], account["period_end"], _dialect(connection))
    lease = new_lease(now, intent.lease_seconds, end)
    fence = JobFence(scope.job_id, intent.owner_uuid, intent.expected_generation + 1)
    after = rows.after_image()
    new = next(row for row in after["job"] if row["id"] == scope.job_id)
    new.update(
        status="running",
        owner=intent.owner_uuid,
        lease_until=lease,
        lease_generation=fence.generation,
    )
    rows.require_headroom(after)
    return fence, after, lease


def claim_generation(
    connection: Connection, scope: ReservationScope, intent: ClaimIntent
) -> JobFence:
    body = require_body(connection, scope)
    if type(intent) is not ClaimIntent:
        raise ReservationRefusal("invalid_intent")
    intent.__post_init__()
    if intent.job_id != scope.job_id:
        raise ReservationRefusal("invalid_intent")
    rows = ReservationRows.capture(connection, scope, body.work)
    fence, after, lease = _prepare_claim(connection, scope, intent, rows)
    require_body(connection, scope)
    changed = connection.execute(
        text(
            "UPDATE jobs SET status='running', owner=:owner, lease_until=:lease, "
            "lease_generation=:generation "
            "WHERE id=:job AND status='queued' AND owner IS NULL AND lease_until IS NULL "
            "AND cancel=:cancel AND lease_generation=:expected"
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
    return fence


def _record(rows: ReservationRows, call: dict[str, Any]) -> ReservationRecord:
    identity = ReservationIntent(
        **{
            field.name: call["id" if field.name == "call_id" else field.name]
            for field in fields(ReservationIntent)
        }
    )
    amounts: dict[str, int] = {}
    for kind in ("settle", "release"):
        entries = [
            row
            for row in rows.data["entry"]
            if row["call_id"] == call["id"] and row["entry_kind"] == kind
        ]
        amounts[kind] = entries[0]["amount_microusd"] if entries else 0
    return ReservationRecord(identity, call["state"], amounts["settle"], amounts["release"])


def _original(rows: ReservationRows, identity: ReservationIntent) -> CallObservation:
    matches = [
        row
        for row in rows.data["call"]
        if row["id"] == identity.call_id
        or (
            row["project_id"] == identity.project_id
            and row["logical_call_id"] == identity.logical_call_id
        )
    ]
    if not matches:
        return CallAbsent()
    if (
        len(matches) != 1
        or matches[0]["job_id"] != identity.job_id
        or matches[0]["project_id"] != identity.project_id
    ):
        return CallConflict()
    call = matches[0]
    for field in fields(ReservationIntent):
        native = call["id" if field.name == "call_id" else field.name]
        expected = getattr(identity, field.name)
        if type(native) is not type(expected) or native != expected:
            return CallConflict()
    return CallMatching(_record(rows, call))


def inspect_original(
    connection: Connection, scope: ReservationScope, identity: ReservationIntent | None
) -> InspectionResult:
    body = require_body(connection, scope)
    if identity is not None:
        _intent(scope, identity)
    rows = ReservationRows.capture(connection, scope, body.work)
    rows.lock_accounts(connection)
    rows.reconcile(_clock(connection))
    job = rows.job
    return InspectionResult(
        JobObservation(
            job["id"], job["owner"], job["lease_generation"], job["status"], job["lease_until"]
        ),
        CallNotRequested() if identity is None else _original(rows, identity),
    )


def reserve(
    connection: Connection,
    scope: ReservationScope,
    fence: JobFence,
    intent: ReservationIntent,
    *,
    configuration: NativeConfiguration | None = None,
) -> ReservationDecision:
    body = require_body(connection, scope)
    _fence(scope, fence)
    _intent(scope, intent)
    rows = ReservationRows.capture(connection, scope, body.work)
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
        return OriginalReservation(original.record)
    if isinstance(original, CallConflict):
        raise ReservationRefusal("identity_conflict")
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
    _insert(connection, "provider_calls", {**call, "created_at": native_time})
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
            "AND lease_generation=:generation AND status='running' AND cancel=:cancel"
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
    return CreatedReservation(ReservationRecord(intent, "reserved", 0, 0))


def _insert(connection: Connection, table: str, values: dict[str, Any]) -> None:
    # Only these fixed in-module constructions call this private helper.
    allowed = {
        "provider_calls": {
            "id",
            "project_id",
            "job_id",
            "logical_call_id",
            "purpose",
            "request_digest",
            "price_version",
            "state",
            "reserved_microusd",
            "usage_estimate_microusd",
            "provider_request_id",
            "created_at",
            "organization_id",
            "job_resource_kind",
            "lease_generation",
            "organization_account_id",
            "project_account_id",
            "job_account_id",
        },
        "resource_scopes": {"resource_kind", "resource_id", "project_id"},
        "budget_entries": {
            "call_id",
            "account_id",
            "entry_kind",
            "amount_microusd",
            "evidence_ref",
            "created_at",
            "project_id",
            "evidence_owner_kind",
            "evidence_role",
        },
    }
    if table not in allowed or set(values) != allowed[table]:
        raise ReservationRefusal("ledger_state_invalid")
    statements = {
        "provider_calls": (
            "INSERT INTO provider_calls (created_at,id,job_account_id,job_id,job_resource_kin"
            "d,lease_generation,logical_call_id,organization_account_id,organization_id,price"
            "_version,project_account_id,project_id,provider_request_id,purpose,request_diges"
            "t,reserved_microusd,state,usage_estimate_microusd) VALUES (:created_at,:id,:job_"
            "account_id,:job_id,:job_resource_kind,:lease_generation,:logical_call_id,:organi"
            "zation_account_id,:organization_id,:price_version,:project_account_id,:project_i"
            "d,:provider_request_id,:purpose,:request_digest,:reserved_microusd,:state,:usage"
            "_estimate_microusd)"
        ),
        "resource_scopes": (
            "INSERT INTO resource_scopes (project_id,resource_id,resource_kind) VALUES (:proj"
            "ect_id,:resource_id,:resource_kind)"
        ),
        "budget_entries": (
            "INSERT INTO budget_entries (account_id,amount_microusd,call_id,created_at,entry_"
            "kind,evidence_owner_kind,evidence_ref,evidence_role,project_id) VALUES (:account"
            "_id,:amount_microusd,:call_id,:created_at,:entry_kind,:evidence_owner_kind,:evid"
            "ence_ref,:evidence_role,:project_id)"
        ),
    }
    statement = statements[table]
    if connection.execute(text(statement), values).rowcount != 1:
        raise ReservationRefusal("ledger_state_invalid")


def flush_constraints(connection: Connection, scope: ReservationScope) -> None:
    require_body(connection, scope)
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET CONSTRAINTS " + ", ".join(TRIGGERS) + " IMMEDIATE")


def require_live_job(connection: Connection, scope: ReservationScope, fence: JobFence) -> None:
    final_fence(connection, scope, fence, None)


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
    statement = (
        select(
            safe.label("valid"),
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
