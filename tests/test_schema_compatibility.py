"""Real guard negatives: no legacy_behavior_schema fixture is used here."""

import json
import time
from dataclasses import FrozenInstanceError

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from agent_rewind.api import create_app
from agent_rewind.database import Database
from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations import service
from agent_rewind.migrations.schema import HEAD
from agent_rewind.worker import work_once


@pytest.fixture
def prepared(settings):
    db = Database(settings)
    db.migrate(installation_key="synthetic-guard")
    yield db
    db.engine.dispose()


def test_packaged_profile_is_explicitly_inspection_only(prepared):
    profile = guard.load_release_profile()
    assert profile.release == "0.1.0"
    assert [(r.revision, r.mode, r.required_completed_backfills) for r in profile.revisions] == [
        (HEAD, "migration_only", ()),
        (
            "ar_0003_ownership",
            "migration_only",
            (guard.BackfillRequirement(revision="ar_0003_ownership", phase="ownership"),),
        ),
        (
            "ar_0004_artifacts",
            "migration_only",
            (guard.BackfillRequirement(revision="ar_0003_ownership", phase="ownership"),),
        ),
    ]
    result = prepared.schema_compatibility()
    assert (result.status, result.code) == ("incompatible", "migration_only")
    with pytest.raises(FrozenInstanceError):
        result.status = "ready"


@pytest.mark.parametrize("mode", ["customer", "ready", "migration_only,ready"])
def test_adoption_cannot_be_enabled_by_an_injected_profile(prepared, mode):
    profile = guard.load_release_profile()
    forged = profile.model_copy(
        update={"revisions": (profile.revisions[0].model_copy(update={"mode": mode}),)}
    )
    with prepared.engine.connect() as connection:
        result = guard.check_schema_compatibility(connection, forged)
    assert (result.status, result.code) == ("incompatible", "release_profile_invalid")


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM alembic_version",
        "UPDATE alembic_version SET version_num='ar_9999_future'",
        "INSERT INTO alembic_version VALUES ('ar_unknown_parallel')",
        "DELETE FROM installation_adoptions",
        "UPDATE installation_adoptions SET mapping_digest='" + "f" * 64 + "'",
        "UPDATE installation_adoptions SET mapping='not-json'",
        "DROP TABLE migration_progress",
        "ALTER TABLE jobs ADD COLUMN unexpected INTEGER",
    ],
)
def test_metadata_drift_refuses_without_writing_or_reusing_previous_result(prepared, mutation):
    assert prepared.schema_compatibility().code == "migration_only"
    with prepared.engine.begin() as connection:
        connection.exec_driver_sql(mutation)
    before = snapshot(prepared.engine)
    result = prepared.schema_compatibility()
    assert result.status == "incompatible"
    assert result.code == "schema_incompatible"
    assert snapshot(prepared.engine) == before


def snapshot(engine):
    with engine.connect() as connection:
        return tuple(
            connection.exec_driver_sql("SELECT name,type,sql FROM sqlite_master ORDER BY name")
        ), tuple(connection.exec_driver_sql("SELECT * FROM alembic_version"))


def test_missing_database_stays_absent(settings):
    db = Database(settings)
    path = settings.data_dir / "metadata.sqlite"
    assert db.schema_compatibility().status == "incompatible"
    assert not path.exists()
    db.engine.dispose()


@pytest.mark.parametrize("ddl", [None, "CREATE TABLE foreign_metadata (secret TEXT)"])
def test_empty_or_partial_database_is_never_initialized(settings, ddl):
    db = Database(settings)
    with db.engine.begin() as connection:
        if ddl:
            connection.exec_driver_sql(ddl)
    with db.engine.connect() as connection:
        before = tuple(connection.exec_driver_sql("SELECT * FROM sqlite_master"))
    assert db.schema_compatibility().status == "incompatible"
    with db.engine.connect() as connection:
        assert tuple(connection.exec_driver_sql("SELECT * FROM sqlite_master")) == before
    db.engine.dispose()


@pytest.mark.parametrize("status", [None, "pending", "running", "blocked", "complete"])
def test_required_backfill_checked_and_complete_still_cannot_activate(prepared, status):
    document = guard.load_release_profile().model_dump(mode="json")
    document["revisions"][0]["required_completed_backfills"] = [
        {"revision": HEAD, "phase": "synthetic_required_phase"}
    ]
    profile = guard.ReleaseProfile.model_validate_json(json.dumps(document))
    if status:
        with prepared.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO migration_progress VALUES "
                    "(:revision,'synthetic_required_phase',:digest,'{}',0,:status,:updated)"
                ),
                {
                    "revision": HEAD,
                    "digest": "a" * 64,
                    "status": status,
                    "updated": "2026-10-20T00:00:00+00:00",
                },
            )
    with prepared.engine.connect() as connection:
        result = guard.check_schema_compatibility(connection, profile)
    assert result.status == "incompatible"
    assert result.code == ("migration_only" if status == "complete" else "backfill_incomplete")


