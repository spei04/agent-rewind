"""Authored complete reader and native scalar boundary controls."""

import json
import sqlite3

import ledger_reader_fixture
import pytest
import test_migrations_postgres as migration_tests
from ledger_operator_fixture import SQLiteTrace
from ledger_reader_fixture import (
    complete_ar6,
    complete_postgres_ar6,
    postgres_snapshot,
    seed_ar7,
    sqlite_snapshot,
)
from sqlalchemy import text
from test_ledger_operator_postgres import PostgresTrace
from test_run_projection_postgres import drain

from agent_rewind.migrations import (
    ledger_inspection,
    ledger_reader_financial,
    ledger_reader_graph,
    ledger_reader_history,
)
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused


@pytest.mark.parametrize(
    "legacy,ledger,empty",
    [
        (False, False, False),
        (True, False, False),
        (False, True, True),
        (False, True, False),
        (True, True, False),
    ],
)
def test_complete_inspector_uses_one_work_and_preserves_source(tmp_path, legacy, ledger, empty):
    case = complete_ar6(tmp_path / "reader.sqlite", legacy=legacy)
    engine = None
    try:
        if ledger:
            seed_ar7(case, empty_accounts=empty)
        before = sqlite_snapshot(case.path)
        engine = case.operator_engine()
        work, outcome = LedgerWork(), LedgerOutcome()
        with ledger_transaction(engine, outcome, work=work) as connection:
            state = inspect_ledger_state(connection)
        assert state.model_dump(mode="json") == case.expected
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert work.prepaid_bootstrap == 12 and work.prepaid_cleanup == 8
        assert 0 < work.observed_ordinary <= 2028
        assert sqlite_snapshot(case.path) == before
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()


@pytest.mark.parametrize(
    "receipt",
    [
        {"candidate_rows": True, "invalid_rows": 0, "safe_revision": ADMISSION},
        {"candidate_rows": 1, "invalid_rows": False, "safe_revision": ADMISSION},
        {"candidate_rows": 1, "invalid_rows": 0, "safe_revision": ADMISSION.encode()},
        {"candidate_rows": 1, "invalid_rows": 0, "safe_revision": ADMISSION, "extra": 0},
    ],
)
def test_revision_receipt_refuses_coerced_native_classes(monkeypatch, receipt):
    monkeypatch.setattr(ledger_reader_history, "_query", lambda *args: [receipt])
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        ledger_reader_history.read_revision(object())


def test_original_api_key_grant_remains_valid_without_live_membership_equality(
    tmp_path, monkeypatch
):
    original = ledger_reader_fixture.mapping_for
    selected = []

    def mapping_with_key(engine):
        mapping = original(engine)
        with engine.connect() as connection:
            key_id = connection.exec_driver_sql(
                "SELECT id FROM api_keys ORDER BY id LIMIT 1"
            ).scalar_one()
        selected.append(key_id)
        mapping["key_dispositions"] = [{"key_id": key_id, "role": "viewer"}]
        mapping["principal_grants"].append(
            {"principal_id": "api-key:" + key_id, "role": "viewer", "legacy_default": False}
        )
        return mapping

    monkeypatch.setattr(ledger_reader_fixture, "mapping_for", mapping_with_key)
    case = complete_ar6(tmp_path / "reader.sqlite", legacy=True)
    engine = None
    try:
        assert len(selected) == 1
        with case.engine.begin() as connection:
            changed = connection.exec_driver_sql(
                "UPDATE project_memberships SET role='operator' WHERE principal_id=?",
                ("api-key:" + selected[0],),
            )
            assert changed.rowcount == 1
        engine = case.operator_engine()
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            state = inspect_ledger_state(connection)
        assert state.model_dump(mode="json") == case.expected
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()


def test_expiry_between_descriptor_validations_stops_before_the_next_body(tmp_path, monkeypatch):
    from agent_rewind.migrations import ledger_reader_financial, ledger_work

    case = seed_ar7(complete_ar6(tmp_path / "reader.sqlite"))
    engine = None
    try:
        ledger_reader_fixture.later_admitted_call(case, effect="settled")
        engine = case.operator_engine()
        clock = [0.0]
        expire = [False]
        observed = []
        original = ledger_reader_financial._object

        def observed_descriptor(value):
            result = original(value)
            observed.append(value["id"])
            if expire[0]:
                clock[0] = 121.0
            return result

        monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])
        monkeypatch.setattr(ledger_reader_financial, "_object", observed_descriptor)
        with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
            assert inspect_ledger_state(connection).model_dump(mode="json") == case.expected
        assert len(observed) >= 2

        observed.clear()
        expire[0] = True
        before = sqlite_snapshot(case.path)
        with (
            pytest.raises(MigrationRefused, match="^migration_busy$"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection,
        ):
            inspect_ledger_state(connection)
        assert len(observed) == 1
        assert sqlite_snapshot(case.path) == before
    finally:
        if engine is not None:
            engine.dispose()
        case.dispose()


pg = migration_tests.pg


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(
                not migration_tests.POSTGRES, reason="Opt-in complete reader integration"
            ),
        ),
    ]
)
def integration_reader_case(request, tmp_path):
    native = request.getfixturevalue("pg") if request.param == "postgres" else None
    case = (
        complete_postgres_ar6(native, legacy=False)
        if native is not None
        else complete_ar6(tmp_path / "integration.sqlite")
    )
    try:
        yield case, native
    finally:
        case.dispose()
        if native is not None:
            drain(native)


