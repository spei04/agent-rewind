"""Native typed money inputs and exact single-project opening observations."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

from ledger_eligibility_fixture import rows
from ledger_money_fixture import EXACT_AMOUNT, money_manifest
from ledger_provisioning_fixture import digest, expected_opening, expected_stage, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    canonical_cursor,
    encrypted_files,
    native_snapshot,
    source_rows,
)
from ledger_restore_authority import typed
from sqlalchemy import BigInteger, bindparam, text
from test_run_projection_postgres import drain

from agent_rewind.migrations.schema import LEDGER, installed_profile

JOB_TYPES_SQL = (
    "SELECT j.id,j.budget,j.reserved,s.project_id,"
    "pg_typeof(j.budget)::text AS budget_type,pg_typeof(j.reserved)::text AS reserved_type "
    "FROM jobs j JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
    "ORDER BY j.id"
)
ACCOUNT_TYPES_SQL = (
    "SELECT id,pg_typeof(limit_microusd)::text AS limit_type,"
    "pg_typeof(opening_held_microusd)::text AS opening_type,"
    "pg_typeof(held_microusd)::text AS held_type,"
    "pg_typeof(accounted_microusd)::text AS accounted_type "
    "FROM budget_accounts ORDER BY id"
)
PROGRESS_TEXT_SQL = (
    "SELECT phase,cursor::text AS cursor FROM migration_progress "
    "WHERE revision='ar_0007_ledger' ORDER BY phase"
)
MONEY_FIELDS = (
    "limit_microusd",
    "opening_held_microusd",
    "held_microusd",
    "accounted_microusd",
)


def assert_job_types(state, observed):
    jobs = sorted(rows(state, "jobs"), key=lambda row: row["id"])
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in rows(state, "resource_scopes")
        if row["resource_kind"] == "job"
    }
    assert len(jobs) == len(scopes) == len(observed) == 3
    expected = []
    for row in jobs:
        assert type(row["budget"]) is type(row["reserved"]) is int
        expected.append(
            {
                "id": row["id"],
                "budget": row["budget"],
                "reserved": row["reserved"],
                "project_id": scopes[row["id"]],
                "budget_type": "bigint",
                "reserved_type": "bigint",
            }
        )
    assert typed(observed) == typed(expected)
    return [
        {key: row[key] for key in ("id", "budget", "reserved", "project_id")} for row in observed
    ]


def assert_setup_delta(before, after, target):
    expected = deepcopy(before)
    original = sorted(rows(before, "jobs"), key=lambda row: row["id"])
    assert len(original) == 3 and target == original[0]["id"]
    assert [row["budget"] for row in original] == [10000000, 10000000, 5000000]
    assert [row["reserved"] for row in original] == [125000, 85000, 35000]
    table = expected["tables"]["jobs"]
    changed = []
    for row in original:
        assert type(row["budget"]) is type(row["reserved"]) is int
        row = {**row, "reserved": EXACT_AMOUNT if row["id"] == target else 0}
        if row["id"] == target:
            row["budget"] = EXACT_AMOUNT
        changed.append(tuple(row[key] for key in table["columns"]))
    table["rows"] = tuple(sorted(changed, key=repr))
    assert typed(after) == typed(expected), "only four native money cells may change"


def observe_inputs(fixture, pg, record):
    state = native_snapshot(fixture.case, pg)
    try:
        with fixture.case.engine.connect() as connection:
            original = source_rows(connection)
            observed = [dict(row) for row in connection.exec_driver_sql(JOB_TYPES_SQL).mappings()]
    finally:
        drain(pg)
    jobs = assert_job_types(state, observed)
    protected = encrypted_files(fixture)
    assert protected == fixture.encrypted and len(protected) == 18
    record("native_job_types", observed)
    return replace(
        fixture,
        before=state,
        original=original,
        source=source_fingerprint(original),
        jobs=jobs,
        encrypted=protected,
    )


def exact_predecessor(fixture, pg, record):
    before = native_snapshot(fixture.case, pg)
    assert typed(before) == typed(fixture.before)
    assert encrypted_files(fixture) == fixture.encrypted and len(fixture.encrypted) == 18
    target = min(row["id"] for row in fixture.jobs)
    updates = []
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            identity = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert identity == (pg["owner_role"], pg["owner"].url.database)
            for row in fixture.jobs:
                selected = row["id"] == target
                sql = (
                    "UPDATE jobs SET budget=:amount,reserved=:amount WHERE id=:id"
                    if selected
                    else "UPDATE jobs SET reserved=:amount WHERE id=:id"
                )
                values = {"amount": EXACT_AMOUNT if selected else 0, "id": row["id"]}
                statement = text(sql).bindparams(bindparam("amount", type_=BigInteger))
                count = connection.execute(statement, values).rowcount
                updates.append({"sql": sql, "parameters": values, "rowcount": count})
                assert count == 1
        record("setup_commit", {"identity": identity, "updates": updates, "acknowledged": True})
    finally:
        drain(pg)
    result = observe_inputs(fixture, pg, record)
    record(
        "money_setup",
        {"before": typed(before), "after": typed(result.before), "target_job": target},
    )
    assert_setup_delta(before, result.before, target)
    return result, target


def observe_result(fixture, pg):
    try:
        with fixture.case.engine.connect() as connection:
            account_types = [
                dict(row) for row in connection.exec_driver_sql(ACCOUNT_TYPES_SQL).mappings()
            ]
            progress_text = [
                dict(row) for row in connection.exec_driver_sql(PROGRESS_TEXT_SQL).mappings()
            ]
    finally:
        drain(pg)
    return account_types, progress_text


def assert_exact_result(
    fixture, manifest, prepared, receipt, after, inspection, account_types, progress_text, role
):
    """Strict native values supplement the existing complete provisioning oracle."""
    assert typed(manifest) == typed(money_manifest(fixture))
    expected = expected_opening(fixture, manifest, receipt.initialized_at)
    assert typed(prepared) == typed(
        {
            "jobs": expected["jobs"],
            "project_totals": expected["project_totals"],
            "organization_opening": EXACT_AMOUNT,
        }
    )
    assert expected["organization_opening_microusd"] == EXACT_AMOUNT
    observed_receipt = receipt.model_dump(mode="json")
    for key in ("sequence", "account_rows", "imported_jobs", "imported_opening_microusd"):
        assert type(observed_receipt[key]) is int
    accounts, progress, state = expected_stage(fixture, [manifest], [receipt], database_role=role)
    native_accounts = []
    for account in accounts:
        account = dict(account)
        for field in ("period_start", "period_end"):
            account[field] = datetime.fromisoformat(account[field].replace("Z", "+00:00"))
        native_accounts.append(account)
    actual = sorted(rows(after, "budget_accounts"), key=lambda row: row["id"])
    comparable = deepcopy(actual)
    for row in comparable:
        for field in ("period_start", "period_end"):
            assert type(row[field]) is datetime and row[field].utcoffset() is not None
            row[field] = row[field].astimezone(UTC)
        assert all(type(row[field]) is int for field in MONEY_FIELDS)
    assert typed(comparable) == typed(sorted(native_accounts, key=lambda row: row["id"]))
    assert typed(account_types) == typed(
        [
            {
                "id": row["id"],
                "limit_type": "bigint",
                "opening_type": "bigint",
                "held_type": "bigint",
                "accounted_type": "bigint",
            }
            for row in actual
        ]
    )
    native_progress = [
        row for row in rows(after, "migration_progress") if row["revision"] == "ar_0007_ledger"
    ]
    assert len(native_progress) == len(progress_text) == len(progress) == 2
    assert [row["phase"] for row in progress_text] == sorted(progress)
    texts = {row["phase"]: row["cursor"] for row in progress_text}
    assert {row["phase"] for row in native_progress} == set(progress)
    for row in native_progress:
        cursor, count, source = progress[row["phase"]]
        assert type(row["cursor"]) is dict and type(texts[row["phase"]]) is str
        decoded = json.loads(canonical_cursor(texts[row["phase"]]))
        assert typed(decoded) == typed(row["cursor"]) == typed(cursor)
        observed_time = row["updated_at"]
        assert type(observed_time) is datetime and observed_time.utcoffset() is not None
        projected = {**row, "updated_at": observed_time.astimezone(UTC)}
        assert typed(projected) == typed(
            {
                "revision": "ar_0007_ledger",
                "phase": row["phase"],
                "source_digest": source,
                "cursor": cursor,
                "rows_verified": count,
                "status": "complete",
                "updated_at": datetime.fromisoformat(receipt.initialized_at.replace("Z", "+00:00")),
            }
        )
    assert typed(inspection) == typed(state)
    for row in rows(after, "jobs"):
        job = next(job for job in fixture.jobs if job["id"] == row["id"])
        assert type(row["legacy_reserved_microusd"]) is type(row["lease_generation"]) is int
        assert row["legacy_reserved_microusd"] == job["reserved"] and row["lease_generation"] == 0

    # Existing complete provisioning checks establish allowed additions; retain
    # exact native types for every unrelated old cell as an independent witness.
    for name, before in fixture.before["tables"].items():
        if name not in {"jobs", "alembic_version", "installation_adoptions", "migration_progress"}:
            assert typed(after["tables"][name]) == typed(before), name
        elif name == "jobs":
            actual_jobs = {row["id"]: row for row in rows(after, name)}
            for old in rows(fixture.before, name):
                assert typed({key: actual_jobs[old["id"]][key] for key in old}) == typed(old)
        elif name == "migration_progress":
            previous = [
                tuple(row[key] for key in before["columns"])
                for row in rows(after, name)
                if row["revision"] != LEDGER
            ]
            assert typed(tuple(sorted(previous, key=repr))) == typed(before["rows"])
        else:
            expected_table = deepcopy(before)
            changed = []
            for row in rows(fixture.before, name):
                if name == "alembic_version":
                    row["version_num"] = LEDGER
                else:
                    row["installed_schema_fingerprint"] = digest(
                        installed_profile("postgresql", LEDGER)
                    )
                changed.append(tuple(row[key] for key in before["columns"]))
            expected_table["rows"] = tuple(sorted(changed, key=repr))
            assert typed(after["tables"][name]) == typed(expected_table)
