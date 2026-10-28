"""Native type checks around the shared complete-cohort witnesses."""

from ledger_cohort_fixture import assert_cohort_change
from ledger_cohort_observer import assert_cohort_refusal
from ledger_eligibility_fixture import cohort_manifest, rows
from ledger_eligibility_observer import assert_preparation
from ledger_eligibility_postgres_fixture import assert_native_jobs
from ledger_restore_authority import typed


def assert_native_cohort_change(fixture, baseline, manifest, case, target, admitted_job):
    assert_cohort_change(fixture, baseline, manifest, case, target, admitted_job)
    assert_native_jobs(fixture.before)
    assert typed(baseline) == typed(cohort_manifest(fixture))
    assert typed({key: value for key, value in baseline.items() if key != "accounts"}) == typed(
        {key: value for key, value in manifest.items() if key != "accounts"}
    )
    previous = {row["id"]: row for row in baseline["accounts"]}
    (template,) = [row for row in previous.values() if row["job_id"] == admitted_job]
    for account in manifest["accounts"]:
        if account["id"] in previous:
            assert typed(account) == typed(previous[account["id"]])
        else:
            # The shared oracle checks the three new string identities and sole addition.
            unchanged = {"id", "scope_id", "job_id"}
            assert typed(
                {key: value for key, value in account.items() if key not in unchanged}
            ) == typed({key: value for key, value in template.items() if key not in unchanged})


def assert_native_preparation(entry, fixture, manifest, watch):
    assert_preparation(entry, fixture, manifest, watch)
    assert typed(entry["manifest"]) == typed(manifest)
    assert typed(sorted(entry["financial"]["job"], key=lambda row: row["id"])) == typed(
        sorted(rows(fixture.before, "jobs"), key=lambda row: row["id"])
    )
    expected_scopes = [
        row for row in rows(fixture.before, "resource_scopes") if row["resource_kind"] == "job"
    ]
    assert typed(sorted(entry["financial"]["scope"], key=lambda row: row["resource_id"])) == typed(
        sorted(expected_scopes, key=lambda row: row["resource_id"])
    )


def assert_native_cohort_refusal(entry, stages, error, watch, *, case, target_job):
    assert_cohort_refusal(entry, stages, error, watch, case=case, target_job=target_job)
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
    accounts = entry["manifest"]["accounts"]
    assignments = {row["job_id"]: row for row in accounts if row["scope"] == "job"}
    if case == "nonexistent-job":
        assert typed(rejected["account"]) == typed(assignments[target_job])
    else:
        assert typed(rejected["assignments"]) == typed(assignments)
        assert typed(rejected["account"]) == typed(accounts[-1])
        assert typed(rejected["job"]) == typed(jobs[accounts[-1]["job_id"]])
