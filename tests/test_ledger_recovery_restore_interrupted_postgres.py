"""One schema-only/data-only COPY cancellation; no intact retry or full recovery claim."""

import json
import math
import os
import time

import pytest
from ledger_provisioning_fixture import initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import assert_stage, invoke
from ledger_restore_authority import typed
from ledger_restore_interruption_control import InterruptionControl
from ledger_restore_interruption_oracles import archive_witness, assert_cancelled_restore
from ledger_restore_interruption_ownership import interrupted_tool_ownership
from ledger_restore_interruption_raw import assert_schema_only, observe_schema_only
from ledger_restore_interruption_tool import (
    data_environment,
    run_interrupted_data_restore,
    split_command,
)
from ledger_restore_postgres_fixture import (
    capture,
    copy_ciphertexts,
    copy_hashes,
    empty_target,
    save,
    tool_configuration,
)
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

__all__ = [
    "controlled_database_name",
    "legacy",
    "observed_reader",
    "pg",
    "pytestmark",
    "interrupted_tool_ownership",
]


def test_cancelled_data_restore_preserves_schema_only_state(
    legacy, pg, tmp_path, monkeypatch, record_property, interrupted_tool_ownership
):
    # The reviewed controller supplies the original child's absolute monotonic limit.
    deadline = float(os.environ["REWIND_TEST_RESTORE_CHILD_DEADLINE"])
    assert math.isfinite(deadline) and 0 < deadline - time.monotonic() <= 360
    directory = tmp_path / "interrupted-restore-evidence"
    binary, socket, port, token = tool_configuration(pg, directory, record_property)
    manifests = [initial_manifest(legacy)]
    manifests.append(next_manifest(manifests[0]))
    receipts = []
    for index, manifest in enumerate(manifests):
        with observe_service(monkeypatch, record_property) as watch:
            receipts.append(invoke(legacy, pg, manifest))
            record_property(
                "interrupted_setup_" + str(index), json.dumps(watch.verify(committed=[True]))
            )
    assert_stage(
        legacy, pg, manifests, receipts, record_property=record_property, observation="source"
    )
    before = capture(legacy, pg, directory, "source-before", record_property)
    source_raw = observe_schema_only(legacy, pg, directory, "source-raw-schema", record_property)
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
            "scope": "same-cluster schema-only/data-only cancellation",
        },
        record_property,
    )
    archive, witness = None, None
    drain(pg)
    try:
        archive = run_tool(
            tool_command(binary / "pg_dump", "pg_dump", pg["owner"].url.database, socket, port),
            directory,
            label="dump",
            env=tool_environment(socket, "ar_restore_" + token + "_dump"),
            archive=True,
        )
        witness = archive_witness(archive, source_raw)
        save(directory, "archive", witness, record_property)
        with empty_target(legacy, pg, directory, record_property) as (target, target_pg):
            database = target_pg["owner"].url.database
            command = split_command(binary / "pg_restore", database, socket, archive, "schema")
            environment = tool_environment(socket, "ar_restore_" + token + "_restore")
            environment.update(LC_ALL="C", LANG="C")
            run_tool(command, directory, label="schema-restore", env=environment)
            drain(target_pg)
            baseline = observe_schema_only(
                target, target_pg, directory, "schema-only-before", record_property
            )
            assert_schema_only(baseline, source_raw)
            relation = next(
                row for row in baseline["inventory"]["relations"] if row["name"] == "api_keys"
            )
            with target.case.engine.connect() as connection:
                connection.exec_driver_sql("SET statement_timeout='2000ms'")
                database_oid = connection.exec_driver_sql(
                    "SELECT oid::bigint FROM pg_database WHERE datname=current_database()"
                ).scalar_one()
            drain(target_pg)
            control = InterruptionControl(
                interrupted_tool_ownership,
                socket=socket,
                token=token,
                database_oid=database_oid,
                relation_oid=relation["oid"],
                directory=directory,
                parent_deadline=deadline,
            )
            control.prepare()
            command = split_command(binary / "pg_restore", database, socket, archive, "data")
            with pytest.raises(RuntimeError) as caught:
                run_interrupted_data_restore(
                    command, directory, env=data_environment(socket, token), control=control
                )
            result = assert_cancelled_restore(
                caught.value, directory, command, control, pg["owner_role"]
            )
            save(directory, "expected-native-cancellation", result, record_property)
            after = observe_schema_only(
                target, target_pg, directory, "schema-only-after", record_property
            )
            assert_schema_only(after, source_raw)
            assert typed(after) == typed(baseline)
            save(
                directory,
                "schema-only-preservation",
                {
                    "exact": True,
                    "reached_copy": "public.api_keys",
                    "earlier_writes_claimed": False,
                    "restore_rollback_acknowledgment_claimed": False,
                },
                record_property,
            )
    finally:
        after = capture(legacy, pg, directory, "source-after", record_property)
        assert after == before
        assert copy_hashes(FIXTURE_ROOT / "objects") == copy_hashes(backup) == backed_up
        if witness is not None:
            assert archive_witness(archive, source_raw) == witness
        save(directory, "source-preservation", {"exact": True}, record_property)
