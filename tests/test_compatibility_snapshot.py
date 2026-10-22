"""Native coherent-read lifecycle controls; no operator body is manufactured."""

import sqlite3
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event

from agent_rewind.database import Database
from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.sqlite_ownership import owned_connect


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now


class Native(sqlite3.Connection):
    clock = None
    expire_on = None
    actions = None

    def execute(self, sql, *args, **kwargs):
        result = super().execute(sql, *args, **kwargs)
        self.actions.append(sql)
        if sql == self.expire_on:
            self.clock.now = 2.0
        return result


@pytest.fixture
def native(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(guard, "time", clock)
    path = tmp_path / "snapshot.sqlite"
    raw = sqlite3.connect(path, factory=Native)
    raw.clock = clock
    raw.actions = []
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA busy_timeout=741")
    raw.execute("CREATE TABLE witness(id INTEGER PRIMARY KEY, value TEXT)")
    raw.execute("INSERT INTO witness VALUES(1,'before')")
    raw.commit()
    engine = create_engine("sqlite://", creator=lambda: raw)
    yield engine, raw, clock, path
    engine.dispose()


def restored(connection, raw):
    assert not connection.in_transaction()
    assert not raw.in_transaction
    assert raw.execute("PRAGMA query_only").fetchone() == (0,)
    assert raw.execute("PRAGMA busy_timeout").fetchone() == (741,)
    assert not list(connection.dispatch.before_cursor_execute)


@pytest.mark.parametrize("coherent", [False, True])
def test_opt_in_has_real_snapshot_and_default_keeps_legacy_select_behavior(native, coherent):
    engine, raw, _, path = native
    with engine.connect() as connection:
        with guard._inspection(connection, coherent_snapshot=coherent) as checks:
            assert connection.connection.driver_connection is raw
            assert connection.exec_driver_sql("SELECT value FROM witness").scalar_one() == "before"
            assert raw.in_transaction is coherent
            writer = sqlite3.connect(path, timeout=0.25)
            try:
                writer.execute("UPDATE witness SET value='after' WHERE id=1")
                writer.commit()
            finally:
                writer.close()
            observed = connection.exec_driver_sql("SELECT value FROM witness").scalar_one()
            checks.check()
            assert observed == ("before" if coherent else "after")
            assert raw.execute("PRAGMA query_only").fetchone() == (1,)
        restored(connection, raw)
        assert connection.exec_driver_sql("SELECT value FROM witness").scalar_one() == "after"


@pytest.mark.parametrize("statement", ["PRAGMA query_only=ON", "PRAGMA busy_timeout=250"])
def test_setup_expiry_prevents_begin_and_still_restores(native, statement):
    engine, raw, _, _ = native
    raw.expire_on = statement
    trace = []
    raw.set_trace_callback(trace.append)
    with engine.connect() as connection:
        with (
            pytest.raises(TimeoutError, match="inspection deadline"),
            guard._inspection(connection, coherent_snapshot=True),
        ):
            pytest.fail("expired setup entered body")
        assert "BEGIN" not in trace
        restored(connection, raw)


@pytest.mark.parametrize("phase", ["begin", "body", "restore"])
def test_same_deadline_survives_native_begin_body_and_cleanup(native, phase):
    engine, raw, clock, _ = native
    trace = []

    def observe(sql):
        trace.append(sql)
        if phase == "begin" and sql == "BEGIN":
            clock.now = 2.0

    raw.set_trace_callback(observe)
    if phase == "restore":
        raw.expire_on = "PRAGMA query_only=0"
    entered = False
    with engine.connect() as connection:
        with (
            pytest.raises(TimeoutError, match="inspection deadline"),
            guard._inspection(connection, coherent_snapshot=True),
        ):
            entered = True
            assert connection.exec_driver_sql("SELECT value FROM witness").scalar_one()
            if phase == "body":
                clock.now = 2.0
        assert entered is (phase != "begin")
        assert "ROLLBACK" in trace
        assert "COMMIT" not in trace
        restored(connection, raw)


def test_coherent_refuses_unowned_native_transaction_without_rolling_it_back(native):
    engine, raw, _, _ = native
    with engine.connect() as connection:
        raw.execute("BEGIN")
        try:
            with (
                pytest.raises(MigrationRefused, match="idle_inspection_connection_required"),
                guard._inspection(connection, coherent_snapshot=True),
            ):
                pytest.fail("borrowed native transaction")
            assert raw.in_transaction
            assert raw.execute("PRAGMA query_only").fetchone() == (0,)
        finally:
            raw.rollback()


@pytest.mark.parametrize("coherent", [False, True])
def test_primary_interruption_survives_expiry_and_owned_cleanup(native, coherent):
    engine, raw, clock, _ = native
    interruption = KeyboardInterrupt("fixture interruption")
    with engine.connect() as connection:
        with (
            pytest.raises(KeyboardInterrupt) as observed,
            guard._inspection(connection, coherent_snapshot=coherent),
        ):
            connection.exec_driver_sql("SELECT 1").scalar_one()
            clock.now = 2.0
            raise interruption
        assert observed.value is interruption
        restored(connection, raw)


@pytest.mark.parametrize("stage", ["acquire", "return"])
def test_runtime_deadline_includes_owned_connection_interval(settings, monkeypatch, stage):
    db = Database(settings)
    db.migrate(installation_key="snapshot-budget")
    clock = Clock()
    monkeypatch.setattr(guard, "time", clock)
    original = guard.owned_connect
    targets = []

    @contextmanager
    def delayed(engine):
        with original(engine) as connection:
            event.listen(
                connection,
                "before_cursor_execute",
                lambda c, cu, sql, p, ctx, many: targets.append(sql),
            )
            if stage == "acquire":
                clock.now = 2.0
            yield connection
        if stage == "return":
            clock.now = 2.0

    monkeypatch.setattr(guard, "owned_connect", delayed)
    try:
        result = guard.runtime_schema_compatibility(db.engine)
        assert (result.status, result.code) == ("unavailable", "schema_unavailable")
        assert bool(targets) is (stage == "return")
        assert db.engine.pool.checkedout() == 0
    finally:
        db.engine.dispose()


def test_direct_api_starts_at_its_own_entry(settings, monkeypatch):
    db = Database(settings)
    db.migrate(installation_key="snapshot-direct")
    clock = Clock()
    monkeypatch.setattr(guard, "time", clock)
    try:
        with owned_connect(db.engine) as connection:
            clock.now = 100.0  # Caller time before this API is not its budget.
            result = guard.check_schema_compatibility(connection, guard.load_release_profile())
            assert result.code == "migration_only"
            assert not connection.in_transaction()
    finally:
        db.engine.dispose()
