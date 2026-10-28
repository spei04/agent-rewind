"""Two native early interruptions; no timeout or driver-failure simulation."""

import json

import pytest
import test_migrations_postgres as migration_tests
from ledger_precommit_boundary_fixture import STAGES
from ledger_precommit_boundary_postgres_fixture import assert_preserved
from ledger_precommit_boundary_postgres_observer import assert_boundary, observe_boundary
from ledger_provisioning_fixture import initial_manifest
from ledger_provisioning_postgres_fixture import build_postgres_case, progress_diagnostic
from ledger_recovery_postgres_fixture import fresh_reentry, observe_command
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_physical_completion
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in actual PostgreSQL early interruption"
)


@pytest.mark.parametrize("stage", STAGES)
def test_postgres_precommit_initialization_rolls_back(
    pg, observed_reader, monkeypatch, record_property, stage
):
    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False, default=progress_diagnostic))

    fixture = build_postgres_case(pg, legacy=True)
    try:
        manifest = initial_manifest(fixture)
        assert len(fixture.jobs) == 3 and len(fixture.encrypted) == 18
        record("original_predecessor", typed(fixture.before))
        record("original_source_rows", typed(fixture.original))
        record("original_source_fingerprint", fixture.source)
        record("original_ciphertexts", fixture.encrypted)
        record("native_jobs", typed(fixture.jobs))
        record("manifest", manifest)
        with (
            observe_command(
                fixture, pg, monkeypatch, record_property, label="physical_service"
            ) as watch,
            observe_boundary(watch, fixture, stage, monkeypatch, record) as (receipt, first),
            pytest.raises(MigrationRefused) as raised,
        ):
            ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(manifest))
        assert_boundary(receipt, fixture, manifest, first, raised.value, watch)
        record("after_rollback", assert_preserved(fixture, pg))
        recovered, reentry = fresh_reentry(
            fixture, pg, manifest, monkeypatch, record_property, previous=watch
        )
        assert recovered is None
        assert_physical_completion(reentry, "commit")
        record("fresh_reentry_result", None)
        record("final_preservation", assert_preserved(fixture, pg))
    finally:
        fixture.close()
