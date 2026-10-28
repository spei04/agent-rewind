"""SQLite window evidence: exact positional bodies, bounded hashes and pooled return."""

import re
import sqlite3
from contextlib import contextmanager
from copy import deepcopy

from ledger_account_window_fixture import equal
from ledger_account_window_observer import identity
from ledger_precommit_boundary_fixture import native_statements
from ledger_provisioning_fixture import WRITE_ACTIONS, assert_no_writes
from ledger_source_boundary import observe_source
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite

from agent_rewind.migrations import ledger_source
from agent_rewind.migrations.schema import TABLES

INSERT_FIELDS = (
    "id",
    "organization_id",
    "scope",
    "scope_id",
    "project_id",
    "job_id",
    "period_start",
    "period_end",
    "limit_microusd",
    "opening_held_microusd",
    "held_microusd",
    "accounted_microusd",
)
INSERT_SQL = (
    "INSERT INTO budget_accounts (\n"
    "  id, organization_id, scope, scope_id, project_id, job_id, period_start, period_end, "
    "limit_microusd, opening_held_microusd, held_microusd, accounted_microusd\n"
    ") VALUES (\n"
    "  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?\n)\n"
)
PROVENANCE_SQL = (
    "SELECT strftime('%Y-%m-%dT%H:%M:%f000Z', 'now') AS initialized_at,\n  NULL AS database_role\n"
)


def expanded(sql, parameters):
    """Expand this bounded fixture's exact qmark inputs, without SQL normalization."""
    assert type(sql) is str and type(parameters) is tuple
    pieces = sql.split("?")
    assert len(pieces) == len(parameters) + 1
    output = pieces[0]
    for value, suffix in zip(parameters, pieces[1:], strict=True):
        assert type(value) in {str, int, type(None)}
        encoded = (
            "NULL"
            if value is None
            else str(value)
            if type(value) is int
            else ("'" + value.replace("'", "''") + "'")
        )
        output += encoded + suffix
    return output


def returned_body(events, start, end, raw, query):
    assert type(start) is type(end) is type(raw) is int and raw > 0
    assert 0 <= start < end <= len(events) and end == start + 3
    equal(
        events[start:end],
        [
            ("c_call", "bootstrap", raw, "execute"),
            ("sql", "bootstrap", raw, query),
            ("c_return", "bootstrap", raw, "execute"),
        ],
    )
    (statement,) = native_statements(events[start:end], raw)
    equal(statement["sql"], [query])
    assert statement["outcome"] == "c_return"


def cursor_close(events, start, end, raw):
    """Cursor cleanup is separate from both body return and later connection disposal."""
    assert type(start) is type(end) is type(raw) is int and raw > 0
    assert 0 <= start < end <= len(events) and end == start + 2
    equal(
        events[start:end],
        [("c_call", "bootstrap", raw, "close"), ("c_return", "bootstrap", raw, "close")],
    )


def guarded_body(execution, body, events, raw):
    start, end = execution["entered_at"], execution["returned_at"]
    auto_closed = body.get("name") == "accounts.insert"
    assert type(start) is type(end) is int and end == start + (8 if auto_closed else 6)
    equal(body["entered_at"], start + 3)
    equal(body["returned_at"], start + 6)
    assert type(body["cursor_id"]) is int and body["cursor_id"] > 0
    assert 0 <= start < end <= len(events)
    setter = events[start + 1][3]
    match = re.fullmatch(r"PRAGMA busy_timeout=([1-9][0-9]*)", setter)
    assert match and int(match[1]) <= 5000
    returned_body(events, start, start + 3, raw, setter)
    returned_body(events, start + 3, start + 6, raw, expanded(body["sql"], body["parameters"]))
    if auto_closed:
        cursor_close(events, start + 6, end, raw)


def assert_native_calls(observations, values, watch):
    calls = observations["native_calls"]
    equal([row["name"] for row in calls], ["accounts.insert", "provenance.observe"])
    expected = tuple(values[key] for key in INSERT_FIELDS)
    assert set(values) == set(INSERT_FIELDS)
    for key in INSERT_FIELDS[-4:]:
        assert type(values[key]) is int
    equal(calls[0]["sql"], INSERT_SQL)
    equal(calls[0]["parameters"], expected)
    equal(calls[1]["sql"], PROVENANCE_SQL)
    equal(calls[1]["parameters"], ())
    for body, count in zip(calls, (1, -1), strict=True):
        equal(body["rowcount"], count)
        (execution,) = [row for row in observations["executions"] if row["name"] == body["name"]]
        equal(execution["rowcount"], count)
        guarded_body(execution, body, watch.trace.events, id(watch.work._raw))
    (provenance,) = observations["provenance"]
    cursor_close(
        watch.trace.events,
        calls[1]["returned_at"],
        provenance["returned_at"],
        id(watch.work._raw),
    )
    equal(watch.work.timeout_seconds, 5)


