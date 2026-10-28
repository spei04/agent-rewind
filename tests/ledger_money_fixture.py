"""Exact single-project money fixtures and independently derived integer assertions."""

import json
from copy import deepcopy

from ledger_eligibility_fixture import cohort_manifest, refreshed, rows
from ledger_provisioning_fixture import (
    canonical,
    ciphertexts,
    expected_opening,
    reader,
    snapshot,
    source_fingerprint,
    source_rows,
)

from agent_rewind.migrations.ledger_inputs import MAX_MONEY, validate_ledger_manifest

EXACT_AMOUNT = 9007199254740993


def assert_setup_delta(before, after, target):
    assert before["schema"] == after["schema"]
    assert set(before["tables"]) == set(after["tables"])
    for name, value in before["tables"].items():
        if name != "jobs":
            assert after["tables"][name] == value, name
    assert before["tables"]["jobs"]["columns"] == after["tables"]["jobs"]["columns"]
    original = {row["id"]: row for row in rows(before, "jobs")}
    changed = {row["id"]: row for row in rows(after, "jobs")}
    assert len(original) == len(changed) == len(rows(after, "jobs")) == 3
    assert set(original) == set(changed) and target == min(original)
    assert sorted(row["reserved"] for row in original.values()) == [35000, 85000, 125000]
    for identity, row in original.items():
        assert type(row["budget"]) is type(row["reserved"]) is int
        assert 0 <= row["reserved"] <= row["budget"] <= MAX_MONEY
        expected = {**row, "reserved": EXACT_AMOUNT if identity == target else 0}
        if identity == target:
            expected["budget"] = EXACT_AMOUNT
        assert changed[identity] == expected
        assert type(changed[identity]["budget"]) is type(changed[identity]["reserved"]) is int
    assert sum(row["reserved"] for row in changed.values()) == EXACT_AMOUNT


def exact_predecessor(fixture, record):
    before = snapshot(fixture.case.path)
    protected = ciphertexts(fixture.case)
    assert before == fixture.before and protected == fixture.encrypted and len(protected) == 18
    target = min(row["id"] for row in fixture.jobs)
    with fixture.case.engine.begin() as connection:
        assert (
            connection.exec_driver_sql(
                "UPDATE jobs SET budget=?,reserved=? WHERE id=?",
                (EXACT_AMOUNT, EXACT_AMOUNT, target),
            ).rowcount
            == 1
        )
        for row in fixture.jobs:
            if row["id"] != target:
                assert (
                    connection.exec_driver_sql(
                        "UPDATE jobs SET reserved=0 WHERE id=?", (row["id"],)
                    ).rowcount
                    == 1
                )
    after = snapshot(fixture.case.path)
    record(
        "money_setup",
        {
            "before": before,
            "after": after,
            "target_job": target,
            "scope": (
                "four committed synthetic setup cells: target budget/reserved "
                "and two other reservations"
            ),
        },
    )
    assert_setup_delta(before, after, target)
    result = refreshed(fixture)
    assert result.before == after and result.encrypted == protected
    assert result.original == source_rows(fixture.case.path)
    assert result.source == source_fingerprint(result.original)
    assert fixture.case.engine.pool.checkedout() == 0
    with reader(fixture.case.path) as connection:
        native = [
            dict(row)
            for row in connection.execute(
                "SELECT id,budget,reserved,typeof(budget) AS budget_type,"
                "typeof(reserved) AS reserved_type FROM jobs ORDER BY id"
            )
        ]
    record("native_setup_money", native)
    assert all(row["budget_type"] == row["reserved_type"] == "integer" for row in native)
    assert [{key: row[key] for key in ("id", "budget", "reserved")} for row in native] == [
        {key: row[key] for key in ("id", "budget", "reserved")} for row in result.jobs
    ]
    return result, target


