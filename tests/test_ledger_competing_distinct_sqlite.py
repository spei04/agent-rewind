"""Real SQLite contention followed by an explicit current-parent identity conflict."""

import json
from pathlib import Path

import pytest
from ledger_competing_distinct import (
    CASES,
    assert_conflict_context,
    assert_sqlite_conflict,
    changed_parent,
    intents,
    prove_collision,
    rows,
)
from ledger_competing_process import CommandGroup
from ledger_provisioning_fixture import (
    assert_stage,
    build_case,
    ciphertexts,
    expected_stage,
    identity,
    initial_manifest,
    invoke,
    snapshot,
    source_rows,
)
from sqlalchemy import text
from test_ledger_competing_sqlite import assert_held_winner, assert_result, prove_still_exclusive

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning


def add_shared_project(fixture):
    before = snapshot(fixture.case.path)
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
    after = snapshot(fixture.case.path)
    assert {key: value for key, value in after.items() if key != "tables"} == {
        key: value for key, value in before.items() if key != "tables"
    }
    assert set(before["tables"]) == set(after["tables"])
    for table in before["tables"]:
        if table != "projects":
            assert before["tables"][table] == after["tables"][table], table
    old, new = rows(before, "projects"), rows(after, "projects")
    assert len(old) == 1 and len(new) == 2
    assert [row for row in new if row["id"] != other] == old
    (added,) = [row for row in new if row["id"] == other]
    assert added == {**old[0], "id": other, "name": "Independent project", "run_sequence": 0}
    assert source_rows(fixture.case.path) == fixture.original
    assert ciphertexts(fixture.case) == fixture.encrypted
    fixture.before = after
    return other, {"before": before, "after": after, "added_project": added}


@pytest.mark.parametrize("case", CASES)
def test_distinct_sqlite_operators_refuse_current_parent_collision(tmp_path, record_property, case):
    fixture = build_case(tmp_path / "distinct.sqlite")
    group = None

    def record(name, value):
        record_property(name, json.dumps(value, allow_nan=False))

    try:
        other_project = None
        if case == "shared-organization":
            other_project, setup = add_shared_project(fixture)
            record("shared_project_setup", setup)
        first = initial_manifest(fixture)
        initial_receipt = invoke(fixture, first)
        assert_stage(fixture, [first], [initial_receipt])
        winner_intent, loser_intent = intents(
            first, case, project=fixture.project, other_project=other_project
        )
        before = snapshot(fixture.case.path)
        protected = ciphertexts(fixture.case)
        proof = prove_collision(before, winner_intent, loser_intent, case)
        record("collision_proof", proof)
        record("exact_before", before)
        record("protected_ciphertexts", protected)
        record("original_intents", {"winner": winner_intent, "loser": loser_intent})
        fixture.close()
        group = CommandGroup(tmp_path)
        worker = Path(__file__).with_name("ledger_sqlite_competing_fixture.py")

        def spawn(role, target, *, conflict=False):
            return group.spawn(
                worker=worker.with_name("ledger_sqlite_conflict_fixture.py")
                if conflict
                else worker,
                case=case,
                role=role,
                intent_sha256=validate_ledger_manifest(target).digest,
                configuration={"url": f"sqlite:///{fixture.case.path}", "manifest": target},
            )

        winner = spawn("winner", winner_intent)
        held = winner.receive()
        record("winner_held", held)
        assert_held_winner(held)
        loser = spawn("loser", loser_intent)
        busy = loser.receive()
        record("distinct_loser_busy", busy)
        assert_result(busy, busy=True)
        assert loser.record["events"][-2:] == ["reaped", "pipe_eof"]
        assert winner.process.poll() is None
        still_held = winner.probe()
        record("winner_after_loser_cleanup", still_held)
        assert_held_winner(still_held)
        assert still_held["witness"] == held["witness"]
        record("independent_exclusion_after_loser", prove_still_exclusive(fixture.case.path))
        winner.resume()
        completed = winner.receive()
        record("winner_result", completed)
        assert_result(completed)
        original = LedgerProvisioning(**completed["witness"]["receipt"])
        assert original.model_dump(mode="json", exclude={"outcome"}) == held["witness"]["receipt"]
        manifests, receipts = [first, winner_intent], [initial_receipt, original]
        assert_stage(fixture, manifests, receipts)
        after = snapshot(fixture.case.path)
        accounts, _, state = expected_stage(fixture, manifests, receipts)
        head = state["head"]
        target = changed_parent(loser_intent, head)
        record(
            "explicit_changed_parent_request",
            {
                "previous": loser_intent,
                "previous_sha256": validate_ledger_manifest(loser_intent).digest,
                "request": target,
                "request_sha256": validate_ledger_manifest(target).digest,
                "actual_committed_head": head,
                "purpose": "current-parent identity conflict; not identical replay",
            },
        )
        conflict = spawn("replay", target, conflict=True)
        refused = conflict.receive()
        record("explicit_changed_parent_conflict", refused)
        history = [
            {"manifest": manifest, "receipt": receipt.model_dump(mode="json", exclude={"outcome"})}
            for manifest, receipt in zip(manifests, receipts, strict=True)
        ]
        assert_conflict_context(refused, target, state, accounts, history, proof["collisions"])
        assert_sqlite_conflict(refused)
        assert len({child.process.pid for child in group.children}) == 3
        assert len(group.messages) == 10 and all(row["completed"] for row in group.messages)
        assert all(
            child.record["events"][-2:] == ["reaped", "pipe_eof"] for child in group.children
        )
        assert snapshot(fixture.case.path) == after
        assert_stage(fixture, manifests, receipts)
        assert ciphertexts(fixture.case) == protected == fixture.encrypted
        assert source_rows(fixture.case.path) == fixture.original
        record("exact_after_winner_and_refusal", after)
    except BaseException as error:
        record("first_failure", {"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        try:
            if group is not None:
                try:
                    group.close()
                finally:
                    record("command_group", group.record)
        finally:
            fixture.close()
