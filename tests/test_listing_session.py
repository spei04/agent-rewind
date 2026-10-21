"""Native cancellation/cleanup, without timeout threads or arbitrary sleeps."""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import QueuePool

from agent_rewind.errors import Fault
from agent_rewind.listing_session import SQLWork, listing_connection


@pytest.fixture
def engine(tmp_path):
    value = create_engine(
        f"sqlite:///{tmp_path}/work.sqlite", poolclass=QueuePool, pool_size=1, max_overflow=0
    )
    with value.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sample (id INTEGER)")
        connection.exec_driver_sql("INSERT INTO sample VALUES (1)")
    yield value
    value.dispose()


def test_read_only_settings_restored_and_no_retained_snapshot(engine):
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        original = raw.execute("PRAGMA busy_timeout").fetchone()[0]
    work = SQLWork()
    with listing_connection(engine, work) as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT id FROM sample").scalar_one() == 1
        assert not connection.connection.driver_connection.in_transaction
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == original
        assert not connection.connection.driver_connection.in_transaction
    assert work.statements == 2


def test_write_is_refused_and_connection_reusable(engine):
    with (
        pytest.raises(Fault, match="dependency_unavailable"),
        listing_connection(engine, SQLWork()) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO sample VALUES (2)")
    with listing_connection(engine, SQLWork()) as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM sample").scalar_one() == 1


def test_native_vm_interrupt_then_safe_reuse(engine, monkeypatch):
    monkeypatch.setattr("agent_rewind.listing_session.MAX_VM_INSTRUCTIONS", 3000)
    work = SQLWork()
    with (
        pytest.raises(Fault, match="dependency_unavailable"),
        listing_connection(engine, work) as connection,
    ):
        connection.execute(
            text(
                "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1000000) "
                "SELECT sum(n) FROM x"
            )
        ).scalar_one()
    assert 3000 < work.instructions <= 4000
    assert work.started is None
    # Handler was removed: an independently owned connection can run more work.
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert (
            connection.exec_driver_sql(
                "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<5000) "
                "SELECT max(n) FROM x"
            ).scalar_one()
            == 5000
        )


def test_statement_budget_is_shared_across_connections(engine, monkeypatch):
    monkeypatch.setattr("agent_rewind.listing_session.MAX_STATEMENTS", 2)
    work = SQLWork()
    for _ in range(2):
        with listing_connection(engine, work) as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    with (
        pytest.raises(Fault, match="dependency_unavailable"),
        listing_connection(engine, work) as connection,
    ):
        connection.exec_driver_sql("SELECT 1")


def test_time_budget_native_callback(engine, monkeypatch):
    work = SQLWork()
    clock = [0.0]
    monkeypatch.setattr("agent_rewind.listing_session.time.monotonic", lambda: clock[0])
    with (
        pytest.raises(Fault, match="dependency_unavailable"),
        listing_connection(engine, work) as connection,
    ):
        # The callback sees elapsed SQL time; deterministic virtual clock.
        def progress():
            clock[0] = 3.0
            return work.progress()

        connection.connection.driver_connection.set_progress_handler(progress, 1000)
        connection.exec_driver_sql(
            "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<5000) "
            "SELECT max(n) FROM x"
        ).scalar_one()
    assert work.seconds == 3.0


@pytest.mark.parametrize("mode", ["isolation_none", "autocommit_true", "autocommit_false"])
def test_unsupported_sqlite_mode_discards_physical_connection(tmp_path, mode):
    if mode.startswith("autocommit") and not hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        pytest.skip("Python 3.12 sqlite3 driver modes")
    captured = []

    def creator():
        raw = sqlite3.connect(str(tmp_path / "mode.sqlite"))
        if not captured:
            if mode == "isolation_none":
                raw.isolation_level = None
            else:
                raw.autocommit = mode == "autocommit_true"
        captured.append(raw)
        return raw

    engine = create_engine(
        "sqlite://", creator=creator, poolclass=QueuePool, pool_size=1, max_overflow=0
    )
    try:
        with (
            pytest.raises(Fault, match="dependency_unavailable"),
            listing_connection(engine, SQLWork()),
        ):
            raise AssertionError("must refuse before reader")
        with pytest.raises(sqlite3.ProgrammingError):
            captured[0].execute("SELECT 1")
        with listing_connection(engine, SQLWork()) as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert len(captured) == 2
    finally:
        engine.dispose()


def test_final_fetch_parse_tail_cannot_return_over_budget(engine, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("agent_rewind.listing_session.time.monotonic", lambda: clock[0])
    work = SQLWork()
    with (
        pytest.raises(Fault, match="dependency_unavailable"),
        listing_connection(engine, work) as c,
    ):
        assert c.exec_driver_sql("SELECT 1").scalar_one() == 1
        clock[0] = 3.0
    assert work.seconds == 3.0 and work.started is None
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA query_only").scalar_one() == 0


@pytest.mark.parametrize("stage", ["register_first", "register_second", "remove"])
def test_listener_failure_always_closes_and_discards_connection(engine, monkeypatch, stage):
    from sqlalchemy import event

    captured = []
    real_listen, real_remove = event.listen, event.remove

    def listen(connection, name, callback):
        captured.append(connection.connection.driver_connection)
        real_listen(connection, name, callback)
        if (stage == "register_first" and name == "before_cursor_execute") or (
            stage == "register_second" and name == "after_cursor_execute"
        ):
            raise RuntimeError("private-event-setup-canary")

    def remove(connection, name, callback):
        real_remove(connection, name, callback)
        if stage == "remove":
            raise RuntimeError("private-event-cleanup-canary")

    with monkeypatch.context() as patch:
        patch.setattr("agent_rewind.listing_session.event.listen", listen)
        patch.setattr("agent_rewind.listing_session.event.remove", remove)
        with (
            pytest.raises(Fault, match="dependency_unavailable") as result,
            listing_connection(engine, SQLWork()) as c,
        ):
            c.exec_driver_sql("SELECT 1")
        assert "canary" not in str(result.value)
    with pytest.raises(sqlite3.ProgrammingError):
        captured[0].execute("SELECT 1")
    with listing_connection(engine, SQLWork()) as c:
        assert c.connection.driver_connection is not captured[0]
        assert c.exec_driver_sql("SELECT 1").scalar_one() == 1


@pytest.mark.parametrize("stage", ["setup", "restore"])
def test_native_settings_failures_are_safe_and_replace_pool(tmp_path, stage):
    captured = []

    class Failing(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if (stage == "setup" and sql == "PRAGMA query_only") or (
                stage == "restore" and sql == "PRAGMA query_only=0"
            ):
                raise sqlite3.OperationalError("private-native-canary")
            return super().execute(sql, *args, **kwargs)

    def creator():
        raw = sqlite3.connect(
            str(tmp_path / "cleanup.sqlite"),
            factory=Failing if not captured else sqlite3.Connection,
        )
        captured.append(raw)
        return raw

    engine = create_engine(
        "sqlite://", creator=creator, poolclass=QueuePool, pool_size=1, max_overflow=0
    )
    try:
        with (
            pytest.raises(Fault, match="dependency_unavailable") as result,
            listing_connection(engine, SQLWork()) as c,
        ):
            c.exec_driver_sql("SELECT 1")
        assert "canary" not in str(result.value)
        with pytest.raises(sqlite3.ProgrammingError):
            captured[0].execute("SELECT 1")
        with listing_connection(engine, SQLWork()) as c:
            assert c.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert len(captured) == 2
    finally:
        engine.dispose()


def test_preclose_failure_discards_without_retaining_checkout(engine, monkeypatch):
    real_close = Connection.close
    captured = []

    def once(connection):
        if not captured:
            captured.append(connection.connection.driver_connection)
            raise RuntimeError("private-close-canary")
        real_close(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", once)
        with (
            pytest.raises(Fault, match="dependency_unavailable") as failure,
            listing_connection(engine, SQLWork()) as c,
        ):
            assert c.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert "canary" not in str(failure.value)
    assert engine.pool.checkedout() == 0
    with pytest.raises(sqlite3.ProgrammingError):
        captured[0].execute("SELECT 1")
    with listing_connection(engine, SQLWork()) as c:
        assert c.connection.driver_connection is not captured[0]
        assert c.exec_driver_sql("SELECT 1").scalar_one() == 1
