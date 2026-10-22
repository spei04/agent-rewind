"""Counted source transport controls on partial original-table SQLite fixtures.

These prove the component under real issued operator work, not complete F3
catalog/history/financial prerequisites or whole-writer capacity.
"""

import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from ledger_operator_fixture import SQLiteTrace
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql, sqlite

from agent_rewind.migrations import inputs, ledger_source
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_source_sql import SQL
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import (
    COLUMNS,
    TABLES,
    MigrationRefused,
    canonical,
    create_baseline,
)


def key(number):
    return f"{number:032x}"


def sample():
    return {
        "api_keys": [
            {
                "id": key(1),
                "hash": None,
                "role": "viewer",
                "name": "ordinary",
                "expires": 1.0,
                "revoked": False,
            }
        ],
        "audit": [
            {
                "id": key(2),
                "created": 1.0,
                "actor": "actor",
                "action": "action",
                "target": "target",
            }
        ],
        "events": [{"run_id": key(3), "step": 1, "artifact": "a" * 64, "hash": "b" * 64}],
        "jobs": [
            {
                "id": key(4),
                "kind": "run",
                "created": 1.0,
                "payload": "a" * 64,
                "status": "succeeded",
                "owner": None,
                "lease_until": None,
                "cancel": False,
                "budget": 245000,
                "reserved": 245000,
                "result": None,
                "error": None,
                "actor": None,
            }
        ],
        "records": [{"id": key(3), "kind": "run", "created": 1.0, "data": '{"b":2,"a":1}'}],
    }


@pytest.fixture
def source_case(tmp_path, monkeypatch, request):
    path = tmp_path / "source.sqlite"
    control = create_engine(f"sqlite:///{path}")
    with control.begin() as connection:
        create_baseline(connection)
    case = SimpleNamespace(control=control, calls=[], fault=None, before=None, last=None)
    trace = SQLiteTrace()
    monkeypatch.setattr(sqlite3, "connect", trace.connect)
    engine = create_ledger_engine(f"sqlite:///{path}")
    case.engine, case.trace, case.node = engine, trace, request.node
    original = ledger_source._query

    def query(connection, name, parameters):
        rows = original(connection, name, parameters)
        case.calls.append((name, parameters.copy(), rows))
        return case.fault(name, rows) if case.fault is not None else rows

    monkeypatch.setattr(ledger_source, "_query", query)
    try:
        yield case
    finally:
        engine.dispose()
        control.dispose()


def insert(case, table, rows):
    if not rows:
        return
    names = list(rows[0])
    # Fixture-owned names only; values stay bound.
    statement = (
        f'INSERT INTO "{table}" ('
        + ",".join('"' + name + '"' for name in names)
        + ") VALUES ("
        + ",".join(":" + name for name in names)
        + ")"
    )
    with case.control.begin() as connection:
        connection.execute(text(statement), rows)


def reference(case):
    with case.control.connect() as connection:
        return inputs.source_digest(connection)


def run(case):
    case.calls.clear()
    work, outcome = LedgerWork(), LedgerOutcome()
    case.last = SimpleNamespace(work=work, outcome=outcome, result=None)
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        if case.before is not None:
            case.before(work)
        start = work.observed_ordinary
        native_start = len(case.trace.events)
        changed = connection.connection.driver_connection.total_changes
        result = ledger_source.source_digest(connection, work)
        assert connection.connection.driver_connection.total_changes == changed
        assert work.observed_ordinary - start == 2 * len(case.calls)
        native = case.trace.sql(native_start)
        assert len(native) == 2 * len(case.calls)
        assert all(sql.startswith("PRAGMA busy_timeout=") for sql in native[::2])
        assert all(sql.lstrip().startswith(("WITH", "SELECT")) for sql in native[1::2])
        case.node.user_properties.append(
            (
                "source_observation",
                json.dumps(
                    {
                        "ordinary_delta": work.observed_ordinary - start,
                        "targets": len(case.calls),
                        "ordered_queries": [name for name, _, _ in case.calls],
                        "native_sql_sha256": [
                            hashlib.sha256(sql.encode()).hexdigest() for sql in native
                        ],
                    },
                    sort_keys=True,
                ),
            )
        )
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert case.engine.pool.checkedout() == 0
    case.last.result = result
    return result


