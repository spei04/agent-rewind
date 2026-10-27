"""One missing opening row after an intact restore; no production fault hooks."""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime

from ledger_restore_authority import typed
from ledger_restore_corrupt_raw import CURSOR_TEXT, REVISION
from ledger_restore_interruption_raw import TABLES
from sqlalchemy import text
from sqlalchemy.util import immutabledict
from test_run_projection_postgres import drain

from agent_rewind.migrations import (
    ledger_catalog,
    ledger_inspection,
    ledger_reader_history,
    ledger_service,
)
from agent_rewind.migrations.ledger_history_sql import SQL
from agent_rewind.migrations.schema import MigrationRefused

OPENING = "ledger_opening"
DELETE_OPENING = (
    "DELETE FROM public.migration_progress WHERE revision=:revision AND phase=:phase "
    "RETURNING revision,phase,source_digest,cursor,rows_verified,status,updated_at,"
    "cursor::text AS __cursor_text"
)
GATE = "H60_ledger_progress"
GATE_SQL = SQL[("all", "postgresql", GATE + "_gate")]
_READ = ledger_reader_history._read
_SERVICE = ledger_service._inspect_ledger_reentry
ROW_FIELDS = {
    "revision",
    "phase",
    "source_digest",
    "cursor",
    "rows_verified",
    "status",
    "updated_at",
    CURSOR_TEXT,
}


def opening_row(before):
    assert set(before) == {"metadata", "tables"} and set(before["tables"]) == set(TABLES)
    rows = before["tables"]["migration_progress"]["rows"]
    found = [row for row in rows if row["revision"] == REVISION and row["phase"] == OPENING]
    assert len(found) == 1, "one intact opening row required"
    row = found[0]
    assert set(row) == ROW_FIELDS
    assert type(row["cursor"]) is dict and type(row[CURSOR_TEXT]) is str
    assert typed(json.loads(row[CURSOR_TEXT])) == typed(row["cursor"])
    assert type(row["updated_at"]) is datetime and row["updated_at"].utcoffset() is not None
    assert type(row["rows_verified"]) is int and row["rows_verified"] >= 0
    assert type(row["source_digest"]) is str and len(row["source_digest"]) == 64
    assert row["status"] == "complete"
    return row


def assert_deletion_receipt(before, mutation, owner, database):
    assert set(mutation) == {"sql", "parameters", "identity", "returned", "rowcount", "committed"}
    assert mutation["sql"] == DELETE_OPENING
    assert typed(mutation["parameters"]) == typed({"revision": REVISION, "phase": OPENING})
    assert typed(mutation["identity"]) == typed((owner, database, "origin"))
    assert type(mutation["rowcount"]) is int and mutation["rowcount"] == 1
    assert mutation["committed"] is True
    assert typed(mutation["returned"]) == typed(opening_row(before))


def assert_missing_opening_delta(before, after, mutation, owner, database):
    assert_deletion_receipt(before, mutation, owner, database)
    expected = deepcopy(before)
    row = opening_row(expected)
    expected["tables"]["migration_progress"]["rows"].remove(row)
    assert typed(after) == typed(expected), "unexpected missing-opening mutation delta"


def delete_opening(fixture, pg, before):
    original = deepcopy(opening_row(before))
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            identity = tuple(
                connection.exec_driver_sql(
                    "SELECT current_user,current_database(),"
                    "current_setting('session_replication_role')"
                ).one()
            )
            assert identity == (pg["owner_role"], pg["owner"].url.database, "origin")
            parameters = {"revision": REVISION, "phase": OPENING}
            result = connection.execute(text(DELETE_OPENING), parameters)
            returned = [dict(row) for row in result.mappings()]
            assert type(result.rowcount) is int and result.rowcount == 1
            assert len(returned) == 1 and typed(returned[0]) == typed(original)
        # A successful original context exit acknowledges this separate setup commit.
        mutation = {
            "sql": DELETE_OPENING,
            "parameters": parameters,
            "identity": identity,
            "returned": returned[0],
            "rowcount": result.rowcount,
            "committed": True,
        }
        assert_deletion_receipt(before, mutation, pg["owner_role"], pg["owner"].url.database)
        return mutation
    finally:
        drain(pg)


