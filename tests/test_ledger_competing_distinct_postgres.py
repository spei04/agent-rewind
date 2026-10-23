"""Three actual native contention cases with current-parent identity refusals."""

import json
from pathlib import Path

import pytest
import test_ledger_competing_postgres as competing
from ledger_competing_distinct import CASES, assert_conflict_context, changed_parent, intents
from ledger_competing_distinct_postgres import (
    assert_added_project,
    assert_native_conflict,
    prove_native_collision,
)
from ledger_competing_native import NativeCommandGroup
from ledger_competing_postgres_observer import (
    TIMEOUT,
    assert_same_backend,
    attest_backend,
    install_cleanup_guard,
    natural_exit,
)
from ledger_provisioning_fixture import expected_stage, identity, initial_manifest
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    encrypted_files,
    invoke,
    native_snapshot,
    progress_diagnostic,
    source_rows,
)
from sqlalchemy import text
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning

__all__ = ["controlled_database_name", "observed_reader"]
pg, legacy = competing.pg, competing.legacy
pytestmark = competing.pytestmark


def add_shared_project(fixture, pg):
    before = native_snapshot(fixture.case, pg)
    other = identity(9000)
    with fixture.case.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at,run_sequence) "
                "SELECT :id,organization_id,'Independent project',created_at,0 "
                "FROM projects WHERE id=:project"
            ),
            {"id": other, "project": fixture.project},
        )
    after = native_snapshot(fixture.case, pg)
    added = assert_added_project(before, after, fixture.project, other)
    try:
        with fixture.case.engine.connect() as connection:
            assert source_rows(connection) == fixture.original
    finally:
        drain(pg)
    assert encrypted_files(fixture) == fixture.encrypted
    fixture.before = after
    return other, {"before": before, "after": after, "added_project": added}


@pytest.mark.parametrize("case", CASES)
def test_distinct_postgres_operators_refuse_current_parent_collision(
    legacy, pg, tmp_path, record_property, case
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    other_project = None
    if case == "shared-organization":
        other_project, setup = add_shared_project(legacy, pg)
        record("shared_project_setup", setup)
    first = initial_manifest(legacy)
    initial_receipt = invoke(legacy, pg, first)
    assert_stage(
        legacy,
        pg,
        [first],
        [initial_receipt],
        record_property=record_property,
        observation="initial",
    )
    winner_intent, loser_intent = intents(
        first, case, project=legacy.project, other_project=other_project
    )
    before, protected = native_snapshot(legacy.case, pg), encrypted_files(legacy)
    proof = prove_native_collision(before, winner_intent, loser_intent, case)
    record("collision_proof", proof)
    record("exact_before", before)
    record("protected_ciphertexts", protected)
    record("original_intents", {"winner": winner_intent, "loser": loser_intent})
    with legacy.case.engine.connect() as connection:
        table_ids = dict(
            connection.exec_driver_sql(
                "SELECT c.relname,c.oid FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname"
            ).all()
        )
    assert set(table_ids) == set(before["tables"])
    record("predecessor_table_ids", table_ids)
    legacy.close()
    drain(pg)
    with pg["control"].connect().execution_options(isolation_level="AUTOCOMMIT") as control:
        control.exec_driver_sql(TIMEOUT).close()
        group = NativeCommandGroup(tmp_path)
        install_cleanup_guard(pg["control"], group, record)
        worker = Path(__file__).with_name("ledger_postgres_competing_fixture.py")

        def spawn(role, target, *, conflict=False):
            return group.spawn(
                worker=worker.with_name("ledger_postgres_conflict_fixture.py")
                if conflict
                else worker,
                case=case,
                role=role,
                intent_sha256=validate_ledger_manifest(target).digest,
                configuration={
                    "url": legacy.case.engine.url.render_as_string(hide_password=False),
                    "manifest": target,
                },
            )

        try:
            winner = spawn("winner", winner_intent)
            held = winner.receive()
            record("winner_held", held)
            competing.assert_held(held, winner=True)
            first_backend = attest_backend(
                control, held, pg, group.work_deadline, winner=True, table_ids=table_ids
            )
            record("winner_backend", first_backend)
            loser = spawn("loser", loser_intent)
            attested = loser.receive()
            record("loser_false_try_lock", attested)
            competing.assert_held(attested, winner=False)
            loser_backend = attest_backend(control, attested, pg, group.work_deadline, winner=False)
            record("loser_backend", loser_backend)
            assert loser_backend["activity"][0]["pid"] != first_backend["activity"][0]["pid"]
            loser.resume()
            busy = loser.receive()
            record("distinct_loser_busy", busy)
            competing.assert_result(busy, busy=True)
            assert busy["witness"]["try_locks"] == attested["witness"]["try_locks"]
            natural_exit(control, loser_backend, loser.record, group.work_deadline, record)
            assert winner.process.poll() is None
            still_held = winner.probe()
            record("winner_after_loser_cleanup", still_held)
            competing.assert_held(still_held, winner=True)
            assert still_held["witness"] == held["witness"]
            current_backend = attest_backend(
                control, still_held, pg, group.work_deadline, winner=True, table_ids=table_ids
            )
            record("winner_backend_after_loser_cleanup", current_backend)
            assert_same_backend(first_backend, current_backend)
            winner.resume()
            completed = winner.receive()
            record("winner_result", completed)
            competing.assert_result(completed)
            original = LedgerProvisioning(**completed["witness"]["receipt"])
            assert (
                original.model_dump(mode="json", exclude={"outcome"}) == held["witness"]["receipt"]
            )
            manifests, receipts = [first, winner_intent], [initial_receipt, original]
            assert_stage(
                legacy,
                pg,
                manifests,
                receipts,
                record_property=record_property,
                observation="winner_committed",
            )
            after = native_snapshot(legacy.case, pg)
            accounts, _, state = expected_stage(
                legacy, manifests, receipts, database_role=pg["owner_role"]
            )
            target = changed_parent(loser_intent, state["head"])
            record(
                "explicit_changed_parent_request",
                {
                    "previous": loser_intent,
                    "previous_sha256": validate_ledger_manifest(loser_intent).digest,
                    "request": target,
                    "request_sha256": validate_ledger_manifest(target).digest,
                    "actual_committed_head": state["head"],
                    "purpose": "current-parent identity conflict; not identical replay",
                },
            )
            conflict = spawn("replay", target, conflict=True)
            refused = conflict.receive()
            record("explicit_changed_parent_conflict", refused)
            history = [
                {
                    "manifest": manifest,
                    "receipt": receipt.model_dump(mode="json", exclude={"outcome"}),
                }
                for manifest, receipt in zip(manifests, receipts, strict=True)
            ]
            assert_conflict_context(refused, target, state, accounts, history, proof["collisions"])
            assert_native_conflict(refused)
            assert len({child.process.pid for child in group.children}) == 3
            assert len(group.messages) == 12 and all(row["completed"] for row in group.messages)
            assert all(
                child.record["events"][-2:] == ["reaped", "pipe_eof"] for child in group.children
            )
            assert native_snapshot(legacy.case, pg) == after
            assert_stage(
                legacy,
                pg,
                manifests,
                receipts,
                record_property=record_property,
                observation="conflict_refused",
            )
            assert encrypted_files(legacy) == protected == legacy.encrypted
            record("exact_after_winner_and_refusal", after)
        except BaseException as error:
            record("first_failure", {"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            try:
                group.close()
            finally:
                record("command_group", group.record)