def test_database_error_is_safe_and_does_not_cache_success(prepared, monkeypatch):
    assert prepared.schema_compatibility().code == "migration_only"

    def fail(*args, **kwargs):
        raise OperationalError("SELECT secret", {}, Exception("private-dsn-secret"))

    monkeypatch.setattr(prepared.engine, "connect", fail)
    result = prepared.schema_compatibility()
    assert (result.status, result.code) == ("unavailable", "schema_unavailable")
    assert "secret" not in repr(result)


def test_inspection_is_read_only_and_restores_sqlite_controls(prepared, monkeypatch):
    def attempt_write(connection):
        connection.exec_driver_sql("CREATE TABLE guard_must_not_write (value TEXT)")

    with prepared.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA busy_timeout=1234")
    monkeypatch.setattr(guard, "catalog", attempt_write)
    assert prepared.schema_compatibility().status == "unavailable"
    with prepared.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 1234
        assert not connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE name='guard_must_not_write'"
        ).first()


def test_sqlite_budget_interrupts_expensive_inspection(prepared, monkeypatch):
    monkeypatch.setattr(guard, "INSPECTION_TIMEOUT_SECONDS", 0.02)

    def expensive(connection):
        connection.exec_driver_sql(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
            "SELECT sum(x) FROM n"
        ).scalar_one()

    monkeypatch.setattr(guard, "catalog", expensive)
    started = time.monotonic()
    assert prepared.schema_compatibility().status == "unavailable"
    assert time.monotonic() - started < 1


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/runs", "get"),
        ("/api/runs", "post"),
        ("/api/runs/abc", "get"),
        ("/api/runs/abc/files/1", "get"),
        ("/api/compare", "get"),
        ("/api/jobs", "get"),
        ("/api/me", "get"),
        ("/api/schema", "get"),
        ("/api/keys", "post"),
        ("/api/branches", "post"),
        ("/api/studies", "post"),
        ("/api/investigations", "post"),
        ("/auth/login", "get"),
        ("/auth/callback", "get"),
        ("/auth/logout", "post"),
    ],
)
def test_all_customer_routes_refuse_before_auth_or_artifacts(settings, path, method, monkeypatch):
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-api-guard")

    def forbidden(*args, **kwargs):
        pytest.fail("Customer data or auth reached before compatibility refusal")

    monkeypatch.setattr(app.state.auth, "principal", forbidden)
    monkeypatch.setattr(app.state.artifacts, "put_json", forbidden)
    monkeypatch.setattr(app.state.artifacts, "json", forbidden)
    with TestClient(app) as client:
        response = getattr(client, method)(path)
    assert response.status_code == 503
    assert response.json()["detail"] == "Service schema is not compatible with this release."
    assert response.headers["cache-control"] == "no-store"
    app.state.db.engine.dispose()


def test_liveness_and_static_do_not_open_or_create_database(settings, monkeypatch):
    app = create_app(settings)

    def forbidden(*args, **kwargs):
        pytest.fail("Safe process inspection must not acquire a database connection")

    monkeypatch.setattr(app.state.db.engine, "connect", forbidden)
    with TestClient(app) as client:
        for path in ["/", "/livez", "/static/app.js"]:
            assert client.get(path).status_code == 200
        assert client.post("/healthz").status_code == 503
    assert not (settings.data_dir / "metadata.sqlite").exists()


def test_claim_and_worker_leave_queued_and_expired_jobs_unchanged(storage, settings, monkeypatch):
    db, artifacts = storage
    queued = db.enqueue("run", "a" * 64, 1, "synthetic")
    expired = db.enqueue("run", "b" * 64, 1, "synthetic")
    with db.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET status='running',owner='old-worker',lease_until=0 WHERE id=:id"),
            {"id": expired},
        )
    before = [db.job(queued), db.job(expired)]

    def forbidden(*args, **kwargs):
        pytest.fail("Artifact or provider accessed on incompatible schema")

    monkeypatch.setattr(artifacts, "json", forbidden)
    monkeypatch.setattr("agent_rewind.worker.ChatPolicy", forbidden)
    with pytest.raises(guard.SchemaNotReady, match="migration_only"):
        db.claim("new-worker")
    with pytest.raises(guard.SchemaNotReady, match="migration_only"):
        work_once(settings, db, artifacts)
    assert [db.job(queued), db.job(expired)] == before


