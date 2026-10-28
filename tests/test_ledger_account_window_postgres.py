"""Three original PostgreSQL window refusals; native execution is explicitly opt-in."""

import json
from contextlib import nullcontext

import ledger_eligibility_postgres_fixture as admission_helpers
import pytest
import test_migrations_postgres as migration_tests
from ledger_account_identity_fixture import assert_admission_delta, assert_stores
from ledger_account_window_fixture import (
    CASES,
    assert_expiry_source,
    assert_intent,
    assert_preservation,
    assert_refusal,
    equal,
    initial_window,
    window_intent,
)
from ledger_account_window_observer import identity, observe_window, observe_window_source
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import file_hashes
from ledger_eligibility_postgres_fixture import assert_typed_initialization, native_handle
from ledger_overflow_postgres_fixture import raw_progress
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import expected_stage, source_fingerprint
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
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in PostgreSQL account windows")
@pytest.mark.parametrize("case", CASES)
def test_postgres_account_window_refusal(
    pg, observed_reader, tmp_path, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    record("window_case", case)
    fixture = build_postgres_case(pg)
    try:
        record("original_predecessor", typed(fixture.before))
        first, legacy_job = initial_window(fixture, case)
        record("M0_manifest", first)
        with observe_command(
            fixture, pg, monkeypatch, record_property, label="M0_service"
        ) as initial:
            initial_receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_physical_completion(initial, "commit")
        equal(initial.work.timeout_seconds, 5)
        stages = []
        assert_stage(
            fixture,
            pg,
            [first],
            [initial_receipt],
            record_property=lambda name, value: stages.append(
                {"name": name, "value": json.loads(value)}
            ),
            observation="M0",
        )
        initialized = admission_helpers.refreshed(fixture, pg)
        assert_typed_initialization(fixture, pg, first, initial_receipt, initialized.before)
        record("M0_stage", stages)
        record("M0_receipt", initial_receipt.model_dump(mode="json"))
        record("M0_state", typed(initialized.before))
        admission_records = []
        evolved, admission = admission_helpers.admit_existing_fixture(
            initialized,
            pg,
            tmp_path,
            monkeypatch,
            lambda name, value: admission_records.append({"name": name, "value": value}),
        )
        assert_admission_delta(initialized.before, evolved.before, admission, fixture.project)
        assert len(evolved.before["tables"]) == 20
        assert len(admission.original_legacy_ciphertexts) == 18
        assert len(admission.ciphertexts) == 3 and len(admission.journal_hashes) == 15
        record("admission_setup", admission_records)
        record("admission_association", typed(admission.association))
        record("admission_adapter_scope", admission.adapter_scope)
        record("evolved_predecessor", typed(evolved.before))
        record("evolved_source", {"rows": typed(evolved.original), "fingerprint": evolved.source})
        stores = {
            "legacy": admission.original_legacy_ciphertexts,
            "objects": admission.ciphertexts,
            "journal": admission.journal_hashes,
        }
        record("admission_stores", stores)
        prior = inspect(evolved, pg).model_dump(mode="json")
        _, _, expected = expected_stage(
            fixture, [first], [initial_receipt], database_role=pg["owner_role"]
        )
        equal(prior, expected)
        equal(native_snapshot(fixture.case, pg), evolved.before)
        record("valid_evolved_inspection", prior)
        requested = window_intent(evolved, first, case, admission.accepted["job_id"], legacy_job)
        target = (
            None
            if case == CASES[0]
            else legacy_job
            if case == CASES[1]
            else admission.accepted["job_id"]
        )
        assert_intent(
            first, requested, evolved.before, case, target, initial_receipt.initialized_at
        )
        record("target_manifest", requested)
        before_progress = raw_progress(evolved, pg)
        with (
            observe_command(
                evolved,
                pg,
                monkeypatch,
                record_property,
                label="target_service",
                observe_writes=True,
            ) as watch,
            observe_projects(watch, monkeypatch, record, raw_handle=native_handle) as projects,
            observe_cohort(watch, monkeypatch, record, raw_handle=native_handle) as (
                entries,
                phases,
            ),
            observe_window(watch, monkeypatch, record) as observations,
            (
                observe_window_source(watch, monkeypatch, observations)
                if case == CASES[2]
                else nullcontext()
            ),
            pytest.raises(MigrationRefused) as refusal,
        ):
            ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(requested))
        assert_refusal(
            first,
            requested,
            prior,
            observations,
            projects,
            entries,
            phases,
            refusal.value,
            watch,
            case,
        )
        assert_physical_completion(watch, "rollback")
        if case != CASES[2]:
            watch.assert_no_writes()
        else:
            equal(watch.observer_units, [6, 3])
            (delta,) = watch.counters
            (relation,) = delta
            assert type(relation[0]) is int and relation[1:] == ("public", "budget_accounts")
            equal(delta[relation], (1, 0, 0))
            equal(observations["source_hashes"][0]["preparation"][0]["state"], prior)
            assert_expiry_source(
                observations,
                evolved.original,
                requested,
                watch.trace.events,
                watch.parameters.receipts,
                identity(watch),
            )
        assert initial.work is not watch.work and initial.work._raw is not watch.work._raw
        after = native_snapshot(fixture.case, pg)
        try:
            with fixture.case.engine.connect() as connection:
                source = source_rows(connection)
        finally:
            drain(pg)
        after_progress = raw_progress(evolved, pg)
        equal(before_progress, after_progress)
        assert_stores(evolved, admission, encrypted_files(evolved))
        stores_after = {
            "legacy": encrypted_files(evolved),
            "objects": file_hashes(admission.objects),
            "journal": file_hashes(admission.journal),
        }
        assert_preservation(evolved.before, after, evolved.original, source, stores, stores_after)
        assert source_fingerprint(source) == requested["source_digest"] == evolved.source
        record("raw_progress_preservation", {"before": before_progress, "after": after_progress})
        record(
            "target_refusal",
            {
                "case": case,
                "code": refusal.value.code,
                "post_insert_rollback": case == CASES[2],
                "watched_services": 2,
                "receipt_replays": 0,
            },
        )
        record(
            "final_preservation",
            {
                "state": typed(after),
                "source": typed(source),
                "source_fingerprint": evolved.source,
                **stores_after,
            },
        )
    finally:
        fixture.close()
