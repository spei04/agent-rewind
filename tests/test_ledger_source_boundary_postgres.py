"""R2: native PostgreSQL refuses only the changed source on a genuine S1."""

import json
from copy import deepcopy

import pytest
import test_migrations_postgres as migration_tests
from ledger_provisioning_fixture import initial_manifest, next_manifest, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    build_postgres_case,
    encrypted_files,
    invoke,
    native_snapshot,
    progress_diagnostic,
    source_rows,
)
from ledger_recovery_postgres_fixture import fresh_reentry, observe_command
from ledger_restore_authority import typed
from ledger_source_boundary import assert_new_intent
from ledger_source_boundary_postgres import (
    assert_physical_completion,
    assert_refusal,
    observe_native_source,
)
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in actual PostgreSQL source boundary"
)


def test_postgres_new_provision_wrong_current_source_preserves_s1(
    pg, observed_reader, monkeypatch, record_property
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False, default=progress_diagnostic))

    fixture = build_postgres_case(pg)
    try:
        first = initial_manifest(fixture)
        accepted = invoke(fixture, pg, first)
        assert_stage(
            fixture, pg, [first], [accepted], record_property=record_property, observation="setup"
        )
        predecessor = typed(native_snapshot(fixture.case, pg))
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
        record("original_source_rows", typed(fixture.original))
        record("original_source_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        record("valid_intent", valid)
        record("manifest", changed)

        def preserved():
            after = typed(native_snapshot(fixture.case, pg))
            assert after == predecessor
            try:
                with fixture.case.engine.connect() as connection:
                    original = source_rows(connection)
                assert typed(original) == typed(fixture.original)
                assert source_fingerprint(original) == fixture.source
                assert encrypted_files(fixture) == fixture.encrypted
            finally:
                drain(pg)
            return after

        with (
            observe_command(
                fixture,
                pg,
                monkeypatch,
                record_property,
                label="physical_service",
                observe_writes=True,
            ) as watch,
            observe_native_source(watch, monkeypatch, record) as (receipt, calls),
            pytest.raises(MigrationRefused) as raised,
        ):
            ledger_service.initialize_ledger(watch.engine, manifest)
        assert_refusal(
            receipt, fixture.original, changed, fixture.source, raised.value, calls, watch
        )
        record("after_rollback", preserved())
        result, reentry = fresh_reentry(
            fixture, pg, changed, monkeypatch, record_property, previous=watch
        )
        assert result is None
        assert_physical_completion(reentry, "commit")
        record("fresh_reentry_result", None)
        record("final_preservation", preserved())
    finally:
        fixture.close()