def assert_missing_gate(receipt):
    assert set(receipt) == {
        "candidate_rows",
        "invalid_rows",
        "native_bytes",
        "utf8_bytes",
        "historical_timestamp_bytes",
        "cursor_bytes",
        "metadata_bytes",
        "opening_rows",
        "manifest_rows",
    }
    assert all(type(value) is int for value in receipt.values())
    assert receipt["candidate_rows"] == receipt["manifest_rows"] == 2
    assert receipt["invalid_rows"] == receipt["opening_rows"] == 0
    assert 1 <= receipt["native_bytes"] <= 16819107
    assert 1 <= receipt["utf8_bytes"] <= 16819107 * 4
    assert 0 <= receipt["historical_timestamp_bytes"] <= 65536
    assert 1 <= receipt["cursor_bytes"] <= 16777216
    assert 1 <= receipt["metadata_bytes"] <= 41891


class MissingOpeningStages:
    def __init__(self, watch):
        self.watch = watch
        self.events, self.refusals, self.gates, self.native = [], [], [], []

    def connection(self, connection, work=None):
        actual = self.watch.work
        assert connection.engine is self.watch.engine
        assert connection is actual._connection
        assert connection.dialect.name == self.watch.engine.dialect.name == "postgresql"
        assert connection.connection.driver_connection is actual._raw
        assert self.watch.owns(actual._raw)
        if work is not None:
            assert work is actual
        return actual

    def record(self, stage, action, connection=None):
        assert len(self.events) < 64
        work = None if connection is None else self.connection(connection)
        self.events.append(
            {
                "stage": stage,
                "action": action,
                "trace_index": len(self.watch.trace.events),
                "raw_id": None if work is None else id(work._raw),
            }
        )

    def wrap(self, delegate, stage):
        def observed(connection, *args, **kwargs):
            self.record(stage, "enter", connection)
            try:
                result = delegate(connection, *args, **kwargs)
            except BaseException as error:
                self.refusals.append((stage, error))
                self.record(stage, "raise", connection)
                raise
            self.record(stage, "return", connection)
            return result

        return observed

    def read(self, delegate):
        observed = self.wrap(delegate, "read")

        def read(connection, name, work, *args, **kwargs):
            if name != GATE:
                return delegate(connection, name, work, *args, **kwargs)
            self.connection(connection, work)
            assert kwargs.get("absent", False) is False
            return observed(connection, name, work, *args, **kwargs)

        return read

    def query(self, delegate):
        def query(connection, name, parameters):
            if name == GATE + "_body":
                raise AssertionError("missing opening reached H60 body transfer")
            if name != GATE + "_gate":
                return delegate(connection, name, parameters)
            self.connection(connection)
            assert type(parameters) is dict and parameters == {}
            self.record("gate", "enter", connection)
            start = len(self.watch.trace.events)
            result = delegate(connection, name, parameters)
            assert type(result) is list and len(result) == 1 and type(result[0]) is dict
            self.gates.append(
                {
                    "name": name,
                    "parameters": deepcopy(parameters),
                    "receipt": deepcopy(result[0]),
                    "start": start,
                    "end": len(self.watch.trace.events),
                }
            )
            self.record("gate", "return", connection)
            return result

        return query

    def invoke(self, manifest):
        self.record("service", "enter")
        try:
            result = _SERVICE(self.watch.engine, manifest)
        except BaseException as error:
            self.refusals.append(("service", error))
            self.record("service", "raise")
            raise
        self.record("service", "return")
        return result

    def verify(self, error):
        assert type(error) is MigrationRefused and error.code == "ledger_progress_invalid"
        assert [stage for stage, _ in self.refusals] == ["read", "history", "inspection", "service"]
        assert all(actual is error for _, actual in self.refusals)
        assert [(r["stage"], r["action"]) for r in self.events] == [
            ("service", "enter"),
            ("inspection", "enter"),
            ("catalog", "enter"),
            ("executables", "enter"),
            ("executables", "return"),
            ("catalog", "return"),
            ("history", "enter"),
            ("read", "enter"),
            ("gate", "enter"),
            ("gate", "return"),
            ("read", "raise"),
            ("history", "raise"),
            ("inspection", "raise"),
            ("service", "raise"),
        ]
        (gate,) = self.gates
        assert_missing_gate(gate["receipt"])
        assert gate["name"] == GATE + "_gate" and gate["parameters"] == {}
        frames = []
        tb = error.__traceback__
        while tb is not None:
            frames.append((tb.tb_frame, tb.tb_lineno))
            tb = tb.tb_next
        selected = [(frame, line) for frame, line in frames if frame.f_code is _READ.__code__]
        assert len(selected) == 1
        frame, line = selected[0]
        assert line == 176 and frame.f_locals["name"] == GATE
        assert frame.f_locals["work"] is self.watch.work
        assert frame.f_locals["connection"] is self.watch.work._connection
        assert typed(frame.f_locals["receipt"]) == typed(gate["receipt"])
        assert frame.f_locals["absent"] is False
        assert any(frame.f_code is _SERVICE.__code__ and line == 300 for frame, line in frames)
        (native,) = self.native
        expected_sql = str(text(GATE_SQL).compile(dialect=self.watch.engine.dialect))
        assert native["sql"] == expected_sql and native["parameters"] == {}
        assert type(native["rowcount"]) is int and native["rowcount"] == 1
        assert type(native["raw_id"]) is int and native["raw_id"] == id(self.watch.work._raw)
        end = self.watch.command_boundary["trace_end"]
        assert type(end) is int and 0 < end <= len(self.watch.trace.events)
        assert all(
            type(row[key]) is int and 0 <= row[key] <= end
            for row in (gate, native)
            for key in ("start", "end")
        )
        assert gate["start"] <= native["start"] < native["end"] <= gate["end"]
        trace = self.watch.trace.events
        assert typed(
            [r for r in trace[native["start"] : native["end"]] if r[1] == "sql-call"]
        ) == typed([("ordinary", "sql-call", id(self.watch.work._raw), expected_sql)])
        receipts = [
            r
            for r in self.watch.parameters.receipts
            if r["sql_sha256"] == hashlib.sha256(expected_sql.encode()).hexdigest()
        ]
        assert len(receipts) == 1
        assert type(receipts[0]["raw_id"]) is int and receipts[0]["raw_id"] == id(
            self.watch.work._raw
        )
        assert receipts[0]["phase"] == "ordinary" and receipts[0]["outcome"] == "return"
        assert type(receipts[0]["parameter_count"]) is int and receipts[0]["parameter_count"] == 0
        for row in self.events:
            assert type(row["trace_index"]) is int and 0 <= row["trace_index"] <= end
            if row["stage"] != "service":
                assert type(row["raw_id"]) is int and row["raw_id"] == id(self.watch.work._raw)
        assert all(
            a["trace_index"] <= b["trace_index"]
            for a, b in zip(self.events, self.events[1:], strict=False)
        )
        return {
            "code": error.code,
            "boundary": "ledger_reader_history._read:169->176",
            "same_exception": True,
            "live_exception_identity": "original traceback and object",
            "gate": deepcopy(gate),
            "native": deepcopy(native),
            "events": deepcopy(self.events),
            "no_h60_body_or_progress_parse": True,
        }


