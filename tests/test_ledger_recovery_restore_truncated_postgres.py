"""One fixed truncated-archive failure; no intact retry or rollback-stage claim."""

import json

import pytest
from ledger_provisioning_fixture import initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import assert_stage, invoke
from ledger_restore_authority import typed
from ledger_restore_empty_target import assert_empty_target, observe_empty_target
from ledger_restore_postgres_fixture import (
    capture,
    copy_ciphertexts,
    copy_hashes,
    empty_target,
    save,
    tool_configuration,
)
from ledger_restore_tools import run_tool, tool_command, tool_environment
from ledger_restore_truncation import (
    assert_archive_pair,
    assert_native_truncation,
    truncate_archive,
)
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

__all__ = ["controlled_database_name", "legacy", "observed_reader", "pg", "pytestmark"]


def test_truncated_custom_archive_leaves_empty_target(
    legacy, pg, tmp_path, monkeypatch, record_property
):
    directory = tmp_path / "truncated-restore-evidence"
    binary, socket, port, token = tool_configuration(pg, directory, record_property)
    manifests = [initial_manifest(legacy)]
    manifests.append(next_manifest(manifests[0]))
    receipts = []
    for index, manifest in enumerate(manifests):
        with observe_service(monkeypatch, record_property) as watch:
            receipts.append(invoke(legacy, pg, manifest))
            record_property(
                "truncated_setup_" + str(index), json.dumps(watch.verify(committed=[True]))
            )
    assert_stage(
        legacy, pg, manifests, receipts, record_property=record_property, observation="source"
    )
    before = capture(legacy, pg, directory, "source-before", record_property)
    backup = directory / "backup-objects"
    backed_up = copy_ciphertexts(FIXTURE_ROOT / "objects", backup)
    assert backed_up == legacy.encrypted
    save(
        directory,
        "source-receipts",
        {
            "manifests": manifests,
            "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            "ciphertexts": backed_up,
            "scope": (
                "one fixed tail truncation; existing roles; no reached-DDL or rollback-ACK claim"
            ),
        },
        record_property,
    )
    witness = None
    drain(pg)
    try:
        archive = run_tool(
            tool_command(binary / "pg_dump", "pg_dump", pg["owner"].url.database, socket, port),
            directory,
            label="dump",
            env=tool_environment(socket, "ar_restore_" + token + "_dump"),
            archive=True,
        )
        witness = truncate_archive(archive, directory / "truncated.archive")
        save(directory, "archive-defect", witness, record_property)
        with empty_target(legacy, pg, directory, record_property) as (target, target_pg):
            arguments = {
                "database": target_pg["owner"].url.database,
                "owner": pg["owner_role"],
                "source_authority": before["authority"],
            }
            empty_before = observe_empty_target(
                target, target_pg, directory, "empty-target-before", record_property
            )
            assert_empty_target(empty_before, **arguments)
            command = tool_command(
                binary / "pg_restore",
                "pg_restore",
                target_pg["owner"].url.database,
                socket,
                port,
                archive=directory / "truncated.archive",
            )
            environment = tool_environment(socket, "ar_restore_" + token + "_restore")
            environment.update(LC_ALL="C", LANG="C")
            with pytest.raises(RuntimeError) as caught:
                run_tool(command, directory, label="truncated-restore", env=environment)
            result = assert_native_truncation(caught.value, directory, command, witness)
            save(
                directory,
                "expected-native-failure",
                {"record": result, "locale": "C", "error": str(caught.value)},
                record_property,
            )
            drain(target_pg)
            empty_after = observe_empty_target(
                target, target_pg, directory, "empty-target-after", record_property
            )
            assert_empty_target(empty_after, **arguments)
            assert typed(empty_after) == typed(empty_before)
            save(directory, "empty-target-preservation", {"exact": True}, record_property)
    finally:
        after = capture(legacy, pg, directory, "source-after", record_property)
        assert after == before
        assert copy_hashes(FIXTURE_ROOT / "objects") == copy_hashes(backup) == backed_up
        if witness is not None:
            assert_archive_pair(witness)
        save(directory, "source-preservation", {"exact": True}, record_property)