def test_empty_source_has_all_five_headers_and_only_terminal_gates(source_case):
    assert run(source_case) == inputs.empty_source_digest() == reference(source_case)
    assert len(source_case.calls) == 15
    assert not any(name.startswith("source_body_") for name, _, _ in source_case.calls)


def test_original_values_and_thirteen_job_columns_match_unchanged_reader(source_case):
    for table, rows in sample().items():
        insert(source_case, table, rows)
    expected = reference(source_case)
    assert run(source_case) == expected
    with source_case.control.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN payload_version INTEGER DEFAULT 2")
        connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN execution_config_ref TEXT")
        connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN lease_generation BIGINT DEFAULT 7")
        connection.exec_driver_sql(
            "ALTER TABLE jobs ADD COLUMN legacy_reserved_microusd BIGINT DEFAULT 9"
        )
    assert run(source_case) == expected == reference(source_case)
    body = next(rows for name, _, rows in source_case.calls if name == "source_body_jobs_first")
    assert set(body[0]) == {field[0] for field in COLUMNS["jobs"]} | {
        "source_ordinal",
        "native_row_bytes",
        "invalid_row",
    }


@pytest.mark.parametrize("count,pages,gates", [(4095, 1, 1), (4096, 1, 2), (4097, 2, 2)])
def test_page_and_terminal_boundaries_use_actual_native_order(source_case, count, pages, gates):
    rows = [
        {"id": f"a{i:06d}", "created": 1.0, "actor": "", "action": "", "target": ""}
        for i in range(count)
    ]
    rows[0]["id"] = ""
    rows[1]["id"] = "nul\0key"
    rows[2]["id"] = "é" * 1024
    insert(source_case, "audit", rows)
    expected = reference(source_case)
    assert run(source_case) == expected
    selected = [item for item in source_case.calls if "audit" in item[0]]
    bodies = [item for item in selected if item[0].startswith("source_body_")]
    assert len(bodies) == pages
    assert sum(name.startswith("source_gate_") for name, _, _ in selected) == gates
    if gates == 2:
        continuation = next(
            params for name, params, _ in selected if name == "source_gate_audit_next"
        )
        assert continuation == {"last_key": bodies[0][2][-1]["id"]}
    assert sum(len(rows) for _, _, rows in bodies) == count


def test_all_original_streams_reach_continuation_without_hiding_commands(source_case):
    original = sample()
    for table in TABLES:
        rows = []
        for number in range(4097):
            row = original[table][0].copy()
            row["run_id" if table == "events" else "id"] = key(number + 1)
            if table == "events":
                row["step"] = number + 1
            rows.append(row)
        insert(source_case, table, rows)
    expected = reference(source_case)
    assert run(source_case) == expected
    assert len(source_case.calls) == 30
    assert {
        name
        for name, _, _ in source_case.calls
        if name.startswith(("source_gate_", "source_body_"))
    } == {
        f"source_{phase}_{table}_{stage}"
        for table in TABLES
        for phase in ("gate", "body")
        for stage in ("first", "next")
    }
    continuation = next(
        args for name, args, _ in source_case.calls if name == "source_body_events_next"
    )
    assert continuation == {"last_run": key(4096), "last_step": 4096, "selected_count": 1}


