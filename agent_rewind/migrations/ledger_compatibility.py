"""Immutable ar7 provenance for the non-ready runtime compatibility check.

This check-only kernel grants no operator body rights and does not validate
current balances, calls, entries, or graph health.
"""

from __future__ import annotations

from typing import Any, NoReturn

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .ledger_check import LedgerCheck
from .ledger_compatibility_sql import SQL
from .ledger_inputs import MAX_MONEY, LedgerAccount
from .ledger_reader_catalog import inspect_catalog
from .ledger_reader_history import History, read_history, read_revision
from .schema import LEDGER, MigrationRefused, canonical, checksum, dialect

_ACCOUNT_FIELDS = (
    "id",
    "organization_id",
    "scope",
    "scope_id",
    "project_id",
    "job_id",
    "period_start",
    "period_end",
    "limit_microusd",
    "opening_held_microusd",
)
_JOB_FIELDS = ("job_id", "project_id", "organization_id", "legacy_reserved_microusd")
_STATS = ("candidate_rows", "invalid_rows", "native_bytes", "utf8_bytes")


def _refuse() -> NoReturn:
    raise MigrationRefused("ledger_progress_invalid")


def _query(
    connection: Connection, name: str, parameters: dict[str, Any], checks: LedgerCheck
) -> list[dict[str, Any]]:
    checks.check()
    prefix = "pg" if dialect(connection) == "postgresql" else "sqlite"
    result = connection.execute(text(SQL[prefix + "_" + name]), parameters)
    checks.check()
    rows = [dict(row) for row in result.mappings()]
    checks.check()
    return rows


def _read(
    connection: Connection,
    family: str,
    parameters: dict[str, Any],
    checks: LedgerCheck,
    *,
    expected_count: int,
) -> list[dict[str, Any]]:
    accounts = family == "immutable_accounts"
    maximum = 4096 if accounts else 12
    per_row = 255 if accounts else 115
    fields = _ACCOUNT_FIELDS if accounts else _JOB_FIELDS
    field_names = set(fields)
    field_rules = tuple(
        (field, field.endswith("microusd"), accounts and field in {"project_id", "job_id"})
        for field in fields
    )
    gate = _query(connection, family + "_gate", parameters, checks)
    if (
        len(gate) != 1
        or set(gate[0]) != set(_STATS)
        or any(type(gate[0][key]) is not int or gate[0][key] < 0 for key in _STATS)
    ):
        _refuse()
    stats = gate[0]
    count = stats["candidate_rows"]
    if (
        count != expected_count
        or count > maximum
        or stats["invalid_rows"] != 0
        or stats["native_bytes"] > per_row * count
        or stats["utf8_bytes"] > 4 * stats["native_bytes"]
    ):
        _refuse()
    if count == 0:
        if stats["native_bytes"] or stats["utf8_bytes"]:
            _refuse()
        return []
    rows = _query(
        connection,
        family + "_body",
        {
            **parameters,
            "expected_rows": count,
            "expected_native_bytes": stats["native_bytes"],
            "expected_utf8_bytes": stats["utf8_bytes"],
        },
        checks,
    )
    if len(rows) != count:
        _refuse()
    receipt = 0
    for row in rows:
        checks.check()
        if set(row) != field_names:
            _refuse()
        for field, money, nullable in field_rules:
            value = row[field]
            if money:
                if type(value) is not int or not 0 <= value <= MAX_MONEY:
                    _refuse()
            elif value is None:
                if not nullable:
                    _refuse()
            elif type(value) is not str or not value.isascii():
                _refuse()
            receipt += 0 if value is None else len(str(value).encode("utf-8"))
        checks.check()
    if receipt != stats["utf8_bytes"]:
        _refuse()
    return rows


def _retained_size(rows: list[dict[str, Any]], checks: LedgerCheck) -> int:
    # The logical retained representation is a flat JSON array, not Python RSS.
    total = 2
    for index, row in enumerate(rows):
        checks.check()
        total += len(canonical(row)) + (1 if index else 0)
        checks.check()
        if total > 1713250:
            _refuse()
    return total


