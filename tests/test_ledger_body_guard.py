"""Authored native continuity controls for the private ledger body guard."""

import json
import sqlite3
from contextlib import closing

import ledger_operator_fixture
import psycopg
import pytest
import test_migrations_postgres as migration_tests
from ledger_operator_fixture import proof_rows
from postgres_control import wait_for_database_drain
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from test_ledger_operator_postgres import PostgresTrace

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import (
    LedgerOutcome,
    _require_ledger_body,
    ledger_transaction,
)
from agent_rewind.migrations.ledger_work import MAX_ORDINARY, LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

ledger_case = ledger_operator_fixture.ledger_case
pg = migration_tests.pg
native_pg = pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in native body guard")


def refused(connection):
    with pytest.raises(MigrationRefused, match="transactional_connection_required"):
        _require_ledger_body(connection)


def test_sqlite_body_is_exclusive_without_validation_sql(ledger_case, record_property):
    case = ledger_case
    outcome, work = LedgerOutcome(), LedgerWork()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        raw = connection.connection.driver_connection
        root = connection.get_transaction()
        start, units = len(case.trace.events), work.observed_ordinary
        for _ in range(3):
            assert _require_ledger_body(connection) is work
        assert case.trace.sql(start) == []
        assert work.observed_ordinary == units
        assert raw.in_transaction and root.is_active
        with closing(sqlite3.connect(case.path, timeout=0)) as other:
            with pytest.raises(sqlite3.OperationalError) as caught:
                other.execute("INSERT INTO proof VALUES (2)")
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
    refused(connection)
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert proof_rows(case.path) == [1]
    with closing(sqlite3.connect(case.path, timeout=0)) as other, other:
        other.execute("INSERT INTO proof VALUES (2)")
    assert proof_rows(case.path) == [1, 2]
    record_property("native_trace", json.dumps(case.trace.events))


def test_ordinary_transaction_and_connection_info_are_not_capabilities(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/plain.sqlite")
    try:
        with engine.begin() as connection:
            connection.info["ledger_body"] = True
            connection.exec_driver_sql("CREATE TABLE proof (id INTEGER)")
            assert connection.get_transaction().is_active
            refused(connection)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "target,attribute,value",
    [
        ("work", "_detached", True),
        ("work", "_claimed", False),
        ("work", "_raw", None),
        ("claim", "released", True),
        ("receipt", "generation", -1),
        ("receipt", "failed", True),
        ("receipt", "completed", True),
        ("receipt", "returned", True),
        ("physical", "generation", -1),
        ("physical", "borrowed", False),
        ("physical", "tainted", True),
        ("physical", "unknown_callback", True),
        ("physical", "lease", None),
        ("lease", "_generation", -1),
        ("lease", "_released", True),
        ("lease", "_owner", None),
    ],
)
def test_live_identity_fault_refuses_without_native_work(ledger_case, target, attribute, value):
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(ledger_case.engine, outcome, work=work) as connection:
        assert _require_ledger_body(connection) is work
        raw = connection.connection.driver_connection
        body = transaction._BODIES[connection]
        objects = {
            "work": work,
            "claim": body.claim,
            "receipt": body.receipt,
            "physical": raw._ownership,
            "lease": work._lease,
        }
        obj = objects[target]
        previous = getattr(obj, attribute)
        start = len(ledger_case.trace.events)
        setattr(obj, attribute, value)
        try:
            refused(connection)
            assert ledger_case.trace.sql(start) == []
        finally:
            setattr(obj, attribute, previous)
        assert _require_ledger_body(connection) is work
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
    assert outcome.commit_acknowledged and proof_rows(ledger_case.path) == [1]


