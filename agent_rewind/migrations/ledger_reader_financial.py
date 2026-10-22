"""Complete bounded financial projections and their relational proof."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, NoReturn

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..admission_records import OPERATION_LIMITS, AdmissionStorageError, operation_value
from ..artifact_metadata import ArtifactError, _object
from ..operation_reads import (
    DESCRIPTOR_FIELDS,
    JOB_LIMITS,
    RawReceipt,
    validate_association,
    validate_job_row,
)
from .ledger_financial_sql import SQL
from .ledger_inputs import MAX_MONEY
from .ledger_reader_history import History
from .ledger_work import LedgerWork
from .schema import LEDGER, MigrationRefused, canonical, dialect

CAP = 2097152
_ORDER = (
    "account",
    "call",
    "entry",
    "job",
    "operation",
    "scope",
    "ref",
    "object",
    "project",
    "organization",
)
# Exact ordered financial projections are separate from original-source transport.
_FIELDS = {
    ("ar6", "job"): (
        "id",
        "kind",
        "created",
        "payload",
        "status",
        "owner",
        "lease_until",
        "cancel",
        "budget",
        "reserved",
        "result",
        "error",
        "actor",
        "payload_version",
        "execution_config_ref",
        "execution_config_digest",
    ),
    ("ar6", "object"): (
        "id",
        "project_id",
        "digest",
        "locator",
        "format_version",
        "byte_count",
        "created_at",
    ),
    ("ar6", "operation"): (
        "id",
        "project_id",
        "principal_id",
        "kind",
        "client_operation_id",
        "request_digest",
        "job_id",
        "accepted_response",
        "created_at",
        "retain_until",
        "job_resource_kind",
        "execution_config_digest",
        "payload_version",
        "failure_correlation_id",
    ),
    ("ar6", "organization"): ("id", "installation_key"),
    ("ar6", "project"): ("id", "organization_id"),
    ("ar6", "ref"): ("project_id", "owner_kind", "owner_id", "artifact_id", "role"),
    ("ar6", "scope"): ("resource_kind", "resource_id", "project_id"),
    ("ar7", "account"): (
        "id",
        "organization_id",
        "scope",
        "scope_id",
        "period_start",
        "period_end",
        "limit_microusd",
        "held_microusd",
        "accounted_microusd",
        "project_id",
        "job_id",
        "opening_held_microusd",
    ),
    ("ar7", "call"): (
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
    ),
    ("ar7", "entry"): (
        "call_id",
        "account_id",
        "entry_kind",
        "amount_microusd",
        "evidence_ref",
        "created_at",
        "project_id",
        "evidence_owner_kind",
        "evidence_role",
    ),
    ("ar7", "job"): (
        "id",
        "kind",
        "created",
        "payload",
        "status",
        "owner",
        "lease_until",
        "cancel",
        "budget",
        "reserved",
        "result",
        "error",
        "actor",
        "payload_version",
        "execution_config_ref",
        "execution_config_digest",
        "lease_generation",
        "legacy_reserved_microusd",
    ),
    ("ar7", "object"): (
        "id",
        "project_id",
        "digest",
        "locator",
        "format_version",
        "byte_count",
        "created_at",
    ),
    ("ar7", "operation"): (
        "id",
        "project_id",
        "principal_id",
        "kind",
        "client_operation_id",
        "request_digest",
        "job_id",
        "accepted_response",
        "created_at",
        "retain_until",
        "job_resource_kind",
        "execution_config_digest",
        "payload_version",
        "failure_correlation_id",
    ),
    ("ar7", "organization"): ("id", "installation_key"),
    ("ar7", "project"): ("id", "organization_id"),
    ("ar7", "ref"): ("project_id", "owner_kind", "owner_id", "artifact_id", "role"),
    ("ar7", "scope"): ("resource_kind", "resource_id", "project_id"),
}
_TIMES = {
    "account": ("period_start", "period_end"),
    "call": ("created_at",),
    "entry": ("created_at",),
    "object": ("created_at",),
    "operation": ("created_at", "retain_until"),
}


def _time(value: Any) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("financial timestamp")
    value = value.astimezone(UTC)
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}.{value.microsecond:06d}Z"
    )


def _refuse() -> NoReturn:
    raise MigrationRefused("ledger_history_unsupported")


def _query(connection: Connection, revision: str, name: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(text(SQL[(revision, dialect(connection), name)])).mappings()
    ]


def read_financial(
    connection: Connection, revision: str, work: LedgerWork
) -> dict[str, list[dict[str, Any]]]:
    key = "ar7" if revision == LEDGER else "ar6"
    base = (
        ("account", "call", "entry", "job", "operation", "scope", "organization")
        if key == "ar7"
        else ("job", "operation", "scope", "organization")
    )
    receipts: dict[str, dict[str, Any]] = {}
    native_bytes = total_rows = 0

    def gate(domain: str, prefix: str) -> None:
        nonlocal native_bytes, total_rows
        work.check()
        rows = _query(connection, key, prefix + "_gate")
        if len(rows) != 1 or set(rows[0]) != {"candidate_rows", "invalid_rows", "native_bytes"}:
            _refuse()
        receipt = rows[0]
        if any(type(value) is not int or value < 0 for value in receipt.values()):
            _refuse()
        if receipt["candidate_rows"] > (4096 if domain == "account" else 65536):
            raise MigrationRefused("ledger_limit_exceeded")
        if receipt["invalid_rows"] or (domain == "organization" and receipt["candidate_rows"] != 1):
            _refuse()
        total_rows += receipt["candidate_rows"]
        native_bytes += receipt["native_bytes"]
        if total_rows > 65536 or native_bytes > CAP:
            raise MigrationRefused("ledger_limit_exceeded")
        receipts[domain] = receipt

    for domain in base:
        gate(domain, "financial_base_" + domain)
    owners = _query(connection, key, "financial_owner_gate")
    if (
        len(owners) != 1
        or set(owners[0]) != {"owner_rows", "invalid_rows"}
        or any(type(value) is not int for value in owners[0].values())
        or owners[0]["invalid_rows"] != 0
        or owners[0]["owner_rows"]
        != receipts["job"]["candidate_rows"]
        + receipts.get("call", {"candidate_rows": 0})["candidate_rows"]
    ):
        _refuse()
    for domain in ("ref", "object", "project"):
        gate(domain, "financial_" + domain)
    # Every financial domain is preflighted before the first financial or graph job body.
    result: dict[str, list[dict[str, Any]]] = {}
    canonical_bytes, frames = 2, 0
    for domain in _ORDER:
        if domain not in receipts:
            result[domain] = []
            continue
        prefix = "financial_base_" if domain in base else "financial_"
        rows = _query(connection, key, prefix + domain + "_body")
        fields = _FIELDS[(key, domain)]
        if len(rows) != receipts[domain]["candidate_rows"]:
            _refuse()
        for row in rows:
            work.check()
            if set(row) != {*fields, "invalid"} or row.pop("invalid") != 0:
                _refuse()
            try:
                for field in _TIMES.get(domain, ()):
                    row[field] = _time(row[field])
                # Native bytes were bounded by SQL. Canonical UTF-8 is a distinct bound.
                frame = canonical([domain, [row[field] for field in fields]])
            except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
                raise MigrationRefused("ledger_history_unsupported") from None
            canonical_bytes += len(frame) + bool(frames)
            frames += 1
            if canonical_bytes > CAP:
                raise MigrationRefused("ledger_limit_exceeded")
        result[domain] = rows
    return result


def _indexed(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    result = {row[field]: row for row in rows}
    if len(result) != len(rows):
        _refuse()
    return result


def validate_financial(
    data: dict[str, list[dict[str, Any]]],
    history: History,
    work: LedgerWork,
) -> None:
    """Validate retained relationships, not initialization eligibility or invoices."""
    organization = history.ownership.organization_id
    if data["organization"] != [
        {"id": organization, "installation_key": history.adoption["installation_key"]}
    ]:
        _refuse()
    projects = _indexed(data["project"], "id")
    if any(row["organization_id"] != organization for row in projects.values()):
        _refuse()
    jobs = _indexed(data["job"], "id")
    calls = _indexed(data["call"], "id")
    accounts = _indexed(data["account"], "id")
    scopes = {
        (row["resource_kind"], row["resource_id"]): row["project_id"] for row in data["scope"]
    }
    if len(scopes) != len(data["scope"]) or set(scopes) != {
        *(("job", key) for key in jobs),
        *(("provider_call", key) for key in calls),
    }:
        _refuse()
    if any(project not in projects for project in scopes.values()):
        _refuse()
    descriptors = _indexed(data["object"], "id")
    references: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    ref_keys = set()
    for row in data["ref"]:
        work.check()
        owner = (row["owner_kind"], row["owner_id"])
        if scopes.get(owner) != row["project_id"]:
            _refuse()
        key = (row["project_id"], *owner, row["artifact_id"], row["role"])
        if key in ref_keys:
            _refuse()
        ref_keys.add(key)
        references[(*owner, row["role"])].append(row)
    required_objects = {
        row["artifact_id"]
        for row in data["ref"]
        if row["role"] in {"admission_config", "budget_evidence"}
    }
    if required_objects != set(descriptors):
        _refuse()
    for row in data["ref"]:
        if row["role"] not in {"admission_config", "budget_evidence"}:
            continue
        descriptor = descriptors[row["artifact_id"]]
        if descriptor["project_id"] != row["project_id"]:
            _refuse()
        try:
            _object(descriptor)
        except (ArtifactError, ValueError, TypeError, KeyError):
            _refuse()
    operations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data["operation"]:
        work.check()
        try:
            value = operation_value(row)
        except (AdmissionStorageError, ValueError, TypeError, KeyError):
            _refuse()
        if value.job_id not in jobs or scopes.get(("job", value.job_id)) != value.project_id:
            _refuse()
        operations[value.job_id].append(row)
    for job in jobs.values():
        work.check()
        if job["payload_version"] == 1:
            if (
                job["execution_config_ref"] is not None
                or job["execution_config_digest"] is not None
                or operations[job["id"]]
            ):
                _refuse()
            continue
        matched = operations[job["id"]]
        refs = references[("job", job["id"], "admission_config")]
        if len(matched) != 1 or len(refs) != 1:
            _refuse()
        config = {**descriptors[refs[0]["artifact_id"]], "reference_id": refs[0]["artifact_id"]}
        try:
            job_receipt = validate_job_row({name: job[name] for name in JOB_LIMITS}, job["id"])
            op = matched[0]
            validate_association(
                RawReceipt(
                    "operation",
                    op["id"],
                    tuple(OPERATION_LIMITS),
                    tuple(op[name] for name in OPERATION_LIMITS),
                ),
                job_receipt,
                RawReceipt(
                    "admission_config",
                    job["id"],
                    (*DESCRIPTOR_FIELDS, "reference_id"),
                    tuple(config[name] for name in (*DESCRIPTOR_FIELDS, "reference_id")),
                ),
            )
        except (AdmissionStorageError, ArtifactError, ValueError, TypeError, KeyError):
            _refuse()
    if history.opening is None:
        if accounts or calls or data["entry"]:
            _refuse()
        return
    _validate_accounts(accounts, jobs, scopes, projects, history, work)
    _validate_calls(
        calls, accounts, jobs, scopes, projects, data["entry"], ref_keys, organization, work
    )


def _validate_accounts(
    accounts: dict[str, dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    scopes: dict[tuple[str, str], str],
    projects: dict[str, dict[str, Any]],
    history: History,
    work: LedgerWork,
) -> None:
    opening = history.opening
    if opening is None:
        _refuse()
        return
    expected: dict[str, dict[str, Any]] = {}
    opening_jobs = {row.job_id: row for row in opening.jobs}
    initial = history.manifests[0]
    job_accounts = {row.job_id: row.id for row in initial.manifest.accounts if row.scope == "job"}
    exposure = {row.account_id: row.opening_held_microusd for row in opening.project_totals}
    exposure.update(
        (job_accounts[key], row.legacy_reserved_microusd) for key, row in opening_jobs.items()
    )
    if opening.organization_account_id is not None:
        exposure[opening.organization_account_id] = opening.organization_opening_microusd
    for cursor in history.manifests:
        for value in cursor.manifest.accounts:
            work.check()
            expected[value.id] = {
                **value.model_dump(mode="json"),
                "opening_held_microusd": exposure.get(value.id, 0),
            }
    if set(expected) != set(accounts):
        _refuse()
    for identity, row in accounts.items():
        work.check()
        if any(row[field] != value for field, value in expected[identity].items()):
            _refuse()
        if row["organization_id"] != history.ownership.organization_id or (
            row["project_id"] is not None and row["project_id"] not in projects
        ):
            _refuse()
        if row["scope"] == "job":
            job = jobs.get(row["job_id"])
            if job is None or scopes.get(("job", row["job_id"])) != row["project_id"]:
                _refuse()
            if row["limit_microusd"] > job["budget"]:
                raise MigrationRefused("ledger_exposure_refused")
    for identity, job in jobs.items():
        work.check()
        imported = opening_jobs.get(identity)
        if imported is None:
            if job["legacy_reserved_microusd"] != 0:
                _refuse()
        elif (
            job["legacy_reserved_microusd"] != imported.legacy_reserved_microusd
            or scopes.get(("job", identity)) != imported.project_id
        ):
            _refuse()
    if not set(opening_jobs) <= set(jobs):
        _refuse()


def _validate_calls(
    calls: dict[str, dict[str, Any]],
    accounts: dict[str, dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    scopes: dict[tuple[str, str], str],
    projects: dict[str, dict[str, Any]],
    entries: list[dict[str, Any]],
    ref_keys: set[tuple[Any, ...]],
    organization: str,
    work: LedgerWork,
) -> None:
    cohorts: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    entry_keys = set()
    for row in entries:
        work.check()
        call = calls.get(row["call_id"])
        key = (row["call_id"], row["account_id"], row["entry_kind"])
        if key in entry_keys or call is None or row["project_id"] != call["project_id"]:
            _refuse()
        entry_keys.add(key)
        if (
            row["evidence_ref"] is not None
            and (
                row["project_id"],
                "provider_call",
                row["call_id"],
                row["evidence_ref"],
                "budget_evidence",
            )
            not in ref_keys
        ):
            _refuse()
        cohorts[row["call_id"]][row["entry_kind"]].append(row)
    logical = set()
    for identity, call in calls.items():
        work.check()
        job = jobs.get(call["job_id"])
        logical_key = (call["project_id"], call["logical_call_id"])
        if (
            logical_key in logical
            or job is None
            or call["organization_id"] != organization
            or call["project_id"] not in projects
            or scopes.get(("job", call["job_id"])) != call["project_id"]
            or scopes.get(("provider_call", identity)) != call["project_id"]
            or call["lease_generation"] > job["lease_generation"]
        ):
            _refuse()
        logical.add(logical_key)
        triple = [call[name + "_account_id"] for name in ("organization", "project", "job")]
        if len(set(triple)) != 3 or any(key not in accounts for key in triple):
            _refuse()
        for scope, scope_id, account_id in zip(
            ("organization", "project", "job"),
            (organization, call["project_id"], call["job_id"]),
            triple,
            strict=True,
        ):
            account = accounts[account_id]
            if (
                account["scope"] != scope
                or account["scope_id"] != scope_id
                or account["organization_id"] != organization
                or (scope != "organization" and account["project_id"] != call["project_id"])
                or not account["period_start"] <= call["created_at"] < account["period_end"]
            ):
                _refuse()
        amounts = {}
        for kind in ("reserve", "settle", "release"):
            rows = cohorts[identity].get(kind, [])
            if not rows and kind != "reserve":
                amounts[kind] = 0
                continue
            if (
                len(rows) != 3
                or {row["account_id"] for row in rows} != set(triple)
                or len({row["amount_microusd"] for row in rows}) != 1
            ):
                _refuse()
            amounts[kind] = rows[0]["amount_microusd"]
        if amounts["reserve"] != call["reserved_microusd"]:
            _refuse()
        if (
            amounts["settle"] + amounts["release"] > MAX_MONEY
            or amounts["settle"] + amounts["release"] > call["reserved_microusd"]
        ):
            raise MigrationRefused("ledger_exposure_refused")
