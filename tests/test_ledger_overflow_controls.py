"""Database-free mutation controls for overflow setup and original reductions."""

import json
from copy import deepcopy

import pytest
from ledger_eligibility_fixture import rows
from ledger_overflow_fixture import (
    CASES,
    HALF,
    JOBS,
    OVERFLOW,
    assert_move_candidate,
    assert_setup_delta,
    overflow_manifest,
)
from ledger_overflow_observer import assert_overflow_refusal, observe_overflow, sum_sites
from ledger_provisioning_fixture import identity
from test_ledger_eligibility_controls import replace_cell, table
from test_ledger_money_controls import context_for, legacy_example

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import MAX_MONEY, validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def original_example():
    fixture = legacy_example()
    fixture.project, fixture.organization = "9" * 32, "8" * 32
    jobs = rows(fixture.before, "jobs")
    for i, row in enumerate(jobs):
        row.update(
            id=JOBS[i],
            status="failed" if i == 2 else "succeeded",
            payload_version=1,
            owner=None,
            lease_until=None,
            result=None,
            execution_config_ref=None,
            execution_config_digest=None,
        )
    fixture.before["tables"]["jobs"] = table(jobs)
    fixture.before["tables"]["projects"] = table(
        [
            {
                "id": fixture.project,
                "organization_id": fixture.organization,
                "name": "Legacy project",
                "created_at": "2026-01-01T00:00:00+00:00",
                "run_sequence": 2,
            }
        ]
    )
    records = [
        {
            "id": str(i + 1) * 32,
            "kind": "run",
            "data": json.dumps(
                {
                    "job_id": JOBS[i],
                    "parent_id": None if i == 0 else "1" * 32,
                }
            ),
        }
        for i in range(2)
    ]
    fixture.before["tables"]["records"] = table(records)
    fixture.before["tables"]["run_index"] = table(
        [{"run_id": row["id"], "project_id": fixture.project} for row in records]
    )
    scopes = [
        {"resource_kind": "job", "resource_id": job, "project_id": fixture.project} for job in JOBS
    ]
    scopes += [
        {"resource_kind": "key", "resource_id": str(i) * 32, "project_id": fixture.project}
        for i in (3, 4)
    ]
    scopes += [
        {"resource_kind": "run", "resource_id": row["id"], "project_id": fixture.project}
        for row in records
    ]
    fixture.before["tables"]["resource_scopes"] = table(scopes)
    for name in ("artifact_refs", "artifact_objects", "operations", "operation_keys"):
        fixture.before["tables"][name] = {"columns": ("id",), "rows": []}
    fixture.jobs = [
        {key: row[key] for key in ("id", "budget", "reserved")} | {"project_id": fixture.project}
        for row in jobs
    ]
    return fixture


def changed_example(case):
    fixture = original_example()
    before = deepcopy(fixture.before)
    for i, row in enumerate(fixture.jobs):
        row["reserved"] = 0 if i == 1 else HALF
        replace_cell(fixture.before, "jobs", i, "reserved", row["reserved"])
        if i != 1:
            row["budget"] = HALF
            replace_cell(fixture.before, "jobs", i, "budget", HALF)
    if case == "organization":
        (old,) = rows(fixture.before, "projects")
        fixture.before["tables"]["projects"] = table(
            [
                {**old, "id": identity(9000), "name": "Independent project", "run_sequence": 0},
                old,
            ]
        )
        replace_cell(fixture.before, "resource_scopes", 2, "project_id", identity(9000))
        fixture.jobs[2]["project_id"] = identity(9000)
    assert_setup_delta(before, fixture.before, fixture.project, case)
    return fixture, before


