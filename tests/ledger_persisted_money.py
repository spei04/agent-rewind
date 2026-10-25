"""Focused witnesses for two invalid persisted-money complete-reader refusals."""

import ast
import inspect
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict

import pytest
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import SOURCE_FIELDS
from ledger_reader_fixture import RowTransferWatch
from ledger_restore_authority import typed
from sqlalchemy.engine import Connection

from agent_rewind import sqlite_ownership
from agent_rewind.migrations import ledger_inspection, ledger_reader_financial, ledger_service
from agent_rewind.migrations.ledger_financial_sql import SQL
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused


def financial_statements(dialect):
    return {
        query.strip(): name
        for (revision, actual, name), query in SQL.items()
        if revision == "ar6" and actual == dialect
    }


def refusal_sites():
    source, first = inspect.getsourcelines(ledger_reader_financial.read_financial)
    (condition,) = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If)
        and ast.unparse(node.test)
        == (
            "receipt['invalid_rows'] or (domain == 'organization' "
            "and receipt['candidate_rows'] != 1)"
        )
    ]
    (call,) = condition.body
    assert ast.unparse(call) == "_refuse()"
    source, refuse_first = inspect.getsourcelines(ledger_reader_financial._refuse)
    (raised,) = ast.parse("".join(source)).body[0].body
    assert ast.unparse(raised) == "raise MigrationRefused('ledger_history_unsupported')"
    return {
        "condition": first + condition.lineno - 1,
        "call": first + call.lineno - 1,
        "raise": refuse_first + raised.lineno - 1,
    }


def assert_money_delta(before, corrupted, source_before, source_corrupted, target, dialect, native):
    value = 0.25 if dialect == "sqlite" else -1
    assert dialect in {"sqlite", "postgresql"}
    assert typed(native) == typed(
        {"value": value, "storage": "real" if dialect == "sqlite" else "bigint"}
    )
    (job,) = [row for row in rows(before, "jobs") if row["id"] == target]
    assert job["payload_version"] == 1 and type(job["reserved"]) is int and job["reserved"] > 0
    expected = deepcopy(before)
    table = expected["tables"]["jobs"]
    column, key = table["columns"].index("reserved"), table["columns"].index("id")
    table["rows"] = tuple(
        tuple(
            value if index == column and row[key] == target else cell
            for index, cell in enumerate(row)
        )
        for row in table["rows"]
    )
    assert typed(corrupted) == typed(expected)
    projected = deepcopy(source_before)
    column = SOURCE_FIELDS["jobs"].index("reserved")
    projected["jobs"] = [
        tuple(
            value if index == column and row[0] == target else cell
            for index, cell in enumerate(row)
        )
        for row in projected["jobs"]
    ]
    assert typed(source_corrupted) == typed(projected)
    assert typed(corrupted) != typed(before)


def reader_identity(watch, connection, work):
    assert work is watch.work and connection is work._connection
    assert connection.engine is watch.engine
    handles = watch.trace.raws if connection.dialect.name == "sqlite" else watch.trace.handles
    (raw,) = handles
    assert work._raw is raw
    return {
        "work_id": id(work),
        "connection_id": id(connection),
        "engine_id": id(watch.engine),
        "raw_id": id(raw),
    }


def inspect_direct(watch, record):
    # Recovery observers wrap these aliases. Explicitly bind their captured
    # objects to the original transaction; no writer/service operation runs.
    work, outcome = ledger_service.LedgerWork(5), ledger_service.LedgerOutcome()
    assert work is watch.work and outcome is watch.outcome
    with ledger_service.ledger_transaction(watch.engine, outcome, work=work) as connection:
        record(
            "reader_transaction",
            {**reader_identity(watch, connection, work), "outcome_id": id(outcome)},
        )
        return ledger_inspection.inspect_ledger_state(connection)


