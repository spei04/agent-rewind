"""Independent native checks for the excluded ledger-body capability."""

import json
import sqlite3

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from ledger_operator_fixture import (
    _CONNECT,
    assert_pool_released,
    ledger_case,
    proof_rows,
)
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from test_ledger_operator_boundaries_postgres import pg_case, pg_trace, visible_rows

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations import ledger_work
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["ledger_case", "pg_case", "pg_trace"]
pg = migration_tests.pg
postgres_only = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in independent PostgreSQL body guard"
)


def _refused_without_native_work(case, connection):
    boundary = len(case.trace.events)
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        transaction._require_ledger_body(connection)
    assert case.trace.events[boundary:] == []


@pytest.fixture
def guard_trace(ledger_case, record_property):
    records = []
    yield records
    record_property("guard_boundaries", json.dumps(records))
    record_property("native_trace", json.dumps(ledger_case.trace.events))


@pytest.fixture
def guard_clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ledger_work, "monotonic", lambda: now[0])
    return now


def test_live_guard_preserves_native_exclusion_and_owns_no_new_hooks(ledger_case, guard_trace):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        raw = connection.connection.driver_connection
        assert raw.in_transaction and connection.in_transaction()
        assert "BEGIN EXCLUSIVE" in case.trace.sql()
        lease = raw._ownership.lease
        listeners = tuple(work._listeners)
        ordinary = work.observed_ordinary
        boundary = len(case.trace.events)
        for _ in range(3):
            assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert work.observed_ordinary == ordinary
        assert raw._ownership.lease is lease and tuple(work._listeners) == listeners
        contender = _CONNECT(case.path, timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError) as caught:
                contender.execute("INSERT INTO proof VALUES (71)")
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        finally:
            contender.close()
        guard_trace.append({"live": True, "ordinary": ordinary, "contender": "SQLITE_BUSY"})
        connection.exec_driver_sql("INSERT INTO proof VALUES (70)")
    _refused_without_native_work(case, connection)
    with _CONNECT(case.path, timeout=0) as contender:
        contender.execute("INSERT INTO proof VALUES (71)")
    contender.close()
    assert proof_rows(case.path) == [70, 71]
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert_pool_released(case)


