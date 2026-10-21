"""Real SQLite rollback/mode/pool faults; no publication or PG evidence."""

import sqlite3

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection

from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.request_authority import ActionForbidden
from agent_rewind.request_identity import IdentityInvalid
from agent_rewind.scoped_lineage import ResourceNotFound


@pytest.fixture
def engine(tmp_path):
    value = create_engine(
        f"sqlite:///{tmp_path / 'transaction.sqlite'}", pool_size=1, max_overflow=0
    )

    @event.listens_for(value, "connect")
    def foreign_keys(raw, _record):
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=741")

    with value.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE proof (id INTEGER PRIMARY KEY)")
    yield value
    value.dispose()


def rows(engine):
    with engine.connect() as connection:
        assert not connection.connection.driver_connection.in_transaction
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741
        return connection.exec_driver_sql("SELECT id FROM proof ORDER BY id").scalars().all()


def test_commit_and_precommit_rollback_have_distinct_observed_outcomes(engine):
    success = TransactionOutcome()
    with admission_transaction(engine, success) as connection:
        connection.execute(text("INSERT INTO proof VALUES(1)"))
    assert success.begun and success.commit_attempted and success.commit_acknowledged
    assert not success.confirmed_precommit_rollback
    failure = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$") as caught,
        admission_transaction(engine, failure) as connection,
    ):
        connection.execute(text("INSERT INTO proof VALUES(2)"))
        raise RuntimeError("PRIVATE-CANARY")
    assert caught.value.__suppress_context__
    assert failure.confirmed_precommit_rollback
    assert not failure.commit_attempted
    assert rows(engine) == [1]


@pytest.mark.parametrize("after_commit", [False, True])
def test_commit_failure_never_becomes_confirmed_precommit_rollback(
    engine, monkeypatch, after_commit
):
    original = Connection.commit
    state = TransactionOutcome()

    def lose_ack(connection):
        if after_commit:
            original(connection)
        raise RuntimeError("PRIVATE-COMMIT")

    monkeypatch.setattr(Connection, "commit", lose_ack)
    with (
        pytest.raises(AdmissionError, match="^outcome_uncertain$"),
        admission_transaction(engine, state) as connection,
    ):
        connection.execute(text("INSERT INTO proof VALUES(1)"))
    assert state.commit_attempted and not state.commit_acknowledged
    assert not state.confirmed_precommit_rollback
    assert rows(engine) == ([1] if after_commit else [])


def test_rollback_failure_discards_connection_and_stays_uncertain(engine, monkeypatch):
    state = TransactionOutcome()
    original = Connection.rollback

    def broken(connection):
        if connection.info.get("fail_rollback"):
            raise RuntimeError("PRIVATE-ROLLBACK")
        return original(connection)

    monkeypatch.setattr(Connection, "rollback", broken)
    with (
        pytest.raises(AdmissionError, match="^outcome_uncertain$"),
        admission_transaction(engine, state) as connection,
    ):
        raw = connection.connection.driver_connection
        connection.info["fail_rollback"] = True
        connection.execute(text("INSERT INTO proof VALUES(1)"))
        raise RuntimeError("PRIMARY")
    assert state.rollback_attempted and not state.rollback_acknowledged
    assert not state.confirmed_precommit_rollback
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    assert rows(engine) == []


@pytest.mark.parametrize("primary", [None, IdentityInvalid, ResourceNotFound, ActionForbidden])
def test_close_fault_discards_pool_and_preserves_primary_denial(engine, monkeypatch, primary):
    original = Connection.close
    calls = 0

    def broken(connection):
        nonlocal calls
        if connection.info.pop("fail_close", False):
            calls += 1
            raise RuntimeError("PRIVATE-CLOSE")
        return original(connection)

    monkeypatch.setattr(Connection, "close", broken)
    state = TransactionOutcome()
    expected = primary if primary else AdmissionError
    with pytest.raises(expected) as caught, admission_transaction(engine, state) as connection:
        raw = connection.connection.driver_connection
        connection.info["fail_close"] = True
        connection.execute(text("INSERT INTO proof VALUES(1)"))
        if primary:
            denial = primary()
            raise denial
    assert calls == 1 and state.cleanup_failed
    if primary:
        assert caught.value is denial
        assert rows(engine) == []
    else:
        assert caught.value.code == "outcome_uncertain"
        assert state.commit_acknowledged
        assert rows(engine) == [1]
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize(
    "mode", ["isolation_none", "dirty", "fk_off", "closed", "autocommit_true", "autocommit_false"]
)
def test_unsupported_or_dirty_physical_mode_refuses_before_body(engine, mode):
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        if mode.startswith("autocommit_") and not hasattr(raw, "autocommit"):
            pytest.skip("sqlite3 autocommit modes require Python 3.12")
    if mode == "isolation_none":
        raw.isolation_level = None
    elif mode == "dirty":
        raw.execute("BEGIN")
    elif mode == "fk_off":
        raw.execute("PRAGMA foreign_keys=OFF")
    elif mode == "closed":
        raw.close()
    else:
        raw.autocommit = mode == "autocommit_true"
    called = False
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, TransactionOutcome()),
    ):
        called = True
    assert not called
    assert engine.pool.checkedout() == 0
    assert rows(engine) == []


def test_reusing_outcome_is_refused_before_sql(engine):
    state = TransactionOutcome(commit_attempted=True)
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, state),
    ):
        pytest.fail("reused transaction state")
    assert rows(engine) == []
