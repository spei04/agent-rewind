"""Independent pooled regressions for A-OP-01/02/03; no PostgreSQL claim."""

import sqlite3
from contextlib import suppress

import pytest
from sqlalchemy.engine import Connection
from test_admission_schema import JOB
from test_admission_transaction import engine, rows
from test_operation_reads import admission_engine, repository, stored

from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.operation_reads import ReceiptBook, read_descriptor
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["engine", "admission_engine", "repository", "stored"]


def release_probe(connection, rollback, close):
    """Failed pre-fix assertions must not retain a checkout or native hooks."""
    if connection is not None and not connection.closed:
        with suppress(BaseException):
            rollback(connection)
        with suppress(BaseException):
            connection.invalidate()
        with suppress(BaseException):
            close(connection)


def test_read_cleanup_accounting_never_skips_native_actions(engine, monkeypatch):
    work = OperationWork()
    original = work.control_attempt
    calls = []
    captured = None
    rollback, close = Connection.rollback, Connection.close

    def fail(kind):
        calls.append(kind)
        if kind in ("rollback", "discard", "close"):
            raise RuntimeError("PRIVATE-ACCOUNTING")
        original(kind)

    monkeypatch.setattr(work, "control_attempt", fail)
    try:
        with (
            pytest.raises(AdmissionError, match="^dependency_unavailable$") as caught,
            operation_connection(engine, work) as connection,
        ):
            captured = connection
            raw = connection.connection.driver_connection
            connection.exec_driver_sql("SELECT 1")
        assert caught.value.__suppress_context__
        assert engine.pool.checkedout() == 0
        assert captured.closed and work._started is None
        assert calls.count("rollback") == 1 and calls.count("close") <= 2
        with pytest.raises(sqlite3.ProgrammingError):
            raw.execute("SELECT 1")
        assert rows(engine) == []
    finally:
        release_probe(captured, rollback, close)


@pytest.mark.parametrize("scope", ["read", "mutation"])
@pytest.mark.parametrize("failure", ["native_rollback", "account_rollback", "native_close"])
@pytest.mark.parametrize("primary_kind", ["denial", "interruption"])
def test_cleanup_interruption_preserves_primary_and_finishes(
    engine, monkeypatch, scope, failure, primary_kind
):
    work = OperationWork()
    outcome = TransactionOutcome()
    expected = ResourceNotFound() if primary_kind == "denial" else SystemExit("PRIMARY")
    secondary = KeyboardInterrupt("PRIVATE-CLEANUP")
    captured = None
    rollback, close = Connection.rollback, Connection.close
    control = work.control_attempt
    fired = []

    def interrupted_rollback(connection):
        if failure == "native_rollback" and not fired:
            fired.append(failure)
            raise secondary
        return rollback(connection)

    def interrupted_close(connection):
        if failure == "native_close" and not fired:
            fired.append(failure)
            raise secondary
        return close(connection)

    def interrupted_account(kind):
        if failure == "account_rollback" and kind == "rollback" and not fired:
            fired.append(failure)
            raise secondary
        return control(kind)

    monkeypatch.setattr(Connection, "rollback", interrupted_rollback)
    monkeypatch.setattr(Connection, "close", interrupted_close)
    monkeypatch.setattr(work, "control_attempt", interrupted_account)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with pytest.raises(BaseException) as caught, manager as connection:
            captured = connection
            raw = connection.connection.driver_connection
            if scope == "mutation":
                connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
            raise expected
        assert fired == [failure]
        assert caught.value is expected and caught.value.__suppress_context__
        assert engine.pool.checkedout() == 0 and captured.closed
        assert work._started is None and work._connection is None
        if scope == "mutation":
            assert outcome.cleanup_failed and outcome.rollback_attempted
            assert outcome.rollback_acknowledged is (failure != "native_rollback")
            assert not outcome.commit_attempted
        if failure != "account_rollback" or scope == "read":
            with pytest.raises(sqlite3.ProgrammingError):
                raw.execute("SELECT 1")
        assert rows(engine) == []
    finally:
        release_probe(captured, rollback, close)