def test_pool_exhaustion_fails_closed_without_background_probe(settings):
    engine = create_engine(settings.database_url, pool_size=1, max_overflow=0, pool_timeout=0.02)
    service.install(engine, "synthetic-pool")
    with engine.connect():
        started = time.monotonic()
        assert guard.runtime_schema_compatibility(engine).status == "unavailable"
        assert time.monotonic() - started < 0.5
    engine.dispose()


@pytest.mark.parametrize(
    "url,valid",
    [
        ("postgresql+psycopg://u:p@127.0.0.1/db", True),
        ("postgresql+psycopg://u:p@[::1]/db", True),
        ("postgresql+psycopg://u:p@tls.example/db?hostaddr=127.0.0.1", True),
        ("postgresql+psycopg://u:p@/db?host=/var/run/postgresql", True),
        ("postgresql+psycopg://u:p@dns.example/db", False),
        ("postgresql+psycopg://u:p@/db?host=127.0.0.1,127.0.0.2", False),
        ("postgresql+psycopg://u:p@/db?service=hidden", False),
    ],
)
def test_production_endpoint_validated_before_any_network(url, valid):
    engine = create_engine(url)
    if valid:
        guard.configure_runtime_engine(engine, production=True)
    else:
        with pytest.raises(service.MigrationRefused):
            guard.configure_runtime_engine(engine, production=True)
    engine.dispose()


def test_runtime_startup_options_are_bounded_and_preserve_tls_identity():
    parameters = {
        "host": "tls.example",
        "hostaddr": "127.0.0.1",
        "sslmode": "verify-full",
        "options": "-capplication_name=synthetic",
    }
    for _ in range(100):
        guard._bounded_connect(None, None, [], parameters)
    assert parameters["options"].count("-csearch_path=") == 1
    assert parameters["connect_timeout"] == 3
    assert parameters["host"] == "tls.example"
    assert parameters["sslmode"] == "verify-full"


def test_unavailable_api_guard_does_not_leak_database_error(settings, monkeypatch):
    app = create_app(settings)
    app.state.db.migrate(installation_key="synthetic-unavailable")

    def disconnected(*args, **kwargs):
        raise OperationalError("private-sql", {}, Exception("private-password"))

    monkeypatch.setattr(app.state.db.engine, "connect", disconnected)
    with TestClient(app) as client:
        response = client.get("/api/runs")
        assert response.status_code == 503
        assert response.json()["detail"] == "A required service is temporarily unavailable."
        assert "private" not in response.text
        assert client.get("/livez").status_code == 200
    app.state.db.engine.dispose()


def test_budget_is_shared_across_many_catalog_queries(prepared, monkeypatch):
    monkeypatch.setattr(guard, "INSPECTION_TIMEOUT_SECONDS", 0.02)
    count = 0

    def many_queries(connection):
        nonlocal count
        for _ in range(100000):
            connection.exec_driver_sql("SELECT 1").scalar_one()
            count += 1
        pytest.fail("Per-query checks never enforced the total inspection work budget")

    monkeypatch.setattr(guard, "catalog", many_queries)
    assert prepared.schema_compatibility().status == "unavailable"
    assert 1 < count < 100000


def test_existing_transaction_is_not_committed_or_rolled_back_by_guard(prepared):
    with prepared.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE installation_adoptions SET installation_key='pending'")
        result = guard.check_schema_compatibility(connection, guard.load_release_profile())
        assert result.status == "incompatible"
        assert connection.in_transaction()
        assert (
            connection.exec_driver_sql(
                "SELECT installation_key FROM installation_adoptions"
            ).scalar_one()
            == "pending"
        )


def test_stalled_probes_are_capped_while_liveness_and_static_respond(settings, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    app = create_app(settings)
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = 0

    def blocked_guard():
        nonlocal calls
        with lock:
            calls += 1
            if calls == 4:
                entered.set()
        if not release.wait(timeout=5):
            raise AssertionError("Test did not release synthetic stalled transport")
        return guard.CompatibilityResult("unavailable", "schema_unavailable")

    monkeypatch.setattr(app.state.db, "schema_compatibility", blocked_guard)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(client.get, "/api/runs") for _ in range(4)]
        try:
            assert entered.wait(timeout=2)
            full = client.get("/api/runs")
            assert full.status_code == 503
            assert full.json()["detail"] == "A required service is temporarily unavailable."
            assert calls == 4
            assert client.get("/healthz").status_code == 503
            assert client.get("/livez").status_code == 200
            assert client.get("/static/app.js").status_code == 200
        finally:
            release.set()
        assert all(future.result(timeout=2).status_code == 503 for future in futures)
        assert (
            client.get("/api/runs").json()["detail"]
            == "A required service is temporarily unavailable."
        )
    assert calls == 5
    app.state.db.engine.dispose()


