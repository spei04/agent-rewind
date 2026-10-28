"""Actual SQLite refusal for a present job assigned to another genuine project."""

import json

import pytest
from ledger_cohort_observer import observe_cohort
from ledger_eligibility_fixture import admitted_predecessor, file_hashes
from ledger_project_binding import (
    assert_binding_manifest,
    assert_binding_refusal,
    binding_manifest,
    observe_projects,
)
from ledger_provisioning_fixture import (
    assert_no_writes,
    ciphertexts,
    inspect,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import observe_command
from test_ledger_competing_distinct_sqlite import add_shared_project

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def test_initialization_refuses_present_job_in_other_real_project(
    tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture, admission = admitted_predecessor(tmp_path / "binding.sqlite", monkeypatch, record)
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
        record("original_legacy_ciphertexts", admission.original_legacy_ciphertexts)
        record("original_admitted_ciphertexts", admission.ciphertexts)
        record("original_journal", admission.journal_hashes)
        assert len(admission.original_legacy_ciphertexts) + len(admission.ciphertexts) == 21
        other, setup = add_shared_project(fixture)
        record("shared_project_setup", setup)
        assert source_rows(fixture.case.path) == fixture.original
        assert source_fingerprint(fixture.original) == fixture.source
        assert file_hashes(admission.objects) == admission.ciphertexts
        assert file_hashes(admission.journal) == admission.journal_hashes
        observed = inspect(fixture)
        assert observed.status == "absent" and observed.revision == "ar_0006_admission"
        assert snapshot(fixture.case.path) == fixture.before
        record("valid_predecessor_inspection", observed.model_dump(mode="json"))
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        target = admission.accepted["job_id"]
        baseline, manifest = binding_manifest(fixture, target, other)
        record("complete_manifest", baseline)
        record("manifest", manifest)
        record(
            "binding_delta",
            {
                "target_job": target,
                "actual_project": fixture.project,
                "requested_project": other,
                "scope": "job project plus supporting project account/opening",
            },
        )
        parsed = validate_ledger_manifest(manifest)
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_projects(watch, monkeypatch, record) as gates,
            observe_cohort(watch, monkeypatch, record) as (preparations, stages),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(watch.engine, parsed)
        watch.assert_single_attempt()
        (entry,) = preparations
        assert_binding_manifest(fixture, baseline, manifest, target, other)
        assert_binding_refusal(
            fixture, manifest, target, other, gates, entry, stages, failure.value, watch
        )
        assert_no_writes(watch.actions)
        after = snapshot(fixture.case.path)
        record("exact_after", after)
        assert after == fixture.before and source_rows(fixture.case.path) == fixture.original
        legacy, admitted, journal = (
            ciphertexts(fixture.case),
            file_hashes(admission.objects),
            file_hashes(admission.journal),
        )
        record("ciphertexts_after", {"legacy": legacy, "admitted": admitted})
        record("journal_after", journal)
        assert legacy == admission.original_legacy_ciphertexts
        assert admitted == admission.ciphertexts and journal == admission.journal_hashes
    finally:
        fixture.close()
