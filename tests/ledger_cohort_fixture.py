"""Single-account manifest changes against an unchanged admitted predecessor."""

from copy import deepcopy

from ledger_eligibility_fixture import cohort_manifest, rows
from ledger_provisioning_fixture import identity

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest

CASES = ("omit-admitted-zero", "omit-reserved-legacy", "nonexistent-job")


def cohort_change(fixture, admitted_job, case):
    assert case in CASES
    baseline = cohort_manifest(fixture)
    manifest = deepcopy(baseline)
    if case == "omit-admitted-zero":
        target = admitted_job
    elif case == "omit-reserved-legacy":
        target = sorted(
            row["id"]
            for row in rows(fixture.before, "jobs")
            if row["payload_version"] == 1 and row["reserved"] > 0
        )[0]
    else:
        target = identity(20000)
    if case.startswith("omit-"):
        manifest["accounts"] = [row for row in manifest["accounts"] if row["job_id"] != target]
    else:
        (template,) = [row for row in baseline["accounts"] if row["job_id"] == admitted_job]
        added = {
            **template,
            "id": identity(10000),
            "scope_id": target,
            "job_id": target,
        }
        manifest["accounts"] = sorted([*manifest["accounts"], added], key=lambda row: row["id"])
    assert_cohort_change(fixture, baseline, manifest, case, target, admitted_job)
    return baseline, manifest, target


def assert_cohort_change(fixture, baseline, manifest, case, target, admitted_job):
    """Require exactly one membership delta, including parser-valid project coverage."""
    assert case in CASES
    assert baseline == cohort_manifest(fixture)
    validate_ledger_manifest(baseline)
    validate_ledger_manifest(manifest)
    assert {k: v for k, v in baseline.items() if k != "accounts"} == {
        k: v for k, v in manifest.items() if k != "accounts"
    }
    jobs = {row["id"]: row for row in rows(fixture.before, "jobs")}
    before = {row["id"]: row for row in baseline["accounts"]}
    after = {row["id"]: row for row in manifest["accounts"]}
    assert len(before) == len(baseline["accounts"])
    assert len(after) == len(manifest["accounts"])
    assert {row["job_id"] for row in before.values() if row["scope"] == "job"} == set(jobs)
    if case.startswith("omit-"):
        assert target in jobs
        (removed,) = [row for row in before.values() if row["job_id"] == target]
        assert after == {key: row for key, row in before.items() if key != removed["id"]}
        if case == "omit-admitted-zero":
            assert target == admitted_job
            job = jobs[target]
            assert (
                job["status"],
                job["payload_version"],
                job["reserved"],
                job["owner"],
                job["lease_until"],
            ) == ("queued", 2, 0, None, None)
        else:
            assert target != admitted_job
            assert jobs[target]["payload_version"] == 1 and jobs[target]["reserved"] > 0
    else:
        assert target not in jobs
        assert set(before) < set(after) and len(after) == len(before) + 1
        assert {key: after[key] for key in before} == before
        (added,) = [row for key, row in after.items() if key not in before]
        (template,) = [row for row in before.values() if row["job_id"] == admitted_job]
        assert added == {
            **template,
            "id": identity(10000),
            "scope_id": target,
            "job_id": target,
        }
        assert added["project_id"] == fixture.project
    assert manifest["accounts"] == sorted(manifest["accounts"], key=lambda row: row["id"])
    assert {row["project_id"] for row in after.values() if row["scope"] == "job"} == {
        row["project_id"] for row in baseline["opening_accounts"]["projects"]
    }