def refused(monkeypatch, case, *, earlier=None, interrupt=None):
    fixture, _ = changed_example(case)
    manifest = overflow_manifest(fixture, case)
    if earlier == "job-cap":
        manifest["accounts"][-3]["limit_microusd"] = HALF + 1
    elif earlier == "project-cap":
        manifest["accounts"][1]["limit_microusd"] = HALF - 1
    watch, context = context_for(fixture)
    context.financial["scope"] = [
        row for row in context.financial["scope"] if row["resource_kind"] == "job"
    ]
    project_calls = []

    # This is explicitly the offline stand-in; real cases delegate the SQL gate.
    def project_delegate(connection, parsed, organization, work):
        project_calls.append((connection, parsed, organization, work))
        assert connection is watch.work._connection and work is watch.work

    monkeypatch.setattr(ledger_service, "_projects", project_delegate)
    if interrupt is not None:

        def check():
            raise interrupt

        watch.work.check = check
    recorded = []
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_overflow(watch, monkeypatch, lambda *args: recorded.append(args)) as observed,
        pytest.raises(type(interrupt) if interrupt is not None else MigrationRefused) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    (entry,), stages = observed
    assert len(project_calls) == 1 and len(recorded) == 1
    assert recorded[0][0] == "overflow_preparation"
    return fixture, manifest, case, entry, stages, failure.value, watch


@pytest.mark.parametrize("case", CASES)
def test_exact_setup_and_in_domain_manifest_separate_overflow_levels(case):
    fixture, before = changed_example(case)
    assert_setup_delta(before, fixture.before, fixture.project, case)
    manifest = overflow_manifest(fixture, case)
    parsed = validate_ledger_manifest(manifest)
    assert sum(row["reserved"] for row in fixture.jobs) == OVERFLOW > MAX_MONEY
    assert len(parsed.accounts) == (5 if case == "project" else 6)
    assert all(
        type(row.limit_microusd) is int and row.limit_microusd <= MAX_MONEY
        for row in parsed.accounts
    )
    projects = {row["project_id"] for row in fixture.jobs}
    totals = [
        sum(row["reserved"] for row in fixture.jobs if row["project_id"] == p) for p in projects
    ]
    assert totals == ([OVERFLOW] if case == "project" else [HALF, HALF])


@pytest.mark.parametrize(
    "change",
    ["result", "config", "operation", "artifact", "record-edge", "index-project", "scope-project"],
)
def test_move_candidate_rejects_connected_job_or_unsupported_topology(change):
    fixture = original_example()
    state = fixture.before
    if change == "result":
        replace_cell(state, "jobs", 2, "result", "e" * 64)
    elif change == "config":
        replace_cell(state, "jobs", 2, "execution_config_ref", "e" * 64)
    elif change in {"operation", "artifact"}:
        state["tables"]["operations" if change == "operation" else "artifact_refs"]["rows"].append(
            ("edge",)
        )
    elif change == "record-edge":
        replace_cell(
            state, "records", 1, "data", json.dumps({"job_id": JOBS[2], "parent_id": None})
        )
    elif change == "index-project":
        replace_cell(state, "run_index", 0, "project_id", identity(9000))
    else:
        replace_cell(state, "resource_scopes", 0, "project_id", identity(9000))
    with pytest.raises(AssertionError):
        assert_move_candidate(state, fixture.project)


@pytest.mark.parametrize(
    "change",
    [
        "other-budget",
        "float-zero",
        "job-state",
        "wrong-scope",
        "run-moved",
        "new-edge",
        "schema",
        "project-owner",
        "unrelated",
    ],
)
def test_full_setup_oracle_rejects_extra_or_inexact_changes(change):
    fixture, before = changed_example("organization")
    state = fixture.before
    if change == "other-budget":
        replace_cell(state, "jobs", 1, "budget", 1)
    elif change == "float-zero":
        replace_cell(state, "jobs", 1, "reserved", 0.0)
    elif change == "job-state":
        replace_cell(state, "jobs", 2, "status", "cancelled")
    elif change == "wrong-scope":
        replace_cell(state, "resource_scopes", 2, "project_id", fixture.project)
    elif change == "run-moved":
        replace_cell(state, "run_index", 0, "project_id", identity(9000))
    elif change == "new-edge":
        state["tables"]["operations"]["rows"].append(("operation",))
    elif change == "schema":
        state["schema"] = ("changed",)
    elif change == "project-owner":
        replace_cell(state, "projects", 0, "organization_id", identity(77))
    else:
        replace_cell(state, "unrelated", 0, "value", "changed")
    with pytest.raises(AssertionError):
        assert_setup_delta(before, state, fixture.project, "organization")


