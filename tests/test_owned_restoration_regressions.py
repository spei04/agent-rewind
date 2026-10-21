"""Failed native restoration cannot certify a dirty owned pool return."""

import sqlite3

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection
from test_owned_caller_integration import engine

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.migrations.compatibility import _inspection
from agent_rewind.projection_source import QueryBudget, readonly_source
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.sqlite_ownership import owned_connect

__all__ = ["engine"]


def clean_replacement(engine, previous):
    assert engine.pool.checkedout() == 0
    with pytest.raises(sqlite3.ProgrammingError):
        previous.execute("SELECT 1")
    with owned_connect(engine) as connection:
        current = connection.connection.driver_connection
        assert current is not previous
        assert not current.in_transaction
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 3000
        assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
        connection.exec_driver_sql("INSERT INTO proof VALUES(2)")
        connection.rollback()
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("fault", ["query_only", "busy_timeout", "listener"])
@pytest.mark.parametrize("denial", [False, True])
def test_inspection_cleanup_and_pre_action_invalidate_failure_quarantines(
    engine, monkeypatch, fault, denial
):
    original_execute = ownership._TrackedSQLite.execute
    original_remove = event.remove
    primary = ResourceNotFound()
    cleanup_error = RuntimeError("PRIVATE-RESTORE")
    failures = []
    invalidates = []

    def execute(raw, statement, *args, **kwargs):
        target = "PRAGMA query_only=0" if fault == "query_only" else "PRAGMA busy_timeout=741"
        if fault != "listener" and statement == target:
            failures.append(statement)
            raise cleanup_error
        return original_execute(raw, statement, *args, **kwargs)

    def remove(target, name, callback):
        original_remove(target, name, callback)
        if fault == "listener" and name == "before_cursor_execute":
            failures.append(name)
            raise cleanup_error

    def invalidate(connection, *args, **kwargs):
        invalidates.append(connection)
        raise RuntimeError("PRIVATE-INVALIDATE")

    with monkeypatch.context() as patch:
        patch.setattr(ownership._TrackedSQLite, "execute", execute)
        patch.setattr(event, "remove", remove)
        patch.setattr(Connection, "invalidate", invalidate)
        with (
            pytest.raises(ResourceNotFound if denial else RuntimeError) as caught,
            owned_connect(engine) as connection,
            _inspection(connection),
        ):
            raw = connection.connection.driver_connection
            receipt = raw._ownership.receipt
            assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
            if denial:
                raise primary
    assert failures and invalidates
    clean_replacement(engine, raw)
    assert receipt.failed and receipt.disposal_acknowledged
    assert caught.value is (primary if denial else cleanup_error)


@pytest.mark.parametrize("denial", [False, True])
def test_projection_restore_failure_cannot_return_dirty_query_only(engine, denial):
    primary = ResourceNotFound()
    cleanup_error = RuntimeError("PRIVATE-PROJECTION-RESTORE")
    failures = []

    def before(connection, cursor, statement, *args):
        if statement == "PRAGMA query_only=0":
            failures.append(statement)
            raise cleanup_error

    event.listen(engine, "before_cursor_execute", before)
    try:
        with (
            pytest.raises((RuntimeError, ResourceNotFound)) as caught,
            readonly_source(engine, QueryBudget()) as connection,
        ):
            raw = connection.connection.driver_connection
            receipt = raw._ownership.receipt
            assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
            if denial:
                raise primary
    finally:
        event.remove(engine, "before_cursor_execute", before)
    assert failures == ["PRAGMA query_only=0"]
    clean_replacement(engine, raw)
    assert receipt.failed and receipt.disposal_acknowledged
    assert caught.value is (primary if denial else cleanup_error)


@pytest.mark.parametrize("denial", [False, True])
def test_projection_attempts_remaining_cleanup_and_preserves_primary_or_first_interrupt(
    engine, monkeypatch, denial
):
    primary = ResourceNotFound()
    first_interrupt = KeyboardInterrupt("FIRST-CLEANUP")
    later_interrupt = SystemExit("LATER-CLEANUP")
    calls = []

    def rollback(connection):
        calls.append("rollback")
        if len(calls) == 1:
            raise RuntimeError("EARLIER-ORDINARY")
        raise later_interrupt

    def before(connection, cursor, statement, *args):
        if statement == "PRAGMA query_only=0":
            calls.append("restore")
            raise first_interrupt

    event.listen(engine, "before_cursor_execute", before)
    try:
        with (
            monkeypatch.context() as patch,
            pytest.raises(ResourceNotFound if denial else KeyboardInterrupt) as caught,
            readonly_source(engine, QueryBudget()) as connection,
        ):
            raw = connection.connection.driver_connection
            connection.exec_driver_sql("SELECT 1")
            patch.setattr(Connection, "rollback", rollback)
            if denial:
                raise primary
    finally:
        event.remove(engine, "before_cursor_execute", before)
    assert calls == ["rollback", "restore", "rollback"]
    assert caught.value is (primary if denial else first_interrupt)
    clean_replacement(engine, raw)


@pytest.mark.parametrize("state", ["closed", "invalidated"])
def test_receipt_capture_never_revalidates_a_released_or_invalidated_connection(engine, state):
    with owned_connect(engine) as connection:
        receipt = ownership.owned_receipt(connection)
        assert receipt.connection is connection
        getattr(connection, "close" if state == "closed" else "invalidate")()
        with pytest.raises(ownership.SQLiteOwnershipError):
            ownership.owned_receipt(connection)
    assert engine.pool.checkedout() == 0
    with owned_connect(engine) as connection:
        assert ownership.owned_receipt(connection) is not receipt
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


@pytest.mark.parametrize("close", [False, True])
def test_capture_and_inspection_preserve_outstanding_registered_predecessor(engine, close):
    previous_pool = engine.pool
    try:
        with owned_connect(engine) as connection:
            original = ownership.owned_receipt(connection)
            engine.dispose(close=close)
            successor = engine.pool
            assert successor is not previous_pool
            assert ownership.owned_receipt(connection) is original
            with owned_connect(engine) as newer:
                new_receipt = ownership.owned_receipt(newer)
                with _inspection(connection):
                    assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
                assert new_receipt is ownership.owned_receipt(newer)
                assert newer.exec_driver_sql("SELECT 2").scalar_one() == 2
                assert not new_receipt.failed
            assert original is ownership.owned_receipt(connection)
        assert ownership.cleanup_snapshot(original).clean
        assert connection.closed and not original.proxy.is_valid
        assert original.returned and successor.checkedout() == 0
    finally:
        previous_pool.dispose()


def test_retained_receipt_capture_refuses_foreign_pool_without_poisoning_owner(engine):
    from sqlalchemy.pool import QueuePool

    original_pool = engine.pool
    replacement = QueuePool(lambda: sqlite3.connect(":memory:"))
    try:
        with owned_connect(engine) as connection:
            receipt = ownership.owned_receipt(connection)
            engine.pool = replacement
            try:
                with pytest.raises(ownership.SQLiteOwnershipError):
                    ownership.owned_receipt(connection)
                assert not receipt.failed
            finally:
                engine.pool = original_pool
            assert ownership.owned_receipt(connection) is receipt
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert ownership.cleanup_snapshot(receipt).clean
        assert engine.pool.checkedout() == 0
    finally:
        replacement.dispose()
