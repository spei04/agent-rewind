"""Identical absent intents compete in independent processes and replay exactly."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from ledger_competing_process import CommandGroup
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    snapshot,
    source_rows,
)
from test_ledger_recovery import pending

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning


def prove_intent_absent(before, target):
    progress = before["tables"]["migration_progress"]
    rows = [dict(zip(progress["columns"], row, strict=True)) for row in progress["rows"]]
    assert "ledger_manifest_" + target["manifest_id"] not in {row["phase"] for row in rows}
    accounts = before["tables"].get("budget_accounts", {"columns": (), "rows": ()})
    present = [dict(zip(accounts["columns"], row, strict=True)) for row in accounts["rows"]]
    requested_ids = {row["id"] for row in target["accounts"]}
    requested_periods = {
        (row["organization_id"], row["scope"], row["scope_id"], row["period_start"])
        for row in target["accounts"]
    }
    assert requested_ids.isdisjoint(row["id"] for row in present)
    assert requested_periods.isdisjoint(
        (row["organization_id"], row["scope"], row["scope_id"], row["period_start"])
        for row in present
    )
    return {
        "manifest_phase_absent": True,
        "requested_ids_absent": sorted(requested_ids),
        "requested_periods_absent": sorted(requested_periods),
    }


def assert_held_winner(message):
    raw = message["raw_id"]
    witness = message["witness"]
    observed = witness["observation"]
    events = observed["native_trace"]
    assert observed["command_boundary"] is None and observed["faults"] == []
    assert len(observed["outcomes"]) == len(observed["work"]) == 1
    outcome = observed["outcomes"][0]
    assert outcome["begin_attempted"] and outcome["begun"] and outcome["commit_attempted"]
    assert not any(
        outcome[key]
        for key in (
            "commit_acknowledged",
            "rollback_attempted",
            "rollback_acknowledged",
            "cleanup_failed",
        )
    )
    assert observed["work"][0]["cleanup"] == []
    assert [event[2] for event in events if event[0] == "connect_return"] == [raw]
    sql = [(index, event[3]) for index, event in enumerate(events) if event[0] == "sql"]
    assert sum(statement == "BEGIN EXCLUSIVE" for _, statement in sql) == 1
    assert not any(statement in {"COMMIT", "ROLLBACK"} for _, statement in sql)
    inserted = [
        index
        for index, statement in sql
        if statement.lstrip().startswith("INSERT INTO migration_progress")
    ]
    assert inserted
    final, classified = witness["stages"]
    assert final[0] == "finalize.return" and classified[0] == "classify.return"
    assert inserted[-1] < final[1] <= classified[1]
    assert any(
        event[0] == "c_return" and event[2:] == [raw, "execute"]
        for event in events[inserted[-1] + 1 : final[1]]
    )
    assert not any(event[0] == "c_call" and event[2:] == [raw, "commit"] for event in events)
    assert observed["markers"] == [
        ["competition.before_physical_commit", raw, observed["markers"][0][2]]
    ]
    assert classified[1] <= observed["markers"][0][2]
    assert witness["in_transaction"]
    assert not any(
        witness[key] for key in ("ownership_closed", "connection_closed", "work_detached")
    )
    assert not any(event[1] == "harness-dispose" for event in events)


def assert_result(message, *, busy=False):
    witness = message["witness"]
    observed = witness["observation"]
    raw = message["raw_id"]
    events = observed["native_trace"]
    assert len(observed["work"]) == len(observed["outcomes"]) == 1
    assert [event[2] for event in events if event[0] == "connect_return"] == [raw]
    sql = [event[3] for event in events if event[0] == "sql"]
    assert sql.count("BEGIN EXCLUSIVE") == 1
    outcome = observed["outcomes"][0]
    boundary = observed["command_boundary"]
    assert boundary["raw_id"] == raw and boundary["connection_closed"]
    assert boundary["checkedout"] == 0 and not boundary["lease_present"]
    assert boundary["receipt_completed"] and boundary["receipt_clean"]
    assert not outcome["cleanup_failed"]
    if busy:
        assert witness["refusal"] == {"type": "MigrationRefused", "code": "migration_busy"}
        assert witness["receipt"] is None
        assert witness["native_errors"] == [
            {
                "type": "OperationalError",
                "sqlite_errorcode": sqlite3.SQLITE_BUSY,
                "mapped_type": "MigrationRefused",
                "mapped_code": "migration_busy",
            }
        ]
        assert outcome["begin_attempted"] and not outcome["begun"]
        assert not outcome["commit_attempted"] and not outcome["commit_acknowledged"]
        assert outcome["rollback_attempted"] and outcome["rollback_acknowledged"]
        assert sql.count("COMMIT") == 0
        assert_no_writes(observed["native_authorizer"])
        assert any(event[0] == "c_exception" and event[2:] == [raw, "execute"] for event in events)
    else:
        assert witness["refusal"] is None and witness["native_errors"] == []
        assert outcome["commit_attempted"] and outcome["commit_acknowledged"]
        assert not outcome["rollback_attempted"] and not outcome["rollback_acknowledged"]
        assert sql.count("COMMIT") == 1
        physical = [
            event
            for event in events
            if event[0] in {"c_call", "c_return", "c_exception"} and event[2:] == [raw, "commit"]
        ]
        assert [event[0] for event in physical] == ["c_call", "c_return"]
        assert witness["receipt"]["outcome"] == "complete"


def prove_still_exclusive(path):
    """A separate zero-write attempt after loser exit cannot obtain exclusion."""
    actions = []
    with closing(sqlite3.connect(path, timeout=0)) as raw:
        raw.set_authorizer(lambda *values: actions.append(values) or sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.OperationalError) as caught:
            raw.execute("BEGIN EXCLUSIVE")
        assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        assert not raw.in_transaction
    assert_no_writes(actions)
    return {
        "sqlite_errorcode": caught.value.sqlite_errorcode,
        "attempt": "BEGIN EXCLUSIVE",
        "authorizer": actions,
    }


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_identical_sqlite_operators_refuse_then_replay(tmp_path, record_property, operation):
    fixture = build_case(tmp_path / "competing.sqlite")
    group = None
    try:
        target, manifests, receipts = pending(fixture, operation)
        before = snapshot(fixture.case.path)
        protected = ciphertexts(fixture.case)
        record_property("intent_absence", json.dumps(prove_intent_absent(before, target)))
        digest = hashlib.sha256(validate_ledger_manifest(target).canonical_bytes).hexdigest()
        record_property("exact_before", json.dumps(before))
        record_property("protected_ciphertexts", json.dumps(protected))
        record_property("intent", json.dumps({"manifest": target, "sha256": digest}))
        fixture.close()
        group = CommandGroup(tmp_path)
        worker = Path(__file__).with_name("ledger_sqlite_competing_fixture.py")
        configuration = {"url": f"sqlite:///{fixture.case.path}", "manifest": target}

        def spawn(role):
            return group.spawn(
                worker=worker,
                case=operation,
                role=role,
                intent_sha256=digest,
                configuration=configuration,
            )

        winner = spawn("winner")
        held = winner.receive()
        record_property("winner_held", json.dumps(held))
        assert_held_winner(held)
        loser = spawn("loser")
        refused = loser.receive()
        record_property("loser_result", json.dumps(refused))
        assert_result(refused, busy=True)
        assert loser.record["events"][-2:] == ["reaped", "pipe_eof"]
        assert winner.process.poll() is None
        still_held = winner.probe()
        record_property("winner_after_loser_cleanup", json.dumps(still_held))
        assert_held_winner(still_held)
        assert still_held["witness"] == held["witness"]
        record_property(
            "independent_exclusion_after_loser",
            json.dumps(prove_still_exclusive(fixture.case.path)),
        )
        winner.resume()
        completed = winner.receive()
        record_property("winner_result", json.dumps(completed))
        assert_result(completed)
        original = LedgerProvisioning(**completed["witness"]["receipt"])
        assert original.model_dump(mode="json", exclude={"outcome"}) == held["witness"]["receipt"]
        assert_stage(fixture, [*manifests, target], [*receipts, original])
        after = snapshot(fixture.case.path)
        assert ciphertexts(fixture.case) == protected == fixture.encrypted
        assert source_rows(fixture.case.path) == fixture.original
        replay = spawn("replay")
        recovered = replay.receive()
        record_property("explicit_replay_result", json.dumps(recovered))
        assert_result(recovered)
        assert_no_writes(recovered["witness"]["observation"]["native_authorizer"])
        assert recovered["witness"]["receipt"] == completed["witness"]["receipt"]
        assert len({child.process.pid for child in group.children}) == 3
        assert len(group.messages) == 10
        assert all(message["completed"] for message in group.messages)
        assert snapshot(fixture.case.path) == after
        assert ciphertexts(fixture.case) == protected
        record_property("exact_after", json.dumps(after))
    except BaseException as error:
        record_property(
            "first_failure", json.dumps({"type": type(error).__name__, "message": str(error)})
        )
        raise
    finally:
        try:
            if group is not None:
                try:
                    group.close()
                finally:
                    record_property("command_group", json.dumps(group.record))
        finally:
            fixture.close()
