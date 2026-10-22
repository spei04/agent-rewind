"""Independent small-state opening/provisioning, preservation and refusal controls."""

import sqlite3
from contextlib import closing

import pytest
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    digest,
    initial_manifest,
    inspect,
    invoke,
    native_actions,
    next_manifest,
    snapshot,
)

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.fixture
def legacy(tmp_path):
    fixture = build_case(tmp_path / "provisioning.sqlite")
    try:
        yield fixture
    finally:
        fixture.close()


def test_real_s0_m0_s1_m1_s2_and_older_replay_preserve_independent_oracles(legacy, monkeypatch):
    assert inspect(legacy).status == "absent"
    first = initial_manifest(legacy)
    original = invoke(legacy, first)
    assert_stage(legacy, [first], [original])
    s1 = snapshot(legacy.case.path)

    later = next_manifest(first)
    assert later["parent_manifest_digest"] == digest(first)
    second = invoke(legacy, later)
    assert_stage(legacy, [first, later], [original, second])
    s2 = snapshot(legacy.case.path)
    assert s2["schema"] == s1["schema"]
    for table, before in s1["tables"].items():
        if table not in {"budget_accounts", "migration_progress"}:
            assert s2["tables"][table] == before, table
    for table in ("budget_accounts", "migration_progress"):
        assert set(s1["tables"][table]["rows"]) <= set(s2["tables"][table]["rows"])
    assert len(s2["tables"]["budget_accounts"]["rows"]) == 7
    assert len(s2["tables"]["migration_progress"]["rows"]) == (
        len(s1["tables"]["migration_progress"]["rows"]) + 1
    )

    # Exact replay must not invoke new-intent source or provenance work. Native
    # authorizer observations also rule out same-value and zero-row DML.
    def forbidden(*args, **kwargs):
        pytest.fail("known replay entered new-intent work")

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "source_digest", forbidden)
        patch.setattr(ledger_service, "_provenance", forbidden)
        patch.setattr(ledger_service, "_prepare_ledger", forbidden)
        with native_actions(patch) as actions:
            engine = legacy.case.operator_engine()
            try:
                replay = ledger_service.initialize_ledger(engine, validate_ledger_manifest(first))
                assert engine.pool.checkedout() == 0
            finally:
                engine.dispose()
        assert replay == original
        assert_no_writes(actions)
    assert snapshot(legacy.case.path) == s2
    assert inspect(legacy).head.manifest_digest == second.manifest_digest


def test_real_empty_initialize_has_exact_zero_opening_and_persisted_provenance(tmp_path):
    fixture = build_case(tmp_path / "empty.sqlite", legacy=False)
    try:
        manifest = initial_manifest(fixture, empty=True)
        receipt = invoke(fixture, manifest)
        assert_stage(fixture, [manifest], [receipt])
        assert (receipt.account_rows, receipt.imported_jobs, receipt.imported_opening_microusd) == (
            0,
            0,
            0,
        )
    finally:
        fixture.close()


@pytest.mark.parametrize("scope", ["organization", "project"])
def test_initial_cap_244999_refuses_exact_native_245000_without_mutation(
    legacy, monkeypatch, scope
):
    manifest = initial_manifest(legacy)
    assert sum(row["reserved"] for row in legacy.jobs) == 245000
    assert inspect(legacy).status == "absent"
    target = next(row for row in manifest["accounts"] if row["scope"] == scope)
    target["limit_microusd"] = 244999
    validate_ledger_manifest(manifest)  # Parsing is valid; the database exposure must refuse.
    before = snapshot(legacy.case.path)
    with (
        native_actions(monkeypatch) as actions,
        pytest.raises(MigrationRefused, match="^ledger_exposure_refused$"),
    ):
        invoke(legacy, manifest)
    assert_no_writes(actions)
    assert snapshot(legacy.case.path) == before


@pytest.mark.parametrize("scope", ["organization", "project"])
def test_new_period_cap_244999_refuses_old_held_without_changing_s1(legacy, monkeypatch, scope):
    first = initial_manifest(legacy)
    original = invoke(legacy, first)
    assert_stage(legacy, [first], [original])
    later = next_manifest(first)
    target = next(row for row in later["accounts"] if row["scope"] == scope)
    target["limit_microusd"] = 244999
    validate_ledger_manifest(later)
    before = snapshot(legacy.case.path)
    with (
        native_actions(monkeypatch) as actions,
        pytest.raises(MigrationRefused, match="^ledger_exposure_refused$"),
    ):
        invoke(legacy, later)
    assert_no_writes(actions)
    assert snapshot(legacy.case.path) == before
    assert_stage(legacy, [first], [original])


@pytest.mark.parametrize("predicate", ["1", "0"])
def test_native_no_write_oracle_detects_same_value_and_zero_row_updates(
    tmp_path, monkeypatch, predicate
):
    path = tmp_path / "oracle.sqlite"
    with closing(sqlite3.connect(path)) as raw, raw:
        raw.execute("CREATE TABLE proof(value INTEGER)")
        raw.execute("INSERT INTO proof VALUES (1)")
    before = snapshot(path)
    with native_actions(monkeypatch) as actions, closing(sqlite3.connect(path)) as raw, raw:
        raw.execute("UPDATE proof SET value=value WHERE " + predicate)
    assert snapshot(path) == before
    with pytest.raises(AssertionError):
        assert_no_writes(actions)
