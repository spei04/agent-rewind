"""Independent pure witnesses for the single restored missing-opening case."""

import hashlib
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import ledger_restore_missing_opening as subject
import pytest
from ledger_restore_authority import typed
from ledger_restore_interruption_raw import TABLES
from sqlalchemy.dialects import postgresql

from agent_rewind.migrations import (
    ledger_catalog,
    ledger_inspection,
    ledger_reader_history,
    ledger_service,
)
from agent_rewind.migrations.schema import MigrationRefused


def literal_state():
    """Small typed raw-state witness; observed after-state is independently listed."""
    opening = {
        "revision": "ar_0007_ledger",
        "phase": "ledger_opening",
        "source_digest": "a" * 64,
        "cursor": {"version": 1, "opening": "literal"},
        "__cursor_text": '{"version": 1, "opening": "literal"}',
        "rows_verified": 3,
        "status": "complete",
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    m0 = {**deepcopy(opening), "phase": "ledger_manifest_" + "0" * 32}
    m1 = {**deepcopy(opening), "phase": "ledger_manifest_" + "1" * 32}
    older = {**deepcopy(opening), "revision": "ar_0003_ownership", "phase": "ownership"}
    tables = {name: {"columns": ("literal",), "rows": [{"literal": name}]} for name in TABLES}
    tables["migration_progress"] = {
        "columns": tuple(k for k in opening if k != "__cursor_text"),
        "rows": [older, m0, m1, opening],
    }
    before = {
        "metadata": {"authority": {"owner": "owner", "acl": None}, "shape": [1, 2]},
        "tables": tables,
    }
    after = deepcopy(before)
    after["tables"]["migration_progress"]["rows"] = [deepcopy(older), deepcopy(m0), deepcopy(m1)]
    mutation = {
        "sql": subject.DELETE_OPENING,
        "parameters": {"revision": "ar_0007_ledger", "phase": "ledger_opening"},
        "identity": ("owner", "database", "origin"),
        "returned": deepcopy(opening),
        "rowcount": 1,
        "committed": True,
    }
    return before, after, mutation


def test_exact_one_opening_delta_and_independent_copies():
    before, after, mutation = literal_state()
    original = deepcopy((before, after, mutation))
    subject.assert_missing_opening_delta(before, after, mutation, "owner", "database")
    assert typed((before, after, mutation)) == typed(original)
    after["tables"]["jobs"]["rows"][0]["literal"] = "changed"
    assert typed(before) == typed(original[0])


@pytest.mark.parametrize(
    "fault",
    [
        "undeleted",
        "extra-delete",
        "different-row",
        "other-table",
        "metadata",
        "columns",
        "manifest-cursor",
        "manifest-time",
        "source-row",
        "source-missing",
        "source-duplicate",
    ],
)
def test_exact_delta_rejects_collateral_or_wrong_source(fault):
    before, after, mutation = literal_state()
    rows = after["tables"]["migration_progress"]["rows"]
    if fault == "undeleted":
        after = deepcopy(before)
    elif fault == "extra-delete":
        rows.pop()
    elif fault == "different-row":
        rows[-1] = deepcopy(mutation["returned"])
    elif fault == "other-table":
        after["tables"]["jobs"]["rows"].clear()
    elif fault == "metadata":
        after["metadata"]["authority"]["acl"] = "changed"
    elif fault == "columns":
        after["tables"]["jobs"]["columns"] = ("changed",)
    elif fault == "manifest-cursor":
        rows[-1]["__cursor_text"] += " "
    elif fault == "manifest-time":
        rows[-1]["updated_at"] = rows[-1]["updated_at"].isoformat()
    elif fault == "source-row":
        before["tables"]["migration_progress"]["rows"][-1]["phase"] = "other"
    elif fault == "source-missing":
        before["tables"]["migration_progress"]["rows"].pop()
    else:
        before["tables"]["migration_progress"]["rows"].append(deepcopy(mutation["returned"]))
    with pytest.raises(AssertionError):
        subject.assert_missing_opening_delta(before, after, mutation, "owner", "database")


@pytest.mark.parametrize(
    "fault",
    [
        "sql",
        "revision",
        "phase",
        "owner",
        "database",
        "replication",
        "count",
        "count-bool",
        "not-committed",
        "cursor",
        "cursor-text",
        "timestamp",
        "row-int-bool",
        "missing-field",
    ],
)
def test_deletion_receipt_is_typed_and_exact(fault):
    before, _, mutation = literal_state()
    if fault == "sql":
        mutation["sql"] += " "
    elif fault in {"revision", "phase"}:
        mutation["parameters"][fault] = "wrong"
    elif fault in {"owner", "database", "replication"}:
        v = list(mutation["identity"])
        v[{"owner": 0, "database": 1, "replication": 2}[fault]] = "wrong"
        mutation["identity"] = tuple(v)
    elif fault == "count":
        mutation["rowcount"] = 0
    elif fault == "count-bool":
        mutation["rowcount"] = True
    elif fault == "not-committed":
        mutation["committed"] = False
    elif fault == "cursor":
        mutation["returned"]["cursor"]["version"] = True
    elif fault == "cursor-text":
        mutation["returned"]["__cursor_text"] += " "
    elif fault == "timestamp":
        mutation["returned"]["updated_at"] = "2026-01-01T00:00:00Z"
    elif fault == "row-int-bool":
        mutation["returned"]["rows_verified"] = True
    else:
        del mutation["returned"]["status"]
    with pytest.raises(AssertionError):
        subject.assert_deletion_receipt(before, mutation, "owner", "database")


def mutation_adapter(monkeypatch, *, fail_exit=False, rowcount=1, returned_count=1):
    before, _, receipt = literal_state()
    calls, exits = [], []

    class Result:
        def __init__(self):
            self.rowcount = rowcount

        def mappings(self):
            return [deepcopy(receipt["returned"]) for _ in range(returned_count)]

    class Connection:
        def exec_driver_sql(self, sql):
            calls.append((sql, None))
            return SimpleNamespace(one=lambda: ("owner", "database", "origin"))

        def execute(self, statement, parameters):
            calls.append((str(statement), deepcopy(parameters)))
            return Result()

    @contextmanager
    def begin():
        yield Connection()
        if fail_exit:
            raise RuntimeError("literal commit failed")
        exits.append("commit")

    fixture = SimpleNamespace(case=SimpleNamespace(engine=SimpleNamespace(begin=begin)))
    pg = {"owner_role": "owner", "owner": SimpleNamespace(url=SimpleNamespace(database="database"))}
    monkeypatch.setattr(subject, "drain", lambda actual: None)
    return before, fixture, pg, calls, exits


def test_mutation_uses_fixed_sql_then_acknowledged_context_exit(monkeypatch):
    before, fixture, pg, calls, exits = mutation_adapter(monkeypatch)
    observed = subject.delete_opening(fixture, pg, before)
    assert exits == ["commit"] and observed["committed"] is True
    assert [sql for sql, _ in calls] == [
        "SET LOCAL statement_timeout='2000ms'",
        "SET LOCAL lock_timeout='1000ms'",
        "SELECT current_user,current_database(),current_setting('session_replication_role')",
        subject.DELETE_OPENING,
    ]
    assert calls[-1][1] == {"revision": "ar_0007_ledger", "phase": "ledger_opening"}


@pytest.mark.parametrize(
    "settings",
    [
        {"fail_exit": True},
        {"rowcount": 0},
        {"rowcount": True},
        {"returned_count": 0},
        {"returned_count": 2},
    ],
)
def test_mutation_never_credits_unacknowledged_or_wrong_return(monkeypatch, settings):
    before, fixture, pg, _, exits = mutation_adapter(monkeypatch, **settings)
    with pytest.raises((AssertionError, RuntimeError)):
        subject.delete_opening(fixture, pg, before)
    assert exits == []


def complete_observation(monkeypatch):
    """Exercise original service and _read with literal, non-database query returns."""
    gate = {
        "candidate_rows": 2,
        "manifest_rows": 2,
        "opening_rows": 0,
        "invalid_rows": 0,
        "native_bytes": 700,
        "utf8_bytes": 700,
        "historical_timestamp_bytes": 0,
        "cursor_bytes": 500,
        "metadata_bytes": 200,
    }
    engine = SimpleNamespace(dialect=postgresql.dialect())
    engine.dialect.server_version_info = (16, 15)
    raw = SimpleNamespace()

    class Watch:
        def __init__(self):
            self.engine, self.works = engine, []
            self.trace = SimpleNamespace(events=[])
            self.parameters = SimpleNamespace(receipts=[])
            self.command_boundary = {}

        @property
        def work(self):
            assert len(self.works) == 1
            return self.works[0]

        def owns(self, actual):
            return bool(self.works) and actual is self.work._raw

    watch = Watch()
    cursor = SimpleNamespace(connection=raw, rowcount=1)

    def native(cursor, statement, parameters, context=None):
        watch.trace.events.extend(
            [
                ("ordinary", "sql-call", id(raw), statement),
                ("ordinary", "sql-return", id(raw), statement),
            ]
        )
        watch.parameters.receipts.append(
            {
                "phase": "ordinary",
                "raw_id": id(raw),
                "sql_sha256": hashlib.sha256(statement.encode()).hexdigest(),
                "parameter_type": "dict",
                "parameter_count": 0,
                "outcome": "return",
            }
        )

    engine.dialect.do_execute = native

    class Connection:
        def execute(self, statement, parameters):
            native_sql = str(statement.compile(dialect=engine.dialect))
            engine.dialect.do_execute(cursor, native_sql, parameters)
            return SimpleNamespace(mappings=lambda: [deepcopy(gate)])

    connection = Connection()
    connection.engine, connection.dialect = engine, engine.dialect
    connection.connection = SimpleNamespace(driver_connection=raw)

    def make_work(timeout):
        assert type(timeout) is int and timeout == 5
        work = SimpleNamespace(_raw=raw, _connection=connection, check=lambda: None)
        watch.works.append(work)
        return work

    @contextmanager
    def transaction(actual_engine, outcome, *, work):
        assert actual_engine is engine and work is watch.work
        yield connection

    def catalog(c):
        ledger_catalog.ledger_executables(c)

    def history(c):
        return ledger_reader_history._read(c, "H60_ledger_progress", watch.work)

    def inspection(c):
        ledger_inspection.inspect_catalog(c)
        return ledger_inspection.read_history(c)

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_checked_manifest", lambda value: value)
        patch.setattr(ledger_service, "LedgerWork", make_work)
        patch.setattr(ledger_service, "LedgerOutcome", SimpleNamespace)
        patch.setattr(ledger_service, "ledger_transaction", transaction)
        patch.setattr(ledger_service, "_inspect_ledger_context", inspection)
        patch.setattr(ledger_inspection, "inspect_catalog", catalog)
        patch.setattr(ledger_catalog, "ledger_executables", lambda c: None)
        patch.setattr(ledger_inspection, "read_history", history)
        with subject.observe_missing_opening(patch, watch) as stages:
            assert watch.works == []
            with pytest.raises(MigrationRefused) as caught:
                stages.invoke(object())
            watch.command_boundary = {"trace_end": len(watch.trace.events)}
    return stages, caught.value, watch


def test_original_h60_refusal_delegates_one_exception_and_no_body(monkeypatch):
    stages, error, _ = complete_observation(monkeypatch)
    result = stages.verify(error)
    assert result["code"] == "ledger_progress_invalid" and result["same_exception"] is True
    assert result["gate"]["receipt"]["opening_rows"] == 0
    assert result["no_h60_body_or_progress_parse"] is True


@pytest.mark.parametrize(
    "fault",
    [
        "gate-missing",
        "gate-duplicate",
        "opening-present",
        "invalid-row",
        "count-bool",
        "gate-parameters",
        "native-sql",
        "native-bind",
        "native-count-bool",
        "native-raw",
        "native-position",
        "native-missing",
        "trace-sql",
        "trace-raw",
        "receipt-hash",
        "receipt-outcome",
        "receipt-count-bool",
        "event-raw",
        "event-position",
        "event-order",
        "new-exception",
    ],
)
def test_whole_refusal_join_rejects_independent_corruption(monkeypatch, fault):
    stages, error, watch = complete_observation(monkeypatch)
    if fault == "gate-missing":
        stages.gates.clear()
    elif fault == "gate-duplicate":
        stages.gates.append(deepcopy(stages.gates[0]))
    elif fault == "opening-present":
        stages.gates[0]["receipt"]["opening_rows"] = 1
    elif fault == "invalid-row":
        stages.gates[0]["receipt"]["invalid_rows"] = 1
    elif fault == "count-bool":
        stages.gates[0]["receipt"]["candidate_rows"] = True
    elif fault == "gate-parameters":
        stages.gates[0]["parameters"] = {"answer": 1}
    elif fault == "native-sql":
        stages.native[0]["sql"] += " "
    elif fault == "native-bind":
        stages.native[0]["parameters"] = {"answer": 1}
    elif fault == "native-count-bool":
        stages.native[0]["rowcount"] = True
    elif fault == "native-raw":
        stages.native[0]["raw_id"] = float(stages.native[0]["raw_id"])
    elif fault == "native-position":
        stages.native[0]["start"] = -1
    elif fault == "native-missing":
        stages.native.clear()
    elif fault == "trace-sql":
        watch.trace.events[0] = ("ordinary", "sql-call", id(watch.work._raw), "SELECT 1")
    elif fault == "trace-raw":
        original = watch.trace.events[0]
        changed = (*original[:2], float(original[2]), original[3])
        assert original == changed and typed(original) != typed(changed)
        watch.trace.events[0] = changed
    elif fault == "receipt-hash":
        watch.parameters.receipts[0]["sql_sha256"] = "0" * 64
    elif fault == "receipt-outcome":
        watch.parameters.receipts[0]["outcome"] = "raise"
    elif fault == "receipt-count-bool":
        watch.parameters.receipts[0]["parameter_count"] = False
    elif fault == "event-raw":
        stages.events[1]["raw_id"] = float(stages.events[1]["raw_id"])
    elif fault == "event-position":
        stages.events[1]["trace_index"] = 0.5
    elif fault == "event-order":
        stages.events[2:4] = reversed(stages.events[2:4])
    else:
        error = MigrationRefused("ledger_progress_invalid")
    with pytest.raises((AssertionError, ValueError)):
        stages.verify(error)


@pytest.mark.parametrize("fault", ["engine", "raw", "connection", "dialect", "work"])
def test_deferred_callback_identity_is_not_weakened(monkeypatch, fault):
    stages, _, watch = complete_observation(monkeypatch)
    connection, work = watch.work._connection, watch.work
    if fault == "engine":
        connection.engine = object()
    elif fault == "raw":
        connection.connection.driver_connection = object()
    elif fault == "connection":
        watch.work._connection = object()
    elif fault == "dialect":
        connection.dialect = SimpleNamespace(name="sqlite")
    else:
        work = object()
    with pytest.raises(AssertionError):
        stages.connection(connection, work)


def test_h60_body_request_is_rejected_before_delegate(monkeypatch):
    stages, _, watch = complete_observation(monkeypatch)
    calls = []
    query = stages.query(lambda *args: calls.append(args))
    with pytest.raises(AssertionError, match="body transfer"):
        query(watch.work._connection, "H60_ledger_progress_body", {})
    assert calls == []


def test_native_module_keeps_existing_restore_opt_in():
    import test_ledger_recovery_restore_missing_opening_postgres as actual
    from test_ledger_recovery_restore_postgres import pytestmark

    assert actual.pytestmark is pytestmark
    assert pytestmark.name == "skipif"
    assert pytestmark.kwargs["reason"] == "Opt-in same-cluster owner-preserving ledger restore"
