"""Native-valid inputs separating project and organization sum overflow."""

import json
from copy import deepcopy

from ledger_eligibility_fixture import refreshed, rows
from ledger_provisioning_fixture import (
    ROLLOVER,
    START,
    canonical,
    ciphertexts,
    identity,
    reader,
    snapshot,
    source_fingerprint,
    source_rows,
)
from sqlalchemy import create_engine
from test_ledger_competing_distinct_sqlite import add_shared_project

from agent_rewind.artifact_metadata import configure_artifact_engine
from agent_rewind.migrations.ledger_inputs import MAX_MONEY, validate_ledger_manifest

HALF = 2**62
OVERFLOW = 2**63
JOBS = ("a" * 32, "b" * 32, "c" * 32)
CASES = ("project", "organization")


def assert_move_candidate(before, project):
    """The failed v1 job has no relational edge requiring a second scope move."""
    jobs = {row["id"]: row for row in rows(before, "jobs")}
    assert set(jobs) == set(JOBS)
    target = jobs[JOBS[2]]
    assert target["status"] == "failed" and target["payload_version"] == 1
    assert (
        target["result"]
        is target["execution_config_ref"]
        is target["execution_config_digest"]
        is None
    )
    for name in ("artifact_refs", "artifact_objects", "operations", "operation_keys"):
        assert rows(before, name) == [], name
    records = rows(before, "records")
    assert len(records) == 2 and all(row["kind"] == "run" for row in records)
    data = [json.loads(row["data"]) for row in records]
    assert {row["job_id"] for row in data} == set(JOBS[:2])
    assert all(
        row["parent_id"] is None or row["parent_id"] in {r["id"] for r in records} for row in data
    )
    indexes = rows(before, "run_index")
    assert {row["run_id"] for row in indexes} == {row["id"] for row in records}
    assert len(indexes) == 2 and all(row["project_id"] == project for row in indexes)
    scopes = rows(before, "resource_scopes")
    assert len(scopes) == 7 and all(row["project_id"] == project for row in scopes)
    assert {row["resource_id"] for row in scopes if row["resource_kind"] == "job"} == set(JOBS)


def assert_setup_delta(before, after, project, case):
    assert case in CASES
    assert_move_candidate(before, project)
    expected = deepcopy(before)
    jobs = expected["tables"]["jobs"]
    old_jobs = rows(before, "jobs")
    assert [row["id"] for row in old_jobs] == list(JOBS)
    assert [row["reserved"] for row in old_jobs] == [125000, 85000, 35000]
    assert [row["budget"] for row in old_jobs] == [10000000, 10000000, 5000000]
    changed = []
    for row in old_jobs:
        row = {**row, "reserved": 0 if row["id"] == JOBS[1] else HALF}
        if row["id"] != JOBS[1]:
            row["budget"] = HALF
        changed.append(tuple(row[key] for key in jobs["columns"]))
    jobs["rows"] = tuple(sorted(changed, key=repr))
    if case == "organization":
        projects = expected["tables"]["projects"]
        (original,) = rows(before, "projects")
        assert original["id"] == project
        added = {**original, "id": identity(9000), "name": "Independent project", "run_sequence": 0}
        projects["rows"] = tuple(
            sorted([*projects["rows"], tuple(added[key] for key in projects["columns"])], key=repr)
        )
        scopes = expected["tables"]["resource_scopes"]
        scopes["rows"] = tuple(
            sorted(
                [
                    tuple(
                        (
                            {**row, "project_id": identity(9000)}
                            if row["resource_kind"] == "job" and row["resource_id"] == JOBS[2]
                            else row
                        )[key]
                        for key in scopes["columns"]
                    )
                    for row in rows(before, "resource_scopes")
                ],
                key=repr,
            )
        )
    # Canonical bytes also distinguish integers from accidentally introduced floats.
    assert canonical(after) == canonical(expected)
    for row in rows(after, "jobs"):
        assert type(row["budget"]) is type(row["reserved"]) is int
        assert 0 <= row["reserved"] <= row["budget"] <= MAX_MONEY
    assert sum(row["reserved"] for row in rows(after, "jobs")) == OVERFLOW


