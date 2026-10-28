"""Actual SQLite initialization rejects incomplete or nonexistent job assignments."""

import json

import pytest
from ledger_cohort_fixture import CASES, assert_cohort_change, cohort_change
from ledger_cohort_observer import assert_cohort_refusal, observe_cohort
from ledger_eligibility_fixture import admitted_predecessor, file_hashes
from ledger_eligibility_observer import assert_preparation
from ledger_provisioning_fixture import (
    assert_no_writes,
    ciphertexts,
    inspect,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.mark.parametrize("case", CASES)
def test_initialization_requires_complete_existing_job_cohort(
    tmp_path, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture, admission = admitted_predecessor(tmp_path / "cohort.sqlite", monkeypatch, record)
    try:
        record("admission_association", admission.association)
        record("pre_admission_legacy_jobs", admission.original_legacy_jobs)
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
        assert len(admission.ciphertexts) + len(admission.original_legacy_ciphertexts) == 21
        observed = inspect(fixture)
        assert observed.status == "absent" and observed.revision == "ar_0006_admission"
        assert snapshot(fixture.case.path) == fixture.before
        assert source_rows(fixture.case.path) == fixture.original
        assert source_fingerprint(fixture.original) == fixture.source
        record("valid_predecessor_inspection", observed.model_dump(mode="json"))
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        baseline, manifest, target = cohort_change(fixture, admission.accepted["job_id"], case)
        record("complete_manifest", baseline)
        record("manifest", manifest)
        record("single_account_delta", {"case": case, "target_job": target})
        parsed = validate_ledger_manifest(manifest)
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_cohort(watch, monkeypatch, record) as (preparations, stages),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(watch.engine, parsed)
        watch.assert_single_attempt()
        (entry,) = preparations
        assert_preparation(entry, fixture, manifest, watch)
        assert_cohort_change(
            fixture, baseline, manifest, case, target, admission.accepted["job_id"]
        )
        assert_cohort_refusal(entry, stages, failure.value, watch, case=case, target_job=target)
        assert_no_writes(watch.actions)
        after = snapshot(fixture.case.path)
        record("exact_after", after)
        assert after == fixture.before
        assert source_rows(fixture.case.path) == fixture.original
        legacy_after = ciphertexts(fixture.case)
        admitted_after = file_hashes(admission.objects)
        journal_after = file_hashes(admission.journal)
        record("ciphertexts_after", {"legacy": legacy_after, "admitted": admitted_after})
        record("journal_after", journal_after)
        assert legacy_after == admission.original_legacy_ciphertexts
        assert admitted_after == admission.ciphertexts
        assert journal_after == admission.journal_hashes
    finally:
        fixture.close()