@contextmanager
def observe_missing_opening(patch, watch):
    # Registration precedes work construction; identities are checked only in callbacks.
    assert watch.engine.dialect.name == "postgresql"
    stages = MissingOpeningStages(watch)
    for module, name, stage in (
        (ledger_service, "_inspect_ledger_context", "inspection"),
        (ledger_inspection, "inspect_catalog", "catalog"),
        (ledger_catalog, "ledger_executables", "executables"),
        (ledger_inspection, "read_history", "history"),
    ):
        patch.setattr(module, name, stages.wrap(getattr(module, name), stage))
    patch.setattr(ledger_reader_history, "_read", stages.read(ledger_reader_history._read))
    patch.setattr(ledger_reader_history, "_query", stages.query(ledger_reader_history._query))
    dialect = watch.engine.dialect
    execute = dialect.do_execute
    expected_sql = str(text(GATE_SQL).compile(dialect=dialect))

    def do_execute(cursor, statement, parameters, context=None):
        if not watch.owns(cursor.connection) or statement != expected_sql:
            return execute(cursor, statement, parameters, context)
        assert type(parameters) in (dict, immutabledict) and parameters == {}
        start = len(watch.trace.events)
        result = execute(cursor, statement, parameters, context)
        stages.native.append(
            {
                "sql": statement,
                "parameters": deepcopy(dict(parameters)),
                "raw_id": id(cursor.connection),
                "start": start,
                "end": len(watch.trace.events),
                "rowcount": cursor.rowcount,
            }
        )
        return result

    patch.setattr(dialect, "do_execute", do_execute)

    def forbidden(*args, **kwargs):
        raise AssertionError("missing opening reached body parsing/classification/writer work")

    for module, names in (
        (ledger_reader_history, ("validate_progress_row", "validate_ledger_chain")),
        (
            ledger_service,
            (
                "initialize_ledger",
                "_legacy_inventory",
                "_classify_manifest",
                "_upgrade",
                "_prepare_ledger",
                "_provenance",
                "_write",
                "source_digest",
            ),
        ),
    ):
        for name in names:
            patch.setattr(module, name, forbidden)
    yield stages