@pytest.mark.parametrize("failure", ["before", "after"])
def test_registration_failure_never_yields_and_revokes_before_cleanup(
    ledger_case, monkeypatch, failure
):
    original = transaction._register_ledger_body
    detach = LedgerWork._detach
    saved = []
    error = MigrationRefused("source_digest_mismatch")

    def register(connection, *args):
        saved.append(connection)
        refused(connection)
        if failure == "after":
            original(connection, *args)
            assert _require_ledger_body(connection) is args[1]
        raise error

    def detaching(work):
        refused(saved[0])
        return detach(work)

    monkeypatch.setattr(transaction, "_register_ledger_body", register)
    monkeypatch.setattr(LedgerWork, "_detach", detaching)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(ledger_case.engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("registration failure yielded")
    assert caught.value is error
    assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed
    assert proof_rows(ledger_case.path) == []
    refused(saved[0])


@pytest.mark.parametrize("error", [None, ValueError("body"), KeyboardInterrupt("first")])
def test_body_revoked_before_commit_preparation_and_detach(ledger_case, monkeypatch, error):
    prepare, detach = LedgerWork._prepare_target, LedgerWork._detach
    saved, witnessed = [], []

    def preparing(work):
        if saved:
            refused(saved[0])
            witnessed.append("prepare")
        return prepare(work)

    def detaching(work):
        refused(saved[0])
        witnessed.append("detach")
        return detach(work)

    monkeypatch.setattr(LedgerWork, "_prepare_target", preparing)
    monkeypatch.setattr(LedgerWork, "_detach", detaching)
    outcome = LedgerOutcome()
    caught = None
    try:
        with ledger_transaction(ledger_case.engine, outcome, work=LedgerWork()) as connection:
            assert _require_ledger_body(connection)
            saved.append(connection)
            if error is not None:
                raise error
    except BaseException as exc:
        caught = exc
    assert witnessed == (["prepare", "detach"] if error is None else ["detach"])
    if error is None:
        assert caught is None and outcome.commit_acknowledged
    elif isinstance(error, KeyboardInterrupt):
        assert caught is error and outcome.confirmed_precommit_rollback
    else:
        assert isinstance(caught, MigrationRefused)
        assert str(caught) == "migration_database_failure"
        assert outcome.confirmed_precommit_rollback
    refused(saved[0])


def test_saved_body_cannot_follow_reused_native_generation(ledger_case):
    with ledger_transaction(ledger_case.engine, LedgerOutcome(), work=LedgerWork()) as old:
        raw = old.connection.driver_connection
        generation = raw._ownership.generation
        assert _require_ledger_body(old)
    work = LedgerWork()
    with ledger_transaction(ledger_case.engine, LedgerOutcome(), work=work) as current:
        assert current.connection.driver_connection is raw
        assert raw._ownership.generation > generation
        refused(old)
        assert _require_ledger_body(current) is work
        assert (
            current.exec_driver_sql(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000) "
                "SELECT sum(x) FROM n"
            ).scalar_one()
            == 2001000
        )
        assert raw._ownership.lease is work._lease


@pytest.fixture
def guard_pg(pg, monkeypatch, request, record_property):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("CREATE TABLE proof (id INTEGER PRIMARY KEY)")
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    engine = create_ledger_engine(pg["owner"].url.render_as_string(hide_password=False))
    trace = PostgresTrace(monkeypatch)

    def finish():
        trace.stop()
        record_property("native_trace", json.dumps(trace.events))
        engine.dispose()
        wait_for_database_drain(pg["control"], pg["owner"].url.database)

    request.addfinalizer(finish)
    return engine, pg, trace


@native_pg
def test_pg_guard_xid_queries_are_observed_and_second_writer_is_excluded(guard_pg):
    engine, pg, trace = guard_pg
    outcome, work = LedgerOutcome(), LedgerWork()
    with ledger_transaction(engine, outcome, work=work) as connection:
        assert sum(sql == "SELECT pg_current_xact_id()::text" for sql in trace.sql("ordinary")) == 1
        units, start = work.observed_ordinary, len(trace.sql("ordinary"))
        assert _require_ledger_body(connection) is work
        assert work.observed_ordinary - units == 3
        assert trace.sql("ordinary")[start:][-1] == "SELECT pg_current_xact_id()::text"
        assert len(trace.sql("ordinary")[start:]) == 3
        trace.phase = "verification"
        with pg["owner"].connect() as other:
            other.exec_driver_sql("SET LOCAL lock_timeout='30ms'")
            with pytest.raises(DBAPIError) as caught:
                other.exec_driver_sql("INSERT INTO proof VALUES (2)")
            assert caught.value.orig.sqlstate == "55P03"
        trace.phase = "ordinary"
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
    refused(connection)
    assert outcome.commit_acknowledged
    trace.phase = "verification"
    with pg["owner"].begin() as other:
        assert list(other.exec_driver_sql("SELECT id FROM proof").scalars()) == [1]
        other.exec_driver_sql("INSERT INTO proof VALUES (2)")


@native_pg
@pytest.mark.parametrize("replace_native", [False, True])
def test_pg_native_rollback_is_rejected_without_starting_an_idle_transaction(
    guard_pg, replace_native
):
    engine, _, trace = guard_pg
    outcome, work = LedgerOutcome(), LedgerWork()
    with ledger_transaction(engine, outcome, work=work) as connection:
        assert _require_ledger_body(connection) is work
        raw = connection.connection.driver_connection
        root = connection.get_transaction()
        raw.rollback()
        assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        if replace_native:
            raw.execute("BEGIN").close()
            assert raw.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        start, units = len(trace.sql("ordinary")), work.observed_ordinary
        refused(connection)
        assert connection.get_transaction() is root and root.is_active
        if replace_native:
            assert work.observed_ordinary - units == 3
            assert trace.sql("ordinary")[start:][-1] == "SELECT pg_current_xact_id()::text"
        else:
            assert trace.sql("ordinary")[start:] == []
            assert work.observed_ordinary == units
            assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


