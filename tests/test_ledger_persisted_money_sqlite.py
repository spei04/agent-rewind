"""Actual SQLite fractional persisted money refused by the complete reader."""

import json

import pytest
from ledger_persisted_money import (
    assert_financial_refusal,
    assert_money_delta,
    dispose_sqlite_reader,
    inspect_direct,
    observe_financial,
    reader_identity,
)
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
from ledger_restore_authority import typed
from sqlalchemy import text

from agent_rewind.migrations.schema import ADMISSION, MigrationRefused, catalog, installed_profile


def test_sqlite_fractional_reserved_refuses_at_complete_financial_gate(
    tmp_path, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "persisted-money.sqlite")
    try:
        valid = inspect(fixture)
        assert valid.model_dump(mode="json") == fixture.case.expected
        assert valid.status == "absent" and valid.revision == ADMISSION
        before = snapshot(fixture.case.path)
        assert typed(before) == typed(fixture.before) and len(before["tables"]) == 17
        with fixture.case.engine.connect() as connection:
            shape = catalog(connection)
        assert shape == installed_profile("sqlite", ADMISSION)
        record("valid_predecessor_inspection", valid.model_dump(mode="json"))
        record("valid_catalog", typed(shape))
        record("valid_predecessor", typed(before))
        record("valid_source_rows", typed(fixture.original))
        record("valid_source_fingerprint", fixture.source)
        assert len(fixture.encrypted) == 18
        record("original_ciphertexts", fixture.encrypted)
        target = sorted(job["id"] for job in fixture.jobs)[0]
        with fixture.case.engine.begin() as connection:
            changed = connection.execute(
                text("UPDATE jobs SET reserved=:value WHERE id=:id"),
                {"value": 0.25, "id": target},
            )
            assert changed.rowcount == 1
        with fixture.case.engine.connect() as connection:
            value, storage = connection.execute(
                text("SELECT reserved,typeof(reserved) FROM jobs WHERE id=:id"), {"id": target}
            ).one()
        native = {"value": value, "storage": storage}
        corrupted = snapshot(fixture.case.path)
        original = source_rows(fixture.case.path)
        assert_money_delta(before, corrupted, fixture.original, original, target, "sqlite", native)
        record("stored_money", {"job_id": target, **native})
        record("corrupted_predecessor", typed(corrupted))
        record("corrupted_source_rows", typed(original))
        record("corrupted_source_fingerprint", source_fingerprint(original))
        with observe_command(
            fixture, monkeypatch, record_property, label="physical_reader"
        ) as watch:
            with (
                observe_financial(watch, monkeypatch, record) as receipt,
                pytest.raises(MigrationRefused) as failure,
            ):
                inspect_direct(watch, record)
            assert_financial_refusal(
                receipt, failure.value, reader_identity(watch, watch.work._connection, watch.work)
            )
            dispose_sqlite_reader(watch, record)
        watch.assert_single_attempt()
        assert_no_writes(watch.actions)
        assert watch.outcome.confirmed_precommit_rollback and not watch.outcome.cleanup_failed
        assert not watch.outcome.commit_attempted
        after = snapshot(fixture.case.path)
        after_source = source_rows(fixture.case.path)
        encrypted = ciphertexts(fixture.case)
        record("exact_after", typed(after))
        record("source_after", typed(after_source))
        record("ciphertexts_after", encrypted)
        assert typed(after) == typed(corrupted)
        assert typed(after_source) == typed(original)
        assert encrypted == fixture.encrypted
    finally:
        fixture.close()