def integration_snapshot(case, native):
    value = postgres_snapshot(case.engine) if native is not None else sqlite_snapshot(case.path)
    if native is not None:
        drain(native)
    return value


def add_multipage_jobs(case):
    identifiers = [f"{10_000_000 + index:032x}" for index in range(4097)]
    with case.engine.begin() as connection:
        project = connection.exec_driver_sql("SELECT id FROM projects").scalar_one()
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,actor) "
                "VALUES(:id,'run',1700000000.125,'{}','queued',false,1,0,NULL)"
            ),
            [{"id": identity} for identity in identifiers],
        )
        connection.execute(
            text(
                "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
                "VALUES('job',:id,:project)"
            ),
            [{"id": identity, "project": project} for identity in identifiers],
        )
    return identifiers


def observe_graph_queries(monkeypatch, *, after=None):
    observed = []
    original = ledger_reader_graph._query

    def query(connection, name, parameters):
        result = original(connection, name, parameters)
        if name.startswith("graph_page_"):
            observed.append(
                {
                    "name": name,
                    "parameters": dict(parameters),
                    "rows": len(result),
                    "gate": dict(result[0]) if "_gate_" in name else None,
                    "first": result[0].get("id") if result and "_body_" in name else None,
                    "last": result[-1].get("id") if result and "_body_" in name else None,
                }
            )
        if after is not None:
            after(connection, name, result)
        return result

    monkeypatch.setattr(ledger_reader_graph, "_query", query)
    return observed


