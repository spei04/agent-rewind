"""Native boundaries for the complete inspector under its actual operator body."""

import json
import sqlite3
from uuid import uuid4

import pytest
import test_migrations_postgres as migration_tests
from ledger_operator_fixture import SQLiteTrace
from ledger_reader_fixture import (
    RowTransferWatch,
    complete_postgres_ar6,
    postgres_snapshot,
    seed_ar7,
    sqlite_snapshot,
)
from postgres_control import observe_exclusion_failure, wait_for_database_drain
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from test_ledger_operator_postgres import PostgresTrace
from test_ledger_reader_independent import COMPLETE_CASES, reader_case
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_work, service
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["reader_case", "observed_reader"]
pg = migration_tests.pg
postgres_only = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in independent PostgreSQL ledger reader"
)


@pytest.fixture
def reader_trace(monkeypatch, record_property):
    trace = SQLiteTrace()
    actions = []

    def connect(*args, **kwargs):
        raw = trace.connect(*args, **kwargs)

        def authorize(action, first, second, database, trigger):
            actions.append((trace.phase, action, first, second, database, trigger))
            return sqlite3.SQLITE_OK

        raw.set_authorizer(authorize)
        return raw

    trace.authorized_actions = actions
    monkeypatch.setattr(sqlite3, "connect", connect)
    yield trace
    record_property("reader_native_trace", json.dumps(trace.events))


