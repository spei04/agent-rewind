"""Pure SQLite adapters; these controls never open a database."""

import sqlite3
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_account_window_fixture import CASES, assert_expiry_source, assert_refusal
from ledger_account_window_observer import identity, observe_window
from ledger_account_window_sqlite import (
    INSERT_FIELDS,
    INSERT_SQL,
    PROVENANCE_SQL,
    assert_pooled_rollback,
    assert_target_actions,
    cursor_close,
    expanded,
    guarded_body,
    observe_sqlite_source,
)
from ledger_cohort_observer import observe_cohort
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import digest, source_fingerprint
from ledger_source_boundary import source_site
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.engine import Connection
from sqlalchemy.engine.cursor import CursorFetchStrategy, CursorResult
from sqlalchemy.engine.default import DefaultExecutionContext
from test_ledger_account_window_controls import OBSERVED, ORG, PROJECT, Result, independent_state

from agent_rewind.migrations import ledger_service, ledger_source
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.ledger_writer_sql import SQL
from agent_rewind.migrations.schema import COLUMNS, LEDGER, MigrationRefused


def inert_sqlite(results):
    """Original work guard and installed do_execute, with literal inert native responses."""
    dialect = SQLiteDialect_pysqlite()
    engine, raw = SimpleNamespace(dialect=dialect), SimpleNamespace()
    connection = SimpleNamespace(
        engine=engine, dialect=dialect, invalidated=False, closed=False, _echo=False
    )
    connection._safe_close_cursor = lambda cursor: Connection._safe_close_cursor(connection, cursor)
    work = LedgerWork()
    work._connection, work._raw, work._attached = connection, raw, True
    events, executed = [], []
    watch = SimpleNamespace(
        engine=engine,
        work=work,
        trace=SimpleNamespace(raws=[raw], events=events, phase="bootstrap"),
        owns=lambda candidate: candidate is raw,
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            rollback_acknowledged=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
        markers=[],
    )

    class Cursor:
        connection = raw

        def __init__(self, count=-1):
            self.rowcount = count

        def execute(self, query, parameters=()):
            # Control-side rendering is independent of the adapter expander.
            observed = query
            for value in parameters:
                if value is None:
                    bound = "NULL"
                elif type(value) is int:
                    bound = str(value)
                else:
                    assert type(value) is str
                    bound = "'" + value.replace("'", "''") + "'"
                observed = observed.replace("?", bound, 1)
            events.extend(
                [
                    ("c_call", "bootstrap", id(raw), "execute"),
                    ("sql", "bootstrap", id(raw), observed),
                    ("c_return", "bootstrap", id(raw), "execute"),
                ]
            )
            return self

        def close(self):
            events.extend(
                [
                    ("c_call", "bootstrap", id(raw), "close"),
                    ("c_return", "bootstrap", id(raw), "close"),
                ]
            )

    class ConsumedResult(Result):
        def __init__(self, rows, count, native_result):
            super().__init__(rows, count)
            self.native_result = native_result

        def __exit__(self, *args):
            self.native_result.close()

        def all(self):
            values = super().all()
            self.native_result._soft_close()
            return values

        def __iter__(self):
            yield from super().__iter__()
            self.native_result._soft_close()

    raw.execute = lambda query: Cursor().execute(query)
    statements = {sql: name for (backend, name), sql in SQL.items() if backend == "sqlite"}
    statements.update(
        {
            sql: name
            for (kind, backend, name), sql in ledger_source.SOURCE_PREFLIGHT_SQL.items()
            if kind == "all" and backend == "sqlite"
        }
    )
    statements.update(
        {sql: name for (backend, name), sql in ledger_source.SQL.items() if backend == "sqlite"}
    )

    def execute(statement, parameters):
        name = statements[statement.text]
        result, count = results(name)
        compiled = statement.compile(dialect=dialect)
        query = str(compiled)
        positional = tuple(parameters[key] for key in compiled.positiontup)
        cursor = Cursor(count)
        entry = {
            **identity(watch),
            "name": name,
            "entered_at": len(events),
            "values": deepcopy(parameters),
        }
        work._before(connection, cursor, query, positional, None, False)
        start = len(events)
        dialect.do_execute(cursor, query, positional)
        end = len(events)
        work._after()
        context = SimpleNamespace(
            dialect=dialect,
            cursor=cursor,
            root_connection=connection,
            engine=engine,
            compiled=None,
            cursor_fetch_strategy=CursorFetchStrategy(),
            isinsert=False,
            _is_server_side=False,
            _num_sentinel_cols=0,
            _is_implicit_returning=False,
            _rowcount=None,
            isupdate=False,
            isdelete=False,
        )
        cursor.description = None
        if name == "accounts.insert":
            # Installed SQLAlchemy closes a no-row text result before execute returns.
            native_result = DefaultExecutionContext._setup_dml_or_text_result(context)
        else:
            # Value iteration below owns SELECT exhaustion; no database is opened.
            native_result = CursorResult(context, CursorFetchStrategy(), None)
        entry.update(returned_at=len(events), rowcount=count)
        executed.append(
            (
                entry,
                {
                    **identity(watch),
                    "name": name,
                    "sql": query,
                    "parameters": positional,
                    "rowcount": count,
                    "entered_at": start,
                    "returned_at": end,
                    "cursor_id": id(cursor),
                },
            )
        )
        return ConsumedResult(result, count, native_result)

    connection.execute = execute
    return watch, connection, executed


