"""Real least-privilege runtime guard tests on the synthetic PostgreSQL16 service."""

import time

import pytest
import test_migrations_postgres as migration_cases
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from agent_rewind.api import create_app
from agent_rewind.database import Database
from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations import service
from agent_rewind.worker import work_once

pg = migration_cases.pg
pytestmark = pytest.mark.skipif(
    not migration_cases.POSTGRES, reason="Opt-in synthetic PostgreSQL integration"
)


def runtime_database(pg, settings):
    service.install(pg["owner"], "synthetic-guard-postgres")
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {pg['app_role']}")
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    settings.database_url = pg["app"].url.render_as_string(hide_password=False)
    return Database(settings)


def test_least_privilege_inspection_does_not_authorize_customer_or_ddl(pg, settings):
    db = runtime_database(pg, settings)
    assert db.schema_compatibility() == guard.CompatibilityResult("incompatible", "migration_only")
    for statement in [
        "CREATE TABLE public.forbidden (id INTEGER)",
        "ALTER TABLE public.jobs ADD COLUMN forbidden INTEGER",
        "UPDATE public.alembic_version SET version_num='forbidden'",
    ]:
        with db.engine.connect() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql(statement)
    db.engine.dispose()


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM alembic_version",
        "UPDATE alembic_version SET version_num='ar_9999_future'",
        "INSERT INTO alembic_version VALUES ('ar_parallel')",
        "DELETE FROM installation_adoptions",
        "UPDATE installation_adoptions SET mapping_digest='" + "f" * 64 + "'",
        "DROP TABLE migration_progress",
    ],
)
def test_postgres_mutated_metadata_refuses_each_new_check(pg, settings, mutation):
    db = runtime_database(pg, settings)
    assert db.schema_compatibility().code == "migration_only"
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(mutation)
    assert db.schema_compatibility().status == "incompatible"
    with pg["owner"].connect() as connection:
        expected = tuple(connection.exec_driver_sql("SELECT version_num FROM alembic_version"))
    assert db.schema_compatibility().status == "incompatible"
    with pg["owner"].connect() as connection:
        assert (
            tuple(connection.exec_driver_sql("SELECT version_num FROM alembic_version")) == expected
        )
    db.engine.dispose()


def test_postgres_api_and_worker_cannot_touch_customer_data(pg, settings, monkeypatch):
    db = runtime_database(pg, settings)
    with pg["owner"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs (id,kind,created,payload,status,cancel,budget,reserved) "
                "VALUES (:id,'run',1,:payload,'queued',false,100,0)"
            ),
            {"id": "a" * 32, "payload": "b" * 64},
        )
    app = create_app(settings)

    def forbidden(*args, **kwargs):
        pytest.fail("An incompatible runtime accessed customer artifacts or a provider")

    monkeypatch.setattr(app.state.artifacts, "json", forbidden)
    monkeypatch.setattr("agent_rewind.worker.ChatPolicy", forbidden)
    with TestClient(app) as client:
        assert client.get("/api/runs").status_code == 503
        assert client.post("/api/runs", json={}).status_code == 503
        assert client.get("/healthz").status_code == 200
    with pytest.raises(guard.SchemaNotReady, match="migration_only"):
        db.claim("synthetic-worker")
    assert work_once(settings, db, app.state.artifacts) is False
    with pg["owner"].connect() as connection:
        assert connection.exec_driver_sql("SELECT status,owner,reserved FROM jobs").one() == (
            "queued",
            None,
            0,
        )
    app.state.db.engine.dispose()
    db.engine.dispose()


def test_postgres_locked_metadata_returns_unavailable_with_server_lock_bound(pg, settings):
    db = runtime_database(pg, settings)
    with pg["owner"].begin() as blocker:
        blocker.exec_driver_sql("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE")
        started = time.monotonic()
        result = db.schema_compatibility()
        # Responsive local CI transport only; this is not a network-partition bound.
        assert time.monotonic() - started < 3
        assert result == guard.CompatibilityResult("unavailable", "schema_unavailable")
    assert db.schema_compatibility().code == "migration_only"
    db.engine.dispose()


def test_postgres_inspection_is_read_only_and_server_query_budgeted(pg, settings, monkeypatch):
    db = runtime_database(pg, settings)

    def write(connection):
        connection.exec_driver_sql("CREATE TABLE forbidden_runtime_write (id INTEGER)")

    monkeypatch.setattr(guard, "catalog", write)
    # Even an owner connection is constrained by the guard's read-only transaction.
    assert guard.runtime_schema_compatibility(pg["owner"]).status == "unavailable"

    def slow(connection):
        connection.exec_driver_sql("SELECT pg_catalog.pg_sleep(5)")

    monkeypatch.setattr(guard, "catalog", slow)
    monkeypatch.setattr(guard, "INSPECTION_TIMEOUT_SECONDS", 0.05)
    started = time.monotonic()
    assert db.schema_compatibility().status == "unavailable"
    assert time.monotonic() - started < 1
    db.engine.dispose()


def test_postgres_guard_uses_read_only_transaction_and_no_ddl(pg, settings):
    db = runtime_database(pg, settings)
    queries = []

    def observed(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement.strip().upper())

    event.listen(db.engine, "before_cursor_execute", observed)
    assert db.schema_compatibility().code == "migration_only"
    assert "SET TRANSACTION READ ONLY" in queries
    assert all(q.startswith(("SELECT", "SHOW", "SET")) for q in queries)
    assert not any(q.startswith(("CREATE", "ALTER", "DROP", "INSERT", "UPDATE")) for q in queries)
    db.engine.dispose()