@pytest.mark.parametrize("value", [b"binary", float("inf"), float("-inf")])
def test_nonserializable_native_cell_refuses_before_its_body(source_case, value):
    row = sample()["audit"][0] | {"actor" if isinstance(value, bytes) else "created": value}
    insert(source_case, "audit", [row])
    with pytest.raises(MigrationRefused, match="^invalid_source_data$"):
        reference(source_case)
    with pytest.raises(MigrationRefused, match="^invalid_source_data$"):
        run(source_case)
    assert not any(name == "source_body_audit_first" for name, _, _ in source_case.calls)
    assert source_case.last.result is None
    assert source_case.last.outcome.confirmed_precommit_rollback


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '{"amount":1e9999}'])
def test_record_json_duplicate_or_nonfinite_refuses_without_hash_publication(source_case, value):
    insert(source_case, "records", [sample()["records"][0] | {"data": value}])
    for reader in (reference, run):
        with pytest.raises(MigrationRefused, match="^invalid_source_data$"):
            reader(source_case)
    assert source_case.last.result is None


def test_record_blob_cast_and_historical_scalar_text_preserve_reference(source_case):
    insert(source_case, "records", [sample()["records"][0] | {"data": b'{"b":2,"a":1}'}])
    insert(source_case, "audit", [sample()["audit"][0] | {"created": "historical"}])
    assert run(source_case) == reference(source_case)


@pytest.mark.parametrize("extra", [0, 1])
def test_exact_canonical_row_boundary_is_independent_of_native_size(source_case, extra):
    row = sample()["audit"][0] | {"actor": "", "action": "", "target": ""}
    fields = [field[0] for field in COLUMNS["audit"]]
    row["actor"] = "x" * (
        inputs.MAX_ROW_BYTES - len(canonical([row[name] for name in fields])) + extra
    )
    insert(source_case, "audit", [row])
    if extra:
        for reader in (reference, run):
            with pytest.raises(MigrationRefused, match="^source_limit_exceeded$"):
                reader(source_case)
        assert source_case.last.result is None
    else:
        assert run(source_case) == reference(source_case)
    gate = next(rows[0] for name, _, rows in source_case.calls if name == "source_gate_audit_first")
    assert gate["selected_bytes"] < inputs.MAX_ROW_BYTES


def test_native_row_limit_refuses_before_any_source_body(source_case):
    insert(source_case, "audit", [sample()["audit"][0] | {"actor": "x" * inputs.MAX_ROW_BYTES}])
    with pytest.raises(MigrationRefused, match="^source_limit_exceeded$"):
        run(source_case)
    assert not any(name.startswith("source_body_") for name, _, _ in source_case.calls)


def test_byte_prefix_splits_without_skipping_the_second_row(source_case):
    rows = [
        sample()["audit"][0] | {"id": key(number), "actor": "x" * (inputs.MAX_ROW_BYTES // 2)}
        for number in (1, 2)
    ]
    insert(source_case, "audit", rows)
    assert run(source_case) == reference(source_case)
    gates = [rows[0] for name, _, rows in source_case.calls if name.startswith("source_gate_audit")]
    assert [(g["candidate_count"], g["selected_count"]) for g in gates] == [(2, 1), (1, 1)]


@pytest.mark.parametrize(
    "fault",
    ["count", "ordinal", "bool_ordinal", "invalid", "native_sum", "extra", "null_key", "gate_bool"],
)
def test_real_gate_body_receipt_faults_never_publish(source_case, fault):
    insert(source_case, "audit", sample()["audit"])
    expected = reference(source_case)

    def damage(name, rows):
        if name == "source_gate_audit_first" and fault == "gate_bool":
            return [rows[0] | {"selected_count": True}]
        if name != "source_body_audit_first":
            return rows
        row = rows[0].copy()
        if fault == "count":
            return []
        if fault == "ordinal":
            row["source_ordinal"] = 2
        elif fault == "bool_ordinal":
            row["source_ordinal"] = True
        elif fault == "invalid":
            row["invalid_row"] = 1
        elif fault == "native_sum":
            row["native_row_bytes"] -= 1
        elif fault == "extra":
            row["unexpected"] = 1
        elif fault == "null_key":
            row["id"] = None
        return [row]

    source_case.fault = damage
    with pytest.raises(MigrationRefused, match="^invalid_source_data$"):
        run(source_case)
    assert source_case.last.result is None
    assert source_case.last.outcome.confirmed_precommit_rollback
    assert source_case.engine.pool.checkedout() == 0
    source_case.fault = None
    assert run(source_case) == expected


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("candidate_rows", 1_000_001, "source_limit_exceeded"),
        ("candidate_rows", True, "invalid_source_data"),
        ("original_native_bytes", 1_073_741_825, "source_limit_exceeded"),
    ],
)
def test_global_preflight_limit_receipts_refuse_before_body(source_case, field, value, code):
    def damage(name, rows):
        wanted = "source_count_api_keys" if field == "candidate_rows" else "source_stats_api_keys"
        return [rows[0] | {field: value}] if name == wanted else rows

    source_case.fault = damage
    with pytest.raises(MigrationRefused, match="^" + code + "$"):
        run(source_case)
    assert not any(name.startswith("source_body_") for name, _, _ in source_case.calls)