def delegated(case, monkeypatch):
    first, requested, before, jobs, scopes, accounts, target = independent_state(case)
    fixtures = {
        "projects.gate": (
            [{"candidate_rows": 1, "invalid_rows": 0, "native_bytes": 64, "max_row_bytes": 64}],
            -1,
        ),
        "projects.body": ([{"id": PROJECT, "organization_id": ORG}], -1),
        "accounts.insert": ([], 1),
        "provenance.observe": ([{"initialized_at": OBSERVED, "database_role": None}], -1),
    }
    watch, connection, _ = inert_sqlite(fixtures.__getitem__)
    prior = {"revision": LEDGER, "status": "ready", "manifest_count": 1, "account_count": 3}
    state = SimpleNamespace(
        **prior,
        installation_key=first["installation_key"],
        head=SimpleNamespace(manifest_digest=digest(first)),
        model_dump=lambda **kwargs: deepcopy(prior),
    )
    context = SimpleNamespace(
        state=state,
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=ORG),
            manifests=(SimpleNamespace(manifest=validate_ledger_manifest(first)),),
            opening=object(),
            adoption={"installed_schema_fingerprint": "c" * 64},
        ),
        financial={"job": jobs, "scope": scopes, "account": accounts},
    )
    with (
        observe_projects(watch, monkeypatch, lambda *_: None) as projects,
        observe_cohort(watch, monkeypatch, lambda *_: None) as (entries, stages),
        observe_window(watch, monkeypatch, lambda *_: None, backend="sqlite") as observations,
        pytest.raises(MigrationRefused) as failure,
    ):
        model = validate_ledger_manifest(requested)
        assert ledger_service._classify_manifest(context, model, watch.work) is None
        ledger_service._projects(connection, model, ORG, watch.work)
        prepared = ledger_service._prepare_ledger(context, model, watch.work)
        values = {
            **requested["accounts"][0],
            "opening_held_microusd": 0,
            "held_microusd": 0,
            "accounted_microusd": 0,
        }
        ledger_service._write(connection, "accounts.insert", values)
        observed, role, uid = ledger_service._provenance(connection)
        ledger_service._ledger_cursors(connection, model, prepared, observed, role, uid, watch.work)
    watch.markers = [
        (name, id(watch.work._raw), len(watch.trace.events))
        for name in (
            "rollback.before_native",
            "rollback.native_ack",
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        )
    ]
    return SimpleNamespace(
        first=first,
        requested=requested,
        prior=prior,
        before=before,
        observations=observations,
        projects=projects,
        entries=entries,
        stages=stages,
        error=failure.value,
        watch=watch,
        target=target,
    )


