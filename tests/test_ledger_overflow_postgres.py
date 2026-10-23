"""Opt-in PostgreSQL project and organization aggregate overflow refusals."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_money_postgres_observer import assert_native_preparation
from ledger_overflow_fixture import CASES, overflow_manifest
from ledger_overflow_observer import assert_overflow_refusal
from ledger_overflow_postgres_fixture import overflow_predecessor, raw_progress
from ledger_overflow_postgres_observer import observe_overflow
from ledger_provisioning_fixture import source_fingerprint
from ledger_provisioning_postgres_fixture import (
    build_postgres_case,
    encrypted_files,
    inspect,
    native_snapshot,
    progress_diagnostic,
    source_rows,
)
from ledger_recovery_postgres_fixture import observe_command
from ledger_restore_authority import typed
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL aggregate overflow"
)


@pytest.fixture
def legacy(pg, observed_reader):
    fixture = build_postgres_case(pg)
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.mark.parametrize("case", CASES)
def test_postgres_original_project_and_organization_sum_overflow(
    legacy, pg, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    record("original_legacy_predecessor", typed(legacy.before))
    record("original_legacy_source", legacy.original)
    record("original_legacy_fingerprint", legacy.source)
    record("original_ciphertexts", legacy.encrypted)
    fixture, progress = overflow_predecessor(legacy, pg, case, record)
    before = inspect(fixture, pg)
    assert before.status == "absent" and before.revision == "ar_0006_admission"
    assert typed(native_snapshot(fixture.case, pg)) == typed(fixture.before)
    record("valid_predecessor_inspection", before.model_dump(mode="json"))
    record("original_predecessor", typed(fixture.before))
    record("original_source_rows", fixture.original)
    record("original_source_fingerprint", fixture.source)
    manifest = overflow_manifest(fixture, case)
    record("manifest", manifest)
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
        observe_overflow(watch, monkeypatch, record) as (entries, stages),
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service.initialize_ledger(watch.engine, parsed)
    watch.assert_single_attempt()
    (entry,) = entries
    assert_native_preparation(entry, fixture, manifest, watch)
    assert_overflow_refusal(fixture, manifest, case, entry, stages, failure.value, watch)
    watch.assert_no_writes()
    after = native_snapshot(fixture.case, pg)
    record("exact_after", typed(after))
    assert typed(after) == typed(fixture.before)
    progress_after = raw_progress(fixture, pg)
    record("raw_progress_after_refusal", progress_after)
    assert typed(progress_after) == typed(progress)
    try:
        with fixture.case.engine.connect() as connection:
            original = source_rows(connection)
    finally:
        drain(pg)
    assert typed(original) == typed(fixture.original)
    assert source_fingerprint(original) == fixture.source
    protected = encrypted_files(fixture)
    record("ciphertexts_after", protected)
    assert protected == fixture.encrypted and len(protected) == 18
    record("refusal", {"code": failure.value.code, "source_digest_gate_reached": False})
