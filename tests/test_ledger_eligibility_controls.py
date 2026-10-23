"""Database-free controls for admission linkage and eligibility attribution oracles."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_eligibility_fixture import (
    CASES,
    CHANGES,
    assert_admitted,
    assert_single_cell_change,
    cohort_manifest,
    rows,
)
from ledger_eligibility_observer import (
    assert_eligibility_refusal,
    assert_preparation,
    observe_preparation,
)
from ledger_provisioning_fixture import identity

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def table(values):
    columns = tuple(values[0])
    return {"columns": columns, "rows": [tuple(row[key] for key in columns) for row in values]}


def example(case="admitted"):
    project, organization = identity(2), identity(1)
    accepted = {"job_id": identity(20), "operation_id": identity(30)}
    principal, digest = "oidc:" + "a" * 64, "c" * 64
    jobs = [
        {
            "id": identity(10),
            "kind": "run",
            "created": 1700000000.0,
            "payload": "d" * 64,
            "status": "succeeded",
            "owner": None,
            "lease_until": None,
            "cancel": 0,
            "budget": 50,
            "reserved": 13,
            "result": None,
            "error": None,
            "actor": principal,
            "payload_version": 1,
            "execution_config_ref": None,
            "execution_config_digest": None,
        },
        {
            "id": accepted["job_id"],
            "kind": "run",
            "created": 1700000001.0,
            "payload": "e" * 64,
            "status": "queued",
            "owner": None,
            "lease_until": None,
            "cancel": 0,
            "budget": 29,
            "reserved": 0,
            "result": None,
            "error": None,
            "actor": principal,
            "payload_version": 2,
            "execution_config_ref": digest,
            "execution_config_digest": digest,
        },
    ]
    target = accepted["job_id"]
    if case == "queued-v1":
        jobs[0].update(reserved=0)
        target = jobs[0]["id"]
    if case != "admitted":
        field, value = CHANGES[case]
        next(row for row in jobs if row["id"] == target)[field] = value
    scopes = [
        {"resource_kind": "job", "resource_id": row["id"], "project_id": project} for row in jobs
    ]
    state = {
        "schema": (),
        "tables": {
            "jobs": table(jobs),
            "resource_scopes": table(scopes),
            "operations": table(
                [
                    {
                        "id": accepted["operation_id"],
                        "job_id": accepted["job_id"],
                        "project_id": project,
                        "principal_id": principal,
                        "execution_config_digest": digest,
                        "payload_version": 2,
                        "kind": "run",
                        "accepted_response": json.dumps(accepted),
                    }
                ]
            ),
            "artifact_refs": table(
                [
                    {
                        "owner_kind": "job",
                        "owner_id": accepted["job_id"],
                        "role": "admission_config",
                        "project_id": project,
                        "artifact_id": identity(40),
                    }
                ]
            ),
            "artifact_objects": table(
                [
                    {
                        "id": identity(40),
                        "project_id": project,
                        "digest": digest,
                    }
                ]
            ),
        },
    }
    fixture = SimpleNamespace(
        case=SimpleNamespace(adoption={"installation_key": "test-installation"}),
        before=state,
        source="f" * 64,
        organization=organization,
        project=project,
        jobs=[
            {
                "id": row["id"],
                "budget": row["budget"],
                "reserved": row["reserved"],
                "project_id": project,
            }
            for row in jobs
        ],
    )
    return fixture, accepted, principal, digest, target


def association(fixture, accepted, principal, digest):
    return assert_admitted(
        fixture.before,
        accepted,
        project=fixture.project,
        principal=principal,
        config_digest=digest,
        budget=29,
    )


def replace_cell(state, table_name, row_index, field, value):
    value_table = state["tables"][table_name]
    row = list(value_table["rows"][row_index])
    row[value_table["columns"].index(field)] = value
    value_table["rows"][row_index] = tuple(row)


def test_admitted_oracle_binds_one_job_operation_scope_and_configuration():
    fixture, accepted, principal, digest, _ = example()
    found = association(fixture, accepted, principal, digest)
    assert found["operation"]["job_id"] == found["job"]["id"]
    assert found["reference"]["artifact_id"] == found["descriptor"]["id"]


@pytest.mark.parametrize(
    "change",
    [
        "wrong-job-state",
        "wrong-operation",
        "wrong-config",
        "wrong-principal",
        "wrong-scope",
        "wrong-reference",
        "wrong-descriptor",
        "duplicate-operation",
        "missing-reference",
        "wrong-accepted-response",
    ],
)
def test_admitted_oracle_rejects_incomplete_or_mismatched_associations(change):
    fixture, accepted, principal, digest, _ = example()
    state = fixture.before
    if change == "wrong-job-state":
        replace_cell(state, "jobs", 1, "status", "running")
    elif change == "wrong-operation":
        replace_cell(state, "operations", 0, "id", identity(99))
    elif change == "wrong-config":
        replace_cell(state, "jobs", 1, "execution_config_digest", "0" * 64)
    elif change == "wrong-principal":
        replace_cell(state, "operations", 0, "principal_id", "other")
    elif change == "wrong-scope":
        replace_cell(state, "resource_scopes", 1, "project_id", identity(99))
    elif change == "wrong-reference":
        replace_cell(state, "artifact_refs", 0, "project_id", identity(99))
    elif change == "wrong-descriptor":
        replace_cell(state, "artifact_objects", 0, "digest", "0" * 64)
    elif change == "duplicate-operation":
        state["tables"]["operations"]["rows"] *= 2
    elif change == "missing-reference":
        state["tables"]["artifact_refs"]["rows"].clear()
    elif change == "wrong-accepted-response":
        replace_cell(state, "operations", 0, "accepted_response", "{}")
    with pytest.raises((AssertionError, ValueError)):
        association(fixture, accepted, principal, digest)


@pytest.mark.parametrize("reserved", [0, 13, 37])
def test_manifest_totals_follow_complete_sql_cohort_including_zero_job(reserved):
    fixture, accepted, _, _, _ = example()
    fixture.jobs[0]["reserved"] = reserved
    manifest = cohort_manifest(fixture)
    checked = validate_ledger_manifest(manifest)
    assert len(checked.accounts) == len(fixture.jobs) + 2
    assert {row.job_id for row in checked.accounts if row.scope == "job"} == {
        identity(10),
        accepted["job_id"],
    }
    assert [row.limit_microusd for row in checked.accounts if row.scope != "job"] == [
        reserved,
        reserved,
    ]
    assert [row.limit_microusd for row in checked.accounts if row.scope == "job"] == [50, 29]


@pytest.mark.parametrize("change", ["none", "other-job", "operation", "schema", "missing-job"])
def test_single_cell_oracle_rejects_collateral_mutation(change):
    fixture, accepted, _, _, _ = example()
    before, after = fixture.before, deepcopy(fixture.before)
    replace_cell(after, "jobs", 1, "status", "running")
    if change == "other-job":
        replace_cell(after, "jobs", 0, "budget", 51)
    elif change == "operation":
        replace_cell(after, "operations", 0, "kind", "other")
    elif change == "schema":
        after["schema"] = ("changed",)
    elif change == "missing-job":
        after["tables"]["jobs"]["rows"].pop(0)
    if change == "none":
        assert_single_cell_change(before, after, accepted["job_id"], "status", "running")
    else:
        with pytest.raises(AssertionError):
            assert_single_cell_change(before, after, accepted["job_id"], "status", "running")


def delegated(case, monkeypatch):
    fixture, _, _, _, target = example(case)
    manifest = cohort_manifest(fixture)
    engine, raw = object(), object()
    work = SimpleNamespace(_connection=SimpleNamespace(engine=engine), _raw=raw, check=lambda: None)
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(raws=[raw], events=[]),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
        markers=[
            (name, id(raw), 0)
            for name in (
                "rollback.before_native",
                "rollback.native_ack",
                "connection.close.before",
                "connection.close.return",
                "command.exit",
            )
        ],
    )
    state = {"status": "absent", "head": None, "revision": "ar_0006_admission"}
    context = SimpleNamespace(
        state=SimpleNamespace(
            manifest_count=0,
            account_count=0,
            model_dump=lambda **kwargs: dict(state),
        ),
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=fixture.organization),
            manifests=(),
            opening=None,
            adoption={"installed_schema_fingerprint": "b" * 64},
        ),
        financial={
            "job": rows(fixture.before, "jobs"),
            "scope": rows(fixture.before, "resource_scopes"),
            "account": [],
        },
    )
    recorded = []
    caught = None
    with observe_preparation(watch, monkeypatch, lambda *value: recorded.append(value)) as observed:
        try:
            ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), work)
        except MigrationRefused as error:
            caught = error
    (entry,), stages = observed
    assert len(recorded) == 1
    return fixture, manifest, watch, entry, stages, caught, target


@pytest.mark.parametrize("case", CASES)
def test_delegated_pure_preparation_preserves_actual_refusal_site_and_identity(case, monkeypatch):
    fixture, manifest, watch, entry, stages, error, target = delegated(case, monkeypatch)
    assert_preparation(entry, fixture, manifest, watch)
    if case == "admitted":
        assert error is None and stages == ["prepare.enter", "prepare.return"]
        assert entry["prepared"]["organization_opening"] == 13
        assert len(entry["prepared"]["jobs"]) == 2
    else:
        assert_eligibility_refusal(entry, stages, error, watch, target_job=target)
        assert entry["traceback"]["frames"][-1]["line"] == entry["eligibility_line"]


@pytest.mark.parametrize(
    "change",
    [
        "wrong-raw",
        "wrong-work",
        "wrong-manifest",
        "stale-fingerprint",
        "missing-job",
        "wrong-scope",
        "account-present",
    ],
)
def test_preparation_context_oracle_rejects_stale_or_different_input(change, monkeypatch):
    fixture, manifest, watch, entry, _, _, _ = delegated("running", monkeypatch)
    if change == "wrong-raw":
        entry["raw_id"] += 1
    elif change == "wrong-work":
        entry["work_id"] += 1
    elif change == "wrong-manifest":
        entry["manifest"]["manifest_id"] = identity(99)
    elif change == "stale-fingerprint":
        fixture.source = "a" * 64
    elif change == "missing-job":
        entry["financial"]["job"].pop()
    elif change == "wrong-scope":
        entry["financial"]["scope"][0]["project_id"] = identity(99)
    elif change == "account-present":
        entry["financial"]["account"].append({"id": identity(99)})
    with pytest.raises(AssertionError):
        assert_preparation(entry, fixture, manifest, watch)


@pytest.mark.parametrize(
    "change",
    [
        "earlier-raise",
        "wrong-rejected-job",
        "wrong-exception",
        "changed-assignment",
        "preparation-returned",
        "write-stage",
        "commit-attempted",
        "rollback-not-acknowledged",
        "cleanup-before-rollback",
    ],
)
def test_refusal_oracle_rejects_earlier_or_wrong_job_and_physical_outcome(change, monkeypatch):
    _, _, watch, entry, stages, error, target = delegated("running", monkeypatch)
    if change == "earlier-raise":
        entry["traceback"]["preparation_frames"][0]["line"] -= 12
    elif change == "wrong-rejected-job":
        entry["traceback"]["preparation_frames"][0]["job_id"] = identity(10)
    elif change == "wrong-exception":
        error = MigrationRefused("ledger_history_unsupported")
    elif change == "changed-assignment":
        entry["traceback"]["preparation_frames"][0]["assignments"].clear()
    elif change == "preparation-returned":
        entry["prepared"] = {}
    elif change == "write-stage":
        stages.append("write:accounts.insert")
    elif change == "commit-attempted":
        watch.outcome.commit_attempted = True
    elif change == "rollback-not-acknowledged":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "cleanup-before-rollback":
        watch.markers[1], watch.markers[2] = watch.markers[2], watch.markers[1]
    with pytest.raises(AssertionError):
        assert_eligibility_refusal(entry, stages, error, watch, target_job=target)
