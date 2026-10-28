"""Opt-in native accounted-only carry after genuine initialization and synthetic settlement."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_accounted_carry_fixture import (
    assert_stores,
    future_carry_manifest,
    initial_carry_manifest,
)
from ledger_accounted_carry_observer import observe_carry
from ledger_accounted_carry_postgres_fixture import (
    assert_raw_progress,
    expected_final,
    fresh_admitted,
    settle_fixture,
)
from ledger_accounted_carry_postgres_observer import assert_native_carry
from ledger_eligibility_postgres_fixture import assert_typed_initialization, native_handle
from ledger_overflow_postgres_fixture import raw_progress
from ledger_provisioning_fixture import expected_stage, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
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

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL accounted-only carry"
)


def test_postgres_accounted_only_carry_is_not_recharged(
    pg, observed_reader, tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    fixture, admission = fresh_admitted(pg, tmp_path, monkeypatch, record)
    try:
        record("original_predecessor", typed(fixture.before))
        record("original_source_rows", typed(fixture.original))
        record("original_source_fingerprint", fixture.source)
        absent = inspect(fixture, pg)
        assert absent.status == "absent" and absent.revision == "ar_0006_admission"
        assert typed(native_snapshot(fixture.case, pg)) == typed(fixture.before)
        record("valid_predecessor_inspection", absent.model_dump(mode="json"))
        first = initial_carry_manifest(fixture)
        record("M0_manifest", first)
        with observe_command(
            fixture, pg, monkeypatch, record_property, label="M0_service"
        ) as initial:
            first_receipt = ledger_service.initialize_ledger(
                initial.engine, validate_ledger_manifest(first)
            )
        assert_physical_completion(initial, "commit")
        stage = []
        assert_stage(
            fixture,
            pg,
            [first],
            [first_receipt],
            record_property=lambda name, value: stage.append(
                {"name": name, "value": json.loads(value)}
            ),
            observation="M0",
        )
        record("M0_stage", stage)
        before = native_snapshot(fixture.case, pg)
        assert_typed_initialization(fixture, pg, first, first_receipt, before)
        _, _, first_state = expected_stage(
            fixture, [first], [first_receipt], database_role=pg["owner_role"]
        )
        assert_stores(admission)
        record("M0_receipt", first_receipt.model_dump(mode="json"))
        record("M0_verified_state", first_state)
        record("M0_before_settlement", typed(before))

        evolved, settlement = settle_fixture(
            fixture, pg, admission, first, first_receipt, tmp_path / "settlement-objects", record
        )
        record("evolved_predecessor", typed(evolved.before))
        record("evolved_source_rows", typed(evolved.original))
        record("evolved_source_fingerprint", evolved.source)
        prior_state = inspect(evolved, pg).model_dump(mode="json")
        assert typed(prior_state) == typed(first_state)
        assert typed(native_snapshot(evolved.case, pg)) == typed(evolved.before)
        record("settled_inspection", prior_state)
        progress_before = raw_progress(evolved, pg)
        second = future_carry_manifest(first, evolved.source)
        record("M1_manifest", second)
        with (
            observe_command(
                evolved, pg, monkeypatch, record_property, label="M1_service"
            ) as provision,
            observe_carry(provision, monkeypatch, record, raw_handle=native_handle) as (
                entries,
                sources,
            ),
        ):
            second_receipt = ledger_service.initialize_ledger(
                provision.engine, validate_ledger_manifest(second)
            )
        assert_physical_completion(provision, "commit")
        assert initial.work is not provision.work
        assert initial.work._raw is not provision.work._raw
        assert initial.engine is not provision.engine
        (entry,) = entries
        assert_native_carry(entry, sources, evolved, first, second, prior_state, provision)
        expected, state = expected_final(
            fixture,
            first,
            first_receipt,
            evolved.before,
            second,
            second_receipt,
            pg["owner_role"],
        )
        after = native_snapshot(evolved.case, pg)
        assert typed(after) == typed(expected)
        inspection = inspect(evolved, pg).model_dump(mode="json")
        assert typed(inspection) == typed(state)
        assert typed(native_snapshot(evolved.case, pg)) == typed(expected)
        progress_after = raw_progress(evolved, pg)
        assert_raw_progress(
            progress_before, progress_after, "ledger_manifest_" + second["manifest_id"]
        )
        try:
            with fixture.case.engine.connect() as connection:
                original = source_rows(connection)
        finally:
            drain(pg)
        assert typed(original) == typed(evolved.original)
        assert source_fingerprint(original) == evolved.source
        assert_stores(admission, settlement)
        record("M1_receipt", second_receipt.model_dump(mode="json"))
        record("M1_expected", typed(expected))
        record("M1_after", typed(after))
        record("M1_inspection", inspection)
        record("M1_raw_progress", {"before": progress_before, "after": progress_after})
        record(
            "final_preservation",
            {
                "source_rows": typed(original),
                "source_fingerprint": evolved.source,
                "admission_objects": admission.object_hashes,
                "admission_journal": admission.journal_hashes,
                "settlement_objects": settlement.hashes,
                "economic_settled_microusd": 1,
                "represented_account_levels": 3,
                "watched_initializations": ["M0_service", "M1_service"],
                "fresh_receipt_replays": 0,
            },
        )
    finally:
        fixture.close()
