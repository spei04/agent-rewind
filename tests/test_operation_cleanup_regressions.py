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
