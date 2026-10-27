"""Independent synthetic native observations; no database or writer invocation."""

from copy import deepcopy
from datetime import datetime

import pytest
from ledger_eligibility_fixture import rows
from ledger_fixture import cursor_for, identifier, opening_for
from ledger_fixture import manifest as input_manifest
from ledger_provisioning_fixture import SOURCE_FIELDS, digest, source_fingerprint
from ledger_restore_authority import typed
from ledger_writer_capacity_fixture import SHAPES, assert_transition, expected_transition

from agent_rewind.migrations.schema import ADMISSION, LEDGER, MigrationRefused, installed_profile

OBSERVED = "2026-01-15T12:00:00.000000Z"
ROLE = "capacity_fixture_owner"


def packed(columns, values):
    columns = tuple(columns)
    return {
        "columns": columns,
        "rows": tuple(
            sorted(
                (tuple(deepcopy(value[column]) for column in columns) for value in values), key=repr
            )
        ),
    }


def set_rows(state, name, values):
    state["tables"][name] = packed(state["tables"][name]["columns"], values)


def witness(shape):
    project_count, job_count = shape
    manifest = input_manifest(projects=project_count, jobs=job_count)
    profiles = {
        revision: installed_profile("postgresql", revision) for revision in (ADMISSION, LEDGER)
    }
    before = {
        "tables": {
            name: packed([column[0] for column in value["columns"]], [])
            for name, value in profiles[ADMISSION].items()
            if not name.startswith("$")
        }
    }
    organization = manifest["accounts"][0]["organization_id"]
    project_ids = [identifier(100 + i) for i in range(project_count)]
    job_ids = [identifier(1000 + i) for i in range(job_count)]
    amounts = [35000, 85000, 125000] + [0] * (job_count - 3)
    job_project = [project_ids[0]] * 4 + [
        project_ids[i % project_count] for i in range(job_count - 4)
    ]

    def complete(table_name, **values):
        assert set(values) <= set(before["tables"][table_name]["columns"])
        return {column: values.get(column) for column in before["tables"][table_name]["columns"]}

    set_rows(
        before,
        "organizations",
        [complete("organizations", id=organization, installation_key=manifest["installation_key"])],
    )
    set_rows(
        before,
        "projects",
        [
            complete("projects", id=project, organization_id=organization, name=f"project-{i}")
            for i, project in enumerate(project_ids)
        ],
    )
    jobs = [
        complete(
            "jobs",
            id=job,
            kind="run",
            created=1700000000.125,
            payload="c" * 64,
            status="queued" if i == 3 else "succeeded",
            owner=None,
            lease_until=None,
            cancel=False,
            budget=1 if i == 3 else 1000000,
            reserved=amounts[i],
            result=None,
            error=None,
            actor="fixture-actor",
            payload_version=2 if i == 3 else 1,
            execution_config_ref="e" * 64 if i == 3 else None,
            execution_config_digest="e" * 64 if i == 3 else None,
        )
        for i, job in enumerate(job_ids)
    ]
    set_rows(before, "jobs", jobs)
    set_rows(
        before,
        "resource_scopes",
        [
            complete("resource_scopes", resource_kind="job", resource_id=job, project_id=project)
            for job, project in zip(job_ids, job_project, strict=True)
        ],
    )
    set_rows(before, "alembic_version", [{"version_num": ADMISSION}])
    set_rows(
        before,
        "installation_adoptions",
        [
            complete(
                "installation_adoptions",
                singleton=1,
                installation_key=manifest["installation_key"],
                installed_schema_fingerprint=digest(profiles[ADMISSION]),
                mapping={"preserve": 7},
            )
        ],
    )
    set_rows(
        before,
        "migration_progress",
        [
            complete(
                "migration_progress",
                revision=ADMISSION,
                phase="admission",
                source_digest="9" * 64,
                cursor={"retain": [1, "native JSONB"]},
                rows_verified=4,
                status="complete",
                updated_at=datetime.fromisoformat(OBSERVED.replace("Z", "+00:00")),
            )
        ],
    )
    set_rows(
        before,
        "records",
        [
            complete(
                "records",
                id=identifier(9000),
                kind="task",
                created=1700000000.5,
                data='{"preserve":"unchanged"}',
            )
        ],
    )
    # Nonempty unrelated state makes deletion/mutation controls meaningful.
    set_rows(
        before,
        "artifact_objects",
        [
            complete(
                "artifact_objects",
                id=identifier(9001),
                project_id=project_ids[0],
                digest="f" * 64,
                byte_count=7,
            )
        ],
    )
    source = {
        name: [tuple(row[field] for field in fields) for row in rows(before, name)]
        for name, fields in SOURCE_FIELDS.items()
    }
    manifest["source_digest"] = source_fingerprint(source)
    for i, account in enumerate(row for row in manifest["accounts"] if row["scope"] == "job"):
        account["project_id"] = job_project[i]
        account["limit_microusd"] = jobs[i]["budget"]
    manifest["opening_accounts"]["projects"] = [
        {"project_id": project, "account_id": identifier(20000 + i)}
        for i, project in enumerate(project_ids)
    ]
    for account in manifest["accounts"]:
        if account["scope"] == "organization":
            account["limit_microusd"] = 245000
        elif account["scope"] == "project":
            account["limit_microusd"] = 245000 if account["project_id"] == project_ids[0] else 0
    # Observations use separate retained input/cursor witnesses and literal known
    # balances. They never call expected_transition or its cohort reduction.
    opening = opening_for(manifest, amounts=amounts)
    cursor = cursor_for(manifest, opening=opening, role=ROLE)
    after = deepcopy(before)
    after["tables"]["jobs"] = packed(
        [column[0] for column in profiles[LEDGER]["jobs"]["columns"]],
        [
            {**job, "lease_generation": 0, "legacy_reserved_microusd": amounts[i]}
            for i, job in enumerate(jobs)
        ],
    )
    balances = dict(zip(job_ids, amounts, strict=True))
    accounts = []
    for account in manifest["accounts"]:
        if account["scope"] == "job":
            held = balances[account["job_id"]]
        elif account["scope"] == "organization" or account["scope_id"] == project_ids[0]:
            held = 245000
        else:
            held = 0
        accounts.append(
            {
                **account,
                "opening_held_microusd": held,
                "held_microusd": held,
                "accounted_microusd": 0,
                "period_start": datetime.fromisoformat(
                    account["period_start"].replace("Z", "+00:00")
                ),
                "period_end": datetime.fromisoformat(account["period_end"].replace("Z", "+00:00")),
            }
        )
    for name, values in (
        ("budget_accounts", accounts),
        ("provider_calls", []),
        ("budget_entries", []),
    ):
        after["tables"][name] = packed(
            [column[0] for column in profiles[LEDGER][name]["columns"]], values
        )
    additions = [
        {
            "revision": LEDGER,
            "phase": phase,
            "source_digest": manifest["source_digest"],
            "cursor": value,
            "rows_verified": count,
            "status": "complete",
            "updated_at": datetime.fromisoformat(OBSERVED.replace("Z", "+00:00")),
        }
        for phase, value, count in (
            ("ledger_opening", opening, job_count),
            ("ledger_manifest_" + manifest["manifest_id"], cursor, 64),
        )
    ]
    set_rows(after, "migration_progress", rows(before, "migration_progress") + additions)
    (adoption,) = rows(before, "installation_adoptions")
    set_rows(
        after,
        "installation_adoptions",
        [{**adoption, "installed_schema_fingerprint": digest(profiles[LEDGER])}],
    )
    set_rows(after, "alembic_version", [{"version_num": LEDGER}])
    receipt = {
        "installation_key": manifest["installation_key"],
        "revision": LEDGER,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": digest(manifest),
        "sequence": 0,
        "operation": "initialize",
        "source_digest": manifest["source_digest"],
        "account_rows": 64,
        "imported_jobs": job_count,
        "imported_opening_microusd": 245000,
        "initialized_at": OBSERVED,
        "outcome": "complete",
    }
    inspection = {
        "status": "complete",
        "installation_key": manifest["installation_key"],
        "revision": LEDGER,
        "head": {key: value for key, value in receipt.items() if key != "outcome"},
        "manifest_count": 1,
        "account_count": 64,
        "opening": deepcopy(opening),
    }
    return {
        "before": before,
        "manifest": manifest,
        "original_jobs": deepcopy(jobs[:3]),
        "admitted_job": deepcopy(jobs[3]),
        "after": after,
        "receipt": receipt,
        "inspection": inspection,
        "original_project": project_ids[0],
    }


