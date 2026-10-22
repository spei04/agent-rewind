"""Real whole-adapter elapsed capacity; no frozen clock or raised timeout."""

import json
import time

import pytest
from ledger_capacity_fixture import (
    CURSOR_LIMIT,
    assert_capacity_history,
    capacity_history,
    pad_cursor_bytes,
)
from ledger_reader_fixture import complete_ar6, sqlite_snapshot
from sqlalchemy import event, text

from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations.ledger_compatibility_sql import SQL
from agent_rewind.migrations.ledger_history_sql import SQL as HISTORY_SQL


def observe_capacity(case, record_property):
    wrapper_started = time.monotonic()
    before = sqlite_snapshot(case.path)
    statements = []
    native = []
    projection_bodies = {
        str(text(SQL["sqlite_" + family + "_body"]).compile(dialect=case.engine.dialect))
        for family in ("immutable_accounts", "original_jobs")
    }
    history_body = str(
        text(HISTORY_SQL[("all", "sqlite", "H60_ledger_progress_body")]).compile(
            dialect=case.engine.dialect
        )
    )
    with case.engine.connect() as connection:
        raw = connection.connection.driver_connection
        raw.set_trace_callback(native.append)

        def observe(c, cu, statement, parameters, context, many):
            statements.append((statement, len(parameters)))
            assert c.connection.driver_connection is raw

        event.listen(connection, "before_cursor_execute", observe)
        profile = guard.load_release_profile()
        started = time.monotonic()
        try:
            result = guard.check_schema_compatibility(connection, profile)
        finally:
            elapsed = time.monotonic() - started
            event.remove(connection, "before_cursor_execute", observe)
            raw.set_trace_callback(None)
        assert not raw.in_transaction and not connection.in_transaction()
        assert raw.execute("PRAGMA query_only").fetchone() == (0,)
    assert case.engine.pool.checkedout() == 0
    assert sqlite_snapshot(case.path) == before
    assert "BEGIN" in native and "ROLLBACK" in native
    assert not any(sql.startswith(("INSERT ", "UPDATE ", "DELETE ", "COMMIT")) for sql in native)
    measurements = {
        "result": {"status": result.status, "code": result.code},
        "inspection_call_elapsed_seconds": elapsed,
        "observation_wrapper_elapsed_seconds": time.monotonic() - wrapper_started,
        "inspection_timeout_seconds": guard.INSPECTION_TIMEOUT_SECONDS,
        "statements": len(statements),
        "projection_body_calls": sum(sql in projection_bodies for sql, _ in statements),
        "history_body_calls": sum(sql == history_body for sql, _ in statements),
        "maximum_projection_binds": max(
            (count for sql, count in statements if sql in projection_bodies), default=0
        ),
        "snapshot_unchanged": True,
        "rollback_observed": True,
        "connection_released": True,
    }
    record_property("whole_compatibility_capacity", json.dumps(measurements))
    return result, measurements


@pytest.mark.parametrize("accounts", [319, 4096])
def test_whole_adapter_complete_maximum_history(tmp_path, record_property, accounts):
    case = complete_ar6(tmp_path / "capacity.sqlite", legacy=True)
    try:
        expected = capacity_history(case, accounts=accounts)
        witness = assert_capacity_history(case, expected)
        record_property("capacity_fixture", json.dumps(witness))
        result, measured = observe_capacity(case, record_property)
        assert result == guard.CompatibilityResult("incompatible", "migration_only")
        assert measured["history_body_calls"] == 1
        assert measured["projection_body_calls"] == 5
        assert measured["maximum_projection_binds"] <= 16
        assert measured["inspection_timeout_seconds"] == 2
        assert assert_capacity_history(case, expected) == witness
    finally:
        case.dispose()


@pytest.mark.parametrize("extra", [0, 1])
def test_whole_adapter_aggregate_cursor_byte_boundary(tmp_path, record_property, extra):
    case = complete_ar6(tmp_path / "cursor-capacity.sqlite", legacy=True)
    try:
        expected = capacity_history(case, accounts=319)
        original = assert_capacity_history(case, expected)
        pad_cursor_bytes(case, total=CURSOR_LIMIT + extra)
        witness = assert_capacity_history(case, expected)
        assert witness["cursor_bytes"] == CURSOR_LIMIT + extra
        assert witness["canonical_cursor_bytes"] == original["canonical_cursor_bytes"]
        record_property("capacity_fixture", json.dumps(witness))
        result, measured = observe_capacity(case, record_property)
        assert result == guard.CompatibilityResult(
            "incompatible", "schema_incompatible" if extra else "migration_only"
        )
        assert measured["history_body_calls"] == (0 if extra else 1)
        assert measured["projection_body_calls"] == (0 if extra else 5)
        assert assert_capacity_history(case, expected) == witness
    finally:
        case.dispose()
