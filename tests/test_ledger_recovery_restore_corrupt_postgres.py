"""Two independent full restores followed by one explicit target corruption each."""

import json

import pytest
from ledger_provisioning_fixture import initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import assert_stage, invoke
from ledger_recovery_postgres_fixture import observe_command
from ledger_restore_authority import assert_same_authority, typed
from ledger_restore_corrupt_observer import assert_refusal_cleanup, observe_corruption
from ledger_restore_corrupt_raw import (
    assert_acl_delta,
    assert_cursor_delta,
    assert_restored_raw,
    capture_raw,
    historical_row,
    mutate_target,
    source_columns,
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
from test_ledger_service_postgres import observe_service
from test_run_projection_postgres import drain

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


def invoke_refused_service(stages, manifest):
    # Only this actual service invocation may satisfy the expected refusal.
    with pytest.raises(MigrationRefused) as caught:
        stages.invoke(manifest)
    return caught.value


@pytest.mark.parametrize("kind", ["cursor", "acl"])
def test_restored_corruption_reaches_service_refusal(
    legacy, pg, tmp_path, monkeypatch, record_property, restore_tool_ownership, kind
):
    directory = tmp_path / "corrupt-restore-evidence"
    binary, socket, port, token = tool_configuration(pg, directory, record_property)
    manifests = [initial_manifest(legacy)]
    manifests.append(next_manifest(manifests[0]))
    receipts = []
    for index, manifest in enumerate(manifests):
        with observe_service(monkeypatch, record_property) as watch:
            receipts.append(invoke(legacy, pg, manifest))
            record_property(
                "corrupt_setup_" + str(index), json.dumps(watch.verify(committed=[True]))
            )
    assert_stage(
        legacy, pg, manifests, receipts, record_property=record_property, observation="source"
    )
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
            "kind": kind,
            "manifests": manifests,
            "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            "ciphertexts": backed_up,
            "scope": (
                "same cluster; existing roles/default database ACL; explicit target corruption"
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
            archive=True,
            env=tool_environment(socket, "ar_restore_" + token + "_dump"),
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
            assert_stage(
                target,
                target_pg,
                manifests,
                receipts,
                record_property=record_property,
                observation="restored-valid",
            )
            original = capture_raw(
                target, target_pg, directory, "target-before", record_property, columns=columns
            )
            assert_restored_raw(source_raw, original)
            phase = "ledger_manifest_" + manifests[1]["manifest_id"]
            mutation = mutate_target(target, target_pg, original, kind, phase)
            save(directory, "mutation", mutation, record_property)
            corrupted = capture_raw(
                target, target_pg, directory, "target-corrupted", record_property, columns=columns
            )
            if kind == "cursor":
                assert_cursor_delta(
                    original,
                    corrupted,
                    phase,
                    mutation["payload"],
                    mutation["returned_cursor_text"],
                )
            else:
                assert_acl_delta(original, corrupted, target_pg["owner_role"])
            checked = validate_ledger_manifest(manifests[1])
            with (
                observe_command(
                    target,
                    target_pg,
                    monkeypatch,
                    record_property,
                    label="corrupt_service",
                    observe_writes=True,
                ) as watch,
                monkeypatch.context() as patch,
                observe_corruption(patch, watch, phase) as stages,
            ):
                refused = invoke_refused_service(stages, checked)
            evidence = stages.verify(
                kind,
                refused,
                expected_progress=historical_row(corrupted, phase) if kind == "cursor" else None,
            )
            assert_refusal_cleanup(watch)
            save(directory, "service-refusal", evidence, record_property)
            after = capture_raw(
                target, target_pg, directory, "target-after", record_property, columns=columns
            )
            assert typed(after) == typed(corrupted)
            assert copy_hashes(restored_objects) == backed_up
            save(
                directory,
                "target-preservation",
                {
                    "exact_corrupted_state": True,
                    "kind": kind,
                    "actual_service_code": refused.code,
                    "zero_service_writes": True,
                },
                record_property,
            )
    finally:
        # All post-corruption snapshots are raw-only, including the valid source.
        after = capture_raw(legacy, pg, directory, "source-after", record_property, columns=columns)
        assert typed(after) == typed(source_raw)
        assert copy_hashes(FIXTURE_ROOT / "objects") == copy_hashes(backup) == backed_up
        save(directory, "source-preservation", {"exact": True}, record_property)