def expected(case, **extra):
    return expected_transition(
        case["before"],
        case["manifest"],
        case["original_jobs"],
        case["admitted_job"],
        initialized_at=OBSERVED,
        database_role=ROLE,
        os_uid=1000,
        original_project=case["original_project"],
        **extra,
    )


@pytest.mark.parametrize("shape", SHAPES)
def test_complete_cohort_and_independent_native_transition(shape):
    case = witness(shape)
    saved = deepcopy(case)
    result = expected(case)
    assert_transition(result, case["after"], case["receipt"], case["inspection"])
    assert typed(case) == typed(saved)
    facts = result["facts"]
    assert facts["accounts"] == 64 and facts["economic_exposure"] == 245000
    assert sorted(facts["project_totals"].values()) == [0] * (shape[0] - 1) + [245000]
    assert facts["jobs"] == facts["backfill_writes"] == shape[1]
    assert facts["raw_manifest_bytes"] == facts["canonical_manifest_bytes"] < 32768
    assert facts["opening_cursor_bytes"] < 65536 and facts["manifest_cursor_bytes"] < 65536
    assert facts["known_write_sql_units_excluding_ddl_reads"] == (345 if shape[1] == 48 else 342)
    opening = result["inspection"]["opening"]
    assert len(opening["jobs"]) == len({row["job_id"] for row in opening["jobs"]}) == shape[1]
    admitted = next(row for row in opening["jobs"] if row["job_id"] == case["admitted_job"]["id"])
    assert admitted["legacy_reserved_microusd"] == 0


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(
    "fault",
    [
        "missing-admitted",
        "duplicate-job",
        "duplicate-scope",
        "missing-scope",
        "wrong-project",
        "move-original-project",
        "added-reserve",
        "queued-v1",
        "changed-original",
        "bool-money",
        "float-money",
        "foreign-project",
        "seeded-ledger",
        "missing-table",
    ],
)
def test_predecessor_coverage_and_native_money_are_required(shape, fault):
    case = witness(shape)
    before = case["before"]
    jobs = rows(before, "jobs")
    scopes = rows(before, "resource_scopes")
    if fault == "missing-admitted":
        jobs = [row for row in jobs if row["id"] != case["admitted_job"]["id"]]
    elif fault == "duplicate-job":
        jobs.append(deepcopy(jobs[-1]))
    elif fault == "duplicate-scope":
        scopes.append(deepcopy(scopes[-1]))
    elif fault == "missing-scope":
        scopes.pop()
    elif fault == "wrong-project":
        scopes[-1]["project_id"] = identifier(99999)
    elif fault == "move-original-project":
        for row in scopes[:3]:
            row["project_id"] = identifier(101)
    elif fault == "added-reserve":
        jobs[-1]["reserved"] = 1
    elif fault == "queued-v1":
        jobs[-1]["status"] = "queued"
    elif fault == "changed-original":
        jobs[0]["payload"] = "9" * 64
    elif fault in {"bool-money", "float-money"}:
        jobs[-1]["reserved"] = False if fault == "bool-money" else 0.0
    elif fault == "foreign-project":
        projects = rows(before, "projects")
        projects[-1]["organization_id"] = identifier(2)
        set_rows(before, "projects", projects)
    elif fault == "seeded-ledger":
        set_rows(before, "alembic_version", [{"version_num": LEDGER}])
    elif fault == "missing-table":
        del before["tables"]["records"]
    set_rows(before, "jobs", jobs)
    set_rows(before, "resource_scopes", scopes)
    with pytest.raises((AssertionError, KeyError)):
        expected(case)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(
    "fault",
    [
        "missing-job-account",
        "duplicate-job-account",
        "wrong-job-project",
        "wrong-project-account",
        "organization-cap",
        "project-cap",
        "job-cap",
        "bool-limit",
        "float-limit",
        "wrong-source",
        "wrong-installation",
        "missing-opening-project",
    ],
)
def test_manifest_must_bind_the_complete_persisted_cohort(shape, fault):
    case = witness(shape)
    manifest = case["manifest"]
    accounts = manifest["accounts"]
    if fault == "missing-job-account":
        accounts.pop()
    elif fault == "duplicate-job-account":
        accounts[-1] = deepcopy(accounts[-2])
    elif fault == "wrong-job-project":
        accounts[-1]["project_id"] = identifier(101)
    elif fault == "wrong-project-account":
        accounts[1]["project_id"] = accounts[1]["scope_id"] = identifier(99999)
    elif fault == "organization-cap":
        accounts[0]["limit_microusd"] = 244999
    elif fault == "project-cap":
        accounts[1]["limit_microusd"] = 244999
    elif fault == "job-cap":
        accounts[-1]["limit_microusd"] = 1000001
    elif fault in {"bool-limit", "float-limit"}:
        accounts[-1]["limit_microusd"] = True if fault == "bool-limit" else 1000000.0
    elif fault == "wrong-source":
        manifest["source_digest"] = "0" * 64
    elif fault == "wrong-installation":
        manifest["installation_key"] = "other"
    elif fault == "missing-opening-project":
        manifest["opening_accounts"]["projects"].pop()
    with pytest.raises((AssertionError, MigrationRefused)):
        expected(case)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(
    "fault",
    [
        "all-projects-org-total",
        "exposure-times-three",
        "missing-account",
        "duplicate-account",
        "wrong-backfill",
        "float-backfill",
        "bool-generation",
        "accounted",
        "held",
        "missing-admitted-opening",
        "wrong-job-count",
        "cursor-count",
        "cursor-digest",
        "old-progress",
        "adoption-field",
        "original-job-field",
        "unrelated-value",
        "unrelated-table",
        "provider-call",
        "extra-column",
        "receipt-bool",
        "receipt-float",
        "inspection-float",
    ],
)
def test_complete_transition_rejects_partial_or_inflated_observations(shape, fault):
    case = witness(shape)
    result = expected(case)
    after = case["after"]
    accounts = rows(after, "budget_accounts")
    jobs = rows(after, "jobs")
    progress = rows(after, "migration_progress")
    opening = next(row for row in progress if row["phase"] == "ledger_opening")
    cursor = next(row for row in progress if row["phase"].startswith("ledger_manifest_"))
    if fault == "all-projects-org-total":
        for row in accounts:
            if row["scope"] == "project":
                row["opening_held_microusd"] = row["held_microusd"] = 245000
    elif fault == "exposure-times-three":
        case["receipt"]["imported_opening_microusd"] = 735000
    elif fault == "missing-account":
        accounts.pop()
    elif fault == "duplicate-account":
        accounts[-1] = deepcopy(accounts[-2])
    elif fault == "wrong-backfill":
        jobs[0]["legacy_reserved_microusd"] += 1
    elif fault == "float-backfill":
        jobs[0]["legacy_reserved_microusd"] = 35000.0
    elif fault == "bool-generation":
        jobs[0]["lease_generation"] = False
    elif fault in {"accounted", "held"}:
        accounts[-1][fault + "_microusd"] = 1
    elif fault == "missing-admitted-opening":
        opening["cursor"]["jobs"] = [
            row for row in opening["cursor"]["jobs"] if row["job_id"] != case["admitted_job"]["id"]
        ]
    elif fault == "wrong-job-count":
        opening["cursor"]["job_count"] -= 1
    elif fault == "cursor-count":
        cursor["rows_verified"] = 63
    elif fault == "cursor-digest":
        cursor["cursor"]["account_projection_digest"] = "0" * 64
    elif fault == "old-progress":
        next(row for row in progress if row["revision"] == ADMISSION)["cursor"]["retain"][0] = 2
    elif fault == "adoption-field":
        adoption = rows(after, "installation_adoptions")
        adoption[0]["mapping"]["preserve"] = 8
        set_rows(after, "installation_adoptions", adoption)
    elif fault == "original-job-field":
        jobs[0]["payload"] = "1" * 64
    elif fault == "unrelated-value":
        values = rows(after, "records")
        values[0]["data"] = "changed"
        set_rows(after, "records", values)
    elif fault == "unrelated-table":
        del after["tables"]["artifact_objects"]
    elif fault == "provider-call":
        set_rows(
            after, "provider_calls", [dict.fromkeys(after["tables"]["provider_calls"]["columns"])]
        )
    elif fault == "extra-column":
        after["tables"]["records"]["columns"] += ("unexpected",)
    elif fault == "receipt-bool":
        case["receipt"]["sequence"] = False
    elif fault == "receipt-float":
        case["receipt"]["account_rows"] = 64.0
    elif fault == "inspection-float":
        case["inspection"]["opening"]["organization_opening_microusd"] = 245000.0
    set_rows(after, "jobs", jobs)
    set_rows(after, "budget_accounts", accounts)
    set_rows(after, "migration_progress", progress)
    with pytest.raises(AssertionError):
        assert_transition(result, after, case["receipt"], case["inspection"])


@pytest.mark.parametrize("shape", SHAPES)
def test_expected_nested_state_is_detached_from_predecessor(shape):
    case = witness(shape)
    result = expected(case)
    frozen = deepcopy(result)
    rows(case["before"], "migration_progress")[0]["cursor"]["retain"][0] = 2
    rows(case["before"], "installation_adoptions")[0]["mapping"]["preserve"] = 8
    assert typed(result) == typed(frozen)
    assert_transition(result, case["after"], case["receipt"], case["inspection"])