@pytest.mark.parametrize("case", CASES)
def test_original_reductions_refuse_at_distinct_callers_with_exact_values(case, monkeypatch):
    args = refused(monkeypatch, case)
    assert_overflow_refusal(*args)
    sites = sum_sites()
    assert sites["total"] == 193 and sites["organization_opening"] == 211 and sites["refusal"] == 88
    assert args[3]["error"]["identity"] == id(args[5])


@pytest.mark.parametrize("earlier", ["job-cap", "project-cap"])
def test_same_code_earlier_refusal_cannot_receive_overflow_credit(earlier, monkeypatch):
    args = refused(monkeypatch, "organization", earlier=earlier)
    assert args[5].code == "ledger_exposure_refused"
    assert args[3]["reduction_frames"][0]["line"] == (119 if earlier == "job-cap" else 202)
    with pytest.raises(AssertionError):
        assert_overflow_refusal(*args)


@pytest.mark.parametrize(
    "change",
    [
        "caller",
        "sum-site",
        "missing-project",
        "project-total",
        "project-values",
        "extra-sum",
        "float-value",
        "wrong-total",
        "imported",
        "project-opening",
        "exposure",
        "work",
        "raw",
        "error",
        "gate",
        "gate-order",
        "rollback",
        "commit",
        "cleanup-order",
    ],
)
def test_reduction_oracle_rejects_substitute_identity_order_or_operands(change, monkeypatch):
    fixture, manifest, case, entry, stages, error, watch = refused(monkeypatch, "organization")
    if change == "caller":
        entry["reduction_frames"][0]["line"] = 193
    elif change == "sum-site":
        entry["sums"][-1]["sum_frames"][0]["line"] -= 1
    elif change == "missing-project":
        entry["sums"].pop(-2)
    elif change == "project-total":
        entry["sums"][-2]["total"] = HALF - 1
    elif change == "project-values":
        entry["sums"][-2]["values"] = [HALF]
    elif change == "extra-sum":
        entry["sums"].append(deepcopy(entry["sums"][-1]))
    elif change == "float-value":
        entry["sums"][-1]["values"][1] = 0.0
    elif change == "wrong-total":
        entry["sums"][-1]["sum_frames"][0]["total"] -= 1
    elif change == "imported":
        entry["reduction_frames"][0]["imported"][2]["project_id"] = fixture.project
    elif change == "project-opening":
        entry["reduction_frames"][0]["projects"].pop()
    elif change == "exposure":
        entry["reduction_frames"][0]["exposure"].clear()
    elif change == "work":
        entry["sums"][-1]["work_id"] += 1
    elif change == "raw":
        entry["raw_id"] += 1
    elif change == "error":
        error = MigrationRefused("ledger_exposure_refused")
    elif change == "gate":
        stages.remove("projects.return")
    elif change == "gate-order":
        entry["project_gate"]["return"] = 1
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "commit":
        watch.outcome.commit_attempted = True
    else:
        watch.markers.reverse()
    with pytest.raises(AssertionError):
        assert_overflow_refusal(fixture, manifest, case, entry, stages, error, watch)


def test_first_baseexception_is_not_reclassified_as_overflow(monkeypatch):
    original = KeyboardInterrupt("overflow-control")
    args = refused(monkeypatch, "organization", interrupt=original)
    assert args[5] is original and args[3]["error"]["identity"] == id(original)
    assert args[3]["sums"] == []
    with pytest.raises(AssertionError):
        assert_overflow_refusal(*args)
