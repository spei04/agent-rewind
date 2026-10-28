"""Offline controls for the restored database's normal runtime inspection factory."""

from contextlib import contextmanager
from types import SimpleNamespace

import psycopg
import pytest
import test_ledger_recovery_restore_postgres as restore
from ledger_reader_fixture import ReaderFixture
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL

from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations.schema import MigrationRefused


@pytest.fixture
def target():
    url = URL.create(
        "postgresql+psycopg",
        username="offline_owner",
        database="offline_restored_target",
        query={"host": "/offline-no-database", "port": "55432"},
    )
    engine = create_engine(url)
    case = ReaderFixture(None, engine, False, "", "", {}, {}, [], {})
    try:
        yield SimpleNamespace(case=case)
    finally:
        engine.dispose()


@pytest.fixture
def capture_factory(monkeypatch):
    engines, disposed, drained = [], [], []

    def factory(*args, **kwargs):
        engine = create_engine(*args, **kwargs)
        engines.append(engine)
        event.listen(engine, "engine_disposed", lambda engine: disposed.append(engine))
        return engine

    monkeypatch.setattr(restore, "create_engine", factory)
    monkeypatch.setattr(restore, "drain", drained.append)
    return engines, disposed, drained


def test_operator_factory_refuses_runtime_without_ledger_claim(target, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("operator guard allowed a physical connection without its claim")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    engine = target.case.operator_engine()
    try:
        with pytest.raises(MigrationRefused) as rejected:
            engine.connect()
        assert rejected.value.code == "migration_database_failure"
        verdict = guard.runtime_schema_compatibility(engine)
        assert verdict == guard.CompatibilityResult(
            "incompatible", "release_profile_or_connection_invalid"
        )
    finally:
        engine.dispose()


def test_restore_helper_reaches_bounded_runtime_dbapi_boundary(
    target, capture_factory, monkeypatch
):
    class PhysicalBoundary(Exception):
        pass

    sentinel = PhysicalBoundary("offline replacement; no database connection")
    observed = []

    def boundary(*args, **params):
        observed.append((args, params))
        raise sentinel

    monkeypatch.setattr(psycopg, "connect", boundary)
    with pytest.raises(PhysicalBoundary) as reached:
        restore.assert_migration_only(target, "offline")
    assert reached.value is sentinel
    engines, disposed, drained = capture_factory
    assert len(engines) == 1 and disposed == engines and drained == ["offline"]
    engine = engines[0]
    assert engine.url == target.case.engine.url
    assert engine.pool.size() == 1 and engine.pool._max_overflow == 0
    assert engine.pool.timeout() == guard.POOL_TIMEOUT_SECONDS
    assert len(observed) == 1
    args, params = observed[0]
    assert args == ()
    assert params["dbname"] == "offline_restored_target"
    assert params["user"] == "offline_owner"
    assert params["host"] == "/offline-no-database" and str(params["port"]) == "55432"
    assert params["connect_timeout"] == guard.CONNECT_TIMEOUT_SECONDS
    assert params["options"].endswith(
        " -cstatement_timeout=2000 -clock_timeout=250 -csearch_path=public,pg_temp"
    )


@pytest.mark.parametrize(
    ("status", "code", "accepted"),
    [
        ("incompatible", "migration_only", True),
        ("incompatible", "release_profile_or_connection_invalid", False),
        ("incompatible", "schema_incompatible", False),
        ("ready", "migration_only", False),
        ("ready", "ready", False),
        ("unavailable", "schema_unavailable", False),
    ],
)
def test_restore_helper_requires_exact_runtime_verdict(
    target, capture_factory, monkeypatch, status, code, accepted
):
    token = object()
    inspected, opened = [], []

    @contextmanager
    def connection_boundary(engine):
        # Keep the actual factory/hook chain; replace only connection and SQL inspection.
        args, params = engine.dialect.create_connect_args(engine.url)
        for hook in engine.dialect.dispatch.do_connect:
            assert hook(engine.dialect, None, args, params) is None
        opened.append(engine)
        yield token

    def inspection(connection, profile, checks):
        assert connection is token and profile.release == "0.1.0"
        checks.check()
        inspected.append(connection)
        return guard.CompatibilityResult(status, code)

    monkeypatch.setattr(guard, "owned_connect", connection_boundary)
    monkeypatch.setattr(guard, "_check_schema_compatibility", inspection)
    if accepted:
        restore.assert_migration_only(target, "offline")
    else:
        with pytest.raises(AssertionError):
            restore.assert_migration_only(target, "offline")
    engines, disposed, drained = capture_factory
    assert len(engines) == 1 and opened == engines and disposed == engines
    assert drained == ["offline"] and inspected == [token]


def test_restore_helper_disposes_and_drains_on_production_endpoint_refusal(target, capture_factory):
    target.case.engine.url = target.case.engine.url.set(query={"host": "unresolved.invalid"})
    with pytest.raises(MigrationRefused) as rejected:
        restore.assert_migration_only(target, "offline")
    assert rejected.value.code == "numeric_runtime_endpoint_required"
    engines, disposed, drained = capture_factory
    assert len(engines) == 1 and disposed == engines and drained == ["offline"]