def overflow_predecessor(fixture, case, record):
    before = snapshot(fixture.case.path)
    protected = ciphertexts(fixture.case)
    assert before == fixture.before and protected == fixture.encrypted and len(protected) == 18
    assert_move_candidate(before, fixture.project)
    if case == "organization":
        other, topology = add_shared_project(fixture)
        assert other == identity(9000)
        record("shared_project_setup", topology)
    else:
        assert case == "project"
    engine = create_engine(fixture.case.engine.url)
    configure_artifact_engine(engine)
    try:
        with engine.begin() as connection:
            fk = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
            record(
                "setup_foreign_keys",
                {"enabled": fk, "raw_id": id(connection.connection.driver_connection)},
            )
            assert fk == 1
            for job in (JOBS[0], JOBS[2]):
                assert (
                    connection.exec_driver_sql(
                        "UPDATE jobs SET budget=?,reserved=? WHERE id=?", (HALF, HALF, job)
                    ).rowcount
                    == 1
                )
            assert (
                connection.exec_driver_sql(
                    "UPDATE jobs SET reserved=0 WHERE id=?", (JOBS[1],)
                ).rowcount
                == 1
            )
            if case == "organization":
                assert (
                    connection.exec_driver_sql(
                        "UPDATE resource_scopes SET project_id=? "
                        "WHERE resource_kind='job' AND resource_id=?",
                        (identity(9000), JOBS[2]),
                    ).rowcount
                    == 1
                )
            violations = [
                tuple(row) for row in connection.exec_driver_sql("PRAGMA foreign_key_check")
            ]
            record("setup_foreign_key_check", violations)
            assert violations == []
        assert engine.pool.checkedout() == 0 and fixture.case.engine.pool.checkedout() == 0
        record(
            "setup_pool_return",
            {
                "setup_checkedout": engine.pool.checkedout(),
                "predecessor_checkedout": fixture.case.engine.pool.checkedout(),
                "distinct_engines": engine is not fixture.case.engine,
            },
        )
    finally:
        engine.dispose()
        record("setup_engine_disposed", True)
    after = snapshot(fixture.case.path)
    record(
        "overflow_setup",
        {
            "before": before,
            "after": after,
            "case": case,
            "money_cells": 5,
            "scope_cells": int(case == "organization"),
        },
    )
    assert_setup_delta(before, after, fixture.project, case)
    result = refreshed(fixture)
    assert result.before == after and result.encrypted == protected
    assert result.original == source_rows(result.case.path)
    assert result.source == source_fingerprint(result.original)
    with reader(fixture.case.path) as connection:
        native = [
            dict(row)
            for row in connection.execute(
                "SELECT id,budget,reserved,typeof(budget) AS budget_type,"
                "typeof(reserved) AS reserved_type FROM jobs ORDER BY id"
            )
        ]
    record("native_overflow_inputs", native)
    assert all(row["budget_type"] == row["reserved_type"] == "integer" for row in native)
    assert [{key: row[key] for key in ("id", "budget", "reserved")} for row in native] == [
        {key: row[key] for key in ("id", "budget", "reserved")} for row in result.jobs
    ]
    return result


def overflow_manifest(fixture, case):
    assert case in CASES and [row["id"] for row in fixture.jobs] == list(JOBS)
    assert [row["reserved"] for row in fixture.jobs] == [HALF, 0, HALF]
    assert all(type(row["reserved"]) is type(row["budget"]) is int for row in fixture.jobs)
    assert all(0 <= row["reserved"] <= row["budget"] <= MAX_MONEY for row in fixture.jobs)
    projects = sorted({row["project_id"] for row in fixture.jobs})
    assert set(projects) == (
        {fixture.project} if case == "project" else {fixture.project, identity(9000)}
    )
    expected_scope = [
        fixture.project,
        fixture.project,
        identity(9000) if case == "organization" else fixture.project,
    ]
    assert [row["project_id"] for row in fixture.jobs] == expected_scope

    def account(number, scope, target, cap, *, project=None, job=None):
        assert type(cap) is int and 0 <= cap <= MAX_MONEY
        return {
            "id": identity(number),
            "organization_id": fixture.organization,
            "scope": scope,
            "scope_id": target,
            "project_id": project,
            "job_id": job,
            "period_start": START,
            "period_end": ROLLOVER,
            "limit_microusd": cap,
        }

    project_accounts = {
        project: account(
            200 + i, "project", project, MAX_MONEY if case == "project" else HALF, project=project
        )
        for i, project in enumerate(projects)
    }
    manifest = {
        "schema_version": 1,
        "installation_key": fixture.case.adoption["installation_key"],
        "manifest_id": identity(1000),
        "operation": "initialize",
        "source_digest": fixture.source,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": [
            account(100, "organization", fixture.organization, MAX_MONEY),
            *project_accounts.values(),
            *[
                account(
                    300 + i,
                    "job",
                    row["id"],
                    row["budget"],
                    project=row["project_id"],
                    job=row["id"],
                )
                for i, row in enumerate(fixture.jobs)
            ],
        ],
        "opening_accounts": {
            "organization_account_id": identity(100),
            "projects": [
                {"project_id": p, "account_id": project_accounts[p]["id"]} for p in projects
            ],
        },
    }
    parsed = validate_ledger_manifest(manifest)
    assert parsed.canonical_bytes == canonical(manifest)
    assert len(parsed.accounts) == 4 + len(projects)
    assert all(
        type(row.limit_microusd) is int and 0 <= row.limit_microusd <= MAX_MONEY
        for row in parsed.accounts
    )
    return manifest
