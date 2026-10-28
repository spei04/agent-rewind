"""Pure complete-table oracle for the two approved writer-capacity cohorts.

Inputs are captured predecessor rows and declared intent, never writer preparation
or observed final balances. Native catalog/authority, real admission, artifacts
and physical execution remain separate adapter obligations.
"""

from copy import deepcopy
from datetime import UTC, datetime

from ledger_capacity_fixture import strict_json_value
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import SOURCE_FIELDS, canonical, digest, source_fingerprint
from ledger_restore_authority import typed

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import ADMISSION, LEDGER, installed_profile

SHAPES = ((15, 48), (16, 47))
MAX_MONEY = 2**63 - 1


def table_value(columns, values):
    """Retain column order and native values; no lossy JSON roundtrip."""
    columns = tuple(columns)
    assert len(columns) == len(set(columns))
    assert all(set(value) == set(columns) for value in values)
    return {
        "columns": columns,
        "rows": tuple(
            sorted((tuple(deepcopy(value[c]) for c in columns) for value in values), key=repr)
        ),
    }


def unique(values, key):
    result = {}
    for value in values:
        identity = value[key]
        assert type(identity) is str and identity not in result
        result[identity] = value
    return result


def money(value):
    assert type(value) is int and 0 <= value <= MAX_MONEY
    return value


def cohort(before, original_jobs, admitted_job, original_project):
    """All persisted jobs participate, including the real admitted zero-held row."""
    tables = before["tables"]
    profile = installed_profile("postgresql", ADMISSION)
    assert set(tables) == {name for name in profile if not name.startswith("$")}
    for name, table in tables.items():
        assert table["columns"] == tuple(column[0] for column in profile[name]["columns"])
        assert all(len(row) == len(table["columns"]) for row in table["rows"])
    assert rows(before, "alembic_version") == [{"version_num": ADMISSION}]
    (organization,) = rows(before, "organizations")
    projects = unique(rows(before, "projects"), "id")
    jobs = unique(rows(before, "jobs"), "id")
    assert (len(projects), len(jobs)) in SHAPES
    assert all(row["organization_id"] == organization["id"] for row in projects.values())
    scopes = [row for row in rows(before, "resource_scopes") if row["resource_kind"] == "job"]
    scoped = unique(scopes, "resource_id")
    assert set(scoped) == set(jobs)
    assert {row["project_id"] for row in scoped.values()} == set(projects)
    original = unique(original_jobs, "id")
    assert len(original) == 3 and sorted(money(row["reserved"]) for row in original.values()) == [
        35000,
        85000,
        125000,
    ]
    assert all(typed(jobs[key]) == typed(row) for key, row in original.items())
    assert all(scoped[key]["project_id"] == original_project for key in original)
    assert scoped[admitted_job["id"]]["project_id"] == original_project
    assert admitted_job["id"] not in original
    assert typed(jobs[admitted_job["id"]]) == typed(admitted_job)
    assert admitted_job["status"] == "queued"
    assert type(admitted_job["payload_version"]) is int and admitted_job["payload_version"] == 2
    assert money(admitted_job["reserved"]) == 0
    assert admitted_job["owner"] is None and admitted_job["lease_until"] is None
    assert type(admitted_job["execution_config_ref"]) is str
    assert admitted_job["execution_config_ref"] == admitted_job["execution_config_digest"]
    amounts = {}
    for key, row in jobs.items():
        amount, budget = money(row["reserved"]), money(row["budget"])
        assert amount <= budget
        if key not in original and key != admitted_job["id"]:
            assert row["status"] in {"succeeded", "failed", "cancelled"}
            assert type(row["payload_version"]) is int and row["payload_version"] == 1
            assert amount == 0 and row["owner"] is None and row["lease_until"] is None
            assert row["execution_config_ref"] is None and row["execution_config_digest"] is None
        amounts[key] = amount
    total = sum(amounts.values())
    assert total == 245000
    totals = {
        key: sum(amounts[job] for job, scope in scoped.items() if scope["project_id"] == key)
        for key in projects
    }
    original_source = {
        name: [
            tuple(row[field] for field in fields)
            for row in sorted(
                rows(before, name),
                key=lambda row: (row["run_id"], row["step"]) if name == "events" else row["id"],
            )
        ]
        for name, fields in SOURCE_FIELDS.items()
    }
    return organization["id"], projects, jobs, scoped, amounts, totals, original_source