@contextmanager
def observe_financial(watch, monkeypatch, record):
    original_reader = ledger_inspection.read_financial
    assert original_reader is ledger_reader_financial.read_financial
    original_query = ledger_reader_financial._query
    original_execute = Connection.execute
    gate_code = next(
        code
        for code in original_reader.__code__.co_consts
        if getattr(code, "co_name", None) == "gate"
    )
    refuse_code = ledger_reader_financial._refuse.__code__
    receipt = {
        "readers": [],
        "queries": [],
        "statements": [],
        "fetches": [],
        "sites": refusal_sites(),
    }
    statements = financial_statements(watch.engine.dialect.name)

    def execute(connection, statement, *args, **kwargs):
        if watch.works and connection is watch.work._connection:
            sql = str(statement).strip()
            if sql in statements:
                receipt["statements"].append(
                    {"name": statements[sql], **reader_identity(watch, connection, watch.work)}
                )
        return original_execute(connection, statement, *args, **kwargs)

    def query(connection, revision, name):
        entry = {
            "revision": revision,
            "name": name,
            **reader_identity(watch, connection, watch.work),
        }
        receipt["queries"].append(entry)
        result = original_query(connection, revision, name)
        entry["rows"] = deepcopy(result)
        return result

    def reader(connection, revision, work):
        entry = {
            **reader_identity(watch, connection, work),
            "revision": revision,
            "original_inspector_caller": inspect.currentframe().f_back.f_code
            is ledger_inspection._inspect_ledger_context.__code__,
        }
        receipt["readers"].append(entry)
        try:
            result = original_reader(connection, revision, work)
        except BaseException as error:
            entry["error"] = {
                "type": type(error).__name__,
                "code": getattr(error, "code", None),
                "identity": id(error),
            }
            entry["frames"] = []
            cursor = error.__traceback__
            while cursor is not None:
                frame = cursor.tb_frame
                if frame.f_code is gate_code or frame.f_code is refuse_code:
                    item = {
                        "kind": "gate" if frame.f_code is gate_code else "refuse",
                        "line": cursor.tb_lineno,
                    }
                    if frame.f_code is gate_code:
                        item.update(
                            domain=frame.f_locals.get("domain"),
                            prefix=frame.f_locals.get("prefix"),
                            receipt=deepcopy(frame.f_locals.get("receipt")),
                        )
                    entry["frames"].append(item)
                cursor = cursor.tb_next
            raise
        entry["returned"] = True
        return result

    with monkeypatch.context() as patch:
        transfer = RowTransferWatch(patch, {}, statements=statements)
        patch.setattr(Connection, "execute", execute)
        patch.setattr(ledger_reader_financial, "_query", query)
        patch.setattr(ledger_inspection, "read_financial", reader)
        try:
            yield receipt
        finally:
            receipt["fetches"] = deepcopy(transfer.statement_hits)
            record("financial_reader", receipt)


def assert_financial_refusal(receipt, error, identity):
    assert type(error) is MigrationRefused and error.code == "ledger_history_unsupported"
    assert receipt["sites"] == refusal_sites() == {"condition": 239, "call": 240, "raise": 206}
    (reader,) = receipt["readers"]
    assert reader["revision"] == ADMISSION and reader["original_inspector_caller"] is True
    assert "returned" not in reader
    assert reader["error"] == {
        "type": "MigrationRefused",
        "code": "ledger_history_unsupported",
        "identity": id(error),
    }
    assert typed({key: reader[key] for key in identity}) == typed(identity)
    (query,) = receipt["queries"]
    assert query["revision"] == "ar6" and query["name"] == "financial_base_job_gate"
    assert typed({key: query[key] for key in identity}) == typed(identity)
    (gate,) = query["rows"]
    assert set(gate) == {"candidate_rows", "invalid_rows", "native_bytes"}
    assert all(type(value) is int for value in gate.values())
    assert gate["candidate_rows"] == 3 and gate["invalid_rows"] == 1 and gate["native_bytes"] >= 0
    assert typed(reader["frames"]) == typed(
        [
            {
                "kind": "gate",
                "line": 240,
                "domain": "job",
                "prefix": "financial_base_job",
                "receipt": gate,
            },
            {"kind": "refuse", "line": 206},
        ]
    )
    (statement,) = receipt["statements"]
    assert typed(statement) == typed({"name": "financial_base_job_gate", **identity})
    assert receipt["fetches"] and all(
        row["name"] == "financial_base_job_gate"
        and row["method"] in {"fetchone", "fetchmany", "fetchall"}
        and type(row["rows"]) is int
        and row["rows"] >= 0
        for row in receipt["fetches"]
    )
    assert sum(row["rows"] for row in receipt["fetches"]) == 1


def dispose_sqlite_reader(watch, record):
    """Keep original pooled return distinct from caller-owned physical disposal."""
    raw, state = watch.work._raw, watch.work._raw._ownership
    returned = {
        "position": len(watch.trace.events),
        "raw_id": id(raw),
        "raw_closed": state.closed,
        "in_transaction": raw.in_transaction,
        "connection_closed": watch.work._connection.closed,
        "checkedout": watch.engine.pool.checkedout(),
        "borrowed": state.borrowed,
        "lease_present": state.lease is not None,
        "receipt": asdict(sqlite_ownership.cleanup_snapshot(state.receipt)),
        "receipt_clean": sqlite_ownership.cleanup_snapshot(state.receipt).clean,
    }
    record("sqlite_transaction_return", returned)
    assert returned["raw_closed"] is False and returned["in_transaction"] is False
    assert returned["connection_closed"] and returned["checkedout"] == 0
    assert not returned["borrowed"] and not returned["lease_present"]
    assert returned["receipt_clean"]
    assert watch.outcome.confirmed_precommit_rollback and not watch.outcome.cleanup_failed
    assert not any(name == "raw.close.native_ack" for name, _, _ in watch.markers)
    previous = watch.trace.phase
    watch.trace.phase = "caller-dispose"
    try:
        watch.engine.dispose()
    finally:
        watch.trace.phase = previous
    assert state.closed is True
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    close = [row for row in watch.markers if row[0] == "raw.close.native_ack"]
    assert len(close) == 1 and close[0][1] == id(raw) and close[0][2] > returned["position"]
    record(
        "sqlite_caller_disposal",
        {
            "raw_id": id(raw),
            "raw_closed": state.closed,
            "position": len(watch.trace.events),
            "native_close": close[0],
            "attribution": "dedicated caller engine disposal, not transaction close",
        },
    )
