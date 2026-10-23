"""Native-valid overflow inputs with exact typed setup and raw JSON preservation."""

from copy import deepcopy

from ledger_eligibility_fixture import rows
from ledger_money_postgres_fixture import observe_inputs
from ledger_overflow_fixture import CASES, HALF, JOBS, OVERFLOW
from ledger_provisioning_fixture import identity
from ledger_provisioning_postgres_fixture import encrypted_files, native_snapshot
from ledger_restore_authority import typed
from sqlalchemy import BigInteger, bindparam, text
from test_run_projection_postgres import drain

from agent_rewind.migrations.ledger_inputs import MAX_MONEY

RAW_PROGRESS_SQL = (
    "SELECT revision,phase,cursor::text AS raw_cursor FROM migration_progress "
    "ORDER BY revision,phase"
)


def raw_progress(fixture, pg):
    try:
        with fixture.case.engine.connect() as connection:
            return [dict(row) for row in connection.exec_driver_sql(RAW_PROGRESS_SQL).mappings()]
    finally:
        drain(pg)


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
    data = [row["data"] for row in records]
    assert all(type(value) is dict for value in data)
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
    # Retain native JSON, boolean, integer and timezone representations in every cell.
    assert typed(after) == typed(expected)
    for row in rows(after, "jobs"):
        assert type(row["budget"]) is type(row["reserved"]) is int
        assert 0 <= row["reserved"] <= row["budget"] <= MAX_MONEY
    assert sum(row["reserved"] for row in rows(after, "jobs")) == OVERFLOW


def overflow_predecessor(fixture, pg, case, record):
    before = native_snapshot(fixture.case, pg)
    assert typed(before) == typed(fixture.before)
    assert encrypted_files(fixture) == fixture.encrypted and len(fixture.encrypted) == 18
    assert case in CASES
    assert_move_candidate(before, fixture.project)
    progress = raw_progress(fixture, pg)
    updates = []
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            owner = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert owner == (pg["owner_role"], pg["owner"].url.database)

            def execute(statement, values):
                count = connection.execute(statement, values).rowcount
                updates.append({"sql": str(statement), "parameters": values, "rowcount": count})
                assert count == 1

            if case == "organization":
                execute(
                    text(
                        "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                        "SELECT :id,organization_id,'Independent project',created_at,0 "
                        "FROM projects WHERE id=:project"
                    ),
                    {"id": identity(9000), "project": fixture.project},
                )
            for job in JOBS:
                selected = job != JOBS[1]
                sql = (
                    "UPDATE jobs SET budget=:amount,reserved=:amount WHERE id=:id"
                    if selected
                    else "UPDATE jobs SET reserved=:amount WHERE id=:id"
                )
                execute(
                    text(sql).bindparams(bindparam("amount", type_=BigInteger)),
                    {"amount": HALF if selected else 0, "id": job},
                )
            if case == "organization":
                execute(
                    text(
                        "UPDATE resource_scopes SET project_id=:project "
                        "WHERE resource_kind='job' AND resource_id=:job"
                    ),
                    {"project": identity(9000), "job": JOBS[2]},
                )
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        record("setup_commit", {"identity": owner, "updates": updates, "acknowledged": True})
    finally:
        drain(pg)
    result = observe_inputs(fixture, pg, record)
    assert_setup_delta(before, result.before, fixture.project, case)
    after_progress = raw_progress(result, pg)
    assert typed(progress) == typed(after_progress)
    record(
        "overflow_setup",
        {
            "before": typed(before),
            "after": typed(result.before),
            "case": case,
            "money_cells": 5,
            "scope_cells": int(case == "organization"),
            "added_projects": int(case == "organization"),
            "raw_progress_before": progress,
            "raw_progress_after": after_progress,
        },
    )
    return result, progress