@pytest.mark.parametrize("scope", ["read", "mutation"])
def test_first_cleanup_interruption_without_primary_is_rethrown_after_release(
    engine, monkeypatch, scope
):
    work = OperationWork()
    outcome = TransactionOutcome()
    expected = KeyboardInterrupt("PRIVATE-FIRST")
    later = SystemExit("PRIVATE-LATER")
    captured = None
    rollback, close = Connection.rollback, Connection.close
    control = work.control_attempt
    calls = []

    def interrupted(kind):
        if kind in ("close", "discard"):
            calls.append(kind)
            raise expected if len(calls) == 1 else later
        return control(kind)

    monkeypatch.setattr(work, "control_attempt", interrupted)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with pytest.raises(BaseException) as caught, manager as connection:
            captured = connection
            if scope == "mutation":
                connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        assert caught.value is expected and caught.value.__suppress_context__
        assert captured.closed and engine.pool.checkedout() == 0
        assert work._started is None
        if scope == "mutation":
            assert outcome.commit_acknowledged and outcome.cleanup_failed
        assert rows(engine) == ([1] if scope == "mutation" else [])
    finally:
        release_probe(captured, rollback, close)


@pytest.mark.parametrize("reuse_book", [False, True])
def test_sqlite_timestamp_blob_cannot_equal_original_descriptor_receipt(stored, reuse_book):
    book = ReceiptBook()
    with stored.engine.connect() as connection:
        descriptor, original = read_descriptor(
            connection, stored.context, JOB, "admission_config", book
        )
        timestamp = connection.exec_driver_sql(
            "SELECT created_at FROM artifact_objects WHERE id=?", (descriptor.id,)
        ).scalar_one()
    assert type(timestamp) is str
    with stored.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE artifact_objects SET created_at=? WHERE id=?",
            (timestamp.encode("utf-8"), descriptor.id),
        )
    selected = book if reuse_book else ReceiptBook()
    with stored.engine.connect() as connection, pytest.raises(ArtifactError):
        read_descriptor(connection, stored.context, JOB, "admission_config", selected)
    assert book.receipts == (original,)
    assert selected.receipts == ((original,) if reuse_book else ())


@pytest.mark.parametrize("scope", ["read", "mutation"])
def test_discard_interruption_is_retried_without_skipping_close_or_finish(
    engine, monkeypatch, scope
):
    from sqlalchemy import event

    work = OperationWork()
    outcome = TransactionOutcome()
    expected = ResourceNotFound()
    invalidate, remove = Connection.invalidate, event.remove
    rollback, close = Connection.rollback, Connection.close
    captured = None
    attempts = []

    def bad_remove(target, name, callback):
        remove(target, name, callback)
        raise RuntimeError("PRIVATE-DETACH")

    def interrupted(connection, *args, **kwargs):
        attempts.append(connection)
        if len(attempts) == 1:
            raise KeyboardInterrupt("PRIVATE-DISCARD")
        return invalidate(connection, *args, **kwargs)

    monkeypatch.setattr(event, "remove", bad_remove)
    monkeypatch.setattr(Connection, "invalidate", interrupted)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with pytest.raises(BaseException) as caught, manager as connection:
            captured = connection
            raw = connection.connection.driver_connection
            raise expected
        assert caught.value is expected and caught.value.__suppress_context__
        assert len(attempts) >= 2
        assert captured.closed and engine.pool.checkedout() == 0
        assert work._started is None
        with pytest.raises(sqlite3.ProgrammingError):
            raw.execute("SELECT 1")
        assert rows(engine) == []
    finally:
        release_probe(captured, rollback, close)


@pytest.mark.parametrize("scope", ["read", "mutation"])
def test_cleanup_interruption_after_ordinary_cleanup_error_is_not_swallowed(
    engine, monkeypatch, scope
):
    work = OperationWork()
    outcome = TransactionOutcome()
    expected = KeyboardInterrupt("PRIVATE-STOP")
    control, close = work.control_attempt, Connection.close
    rollback = Connection.rollback
    captured = None
    failed = []

    def accounting(kind):
        control(kind)
        if kind == "close":
            raise RuntimeError("PRIVATE-ACCOUNT")

    def interrupted(connection):
        if not failed:
            failed.append(True)
            raise expected
        return close(connection)

    monkeypatch.setattr(work, "control_attempt", accounting)
    monkeypatch.setattr(Connection, "close", interrupted)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with pytest.raises(BaseException) as caught, manager as connection:
            captured = connection
        assert caught.value is expected and caught.value.__suppress_context__
        assert captured.closed and engine.pool.checkedout() == 0
        assert work._started is None
        assert rows(engine) == []
    finally:
        release_probe(captured, rollback, close)