@pytest.mark.parametrize("state", ["unbegun", "logical", "native_exclusive"])
def test_unissued_connection_and_forged_info_never_grant_body(ledger_case, guard_trace, state):
    case = ledger_case
    engine = create_engine(f"sqlite:///{case.path}", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            if state == "logical":
                connection.begin()
            elif state == "native_exclusive":
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
            connection.info.update(
                {"ledger_body": True, "ledger_work": LedgerWork(), "excluded": True}
            )
            raw = connection.connection.driver_connection
            before = (connection.in_transaction(), raw.in_transaction)
            _refused_without_native_work(case, connection)
            assert (connection.in_transaction(), raw.in_transaction) == before
            guard_trace.append({"unissued_state": state, "native_transaction": before[1]})
    finally:
        engine.dispose()
    assert proof_rows(case.path) == []


@pytest.mark.parametrize("after_exclusion", [False, True])
def test_failed_begin_has_no_live_body_before_or_after_native_exclusion(
    ledger_case, guard_trace, monkeypatch, after_exclusion
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    original = transaction._begin
    seen = []

    def begin(connection, result, budget):
        seen.append(connection)
        _refused_without_native_work(case, connection)
        if after_exclusion:
            original(connection, result, budget)
            assert connection.connection.driver_connection.in_transaction
            _refused_without_native_work(case, connection)
        guard_trace.append({"begin_failure_after_exclusion": after_exclusion})
        raise MigrationRefused("schema_incompatible")

    monkeypatch.setattr(transaction, "_begin", begin)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("failed exclusion yielded a body")
    assert len(seen) == 1
    _refused_without_native_work(case, seen[0])
    assert ("BEGIN EXCLUSIVE" in case.trace.sql()) is after_exclusion
    assert ("ROLLBACK" in case.trace.sql()) is after_exclusion
    assert not outcome.commit_attempted and not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    assert_pool_released(case)


@pytest.mark.parametrize("after_publication", [False, True])
def test_partial_publication_is_revoked_before_cleanup(
    ledger_case, guard_trace, monkeypatch, after_publication
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    original = transaction._register_ledger_body
    detach = work._detach
    seen = []
    cleanup = []

    def register(connection, claim, budget, receipt):
        seen.append(connection)
        _refused_without_native_work(case, connection)
        if after_publication:
            original(connection, claim, budget, receipt)
            assert transaction._require_ledger_body(connection) is budget
        raise MigrationRefused("schema_incompatible")

    def detached():
        _refused_without_native_work(case, seen[0])
        cleanup.append("detached_after_revocation")
        return detach()

    monkeypatch.setattr(transaction, "_register_ledger_body", register)
    monkeypatch.setattr(work, "_detach", detached)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, outcome, work=work),
    ):
        pytest.fail("partial publication yielded a body")
    assert cleanup == ["detached_after_revocation"] and len(seen) == 1
    _refused_without_native_work(case, seen[0])
    assert "BEGIN EXCLUSIVE" in case.trace.sql() and "ROLLBACK" in case.trace.sql()
    assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    guard_trace.append({"after_publication": after_publication, "cleanup": cleanup})
    assert_pool_released(case)


@pytest.mark.parametrize("exit_kind", ["normal", "typed", "error", "interrupt", "close"])
def test_every_body_exit_revokes_before_commit_preparation_detach_and_close(
    ledger_case, guard_trace, monkeypatch, exit_kind
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    prepare, detach, close = work._prepare_target, work._detach, Connection.close
    target = []
    ending = [False]
    checks = []

    def check(stage):
        if ending[0]:
            _refused_without_native_work(case, target[0])
            checks.append(stage)

    def prepared():
        check("commit_prepare")
        return prepare()

    def detached():
        check("detach")
        return detach()

    def closed(connection):
        if target and connection is target[0]:
            check("close")
        return close(connection)

    monkeypatch.setattr(work, "_prepare_target", prepared)
    monkeypatch.setattr(work, "_detach", detached)
    monkeypatch.setattr(Connection, "close", closed)
    context = ledger_transaction(case.engine, outcome, work=work)
    connection = context.__enter__()
    target.append(connection)
    assert transaction._require_ledger_body(connection) is work
    connection.exec_driver_sql("INSERT INTO proof VALUES (72)")
    ending[0] = True
    if exit_kind == "normal":
        context.__exit__(None, None, None)
    elif exit_kind == "close":
        context.gen.close()
    else:
        error = {
            "typed": MigrationRefused("schema_incompatible"),
            "error": RuntimeError("body-fault"),
            "interrupt": KeyboardInterrupt("first-body-interruption"),
        }[exit_kind]
        if exit_kind == "error":
            with pytest.raises(MigrationRefused, match="^migration_database_failure$"):
                context.__exit__(type(error), error, error.__traceback__)
        else:
            # contextlib suppresses the identical exception at this explicit boundary.
            assert context.__exit__(type(error), error, error.__traceback__) is False
    assert checks == (
        ["commit_prepare", "detach", "close"] if exit_kind == "normal" else ["detach", "close"]
    )
    _refused_without_native_work(case, connection)
    assert outcome.commit_acknowledged is (exit_kind == "normal")
    assert not outcome.cleanup_failed
    assert proof_rows(case.path) == ([72] if exit_kind == "normal" else [])
    guard_trace.append({"exit_kind": exit_kind, "revoked_at": checks})
    assert_pool_released(case)


@pytest.mark.parametrize("mutation", ["rollback", "commit", "close", "invalidate", "new_root"])
def test_changed_native_or_logical_transaction_refuses_without_reconnect(
    ledger_case, guard_trace, mutation
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    observed = []
    try:
        with ledger_transaction(case.engine, outcome, work=work) as connection:
            assert transaction._require_ledger_body(connection) is work
            if mutation == "new_root":
                connection.commit()
                connection.exec_driver_sql("BEGIN EXCLUSIVE")
                assert connection.connection.driver_connection.in_transaction
            elif mutation == "rollback":
                # Inject a real native rollback below the cooperative lease API.
                # The logical wrapper remains active, so native state must decide.
                raw = connection.connection.driver_connection
                sqlite3.Connection.rollback(raw)
                assert connection.in_transaction() and not raw.in_transaction
            elif mutation == "close":
                connection.commit()
                connection.close()
                assert connection.closed
            else:
                getattr(connection, mutation)()
            _refused_without_native_work(case, connection)
            observed.append(mutation)
            raise MigrationRefused("schema_incompatible")
    except MigrationRefused as error:
        assert str(error) in {"schema_incompatible", "ledger_outcome_uncertain"}
    assert observed == [mutation]
    assert not outcome.commit_attempted and proof_rows(case.path) == []
    guard_trace.append({"changed_transaction": mutation, "cleanup_failed": outcome.cleanup_failed})
    assert_pool_released(case)


def test_active_savepoint_refuses_and_restored_outer_body_stays_valid(ledger_case, guard_trace):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert transaction._require_ledger_body(connection) is work
        with connection.begin_nested():
            assert connection.in_nested_transaction()
            _refused_without_native_work(case, connection)
        assert transaction._require_ledger_body(connection) is work
        connection.exec_driver_sql("INSERT INTO proof VALUES (73)")
    assert any(sql.startswith("SAVEPOINT") for sql in case.trace.sql())
    assert outcome.commit_acknowledged and proof_rows(case.path) == [73]
    guard_trace.append({"nested_refused": True, "original_outer_restored": True})
    assert_pool_released(case)


def test_stale_connection_cannot_use_or_revoke_a_new_checkout_body(
    ledger_case, guard_trace, monkeypatch
):
    case = ledger_case
    old_work = LedgerWork()
    with ledger_transaction(case.engine, LedgerOutcome(), work=old_work) as old:
        raw = old.connection.driver_connection
        old_receipt = raw._ownership.receipt
        assert transaction._require_ledger_body(old) is old_work
    work, outcome = LedgerWork(), LedgerOutcome()
    callbacks = []

    def progress():
        callbacks.append(True)
        return 0

    monkeypatch.setattr(work, "_progress", progress)
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        receipt = raw._ownership.receipt
        assert connection.connection.driver_connection is raw
        assert receipt.generation > old_receipt.generation
        boundary = len(case.trace.events)
        _refused_without_native_work(case, old)
        transaction._revoke_ledger_body(old)
        assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert raw._ownership.lease is work._lease
        assert (
            connection.exec_driver_sql(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000) "
                "SELECT sum(x) FROM n"
            ).scalar_one()
            == 2001000
        )
        assert callbacks
        connection.exec_driver_sql("INSERT INTO proof VALUES (74)")
        guard_trace.append({"generations": [old_receipt.generation, receipt.generation]})
    assert outcome.commit_acknowledged and proof_rows(case.path) == [74]
    assert_pool_released(case)


def test_property_only_guard_does_not_refund_or_reset_full_ordinary_budget(
    ledger_case, guard_trace
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        work.reserve_ordinary(2028 - work.observed_ordinary)
        boundary = len(case.trace.events)
        for _ in range(3):
            assert transaction._require_ledger_body(connection) is work
        assert case.trace.events[boundary:] == []
        assert (work.prepaid_bootstrap, work.prepaid_cleanup, work.observed_ordinary) == (
            12,
            8,
            2028,
        )
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert "COMMIT" not in case.trace.sql()
    assert proof_rows(case.path) == []
    guard_trace.append({"ordinary": 2028, "prepaid": 20, "commit_refused": True})
    assert_pool_released(case)


def test_expired_live_body_refuses_before_native_work(ledger_case, guard_trace, guard_clock):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^migration_busy$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        assert transaction._require_ledger_body(connection) is work
        guard_clock[0] += 121
        boundary = len(case.trace.events)
        ordinary = work.observed_ordinary
        try:
            transaction._require_ledger_body(connection)
        finally:
            assert case.trace.events[boundary:] == [] and work.observed_ordinary == ordinary
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    guard_trace.append({"expired": True, "ordinary_unchanged": ordinary})
    assert_pool_released(case)


def test_committed_cleanup_fault_leaves_no_live_guard_or_reusable_engine(
    ledger_case, guard_trace, monkeypatch
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    close = Connection.close
    target, faults = [], []

    def failed_close(connection):
        if target and connection is target[0] and not faults:
            _refused_without_native_work(case, connection)
            faults.append(True)
            raise RuntimeError("first-close-fault")
        return close(connection)

    monkeypatch.setattr(Connection, "close", failed_close)
    with (
        pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
        ledger_transaction(case.engine, outcome, work=work) as connection,
    ):
        target.append(connection)
        connection.exec_driver_sql("INSERT INTO proof VALUES (75)")
    assert faults == [True]
    _refused_without_native_work(case, connection)
    assert outcome.commit_acknowledged and outcome.cleanup_failed
    assert proof_rows(case.path) == [75]
    boundary = len(case.trace.events)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("uncertain cleanup published a reusable engine")
    assert case.trace.events[boundary:] == []
    guard_trace.append({"commit_visible": True, "cleanup_failed": True, "guard_revoked": True})
    assert_pool_released(case)


@pytest.mark.parametrize("options", [{"stream_results": True}, {"yield_per": 1}])
def test_changed_connection_options_refuse_before_guard_native_work(
    ledger_case, guard_trace, options
):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert transaction._require_ledger_body(connection) is work
        assert not connection.get_execution_options()
        connection.execution_options(**options)
        _refused_without_native_work(case, connection)
        guard_trace.append({"unsupported_options": options})
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert proof_rows(case.path) == []
    assert_pool_released(case)


def test_detached_proxy_refuses_before_guard_native_work(ledger_case, guard_trace):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    checked = []
    try:
        with ledger_transaction(case.engine, outcome, work=work) as connection:
            proxy = connection.connection
            raw = proxy.driver_connection
            root = connection.get_transaction()
            assert transaction._require_ledger_body(connection) is work
            connection.detach()
            assert proxy.is_detached and connection.connection is proxy
            assert connection.get_transaction() is root and raw.in_transaction
            _refused_without_native_work(case, connection)
            checked.append(True)
            raise MigrationRefused("schema_incompatible")
    except MigrationRefused as error:
        assert str(error) in {"schema_incompatible", "ledger_outcome_uncertain"}
    assert checked == [True]
    assert proof_rows(case.path) == []
    guard_trace.append({"detached": True, "cleanup_failed": outcome.cleanup_failed})
    assert_pool_released(case)


@pytest.fixture
def pg_driver_controls(pg_trace, monkeypatch):
    for name in ("execute", "fetchone", "fetchmany"):
        original = getattr(psycopg.ServerCursor, name)

        def observed(cursor, *args, _name=name, _original=original, **kwargs):
            pg_trace.events.append((pg_trace.phase, "server-" + _name, id(cursor.connection), None))
            return _original(cursor, *args, **kwargs)

        monkeypatch.setattr(psycopg.ServerCursor, name, observed)
    yield
    assert not any(event[1].startswith("server-") for event in pg_trace.events)


def _pg_refused_without_native_work(trace, connection):
    boundary = len(trace.events)
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        transaction._require_ledger_body(connection)
    assert trace.events[boundary:] == []


def _pg_sql(trace, start, end=None):
    return [event[3] for event in trace.events[start:end] if event[1] == "sql-call"]


def _assert_xid_bundle(sql):
    assert len(sql) == 3
    assert sql[0].startswith("SET LOCAL statement_timeout")
    assert sql[1].startswith("SET LOCAL lock_timeout")
    assert sql[2] == "SELECT pg_current_xact_id()::text"


@postgres_only
def test_pg_publication_and_each_guard_pay_one_native_bundle(
    pg_case, pg_trace, pg_driver_controls, monkeypatch, record_property
):
    work, outcome = LedgerWork(), LedgerOutcome()
    register = transaction._register_ledger_body
    prepare = work._prepare_target
    registrations, checks, target = [], [], []
    ending = [False]

    def registered(connection, claim, budget, receipt):
        before = budget.observed_ordinary
        boundary = len(pg_trace.events)
        register(connection, claim, budget, receipt)
        sql = _pg_sql(pg_trace, boundary)
        _assert_xid_bundle(sql)
        assert budget.observed_ordinary - before == 3
        registrations.append(sql)

    def prepared():
        if ending[0]:
            _pg_refused_without_native_work(pg_trace, target[0])
            checks.append("revoked_before_commit_prepare")
        return prepare()

    monkeypatch.setattr(transaction, "_register_ledger_body", registered)
    monkeypatch.setattr(work, "_prepare_target", prepared)
    with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
        target.append(connection)
        raw = connection.connection.driver_connection
        assert raw.info.transaction_status is psycopg.pq.TransactionStatus.INTRANS
        for _ in range(2):
            before, boundary = work.observed_ordinary, len(pg_trace.events)
            assert transaction._require_ledger_body(connection) is work
            _assert_xid_bundle(_pg_sql(pg_trace, boundary))
            assert work.observed_ordinary - before == 3
        pg_trace.phase = "contender"
        with pg_case.verifier.connect() as contender:
            contender.exec_driver_sql("SET LOCAL lock_timeout='1ms'")
            with pytest.raises(DBAPIError) as caught:
                contender.exec_driver_sql("INSERT INTO proof VALUES (81)")
            assert caught.value.orig.sqlstate == "55P03"
            contender.rollback()
        pg_trace.phase = "ordinary"
        connection.exec_driver_sql("INSERT INTO proof VALUES (80)")
        ending[0] = True
    assert len(registrations) == 1 and checks == ["revoked_before_commit_prepare"]
    _pg_refused_without_native_work(pg_trace, connection)
    assert raw.closed and outcome.commit_acknowledged and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == [80]
    with pg_case.verifier.begin() as contender:
        contender.exec_driver_sql("INSERT INTO proof VALUES (81)")
    assert visible_rows(pg_case, pg_trace) == [80, 81]
    record_property("native_registration_bundle", json.dumps(registrations))


@postgres_only
@pytest.mark.parametrize("restart", [False, True])
def test_pg_native_transaction_change_cannot_reuse_logical_body(
    pg_case, pg_trace, pg_driver_controls, record_property, restart
):
    work, outcome = LedgerWork(), LedgerOutcome()
    identities = []
    with (
        pytest.raises(MigrationRefused, match="^transactional_connection_required$"),
        ledger_transaction(pg_case.engine, outcome, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        root, proxy = connection.get_transaction(), connection.connection
        assert transaction._require_ledger_body(connection) is work
        pg_trace.phase = "test-native-control"
        with raw.cursor() as cursor:
            cursor.execute("SELECT pg_current_xact_id()::text")
            identities.append(cursor.fetchone()[0])
        raw.rollback()
        assert raw.info.transaction_status is psycopg.pq.TransactionStatus.IDLE
        if restart:
            with raw.cursor() as cursor:
                cursor.execute("BEGIN")
                cursor.execute("SELECT pg_current_xact_id()::text")
                identities.append(cursor.fetchone()[0])
            assert identities[0] != identities[1]
            assert raw.info.transaction_status is psycopg.pq.TransactionStatus.INTRANS
        assert connection.get_transaction() is root and connection.connection is proxy
        pg_trace.phase = "ordinary"
        boundary, before = len(pg_trace.events), work.observed_ordinary
        try:
            transaction._require_ledger_body(connection)
        finally:
            if restart:
                _assert_xid_bundle(_pg_sql(pg_trace, boundary))
                assert work.observed_ordinary - before == 3
            else:
                assert pg_trace.events[boundary:] == [] and work.observed_ordinary == before
    assert raw.closed and outcome.confirmed_precommit_rollback
    assert not outcome.commit_attempted and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []
    record_property("native_transaction_ids", json.dumps(identities))


@postgres_only
@pytest.mark.parametrize("mutation", ["stream_results", "yield_per", "detach"])
def test_pg_changed_options_and_detach_refuse_before_any_driver_query(
    pg_case, pg_trace, pg_driver_controls, record_property, mutation
):
    work, outcome = LedgerWork(), LedgerOutcome()
    witnesses = []
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(pg_case.engine, outcome, work=work) as connection,
    ):
        raw, proxy, root = (
            connection.connection.driver_connection,
            connection.connection,
            connection.get_transaction(),
        )
        assert transaction._require_ledger_body(connection) is work
        if mutation == "detach":
            connection.detach()
            assert proxy.is_detached and connection.get_transaction() is root
            assert raw.info.transaction_status is psycopg.pq.TransactionStatus.INTRANS
            # Pinned SQLAlchemy already changes this identity on detach. Retain
            # the actual witness rather than declaring an unobserved old defect.
            witnesses.append({"retained_driver_same": proxy.driver_connection is raw})
        else:
            connection.execution_options(**{mutation: True if mutation == "stream_results" else 1})
        _pg_refused_without_native_work(pg_trace, connection)
        raise MigrationRefused("schema_incompatible")
    assert raw.closed and outcome.confirmed_precommit_rollback
    assert not outcome.commit_attempted and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []
    record_property(
        "changed_connection", json.dumps({"mutation": mutation, "witnesses": witnesses})
    )


@postgres_only
@pytest.mark.parametrize("remaining", [2, 3])
def test_pg_guard_cannot_split_or_refund_its_last_native_bundle(
    pg_case, pg_trace, pg_driver_controls, record_property, remaining
):
    work, outcome = LedgerWork(), LedgerOutcome()
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(pg_case.engine, outcome, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        work.reserve_ordinary(2028 - remaining - work.observed_ordinary)
        before, boundary = work.observed_ordinary, len(pg_trace.events)
        if remaining == 3:
            assert transaction._require_ledger_body(connection) is work
            _assert_xid_bundle(_pg_sql(pg_trace, boundary))
            assert work.observed_ordinary == 2028
            raise MigrationRefused("schema_incompatible")
        try:
            transaction._require_ledger_body(connection)
        finally:
            assert pg_trace.events[boundary:] == [] and work.observed_ordinary == before
    assert str(caught.value) == (
        "schema_incompatible" if remaining == 3 else "ledger_limit_exceeded"
    )
    assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
    assert raw.closed and outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert visible_rows(pg_case, pg_trace) == []
    record_property(
        "last_guard_bundle",
        json.dumps({"remaining": remaining, "ordinary": work.observed_ordinary}),
    )


@postgres_only
@pytest.mark.parametrize("setter", ["statement_timeout", "lock_timeout"])
@pytest.mark.parametrize("expire", [False, True])
def test_pg_guard_rechecks_clock_after_each_actual_native_setter(
    pg_case, pg_trace, pg_driver_controls, guard_clock, monkeypatch, record_property, setter, expire
):
    work, outcome = LedgerWork(), LedgerOutcome()
    execute = psycopg.Cursor.execute
    armed, delays, intervals, errors = [False], [], [], []

    def elapsed(cursor, query, *args, **kwargs):
        result = execute(cursor, query, *args, **kwargs)
        if armed[0] and str(query).startswith("SET LOCAL " + setter):
            armed[0] = False
            delays.append(str(query))
            if expire:
                guard_clock[0] += 121
        return result

    monkeypatch.setattr(psycopg.Cursor, "execute", elapsed)
    try:
        with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
            raw = connection.connection.driver_connection
            before = work.observed_ordinary
            armed[0] = True
            intervals.append(len(pg_trace.events))
            try:
                assert transaction._require_ledger_body(connection) is work
            finally:
                intervals.append(len(pg_trace.events))
                assert work.observed_ordinary - before == 3
    except MigrationRefused as error:
        errors.append(str(error))
    sql = _pg_sql(pg_trace, *intervals)
    assert len(delays) == 1 and raw.closed
    if expire:
        assert errors == ["migration_busy"]
        assert len(sql) == (1 if setter == "statement_timeout" else 2)
        assert not any("pg_current_xact_id" in query for query in sql)
        assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    else:
        assert errors == []
        _assert_xid_bundle(sql)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []
    record_property(
        "guard_setter_clock", json.dumps({"setter": setter, "expire": expire, "sql": sql})
    )


@postgres_only
@pytest.mark.parametrize("after_native", [False, True])
def test_pg_failed_identity_publication_never_yields_or_survives_cleanup(
    pg_case, pg_trace, pg_driver_controls, monkeypatch, record_property, after_native
):
    work, outcome = LedgerWork(), LedgerOutcome()
    execute = psycopg.Cursor.execute
    touched = []

    def failed(cursor, query, *args, **kwargs):
        if str(query) == "SELECT pg_current_xact_id()::text" and not touched:
            touched.append(cursor.connection)
            if after_native:
                execute(cursor, query, *args, **kwargs)
            raise MigrationRefused("schema_incompatible")
        return execute(cursor, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", failed)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(pg_case.engine, outcome, work=work),
    ):
        pytest.fail("failed native identity registration yielded the body")
    assert len(touched) == 1 and touched[0].closed
    _pg_refused_without_native_work(pg_trace, work._connection)
    assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
    assert not outcome.cleanup_failed and visible_rows(pg_case, pg_trace) == []
    record_property("failed_identity_publication", json.dumps({"after_native": after_native}))


@pytest.mark.parametrize("event_name", ["before_cursor_execute", "after_cursor_execute"])
def test_added_connection_listener_refuses_the_supported_body(ledger_case, guard_trace, event_name):
    case = ledger_case
    work, outcome = LedgerWork(), LedgerOutcome()
    calls = []

    def foreign(*args):
        calls.append(True)

    with ledger_transaction(case.engine, outcome, work=work) as connection:
        assert transaction._require_ledger_body(connection) is work
        event.listen(connection, event_name, foreign)
        assert event.contains(connection, event_name, foreign)
        try:
            _refused_without_native_work(case, connection)
        finally:
            event.remove(connection, event_name, foreign)
        assert calls == []
        guard_trace.append({"foreign_event": event_name, "native_effects": False})
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert_pool_released(case)


@postgres_only
@pytest.mark.parametrize("event_name", ["before_cursor_execute", "after_cursor_execute"])
def test_pg_foreign_listener_refuses_before_unmetered_native_callback(
    pg_case, pg_trace, pg_driver_controls, record_property, event_name
):
    work, outcome = LedgerWork(), LedgerOutcome()
    calls = []

    def foreign(connection, cursor, statement, *args):
        if statement == "SELECT pg_current_xact_id()::text":
            with cursor.connection.cursor() as side:
                side.execute("SELECT 91")
            calls.append(True)

    with ledger_transaction(pg_case.engine, outcome, work=work) as connection:
        assert transaction._require_ledger_body(connection) is work
        event.listen(connection, event_name, foreign)
        before, boundary = work.observed_ordinary, len(pg_trace.events)
        try:
            _pg_refused_without_native_work(pg_trace, connection)
        finally:
            event.remove(connection, event_name, foreign)
            record_property(
                "foreign_native_cost",
                json.dumps(
                    {
                        "event_name": event_name,
                        "sql": _pg_sql(pg_trace, boundary),
                        "ordinary_delta": work.observed_ordinary - before,
                        "callback_calls": len(calls),
                    }
                ),
            )
        assert calls == [] and work.observed_ordinary == before
    assert outcome.commit_acknowledged and not outcome.cleanup_failed
    assert visible_rows(pg_case, pg_trace) == []
