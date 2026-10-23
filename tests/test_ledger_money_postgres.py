"""Opt-in native job-cap refusal and exact 2**53+1 initialization."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_money_fixture import below_job_cap, money_manifest
from ledger_money_observer import assert_job_cap_refusal
from ledger_money_postgres_fixture import (
    assert_exact_result,
    exact_predecessor,
    observe_inputs,
    observe_result,
)
from ledger_money_postgres_observer import assert_native_preparation, observe_money
from ledger_provisioning_fixture import source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
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
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL money boundaries"
)


@pytest.fixture
def legacy(pg, observed_reader):
    fixture = build_postgres_case(pg)
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.mark.parametrize("case", ["job-cap", "exact-integer"])
def test_postgres_original_job_cap_and_exact_integer(
    legacy, pg, monkeypatch, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    fixture = legacy
    record("original_legacy_predecessor", typed(fixture.before))
    record("original_legacy_source", fixture.original)
    record("original_legacy_fingerprint", fixture.source)
    record("original_ciphertexts", fixture.encrypted)
    if case == "exact-integer":
        fixture, target = exact_predecessor(fixture, pg, record)
        manifest = money_manifest(fixture)
    else:
        observed = observe_inputs(fixture, pg, record)
        assert typed(observed.before) == typed(fixture.before)
        assert typed(observed.original) == typed(fixture.original)
        assert typed(observed.jobs) == typed(fixture.jobs)
        assert observed.source == fixture.source
        baseline, manifest, target = below_job_cap(fixture)
        record("complete_manifest", baseline)
    before = inspect(fixture, pg)
    assert before.status == "absent" and before.revision == "ar_0006_admission"
    assert typed(native_snapshot(fixture.case, pg)) == typed(fixture.before)
    record("valid_predecessor_inspection", before.model_dump(mode="json"))
    record("original_predecessor", typed(fixture.before))
    record("original_source_rows", fixture.original)
    record("original_source_fingerprint", fixture.source)
    record("manifest", manifest)
    record("target_job", target)
    parsed = validate_ledger_manifest(manifest)
    caught = None
    with (
        observe_command(
            fixture,
            pg,
            monkeypatch,
            record_property,
            label="physical_service",
            observe_writes=case == "job-cap",
        ) as watch,
        observe_money(watch, monkeypatch, record) as (entries, stages),
    ):
        if case == "job-cap":
            with pytest.raises(MigrationRefused) as failure:
                ledger_service.initialize_ledger(watch.engine, parsed)
            caught = failure.value
        else:
            receipt = ledger_service.initialize_ledger(watch.engine, parsed)
    watch.assert_single_attempt()
    (entry,) = entries
    assert_native_preparation(entry, fixture, manifest, watch)
    if case == "job-cap":
        assert_job_cap_refusal(fixture, manifest, target, entry, stages, caught, watch)
        watch.assert_no_writes()
        after = native_snapshot(fixture.case, pg)
        assert typed(after) == typed(fixture.before)
        record("refusal", {"code": caught.code, "source_digest_gate_reached": False})
    else:
        assert stages == ["prepare.enter", "prepare.return"]
        assert watch.outcome.commit_acknowledged and not watch.outcome.cleanup_failed
        assert_stage(
            fixture,
            pg,
            [manifest],
            [receipt],
            record_property=record_property,
            observation="exact_integer",
        )
        after = native_snapshot(fixture.case, pg)
        inspection = inspect(fixture, pg).model_dump(mode="json")
        account_types, progress_text = observe_result(fixture, pg)
        record("native_account_types", account_types)
        record("native_progress_text", progress_text)
        record("receipt", receipt.model_dump(mode="json"))
        record("fresh_inspection", inspection)
        assert_exact_result(
            fixture,
            manifest,
            entry["prepared"],
            receipt,
            after,
            inspection,
            account_types,
            progress_text,
            pg["owner_role"],
        )
    record("exact_after", typed(after))
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