@pytest.mark.parametrize("scope", ["read", "mutation"])
def test_setup_primary_survives_interrupted_discard(engine, monkeypatch, scope):
    from sqlalchemy import event

    expected = ResourceNotFound()
    work = OperationWork()
    outcome = TransactionOutcome()
    invalidate = Connection.invalidate
    interrupted = []
    touched = []

    def setup_fault(_connection, _cursor, statement, *_args):
        if statement == "PRAGMA busy_timeout=3000":
            touched.append(statement)
            raise expected

    def disposal_fault(connection, *args, **kwargs):
        if not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt("PRIVATE-SETUP-DISPOSAL")
        return invalidate(connection, *args, **kwargs)

    event.listen(engine, "after_cursor_execute", setup_fault)
    monkeypatch.setattr(Connection, "invalidate", disposal_fault)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with pytest.raises(BaseException) as caught, manager:
            pytest.fail("failed setup reached body")
        assert caught.value is expected and caught.value.__suppress_context__
        assert touched and interrupted
        assert engine.pool.checkedout() == 0 and work._started is None
        assert not outcome.begun and not outcome.commit_attempted
    finally:
        event.remove(engine, "after_cursor_execute", setup_fault)
    assert rows(engine) == []


@pytest.mark.parametrize("scope", ["read", "mutation"])
def test_multiple_cleanup_interruptions_fit_reserved_attempts(engine, monkeypatch, scope):
    from sqlalchemy import event

    work = OperationWork()
    outcome = TransactionOutcome()
    expected = ResourceNotFound()
    remove, invalidate, close = event.remove, Connection.invalidate, Connection.close
    invalidations, closes = [], []

    def detach_fault(target, name, callback):
        remove(target, name, callback)
        raise RuntimeError("PRIVATE-DETACH")

    def discard_fault(connection, *args, **kwargs):
        invalidations.append(connection)
        if len(invalidations) == 1:
            raise KeyboardInterrupt("PRIVATE-FIRST-DISCARD")
        return invalidate(connection, *args, **kwargs)

    def close_fault(connection):
        closes.append(connection)
        if len(closes) == 1:
            raise SystemExit("PRIVATE-FIRST-CLOSE")
        return close(connection)

    monkeypatch.setattr(event, "remove", detach_fault)
    monkeypatch.setattr(Connection, "invalidate", discard_fault)
    monkeypatch.setattr(Connection, "close", close_fault)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    with pytest.raises(BaseException) as caught, manager as connection:
        raw = connection.connection.driver_connection
        # Exhaust the ordinary allowance after real setup/body, like the
        # accepted worst-chain fixture; cleanup retains its own eight slots.
        connection.exec_driver_sql("SELECT 1")
        work.statements = 504
        raise expected
    assert caught.value is expected and caught.value.__suppress_context__
    assert work.statements <= 512
    assert len(closes) == 2 and len(invalidations) >= 2
    assert engine.pool.checkedout() == 0 and work._started is None
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    assert rows(engine) == []


@pytest.mark.parametrize("scope", ["read", "mutation"])
@pytest.mark.parametrize("primary", [False, True])
def test_finish_interruption_runs_after_native_release(engine, monkeypatch, scope, primary):
    work = OperationWork()
    outcome = TransactionOutcome()
    expected = ResourceNotFound()
    interrupted = KeyboardInterrupt("PRIVATE-FINISH")
    finish = work.finish
    observed = []

    def finish_fault():
        observed.append(engine.pool.checkedout())
        finish()
        raise interrupted

    monkeypatch.setattr(work, "finish", finish_fault)
    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    with pytest.raises(BaseException) as caught, manager:
        if primary:
            raise expected
    assert caught.value is (expected if primary else interrupted)
    assert caught.value.__suppress_context__
    assert observed == [0] and work._started is None
    if scope == "mutation":
        assert outcome.cleanup_failed
        assert outcome.commit_acknowledged is not primary
    assert rows(engine) == []


