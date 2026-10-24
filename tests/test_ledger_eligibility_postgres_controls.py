"""Pure controls for PostgreSQL-specific predecessor and eligibility boundaries."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from ledger_eligibility_fixture import CASES, cohort_manifest, rows
from ledger_eligibility_observer import (
    assert_eligibility_refusal,
    assert_preparation,
    observe_preparation,
)
from ledger_eligibility_postgres_fixture import (
    assert_job_change,
    assert_native_jobs,
    assert_typed_initialization,
    native_handle,
    native_principal,
)
from ledger_provisioning_fixture import digest, expected_stage
from test_ledger_eligibility_controls import example, mapped_fixture

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, installed_profile


def replace_cell(state, table, index, field, value):
    selected = state["tables"][table]
    original = selected["rows"]
    rows_value = list(original)
    row = list(rows_value[index])
    row[selected["columns"].index(field)] = value
    rows_value[index] = tuple(row)
    selected["rows"] = tuple(rows_value) if type(original) is tuple else rows_value


def native_example(case="admitted"):
    fixture, accepted, principal, configuration, target = example(case)
    fixture.before.pop("schema")
    for table in fixture.before["tables"].values():
        table["rows"] = tuple(table["rows"])
    fixture.before.update(
        catalog={},
        authority={
            "schema": (("public", "owner", None),),
            "relations": (("jobs", "owner", None),),
            "functions": (("sample", "", "owner", None),),
        },
        role="owner",
    )
    for index, job in enumerate(rows(fixture.before, "jobs")):
        replace_cell(fixture.before, "jobs", index, "cancel", bool(job["cancel"]))
    return fixture, accepted, principal, configuration, target


@pytest.mark.parametrize("kind", ["valid", "integer", "false", "wrong-role", "wrong-project"])
def test_native_existing_principal_preserves_boolean_membership(kind):
    fixture, _ = mapped_fixture()
    replace_cell(fixture.before, "project_memberships", 0, "legacy_default", True)
    if kind == "integer":
        replace_cell(fixture.before, "project_memberships", 0, "legacy_default", 1)
    elif kind == "false":
        replace_cell(fixture.before, "project_memberships", 0, "legacy_default", False)
    elif kind == "wrong-role":
        replace_cell(fixture.before, "project_memberships", 0, "role", "operator")
    elif kind == "wrong-project":
        replace_cell(fixture.before, "project_memberships", 0, "project_id", "0" * 32)
    before = deepcopy(fixture.before)
    if kind == "valid":
        principal, binding = native_principal(fixture)
        assert principal.principal_id == binding["persisted_membership"]["principal_id"]
        assert binding["persisted_membership"]["legacy_default"] is True
    else:
        with pytest.raises(AssertionError):
            native_principal(fixture)
    assert fixture.before == before


@pytest.mark.parametrize(
    "field,value",
    [
        (None, None),
        ("created", 1700000000),
        ("lease_until", 1700000000),
        ("cancel", 0),
        ("budget", 50.0),
        ("reserved", False),
        ("payload_version", True),
    ],
)
def test_native_job_types_reject_equal_value_representations(field, value):
    fixture, *_ = native_example()
    if field is not None:
        replace_cell(fixture.before, "jobs", 0, field, value)
        with pytest.raises(AssertionError):
            assert_native_jobs(fixture.before)
    else:
        assert_native_jobs(fixture.before)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "catalog",
        "authority",
        "role",
        "other-table",
        "other-job-type",
        "target-type",
    ],
)
def test_native_single_cell_witness_preserves_whole_typed_predecessor(fault):
    fixture, accepted, *_ = native_example()
    before, after = fixture.before, deepcopy(fixture.before)
    target = accepted["job_id"]
    replace_cell(after, "jobs", 1, "status", "running")
    if fault == "catalog":
        after["catalog"]["unexpected"] = True
    elif fault == "authority":
        after["authority"]["schema"] = (("public", "other", None),)
    elif fault == "role":
        after["role"] = "other"
    elif fault == "other-table":
        after["tables"]["operations"]["rows"] = ()
    elif fault == "other-job-type":
        replace_cell(after, "jobs", 0, "cancel", 0)
    elif fault == "target-type":
        replace_cell(after, "jobs", 1, "reserved", False)
    if fault is None:
        assert_job_change(before, after, target, {"status": "running"})
    else:
        with pytest.raises(AssertionError):
            assert_job_change(before, after, target, {"status": "running"})


def preparation_case(case):
    fixture, _, _, _, target = native_example(case)
    manifest = cohort_manifest(fixture)
    engine, raw = object(), object()
    work = SimpleNamespace(_connection=SimpleNamespace(engine=engine), _raw=raw, check=lambda: None)
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(handles=[raw], events=[]),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True, commit_attempted=False, cleanup_failed=False
        ),
        markers=[
            (name, id(raw), 0)
            for name in (
                "rollback.before_native",
                "rollback.native_ack",
                "connection.close.before",
                "raw.close.before_native",
                "raw.close.native_ack",
                "connection.close.return",
                "raw.close.before_native",
                "raw.close.native_ack",
                "command.exit",
            )
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
    return fixture, manifest, watch, context, target


@pytest.mark.parametrize("case", CASES)
def test_native_handle_delegates_original_six_preparation_paths(monkeypatch, case):
    fixture, manifest, watch, context, target = preparation_case(case)
    records, caught = [], None
    with observe_preparation(
        watch, monkeypatch, lambda *row: records.append(row), raw_handle=native_handle
    ) as (entries, stages):
        try:
            ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
        except MigrationRefused as error:
            caught = error
    (entry,) = entries
    assert_preparation(entry, fixture, manifest, watch)
    assert len(records) == 1 and not hasattr(watch.trace, "raws")
    if case == "admitted":
        assert caught is None and stages == ["prepare.enter", "prepare.return"]
    else:
        assert_eligibility_refusal(entry, stages, caught, watch, target_job=target)


@pytest.mark.parametrize(
    "fault", ["foreign-handle", "multiple-handles", "foreign-work", "foreign-engine"]
)
def test_native_identity_callback_cannot_substitute_original_work(monkeypatch, fault):
    _, manifest, watch, context, _ = preparation_case("running")
    work = watch.work
    if fault == "foreign-handle":
        watch.trace.handles = [object()]
    elif fault == "multiple-handles":
        watch.trace.handles.append(object())
    elif fault == "foreign-work":
        work = SimpleNamespace(_raw=work._raw, _connection=work._connection)
    else:
        work._connection.engine = object()
    with (
        observe_preparation(watch, monkeypatch, lambda *row: None, raw_handle=native_handle),
        pytest.raises((AssertionError, ValueError)),
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), work)


def initialized_example():
    fixture, *_ = native_example()
    before = fixture.before
    before["tables"].update(
        {
            "migration_progress": {
                "columns": ("revision", "rows_verified"),
                "rows": (("ar_0006_admission", 1),),
            },
            "installation_adoptions": {
                "columns": ("installed_schema_fingerprint", "identity"),
                "rows": (("a" * 64, 1),),
            },
            "alembic_version": {"columns": ("version_num",), "rows": (("ar_0006_admission",),)},
        }
    )
    manifest = cohort_manifest(fixture)
    value = {
        "installation_key": manifest["installation_key"],
        "revision": LEDGER,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": digest(manifest),
        "sequence": 0,
        "operation": "initialize",
        "source_digest": fixture.source,
        "account_rows": len(manifest["accounts"]),
        "imported_jobs": len(fixture.jobs),
        "imported_opening_microusd": sum(row["reserved"] for row in fixture.jobs),
        "initialized_at": "2026-10-24T00:00:00Z",
        "outcome": "complete",
    }
    receipt = SimpleNamespace(
        initialized_at=value["initialized_at"], model_dump=lambda **kwargs: deepcopy(value)
    )
    accounts, _, _ = expected_stage(fixture, [manifest], [receipt], database_role="owner")
    accounts = [
        {
            **row,
            "period_start": datetime.fromisoformat(row["period_start"].replace("Z", "+00:00")),
            "period_end": datetime.fromisoformat(row["period_end"].replace("Z", "+00:00")),
        }
        for row in sorted(accounts, key=lambda row: row["id"])
    ]
    after = deepcopy(before)
    after["catalog"] = installed_profile("postgresql", LEDGER)
    columns = tuple(accounts[0])
    after["tables"]["budget_accounts"] = {
        "columns": columns,
        "rows": tuple(tuple(row[key] for key in columns) for row in accounts),
    }
    old_jobs = before["tables"]["jobs"]
    reserved = old_jobs["columns"].index("reserved")
    after["tables"]["jobs"] = {
        "columns": (*old_jobs["columns"], "lease_generation", "legacy_reserved_microusd"),
        "rows": tuple((*row, 0, row[reserved]) for row in old_jobs["rows"]),
    }
    after["tables"]["installation_adoptions"]["rows"] = (
        (digest(installed_profile("postgresql", LEDGER)), 1),
    )
    return fixture, manifest, receipt, after


@pytest.mark.parametrize(
    "fault", [None, "account-type", "old-job-type", "progress-type", "adoption-type", "authority"]
)
def test_success_oracle_keeps_native_types_across_allowed_schema_changes(fault):
    fixture, manifest, receipt, after = initialized_example()
    if fault == "account-type":
        replace_cell(after, "budget_accounts", 0, "held_microusd", 13.0)
    elif fault == "old-job-type":
        replace_cell(after, "jobs", 0, "cancel", 0)
    elif fault == "progress-type":
        replace_cell(after, "migration_progress", 0, "rows_verified", 1.0)
    elif fault == "adoption-type":
        replace_cell(after, "installation_adoptions", 0, "identity", True)
    elif fault == "authority":
        after["authority"]["relations"] = (("jobs", "other", None),)
    if fault is None:
        assert_typed_initialization(fixture, {"owner_role": "owner"}, manifest, receipt, after)
    else:
        with pytest.raises(AssertionError):
            assert_typed_initialization(fixture, {"owner_role": "owner"}, manifest, receipt, after)


def test_failed_admission_setup_disposes_pool_before_drain_and_keeps_original_error(
    monkeypatch, tmp_path
):
    import ledger_eligibility_postgres_fixture as adapter

    events = []
    fixture = SimpleNamespace(
        case=SimpleNamespace(engine=SimpleNamespace(url="postgresql://unused")),
        close=lambda: events.append("predecessor-disposed"),
    )
    engine = SimpleNamespace(dispose=lambda: events.append("admission-disposed"))
    original = KeyboardInterrupt("controlled setup failure")

    def refuse(_):
        raise original

    monkeypatch.setattr(adapter, "build_postgres_case", lambda pg: fixture)
    monkeypatch.setattr(adapter, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(adapter, "native_principal", refuse)
    monkeypatch.setattr(adapter, "drain", lambda pg: events.append("drain"))
    with pytest.raises(KeyboardInterrupt) as caught:
        adapter.admitted_predecessor({}, tmp_path, monkeypatch, lambda *row: None)
    assert caught.value is original
    assert events == ["predecessor-disposed", "admission-disposed", "drain"]
