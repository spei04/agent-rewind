"""Native initialization refuses incomplete and nonexistent job-account cohorts."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_cohort_fixture import CASES, cohort_change
from ledger_cohort_observer import observe_cohort
from ledger_cohort_postgres_fixture import (
    assert_native_cohort_change,
    assert_native_cohort_refusal,
    assert_native_preparation,
)
from ledger_eligibility_fixture import file_hashes
from ledger_eligibility_postgres_fixture import admitted_predecessor, native_handle
from ledger_provisioning_fixture import source_fingerprint
from ledger_provisioning_postgres_fixture import (
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
from agent_rewind.migrations.schema import MigrationRefused, installed_profile

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL complete-cohort checks"
)


@pytest.mark.parametrize("case", CASES)
def test_postgres_initialization_requires_complete_existing_job_cohort(
    pg, observed_reader, tmp_path, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False, default=progress_diagnostic))

    fixture, admission = admitted_predecessor(pg, tmp_path, monkeypatch, record)
    try:
        record("admission_association", typed(admission.association))
        record("pre_admission_legacy_jobs", typed(admission.original_legacy_jobs))
        record(
            "admission_adapter",
            {
                "original_compatibility": admission.compatibility,
                "scope": admission.adapter_scope,
            },
        )
        record("original_admitted_ciphertexts", admission.ciphertexts)
        record("original_legacy_ciphertexts", admission.original_legacy_ciphertexts)
        record("original_journal", admission.journal_hashes)
        assert len(admission.original_legacy_ciphertexts) == 18
        assert len(admission.ciphertexts) == 3 and len(admission.journal_hashes) == 15
        assert len(fixture.before["tables"]) == 17
        assert typed(fixture.before["catalog"]) == typed(
            installed_profile("postgresql", "ar_0006_admission")
        )
        observed = inspect(fixture, pg)
        assert observed.status == "absent" and observed.revision == "ar_0006_admission"
        assert typed(native_snapshot(fixture.case, pg)) == typed(fixture.before)
        try:
            with fixture.case.engine.connect() as connection:
                original = source_rows(connection)
            assert typed(original) == typed(fixture.original)
            assert source_fingerprint(original) == fixture.source
        finally:
            drain(pg)
        record("valid_predecessor_inspection", observed.model_dump(mode="json"))
        record("original_predecessor", typed(fixture.before))
        record("original_source_rows", typed(fixture.original))
        record("original_source_fingerprint", fixture.source)
        baseline, manifest, target = cohort_change(fixture, admission.accepted["job_id"], case)
        assert_native_cohort_change(
            fixture, baseline, manifest, case, target, admission.accepted["job_id"]
        )
        record("complete_manifest", baseline)
        record("manifest", manifest)
        record("single_account_delta", {"case": case, "target_job": target})
        parsed = validate_ledger_manifest(manifest)
        with (
            observe_command(
                fixture,
                pg,
                monkeypatch,
                record_property,
                label="physical_service",
                observe_writes=True,
            ) as watch,
            observe_cohort(watch, monkeypatch, record, raw_handle=native_handle) as (
                preparations,
                stages,
            ),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(watch.engine, parsed)
        (entry,) = preparations
        assert_native_preparation(entry, fixture, manifest, watch)
        assert_native_cohort_change(
            fixture, baseline, manifest, case, target, admission.accepted["job_id"]
        )
        assert_native_cohort_refusal(
            entry, stages, failure.value, watch, case=case, target_job=target
        )
        watch.assert_no_writes()
        assert_physical_completion(watch, "rollback")
        after = native_snapshot(fixture.case, pg)
        record("exact_after", typed(after))
        assert typed(after) == typed(fixture.before)
        try:
            with fixture.case.engine.connect() as connection:
                original = source_rows(connection)
            record("source_after", typed(original))
            assert typed(original) == typed(fixture.original)
            assert source_fingerprint(original) == fixture.source
        finally:
            drain(pg)
        legacy_after = encrypted_files(fixture)
        admitted_after = file_hashes(admission.objects)
        journal_after = file_hashes(admission.journal)
        record("ciphertexts_after", {"legacy": legacy_after, "admitted": admitted_after})
        record("journal_after", journal_after)
        assert legacy_after == admission.original_legacy_ciphertexts
        assert admitted_after == admission.ciphertexts
        assert journal_after == admission.journal_hashes
    finally:
        fixture.close()