def test_complete_reader_multipage_state_and_terminal_queries(
    integration_reader_case, monkeypatch, record_property
):
    case, native = integration_reader_case
    identifiers = add_multipage_jobs(case)
    before = integration_snapshot(case, native)
    graph = observe_graph_queries(monkeypatch)
    receipts, measured = [], {}
    original_query = ledger_reader_financial._query
    original_financial = ledger_inspection.read_financial

    def financial_query(*args):
        result = original_query(*args)
        if args[-1].endswith("_gate") and result and "native_bytes" in result[0]:
            receipts.append(dict(result[0]))
        return result

    def financial(*args):
        data = original_financial(*args)
        assert all(
            not data[key] for key in ("account", "call", "entry", "operation", "ref", "object")
        )
        # Independent ordered projections for this ar6 fixture's four nonempty domains.
        fields = {
            "job": (
                "id",
                "kind",
                "created",
                "payload",
                "status",
                "owner",
                "lease_until",
                "cancel",
                "budget",
                "reserved",
                "result",
                "error",
                "actor",
                "payload_version",
                "execution_config_ref",
                "execution_config_digest",
            ),
            "scope": ("resource_kind", "resource_id", "project_id"),
            "project": ("id", "organization_id"),
            "organization": ("id", "installation_key"),
        }
        frames = [
            [domain, [row[field] for field in names]]
            for domain, names in fields.items()
            for row in data[domain]
        ]
        measured["canonical"] = len(
            json.dumps(frames, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        )
        measured["native"] = sum(value["native_bytes"] for value in receipts)
        assert len(data["job"]) == len(data["scope"]) == 4097
        assert 0 < measured["canonical"] < 2 * 1024 * 1024
        assert 0 < measured["native"] < 2 * 1024 * 1024
        return data

    monkeypatch.setattr(ledger_reader_financial, "_query", financial_query)
    monkeypatch.setattr(ledger_inspection, "read_financial", financial)
    trace = PostgresTrace(monkeypatch) if native is not None else SQLiteTrace()
    if native is None:
        monkeypatch.setattr(sqlite3, "connect", trace.connect)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            trace.phase = "reader"
            state = inspect_ledger_state(connection)
            trace.phase = "ordinary"
        assert state.model_dump(mode="json") == case.expected
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert 0 < work.observed_ordinary <= 2028
    finally:
        engine.dispose()
        if native is not None:
            trace.stop()
    job_pages = [value for value in graph if "_jobs_" in value["name"]]
    assert [value["name"] for value in job_pages] == [
        "graph_page_gate_jobs_first",
        "graph_page_body_jobs_first",
        "graph_page_gate_jobs_next",
        "graph_page_body_jobs_next",
        "graph_page_gate_jobs_next",
    ]
    first_gate, first_body, second_gate, second_body, terminal = job_pages
    assert first_gate["gate"]["accepted_rows"] == first_body["rows"] == 4096
    assert first_body["first"] == identifiers[0]
    assert first_gate["gate"]["end_id"] == first_body["last"] == identifiers[4095]
    assert second_gate["parameters"]["after_id"] == identifiers[4095]
    assert second_gate["gate"]["accepted_rows"] == second_body["rows"] == 1
    assert second_body["first"] == second_body["last"] == identifiers[-1]
    assert terminal["parameters"]["after_id"] == identifiers[-1]
    assert terminal["gate"]["candidates"] == terminal["gate"]["accepted_rows"] == 0
    assert (
        len([value for value in graph if value["gate"] and value["gate"]["candidates"] == 0]) == 4
    )
    if native is not None:
        assert len(trace.handles) == 1
        assert not [
            event
            for event in trace.events
            if event[1] in {"sql-call", "command"}
            and event[-1]
            and event[-1].lstrip().upper().startswith(("DECLARE", "FETCH", "CLOSE"))
        ]
    else:
        assert len([event for event in trace.events if event[0] == "connect_return"]) == 1
    record_property("multipage_graph", json.dumps(graph))
    record_property("multipage_financial_bytes", json.dumps(measured))
    record_property("reader_work", str(work.observed_ordinary))
    record_property("reader_native_trace", json.dumps(trace.events))
    assert integration_snapshot(case, native) == before


def test_complete_reader_late_exhaustion_refuses_before_terminal_page(
    integration_reader_case, monkeypatch, record_property
):
    case, native = integration_reader_case
    add_multipage_jobs(case)
    before = integration_snapshot(case, native)
    work, outcome = LedgerWork(), LedgerOutcome()
    filled = []

    def exhaust(connection, name, result):
        if name != "graph_page_body_jobs_next":
            return
        assert len(result) == 1 and not filled
        bundle = 3 if native is not None else 2
        while 2028 - work.observed_ordinary >= bundle:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            filled.append(1)
        assert 0 <= 2028 - work.observed_ordinary < bundle

    graph = observe_graph_queries(monkeypatch, after=exhaust)
    engine = case.operator_engine()
    published = []
    try:
        with (
            pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
            ledger_transaction(engine, outcome, work=work) as connection,
        ):
            published.append(inspect_ledger_state(connection))
        assert not published and filled
        assert graph[-1]["name"] == "graph_page_body_jobs_next"
        assert outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        record_property("late_read_targets", str(len(filled)))
        record_property("reader_work", str(work.observed_ordinary))
    finally:
        engine.dispose()
    assert integration_snapshot(case, native) == before


@pytest.mark.parametrize("change", ["control", "reentrant", "final-options", "final-deadline"])
def test_complete_reader_boundary_change_never_publishes_partial_state(
    integration_reader_case, monkeypatch, change
):
    from agent_rewind.migrations import ledger_work

    case, native = integration_reader_case
    before = integration_snapshot(case, native)
    original = ledger_inspection.read_graph
    clock = [0.0]
    finished = []
    monkeypatch.setattr(ledger_work, "monotonic", lambda: clock[0])

    def after_graph(connection, *args):
        result = original(connection, *args)
        finished.append(True)
        if change == "reentrant":
            inspect_ledger_state(connection)
        elif change == "final-options":
            connection.execution_options(stream_results=True)
        elif change == "final-deadline":
            clock[0] = 121.0
        return result

    monkeypatch.setattr(ledger_inspection, "read_graph", after_graph)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    published = []
    try:
        if change == "control":
            with ledger_transaction(engine, outcome, work=work) as connection:
                published.append(inspect_ledger_state(connection))
            assert published[0].model_dump(mode="json") == case.expected
            assert outcome.commit_acknowledged
        else:
            expected = (
                "migration_busy"
                if change == "final-deadline"
                else "transactional_connection_required"
            )
            with (
                pytest.raises(MigrationRefused, match="^" + expected + "$"),
                ledger_transaction(engine, outcome, work=work) as connection,
            ):
                published.append(inspect_ledger_state(connection))
            assert not published and not outcome.commit_attempted
            assert outcome.rollback_acknowledged and not outcome.cleanup_failed
        assert finished == [True]
    finally:
        engine.dispose()
    assert integration_snapshot(case, native) == before
