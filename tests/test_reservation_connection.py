"""Owned transaction and engine prerequisites, independent from ledger validity."""

import pytest
from sqlalchemy import create_engine, event

from agent_rewind.admission_transaction import TransactionOutcome, admission_transaction
from agent_rewind.migrations.compatibility import configure_runtime_engine
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.reservation_connection import issued_connection, require_body, require_engine
from agent_rewind.reservation_types import ReservationRefusal, ReservationScope
from agent_rewind.scoped_repositories import ProjectContext
from agent_rewind.sqlite_ownership import (
    SQLiteOwnershipError,
    connect_owned,
    create_owned_sqlite_engine,
    owned_connect,
    require_owned_sqlite,
)


@pytest.fixture
def engine(tmp_path):
    value = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path / 'transaction.sqlite'}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        connect_timeout=3,
    )

    @event.listens_for(value, "connect")
    def foreign_keys(raw, _record):
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=741")

    with owned_connect(value) as connection, connection.begin():
        connection.exec_driver_sql("CREATE TABLE proof (id INTEGER PRIMARY KEY)")
    yield value
    value.dispose()


def rows(engine):
    with owned_connect(engine) as connection:
        assert not connection.connection.driver_connection.in_transaction
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741
        return connection.exec_driver_sql("SELECT id FROM proof ORDER BY id").scalars().all()


@pytest.fixture
def scope():
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    return ReservationScope(
        principal, ProjectContext("1" * 32, "2" * 32, principal.principal_id), "3" * 32
    )


def test_bare_connection_refuses_before_any_sql(engine, scope):
    queries = []
    with owned_connect(engine) as connection:
        event.listen(connection, "before_cursor_execute", lambda *args: queries.append(args[2]))
        with pytest.raises(ReservationRefusal) as caught:
            require_body(connection, scope)
        assert caught.value.reason == "transaction_not_owned"
    assert queries == []


def test_issued_connection_retains_exact_scope_and_revokes_after_body(engine, scope):
    work, outcome = OperationWork(include_acquisition=True), TransactionOutcome()
    with admission_transaction(engine, outcome, work=work) as connection:
        with issued_connection(connection, scope, work) as body:
            assert require_body(connection, scope) is body
            other = ReservationScope(scope.principal, scope.context, scope.job_id)
            with pytest.raises(ReservationRefusal):
                require_body(connection, other)
            connection.exec_driver_sql("INSERT INTO proof VALUES(7)")
        with pytest.raises(ReservationRefusal):
            require_body(connection, scope)
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert rows(engine) == [7]


def test_replaced_transaction_is_not_rebound_to_issued_owner(engine, scope, monkeypatch):
    work, outcome = OperationWork(include_acquisition=True), TransactionOutcome()
    replaced = False
    with (
        pytest.raises(ReservationRefusal) as caught,
        admission_transaction(engine, outcome, work=work) as connection,
        issued_connection(connection, scope, work),
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(7)")
        # SQLite's owned raw rollback already refuses while the work lease is
        # active. Intercept the root observation here; the real PG raw
        # COMMIT/BEGIN replacement is exercised by the native tests.
        with monkeypatch.context() as changed:
            changed.setattr(connection, "get_transaction", lambda: None)
            replaced = True
            require_body(connection, scope)
    assert replaced
    assert caught.value.reason == "transaction_not_owned"
    assert outcome.confirmed_precommit_rollback and rows(engine) == []
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize(
    ("connect_timeout", "pool_timeout"),
    [(4, 1), (3, 2), (3, None)],
    ids=["connect-bound", "pool-bound", "huge-integer-pool-bound"],
)
def test_unsupported_engine_bounds_refuse_before_checkout(tmp_path, connect_timeout, pool_timeout):
    if pool_timeout is None:
        engine = create_engine(f"sqlite:///{tmp_path / 'bounded.db'}", pool_timeout=10**1000)
    else:
        engine = create_owned_sqlite_engine(
            f"sqlite:///{tmp_path / 'bounded.db'}",
            connect_timeout=connect_timeout,
            pool_timeout=pool_timeout,
        )
    observed = []
    event.listen(engine, "checkout", lambda *args: observed.append(args))
    try:
        with pytest.raises(ReservationRefusal) as caught:
            require_engine(engine)
        assert caught.value.reason == "transaction_not_owned"
        assert observed == []
    finally:
        engine.dispose()


def test_removed_owned_connect_hook_refuses_without_connecting(engine):
    capability = require_owned_sqlite(engine)
    event.remove(engine, "do_connect", capability.connect_hook)
    with pytest.raises(ReservationRefusal) as caught:
        require_engine(engine)
    assert caught.value.reason == "transaction_not_owned"


def test_actual_factory_timeout_must_match_retained_bound(engine):
    require_engine(engine)
    original = require_owned_sqlite(engine).connect_hook
    assert original is not None
    event.remove(engine, "do_connect", original)

    def altered(dialect, record, args, parameters):
        return original(dialect, record, args, {**parameters, "timeout": 99})

    event.listen(engine, "do_connect", altered)
    engine.dispose()  # Require a fresh physical checkout, preserving factory identity.
    with pytest.raises(SQLiteOwnershipError):
        connect_owned(engine)
    assert engine.pool.checkedout() == 0


def test_custom_creator_is_not_an_existing_bounded_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'custom.db'}", creator=lambda: pytest.fail("native connect")
    )
    try:
        with pytest.raises(ReservationRefusal):
            require_engine(engine)
    finally:
        engine.dispose()


def test_postgres_requires_the_original_final_connect_hook_without_network():
    engine = create_engine(
        "postgresql+psycopg://fixture@127.0.0.1:55432/fixture",
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        pool_pre_ping=False,
    )
    try:
        with pytest.raises(ReservationRefusal):
            require_engine(engine)
        configure_runtime_engine(engine)
        require_engine(engine)
        event.listen(engine, "do_connect", lambda *args: None)
        with pytest.raises(ReservationRefusal):
            require_engine(engine)
    finally:
        engine.dispose()
