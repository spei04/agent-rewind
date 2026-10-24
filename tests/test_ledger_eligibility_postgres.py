"""Six native PostgreSQL I2 admission/eligibility counterparts."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_eligibility_fixture import CASES, cohort_manifest, file_hashes, rows
from ledger_eligibility_observer import (
    assert_eligibility_refusal,
    assert_preparation,
    observe_preparation,
)
from ledger_eligibility_postgres_fixture import (
    admitted_predecessor,
    assert_typed_initialization,
    change_eligibility,
    native_handle,
    terminal_precursor,
)
from ledger_provisioning_fixture import expected_opening, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
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
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL eligibility"
)


@pytest.mark.parametrize("case", CASES)
def test_postgres_admitted_queue_initialization_eligibility(
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
        record("admitted_ciphertexts", admission.ciphertexts)
        record("admission_journal", admission.journal_hashes)
        target_job = admission.accepted["job_id"]
        if case == "queued-v1":
            target_job = sorted(
                row["id"] for row in rows(fixture.before, "jobs") if row["payload_version"] == 1
            )[0]
            fixture = terminal_precursor(fixture, pg, target_job)
            record(
                "valid_terminal_v1_precursor",
                typed(next(row for row in rows(fixture.before, "jobs") if row["id"] == target_job)),
            )
        valid_before = typed(native_snapshot(fixture.case, pg))
        observed = inspect(fixture, pg)
        assert observed.status == "absent" and observed.revision == "ar_0006_admission"
        assert typed(native_snapshot(fixture.case, pg)) == valid_before
        record("valid_predecessor_inspection", observed.model_dump(mode="json"))
        record("valid_predecessor", valid_before)
        if case != "admitted":
            fixture = change_eligibility(fixture, pg, case, target_job)
        manifest = cohort_manifest(fixture)
        record("case", case)
        record("target_job", target_job)
        record("original_predecessor", typed(fixture.before))
        record("original_source_rows", typed(fixture.original))
        record("original_source_fingerprint", fixture.source)
        record("manifest", manifest)
        record("original_legacy_ciphertexts", fixture.encrypted)
        caught = None
        with (
            observe_command(
                fixture,
                pg,
                monkeypatch,
                record_property,
                label="physical_service",
                observe_writes=case != "admitted",
            ) as watch,
            observe_preparation(watch, monkeypatch, record, raw_handle=native_handle) as (
                preparations,
                stages,
            ),
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
        (entry,) = preparations
        assert_preparation(entry, fixture, manifest, watch)
        assert typed(sorted(entry["financial"]["job"], key=lambda row: row["id"])) == typed(
            sorted(rows(fixture.before, "jobs"), key=lambda row: row["id"])
        )
        if case == "admitted":
            assert stages[:2] == ["prepare.enter", "prepare.return"] and "upgrade" in stages
            assert_physical_completion(watch, "commit")
            assert_stage(
                fixture,
                pg,
                [manifest],
                [receipt],
                record_property=record_property,
                observation="admitted",
            )
            expected = expected_opening(fixture, manifest, receipt.initialized_at)
            assert entry["prepared"] == {
                "jobs": expected["jobs"],
                "project_totals": expected["project_totals"],
                "organization_opening": expected["organization_opening_microusd"],
            }
            assert len(fixture.jobs) == receipt.imported_jobs == 4
            assert receipt.account_rows == 6 and receipt.imported_opening_microusd == 245000
            assert (
                next(row for row in entry["prepared"]["jobs"] if row["job_id"] == target_job)[
                    "legacy_reserved_microusd"
                ]
                == 0
            )
            after = native_snapshot(fixture.case, pg)
            assert_typed_initialization(fixture, pg, manifest, receipt, after)
            record("receipt", receipt.model_dump(mode="json"))
        else:
            assert_eligibility_refusal(entry, stages, caught, watch, target_job=target_job)
            watch.assert_no_writes()
            assert_physical_completion(watch, "rollback")
            after = native_snapshot(fixture.case, pg)
            assert typed(after) == typed(fixture.before)
        record("exact_after", typed(after))
        try:
            with fixture.case.engine.connect() as connection:
                original = source_rows(connection)
            assert typed(original) == typed(fixture.original)
            assert source_fingerprint(original) == fixture.source
        finally:
            drain(pg)
        assert encrypted_files(fixture) == admission.original_legacy_ciphertexts
        assert file_hashes(admission.objects) == admission.ciphertexts
        assert file_hashes(admission.journal) == admission.journal_hashes
        record(
            "preserved_sources_and_files",
            {
                "source_fingerprint": fixture.source,
                "legacy_ciphertexts": fixture.encrypted,
                "admission_ciphertexts": admission.ciphertexts,
                "admission_journal": admission.journal_hashes,
            },
        )
    finally:
        fixture.close()
