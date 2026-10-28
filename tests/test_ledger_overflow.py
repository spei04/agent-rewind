"""Two actual SQLite overflow refusals with independently refreshed topology."""

import json

import pytest
from ledger_overflow_fixture import CASES, overflow_manifest, overflow_predecessor
from ledger_overflow_observer import assert_overflow_refusal, observe_overflow
from ledger_provisioning_fixture import (
    assert_no_writes,
    build_case,
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
def test_original_project_and_organization_sum_overflow(
    tmp_path, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "overflow.sqlite")
    try:
        record("original_legacy_predecessor", fixture.before)
        record("original_legacy_source", fixture.original)
        record("original_legacy_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        fixture = overflow_predecessor(fixture, case, record)
        before = inspect(fixture)
        record("valid_predecessor_inspection", before.model_dump(mode="json"))
        assert before.status == "absent" and before.revision == "ar_0006_admission"
        assert snapshot(fixture.case.path) == fixture.before
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        manifest = overflow_manifest(fixture, case)
        record("manifest", manifest)
        parsed = validate_ledger_manifest(manifest)
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_overflow(watch, monkeypatch, record) as (entries, stages),
            pytest.raises(MigrationRefused) as failure,
        ):
            ledger_service.initialize_ledger(watch.engine, parsed)
        watch.assert_single_attempt()
        (entry,) = entries
        assert_overflow_refusal(fixture, manifest, case, entry, stages, failure.value, watch)
        assert_no_writes(watch.actions)
        after = snapshot(fixture.case.path)
        record("exact_after", after)
        assert after == fixture.before
        assert source_rows(fixture.case.path) == fixture.original
        assert source_fingerprint(source_rows(fixture.case.path)) == fixture.source
        actual_ciphertexts = ciphertexts(fixture.case)
        record("ciphertexts_after", actual_ciphertexts)
        assert actual_ciphertexts == fixture.encrypted and len(actual_ciphertexts) == 18
        assert fixture.case.engine.pool.checkedout() == 0
    finally:
        fixture.close()
