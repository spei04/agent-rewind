"""Constraint-boundary regressions for the actual native contention observer."""

import hashlib

import psycopg
import pytest
import test_ledger_competing_postgres as observer
from ledger_postgres_competing_fixture import TRY_LOCK_SQL

from agent_rewind.migrations.ledger_writer_sql import SQL
from agent_rewind.migrations.service import MIGRATOR_LOCK


def held_message(constraint_sql):
    raw = 456
    events = [
        ["ordinary", "connect-call", raw, None],
        ["ordinary", "internal-connect", raw, None],
        ["ordinary", "connect-return", raw, None],
        ["ordinary", "sql-call", raw, TRY_LOCK_SQL],
        ["ordinary", "sql-return", raw, TRY_LOCK_SQL],
        ["ordinary", "try-lock-fetched", raw, True],
        ["ordinary", "sql-call", raw, "INSERT INTO migration_progress VALUES (1)"],
        ["ordinary", "sql-return", raw, "INSERT INTO migration_progress VALUES (1)"],
        ["ordinary", "sql-call", raw, constraint_sql],
        ["ordinary", "sql-return", raw, constraint_sql],
    ]
    outcomes = {
        "begin_attempted": True,
        "begun": True,
        "commit_attempted": True,
        "commit_acknowledged": False,
        "rollback_attempted": False,
        "rollback_acknowledged": False,
        "cleanup_failed": False,
    }
    observed = {
        "faults": [],
        "work": [{"ordinary": 3, "cleanup": []}],
        "outcomes": [outcomes],
        "native_trace": events,
        "native_parameters": [
            {
                "phase": phase,
                "raw_id": actual_raw,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                "outcome": "return",
                "parameter_count": 1 if sql == TRY_LOCK_SQL else 0,
            }
            for phase, kind, actual_raw, sql in events
            if kind == "sql-call"
        ],
        "markers": [["competition.before_physical_commit", raw, len(events)]],
        "command_boundary": None,
        "physical": [],
        "xids": [[raw, 123]],
    }
    return {
        "phase": "held",
        "raw_id": raw,
        "witness": {
            "observation": observed,
            "boundary": "final_proof_before_physical_commit",
            "raw_closed": False,
            "connection_closed": False,
            "work_detached": False,
            "claim_released": False,
            "transaction_status": int(psycopg.pq.TransactionStatus.INTRANS),
            "stages": [["finalize.return", 8], ["classify.return", 8]],
            "backend_pid": 123,
            "database": "owned",
            "role": "owner",
            "try_locks": [
                {
                    "fetched": True,
                    "raw_id": raw,
                    "sql": TRY_LOCK_SQL,
                    "parameters": {"key": MIGRATOR_LOCK},
                    "backend_pid": 123,
                    "database": "owned",
                    "role": "owner",
                    "execute_return_trace_index": 4,
                    "fetch_return_trace_index": 5,
                }
            ],
        },
    }


@pytest.mark.parametrize(
    "sql",
    [
        pytest.param(SQL["postgresql", "constraints.immediate"], id="runtime-sql"),
        pytest.param("SET CONSTRAINTS ALL IMMEDIATE", id="no-outer-whitespace"),
        pytest.param("\t SET CONSTRAINTS ALL IMMEDIATE\r\n", id="outer-whitespace"),
    ],
)
def test_held_constraint_observer_accepts_only_outer_whitespace(sql):
    observer.assert_held(held_message(sql), winner=True)


@pytest.mark.parametrize(
    "sql",
    [
        "SET CONSTRAINTS ALL DEFERRED",
        "SET CONSTRAINTS one_constraint IMMEDIATE",
        "UPDATE migration_progress SET status='complete'",
        "SET CONSTRAINTS ALL IMMEDIATE; DROP TABLE migration_progress",
        "SET CONSTRAINTS ALL IMMEDIATE -- ignored",
        "SET  CONSTRAINTS ALL IMMEDIATE",
        "set constraints all immediate",
    ],
)
def test_held_constraint_observer_rejects_different_statement(sql):
    with pytest.raises(AssertionError):
        observer.assert_held(held_message(sql), winner=True)


@pytest.mark.parametrize(
    "change", ["duplicate", "missing", "wrong-connection", "before-classification", "after-gate"]
)
def test_held_constraint_observer_requires_unique_owned_ordered_return(change):
    message = held_message(SQL["postgresql", "constraints.immediate"])
    witness = message["witness"]
    observed = witness["observation"]
    events = observed["native_trace"]
    if change == "duplicate":
        events.append(list(events[-1]))
        observed["markers"][0][2] = len(events)
    elif change == "missing":
        events.pop()
    elif change == "wrong-connection":
        events[-1][2] = 999
    elif change == "before-classification":
        witness["stages"][1][1] = 10
    else:
        assert change == "after-gate"
        observed["markers"][0][2] = 9
    with pytest.raises(AssertionError):
        observer.assert_held(message, winner=True)
