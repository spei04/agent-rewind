"""Offline controls for the present-job operand and supporting project manifest."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import rows
from ledger_project_binding import (
    PROJECT_ACCOUNT,
    assert_binding_manifest,
    assert_binding_refusal,
    binding_manifest,
    observe_projects,
)
from ledger_provisioning_fixture import identity
from test_ledger_eligibility_controls import example, table

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def scenario():
    fixture, accepted, _, _, _ = example()
    other = identity(9000)
    fixture.before["tables"]["projects"] = table(
        [
            {"id": fixture.project, "organization_id": fixture.organization, "name": "Original"},
            {"id": other, "organization_id": fixture.organization, "name": "Independent"},
        ]
    )
    target = accepted["job_id"]
    baseline, manifest = binding_manifest(fixture, target, other)
    raw, engine = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine), check=lambda: None)
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
            (name, id(raw), 1)
            for name in [
                "rollback.before_native",
                "rollback.native_ack",
                "connection.close.before",
                "connection.close.return",
                "command.exit",
            ]
        ],
    )
    context = SimpleNamespace(
        state=SimpleNamespace(
            manifest_count=0,
            account_count=0,
            model_dump=lambda **kwargs: {
                "status": "absent",
                "head": None,
                "revision": "ar_0006_admission",
            },
        ),
        history=SimpleNamespace(ownership=SimpleNamespace(organization_id=fixture.organization)),
        financial={
            "job": rows(fixture.before, "jobs"),
            "scope": rows(fixture.before, "resource_scopes"),
            "account": [],
        },
    )
    return fixture, baseline, manifest, target, other, watch, context


def delegated(monkeypatch):
    fixture, baseline, manifest, target, other, watch, context = scenario()
    calls, records = [], []

    def projects(connection, parsed, organization, work):
        calls.append((connection, parsed, organization, work))
        watch.trace.events.append(("offline-project-return",))

    monkeypatch.setattr(ledger_service, "_projects", projects)
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_projects(watch, monkeypatch, lambda *args: records.append(args)) as gates,
        observe_cohort(watch, monkeypatch, lambda *args: records.append(args)) as observed,
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    assert calls == [(watch.work._connection, parsed, fixture.organization, watch.work)]
    assert [item[0] for item in records] == ["cohort_preparation", "projects_gate"]
    (entry,), stages = observed
    return fixture, baseline, manifest, target, other, watch, gates, entry, stages, failure.value


def test_complete_manifest_delta_keeps_source_jobs_caps_and_original_identities():
    fixture, baseline, manifest, target, other, _, _ = scenario()
    original = deepcopy(fixture.before)
    old = {row["id"]: row for row in baseline["accounts"]}
    new = {row["id"]: row for row in manifest["accounts"]}
    assert set(new) - set(old) == {PROJECT_ACCOUNT}
    assert new[PROJECT_ACCOUNT]["limit_microusd"] == 0
    assert new[PROJECT_ACCOUNT]["project_id"] == other
    assert [row for row in baseline["accounts"] if row["scope"] != "job"] == [
        row for row in manifest["accounts"] if row["scope"] != "job" and row["id"] in old
    ]
    assert fixture.before == original
    assert rows(fixture.before, "resource_scopes")[-1]["resource_id"] == target


@pytest.mark.parametrize(
    "change",
    [
        "missing-project-account",
        "missing-opening",
        "wrong-new-cap",
        "original-cap",
        "fingerprint",
        "other-job",
        "nonexistent-project",
        "target-scope",
        "foreign-organization",
        "duplicate-id",
        "unsorted",
        "missing-job",
    ],
)
def test_manifest_oracle_rejects_missing_support_or_collateral_changes(change):
    fixture, baseline, manifest, target, other, _, _ = scenario()
    added = next(row for row in manifest["accounts"] if row["id"] == PROJECT_ACCOUNT)
    if change == "missing-project-account":
        manifest["accounts"].remove(added)
    elif change == "missing-opening":
        manifest["opening_accounts"]["projects"] = [
            row for row in manifest["opening_accounts"]["projects"] if row["project_id"] != other
        ]
    elif change == "wrong-new-cap":
        added["limit_microusd"] = 1
    elif change == "original-cap":
        manifest["accounts"][0]["limit_microusd"] += 1
    elif change == "fingerprint":
        manifest["source_digest"] = "0" * 64
    elif change == "other-job":
        next(
            row for row in manifest["accounts"] if row["scope"] == "job" and row["job_id"] != target
        )["limit_microusd"] -= 1
    elif change == "nonexistent-project":
        fixture.before["tables"]["projects"]["rows"].pop()
    elif change == "target-scope":
        scope = fixture.before["tables"]["resource_scopes"]
        row = list(scope["rows"][-1])
        row[scope["columns"].index("project_id")] = other
        scope["rows"][-1] = tuple(row)
    elif change == "foreign-organization":
        project = fixture.before["tables"]["projects"]
        row = list(project["rows"][-1])
        row[project["columns"].index("organization_id")] = identity(99)
        project["rows"][-1] = tuple(row)
    elif change == "duplicate-id":
        added["id"] = manifest["accounts"][0]["id"]
    elif change == "unsorted":
        manifest["accounts"].reverse()
    else:
        manifest["accounts"] = [row for row in manifest["accounts"] if row["job_id"] != target]
    with pytest.raises((AssertionError, MigrationRefused)):
        assert_binding_manifest(fixture, baseline, manifest, target, other)


def test_original_pure_preparation_distinguishes_present_job_from_absent_operand(monkeypatch):
    fixture, _, manifest, target, other, watch, gates, entry, stages, error = delegated(monkeypatch)
    assert_binding_refusal(fixture, manifest, target, other, gates, entry, stages, error, watch)
    (frame,) = entry["traceback"]["preparation_frames"]
    assert frame["line"] == 117
    assert frame["job"]["id"] == target
    assert frame["scopes"][target] == fixture.project
    assert frame["account"]["project_id"] == other


@pytest.mark.parametrize(
    "change",
    [
        "absent-job",
        "scope-map",
        "wrong-account",
        "wrong-exception",
        "wrong-site",
        "no-gate",
        "gate-refused",
        "gate-raw",
        "gate-connection",
        "gate-order",
        "duplicate-gate",
        "returned",
        "commit",
        "rollback",
        "cleanup-order",
        "missing-project",
    ],
)
def test_binding_oracle_rejects_wrong_operand_gate_identity_and_cleanup(change, monkeypatch):
    fixture, _, manifest, target, other, watch, gates, entry, stages, error = delegated(monkeypatch)
    frame = entry["traceback"]["preparation_frames"][0]
    if change == "absent-job":
        frame["job"] = None
    elif change == "scope-map":
        frame["scopes"][target] = other
    elif change == "wrong-account":
        frame["account"] = manifest["accounts"][0]
    elif change == "wrong-exception":
        error = MigrationRefused("ledger_history_unsupported")
    elif change == "wrong-site":
        frame["line"] = 149
    elif change == "no-gate":
        gates.clear()
    elif change == "gate-refused":
        gates[0]["error"] = {"type": "MigrationRefused"}
    elif change == "gate-raw":
        gates[0]["raw_id"] += 1
    elif change == "gate-connection":
        gates[0]["connection_id"] += 1
    elif change == "gate-order":
        gates[0]["return_trace_position"] = entry["trace_position"] + 1
    elif change == "duplicate-gate":
        gates.append(deepcopy(gates[0]))
    elif change == "returned":
        entry["returned"] = True
    elif change == "commit":
        watch.outcome.commit_attempted = True
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "cleanup-order":
        watch.markers.reverse()
    else:
        fixture.before["tables"]["projects"]["rows"].pop()
    with pytest.raises((AssertionError, ValueError)):
        assert_binding_refusal(fixture, manifest, target, other, gates, entry, stages, error, watch)


@pytest.mark.parametrize("kind", ["refusal", "interrupt"])
def test_original_project_gate_failure_is_recorded_and_never_reaches_preparation(kind, monkeypatch):
    fixture, _, manifest, _, _, watch, context = scenario()
    original = (
        MigrationRefused("ledger_history_unsupported")
        if kind == "refusal"
        else KeyboardInterrupt("project-gate-control")
    )
    calls, records = [], []

    def projects(*args):
        calls.append(args)
        raise original

    monkeypatch.setattr(ledger_service, "_projects", projects)
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_projects(watch, monkeypatch, lambda *args: records.append(args)) as gates,
        observe_cohort(watch, monkeypatch, lambda *args: records.append(args)) as observed,
        pytest.raises(type(original)) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    assert failure.value is original and len(calls) == 1
    assert observed == ([], [])
    assert gates[0]["error"]["identity"] == id(original)
    assert "returned" not in gates[0]
    assert [item[0] for item in records] == ["cohort_preparation", "projects_gate"]