def expected_transition(
    before,
    manifest,
    original_jobs,
    admitted_job,
    *,
    initialized_at,
    database_role,
    os_uid,
    original_project,
    raw_manifest=None,
):
    """Expected PostgreSQL table cells, receipt and inspection for one initialization."""
    organization, projects, jobs, scoped, amounts, totals, source = cohort(
        before, original_jobs, admitted_job, original_project
    )
    assert type(os_uid) is int and os_uid >= 0
    assert type(database_role) is str and database_role
    observed = datetime.fromisoformat(initialized_at.replace("Z", "+00:00"))
    assert observed.utcoffset() is not None
    assert (
        observed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        == initialized_at
    )
    checked = validate_ledger_manifest(manifest)
    assert checked.canonical_bytes == canonical(manifest)
    assert typed(checked.model_dump(mode="json")) == typed(manifest)
    raw = canonical(manifest) if raw_manifest is None else raw_manifest
    assert type(raw) is bytes and len(raw) <= 32768
    assert typed(strict_json_value(raw.decode())) == typed(manifest)
    assert len(canonical(manifest)) <= 32768
    assert manifest["operation"] == "initialize" and manifest["parent_manifest_digest"] is None
    assert manifest["source_digest"] == source_fingerprint(source)
    (adoption,) = rows(before, "installation_adoptions")
    assert manifest["installation_key"] == adoption["installation_key"]
    accounts = manifest["accounts"]
    assert len(accounts) == 64
    assert len(unique(accounts, "id")) == 64
    by_scope = {
        scope: [row for row in accounts if row["scope"] == scope]
        for scope in ("organization", "project", "job")
    }
    assert len(by_scope["organization"]) == 1
    org = by_scope["organization"][0]
    project_accounts = unique(by_scope["project"], "scope_id")
    job_accounts = unique(by_scope["job"], "job_id")
    assert set(project_accounts) == set(projects) and set(job_accounts) == set(jobs)
    assert org["scope_id"] == organization
    assignment = manifest["opening_accounts"]
    assert assignment["organization_account_id"] == org["id"]
    assert typed(assignment["projects"]) == typed(
        [{"project_id": key, "account_id": project_accounts[key]["id"]} for key in sorted(projects)]
    )
    projected = []
    for account in accounts:
        assert account["organization_id"] == organization
        limit = money(account["limit_microusd"])
        if account["scope"] == "job":
            key = account["job_id"]
            assert account["scope_id"] == key
            assert account["project_id"] == scoped[key]["project_id"]
            assert limit <= jobs[key]["budget"]
            amount = amounts[key]
        elif account["scope"] == "project":
            assert account["project_id"] == account["scope_id"]
            amount = totals[account["project_id"]]
        else:
            amount = 245000
        assert amount <= limit
        assert account["period_start"] <= initialized_at < account["period_end"]
        projected.append({**account, "opening_held_microusd": amount})
    opening_jobs = [
        {
            "job_id": key,
            "project_id": scoped[key]["project_id"],
            "budget_microusd": jobs[key]["budget"],
            "legacy_reserved_microusd": amounts[key],
        }
        for key in sorted(jobs)
    ]
    opening = {
        "schema_version": 1,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": digest(manifest),
        "source_digest": manifest["source_digest"],
        "initialized_at": initialized_at,
        "jobs": opening_jobs,
        "jobs_digest": digest(opening_jobs),
        "project_totals": [
            {**row, "opening_held_microusd": totals[row["project_id"]]}
            for row in assignment["projects"]
        ],
        "organization_account_id": org["id"],
        "organization_opening_microusd": 245000,
        "job_count": len(jobs),
    }
    cursor = {
        "schema_version": 1,
        "manifest": deepcopy(manifest),
        "manifest_digest": digest(manifest),
        "sequence": 0,
        "parent_manifest_digest": None,
        "database_role": database_role,
        "os_uid": os_uid,
        "initialized_at": initialized_at,
        "account_projection_digest": digest(projected),
        "account_count": 64,
        "imported_jobs": len(jobs),
        "imported_opening_microusd": 245000,
    }
    assert len(canonical(opening)) <= 65536 and len(canonical(cursor)) <= 65536
    receipt = {
        "installation_key": manifest["installation_key"],
        "revision": LEDGER,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": digest(manifest),
        "sequence": 0,
        "operation": "initialize",
        "source_digest": manifest["source_digest"],
        "account_rows": 64,
        "imported_jobs": len(jobs),
        "imported_opening_microusd": 245000,
        "initialized_at": initialized_at,
        "outcome": "complete",
    }
    profile = installed_profile("postgresql", LEDGER)
    result = deepcopy(before["tables"])
    result["jobs"] = table_value(
        [row[0] for row in profile["jobs"]["columns"]],
        [
            {**job, "lease_generation": 0, "legacy_reserved_microusd": amounts[key]}
            for key, job in jobs.items()
        ],
    )
    native_accounts = []
    for account in projected:
        native_accounts.append(
            {
                **account,
                "period_start": datetime.fromisoformat(
                    account["period_start"].replace("Z", "+00:00")
                ),
                "period_end": datetime.fromisoformat(account["period_end"].replace("Z", "+00:00")),
                "held_microusd": account["opening_held_microusd"],
                "accounted_microusd": 0,
            }
        )
    for name, values in (
        ("budget_accounts", native_accounts),
        ("provider_calls", []),
        ("budget_entries", []),
    ):
        result[name] = table_value([row[0] for row in profile[name]["columns"]], values)
    old_progress = rows(before, "migration_progress")
    assert all(row["revision"] != LEDGER for row in old_progress)
    additions = [
        {
            "revision": LEDGER,
            "phase": phase,
            "source_digest": manifest["source_digest"],
            "cursor": value,
            "rows_verified": count,
            "status": "complete",
            "updated_at": observed,
        }
        for phase, value, count in (
            ("ledger_opening", opening, len(jobs)),
            ("ledger_manifest_" + manifest["manifest_id"], cursor, 64),
        )
    ]
    result["migration_progress"] = table_value(
        result["migration_progress"]["columns"], old_progress + additions
    )
    result["installation_adoptions"] = table_value(
        result["installation_adoptions"]["columns"],
        [{**adoption, "installed_schema_fingerprint": digest(profile)}],
    )
    result["alembic_version"] = table_value(("version_num",), [{"version_num": LEDGER}])
    head = {key: value for key, value in receipt.items() if key != "outcome"}
    inspection = {
        "status": "complete",
        "installation_key": manifest["installation_key"],
        "revision": LEDGER,
        "head": head,
        "manifest_count": 1,
        "account_count": 64,
        "opening": opening,
    }
    facts = {
        "projects": len(projects),
        "jobs": len(jobs),
        "accounts": 64,
        "economic_exposure": 245000,
        "project_totals": totals,
        "raw_manifest_bytes": len(raw),
        "canonical_manifest_bytes": len(canonical(manifest)),
        "opening_cursor_bytes": len(canonical(opening)),
        "manifest_cursor_bytes": len(canonical(cursor)),
        "backfill_writes": len(jobs),
        "account_inserts": 64,
        "progress_inserts": 2,
        "adoption_updates": 1,
        # Each native writer statement includes two setters. DDL, reads, hashes,
        # provenance/finalization and reserved cleanup are additional work.
        "known_write_sql_units_excluding_ddl_reads": 3 * (len(jobs) + 64 + 2 + 1),
    }
    return {"tables": result, "receipt": receipt, "inspection": inspection, "facts": facts}


def assert_transition(expected, after, receipt, inspection):
    """Compare complete typed domains, including every otherwise unrelated table."""
    assert typed(after["tables"]) == typed(expected["tables"])
    assert typed(receipt) == typed(expected["receipt"])
    assert typed(inspection) == typed(expected["inspection"])
