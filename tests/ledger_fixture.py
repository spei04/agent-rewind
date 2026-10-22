"""Independent JSON fixtures for ledger entry-policy tests, without SQL authority."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

ORGANIZATION = f"{1:032x}"
OBSERVED = "2026-01-15T12:00:00.000000Z"
START = "2026-01-01T00:00:00.000000Z"
END = "2026-02-01T00:00:00.000000Z"
MAX_MONEY = 2**63 - 1


def identifier(number):
    return f"{number:032x}"


def canonical_bytes(value):
    """The published wire convention, independent of the product serializer."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class DialectOnlyConnection:
    """A pure-parser seam: any attempt to access SQL or connection state fails."""

    def __init__(self, name="sqlite", version=None):
        self.dialect = SimpleNamespace(
            name=name, server_version_info=(16, 15) if version is None else version
        )

    def __getattr__(self, name):
        raise AssertionError(f"pure ledger validation accessed connection.{name}")


def account(number, scope="organization", *, project=None, job=None, start=START, end=END):
    return {
        "id": identifier(number),
        "organization_id": ORGANIZATION,
        "scope": scope,
        "scope_id": {"organization": ORGANIZATION, "project": project, "job": job}[scope],
        "project_id": project,
        "job_id": job,
        "period_start": start,
        "period_end": end,
        "limit_microusd": 1_000_000,
    }


def manifest(*, projects=1, jobs=2, empty=False):
    """Build complete independent account/window intent; no balances are input."""
    rows = [] if empty else [account(10_000)]
    project_ids = [identifier(100 + n) for n in range(projects)] if not empty else []
    for index, project in enumerate(project_ids):
        rows.append(account(20_000 + index, "project", project=project))
    for index in range(jobs if not empty else 0):
        rows.append(
            account(
                30_000 + index,
                "job",
                project=project_ids[index % projects],
                job=identifier(1000 + index),
            )
        )
    used = {row["project_id"] for row in rows if row["scope"] == "job"}
    return {
        "schema_version": 1,
        "installation_key": "independent-ledger-fixture",
        "manifest_id": identifier(1_000_000),
        "operation": "initialize",
        "source_digest": "1" * 64,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "2" * 64,
        "drain_evidence_digest": "3" * 64,
        "accounts": rows,
        "opening_accounts": {
            "organization_account_id": None if empty else identifier(10_000),
            "projects": [
                {"project_id": project, "account_id": identifier(20_000 + index)}
                for index, project in enumerate(project_ids)
                if project in used
            ],
        },
    }


def opening_for(raw, *, amounts=None):
    jobs = [row for row in raw["accounts"] if row["scope"] == "job"]
    if amounts is None:
        amounts = [120_000, 125_000] if len(jobs) == 2 else [0] * len(jobs)
    assert len(amounts) == len(jobs)
    receipts = sorted(
        [
            {
                "job_id": row["job_id"],
                "project_id": row["project_id"],
                "budget_microusd": row["limit_microusd"],
                "legacy_reserved_microusd": amount,
            }
            for row, amount in zip(jobs, amounts, strict=True)
        ],
        key=lambda row: row["job_id"],
    )
    totals = [
        {
            **destination,
            "opening_held_microusd": sum(
                job["legacy_reserved_microusd"]
                for job in receipts
                if job["project_id"] == destination["project_id"]
            ),
        }
        for destination in raw["opening_accounts"]["projects"]
    ]
    return {
        "schema_version": 1,
        "manifest_id": raw["manifest_id"],
        "manifest_digest": digest(raw),
        "source_digest": raw["source_digest"],
        "initialized_at": OBSERVED,
        "jobs": receipts,
        "jobs_digest": digest(receipts),
        "project_totals": totals,
        "organization_account_id": raw["opening_accounts"]["organization_account_id"],
        "organization_opening_microusd": sum(amounts),
        "job_count": len(receipts),
    }


def cursor_for(raw, *, opening=None, sequence=0, role=None):
    exposure = {}
    if opening is not None:
        if opening["organization_account_id"] is not None:
            exposure[opening["organization_account_id"]] = opening["organization_opening_microusd"]
        exposure.update(
            (row["account_id"], row["opening_held_microusd"]) for row in opening["project_totals"]
        )
        by_job = {row["job_id"]: row["legacy_reserved_microusd"] for row in opening["jobs"]}
        exposure.update(
            (row["id"], by_job[row["job_id"]]) for row in raw["accounts"] if row["scope"] == "job"
        )
    projection = [
        {**row, "opening_held_microusd": exposure.get(row["id"], 0)} for row in raw["accounts"]
    ]
    return {
        "schema_version": 1,
        "manifest": deepcopy(raw),
        "manifest_digest": digest(raw),
        "sequence": sequence,
        "parent_manifest_digest": raw["parent_manifest_digest"],
        "database_role": role,
        "os_uid": 1000,
        "initialized_at": OBSERVED,
        "account_projection_digest": digest(projection),
        "account_count": len(raw["accounts"]),
        "imported_jobs": 0 if opening is None else opening["job_count"],
        "imported_opening_microusd": (
            0 if opening is None else opening["organization_opening_microusd"]
        ),
    }


def initial_bundle(*, projects=1, jobs=2, empty=False):
    raw = manifest(projects=projects, jobs=jobs, empty=empty)
    opening = opening_for(raw)
    return raw, cursor_for(raw, opening=opening), opening


def provision(parent, sequence, *, rows=None):
    raw = manifest(empty=True)
    raw.update(
        manifest_id=identifier(1_000_000 + sequence),
        operation="provision",
        parent_manifest_digest=digest(parent),
        opening_accounts=None,
        accounts=rows
        if rows is not None
        else [
            account(
                100_000 + sequence,
                "project",
                project=identifier(10_000_000 + sequence),
            )
        ],
    )
    return raw


def progress_row(cursor, *, opening=False, postgres=False):
    return {
        "revision": "ar_0007_ledger",
        "phase": "ledger_opening"
        if opening
        else "ledger_manifest_" + cursor["manifest"]["manifest_id"],
        "source_digest": cursor["source_digest"]
        if opening
        else cursor["manifest"]["source_digest"],
        "cursor": canonical_bytes(cursor).decode("utf-8"),
        "rows_verified": cursor["job_count"] if opening else cursor["account_count"],
        "status": "complete",
        "updated_at": datetime.fromisoformat(OBSERVED.replace("Z", "+00:00"))
        if postgres
        else OBSERVED,
    }


def disjoint_accounts(sequence, count=64):
    """16 project scopes with four nonoverlapping periods each, within each input."""
    rows = []
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(count):
        start = origin + timedelta(days=index // 16)
        end = start + timedelta(days=1)
        rows.append(
            account(
                2_000_000 + sequence * 64 + index,
                "project",
                project=identifier(20_000_000 + sequence * 16 + index % 16),
                start=start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                end=end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            )
        )
    return rows