@pytest.mark.parametrize("reader_case", COMPLETE_CASES, indirect=True)
def test_reader_uses_one_raw_connection_and_no_native_data_or_schema_writes(
    reader_case, reader_trace, record_property
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case, trace = reader_case, reader_trace
    before = sqlite_snapshot(case.path)
    boundary = len(trace.events)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            trace.phase = "reader"
            raw = connection.connection.driver_connection
            assert raw.in_transaction
            result = inspect_ledger_state(connection)
            assert connection.connection.driver_connection is raw and raw.in_transaction
            assert result.model_dump(mode="json") == case.expected
            trace.phase = "cleanup"
        events = trace.events[boundary:]
        assert len([event for event in events if event[0] == "connect_return"]) == 1
        sql = [event[3] for event in events if event[0] == "sql"]
        assert "BEGIN EXCLUSIVE" in sql and "COMMIT" in sql
        reader_sql = [event[3] for event in events if event[:2] == ("sql", "reader")]
        assert reader_sql
        writes = {
            getattr(sqlite3, name)
            for name in (
                "SQLITE_INSERT",
                "SQLITE_UPDATE",
                "SQLITE_DELETE",
                "SQLITE_CREATE_INDEX",
                "SQLITE_CREATE_TABLE",
                "SQLITE_CREATE_TEMP_INDEX",
                "SQLITE_CREATE_TEMP_TABLE",
                "SQLITE_CREATE_TEMP_TRIGGER",
                "SQLITE_CREATE_TEMP_VIEW",
                "SQLITE_CREATE_TRIGGER",
                "SQLITE_CREATE_VIEW",
                "SQLITE_DROP_INDEX",
                "SQLITE_DROP_TABLE",
                "SQLITE_DROP_TEMP_INDEX",
                "SQLITE_DROP_TEMP_TABLE",
                "SQLITE_DROP_TEMP_TRIGGER",
                "SQLITE_DROP_TEMP_VIEW",
                "SQLITE_DROP_TRIGGER",
                "SQLITE_DROP_VIEW",
                "SQLITE_ALTER_TABLE",
                "SQLITE_REINDEX",
                "SQLITE_ANALYZE",
                "SQLITE_ATTACH",
                "SQLITE_DETACH",
            )
        }
        assert not [
            action
            for action in trace.authorized_actions
            if action[0] == "reader" and action[1] in writes
        ]
        assert work.prepaid_bootstrap == 12 and work.prepaid_cleanup == 8
        assert 0 < work.observed_ordinary <= 2028
        assert not outcome.cleanup_failed and outcome.commit_acknowledged
        assert engine.pool.checkedout() == 0
        record_property("reader_work", str(work.observed_ordinary))
    finally:
        engine.dispose()
    assert sqlite_snapshot(case.path) == before


@pytest.mark.parametrize("state", ["unbegun", "logical", "native-exclusive"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_unissued_connection_refuses_before_any_reader_sql(reader_case, reader_trace, state):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    engine = create_engine(str(reader_case.engine.url))
    try:
        with engine.connect() as connection:
            if state == "logical":
                connection.begin()
            elif state == "native-exclusive":
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
            boundary = len(reader_trace.events)
            with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
                inspect_ledger_state(connection)
            assert reader_trace.events[boundary:] == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["deadline", "ordinary-budget"])
@pytest.mark.parametrize("reader_case", [COMPLETE_CASES[0]], indirect=True)
def test_reader_exhaustion_never_publishes_and_still_cleans_up(
    reader_case, reader_trace, monkeypatch, failure
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    case, trace = reader_case, reader_trace
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    work, outcome, returned = LedgerWork(), LedgerOutcome(), []
    code = "migration_busy" if failure == "deadline" else "ledger_limit_exceeded"
    try:
        with (
            pytest.raises(MigrationRefused, match="^" + code + "$"),
            ledger_transaction(engine, outcome, work=work) as connection,
        ):
            if failure == "deadline":
                now[0] += 121
            else:
                # Spend real observed bundles, leaving insufficient work for a catalog.
                while work.observed_ordinary < 1950:
                    connection.exec_driver_sql("SELECT 1").scalar_one()
            trace.phase = "reader"
            returned.append(inspect_ledger_state(connection))
        assert returned == []
        assert outcome.rollback_acknowledged and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert work.observed_ordinary <= 2028
        assert len(work.cleanup_observations) <= 8
        assert engine.pool.checkedout() == 0
        assert "ROLLBACK" in trace.sql()
    finally:
        engine.dispose()
    assert sqlite_snapshot(case.path) == before


@pytest.fixture
def postgres_reader_case(request, pg, observed_reader):
    legacy, ledger, empty = request.param
    case = complete_postgres_ar6(pg, legacy=legacy)
    if ledger:
        seed_ar7(case, empty_accounts=empty)
        drain(pg)
    yield case
    case.dispose()
    drain(pg)


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", COMPLETE_CASES, indirect=True)
def test_postgres_fixture_has_complete_profile_history_and_opening(postgres_reader_case, pg):
    from agent_rewind.migrations.ledger_state import validate_ledger_chain, validate_progress_row
    from agent_rewind.migrations.schema import LEDGER

    case = postgres_reader_case
    with case.engine.connect() as connection:
        adoption = dict(
            connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
        )
        assert {
            key: value for key, value in adoption.items() if key != "installed_schema_fingerprint"
        } == {
            key: value
            for key, value in case.adoption.items()
            if key != "installed_schema_fingerprint"
        }
        if case.revision == LEDGER:
            rows = (
                connection.exec_driver_sql(
                    "SELECT revision,phase,source_digest,CAST(cursor AS TEXT) AS cursor,"
                    "rows_verified,status,updated_at FROM migration_progress "
                    "WHERE revision='ar_0007_ledger' "
                    "ORDER BY phase"
                )
                .mappings()
                .all()
            )
            values = [validate_progress_row(connection, dict(row)) for row in rows]
            receipt = validate_ledger_chain(
                [value for value in values if hasattr(value, "manifest")],
                next(value for value in values if hasattr(value, "jobs")),
            )
            assert receipt.model_dump(mode="json") == case.expected["head"]
    drain(pg)


@postgres_only
@pytest.mark.parametrize("postgres_reader_case", COMPLETE_CASES, indirect=True)
def test_postgres_complete_reader_identity_and_unchanged_rows(
    postgres_reader_case, pg, monkeypatch, record_property
):
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = postgres_reader_case
    before = postgres_snapshot(case.engine)
    drain(pg)
    trace = PostgresTrace(monkeypatch)
    engine = case.operator_engine()
    work, outcome = LedgerWork(), LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=work) as connection:
            trace.phase = "reader"
            raw = connection.connection.driver_connection
            state = inspect_ledger_state(connection)
            assert connection.connection.driver_connection is raw
            assert state.model_dump(mode="json") == case.expected
            trace.phase = "ordinary"
        assert len(trace.handles) == 1
        assert raw.closed and outcome.commit_acknowledged and not outcome.cleanup_failed
        assert work.observed_ordinary <= 2028
        commands = [
            sql.strip().upper()
            for phase, kind, _, sql in trace.events
            if phase == "reader" and kind in {"sql-call", "command"} and sql
        ]
        assert commands
        assert all(sql.startswith(("SELECT", "WITH", "SET LOCAL", "SHOW")) for sql in commands)
        assert not any(
            sql.startswith(("DECLARE", "FETCH", "INSERT", "UPDATE", "DELETE")) for sql in commands
        )
        record_property("reader_work", str(work.observed_ordinary))
    finally:
        engine.dispose()
        trace.stop()
        record_property("reader_native_trace", json.dumps(trace.events))
    drain(pg)
    assert postgres_snapshot(case.engine) == before
    drain(pg)


@pytest.fixture
def latin1_pg(monkeypatch):
    """Own a C-locale LATIN1 database and roles, independent of default-encoding cases."""
    admin = create_engine(
        migration_tests.POSTGRES, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    token = "ar_reader_latin1_" + uuid4().hex
    owner, app, group = token + "_owner", token + "_app", token + "_group"
    password = "synthetic-test-only"
    roles, engines = [], []
    database_created = False
    exclusion = service._postgres_exclusion

    def observed_exclusion(connection, tables):
        observe_exclusion_failure(exclusion, connection, tables, control=admin, database=token)

    monkeypatch.setattr(service, "_postgres_exclusion", observed_exclusion)
    try:
        with admin.connect() as connection:
            assert (
                connection.exec_driver_sql("SHOW server_version_num").scalar_one().startswith("16")
            )
            for role, options in (
                (owner, f"LOGIN PASSWORD '{password}'"),
                (app, f"LOGIN NOINHERIT PASSWORD '{password}'"),
                (group, "NOLOGIN"),
            ):
                connection.exec_driver_sql(f"CREATE ROLE {role} {options}")
                roles.append(role)
            connection.exec_driver_sql(
                f"CREATE DATABASE {token} OWNER {owner} TEMPLATE template0 "
                "ENCODING 'LATIN1' LC_COLLATE 'C' LC_CTYPE 'C'"
            )
            database_created = True
        url = admin.url.set(database=token)
        for identity, secret in ((owner, password), (app, password), (url.username, url.password)):
            engines.append(
                create_engine(
                    url.set(username=identity, password=secret),
                    poolclass=NullPool,
                    connect_args={"client_encoding": "UTF8"},
                )
            )
        owner_engine, app_engine, privileged = engines
        with owner_engine.begin() as connection:
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            assert tuple(
                connection.exec_driver_sql(
                    "SELECT pg_encoding_to_char(encoding),datcollate,datctype "
                    "FROM pg_database WHERE datname=current_database()"
                ).one()
            ) == ("LATIN1", "C", "C")
            assert connection.exec_driver_sql("SHOW client_encoding").scalar_one() == "UTF8"
            assert tuple(
                connection.exec_driver_sql(
                    "SELECT rolsuper,rolcreaterole FROM pg_roles WHERE rolname=current_user"
                ).one()
            ) == (False, False)
        wait_for_database_drain(admin, token)
        yield {
            "owner": owner_engine,
            "app": app_engine,
            "admin": privileged,
            "control": admin,
            "owner_role": owner,
            "app_role": app,
            "group_role": group,
        }
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as connection:
            if database_created:
                connection.exec_driver_sql(f"DROP DATABASE {token} WITH (FORCE)")
            for role in reversed(roles):
                connection.exec_driver_sql(f"DROP ROLE {role}")
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": token}
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_roles WHERE rolname IN (:owner,:app,:group)"),
                    {"owner": owner, "app": app, "group": group},
                ).scalar_one()
                == 0
            )
        admin.dispose()


@postgres_only
def test_postgres_latin1_native_bytes_and_utf8_transfer_are_distinct(
    latin1_pg, observed_reader, monkeypatch, record_property
):
    from test_ownership import FRESH

    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state

    case = complete_postgres_ar6(latin1_pg, legacy=False)
    try:
        with case.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved,actor) "
                    "VALUES(:id,'run',1700000000.125,:payload,'queued',false,1,0,:actor)"
                ),
                {
                    "id": "e" * 32,
                    "payload": "café",
                    "actor": FRESH["principal_grants"][0]["principal_id"],
                },
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('job',:id,:project)"),
                {"id": "e" * 32, "project": FRESH["project_id"]},
            )
            native, value = connection.exec_driver_sql(
                "SELECT octet_length(payload),payload FROM jobs"
            ).one()
            assert native == 4 and value == "café" and len(value.encode("utf-8")) == 5
        drain(latin1_pg)
        before = postgres_snapshot(case.engine)
        drain(latin1_pg)
        watch = RowTransferWatch(monkeypatch, {"latin1-financial-payload": "café"})
        engine, outcome = case.operator_engine(), LedgerOutcome()
        try:
            with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
                state = inspect_ledger_state(connection)
                assert state.model_dump(mode="json") == case.expected
            assert outcome.commit_acknowledged and not outcome.cleanup_failed
        finally:
            engine.dispose()
        # The observed wire cell is UTF-8 sized independently of PostgreSQL octets.
        assert watch.hits and all(hit["bytes"] == 5 for hit in watch.hits)
        record_property(
            "encoding_receipt",
            json.dumps(
                {
                    "server_encoding": "LATIN1",
                    "native_bytes": native,
                    "utf8_bytes": 5,
                    "transport_bound": 4 * native,
                    "observed_transfers": watch.hits,
                }
            ),
        )
        drain(latin1_pg)
        assert postgres_snapshot(case.engine) == before
        drain(latin1_pg)
    finally:
        case.dispose()
