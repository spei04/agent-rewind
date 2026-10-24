"""Native source-gate evidence for the bounded, genuine S1 provisioning fixture."""

import hashlib
import re
from contextlib import contextmanager
from copy import deepcopy

import psycopg
from ledger_source_boundary import assert_provenance, observe_source
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from agent_rewind.migrations import ledger_source
from agent_rewind.migrations.schema import TABLES, MigrationRefused


def native_identity(watch):
    work = watch.work
    assert work._connection.engine is watch.engine
    assert work._raw is watch.trace.handles[0]
    return {
        "raw_id": id(work._raw),
        "work_id": id(work),
        "engine_id": id(watch.engine),
        "connection_id": id(work._connection),
    }


@contextmanager
def observe_native_source(watch, monkeypatch, record):
    # Observe the unchanged driver delegate only during the original hash call.
    # SQLAlchemy's bind values complement the existing native return receipts.
    calls = []
    with (
        observe_source(watch, monkeypatch, record, identify=native_identity) as receipt,
        monkeypatch.context() as patch,
    ):
        delegate = psycopg.Cursor.execute

        def execute(cursor, query, *args, **kwargs):
            hashing = receipt["hashes"]
            if not hashing or "returned_at" in hashing[-1] or not watch.owns(cursor.connection):
                return delegate(cursor, query, *args, **kwargs)
            parameters = args[0] if args else kwargs.get("params")
            call = {
                "entered_at": len(watch.trace.events),
                "phase": watch.trace.phase,
                "raw_id": id(cursor.connection),
                "sql": query.decode() if isinstance(query, bytes) else str(query),
                "parameter_type": type(parameters).__name__,
                "parameters": deepcopy(parameters),
                "outcome": "pending",
            }
            calls.append(call)
            try:
                result = delegate(cursor, query, *args, **kwargs)
            except BaseException:
                call.update(outcome="raise", returned_at=len(watch.trace.events))
                raise
            call.update(outcome="return", returned_at=len(watch.trace.events))
            return result

        patch.setattr(psycopg.Cursor, "execute", execute)
        try:
            yield receipt, calls
        finally:
            record("source_native_calls", calls)


def source_profile(original):
    """Exact original queries and binds for this fixture's single small page."""
    assert set(original) == set(TABLES)
    counts = {table: len(original[table]) for table in TABLES}
    assert all(0 <= count < 4096 for count in counts.values())
    profile = []
    total = 0

    def append(name, parameters):
        sql = (
            ledger_source.SOURCE_PREFLIGHT_SQL[("all", "postgresql", name)]
            if name.startswith(("source_count_", "source_stats_"))
            else ledger_source.SQL[("postgresql", name)]
        )
        profile.append((str(text(sql).compile(dialect=PGDialect_psycopg())), parameters))

    for table in TABLES:
        append("source_count_" + table, {"remaining_rows_plus_one": 1_000_000 - total + 1})
        append("source_stats_" + table, {})
        total += counts[table]
    for table in TABLES:
        append("source_gate_" + table + "_first", {})
        if counts[table]:
            append("source_body_" + table + "_first", {"selected_count": counts[table]})
    return profile


def assert_hash_span(hashed, original, raw_id, events, parameters, calls):
    start, end = hashed["entered_at"], hashed["returned_at"]
    assert 0 <= start < end <= len(events)
    profile = source_profile(original)
    assert end - start == len(profile) * 6
    assert hashed["work_after"] - hashed["work_before"] == len(profile) * 3
    all_calls = [row for row in events if row[1] == "sql-call"]
    assert len(all_calls) == len(parameters)
    selected = [
        receipt
        for (position, row), receipt in zip(
            [(i, row) for i, row in enumerate(events) if row[1] == "sql-call"],
            parameters,
            strict=True,
        )
        if start <= position < end
    ]
    assert len(selected) == len(calls) == len(profile) * 3
    for index, (query, expected_parameters) in enumerate(profile):
        for offset, expected in enumerate((None, None, query)):
            ordinal = index * 3 + offset
            position = start + ordinal * 2
            phase, kind, raw, sql = events[position]
            assert (phase, kind, raw) == ("ordinary", "sql-call", raw_id)
            assert events[position + 1] == ("ordinary", "sql-return", raw_id, sql)
            if expected is None:
                setting, cap = (
                    ("statement_timeout", 20_000) if offset == 0 else ("lock_timeout", 5_000)
                )
                match = re.fullmatch(r"SET LOCAL " + setting + r" = '([1-9][0-9]*)ms'", sql)
                assert match and int(match[1]) <= cap
                values, parameter_type = None, "NoneType"
            else:
                assert sql == expected
                captured = calls[ordinal]["parameters"]
                assert type(captured) is dict
                assert all(type(value) is int for value in captured.values())
                values, parameter_type = expected_parameters, "dict"
            native = selected[ordinal]
            assert native == {
                "phase": phase,
                "raw_id": raw_id,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                "parameter_type": parameter_type,
                "parameter_count": 0 if values is None else len(values),
                "outcome": "return",
            }
            assert calls[ordinal] == {
                "entered_at": position,
                "returned_at": position + 2,
                "phase": phase,
                "raw_id": raw_id,
                "sql": sql,
                "parameter_type": parameter_type,
                "parameters": values,
                "outcome": "return",
            }


def assert_physical_completion(watch, action):
    assert action in {"rollback", "commit"}
    watch.assert_single_attempt()
    watch.assert_no_writes()
    assert not watch.outcome.cleanup_failed and watch.faults == []
    assert [row["action"] for row in watch.physical] == [action, "close", "close"]
    transaction, close, released = watch.physical
    assert transaction["raw_id"] == close["raw_id"] == released["raw_id"] == id(watch.work._raw)
    assert transaction["closed_before"] is False and transaction["closed_after"] is False
    assert transaction["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
    assert transaction["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)
    assert close["closed_before"] is False and close["closed_after"] is True
    assert close["status_before"] == int(psycopg.pq.TransactionStatus.IDLE)
    assert close["status_after"] is None
    assert released["closed_before"] is True and released["closed_after"] is True
    assert released["status_before"] is None and released["status_after"] is None
    assert (
        transaction["trace_end"]
        < close["trace_end"]
        < released["trace_end"]
        <= watch.command_boundary["trace_end"]
    )
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
    assert [row[0] for row in watch.markers] == names
    assert all(row[1] == id(watch.work._raw) for row in watch.markers)
    positions = [row[2] for row in watch.markers]
    assert positions == sorted(positions)
    assert not watch.command_boundary["engine_poisoned"]
    if action == "rollback":
        assert watch.outcome.confirmed_precommit_rollback
        assert watch.outcome.rollback_acknowledged and not watch.outcome.commit_attempted
    else:
        assert watch.outcome.commit_acknowledged and not watch.outcome.rollback_attempted


def assert_refusal(receipt, original, manifest, expected_source, error, calls, watch):
    assert type(error) is MigrationRefused and error.code == "source_digest_mismatch"
    assert_provenance(receipt, manifest, expected_source, native_identity(watch), id(error))
    (hashed,) = receipt["hashes"]
    assert_hash_span(
        hashed, original, id(watch.work._raw), watch.trace.events, watch.parameters.receipts, calls
    )
    assert_physical_completion(watch, "rollback")
    assert receipt["refusals"][0]["position"] <= watch.markers[0][2]