def test_cancelled_request_retains_capacity_until_its_sync_probe_exits(settings, monkeypatch):
    import asyncio
    import threading

    import httpx

    async def scenario():
        app = create_app(settings)
        entered = asyncio.Event()
        release = threading.Event()
        lock = threading.Lock()
        loop = asyncio.get_running_loop()
        calls = 0

        def blocked_guard():
            nonlocal calls
            with lock:
                calls += 1
                if calls == 4:
                    loop.call_soon_threadsafe(entered.set)
            if not release.wait(timeout=5):
                raise AssertionError("Synthetic blocked probe was not released")
            return guard.CompatibilityResult("unavailable", "schema_unavailable")

        monkeypatch.setattr(app.state.db, "schema_compatibility", blocked_guard)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            tasks = [asyncio.create_task(client.get("/api/runs")) for _ in range(4)]
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                tasks[0].cancel()
                # Allow actual task cancellation to propagate through the ASGI boundary.
                await asyncio.wait({tasks[0]}, timeout=0.05)
                full = await asyncio.wait_for(client.get("/api/runs"), timeout=1)
                assert full.json()["detail"] == "A required service is temporarily unavailable."
                assert calls == 4
                health = await asyncio.wait_for(client.get("/livez"), timeout=1)
                assert health.status_code == 200
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
        app.state.db.engine.dispose()

    asyncio.run(scenario())


def test_closed_sqlite_probe_connection_is_invalidated_and_safely_replaced(prepared, monkeypatch):
    original_catalog = guard.catalog

    def closed_connection(connection):
        connection.connection.driver_connection.close()
        raise OperationalError("private SQL", {}, Exception("private transport failure"))

    monkeypatch.setattr(guard, "catalog", closed_connection)
    result = prepared.schema_compatibility()
    assert result == guard.CompatibilityResult("unavailable", "schema_unavailable")
    monkeypatch.setattr(guard, "catalog", original_catalog)
    assert prepared.schema_compatibility().code == "migration_only"


def test_worker_command_reports_schema_refusal_instead_of_empty_queue(prepared, settings):
    from agent_rewind.worker import serve_worker

    with pytest.raises(SystemExit, match="^worker_schema_refused:migration_only$"):
        serve_worker(settings)


@pytest.mark.parametrize(
    "name,value",
    [
        ("PGSERVICE", "synthetic-hidden"),
        ("PGSERVICEFILE", "/synthetic-service-file"),
        ("PGHOSTADDR", "203.0.113.9"),
        ("PGHOST", "hidden.example"),
        ("PGPORT", "6543"),
    ],
)
def test_hidden_libpq_environment_routing_refuses_before_dbapi(name, value, monkeypatch):
    monkeypatch.setenv(name, value)
    parameters = {"host": "127.0.0.1"}
    if name == "PGHOST":
        parameters = {"hostaddr": "127.0.0.1"}
    with pytest.raises(service.MigrationRefused, match="explicit_runtime_endpoint_required"):
        guard._bounded_connect(None, None, [], parameters, production=True)


@pytest.mark.parametrize(
    "connect_args",
    [
        {"host": "hidden.example"},
        {"hostaddr": "127.0.0.1,127.0.0.2"},
        {"service": "synthetic-hidden"},
        {"port": "5432,5433"},
    ],
)
def test_final_connect_args_are_validated_even_after_url_validation(connect_args, monkeypatch):
    engine = create_engine("postgresql+psycopg://u:p@127.0.0.1/db", connect_args=connect_args)
    guard.configure_runtime_engine(engine, production=True)
    guard.configure_runtime_engine(engine)  # The runtime wrapper cannot downgrade production.

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid effective routing reached DBAPI connect")

    monkeypatch.setattr(engine.dialect, "connect", forbidden)
    with pytest.raises(service.MigrationRefused):
        engine.connect()
    engine.dispose()


def test_legacy_health_checks_connectivity_without_claiming_schema_readiness(settings, monkeypatch):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 503
        assert not (settings.data_dir / "metadata.sqlite").exists()
        app.state.db.migrate(installation_key="synthetic-health")
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.head("/healthz").status_code == 200
        assert (
            client.get("/api/runs").json()["detail"]
            == "Service schema is not compatible with this release."
        )
        with app.state.db.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='ar_future'")
        # Legacy health is connectivity only, even when admission is incompatible.
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/runs").status_code == 503

        def fail(*args, **kwargs):
            raise OperationalError("private SQL", {}, Exception("private DSN"))

        monkeypatch.setattr(app.state.db.engine, "connect", fail)
        response = client.get("/healthz")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert client.get("/livez").status_code == 200
        assert client.head("/livez").status_code == 200
        assert client.get("/livez").json() == {"status": "live"}
    app.state.db.engine.dispose()
