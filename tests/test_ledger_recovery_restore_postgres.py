"""Two complete same-cluster restore positives; negative restore slices remain separate."""

import json
import os

import pytest
import test_migrations_postgres as migration_tests
from ledger_provisioning_fixture import initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import assert_stage, build_postgres_case, inspect, invoke
from ledger_recovery_postgres_fixture import fresh_reentry
from ledger_restore_authority import assert_ledger_authority, assert_same_authority
from ledger_restore_postgres_fixture import (
    TOOLS_ENV,
    assert_application_denials,
    capture,
    copy_ciphertexts,
    copy_hashes,
    empty_target,
    save,
    tool_configuration,
)
from ledger_restore_receipts import assert_original_receipt
from ledger_restore_tools import run_tool, tool_command, tool_environment
from ledger_service_fixture import invoke_postgres
from legacy_fixture import FIXTURE_ROOT
from sqlalchemy import create_engine
from test_ledger_provisioning_postgres import assert_no_writes, observe_no_writes
from test_ledger_service_postgres import controlled_database_name, observe_service
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.compatibility import (
    POOL_TIMEOUT_SECONDS,
    configure_runtime_engine,
    runtime_schema_compatibility,
)
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import LEDGER, installed_profile

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES or not os.environ.get(TOOLS_ENV),
    reason="Opt-in same-cluster owner-preserving ledger restore",
)


@pytest.fixture
def legacy(pg, observed_reader):
    fixture = build_postgres_case(pg)
    try:
        yield fixture
    finally:
        fixture.close()


def assert_migration_only(fixture, pg):
    engine = create_engine(
        fixture.case.engine.url, pool_size=1, max_overflow=0, pool_timeout=POOL_TIMEOUT_SECONDS
    )
    try:
        configure_runtime_engine(engine, production=True)
        verdict = runtime_schema_compatibility(engine)
        assert verdict.status == "incompatible" and verdict.code == "migration_only"
    finally:
        engine.dispose()
        drain(pg)


def replay_original(fixture, pg, manifest, original, monkeypatch, record_property):
    def forbidden(*args, **kwargs):
        raise AssertionError("restored known intent entered new-source work")

    with monkeypatch.context() as patch:
        for name in ("source_digest", "_provenance", "_prepare_ledger"):
            patch.setattr(ledger_service, name, forbidden)
        with observe_no_writes(patch, record_property) as (watch, counters, units):
            receipt = invoke_postgres(fixture.case, pg, validate_ledger_manifest(manifest))
            assert receipt == original
            record_property(
                "restore_replay_" + manifest["operation"],
                json.dumps(assert_no_writes(watch, counters, units, committed=True)),
            )
    recovered, _ = fresh_reentry(fixture, pg, manifest, monkeypatch, record_property)
    assert_original_receipt(recovered, original, record_property)


@pytest.mark.parametrize("stage", ["s0", "s2"])
def test_owner_preserving_full_restore(legacy, pg, tmp_path, monkeypatch, record_property, stage):
    directory = tmp_path / "restore-evidence"
    binary, socket, port, token = tool_configuration(pg, directory, record_property)
    manifests = [initial_manifest(legacy)]
    receipts = []
    if stage == "s2":
        manifests.append(next_manifest(manifests[0]))
        for index, manifest in enumerate(manifests):
            with observe_service(monkeypatch, record_property) as watch:
                receipts.append(invoke(legacy, pg, manifest))
                record_property(
                    "restore_setup_" + str(index), json.dumps(watch.verify(committed=[True]))
                )
        assert_stage(
            legacy,
            pg,
            manifests,
            receipts,
            record_property=record_property,
            observation="restore-source",
        )
    else:
        assert inspect(legacy, pg).status == "absent"
    before = capture(legacy, pg, directory, "source-before", record_property)
    assert before["authority"]["database"][0]["acl"] is None, "default database ACL scope only"
    expected_function = installed_profile("postgresql", LEDGER)["$postgres"]["ledger_executables"][
        "function"
    ]
    if stage == "s2":
        assert_ledger_authority(before["authority"], pg["owner_role"], expected_function)
    backup = directory / "backup-objects"
    backed_up = copy_ciphertexts(FIXTURE_ROOT / "objects", backup)
    assert backed_up == legacy.encrypted
    save(
        directory,
        "source-receipts",
        {
            "stage": stage,
            "manifests": manifests,
            "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            "ciphertexts": backed_up,
            "scope": (
                "same cluster; existing synthetic roles; default database ACL; no readiness claim"
            ),
        },
        record_property,
    )
    drain(pg)
    try:
        archive = run_tool(
            tool_command(binary / "pg_dump", "pg_dump", pg["owner"].url.database, socket, port),
            directory,
            label="dump",
            env=tool_environment(socket, "ar_restore_" + token + "_dump"),
            archive=True,
        )
        with empty_target(legacy, pg, directory, record_property) as (target, target_pg):
            run_tool(
                tool_command(
                    binary / "pg_restore",
                    "pg_restore",
                    target_pg["owner"].url.database,
                    socket,
                    port,
                    archive=archive,
                ),
                directory,
                label="restore",
                env=tool_environment(socket, "ar_restore_" + token + "_restore"),
            )
            drain(target_pg)
            restored_objects = directory / "restored-objects"
            assert copy_ciphertexts(backup, restored_objects) == backed_up
            restored = capture(target, target_pg, directory, "target-restored", record_property)
            assert restored["snapshot"] == before["snapshot"]
            assert restored["progress"] == before["progress"]
            assert_same_authority(before["authority"], restored["authority"])
            assert copy_hashes(restored_objects) == backed_up
            if stage == "s0":
                assert inspect(target, target_pg).status == "absent"
                with observe_service(monkeypatch, record_property) as watch:
                    target_receipts = [invoke(target, target_pg, manifests[0])]
                    record_property(
                        "restore_s0_initialize", json.dumps(watch.verify(committed=[True]))
                    )
            else:
                target_receipts = receipts
                assert_ledger_authority(
                    restored["authority"], target_pg["owner_role"], expected_function
                )
                assert_stage(
                    target,
                    target_pg,
                    manifests,
                    receipts,
                    record_property=record_property,
                    observation="restored",
                )
                for manifest, receipt in zip(manifests, receipts, strict=True):
                    replay_original(
                        target, target_pg, manifest, receipt, monkeypatch, record_property
                    )
                replayed = capture(target, target_pg, directory, "target-replayed", record_property)
                assert replayed == restored
            assert_stage(
                target,
                target_pg,
                manifests,
                target_receipts,
                record_property=record_property,
                observation="restore-final",
            )
            final = capture(target, target_pg, directory, "target-final", record_property)
            assert_ledger_authority(final["authority"], target_pg["owner_role"], expected_function)
            assert_application_denials(target, target_pg, directory, record_property)
            assert_migration_only(target, target_pg)
            assert copy_hashes(backup) == copy_hashes(restored_objects) == backed_up
    finally:
        after = capture(legacy, pg, directory, "source-after", record_property)
        assert after == before
        assert copy_hashes(FIXTURE_ROOT / "objects") == backed_up
        save(directory, "source-preservation", {"exact": True}, record_property)
