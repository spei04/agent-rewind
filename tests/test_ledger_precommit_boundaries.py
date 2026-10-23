"""Actual SQLite DDL/first-backfill interruption; no genuine timeout claim."""

import json

import pytest
from ledger_accounted_carry_observer import assert_commit
from ledger_precommit_boundary_fixture import STAGES, assert_preserved
from ledger_precommit_boundary_observer import assert_boundary, observe_boundary
from ledger_provisioning_fixture import build_case, initial_manifest
from ledger_recovery_fixture import fresh_reentry, observe_command

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


@pytest.mark.parametrize("stage", STAGES)
def test_sqlite_precommit_initialization_rolls_back(tmp_path, monkeypatch, record_property, stage):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "precommit.sqlite")
    try:
        manifest = initial_manifest(fixture)
        assert len(fixture.jobs) == 3 and fixture.jobs[0]["reserved"] == 125000
        assert len(fixture.encrypted) == 18
        record("original_predecessor", fixture.before)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        record("manifest", manifest)
        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_boundary(watch, fixture, stage, monkeypatch, record) as (receipt, first),
            pytest.raises(MigrationRefused) as raised,
        ):
            ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(manifest))
        assert_boundary(receipt, fixture, manifest, first, raised.value, watch)
        record("after_rollback", assert_preserved(fixture))
        recovered, reentry = fresh_reentry(
            fixture, manifest, monkeypatch, record_property, previous=watch
        )
        assert recovered is None
        assert_commit(reentry)
        record("fresh_reentry_result", None)
        record("final_preservation", assert_preserved(fixture))
    finally:
        fixture.close()