def _validate_native_projection(
    connection: Connection, history: History, checks: LedgerCheck
) -> None:
    opening = history.opening
    if opening is None or not history.manifests:
        _refuse()
    organization_id = history.ownership.organization_id
    expected: dict[str, LedgerAccount] = {}
    for cursor in history.manifests:
        checks.check()
        for account in cursor.manifest.accounts:
            checks.check()
            if account.id in expected:
                _refuse()
            expected[account.id] = account
    if len(expected) > 4096:
        _refuse()
    accounts = _read(
        connection,
        "immutable_accounts",
        {"organization_id": organization_id},
        checks,
        expected_count=len(expected),
    )
    observed: dict[str, dict[str, Any]] = {}
    try:
        for row in accounts:
            checks.check()
            account = LedgerAccount.model_validate({key: row[key] for key in _ACCOUNT_FIELDS[:-1]})
            if (
                account.id in observed
                or account.organization_id != organization_id
                or account != expected.get(account.id)
                or row["opening_held_microusd"] > account.limit_microusd
            ):
                _refuse()
            observed[account.id] = row
            checks.check()
    except ValidationError:
        raise MigrationRefused("ledger_progress_invalid") from None
    if set(observed) != set(expected):
        _refuse()
    jobs: list[dict[str, Any]] = []
    for start in range(0, len(opening.jobs), 12):
        checks.check()
        batch = opening.jobs[start : start + 12]
        parameters: dict[str, Any] = {"organization_id": organization_id}
        parameters.update(
            {f"job_{i:02}": batch[i].job_id if i < len(batch) else None for i in range(12)}
        )
        jobs.extend(
            _read(connection, "original_jobs", parameters, checks, expected_count=len(batch))
        )
    if _retained_size(accounts, checks) + _retained_size(jobs, checks) > 1713250:
        _refuse()
    original = {job.job_id: job for job in opening.jobs}
    native_jobs: dict[str, int] = {}
    project_totals: dict[str, int] = {}
    for row in jobs:
        checks.check()
        job = original.get(row["job_id"])
        if (
            job is None
            or row["job_id"] in native_jobs
            or row["organization_id"] != organization_id
            or row["project_id"] != job.project_id
            or row["legacy_reserved_microusd"] != job.legacy_reserved_microusd
        ):
            _refuse()
        amount = row["legacy_reserved_microusd"]
        native_jobs[row["job_id"]] = amount
        project = row["project_id"]
        project_totals[project] = project_totals.get(project, 0) + amount
        if project_totals[project] > MAX_MONEY:
            _refuse()
    if set(native_jobs) != set(original):
        _refuse()
    total = sum(project_totals.values())
    if (
        total > MAX_MONEY
        or total != opening.organization_opening_microusd
        or project_totals
        != {item.project_id: item.opening_held_microusd for item in opening.project_totals}
    ):
        _refuse()
    destinations = {
        item.account_id: project_totals[item.project_id] for item in opening.project_totals
    }
    if opening.organization_account_id is not None:
        destinations[opening.organization_account_id] = total
    for cursor in history.manifests:
        checks.check()
        projection = []
        for account in cursor.manifest.accounts:
            checks.check()
            expected_opening = 0
            if cursor.sequence == 0:
                if account.scope == "job" and account.job_id is None:
                    _refuse()
                expected_opening = (
                    native_jobs[account.job_id]
                    if account.scope == "job" and account.job_id is not None
                    else destinations.get(account.id, 0)
                )
            row = observed[account.id]
            if row["opening_held_microusd"] != expected_opening:
                _refuse()
            projection.append(row)
        projection.sort(key=lambda row: row["id"])
        checks.check()
        if len(canonical(projection)) > 26625:
            _refuse()
        checks.check()
        if checksum(projection) != cursor.account_projection_digest:
            _refuse()
        checks.check()


def _validate_ar7_history(connection: Connection, checks: LedgerCheck) -> None:
    """Validate immutable native history; never return a ready result or ledger state."""
    validated_ar7_history(connection, checks)


def validated_ar7_history(connection: Connection, checks: LedgerCheck) -> History:
    """Return immutable provenance only; no ready result or operator body rights."""
    checks.check()
    if read_revision(connection) != LEDGER:
        raise MigrationRefused("schema_incompatible")
    checks.check()
    shape = inspect_catalog(connection, LEDGER, checks)
    history = read_history(connection, LEDGER, shape, checks)
    checks.check()
    _validate_native_projection(connection, history, checks)
    checks.check()
    return history