@native_pg
def test_pg_guard_exhaustion_reserves_no_partial_query_bundle(guard_pg):
    engine, _, trace = guard_pg
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="ledger_limit_exceeded"),
        ledger_transaction(engine, outcome, work=work) as connection,
    ):
        assert _require_ledger_body(connection) is work
        work.reserve_ordinary(MAX_ORDINARY - work.observed_ordinary - 2)
        start, units = len(trace.sql("ordinary")), work.observed_ordinary
        with pytest.raises(MigrationRefused, match="ledger_limit_exceeded"):
            _require_ledger_body(connection)
        assert work.observed_ordinary == units == MAX_ORDINARY - 2
        assert trace.sql("ordinary")[start:] == []
        raise MigrationRefused("ledger_limit_exceeded")
    assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed


@native_pg
@pytest.mark.parametrize("mutation", ["detach", "stream_results", "yield_per"])
def test_pg_detached_or_streaming_connection_refuses_before_identity_sql(guard_pg, mutation):
    engine, _, trace = guard_pg
    outcome, work = LedgerOutcome(), LedgerWork()
    with ledger_transaction(engine, outcome, work=work) as connection:
        assert _require_ledger_body(connection) is work
        raw = connection.connection.driver_connection
        if mutation == "detach":
            connection.detach()
            assert connection.connection.is_detached
        else:
            connection.execution_options(**{mutation: True if mutation == "stream_results" else 1})
        start, units = len(trace.events), work.observed_ordinary
        refused(connection)
        assert trace.events[start:] == []
        assert work.observed_ordinary == units
        assert raw.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
    assert raw.closed and outcome.commit_acknowledged and not outcome.cleanup_failed


@pytest.mark.parametrize(
    "scope,name",
    [
        ("connection", "before_cursor_execute"),
        ("connection", "after_cursor_execute"),
        ("connection", "before_execute"),
        ("connection", "commit"),
        ("connection", "begin"),
        ("engine", "before_cursor_execute"),
        ("engine", "engine_connect"),
        ("engine", "do_execute"),
        ("engine", "checkout"),
        ("connection_class", "before_cursor_execute"),
        ("engine_class", "before_cursor_execute"),
        ("pool_class", "checkout"),
        ("dialect_class", "do_execute"),
    ],
)
def test_foreign_public_handlers_refuse_without_running_or_removing_them(ledger_case, scope, name):
    work = LedgerWork()
    calls = []

    def foreign(*args):
        calls.append(True)

    with ledger_transaction(ledger_case.engine, LedgerOutcome(), work=work) as connection:
        assert _require_ledger_body(connection) is work
        targets = {
            "connection": connection,
            "engine": ledger_case.engine,
            "connection_class": Connection,
            "engine_class": Engine,
            "pool_class": type(ledger_case.engine.pool),
            "dialect_class": type(ledger_case.engine.dialect),
        }
        target = targets[scope]
        start, units = len(ledger_case.trace.events), work.observed_ordinary
        event.listen(target, name, foreign)
        try:
            refused(connection)
            assert event.contains(target, name, foreign)
            assert calls == []
            assert ledger_case.trace.sql(start) == []
            assert work.observed_ordinary == units
        finally:
            event.remove(target, name, foreign)
        assert _require_ledger_body(connection) is work
        assert connection.exec_driver_sql("SELECT 43").scalar_one() == 43


@pytest.mark.parametrize("name", ["before_execute", "do_execute"])
def test_foreign_handler_is_not_granted_permission_at_publication(ledger_case, monkeypatch, name):
    register = transaction._register_ledger_body
    saved, calls = [], []

    def foreign(*args):
        calls.append(True)

    def registering(connection, *args):
        saved.append(connection)
        target = connection if name == "before_execute" else connection.engine
        event.listen(target, name, foreign)
        try:
            return register(connection, *args)
        finally:
            event.remove(target, name, foreign)

    monkeypatch.setattr(transaction, "_register_ledger_body", registering)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="transactional_connection_required"),
        ledger_transaction(ledger_case.engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("a foreign handler was grandfathered into publication")
    assert calls == [] and outcome.confirmed_precommit_rollback and not outcome.cleanup_failed
    refused(saved[0])
