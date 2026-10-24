"""R2: a fresh provision intent reaches the original current-source refusal on S1."""

import json
from copy import deepcopy

import pytest
from ledger_accounted_carry_observer import assert_commit
from ledger_provisioning_fixture import (
    assert_stage,
    build_case,
    ciphertexts,
    initial_manifest,
    invoke,
    next_manifest,
    snapshot,
    source_fingerprint,
    source_rows,
)
from ledger_recovery_fixture import fresh_reentry, observe_command
from ledger_source_boundary import assert_new_intent, assert_refusal, observe_source

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def test_new_provision_wrong_current_source_preserves_s1(tmp_path, monkeypatch, record_property):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    fixture = build_case(tmp_path / "source-boundary.sqlite")
    try:
        first = initial_manifest(fixture)
        accepted = invoke(fixture, first)
        assert_stage(fixture, [first], [accepted])
        predecessor = snapshot(fixture.case.path)
        valid = next_manifest(first)
        changed = deepcopy(valid)
        changed["source_digest"] = "e" * 64
        assert_new_intent(first, valid, changed)
        validate_ledger_manifest(valid)
        manifest = validate_ledger_manifest(changed)
        assert len(fixture.encrypted) == 18
        record("initial_manifest", first)
        record("accepted_initialization", accepted.model_dump(mode="json"))
        record("original_predecessor", predecessor)
        record("original_source_rows", fixture.original)
        record("original_source_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        record("valid_intent", valid)
        record("manifest", changed)

        def preserved():
            after = snapshot(fixture.case.path)
            assert after == predecessor
            assert source_rows(fixture.case.path) == fixture.original
            assert source_fingerprint(source_rows(fixture.case.path)) == fixture.source
            assert ciphertexts(fixture.case) == fixture.encrypted
            return after

        with (
            observe_command(
                fixture, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_source(watch, monkeypatch, record) as receipt,
            pytest.raises(MigrationRefused) as raised,
        ):
            ledger_service.initialize_ledger(watch.engine, manifest)
        assert_refusal(receipt, changed, fixture.source, raised.value, watch)
        record("after_rollback", preserved())
        result, reentry = fresh_reentry(
            fixture, changed, monkeypatch, record_property, previous=watch
        )
        assert result is None
        assert_commit(reentry)
        record("fresh_reentry_result", None)
        record("final_preservation", preserved())
    finally:
        fixture.close()
