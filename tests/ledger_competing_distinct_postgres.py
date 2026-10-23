"""Native typed collision-key comparison and physical refusal evidence."""

from copy import deepcopy
from datetime import UTC, datetime

import psycopg
from ledger_competing_distinct import prove_collision, rows
from test_ledger_competing_postgres import assert_try_lock, prove_absence
from test_ledger_reader_native import _assert_reviewed_ctes


def prove_native_collision(before, winner, loser, case):
    """Retain typed snapshots; normalize only the two account-key timestamp cells."""
    absence = [prove_absence(before, value) for value in (winner, loser)]
    comparable = deepcopy(before)
    table = comparable["tables"]["budget_accounts"]
    normalized = []
    for values in table["rows"]:
        row = list(values)
        for name in ("period_start", "period_end"):
            index = table["columns"].index(name)
            value = row[index]
            assert type(value) is datetime and value.utcoffset() is not None
            row[index] = (
                value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
            )
        normalized.append(tuple(row))
    table["rows"] = tuple(normalized)
    proof = prove_collision(comparable, winner, loser, case)
    return {"native_absence": absence, **proof}


def assert_native_conflict(message):
    witness, raw = message["witness"], message["raw_id"]
    observed, events = assert_try_lock(message, True)
    (entry,) = witness["classifications"]
    (lock,) = witness["try_locks"]
    assert entry["backend"] == {
        "pid": lock["backend_pid"],
        "database": lock["database"],
        "role": lock["role"],
        "transaction_status": int(psycopg.pq.TransactionStatus.INTRANS),
        "raw_closed": False,
        "claim_released": False,
        "connection_closed": False,
        "work_detached": False,
    }
    assert entry["raw_id"] == raw and entry["engine_id"] == message["engine_id"]
    (outcome,) = observed["outcomes"]
    boundary = observed["command_boundary"]
    assert outcome["begin_attempted"] and outcome["begun"]
    assert outcome["rollback_attempted"] and outcome["rollback_acknowledged"]
    assert not any(
        outcome[key] for key in ("commit_attempted", "commit_acknowledged", "cleanup_failed")
    )
    assert boundary["raw_id"] == raw and not boundary["engine_poisoned"]
    assert all(
        boundary[key]
        for key in ("raw_closed", "connection_closed", "claim_released", "claim_absent")
    )
    assert witness["refusal"] == {"type": "MigrationRefused", "code": "ledger_manifest_conflict"}
    assert witness["receipt"] is None
    assert witness["native_errors"] == [
        {
            "type": "MigrationRefused",
            "code": "ledger_manifest_conflict",
            "mapped_type": "MigrationRefused",
            "mapped_code": "ledger_manifest_conflict",
            "same_error": True,
        }
    ]
    assert witness["scoped_cleanup"] == {
        "raw_ids": [raw],
        "closed": [True],
        "rescued_raw_ids": [],
        "errors": [],
        "engine_id": message["engine_id"],
    }
    assert observed["observer_units"] == [6, 3] and observed["tuple_deltas"] == [[]]
    ordinary = [sql for phase, kind, _, sql in events if phase == "ordinary" and kind == "sql-call"]
    _assert_reviewed_ctes(ordinary)
    assert ordinary and all(
        sql.lstrip().upper().startswith(("SELECT", "WITH", "SET", "SHOW", "LOCK"))
        for sql in ordinary
    )
    assert all(row["raw_id"] == raw for row in observed["physical"])
    assert not any(row["action"] == "commit" for row in observed["physical"])
    enters = [row for row in observed["markers"] if row[0] == "conflict.classify.enter"]
    refused = [row for row in observed["markers"] if row[0] == "conflict.classify.refused"]
    closes = [row for row in observed["markers"] if row[0] == "connection.close.before"]
    assert len(enters) == len(refused) == len(closes) == 1
    enter, refusal, close = enters[0][2], refused[0][2], closes[0][2]
    assert lock["fetch_return_trace_index"] < enter <= refusal < close <= boundary["trace_end"]
    rollbacks = [
        row
        for row in observed["physical"]
        if row["action"] == "rollback" and row["trace_end"] <= close
    ]
    (rollback,) = rollbacks
    assert rollback["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
    assert rollback["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)
    assert refusal < rollback["trace_end"] <= close
    prefix = events[refusal:close]
    assert [
        row[1] for row in prefix if row[1] in {"rollback-call", "rollback-return", "rollback-error"}
    ] == ["rollback-call", "rollback-return"]
    assert [row[3] for row in prefix if row[1] == "command"] == ["ROLLBACK"]
    assert any(
        row["action"] == "close"
        and not row["closed_before"]
        and row["closed_after"]
        and close < row["trace_end"] <= boundary["trace_end"]
        for row in observed["physical"]
    )
    assert not any(row[1] in {"commit-call", "commit-return"} for row in events)
    assert all(row[0] != "harness-dispose" for row in events[: boundary["trace_end"]])
    assert observed["xids"] and {row[0] for row in observed["xids"]} == {raw}
    assert len({row[1] for row in observed["xids"]}) == 1


def assert_added_project(before, after, original_project, other):
    """A fixture-only insertion changes one project row, never catalog or authority."""
    assert {key: value for key, value in after.items() if key != "tables"} == {
        key: value for key, value in before.items() if key != "tables"
    }
    assert set(before["tables"]) == set(after["tables"])
    for table in before["tables"]:
        if table != "projects":
            assert before["tables"][table] == after["tables"][table], table
    old, new = rows(before, "projects"), rows(after, "projects")
    assert len(old) == 1 and old[0]["id"] == original_project and len(new) == 2
    assert other != original_project
    assert [row for row in new if row["id"] != other] == old
    (added,) = [row for row in new if row["id"] == other]
    assert added == {**old[0], "id": other, "name": "Independent project", "run_sequence": 0}
    return added