@pytest.mark.parametrize("scope", ["read", "mutation"])
@pytest.mark.parametrize("chain", ["listeners", "progress", "ordinary_progress"])
@pytest.mark.parametrize("primary_kind", ["none", "denial", "interruption"])
def test_detach_preserves_first_inner_interruption_after_all_removals(
    engine, monkeypatch, scope, chain, primary_kind
):
    from sqlalchemy import event

    work, outcome = OperationWork(), TransactionOutcome()
    first = KeyboardInterrupt("PRIVATE-FIRST-DETACH")
    second = SystemExit("PRIVATE-LATER-LISTENER")
    last = GeneratorExit("PRIVATE-LATER-INFO")
    primary = {
        "none": None,
        "denial": ResourceNotFound(),
        "interruption": SystemExit("PRIMARY-BODY"),
    }[primary_kind]
    remove, finish, control = event.remove, work.finish, work.control_attempt
    removed, controls, finished, progress = [], [], [], []
    callbacks, captured, original_info = [], None, None
    rollback, close = Connection.rollback, Connection.close

    def remove_fault(target, name, callback):
        remove(target, name, callback)  # Real listener removal before failure.
        removed.append(name)
        raise first if len(removed) == 1 and chain != "progress" else second

    def account(kind):
        controls.append(kind)
        control(kind)

    def finished_after_release():
        finished.append(engine.pool.checkedout())
        finish()

    class ProgressFault:
        def __init__(self, raw):
            self.raw = raw

        def __getattr__(self, name):
            return getattr(self.raw, name)

        def set_progress_handler(self, callback, interval):
            self.raw.set_progress_handler(callback, interval)
            assert callback is None and interval == 0
            progress.append(True)
            if chain == "progress":
                raise first
            raise RuntimeError("PRIVATE-EARLIER-ORDINARY")

    class InfoFault:
        def get(self, key):
            return original_info.get(key)

        def __delitem__(self, key):
            del original_info[key]  # Real marker removal before interruption.
            raise last

    manager = (
        operation_connection(engine, work)
        if scope == "read"
        else admission_transaction(engine, outcome, work=work)
    )
    try:
        with monkeypatch.context() as patch:
            patch.setattr(event, "remove", remove_fault)
            patch.setattr(work, "control_attempt", account)
            patch.setattr(work, "finish", finished_after_release)
            with pytest.raises(BaseException) as caught, manager as connection:
                captured = connection
                raw = connection.connection.driver_connection
                original_info = connection.info
                callbacks = list(work._listeners)
                connection.exec_driver_sql(
                    "INSERT INTO proof VALUES(1)" if scope == "mutation" else "SELECT 1"
                )
                if chain != "listeners":
                    work._raw = ProgressFault(raw)
                    work._info = InfoFault()
                if primary is not None:
                    raise primary
        assert removed == ["before_cursor_execute", "after_cursor_execute"]
        assert progress == ([] if chain == "listeners" else [True])
        assert all(not event.contains(captured, name, callback) for name, callback in callbacks)
        assert "operation_work" not in original_info
        assert captured.closed and engine.pool.checkedout() == 0 and finished == [0]
        assert work._started is None and work._connection is None
        assert work._listeners == [] and not work._progress
        if scope == "read":
            assert controls == ["rollback", "discard", "close"]
            assert work.statements == 9
        else:
            assert controls == (
                ["commit", "discard", "close"]
                if primary is None
                else ["discard", "rollback", "discard", "close"]
            )
            assert work.statements == 10
            assert outcome.cleanup_failed and outcome.commit_acknowledged is (primary is None)
        with pytest.raises(sqlite3.ProgrammingError):
            raw.execute("SELECT 1")
        assert rows(engine) == ([1] if scope == "mutation" and primary is None else [])
        assert caught.value.__suppress_context__
        assert caught.value is (first if primary is None else primary)
    finally:
        release_probe(captured, rollback, close)