def accept(value, case):
    assert_refusal(
        value.first,
        value.requested,
        value.prior,
        value.observations,
        value.projects,
        value.entries,
        value.stages,
        value.error,
        value.watch,
        case,
        backend="sqlite",
    )


@pytest.mark.parametrize("case", CASES)
def test_sqlite_original_refusal_preserves_exception_and_native_body(case, monkeypatch):
    value = delegated(case, monkeypatch)
    accept(value, case)
    calls = value.observations["native_calls"]
    assert len(calls) == (2 if case == CASES[2] else 0)
    if calls:
        assert [call["rowcount"] for call in calls] == [1, -1]
        assert all(type(call["parameters"]) is tuple for call in calls)
        assert calls[0]["sql"].endswith("\n") and "?" in calls[0]["sql"]
        for call in calls:
            assert call["returned_at"] - call["entered_at"] == 3


@pytest.mark.parametrize(
    "fault",
    [
        "postgres_sql",
        "missing_newline",
        "mapping_binds",
        "swapped_binds",
        "float_money",
        "bool_money",
        "raw_float",
        "cursor_float",
        "missing_return",
        "wrong_body_order",
        "attempted_insert",
        "wrong_provenance_count",
        "provenance_role",
        "provenance_params",
        "missing_setter",
        "over_cap",
        "zero_setter",
        "wrong_setter",
        "guard_span",
        "wrong_exception",
        "wrong_original_frame",
    ],
)
def test_sqlite_expiry_rejects_inexact_native_body_or_refusal(fault, monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    calls = value.observations["native_calls"]
    insert, provenance = calls
    events = value.watch.trace.events
    if fault == "postgres_sql":
        insert["sql"] = insert["sql"].replace("?", "%(id)s", 1)
    elif fault == "missing_newline":
        insert["sql"] = insert["sql"][:-1]
    elif fault == "mapping_binds":
        insert["parameters"] = dict(zip(INSERT_FIELDS, insert["parameters"], strict=True))
    elif fault == "swapped_binds":
        p = list(insert["parameters"])
        p[0], p[1] = p[1], p[0]
        insert["parameters"] = tuple(p)
    elif fault in {"float_money", "bool_money"}:
        p = list(insert["parameters"])
        p[-1] = 0.0 if fault == "float_money" else False
        insert["parameters"] = tuple(p)
    elif fault == "raw_float":
        insert["raw_id"] = float(insert["raw_id"])
    elif fault == "cursor_float":
        insert["cursor_id"] = float(insert["cursor_id"])
    elif fault == "missing_return":
        position = insert["returned_at"] - 1
        events[position] = ("c_exception", *events[position][1:])
    elif fault == "wrong_body_order":
        calls.reverse()
    elif fault == "attempted_insert":
        insert["rowcount"] = 0
    elif fault == "wrong_provenance_count":
        provenance["rowcount"] = 1
    elif fault == "provenance_role":
        value.observations["provenance"][0]["database_role"] = "postgres-owner"
    elif fault == "provenance_params":
        provenance["parameters"] = {}
    elif fault in {"missing_setter", "over_cap", "zero_setter", "wrong_setter"}:
        position = insert["entered_at"] - 2
        query = {
            "missing_setter": "SELECT 1",
            "over_cap": "PRAGMA busy_timeout=5001",
            "zero_setter": "PRAGMA busy_timeout=0",
            "wrong_setter": "PRAGMA cache_size=5000",
        }[fault]
        events[position] = (*events[position][:3], query)
    elif fault == "guard_span":
        execution = next(
            x for x in value.observations["executions"] if x["name"] == "accounts.insert"
        )
        execution["entered_at"] += 1
    elif fault == "wrong_exception":
        value.error = MigrationRefused("invalid_ledger_manifest")
    elif fault == "wrong_original_frame":
        value.observations["cursors"][0]["original_frames"][0]["line"] += 1
    with pytest.raises((AssertionError, ValueError, TypeError)):
        accept(value, CASES[2])


def test_sqlite_literal_and_position_order_match_original_compiler():
    from sqlalchemy import BigInteger, String, bindparam

    from agent_rewind.migrations.ledger_writer_sql import PARAMETER_TYPES

    statement = text(SQL[("sqlite", "accounts.insert")]).bindparams(
        *[
            bindparam(key, type_=BigInteger() if kind == "BigInteger" else String())
            for key, kind in PARAMETER_TYPES[("sqlite", "accounts.insert")].items()
        ]
    )
    compiled = statement.compile(dialect=SQLiteDialect_pysqlite())
    assert str(compiled) == INSERT_SQL
    assert tuple(compiled.positiontup) == INSERT_FIELDS
    assert (
        str(text(SQL[("sqlite", "provenance.observe")]).compile(dialect=SQLiteDialect_pysqlite()))
        == PROVENANCE_SQL
    )


def test_sqlite_expansion_retains_quotes_nulls_and_exact_whitespace():
    assert expanded("SELECT ?, ?, ?\n", ("a'b", None, 7)) == "SELECT 'a''b', NULL, 7\n"
    with pytest.raises(AssertionError):
        expanded("SELECT ?", (True,))
    with pytest.raises(AssertionError):
        expanded("SELECT ?", (1.0,))


def retained_cursor_witness():
    # Literal slices from retained SQLite M1, with only raw identity rebased.
    # Source query3500:3508; INSERT3660:3668; provenance3668:3676.
    # These observations are independent of the source profile and SQL expander.
    events = [
        ("c_call", "bootstrap", 77, "execute"),
        ("sql", "bootstrap", 77, "PRAGMA busy_timeout=5000"),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "execute"),
        (
            "sql",
            "bootstrap",
            77,
            (
                'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "api_k'
                'eys" ORDER BY "id" LIMIT 1000001) AS bounded\n'
            ),
        ),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "close"),
        ("c_return", "bootstrap", 77, "close"),
        ("c_call", "bootstrap", 77, "execute"),
        ("sql", "bootstrap", 77, "PRAGMA busy_timeout=5000"),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "execute"),
        (
            "sql",
            "bootstrap",
            77,
            (
                "INSERT INTO budget_accounts (\n  id, organization_id, scope, "
                "scope_id, project_id, job_id, period_start, period_end, limi"
                "t_microusd, opening_held_microusd, held_microusd, accounted_"
                "microusd\n) VALUES (\n  '00000000000000000000000000001f41', '8"
                "8888888888888888888888888888888', 'job', 'a394e311ebd24a47a5"
                "4f67a12a48a6ef', '99999999999999999999999999999999', 'a394e3"
                "11ebd24a47a54f67a12a48a6ef', '2000-01-01T00:00:00.000000Z', "
                "'2100-01-01T00:00:00.000000Z', 1, 0, 0, 0\n)\n"
            ),
        ),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "close"),
        ("c_return", "bootstrap", 77, "close"),
        ("c_call", "bootstrap", 77, "execute"),
        ("sql", "bootstrap", 77, "PRAGMA busy_timeout=5000"),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "execute"),
        (
            "sql",
            "bootstrap",
            77,
            (
                "SELECT strftime('%Y-%m-%dT%H:%M:%f000Z', 'now') AS initializ"
                "ed_at,\n  NULL AS database_role\n"
            ),
        ),
        ("c_return", "bootstrap", 77, "execute"),
        ("c_call", "bootstrap", 77, "close"),
        ("c_return", "bootstrap", 77, "close"),
    ]
    bodies = [
        {
            "name": "source_count_api_keys",
            "sql": (
                'SELECT count(*) AS candidate_rows FROM (SELECT 1 FROM "api_k'
                'eys" ORDER BY "id" LIMIT ?) AS bounded\n'
            ),
            "parameters": (1000001,),
            "cursor_id": 91,
            "entered_at": 3,
            "returned_at": 6,
        },
        {
            "name": "accounts.insert",
            "sql": INSERT_SQL,
            "parameters": (
                "00000000000000000000000000001f41",
                "88888888888888888888888888888888",
                "job",
                "a394e311ebd24a47a54f67a12a48a6ef",
                "99999999999999999999999999999999",
                "a394e311ebd24a47a54f67a12a48a6ef",
                "2000-01-01T00:00:00.000000Z",
                "2100-01-01T00:00:00.000000Z",
                1,
                0,
                0,
                0,
            ),
            "cursor_id": 92,
            "entered_at": 11,
            "returned_at": 14,
        },
        {
            "name": "provenance.observe",
            "sql": PROVENANCE_SQL,
            "parameters": (),
            "cursor_id": 93,
            "entered_at": 19,
            "returned_at": 22,
        },
    ]
    executions = [
        {"entered_at": 0, "returned_at": 6},
        {"entered_at": 8, "returned_at": 16},
        {"entered_at": 16, "returned_at": 22},
    ]
    return events, bodies, executions


