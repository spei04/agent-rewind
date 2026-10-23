"""One real SQLite carry path; synthetic settlement is separately preserved setup."""

import json

from ledger_accounted_carry_fixture import (
    assert_stores,
    fresh_admitted,
    future_carry_manifest,
    initial_carry_manifest,
    settle_fixture,
)
from ledger_accounted_carry_observer import (
    assert_carry,
    assert_commit,
    assert_receipt_reentry,
    expected_final,
    observe_carry,
)
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    inspect,
    native_actions,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import fresh_reentry, observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest


def test_accounted_only_carry_is_not_recharged(tmp_path, monkeypatch, record_property):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture, admission = fresh_admitted(tmp_path / "carry.sqlite", monkeypatch, record)
    try:
        first = initial_carry_manifest(fixture)
        record("original_predecessor", fixture.before)
        record("M0_manifest", first)
        record("M0_source_rows", fixture.original)
        record("M0_source_fingerprint", fixture.source)
        with observe_command(fixture, monkeypatch, record_property, label="M0_service") as initial:
            first_receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_commit(initial)
        assert_stage(fixture, [first], [first_receipt])
        initialized = snapshot(fixture.case.path)
        record("M0_receipt", first_receipt.model_dump(mode="json"))
        record("M0_state", initialized)
        assert_stores(admission)

        evolved, settlement = settle_fixture(fixture, admission, first, first_receipt, record)
        record("evolved_predecessor", evolved.before)
        record("M1_source_rows", evolved.original)
        record("M1_source_fingerprint", evolved.source)
        before_inspection = snapshot(fixture.case.path)
        with native_actions(monkeypatch) as inspection_actions:
            prior_state = inspect(evolved).model_dump(mode="json")
        assert_no_writes(inspection_actions)
        assert snapshot(fixture.case.path) == before_inspection == evolved.before
        record("evolved_whole_inspection", prior_state)
        record("evolved_inspection_authorizer", inspection_actions)
        second = future_carry_manifest(first, evolved.source)
        record("M1_manifest", second)
        with (
            observe_command(evolved, monkeypatch, record_property, label="M1_service") as provision,
            observe_carry(provision, monkeypatch, record) as (entries, sources),
        ):
            second_receipt = ledger_service.initialize_ledger(
                provision.engine, validate_ledger_manifest(second)
            )
        assert_commit(provision)
        (entry,) = entries
        assert_carry(entry, sources, evolved, first, second, prior_state, provision)
        expected, state = expected_final(
            fixture, first, first_receipt, evolved.before, second, second_receipt
        )
        after = snapshot(fixture.case.path)
        assert after == expected
        assert source_rows(fixture.case.path) == evolved.original
        assert source_fingerprint(source_rows(fixture.case.path)) == evolved.source
        with native_actions(monkeypatch) as inspection_actions:
            actual_state = inspect(evolved).model_dump(mode="json")
        assert_no_writes(inspection_actions)
        assert actual_state == state and snapshot(fixture.case.path) == after
        record("M1_receipt", second_receipt.model_dump(mode="json"))
        record("M1_state", after)
        record("M1_whole_inspection", actual_state)
        record("M1_inspection_authorizer", inspection_actions)

        previous = provision
        for name, manifest, written in (
            ("M0", first, first_receipt),
            ("M1", second, second_receipt),
        ):

            def record_reentry(key, value, *, label=name):
                record_property(label + "_" + key, value)

            result, watch = fresh_reentry(
                evolved, manifest, monkeypatch, record_reentry, previous=previous
            )
            assert_receipt_reentry(result, written)
            assert_commit(watch)
            record(name + "_reentered_receipt", result.model_dump(mode="json"))
            assert snapshot(fixture.case.path) == after
            previous = watch
        assert_stores(admission, settlement)
        record(
            "final_preservation",
            {
                "admission_objects": admission.object_hashes,
                "admission_journal": admission.journal_hashes,
                "settlement_objects": settlement.hashes,
                "source_fingerprint": evolved.source,
                "economic_settled_microusd": 1,
                "represented_account_levels": 3,
            },
        )
    finally:
        fixture.close()
