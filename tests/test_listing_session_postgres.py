"""Opt-in PostgreSQL native read-session limits and physical-pool cleanup.

Only the existing disposable PostgreSQL fixture is used. A nonsuperuser owner
proves transaction read-only enforcement; a separate SELECT-only role proves
the reader needs no write grant. Native pg_sleep is a timeout target, never
sleep-based synchronization. All asserted driver identities remain in memory.

The close-failure case intentionally requires A's follow-up to f78995d; it must
not be weakened to accept a checked-out physical connection after failed close.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migrations
from psycopg.pq import TransactionStatus
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.pool import QueuePool

from agent_rewind import listing_session
from agent_rewind.errors import Fault
from agent_rewind.listing_session import SQLWork, listing_connection

pg = migrations.pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")

SETTINGS = (
    "SELECT current_setting('transaction_isolation'),"
    "current_setting('transaction_read_only'),"
    "current_setting('statement_timeout'),current_setting('lock_timeout')"
)
ORIGINAL = ("serializable", "off", "5s", "1250ms")


@pytest.fixture
def sessions(pg):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE listing_sample (id INTEGER PRIMARY KEY,value INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO listing_sample VALUES (1,10)")
        role = pg["app_role"]  # Fixture-generated identifier, never caller input.
        connection.exec_driver_sql(f"GRANT SELECT ON listing_sample TO {role}")
    engines = {
        role: create_engine(
            pg[role].url,
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=2,
            isolation_level="SERIALIZABLE",
            connect_args={"options": "-c statement_timeout=5000 -c lock_timeout=1250"},
        )
        for role in ("owner", "app")
    }
    try:
        yield engines
    finally:
        for engine in engines.values():
            engine.dispose()


def clean_pool(engine, *, same=None, discarded=None):
    assert engine.pool.checkedout() == 0
    if discarded is not None:
        assert discarded.closed
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        assert raw.info.transaction_status == TransactionStatus.IDLE
        assert raw.autocommit is False
        if same is not None:
            assert raw is same
        if discarded is not None:
            assert raw is not discarded
        assert tuple(connection.exec_driver_sql(SETTINGS).one()) == ORIGINAL
    assert engine.pool.checkedout() == 0
    assert raw.info.transaction_status == TransactionStatus.IDLE
    return raw


@contextmanager
def error_codes(engine):
    codes = []

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    event.listen(engine, "handle_error", observed)
    try:
        yield codes
    finally:
        event.remove(engine, "handle_error", observed)


def test_postgres_session_native_modes_and_local_settings_restore(sessions):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    work = SQLWork()
    with listing_connection(engine, work) as connection:
        assert connection.connection.driver_connection is raw
        isolation, read_only, statement_ms, lock_ms = connection.exec_driver_sql(
            "SELECT current_setting('transaction_isolation'),"
            "current_setting('transaction_read_only'),"
            "(SELECT setting::int FROM pg_settings WHERE name='statement_timeout'),"
            "(SELECT setting::int FROM pg_settings WHERE name='lock_timeout')"
        ).one()
        assert (isolation, read_only) == ("read committed", "on")
        assert 0 < statement_ms <= 2000
        assert 0 < lock_ms <= min(250, statement_ms)
        assert raw.info.transaction_status == TransactionStatus.INTRANS
        assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
    count = work.statements
    assert count == 2 and work.seconds > 0 and work.started is None
    clean_pool(engine, same=raw)
    assert work.statements == count  # Connection-local callbacks did not escape.


def test_postgres_session_select_only_role_needs_no_mutation_privilege(sessions):
    engine = sessions["app"]
    with listing_connection(engine, SQLWork()) as connection:
        assert connection.exec_driver_sql(
            "SELECT has_table_privilege(current_user,'listing_sample','SELECT'),"
            "has_table_privilege(current_user,'listing_sample','UPDATE'),"
            "has_table_privilege(current_user,'listing_sample','INSERT'),"
            "has_schema_privilege(current_user,'public','CREATE')"
        ).one() == (True, False, False, False)
        assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
    clean_pool(engine)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO listing_sample VALUES (2,20)",
        "CREATE TABLE listing_forbidden (id INTEGER)",
    ],
)
def test_postgres_session_refuses_normally_authorized_dml_and_ddl(sessions, statement):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'listing_sample','INSERT'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, True)
    with (
        error_codes(engine) as codes,
        pytest.raises(Fault) as caught,
        listing_connection(engine, SQLWork()) as connection,
    ):
        connection.exec_driver_sql(statement)
    assert caught.value.code == "dependency_unavailable"
    assert codes == ["25006"]  # read_only_sql_transaction, not missing role grants.
    clean_pool(engine, discarded=raw)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM listing_sample").scalar_one() == 1
        assert connection.exec_driver_sql(
            "SELECT to_regclass('public.listing_forbidden') IS NULL"
        ).scalar_one()


def test_postgres_session_second_statement_observes_committed_change(pg, sessions):
    engine = sessions["app"]
    with listing_connection(engine, SQLWork()) as reader:
        raw = reader.connection.driver_connection
        transaction = reader.get_transaction()
        assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
        with pg["owner"].connect() as writer:
            writer.exec_driver_sql("UPDATE listing_sample SET value=20 WHERE id=1")
            assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
            writer.commit()  # Explicit barrier; no timing assumption.
        assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 20
        assert reader.get_transaction() is transaction and transaction.is_active
        assert reader.connection.driver_connection is raw
    clean_pool(engine, same=raw)


def test_postgres_native_statement_timeout_cancels_and_discards(sessions, monkeypatch):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    monkeypatch.setattr(listing_session, "MAX_SQL_SECONDS", 0.25)
    work = SQLWork()
    with (
        error_codes(engine) as codes,
        pytest.raises(Fault) as caught,
        listing_connection(engine, work) as connection,
    ):
        # This server operation must be cancelled by SET LOCAL, not by a
        # Python timeout wrapper returning while SQL continues in the pool.
        connection.exec_driver_sql("SELECT pg_sleep(10)").one()
    assert caught.value.code == "dependency_unavailable"
    assert codes == ["57014"]  # query_canceled from PostgreSQL's native timeout.
    assert work.statements == 1 and work.seconds > 0 and work.started is None
    clean_pool(engine, discarded=raw)


def test_postgres_native_lock_timeout_releases_reader_and_keeps_failed_work(pg, sessions):
    engine = sessions["app"]
    raw = clean_pool(engine)
    work = SQLWork()
    with pg["owner"].connect() as blocker:
        blocker.exec_driver_sql("LOCK TABLE listing_sample IN ACCESS EXCLUSIVE MODE")
        # Acquiring the lock is the barrier. It remains held until the reader's
        # native timeout returns; no race to release it on an assumed delay.
        with (
            error_codes(engine) as codes,
            pytest.raises(Fault) as caught,
            listing_connection(engine, work) as reader,
        ):
            reader.exec_driver_sql("SELECT value FROM listing_sample").one()
        assert caught.value.code == "dependency_unavailable"
        assert codes == ["55P03"]  # lock_not_available, not statement_timeout.
        blocker.rollback()
    assert work.statements == 1 and work.seconds > 0 and work.started is None
    spent = work.seconds
    clean_pool(engine, discarded=raw)
    with listing_connection(engine, work) as connection:
        assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
    assert work.statements == 2 and work.seconds >= spent


def test_postgres_remaining_native_time_is_shared_across_connections(sessions, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    engine = sessions["owner"]
    work = SQLWork(seconds=1.5)
    with listing_connection(engine, work) as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT setting::int FROM pg_settings WHERE name='statement_timeout'"
            ).scalar_one()
            == 500
        )
        clock[0] = 0.25
    assert work.seconds == 1.75
    clock[0] = 100.0  # Time between SQL phases is not charged as SQL work.
    with listing_connection(engine, work) as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT setting::int FROM pg_settings WHERE name='statement_timeout'"
            ).scalar_one()
            == 250
        )
        clock[0] = 100.125
    assert work.seconds == 1.875 and work.statements == 2 and work.started is None
    clean_pool(engine)


def test_postgres_statement_budget_does_not_reset_with_a_new_connection(sessions, monkeypatch):
    monkeypatch.setattr(listing_session, "MAX_STATEMENTS", 2)
    engine = sessions["owner"]
    work = SQLWork()
    for _ in range(2):
        with listing_connection(engine, work) as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    with pytest.raises(Fault) as caught, listing_connection(engine, work) as connection:
        connection.exec_driver_sql("SELECT 1")
    assert caught.value.code == "dependency_unavailable"
    assert work.statements == 3 and work.started is None
    clean_pool(engine)


def test_postgres_final_parse_tail_cannot_return_after_shared_deadline(sessions, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(listing_session, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    engine = sessions["owner"]
    raw = clean_pool(engine)
    work = SQLWork()
    with pytest.raises(Fault) as caught, listing_connection(engine, work) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        clock[0] = 3.0
    assert caught.value.code == "dependency_unavailable"
    assert work.seconds == 3 and work.started is None
    clean_pool(engine, same=raw)


@pytest.mark.parametrize("mode", ["engine_autocommit", "pooled_autocommit", "pooled_transaction"])
def test_postgres_unsupported_effective_mode_discards_before_reader(sessions, mode):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    target = engine
    if mode == "engine_autocommit":
        target = engine.execution_options(isolation_level="AUTOCOMMIT")
    elif mode == "pooled_autocommit":
        raw.autocommit = True  # Simulate an unsupported external pool mutation.
    else:
        with raw.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
        assert raw.info.transaction_status == TransactionStatus.INTRANS
    work = SQLWork()
    with pytest.raises(Fault) as caught, listing_connection(target, work):
        pytest.fail("Unsupported connection mode must not reach the reader")
    assert caught.value.code == "dependency_unavailable"
    assert work.statements == 0
    clean_pool(engine, discarded=raw)


@pytest.mark.parametrize("stage", ["partial_registration", "listener_removal"])
def test_postgres_listener_failure_discards_native_session(sessions, monkeypatch, stage):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    listen, remove = event.listen, event.remove
    injected = []

    def failed_listen(target, name, callback, *args, **kwargs):
        listen(target, name, callback, *args, **kwargs)
        if isinstance(target, Connection) and name == "after_cursor_execute" and not injected:
            injected.append(True)
            raise RuntimeError("synthetic-listener-canary")

    def failed_remove(target, name, callback):
        if isinstance(target, Connection) and not injected:
            injected.append(True)
            raise RuntimeError("synthetic-listener-canary")
        remove(target, name, callback)

    with monkeypatch.context() as patch:
        if stage == "partial_registration":
            patch.setattr(event, "listen", failed_listen)
        else:
            patch.setattr(event, "remove", failed_remove)
        with pytest.raises(Fault) as caught, listing_connection(engine, SQLWork()) as connection:
            if stage == "partial_registration":
                pytest.fail("Partial registration must not reach the reader")
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert injected == [True] and caught.value.code == "dependency_unavailable"
    assert "canary" not in str(caught.value)
    clean_pool(engine, discarded=raw)


@pytest.mark.parametrize("stage", ["rollback", "close"])
def test_postgres_native_cleanup_failure_discards_physical_connection(sessions, monkeypatch, stage):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    target = []
    injected = []
    original = getattr(Connection, stage)

    def fail_once(connection):
        if target and connection is target[0] and not injected:
            injected.append(True)
            raise RuntimeError("synthetic-cleanup-canary")
        return original(connection)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(Connection, stage, fail_once)
            with (
                pytest.raises(Fault) as caught,
                listing_connection(engine, SQLWork()) as connection,
            ):
                target.append(connection)
                assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert injected == [True] and caught.value.code == "dependency_unavailable"
        assert "canary" not in str(caught.value)
        clean_pool(engine, discarded=raw)
    finally:
        # Keep the disposable fixture releasable even when the regression fails.
        for connection in target:
            connection.close()