@contextmanager
def observe_sqlite_source(watch, monkeypatch, record):
    """Capture original hash bodies on the owned dialect; raw setters remain in the trace."""
    assert watch.engine.dialect.name == "sqlite"
    calls = []
    with (
        observe_source(watch, monkeypatch, record, identify=identity) as boundary,
        monkeypatch.context() as patch,
    ):
        delegate = watch.engine.dialect.do_execute

        def execute(cursor, query, parameters, context=None):
            hashes = boundary["hashes"]
            if not hashes or "returned_at" in hashes[-1] or not watch.owns(cursor.connection):
                return delegate(cursor, query, parameters, context)
            call = {
                "entered_at": len(watch.trace.events),
                "phase": watch.trace.phase,
                "raw_id": id(cursor.connection),
                "cursor_id": id(cursor),
                "sql": query,
                "parameter_type": type(parameters).__name__,
                "parameters": deepcopy(parameters),
                "outcome": "pending",
            }
            calls.append(call)
            try:
                result = delegate(cursor, query, parameters, context)
            except BaseException:
                call.update(outcome="raise", returned_at=len(watch.trace.events))
                raise
            call.update(outcome="return", returned_at=len(watch.trace.events))
            return result

        patch.setattr(watch.engine.dialect, "do_execute", execute)
        yield boundary, calls


def source_profile(original):
    """Exact original first-page SQLite query/bind contract; observations come separately."""
    assert set(original) == set(TABLES)
    counts = {name: len(original[name]) for name in TABLES}
    assert all(0 <= n < 4096 for n in counts.values())
    profile, total = [], 0

    def append(name, values):
        sql = (
            ledger_source.SOURCE_PREFLIGHT_SQL[("all", "sqlite", name)]
            if name.startswith(("source_count_", "source_stats_"))
            else ledger_source.SQL[("sqlite", name)]
        )
        compiled = text(sql).compile(dialect=SQLiteDialect_pysqlite())
        profile.append((str(compiled), tuple(values[key] for key in compiled.positiontup)))

    for name in TABLES:
        append("source_count_" + name, {"remaining_rows_plus_one": 1_000_000 - total + 1})
        append("source_stats_" + name, {})
        total += counts[name]
    for name in TABLES:
        append("source_gate_" + name + "_first", {})
        if counts[name]:
            append("source_body_" + name + "_first", {"selected_count": counts[name]})
    return profile


def assert_expiry_span(observations, original, events, anchor):
    (hashed,) = observations["source_hashes"]
    start, end = hashed["entered_at"], hashed["returned_at"]
    raw = anchor["raw_id"]
    profile = source_profile(original)
    calls = hashed["native_calls"]
    assert len(calls) == len(profile)
    equal(end - start, len(profile) * 8)
    equal(hashed["work_after"] - hashed["work_before"], len(profile) * 2)
    source_ctes = set()
    for ordinal, ((query, parameters), call) in enumerate(zip(profile, calls, strict=True)):
        equal(call["phase"], "bootstrap")
        equal(call["raw_id"], raw)
        equal(call["sql"], query)
        equal(call["parameter_type"], "tuple")
        equal(call["parameters"], parameters)
        assert all(type(value) is int for value in call["parameters"])
        equal(call["outcome"], "return")
        query_start = start + ordinal * 8
        execution = {"entered_at": query_start, "returned_at": query_start + 6}
        guarded_body(execution, call, events, raw)
        cursor_close(events, query_start + 6, query_start + 8, raw)
        if query.lstrip().upper().startswith("WITH"):
            source_ctes.add(expanded(query, parameters))
    (insert,) = [row for row in observations["native_calls"] if row["name"] == "accounts.insert"]
    equal(insert["sql"], INSERT_SQL)
    equal(insert["rowcount"], 1)
    (execution,) = [row for row in observations["executions"] if row["name"] == "accounts.insert"]
    guarded_body(execution, insert, events, raw)
    for position, event in enumerate(events):
        if len(event) == 4 and event[0] == "sql" and event[3] in source_ctes:
            equal(event[2], raw)
            assert start <= position < end, "source CTE outside proved original hash span"


def assert_target_actions(actions, *, inserted):
    writes = [row for row in actions if row[0] in WRITE_ACTIONS]
    if not inserted:
        assert_no_writes(actions)
    else:
        equal(writes, [(sqlite3.SQLITE_INSERT, "budget_accounts", None, "main", None)])


def assert_pooled_rollback(watch):
    watch.assert_single_attempt()
    equal(watch.work.timeout_seconds, 5)
    assert watch.outcome.confirmed_precommit_rollback
    assert watch.outcome.rollback_acknowledged and not watch.outcome.commit_attempted
    assert not watch.outcome.cleanup_failed and watch.faults == []
    boundary = watch.command_boundary
    for name in ("connection_closed", "receipt_completed", "receipt_clean"):
        assert boundary[name] is True
    for name in (
        "raw_closed",
        "in_transaction",
        "ownership_closed",
        "borrowed",
        "tainted",
        "native_busy",
        "unknown_callback",
        "lease_present",
    ):
        assert boundary[name] is False
    equal(boundary["checkedout"], 0)
    selected = [
        row
        for row in watch.markers
        if row[0]
        in {
            "rollback.before_native",
            "rollback.native_ack",
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        }
    ]
    equal(
        [row[0] for row in selected],
        [
            "rollback.before_native",
            "rollback.native_ack",
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        ],
    )
    assert [row[2] for row in selected] == sorted(row[2] for row in selected)
    for _, raw, position in selected:
        equal(raw, id(watch.work._raw))
        assert type(position) is int and 0 <= position <= boundary["trace_end"]
    assert watch.work._raw._ownership.closed is True  # Subsequent caller disposal.
    closes = [row for row in watch.markers if row[0] == "raw.close.native_ack"]
    assert closes and all(row[2] >= boundary["trace_end"] for row in closes)
