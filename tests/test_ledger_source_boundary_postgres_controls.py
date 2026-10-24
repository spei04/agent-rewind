"""Pure rejection controls for the native source witness; no database calls."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_source_boundary_postgres import (
    assert_hash_span,
    assert_physical_completion,
    native_identity,
    source_profile,
)

from agent_rewind.migrations.schema import TABLES


def witness():
    original = {table: [None] for table in TABLES}
    events, parameters, calls = [], [], []
    for query, values in source_profile(original):
        for sql, bound in (
            ("SET LOCAL statement_timeout = '20000ms'", None),
            ("SET LOCAL lock_timeout = '5000ms'", None),
            (query, values),
        ):
            position = len(events)
            events.extend(
                [
                    ("ordinary", "sql-call", 11, sql),
                    ("ordinary", "sql-return", 11, sql),
                ]
            )
            parameter_type = type(bound).__name__
            parameters.append(
                {
                    "phase": "ordinary",
                    "raw_id": 11,
                    "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                    "parameter_type": parameter_type,
                    "parameter_count": 0 if bound is None else len(bound),
                    "outcome": "return",
                }
            )
            calls.append(
                {
                    "entered_at": position,
                    "returned_at": position + 2,
                    "phase": "ordinary",
                    "raw_id": 11,
                    "sql": sql,
                    "parameter_type": parameter_type,
                    "parameters": bound,
                    "outcome": "return",
                }
            )
    hashed = {
        "entered_at": 0,
        "returned_at": len(events),
        "work_before": 10,
        "work_after": 10 + len(calls),
    }
    return hashed, original, 11, events, parameters, calls


def test_complete_native_source_query_and_parameter_witness():
    assert_hash_span(*witness())


@pytest.mark.parametrize(
    "fault",
    [
        "missing-return",
        "native-error",
        "foreign-raw",
        "wrong-phase",
        "wrong-setter",
        "statement-cap",
        "lock-cap",
        "zero-timeout",
        "work-undercount",
        "extra-statement",
        "parameter-receipt-missing",
        "parameter-receipt-raised",
        "parameter-receipt-count",
        "driver-values-missing",
        "driver-values-raised",
        "driver-return-incomplete",
        "count-parameter-changed",
        "body-parameter-changed",
        "side-effect-select",
        "write-cte",
    ],
)
def test_incomplete_or_different_native_hash_is_rejected(fault):
    hashed, original, raw, events, parameters, calls = deepcopy(witness())
    if fault == "missing-return":
        events.pop()
    elif fault == "native-error":
        events[-1] = ("ordinary", "sql-raise", raw, events[-1][3])
    elif fault in {"foreign-raw", "wrong-phase"}:
        phase = "cleanup" if fault == "wrong-phase" else "ordinary"
        identity = 99 if fault == "foreign-raw" else raw
        events[4] = (phase, "sql-call", identity, events[4][3])
    elif fault == "work-undercount":
        hashed["work_after"] -= 1
    elif fault == "extra-statement":
        events.extend(events[-2:])
        hashed["returned_at"] += 2
    elif fault == "parameter-receipt-missing":
        parameters.pop()
    elif fault == "parameter-receipt-raised":
        parameters[2]["outcome"] = "raise"
    elif fault == "parameter-receipt-count":
        parameters[2]["parameter_count"] = 0
    elif fault == "driver-values-missing":
        calls.pop()
    elif fault == "driver-values-raised":
        calls[2]["outcome"] = "raise"
    elif fault == "driver-return-incomplete":
        calls[2]["returned_at"] -= 1
    elif fault in {"count-parameter-changed", "body-parameter-changed"}:
        key = "remaining_rows_plus_one" if fault.startswith("count-") else "selected_count"
        selected = next(row for row in calls if row["parameters"] and key in row["parameters"])
        selected["parameters"][key] += 1
    else:
        ordinal, sql = {
            "wrong-setter": (0, "SET LOCAL lock_timeout = '5000ms'"),
            "statement-cap": (0, "SET LOCAL statement_timeout = '20001ms'"),
            "lock-cap": (1, "SET LOCAL lock_timeout = '5001ms'"),
            "zero-timeout": (0, "SET LOCAL statement_timeout = '0ms'"),
            "side-effect-select": (2, "SELECT pg_advisory_lock(1)"),
            "write-cte": (
                2,
                "WITH changed AS (DELETE FROM jobs RETURNING id) SELECT * FROM changed",
            ),
        }[fault]
        # Keep the three observers mutually consistent: the original query
        # contract itself must reject an unreviewed command.
        for index, kind in enumerate(("sql-call", "sql-return")):
            events[ordinal * 2 + index] = ("ordinary", kind, raw, sql)
        calls[ordinal]["sql"] = sql
        parameters[ordinal]["sql_sha256"] = hashlib.sha256(sql.encode()).hexdigest()
    with pytest.raises(AssertionError):
        assert_hash_span(hashed, original, raw, events, parameters, calls)


def test_native_identity_uses_the_actual_handle_collection():
    engine, raw = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine))
    watch = SimpleNamespace(engine=engine, work=work, trace=SimpleNamespace(handles=[raw]))
    assert native_identity(watch) == {
        "raw_id": id(raw),
        "work_id": id(work),
        "engine_id": id(engine),
        "connection_id": id(work._connection),
    }


@pytest.mark.parametrize("fault", ["foreign-handle", "foreign-engine"])
def test_native_identity_rejects_foreign_ownership(fault):
    engine, raw = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine))
    watch = SimpleNamespace(engine=engine, work=work, trace=SimpleNamespace(handles=[raw]))
    if fault == "foreign-handle":
        watch.trace.handles[0] = object()
    else:
        work._connection.engine = object()
    with pytest.raises(AssertionError):
        native_identity(watch)


def physical_witness(action):
    raw = object()
    seen = []
    names = [
        action + ".before_native",
        action + ".native_ack",
        "connection.close.before",
        "raw.close.before_native",
        "raw.close.native_ack",
        "connection.close.return",
        "raw.close.before_native",
        "raw.close.native_ack",
        "command.exit",
    ]
    physical = [
        {
            "action": action,
            "raw_id": id(raw),
            "closed_before": False,
            "closed_after": False,
            "status_before": 2,
            "status_after": 0,
            "trace_end": 11,
        },
        {
            "action": "close",
            "raw_id": id(raw),
            "closed_before": False,
            "closed_after": True,
            "status_before": 0,
            "status_after": None,
            "trace_end": 14,
        },
        {
            "action": "close",
            "raw_id": id(raw),
            "closed_before": True,
            "closed_after": True,
            "status_before": None,
            "status_after": None,
            "trace_end": 17,
        },
    ]
    watch = SimpleNamespace(
        work=SimpleNamespace(_raw=raw),
        outcome=SimpleNamespace(
            cleanup_failed=False,
            confirmed_precommit_rollback=action == "rollback",
            rollback_acknowledged=action == "rollback",
            rollback_attempted=action == "rollback",
            commit_attempted=action == "commit",
            commit_acknowledged=action == "commit",
        ),
        faults=[],
        physical=physical,
        markers=[(name, id(raw), 10 + i) for i, name in enumerate(names)],
        command_boundary={"trace_end": 18, "engine_poisoned": False},
        assert_single_attempt=lambda: seen.append("single_attempt"),
        assert_no_writes=lambda: seen.append("no_writes"),
    )
    return watch, seen


@pytest.mark.parametrize("action", ["rollback", "commit"])
def test_native_physical_profile_keeps_first_close_and_later_registry_release(action):
    watch, seen = physical_witness(action)
    assert_physical_completion(watch, action)
    assert seen == ["single_attempt", "no_writes"]


@pytest.mark.parametrize(
    "fault", ["native-error-state", "already-closed-first", "live-release", "late-close"]
)
def test_physical_profile_rejects_false_or_late_close_evidence(fault):
    watch, _ = physical_witness("rollback")
    if fault == "native-error-state":
        watch.physical[0]["status_before"] = 3
    elif fault == "already-closed-first":
        watch.physical[1]["closed_before"] = True
    elif fault == "live-release":
        watch.physical[2]["closed_before"] = False
    else:
        watch.physical[2]["trace_end"] = watch.command_boundary["trace_end"] + 1
    with pytest.raises(AssertionError):
        assert_physical_completion(watch, "rollback")
