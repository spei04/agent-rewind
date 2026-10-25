"""Offline controls for native project provenance, handles, and typed witnesses."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import native_handle
from ledger_project_binding import assert_binding_refusal, binding_manifest, observe_projects
from ledger_project_binding_postgres_fixture import (
    assert_native_binding_manifest,
    assert_native_binding_refusal,
    assert_native_project_setup,
)
from ledger_provisioning_fixture import identity
from test_ledger_eligibility_postgres_controls import preparation_case

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def scenario():
    fixture, _, watch, context, target = preparation_case("admitted")
    other = identity(9000)
    original = {
        "id": fixture.project,
        "organization_id": fixture.organization,
        "name": "Original",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "run_sequence": 0,
    }
    added = {**original, "id": other, "name": "Independent project"}
    columns = tuple(original)
    fixture.before["tables"]["projects"] = {
        "columns": columns,
        "rows": (tuple(original[key] for key in columns),),
    }
    before = deepcopy(fixture.before)
    fixture.before["tables"]["projects"]["rows"] += (tuple(added[key] for key in columns),)
    setup = {"before": before, "after": deepcopy(fixture.before), "added_project": added}
    baseline, manifest = binding_manifest(fixture, target, other)
    watch.markers = [(name, raw, 10) for name, raw, _ in watch.markers]
    return fixture, baseline, manifest, target, other, watch, context, setup


def install_project_reader(monkeypatch, fixture, watch, fault=None):
    """Only the database result boundary is synthetic; the original gate executes."""
    calls = []
    original = ledger_service._projects
    receipts = [{"candidate_rows": 2, "invalid_rows": 0, "native_bytes": 128, "max_row_bytes": 64}]
    projects = [
        {"id": row["id"], "organization_id": row["organization_id"]}
        for row in rows(fixture.before, "projects")
    ]
    if fault == "receipt-bool":
        receipts[0]["invalid_rows"] = False
    elif fault == "receipt-count":
        receipts[0]["candidate_rows"] = 1
    elif fault == "missing-body":
        projects.pop()
    elif fault == "wrong-project":
        projects[-1]["id"] = identity(99)
    elif fault == "foreign-organization":
        projects[-1]["organization_id"] = identity(99)
    elif fault == "body-type":
        projects[-1]["organization_id"] = 1
    elif fault == "duplicate-body":
        projects[-1] = deepcopy(projects[0])
    interruption = KeyboardInterrupt("native-project-reader-control")

    @contextmanager
    def execute(connection, query, parameters):
        assert connection is watch.work._connection
        assert query in {"projects.gate", "projects.body"}
        assert set(parameters) == {f"project_{index:02d}" for index in range(16)}
        assert [parameters[f"project_{index:02d}"] for index in range(2)] == sorted(
            row["id"] for row in rows(fixture.before, "projects")
        )
        assert all(parameters[f"project_{index:02d}"] is None for index in range(2, 16))
        calls.append(query)
        watch.trace.events.append(("synthetic-project-reader", query))
        if fault == "interrupt":
            raise interruption
        values = receipts if query == "projects.gate" else projects
        yield SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: deepcopy(values)))

    monkeypatch.setattr(ledger_service, "_execute", execute)
    assert ledger_service._projects is original
    return calls, interruption


def delegated(monkeypatch):
    fixture, baseline, manifest, target, other, watch, context, setup = scenario()
    calls, _ = install_project_reader(monkeypatch, fixture, watch)
    records = []
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_projects(
            watch, monkeypatch, lambda *row: records.append(row), raw_handle=native_handle
        ) as gates,
        observe_cohort(
            watch, monkeypatch, lambda *row: records.append(row), raw_handle=native_handle
        ) as observed,
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    assert calls == ["projects.gate", "projects.body"]
    assert [row[0] for row in records] == ["cohort_preparation", "projects_gate"]
    assert not hasattr(watch.trace, "raws")
    (entry,), stages = observed
    return (
        fixture,
        baseline,
        manifest,
        target,
        other,
        watch,
        gates,
        entry,
        stages,
        failure.value,
        setup,
    )


def test_original_project_gate_then_preparation_rejects_present_job_scope(monkeypatch):
    fixture, baseline, manifest, target, other, watch, gates, entry, stages, error, setup = (
        delegated(monkeypatch)
    )
    assert_native_project_setup(setup, fixture.project, other)
    assert_native_binding_manifest(fixture, baseline, manifest, target, other)
    assert_native_binding_refusal(
        fixture, manifest, target, other, gates, entry, stages, error, watch
    )
    (frame,) = entry["traceback"]["preparation_frames"]
    assert frame["line"] == 117 and frame["job"]["id"] == target
    assert frame["scopes"][target] == fixture.project != frame["account"]["project_id"]
    assert gates[0]["returned"] is True
    assert gates[0]["return_trace_position"] <= entry["trace_position"]


@pytest.mark.parametrize(
    "fault",
    [
        "receipt-bool",
        "receipt-count",
        "missing-body",
        "wrong-project",
        "foreign-organization",
        "body-type",
        "duplicate-body",
        "interrupt",
    ],
)
def test_original_project_gate_refusal_or_interrupt_never_reaches_preparation(fault, monkeypatch):
    fixture, _, manifest, _, _, watch, context, _ = scenario()
    calls, interruption = install_project_reader(monkeypatch, fixture, watch, fault)
    parsed = validate_ledger_manifest(manifest)
    with (
        observe_projects(watch, monkeypatch, lambda *row: None, raw_handle=native_handle) as gates,
        observe_cohort(watch, monkeypatch, lambda *row: None, raw_handle=native_handle) as observed,
        pytest.raises(KeyboardInterrupt if fault == "interrupt" else MigrationRefused) as failure,
    ):
        ledger_service._projects(watch.work._connection, parsed, fixture.organization, watch.work)
        ledger_service._prepare_ledger(context, parsed, watch.work)
    assert observed == ([], [])
    assert gates[0]["error"]["identity"] == id(failure.value)
    assert "returned" not in gates[0]
    assert calls and calls[0] == "projects.gate"
    if fault == "interrupt":
        assert failure.value is interruption


@pytest.mark.parametrize(
    "fault", ["foreign-handle", "multiple-handles", "work", "engine", "connection"]
)
def test_project_observer_native_callback_rejects_foreign_identities(fault, monkeypatch):
    fixture, _, manifest, _, _, watch, _, _ = scenario()
    calls, _ = install_project_reader(monkeypatch, fixture, watch)
    work, connection = watch.work, watch.work._connection
    if fault == "foreign-handle":
        watch.trace.handles = [object()]
    elif fault == "multiple-handles":
        watch.trace.handles.append(object())
    elif fault == "work":
        work = SimpleNamespace(_raw=work._raw, _connection=connection)
    elif fault == "engine":
        connection.engine = object()
    else:
        connection = SimpleNamespace(engine=watch.engine)
    with (
        observe_projects(watch, monkeypatch, lambda *row: None, raw_handle=native_handle) as gates,
        pytest.raises((AssertionError, ValueError)),
    ):
        ledger_service._projects(
            connection, validate_ledger_manifest(manifest), fixture.organization, work
        )
    assert gates == [] and calls == []


@pytest.mark.parametrize(
    "fault",
    [
        "gate-manifest",
        "preparation-manifest",
        "financial-job",
        "rejected-jobs",
        "rejected-job",
        "rejected-account",
    ],
)
def test_native_binding_witness_rejects_equal_value_type_substitution(fault, monkeypatch):
    fixture, _, manifest, target, other, watch, gates, entry, stages, error, _ = delegated(
        monkeypatch
    )
    rejected = entry["traceback"]["preparation_frames"][0]
    if fault in {"gate-manifest", "preparation-manifest"}:
        account = (gates[0] if fault == "gate-manifest" else entry)["manifest"]["accounts"][0]
        account["limit_microusd"] = float(account["limit_microusd"])
    elif fault == "financial-job":
        entry["financial"]["job"][0]["cancel"] = int(entry["financial"]["job"][0]["cancel"])
    elif fault == "rejected-jobs":
        row = next(iter(rejected["jobs"].values()))
        row["cancel"] = int(row["cancel"])
    elif fault == "rejected-job":
        rejected["job"]["cancel"] = int(rejected["job"]["cancel"])
    else:
        rejected["account"]["limit_microusd"] = float(rejected["account"]["limit_microusd"])
    # The shared SQLite oracle accepts equal values; native types must also match.
    assert_binding_refusal(fixture, manifest, target, other, gates, entry, stages, error, watch)
    with pytest.raises(AssertionError):
        assert_native_binding_refusal(
            fixture, manifest, target, other, gates, entry, stages, error, watch
        )


@pytest.mark.parametrize("fault", ["added-sequence", "original-sequence", "job-bool", "role-type"])
def test_native_project_setup_rejects_equal_value_type_changes(fault):
    fixture, _, _, _, other, _, _, setup = scenario()
    after = setup["after"]
    if fault == "role-type":
        after["authority"]["functions"] = list(after["authority"]["functions"])
    elif fault == "job-bool":
        table = after["tables"]["jobs"]
        column = table["columns"].index("cancel")
        table["rows"] = tuple(
            tuple(int(value) if index == column else value for index, value in enumerate(row))
            for row in table["rows"]
        )
    else:
        table = after["tables"]["projects"]
        column = table["columns"].index("run_sequence")
        selected = 1 if fault == "added-sequence" else 0
        table["rows"] = tuple(
            tuple(
                False if index == column and row_index == selected else value
                for index, value in enumerate(row)
            )
            for row_index, row in enumerate(table["rows"])
        )
        if fault == "added-sequence":
            setup["added_project"]["run_sequence"] = False
    with pytest.raises(AssertionError):
        assert_native_project_setup(setup, fixture.project, other)


@pytest.mark.parametrize("fault", ["extra-opening", "target-absent", "collateral-project"])
def test_native_binding_manifest_rejects_incomplete_or_collateral_changes(fault):
    fixture, baseline, manifest, target, other, _, _, _ = scenario()
    if fault == "extra-opening":
        manifest["opening_accounts"]["projects"].append(
            deepcopy(manifest["opening_accounts"]["projects"][-1])
        )
    elif fault == "target-absent":
        fixture.before["tables"]["jobs"]["rows"] = tuple(
            row
            for row in fixture.before["tables"]["jobs"]["rows"]
            if row[fixture.before["tables"]["jobs"]["columns"].index("id")] != target
        )
    else:
        next(
            row for row in manifest["accounts"] if row["scope"] == "job" and row["job_id"] != target
        )["project_id"] = other
    with pytest.raises((AssertionError, KeyError, MigrationRefused)):
        assert_native_binding_manifest(fixture, baseline, manifest, target, other)
