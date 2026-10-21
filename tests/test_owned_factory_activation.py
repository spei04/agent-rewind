"""Narrow Database factory selection; no operation service/profile activation."""

import sqlite3

import pytest
from sqlalchemy import create_engine

from agent_rewind import database as database_module
from agent_rewind import sqlite_ownership as ownership
from agent_rewind.database import Database
from agent_rewind.migrations.compatibility import CONNECT_TIMEOUT_SECONDS, POOL_TIMEOUT_SECONDS
from agent_rewind.sqlite_ownership import SQLiteOwnershipError, owned_connect, require_owned_sqlite


@pytest.mark.parametrize("driver", ["sqlite", "sqlite+pysqlite"])
@pytest.mark.parametrize("name", ["plain.sqlite", "with spaces.sqlite", "prefix:memory:.sqlite"])
def test_supported_file_factory_is_lazy_owned_and_keeps_timeouts(
    settings, tmp_path, monkeypatch, driver, name
):
    path = tmp_path / name
    calls = []
    original_connect = sqlite3.connect

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    database = Database(settings.model_copy(update={"database_url": f"{driver}:///{path}"}))
    try:
        require_owned_sqlite(database.engine)
        assert calls == [] and not path.exists()
        assert database.engine.pool.timeout() == POOL_TIMEOUT_SECONDS
        with owned_connect(database.engine) as connection:
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == (
                CONNECT_TIMEOUT_SECONDS * 1000
            )
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert len(calls) == 1 and path.exists()
        assert calls[0][1]["check_same_thread"] is False
        assert calls[0][1]["timeout"] == CONNECT_TIMEOUT_SECONDS
        assert database.engine.pool.checkedout() == 0
    finally:
        database.engine.dispose()


def test_relative_file_is_owned_without_opening_or_resolving_it(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("constructor connected")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    database = Database(settings.model_copy(update={"database_url": "sqlite:///relative.sqlite"}))
    try:
        require_owned_sqlite(database.engine)
        assert database.engine.url.database == "relative.sqlite"
    finally:
        database.engine.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite+pysqlite:///:memory:",
        "sqlite:///file:memory?mode=memory&cache=shared&uri=true",
        "sqlite:///file:relative.sqlite",
        "sqlite:///plain.sqlite?timeout=7",
        "sqlite:///plain.sqlite?uri=true",
        "sqlite://host/plain.sqlite",
        "sqlite://user@host/plain.sqlite",
        "sqlite://user:secret@host:123/plain.sqlite",
        "sqlite+other:///plain.sqlite",
        "postgresql+psycopg://synthetic@127.0.0.1:5432/synthetic",
    ],
)
def test_unsupported_forms_use_unchanged_legacy_construction_policy(settings, monkeypatch, url):
    engine = object()
    calls = []

    def legacy(value, **kwargs):
        calls.append(("legacy", value, kwargs))
        return engine

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported URL acquired an owned factory")

    def configure(value, **kwargs):
        calls.append(("configure", value, kwargs))

    monkeypatch.setattr(database_module, "create_engine", legacy)
    monkeypatch.setattr(database_module, "create_owned_sqlite_engine", forbidden)
    monkeypatch.setattr(database_module, "configure_runtime_engine", configure)
    assert Database(settings.model_copy(update={"database_url": url})).engine is engine
    expected = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        expected["connect_args"] = {"check_same_thread": False, "timeout": CONNECT_TIMEOUT_SECONDS}
    if ":memory:" not in url and url != "sqlite://":
        expected["pool_timeout"] = POOL_TIMEOUT_SECONDS
    assert calls == [("legacy", url, expected), ("configure", engine, {"production": False})]


@pytest.mark.parametrize(
    "url", ["sqlite://", "sqlite:///:memory:", "sqlite:///unused.sqlite?timeout=7"]
)
def test_real_legacy_engines_are_not_certified(settings, url):
    database = Database(settings.model_copy(update={"database_url": url}))
    try:
        with pytest.raises(SQLiteOwnershipError):
            require_owned_sqlite(database.engine)
    finally:
        database.engine.dispose()


def test_injected_engine_is_not_automatically_certified(settings):
    database = Database(settings)
    original = database.engine
    injected = create_engine("sqlite://")
    try:
        require_owned_sqlite(original)
        database.engine = injected
        with pytest.raises(SQLiteOwnershipError):
            require_owned_sqlite(database.engine)
        with injected.connect() as connection:
            assert ownership.owned_receipt(connection) is None
    finally:
        original.dispose()
        injected.dispose()


@pytest.mark.parametrize("production", [False, True])
def test_postgresql_factory_is_lazy_untracked_and_preserves_configuration(
    settings, monkeypatch, production
):
    import psycopg

    configured = []
    original = database_module.configure_runtime_engine

    def forbidden(*args, **kwargs):
        pytest.fail("constructor connected to PostgreSQL")

    def configure(engine, **kwargs):
        configured.append((engine, kwargs))
        return original(engine, **kwargs)

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(database_module, "configure_runtime_engine", configure)
    database = Database(
        settings.model_copy(
            update={
                "mode": "production" if production else "development",
                "database_url": "postgresql+psycopg://synthetic@127.0.0.1:5432/synthetic",
            }
        )
    )
    try:
        assert database.engine.dialect.driver == "psycopg"
        assert database.engine.pool.timeout() == POOL_TIMEOUT_SECONDS
        assert configured == [(database.engine, {"production": production})]
        with pytest.raises(SQLiteOwnershipError):
            require_owned_sqlite(database.engine)
    finally:
        database.engine.dispose()
