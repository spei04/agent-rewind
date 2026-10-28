"""Actual SQLite job-cap refusal and exact large-integer initialization."""

import json

import pytest
from ledger_eligibility_observer import assert_preparation
from ledger_money_fixture import (
    EXACT_AMOUNT,
    assert_cap_manifest,
    assert_exact_money,
    below_job_cap,
    exact_predecessor,
    money_manifest,
)
from ledger_money_observer import assert_job_cap_refusal, observe_money
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    inspect,
    reader,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.mark.parametrize("case", ["job-cap", "exact-integer"])
def test_original_job_cap_and_exact_integer_opening(tmp_path, monkeypatch, record_property, case):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "money.sqlite")
    try:
        record("original_legacy_predecessor", fixture.before)
        record("original_legacy_source", fixture.original)
        record("original_legacy_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        assert len(fixture.encrypted) == 18
        if case == "exact-integer":
            fixture, target = exact_predecessor(fixture, record)
            manifest = money_manifest(fixture)
        else:
            baseline, manifest, target = below_job_cap(fixture)
            record("complete_manifest", baseline)
        before = inspect(fixture)
        assert before.status == "absent" and before.revision == "ar_0006_admission"
        assert snapshot(fixture.case.path) == fixture.before
        record("valid_predecessor_inspection", before.model_dump(mode="json"))
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        record("manifest", manifest)
        record("target_job", target)
        parsed = validate_ledger_manifest(manifest)
        caught = None
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_money(watch, monkeypatch, record) as (records, stages),
        ):
            if case == "exact-integer":
                receipt = ledger_service.initialize_ledger(watch.engine, parsed)
            else:
                with pytest.raises(MigrationRefused) as error:
                    ledger_service.initialize_ledger(watch.engine, parsed)
                caught = error.value
        watch.assert_single_attempt()
        (entry,) = records
        assert_preparation(entry, fixture, manifest, watch)
        if case == "job-cap":
            assert_cap_manifest(fixture, baseline, manifest, target)
            assert_job_cap_refusal(fixture, manifest, target, entry, stages, caught, watch)
            assert_no_writes(watch.actions)
            after = snapshot(fixture.case.path)
            assert after == fixture.before
        else:
            assert stages == ["prepare.enter", "prepare.return"]
            assert watch.outcome.commit_acknowledged and not watch.outcome.cleanup_failed
            assert_stage(fixture, [manifest], [receipt])
            after = snapshot(fixture.case.path)
            inspected = inspect(fixture).model_dump(mode="json")
            assert_exact_money(fixture, manifest, entry["prepared"], receipt, after, inspected)
            with reader(fixture.case.path) as connection:
                types = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id,typeof(limit_microusd) AS limit_type,"
                        "typeof(opening_held_microusd) AS opening_type,"
                        "typeof(held_microusd) AS held_type,"
                        "typeof(accounted_microusd) AS accounted_type "
                        "FROM budget_accounts ORDER BY id"
                    )
                ]
            assert all(
                all(value == "integer" for key, value in row.items() if key != "id")
                for row in types
            )
            record("native_account_types", types)
            record("receipt", receipt.model_dump(mode="json"))
            record("fresh_inspection", inspected)
            record("economic_opening", {"exact_integer": EXACT_AMOUNT, "counted_once": True})
        record("exact_after", after)
        assert source_rows(fixture.case.path) == fixture.original
        assert source_fingerprint(source_rows(fixture.case.path)) == fixture.source
        actual_ciphertexts = ciphertexts(fixture.case)
        record("ciphertexts_after", actual_ciphertexts)
        assert actual_ciphertexts == fixture.encrypted
    finally:
        fixture.close()
