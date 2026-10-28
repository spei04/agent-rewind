"""Focused manifest project mismatch and original project-gate observations."""

from contextlib import contextmanager
from copy import deepcopy

from ledger_cohort_observer import cohort_sites
from ledger_eligibility_fixture import cohort_manifest, rows
from ledger_eligibility_observer import assert_preparation
from ledger_provisioning_fixture import identity

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

PROJECT_ACCOUNT = identity(8000)


def binding_manifest(fixture, target_job, other_project):
    baseline = cohort_manifest(fixture)
    manifest = deepcopy(baseline)
    (project,) = [
        row
        for row in baseline["accounts"]
        if row["scope"] == "project" and row["project_id"] == fixture.project
    ]
    for account in manifest["accounts"]:
        if account["job_id"] == target_job:
            account["project_id"] = other_project
    manifest["accounts"].append(
        {
            **project,
            "id": PROJECT_ACCOUNT,
            "scope_id": other_project,
            "project_id": other_project,
            "limit_microusd": 0,
        }
    )
    manifest["accounts"].sort(key=lambda row: row["id"])
    manifest["opening_accounts"]["projects"].append(
        {
            "project_id": other_project,
            "account_id": PROJECT_ACCOUNT,
        }
    )
    manifest["opening_accounts"]["projects"].sort(key=lambda row: row["project_id"])
    assert_binding_manifest(fixture, baseline, manifest, target_job, other_project)
    return baseline, manifest


def assert_binding_manifest(fixture, baseline, manifest, target_job, other_project):
    assert baseline == cohort_manifest(fixture)
    validate_ledger_manifest(baseline)
    validate_ledger_manifest(manifest)
    assert fixture.project != other_project
    projects = rows(fixture.before, "projects")
    assert len(projects) == 2
    assert {row["id"] for row in projects} == {fixture.project, other_project}
    assert {row["organization_id"] for row in projects} == {fixture.organization}
    jobs = {row["id"]: row for row in rows(fixture.before, "jobs")}
    target = jobs[target_job]
    assert (
        target["status"],
        target["payload_version"],
        target["reserved"],
        target["owner"],
        target["lease_until"],
    ) == ("queued", 2, 0, None, None)
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in rows(fixture.before, "resource_scopes")
        if row["resource_kind"] == "job"
    }
    assert scopes[target_job] == fixture.project
    assert {k: v for k, v in baseline.items() if k not in {"accounts", "opening_accounts"}} == {
        k: v for k, v in manifest.items() if k not in {"accounts", "opening_accounts"}
    }
    old = {row["id"]: row for row in baseline["accounts"]}
    new = {row["id"]: row for row in manifest["accounts"]}
    assert PROJECT_ACCOUNT not in old
    assert len(new) == len(manifest["accounts"]) == len(old) + 1
    assert set(new) == set(old) | {PROJECT_ACCOUNT}
    for key, row in old.items():
        expected = {**row, "project_id": other_project} if row["job_id"] == target_job else row
        assert new[key] == expected
    (original_project,) = [
        row
        for row in old.values()
        if row["scope"] == "project" and row["project_id"] == fixture.project
    ]
    assert new[PROJECT_ACCOUNT] == {
        **original_project,
        "id": PROJECT_ACCOUNT,
        "scope_id": other_project,
        "project_id": other_project,
        "limit_microusd": 0,
    }
    assert manifest["opening_accounts"] == {
        **baseline["opening_accounts"],
        "projects": sorted(
            [
                *baseline["opening_accounts"]["projects"],
                {"project_id": other_project, "account_id": PROJECT_ACCOUNT},
            ],
            key=lambda row: row["project_id"],
        ),
    }
    assert manifest["accounts"] == sorted(manifest["accounts"], key=lambda row: row["id"])
    requested = [row for row in manifest["accounts"] if row["scope"] == "job"]
    assert len(requested) == len(jobs)
    assert {row["job_id"] for row in requested} == set(jobs)
    assert {row["project_id"] for row in requested} == {fixture.project, other_project}


@contextmanager
def observe_projects(watch, monkeypatch, record, *, raw_handle=None):
    entries = []
    original = ledger_service._projects

    def projects(connection, manifest, organization, work):
        assert work is watch.work and connection is work._connection
        assert connection.engine is watch.engine
        assert work._raw is (watch.trace.raws[0] if raw_handle is None else raw_handle(watch))
        entry = {
            "raw_id": id(work._raw),
            "work_id": id(work),
            "connection_id": id(connection),
            "engine_id": id(watch.engine),
            "organization": organization,
            "manifest": manifest.model_dump(mode="json"),
            "trace_position": len(watch.trace.events),
        }
        entries.append(entry)
        try:
            result = original(connection, manifest, organization, work)
        except BaseException as error:
            entry["error"] = {
                "type": type(error).__name__,
                "code": getattr(error, "code", None),
                "identity": id(error),
            }
            entry["error_trace_position"] = len(watch.trace.events)
            raise
        entry["returned"] = True
        entry["return_trace_position"] = len(watch.trace.events)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_projects", projects)
        try:
            yield entries
        finally:
            record("projects_gate", entries)


def assert_binding_refusal(
    fixture, manifest, target_job, other_project, projects, entry, stages, error, watch
):
    assert_preparation(entry, fixture, manifest, watch)
    assert type(error) is MigrationRefused and error.code == "ledger_history_unsupported"
    assert entry["error"] == {
        "type": "MigrationRefused",
        "code": "ledger_history_unsupported",
        "identity": id(error),
    }
    assert "returned" not in entry and stages == ["prepare.enter", "prepare.refused"]
    (gate,) = projects
    assert "error" not in gate and gate["returned"] is True
    assert gate["raw_id"] == entry["raw_id"] == id(watch.work._raw)
    assert gate["work_id"] == entry["work_id"] == id(watch.work)
    assert gate["connection_id"] == id(watch.work._connection)
    assert gate["engine_id"] == entry["engine_id"] == id(watch.engine)
    assert gate["organization"] == entry["organization"] == fixture.organization
    assert gate["manifest"] == entry["manifest"] == manifest
    assert gate["trace_position"] < gate["return_trace_position"] <= entry["trace_position"]
    (rejected,) = entry["traceback"]["preparation_frames"]
    assert entry["sites"] == cohort_sites()[1]
    assert rejected["line"] == entry["sites"]["missing-job"]
    jobs = {row["id"]: row for row in entry["financial"]["job"]}
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in entry["financial"]["scope"]
        if row["resource_kind"] == "job"
    }
    assert rejected["jobs"] == jobs and rejected["scopes"] == scopes
    assert rejected["current"] == entry["financial"]["account"] == []
    requested = {row["job_id"]: row for row in manifest["accounts"] if row["scope"] == "job"}
    assert set(requested) == set(jobs) and rejected["assignments"] is None
    assert rejected["job"] == jobs[target_job] and rejected["job"] is not None
    assert scopes[target_job] == fixture.project != other_project
    assert rejected["account"] == requested[target_job]
    assert rejected["account"]["project_id"] == other_project
    assert {row["id"] for row in rows(fixture.before, "projects")} == {
        fixture.project,
        other_project,
    }
    for job_id, account in requested.items():
        if job_id != target_job:
            assert account["project_id"] == scopes[job_id]
    assert watch.outcome.confirmed_precommit_rollback
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    markers = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in markers] == names
    assert all(row[1] == entry["raw_id"] for row in markers)
    assert entry["trace_position"] <= entry["refusal_trace_position"] <= markers[0][2]
    assert "commit.before_native" not in [row[0] for row in watch.markers]