def money_manifest(fixture):
    assert len(fixture.jobs) == 3
    assert {row["project_id"] for row in fixture.jobs} == {fixture.project}
    assert all(type(row["budget"]) is type(row["reserved"]) is int for row in fixture.jobs)
    assert all(0 <= row["reserved"] <= row["budget"] <= MAX_MONEY for row in fixture.jobs)
    total = sum(row["reserved"] for row in fixture.jobs)
    assert 0 <= total <= MAX_MONEY
    manifest = cohort_manifest(fixture)
    parsed = validate_ledger_manifest(manifest)
    assert parsed.canonical_bytes == canonical(manifest)
    assert len(parsed.accounts) == 5
    assert [row.limit_microusd for row in parsed.accounts if row.scope != "job"] == [total, total]
    assert all(type(row.limit_microusd) is int for row in parsed.accounts)
    return manifest


def below_job_cap(fixture):
    baseline = money_manifest(fixture)
    manifest = deepcopy(baseline)
    target = min(row["id"] for row in fixture.jobs)
    job = next(row for row in fixture.jobs if row["id"] == target)
    assert job["budget"] >= job["reserved"] > 0
    for row in manifest["accounts"]:
        if row["job_id"] == target:
            row["limit_microusd"] = job["reserved"] - 1
    assert_cap_manifest(fixture, baseline, manifest, target)
    return baseline, manifest, target


def assert_cap_manifest(fixture, baseline, manifest, target):
    assert baseline == money_manifest(fixture)
    expected = deepcopy(baseline)
    job = next(row for row in fixture.jobs if row["id"] == target)
    assert type(job["reserved"]) is int and job["budget"] >= job["reserved"] > 0
    (account,) = [row for row in expected["accounts"] if row["job_id"] == target]
    account["limit_microusd"] = job["reserved"] - 1
    assert manifest == expected
    validate_ledger_manifest(manifest)


def assert_exact_money(fixture, manifest, prepared, receipt, after, inspection):
    target = min(row["id"] for row in fixture.jobs)
    assert manifest == money_manifest(fixture)
    expected = expected_opening(fixture, manifest, receipt.initialized_at)
    assert expected["organization_opening_microusd"] == EXACT_AMOUNT
    assert all(type(row["budget"]) is type(row["reserved"]) is int for row in fixture.jobs)
    assert next(row for row in fixture.jobs if row["id"] == target)["reserved"] == EXACT_AMOUNT
    assert all(row["reserved"] == 0 for row in fixture.jobs if row["id"] != target)
    assert prepared["jobs"] == expected["jobs"]
    assert prepared["project_totals"] == expected["project_totals"]
    assert type(prepared["organization_opening"]) is int
    assert prepared["organization_opening"] == EXACT_AMOUNT
    assert type(receipt.imported_opening_microusd) is int
    assert receipt.imported_opening_microusd == EXACT_AMOUNT
    assert receipt.imported_jobs == 3 and receipt.account_rows == 5
    accounts = rows(after, "budget_accounts")
    assert len(accounts) == 5
    for row in accounts:
        amount = EXACT_AMOUNT if row["job_id"] in (None, target) else 0
        for key in (
            "limit_microusd",
            "opening_held_microusd",
            "held_microusd",
            "accounted_microusd",
        ):
            assert type(row[key]) is int
        assert row["opening_held_microusd"] == row["held_microusd"] == amount
        assert row["accounted_microusd"] == 0
    assert sum(row["held_microusd"] for row in accounts if row["scope"] == "job") == EXACT_AMOUNT
    assert [row["held_microusd"] for row in accounts if row["scope"] == "project"] == [EXACT_AMOUNT]
    assert [row["held_microusd"] for row in accounts if row["scope"] == "organization"] == [
        EXACT_AMOUNT
    ]
    progress = {
        row["phase"]: json.loads(row["cursor"])
        for row in rows(after, "migration_progress")
        if row["revision"] == "ar_0007_ledger"
    }
    opening = progress["ledger_opening"]
    cursor = progress["ledger_manifest_" + manifest["manifest_id"]]
    assert opening == expected
    assert type(opening["organization_opening_microusd"]) is int
    assert cursor["manifest"] == manifest
    assert type(cursor["imported_opening_microusd"]) is int
    assert cursor["imported_opening_microusd"] == EXACT_AMOUNT
    assert inspection["opening"] == expected
    assert type(inspection["head"]["imported_opening_microusd"]) is int
    assert inspection["head"]["imported_opening_microusd"] == EXACT_AMOUNT
