"""Native typed witnesses for a present job bound to another genuine project."""

from ledger_cohort_postgres_fixture import assert_native_preparation
from ledger_competing_distinct_postgres import assert_added_project
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import assert_native_jobs
from ledger_project_binding import (
    assert_binding_manifest,
    assert_binding_refusal,
    binding_manifest,
)
from ledger_restore_authority import typed


def assert_native_project_setup(setup, original_project, other_project):
    before, after = setup["before"], setup["after"]
    added = assert_added_project(before, after, original_project, other_project)
    assert typed(setup["added_project"]) == typed(added)
    assert typed({key: value for key, value in before.items() if key != "tables"}) == typed(
        {key: value for key, value in after.items() if key != "tables"}
    )
    for name, table in before["tables"].items():
        if name != "projects":
            assert typed(table) == typed(after["tables"][name])
    assert typed(before["tables"]["projects"]["columns"]) == typed(
        after["tables"]["projects"]["columns"]
    )
    (original,) = rows(before, "projects")
    assert typed([row for row in rows(after, "projects") if row["id"] != other_project]) == typed(
        [original]
    )
    assert typed(added) == typed(
        {**original, "id": other_project, "name": "Independent project", "run_sequence": 0}
    )


def assert_native_binding_manifest(fixture, baseline, manifest, target, other_project):
    assert_binding_manifest(fixture, baseline, manifest, target, other_project)
    assert_native_jobs(fixture.before)
    expected_baseline, expected_manifest = binding_manifest(fixture, target, other_project)
    assert typed(baseline) == typed(expected_baseline)
    assert typed(manifest) == typed(expected_manifest)


def assert_native_binding_refusal(
    fixture, manifest, target, other_project, projects, entry, stages, error, watch
):
    assert_binding_refusal(
        fixture, manifest, target, other_project, projects, entry, stages, error, watch
    )
    assert_native_preparation(entry, fixture, manifest, watch)
    (gate,) = projects
    assert typed(gate["manifest"]) == typed(entry["manifest"]) == typed(manifest)
    (rejected,) = entry["traceback"]["preparation_frames"]
    jobs = {row["id"]: row for row in entry["financial"]["job"]}
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in entry["financial"]["scope"]
        if row["resource_kind"] == "job"
    }
    assert typed(rejected["jobs"]) == typed(jobs)
    assert typed(rejected["scopes"]) == typed(scopes)
    assert typed(rejected["current"]) == typed(entry["financial"]["account"]) == typed([])
    assert typed(rejected["job"]) == typed(jobs[target])
    (account,) = [row for row in manifest["accounts"] if row["job_id"] == target]
    assert typed(rejected["account"]) == typed(account)