def test_canonical_remaining_budget_counts_rows_without_headers_or_linefeeds():
    row = sample()["audit"][0]
    body = row | {"source_ordinal": 1, "native_row_bytes": 1, "invalid_row": 0}
    fields = [field[0] for field in COLUMNS["audit"]]
    encoded = canonical([row[name] for name in fields])
    gate = {"selected_count": 1, "selected_bytes": 1}
    digest = hashlib.sha256()
    cursor, used = ledger_source._digest_page(
        [body], "audit", gate, len(encoded), digest, LedgerWork()
    )
    assert used == len(encoded) and cursor == (row["id"],)
    assert digest.hexdigest() == hashlib.sha256(encoded + b"\n").hexdigest()
    with pytest.raises(MigrationRefused, match="^source_limit_exceeded$"):
        ledger_source._digest_page(
            [body], "audit", gate, len(encoded) - 1, hashlib.sha256(), LedgerWork()
        )


def test_exhausted_shared_work_refuses_before_first_native_source_query(source_case):
    source_case.before = lambda work: work.reserve_ordinary(2028 - work.observed_ordinary)
    with pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"):
        run(source_case)
    assert source_case.calls == []
    assert source_case.last.work.observed_ordinary == 2028
    assert source_case.last.outcome.confirmed_precommit_rollback
    assert source_case.last.result is None


def test_expiry_between_body_rows_refuses_and_rolls_back(source_case, monkeypatch):
    insert(source_case, "audit", sample()["audit"])
    original = ledger_source.canonical
    reached = []

    def expired(value):
        encoded = original(value)
        if len(value) == 5 and value[0] == key(2):
            reached.append(True)
            source_case.last.work._deadline = 0
        return encoded

    monkeypatch.setattr(ledger_source, "canonical", expired)
    with pytest.raises(MigrationRefused, match="^migration_busy$"):
        run(source_case)
    assert reached == [True]
    assert source_case.last.result is None
    assert source_case.last.outcome.confirmed_precommit_rollback


def test_source_requires_the_callers_attached_work():
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        ledger_source.source_digest(object(), LedgerWork())


@pytest.mark.parametrize(
    "kind,compiler", [("sqlite", sqlite.dialect), ("postgresql", postgresql.dialect)]
)
def test_fixed_statement_parameters_remain_within_reviewed_transport_limit(kind, compiler):
    selected = [(name, sql) for (dialect, name), sql in SQL.items() if dialect == kind]
    assert len(selected) == 20
    for name, sql in selected:
        compiled = text(sql).compile(dialect=compiler())
        expected = (
            ({"last_run", "last_step"} if "_events_" in name else {"last_key"})
            if name.endswith("_next")
            else set()
        )
        if name.startswith("source_body_"):
            expected.add("selected_count")
        assert set(compiled.params) == expected
        assert len(compiled.positiontup or compiled.params) <= 4
        assert len(compiled.params) <= 3
