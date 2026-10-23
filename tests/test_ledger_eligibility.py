"""Actual SQLite admitted-queue initialization and isolated preparation eligibility."""

import json

import pytest
from ledger_eligibility_fixture import (
    CASES,
    admitted_predecessor,
    change_eligibility,
    cohort_manifest,
    file_hashes,
    refreshed,
    rows,
)
from ledger_eligibility_observer import (
    assert_eligibility_refusal,
    assert_preparation,
    observe_preparation,
)
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    ciphertexts,
    expected_opening,
    inspect,
    snapshot,
)
from ledger_recovery_fixture import observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.mark.parametrize("case", CASES)
def test_admitted_queue_initialization_eligibility(tmp_path, monkeypatch, record_property, case):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture, admission = admitted_predecessor(tmp_path / "eligibility.sqlite", monkeypatch)
    try:
        record("admission_association", admission.association)
        record("pre_admission_legacy_jobs", admission.original_legacy_jobs)
        record(
            "admission_adapter",
            {"original_compatibility": admission.compatibility, "scope": admission.adapter_scope},
        )
        record("admitted_ciphertexts", admission.ciphertexts)
        target_job = admission.accepted["job_id"]
        if case == "queued-v1":
            # A separate valid terminal-v1 precursor makes status the only
            # eligibility change; the genuinely admitted v2 association stays intact.
            (target_job,) = sorted(
                row["id"] for row in rows(fixture.before, "jobs") if row["payload_version"] == 1
            )[:1]
            with fixture.case.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE jobs SET reserved=0,owner=NULL,lease_until=NULL WHERE id=?",
                    (target_job,),
                )
            fixture = refreshed(fixture)
            terminal = next(row for row in rows(fixture.before, "jobs") if row["id"] == target_job)
            assert terminal["status"] in {"succeeded", "failed", "cancelled"}
            assert (
                terminal["payload_version"],
                terminal["reserved"],
                terminal["owner"],
                terminal["lease_until"],
            ) == (1, 0, None, None)
            record("valid_terminal_v1_precursor", terminal)
        valid_before = snapshot(fixture.case.path)
        observed = inspect(fixture)
        assert observed.status == "absent" and observed.revision == "ar_0006_admission"
        assert snapshot(fixture.case.path) == valid_before
        record("valid_predecessor_inspection", observed.model_dump(mode="json"))
        record("valid_predecessor", valid_before)
        if case != "admitted":
            fixture = change_eligibility(fixture, case, target_job)
        manifest = cohort_manifest(fixture)
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        record("manifest", manifest)
        record("original_legacy_ciphertexts", fixture.encrypted)
        caught = None
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_preparation(watch, monkeypatch, record) as (preparations, stages),
        ):
            if case == "admitted":
                receipt = ledger_service.initialize_ledger(
                    watch.engine, validate_ledger_manifest(manifest)
                )
            else:
                with pytest.raises(MigrationRefused) as failure:
                    ledger_service.initialize_ledger(
                        watch.engine, validate_ledger_manifest(manifest)
                    )
                caught = failure.value
        watch.assert_single_attempt()
        (entry,) = preparations
        assert_preparation(entry, fixture, manifest, watch)
        if case == "admitted":
            assert stages[:2] == ["prepare.enter", "prepare.return"]
            assert "upgrade" in stages
            assert watch.outcome.commit_acknowledged and not watch.outcome.cleanup_failed
            assert_stage(fixture, [manifest], [receipt])
            expected = expected_opening(fixture, manifest, receipt.initialized_at)
            assert entry["prepared"] == {
                "jobs": expected["jobs"],
                "project_totals": expected["project_totals"],
                "organization_opening": expected["organization_opening_microusd"],
            }
            imported = entry["prepared"]["jobs"]
            assert {row["job_id"] for row in imported} == {row["id"] for row in fixture.jobs}
            assert (
                next(row for row in imported if row["job_id"] == target_job)[
                    "legacy_reserved_microusd"
                ]
                == 0
            )
            assert receipt.imported_jobs == len(fixture.jobs)
            assert receipt.imported_opening_microusd == sum(row["reserved"] for row in fixture.jobs)
            record("receipt", receipt.model_dump(mode="json"))
            record("exact_after", snapshot(fixture.case.path))
        else:
            assert_eligibility_refusal(entry, stages, caught, watch, target_job=target_job)
            assert_no_writes(watch.actions)
            assert snapshot(fixture.case.path) == fixture.before
            record("exact_after", snapshot(fixture.case.path))
        assert ciphertexts(fixture.case) == admission.original_legacy_ciphertexts
        assert file_hashes(admission.objects) == admission.ciphertexts
        assert file_hashes(admission.journal) == admission.journal_hashes
    finally:
        fixture.close()