def test_sqlite_retained_cursor_returns_distinguish_body_execute_and_consumption():
    events, bodies, executions = retained_cursor_witness()
    for body, execution in zip(bodies, executions, strict=True):
        guarded_body(execution, body, events, 77)
    cursor_close(events, 6, 8, 77)
    cursor_close(events, 22, 24, 77)
    assert [x["returned_at"] - x["entered_at"] for x in bodies] == [3, 3, 3]
    assert [x["returned_at"] - x["entered_at"] for x in executions] == [6, 8, 6]


@pytest.mark.parametrize("phase", ["source", "insert", "provenance"])
@pytest.mark.parametrize("fault", ["missing_return", "wrong_raw", "wrong_phase", "extra_close"])
def test_sqlite_retained_cursor_close_requires_exact_pair(phase, fault):
    events, bodies, executions = retained_cursor_witness()
    index = {"source": 0, "insert": 1, "provenance": 2}[phase]
    start = (6, 14, 22)[index]
    end = start + 2
    if fault == "missing_return":
        events[start + 1] = ("c_exception", *events[start + 1][1:])
    elif fault == "wrong_raw":
        events[start] = ("c_call", "bootstrap", 78, "close")
    elif fault == "wrong_phase":
        events[start] = ("c_call", "harness-dispose", 77, "close")
    else:
        events.insert(end, ("c_return", "bootstrap", 77, "close"))
        end += 1
        if phase == "insert":
            executions[index]["returned_at"] += 1
    with pytest.raises(AssertionError):
        if phase == "insert":
            guarded_body(executions[index], bodies[index], events, 77)
        else:
            cursor_close(events, start, end, 77)


