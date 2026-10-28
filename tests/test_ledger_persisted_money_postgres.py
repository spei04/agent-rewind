"""Actual PostgreSQL negative persisted BIGINT refused by the complete reader."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_persisted_money import (
    assert_financial_refusal,
    assert_money_delta,
    inspect_direct,
    observe_financial,
    reader_identity,
)
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
from ledger_source_boundary_postgres import assert_physical_completion
from sqlalchemy import text
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations.schema import ADMISSION, MigrationRefused, installed_profile

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native PostgreSQL persisted-money check"
)


def test_postgres_negative_reserved_refuses_at_complete_financial_gate(
    pg, observed_reader, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False, default=progress_diagnostic))

    fixture = build_postgres_case(pg)
    try:
        valid = inspect(fixture, pg)
        assert valid.model_dump(mode="json") == fixture.case.expected
        assert valid.status == "absent" and valid.revision == ADMISSION
        before = native_snapshot(fixture.case, pg)
        assert typed(before) == typed(fixture.before) and len(before["tables"]) == 17
        assert typed(before["catalog"]) == typed(installed_profile("postgresql", ADMISSION))
        record("valid_predecessor_inspection", valid.model_dump(mode="json"))
        record("valid_predecessor", typed(before))
        record("valid_source_rows", typed(fixture.original))
        record("valid_source_fingerprint", fixture.source)
        assert len(fixture.encrypted) == 18
        record("original_ciphertexts", fixture.encrypted)
        target = sorted(job["id"] for job in fixture.jobs)[0]
        try:
            with fixture.case.engine.begin() as connection:
                changed = connection.execute(
                    text("UPDATE jobs SET reserved=:value WHERE id=:id"),
                    {"value": -1, "id": target},
                )
                assert changed.rowcount == 1
            with fixture.case.engine.connect() as connection:
                value, storage = connection.execute(
                    text("SELECT reserved,pg_typeof(reserved)::text FROM jobs WHERE id=:id"),
                    {"id": target},
                ).one()
                original = source_rows(connection)
        finally:
            drain(pg)
        native = {"value": value, "storage": storage}
        corrupted = native_snapshot(fixture.case, pg)
        assert_money_delta(
            before, corrupted, fixture.original, original, target, "postgresql", native
        )
        record("stored_money", {"job_id": target, **native})
        record("corrupted_predecessor", typed(corrupted))
        record("corrupted_source_rows", typed(original))
        record("corrupted_source_fingerprint", source_fingerprint(original))
        with (
            observe_command(
                fixture,
                pg,
                monkeypatch,
                record_property,
                label="physical_reader",
                observe_writes=True,
            ) as watch,
            observe_financial(watch, monkeypatch, record) as receipt,
            pytest.raises(MigrationRefused) as failure,
        ):
            inspect_direct(watch, record)
        assert_financial_refusal(
            receipt, failure.value, reader_identity(watch, watch.work._connection, watch.work)
        )
        watch.assert_no_writes()
        assert_physical_completion(watch, "rollback")
        after = native_snapshot(fixture.case, pg)
        try:
            with fixture.case.engine.connect() as connection:
                after_source = source_rows(connection)
        finally:
            drain(pg)
        encrypted = encrypted_files(fixture)
        record("exact_after", typed(after))
        record("source_after", typed(after_source))
        record("ciphertexts_after", encrypted)
        assert typed(after) == typed(corrupted)
        assert typed(after_source) == typed(original)
        assert encrypted == fixture.encrypted
    finally:
        fixture.close()
