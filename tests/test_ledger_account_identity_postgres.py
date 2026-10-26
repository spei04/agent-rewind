"""Native finite first account and disjoint second-account refusal, explicitly opt-in."""

import json
from copy import deepcopy
from types import SimpleNamespace

import ledger_eligibility_postgres_fixture as admission_helpers
import pytest
import test_migrations_postgres as migration_tests
from ledger_account_identity_fixture import (
    assert_admission_delta,
    assert_second_refusal,
    assert_stores,
    job_intents,
)
from ledger_account_identity_postgres_fixture import expected_native_first
from ledger_accounted_carry_fixture import replace_rows
from ledger_accounted_carry_postgres_fixture import assert_raw_progress, native_time
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import assert_typed_initialization, native_handle
from ledger_overflow_postgres_fixture import raw_progress
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import expected_stage, initial_manifest, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    build_postgres_case,
    encrypted_files,
    inspect,
    native_snapshot,
    progress_diagnostic,
    source_rows,
)
from ledger_recovery_postgres_fixture import observe_command
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_physical_completion
from test_ledger_account_identity import synthetic_identity
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in native finite job account")
def test_postgres_first_finite_job_account_rejects_second_disjoint_account(
    pg, observed_reader, tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    fixture = build_postgres_case(pg)
    try:
        record("original_predecessor", typed(fixture.before))
        first = initial_manifest(fixture)
        record("M0_manifest", first)
        with observe_command(
            fixture, pg, monkeypatch, record_property, label="M0_service"
        ) as initial:
            first_receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_physical_completion(initial, "commit")
        stages = []
        assert_stage(
            fixture,
            pg,
            [first],
            [first_receipt],
            record_property=lambda name, value: stages.append(
                {"name": name, "value": json.loads(value)}
            ),
            observation="M0",
        )
        initialized = admission_helpers.refreshed(fixture, pg)
        assert_typed_initialization(fixture, pg, first, first_receipt, initialized.before)
        record("M0_stage", stages)
        record("M0_receipt", first_receipt.model_dump(mode="json"))
        record("M0_state", typed(initialized.before))
        evolved, admission = admission_helpers.admit_existing_fixture(
            initialized,
            pg,
            tmp_path,
            monkeypatch,
            lambda name, value: record("admission_" + name, value),
        )
        assert_admission_delta(initialized.before, evolved.before, admission, fixture.project)
        record("admission_association", typed(admission.association))
        record("admission_adapter", admission.adapter_scope)
        record("evolved_predecessor", typed(evolved.before))
        record("evolved_source", {"rows": typed(evolved.original), "fingerprint": evolved.source})
        record(
            "admission_stores",
            {
                "legacy": admission.original_legacy_ciphertexts,
                "objects": admission.ciphertexts,
                "journal": admission.journal_hashes,
            },
        )
        prior = inspect(evolved, pg).model_dump(mode="json")
        _, _, first_state = expected_stage(
            fixture, [first], [first_receipt], database_role=pg["owner_role"]
        )
        assert typed(prior) == typed(first_state)
        assert typed(native_snapshot(fixture.case, pg)) == typed(evolved.before)
        record("valid_evolved_inspection", prior)
        one, two = job_intents(evolved, first, admission.accepted["job_id"])
        record("M1_manifest", one)
        before_progress = raw_progress(evolved, pg)
        with (
            observe_command(
                evolved, pg, monkeypatch, record_property, label="M1_service"
            ) as provision,
            observe_cohort(
                provision,
                monkeypatch,
                lambda name, value: record("M1_" + name, value),
                raw_handle=native_handle,
            ) as (preparations, stages),
        ):
            written = ledger_service.initialize_ledger(
                provision.engine, validate_ledger_manifest(one)
            )
        assert_physical_completion(provision, "commit")
        assert stages == ["prepare.enter", "prepare.return"] and len(preparations) == 1
        assert typed(preparations[0]["state"]) == typed(prior)
        expected, state = expected_native_first(
            fixture, first, first_receipt, evolved.before, one, written, pg["owner_role"]
        )
        after = native_snapshot(fixture.case, pg)
        assert typed(after) == typed(expected)
        observed = inspect(evolved, pg).model_dump(mode="json")
        assert typed(observed) == typed(state)
        assert typed(native_snapshot(fixture.case, pg)) == typed(after)
        after_progress = raw_progress(evolved, pg)
        assert_raw_progress(
            before_progress, after_progress, "ledger_manifest_" + one["manifest_id"]
        )
        record("M1_receipt", written.model_dump(mode="json"))
        record("M1_expected", typed(expected))
        record("M1_state", typed(after))
        record("M1_whole_inspection", observed)
        record("M1_raw_progress", {"before": before_progress, "after": after_progress})
        record("M2_manifest", two)
        with (
            observe_command(
                evolved,
                pg,
                monkeypatch,
                record_property,
                label="M2_service",
                observe_writes=True,
            ) as refusal,
            observe_projects(refusal, monkeypatch, record, raw_handle=native_handle) as gates,
            observe_cohort(refusal, monkeypatch, record, raw_handle=native_handle) as (
                entries,
                stages,
            ),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(refusal.engine, validate_ledger_manifest(two))
        assert_second_refusal(one, two, state, gates, entries, stages, failure.value, refusal)
        refusal.assert_no_writes()
        assert_physical_completion(refusal, "rollback")
        assert typed(native_snapshot(fixture.case, pg)) == typed(after)
        try:
            with fixture.case.engine.connect() as connection:
                original = source_rows(connection)
            assert typed(original) == typed(evolved.original)
            assert source_fingerprint(original) == evolved.source
        finally:
            drain(pg)
        assert_stores(evolved, admission, encrypted_files(evolved))
        assert len({id(watch.work) for watch in (initial, provision, refusal)}) == 3
        assert len({id(watch.work._raw) for watch in (initial, provision, refusal)}) == 3
        record(
            "final_preservation",
            {
                "state": typed(native_snapshot(fixture.case, pg)),
                "source": typed(original),
                "source_fingerprint": evolved.source,
                "legacy": encrypted_files(evolved),
                "objects": admission.ciphertexts,
                "journal": admission.journal_hashes,
                "watched_services": 3,
                "receipt_replays": 0,
            },
        )
    finally:
        fixture.close()


def native_example():
    values = list(synthetic_identity())
    before = values[3]
    before.pop("schema")
    before.update(catalog={"synthetic": "catalog"}, authority={"synthetic": "owner"}, role="owner")
    accounts = rows(before, "budget_accounts")
    for row in accounts:
        row["period_start"] = native_time(row["period_start"])
        row["period_end"] = native_time(row["period_end"])
    replace_rows(before, "budget_accounts", accounts)
    progress = rows(before, "migration_progress")
    for row in progress:
        row["cursor"] = json.loads(row["cursor"])
        if row["phase"].startswith("ledger_manifest_"):
            row["cursor"]["database_role"] = "owner"
        row["updated_at"] = native_time(row["updated_at"])
    replace_rows(before, "migration_progress", progress)
    return values


class TestNativeAccountIdentityControls:
    def test_native_delta_retains_typed_history_and_adds_zero_account(self):
        frozen, first, initial, before, one, _, written, _ = native_example()
        original = deepcopy(before)
        expected, state = expected_native_first(
            frozen, first, initial, before, one, written, "owner"
        )
        (account,) = [row for row in rows(expected, "budget_accounts") if row["job_id"] == "3" * 32]
        assert typed(account["held_microusd"]) == typed(0)
        assert typed(account["period_start"]) == typed(native_time("2000-01-01T00:00:00.000000Z"))
        assert state["account_count"] == 4
        assert typed(before) == typed(original)
        previous = rows(before, "migration_progress")
        current = rows(expected, "migration_progress")
        assert len(current) == len(previous) + 1
        for row in previous:
            assert any(typed(row) == typed(candidate) for candidate in current)
        assert typed(expected["authority"]) == typed(before["authority"])

    @pytest.mark.parametrize("kind", ["old-money", "cursor-role", "cursor-type", "timestamp"])
    def test_native_delta_rejects_inconsistent_predecessor(self, kind):
        frozen, first, initial, before, one, _, written, _ = native_example()
        if kind == "old-money":
            accounts = rows(before, "budget_accounts")
            accounts[0]["accounted_microusd"] = False
            replace_rows(before, "budget_accounts", accounts)
        else:
            progress = rows(before, "migration_progress")
            row = next(row for row in progress if row["phase"].startswith("ledger_manifest_"))
            if kind == "cursor-role":
                row["cursor"]["database_role"] = "wrong-owner"
            elif kind == "cursor-type":
                row["cursor"]["account_count"] = 3.0
            else:
                row["updated_at"] = row["updated_at"].replace(tzinfo=None)
            replace_rows(before, "migration_progress", progress)
        with pytest.raises((AssertionError, ValueError)):
            expected_native_first(frozen, first, initial, before, one, written, "owner")

    def test_native_existing_fixture_failure_preserves_caller(self, monkeypatch):
        closed = []
        fixture = SimpleNamespace(
            close=lambda: closed.append(True), case=SimpleNamespace(engine=SimpleNamespace(url="x"))
        )
        failure = RuntimeError("synthetic engine creation failure")

        def unavailable(*_args, **_kwargs):
            raise failure

        monkeypatch.setattr(admission_helpers, "create_engine", unavailable)
        with pytest.raises(RuntimeError) as observed:
            admission_helpers.admit_existing_fixture(
                fixture, {}, None, monkeypatch, lambda *_: None
            )
        assert observed.value is failure and closed == []

    def test_native_builder_wrapper_keeps_cleanup_and_legacy_argument(self, monkeypatch):
        closed, calls = [], []
        fixture = SimpleNamespace(close=lambda: closed.append(True))

        def build(pg, *, legacy):
            calls.append((pg, legacy))
            return fixture

        failure = RuntimeError("synthetic publication failure")

        def unavailable(*_args):
            raise failure

        monkeypatch.setattr(admission_helpers, "build_postgres_case", build)
        monkeypatch.setattr(admission_helpers, "admit_existing_fixture", unavailable)
        with pytest.raises(RuntimeError) as observed:
            admission_helpers.admitted_predecessor(
                {"owner": "synthetic"}, None, monkeypatch, lambda *_: None, legacy=False
            )
        assert observed.value is failure and closed == [True]
        assert calls == [({"owner": "synthetic"}, False)]