def test_sqlite_installed_result_cleanup_preserves_execute_vs_consume_boundaries(monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    accept(value, CASES[2])
    calls = value.observations["native_calls"]
    executions = [
        next(row for row in value.observations["executions"] if row["name"] == call["name"])
        for call in calls
    ]
    assert [row["returned_at"] - row["entered_at"] for row in executions] == [8, 6]
    assert calls[0]["returned_at"] + 2 == executions[0]["returned_at"]
    assert calls[1]["returned_at"] == executions[1]["returned_at"]
    assert value.observations["provenance"][0]["returned_at"] == calls[1]["returned_at"] + 2


def source_span(monkeypatch):
    original = {
        "api_keys": [("a" * 32, "hash", "admin", "key", None, 0)],
        "audit": [(1, 1.0, "actor", "action", "target")],
        "events": [("run", 1, "artifact", "hash")],
        "jobs": [
            ("b" * 32, "run", 1.0, "{}", "failed", None, None, 0, 1, 0, None, "error", "actor")
        ],
        "records": [("c" * 32, "task", 1.0, {})],
    }

    def result(name):
        if name == "accounts.insert":
            return [], 1
        if name.startswith("source_count_"):
            return [{"candidate_rows": 1}], -1
        if name.startswith("source_stats_"):
            return [
                {
                    "observed_rows": 1,
                    "graph_invalid_rows": 0,
                    "original_native_bytes": 1,
                    "max_original_native_bytes": 1,
                }
            ], -1
        if name.startswith("source_gate_"):
            return [
                {
                    "candidate_count": 1,
                    "invalid_rows": 0,
                    "max_row_bytes": 1,
                    "selected_count": 1,
                    "selected_bytes": 1,
                }
            ], -1
        assert name.startswith("source_body_") and name.endswith("_first")
        table = name.removeprefix("source_body_").removesuffix("_first")
        fields = [column[0] for column in COLUMNS[table]]
        return [
            {
                **dict(zip(fields, original[table][0], strict=True)),
                "source_ordinal": 1,
                "native_row_bytes": 1,
                "invalid_row": 0,
            }
        ], -1

    watch, connection, executed = inert_sqlite(result)
    with observe_sqlite_source(watch, monkeypatch, lambda *_: None) as (boundary, calls):
        fingerprint = ledger_service.source_digest(connection, watch.work)
    (observed,) = boundary["hashes"]
    assert observed["original_caller"] is False  # Control call, not original initialize_ledger.
    _, manifest, *_ = independent_state(CASES[2])
    manifest["source_digest"] = source_fingerprint(original)
    assert fingerprint == manifest["source_digest"]
    values = {
        **manifest["accounts"][0],
        "opening_held_microusd": 0,
        "held_microusd": 0,
        "accounted_microusd": 0,
    }
    ledger_service._write(connection, "accounts.insert", values)
    gate, _ = source_site()
    anchor = identity(watch)
    hashed = {
        **observed,
        "original_caller": True,
        "line": gate,
        "native_calls": calls,
        "preparation": [
            {
                **anchor,
                "original_caller": True,
                "line": gate - 1,
                "entered_at": 0,
                "returned_at": 0,
                "completed": True,
                "manifest": deepcopy(manifest),
                "state": {"manifest_count": 1},
            }
        ],
    }
    execution, body = executed[-1]
    observations = {"source_hashes": [hashed], "executions": [execution], "native_calls": [body]}
    return observations, original, manifest, watch.trace.events, None, anchor


def test_sqlite_original_hash_uses_positional_bodies_and_exact_work(monkeypatch):
    data = source_span(monkeypatch)
    assert_expiry_source(*data, backend="sqlite")
    hashed = data[0]["source_hashes"][0]
    assert len(hashed["native_calls"]) == 20
    assert hashed["work_after"] - hashed["work_before"] == 40
    assert hashed["returned_at"] - hashed["entered_at"] == 160


@pytest.mark.parametrize(
    "fault",
    [
        "caller",
        "frame",
        "source",
        "manifest",
        "identity",
        "range_float",
        "work_float",
        "missing_call",
        "missing_close",
        "wrong_close",
        "extra_close",
        "mapping",
        "float_bind",
        "wrong_bound",
        "changed_sql",
        "missing_setter",
        "over_cap",
        "missing_return",
        "outside_cte",
        "insert_return",
        "wrong_raw",
        "wrong_phase",
    ],
)
def test_sqlite_hash_span_rejects_provenance_bind_and_locality_corruption(fault, monkeypatch):
    data = source_span(monkeypatch)
    observations, original, manifest, events, _, anchor = data
    hashed = observations["source_hashes"][0]
    call = hashed["native_calls"][0]
    if fault == "caller":
        hashed["original_caller"] = False
    elif fault == "frame":
        hashed["line"] += 1
    elif fault == "source":
        original["audit"][0] = (2, 1.0, "actor", "action", "target")
    elif fault == "manifest":
        hashed["preparation"][0]["manifest"]["manifest_id"] = "e" * 32
    elif fault == "identity":
        hashed["work_id"] += 1
    elif fault == "range_float":
        hashed["entered_at"] = float(hashed["entered_at"])
    elif fault == "work_float":
        hashed["work_after"] = float(hashed["work_after"])
    elif fault == "missing_call":
        hashed["native_calls"].pop()
    elif fault == "missing_close":
        del events[6:8]
    elif fault == "wrong_close":
        events[7] = ("c_exception", *events[7][1:])
    elif fault == "extra_close":
        events.insert(8, ("c_return", "bootstrap", anchor["raw_id"], "close"))
        hashed["returned_at"] += 1
    elif fault == "mapping":
        call["parameters"] = {"remaining_rows_plus_one": 1000001}
    elif fault == "float_bind":
        call["parameters"] = (1000001.0,)
    elif fault == "wrong_bound":
        call["parameters"] = (1000000,)
    elif fault == "changed_sql":
        call["sql"] += " "
    elif fault in {"missing_setter", "over_cap"}:
        events[1] = (
            *events[1][:3],
            "SELECT 1" if fault == "missing_setter" else "PRAGMA busy_timeout=5001",
        )
    elif fault == "missing_return":
        events[5] = ("c_exception", *events[5][1:])
    elif fault == "outside_cte":
        query = next(row[3] for row in events if row[0] == "sql" and row[3].startswith("WITH"))
        events.extend(
            [
                ("c_call", "bootstrap", anchor["raw_id"], "execute"),
                ("sql", "bootstrap", anchor["raw_id"], query),
                ("c_return", "bootstrap", anchor["raw_id"], "execute"),
            ]
        )
    elif fault == "insert_return":
        observations["native_calls"][0]["rowcount"] = 0
    elif fault == "wrong_raw":
        call["raw_id"] += 1
    elif fault == "wrong_phase":
        call["phase"] = "ordinary"
    with pytest.raises((AssertionError, ValueError, TypeError)):
        assert_expiry_source(*data, backend="sqlite")


def pooled():
    raw = SimpleNamespace(_ownership=SimpleNamespace(closed=True))
    boundary = {
        "trace_end": 9,
        "raw_id": id(raw),
        "connection_closed": True,
        "checkedout": 0,
        "raw_closed": False,
        "in_transaction": False,
        "ownership_closed": False,
        "borrowed": False,
        "tainted": False,
        "native_busy": False,
        "unknown_callback": False,
        "lease_present": False,
        "receipt_completed": True,
        "receipt_clean": True,
    }
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    return SimpleNamespace(
        work=SimpleNamespace(_raw=raw, timeout_seconds=5),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            rollback_acknowledged=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
        faults=[],
        command_boundary=boundary,
        assert_single_attempt=lambda: None,
        markers=[(name, id(raw), i + 1 if i < 4 else 9) for i, name in enumerate(names)]
        + [("raw.close.native_ack", id(raw), 10)],
    )


def test_sqlite_clean_pool_return_precedes_separately_attributed_close():
    assert_pooled_rollback(pooled())
    assert_target_actions([(sqlite3.SQLITE_READ, "jobs", "id", "main", None)], inserted=False)
    assert_target_actions(
        [(sqlite3.SQLITE_INSERT, "budget_accounts", None, "main", None)], inserted=True
    )


@pytest.mark.parametrize(
    "fault",
    [
        "raw_closed",
        "in_transaction",
        "borrowed",
        "tainted",
        "lease_present",
        "native_busy",
        "unknown_callback",
        "receipt_clean",
        "receipt_completed",
        "checkedout",
        "close_before_return",
        "no_disposal",
        "commit",
        "timeout_float",
    ],
)
def test_sqlite_return_and_disposal_obligations_remain_separate(fault):
    value = pooled()
    if fault in {"receipt_clean", "receipt_completed"}:
        value.command_boundary[fault] = False
    elif fault == "checkedout":
        value.command_boundary[fault] = 1
    elif fault == "close_before_return":
        value.markers[-1] = ("raw.close.native_ack", id(value.work._raw), 3)
    elif fault == "no_disposal":
        value.work._raw._ownership.closed = False
    elif fault == "commit":
        value.outcome.commit_attempted = True
    elif fault == "timeout_float":
        value.work.timeout_seconds = 5.0
    else:
        value.command_boundary[fault] = True
    with pytest.raises(AssertionError):
        assert_pooled_rollback(value)


@pytest.mark.parametrize(
    "writes",
    [
        [],
        [(sqlite3.SQLITE_INSERT, "migration_progress", None, "main", None)],
        [(sqlite3.SQLITE_INSERT, "budget_accounts", None, "main", None)] * 2,
        [(sqlite3.SQLITE_UPDATE, "budget_accounts", "held_microusd", "main", None)],
    ],
)
def test_sqlite_expiry_authorization_never_substitutes_for_exact_insert(writes):
    with pytest.raises(AssertionError):
        assert_target_actions(writes, inserted=True)
