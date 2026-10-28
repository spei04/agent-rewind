"""One same-cluster S2 restore followed by deletion of only ar7 opening provenance."""

import hashlib
import json

import pytest
from ledger_provisioning_fixture import initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import assert_stage
from ledger_recovery_postgres_fixture import observe_command
from ledger_restore_authority import assert_same_authority, typed
from ledger_restore_corrupt_observer import assert_refusal_cleanup
from ledger_restore_corrupt_raw import assert_restored_raw, capture_raw, source_columns
from ledger_restore_missing_opening import (
    assert_missing_opening_delta,
    delete_opening,
    observe_missing_opening,
)
from ledger_restore_postgres_fixture import (
    capture,
    copy_ciphertexts,
    copy_hashes,
    empty_target,
    save,
    tool_configuration,
)
from ledger_restore_tool_ownership import restore_tool_ownership
from ledger_restore_tools import run_tool, tool_command, tool_environment
from legacy_fixture import FIXTURE_ROOT
from test_ledger_recovery_restore_postgres import (
    controlled_database_name,
    legacy,
    observed_reader,
    pg,
    pytestmark,
)
from test_run_projection_postgres import drain

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = [
    "controlled_database_name",
    "legacy",
    "observed_reader",
    "pg",
    "pytestmark",
    "restore_tool_ownership",
]


def test_restored_s2_missing_opening_refuses_without_mutation(
    legacy, pg, tmp_path, monkeypatch, record_property, restore_tool_ownership
):
    directory = tmp_path / "missing-opening-restore-evidence"
    binary, socket, port, token = tool_configuration(pg, directory, record_property)
    manifests = [initial_manifest(legacy)]
    manifests.append(next_manifest(manifests[0]))
    receipts = []
    for label, manifest in zip(
        ("missing_M0_service", "missing_M1_service"), manifests, strict=True
    ):
        with observe_command(legacy, pg, monkeypatch, record_property, label=label) as watch:
            receipts.append(
                ledger_service.initialize_ledger(watch.engine, validate_ledger_manifest(manifest))
            )
        watch.assert_single_attempt()
        assert watch.outcome.commit_acknowledged and not watch.outcome.rollback_attempted
        assert not watch.outcome.cleanup_failed and watch.observer_units == []
    stage = []
    assert_stage(
        legacy,
        pg,
        manifests,
        receipts,
        record_property=lambda name, value: stage.append((name, json.loads(value))),
        observation="missing-source",
    )
    record_property("missing_source_stage", json.dumps(stage))
    before = capture(legacy, pg, directory, "source-valid", record_property)
    assert before["authority"]["database"][0]["acl"] is None
    source_raw = capture_raw(legacy, pg, directory, "source-before", record_property)
    columns = source_columns(source_raw["metadata"])
    backup = directory / "backup-objects"
    backed_up = copy_ciphertexts(FIXTURE_ROOT / "objects", backup)
    assert backed_up == legacy.encrypted
    save(
        directory,
        "source-receipts",
        {
            "manifests": manifests,
            "receipts": [r.model_dump(mode="json") for r in receipts],
            "source_digest": legacy.source,
            "ciphertexts": backed_up,
            "scope": "same cluster; genuine M0/M1; one opening-row deletion; no replay",
        },
        record_property,
    )
    drain(pg)
    archive = None
    try:
        archive = run_tool(
            tool_command(binary / "pg_dump", "pg_dump", pg["owner"].url.database, socket, port),
            directory,
            label="dump",
            archive=True,
            env=tool_environment(socket, "ar_restore_" + token + "_dump"),
        )
        archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        save(
            directory,
            "archive",
            {"bytes": archive.stat().st_size, "sha256": archive_hash},
            record_property,
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
            assert restore_tool_ownership.resolved() and len(restore_tool_ownership.children) == 4
            drain(target_pg)
            restored_objects = directory / "restored-objects"
            assert copy_ciphertexts(backup, restored_objects) == backed_up
            restored = capture(target, target_pg, directory, "target-valid", record_property)
            assert restored["snapshot"] == before["snapshot"]
            assert restored["progress"] == before["progress"]
            assert_same_authority(before["authority"], restored["authority"])
            stage = []
            assert_stage(
                target,
                target_pg,
                manifests,
                receipts,
                record_property=lambda name, value: stage.append((name, json.loads(value))),
                observation="missing-restored",
            )
            record_property("missing_restored_stage", json.dumps(stage))
            original = capture_raw(
                target, target_pg, directory, "target-before", record_property, columns=columns
            )
            assert_restored_raw(source_raw, original)
            mutation = delete_opening(target, target_pg, original)
            save(directory, "mutation", typed(mutation), record_property)
            corrupted = capture_raw(
                target, target_pg, directory, "target-corrupted", record_property, columns=columns
            )
            assert_missing_opening_delta(
                original,
                corrupted,
                mutation,
                target_pg["owner_role"],
                target_pg["owner"].url.database,
            )
            with (
                observe_command(
                    target,
                    target_pg,
                    monkeypatch,
                    record_property,
                    label="missing_target_service",
                    observe_writes=True,
                ) as watch,
                monkeypatch.context() as patch,
                observe_missing_opening(patch, watch) as stages,
                pytest.raises(MigrationRefused) as caught,
            ):
                stages.invoke(validate_ledger_manifest(manifests[1]))
            refusal = stages.verify(caught.value)
            assert_refusal_cleanup(watch)
            save(directory, "service-refusal", refusal, record_property)
            after = capture_raw(
                target, target_pg, directory, "target-after", record_property, columns=columns
            )
            assert typed(after) == typed(corrupted)
            assert copy_hashes(restored_objects) == backed_up
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
            save(
                directory,
                "target-preservation",
                {
                    "exact_corrupted_state": True,
                    "actual_service_code": caught.value.code,
                    "zero_service_writes": True,
                    "archive_unchanged": True,
                    "restored_ciphertexts": copy_hashes(restored_objects),
                },
                record_property,
            )
    finally:
        # The target cleanup runs first; all subsequent state captures are raw-only.
        after = capture_raw(legacy, pg, directory, "source-after", record_property, columns=columns)
        assert typed(after) == typed(source_raw)
        assert copy_hashes(FIXTURE_ROOT / "objects") == copy_hashes(backup) == backed_up
        if archive is not None:
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
        save(
            directory,
            "source-preservation",
            {"exact": True, "ciphertexts": backed_up},
            record_property,
        )
