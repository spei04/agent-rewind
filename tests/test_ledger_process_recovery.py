"""Actual SQLite child death, independently proved persisted states and reentry."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from ledger_process_fixture import HeldProcess
from ledger_provisioning_fixture import (
    assert_no_writes,
    assert_stage,
    build_case,
    ciphertexts,
    snapshot,
    source_rows,
)
from ledger_recovery_fixture import fresh_reentry
from test_ledger_recovery import pending

from agent_rewind.migrations.ledger_state import LedgerProvisioning


def assert_physical_barrier(marker, phase):
    witness = marker["witness"]
    observation = witness["observation"]
    raw = marker["raw_id"]
    events = observation["native_trace"]
    assert observation["command_boundary"] is None
    assert observation["faults"] == []
    assert len(observation["work"]) == len(observation["outcomes"]) == 1
    outcome = observation["outcomes"][0]
    assert outcome["begin_attempted"] and outcome["begun"] and outcome["commit_attempted"]
    assert not any(
        outcome[name]
        for name in (
            "commit_acknowledged",
            "rollback_attempted",
            "rollback_acknowledged",
            "cleanup_failed",
        )
    )
    assert observation["work"][0]["cleanup"] == []
    assert 0 < observation["work"][0]["ordinary"] <= 2028
    assert sum(event[0] == "connect_attempt" for event in events) == 1
    assert [event[2] for event in events if event[0] == "connect_return"] == [raw]
    sql = [(i, event[3]) for i, event in enumerate(events) if event[0] == "sql"]
    assert sum(value == "BEGIN EXCLUSIVE" for _, value in sql) == 1
    assert sum(value == "COMMIT" for _, value in sql) == int(phase == "after")
    assert not any(value == "ROLLBACK" for _, value in sql)
    inserted = [
        i for i, value in sql if value.lstrip().startswith("INSERT INTO migration_progress")
    ]
    assert inserted
    final, classified = witness["stages"]
    assert final[0] == "finalize.return" and classified[0] == "classify.return"
    assert inserted[-1] < final[1] <= classified[1]
    assert any(
        event[0] == "c_return" and event[2:] == [raw, "execute"]
        for event in events[inserted[-1] + 1 : final[1]]
    )
    physical = [
        event
        for event in events
        if event[0] in {"c_call", "c_return", "c_exception"} and event[2:] == [raw, "commit"]
    ]
    assert [event[0] for event in physical] == (["c_call", "c_return"] if phase == "after" else [])
    assert witness["in_transaction"] is (phase == "before")
    names = [row[0] for row in observation["markers"]]
    assert names == (
        [
            "death.before_physical_commit",
            "commit.before_native",
            "commit.native_ack",
            "death.physical_commit_ack",
        ]
        if phase == "after"
        else ["death.before_physical_commit"]
    )
    assert all(row[1] == raw for row in observation["markers"])
    assert classified[1] <= observation["markers"][0][2]
    # Cursor.close shares the trace raw identity; only the scoped physical
    # connection markers and live ownership witness identify connection closure.
    assert not witness["ownership_closed"] and not witness["connection_closed"]
    assert not witness["work_detached"]
    assert not any(event[1] == "harness-dispose" for event in events)


def prove_sqlite_drain(path, lifecycle):
    assert lifecycle["reaped"] and lifecycle["events"][-1] == "pipe_eof"
    actions = []
    with closing(sqlite3.connect(path, timeout=1)) as raw:
        raw.set_authorizer(lambda *arguments: actions.append(arguments) or sqlite3.SQLITE_OK)
        raw.execute("BEGIN EXCLUSIVE")
        assert raw.in_transaction
        raw.execute("ROLLBACK")
        assert not raw.in_transaction
    assert_no_writes(actions)
    return {"exclusive_begin_returned": True, "rollback_returned": True, "authorizer": actions}


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_actual_child_death_at_physical_commit(
    tmp_path, monkeypatch, record_property, operation, phase
):
    fixture = build_case(tmp_path / "death.sqlite")
    process = None
    try:
        target, manifests, receipts = pending(fixture, operation)
        before = snapshot(fixture.case.path)
        protected = ciphertexts(fixture.case)
        record_property("exact_before", json.dumps(before))
        record_property("protected_ciphertexts", json.dumps(protected))
        # The spawned child receives only values, and creates its own attested
        # engine. Close every parent setup connection before it is started.
        fixture.close()
        process = HeldProcess(
            tmp_path,
            worker=Path(__file__).with_name("ledger_sqlite_process_fixture.py"),
            case=operation,
            phase=phase,
            configuration={"url": f"sqlite:///{fixture.case.path}", "manifest": target},
        )
        try:
            marker = process.barrier()
            # Freeze the native witness before killing; validate it only after
            # the child is reaped so assertion failures cannot race recovery.
            record_property("child_barrier", json.dumps(marker))
            lifecycle = process.kill_and_reap()
        finally:
            process.close()
            record_property("child_lifecycle", json.dumps(process.record))
        assert_physical_barrier(marker, phase)
        record_property(
            "sqlite_drain", json.dumps(prove_sqlite_drain(fixture.case.path, lifecycle))
        )
        after = snapshot(fixture.case.path)
        if phase == "before":
            assert after == before
        else:
            original = LedgerProvisioning(**marker["witness"]["receipt"], outcome="complete")
            assert_stage(fixture, [*manifests, target], [*receipts, original])
        assert ciphertexts(fixture.case) == protected == fixture.encrypted
        assert source_rows(fixture.case.path) == fixture.original
        recovered, _ = fresh_reentry(fixture, target, monkeypatch, record_property)
        if phase == "before":
            assert recovered is None
        else:
            assert recovered.model_dump(mode="json") == marker["witness"]["receipt"]
        assert snapshot(fixture.case.path) == after
        assert ciphertexts(fixture.case) == protected
        record_property("exact_after", json.dumps(after))
    finally:
        if process is not None:
            process.close()
        fixture.close()
