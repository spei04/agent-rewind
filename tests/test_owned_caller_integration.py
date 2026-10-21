"""Dormant owned-engine injection across actual callback and caller boundaries."""

import sqlite3
from contextlib import contextmanager
from itertools import permutations

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.pool import QueuePool

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.database import Database
from agent_rewind.errors import Fault
from agent_rewind.listing_session import SQLWork, listing_connection
from agent_rewind.migrations.compatibility import _inspection
from agent_rewind.migrations.schema import MigrationRefused
from agent_rewind.migrations.service import migration_transaction
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.sqlite_ownership import (
    SQLiteOwnershipError,
    close_owned,
    connect_owned,
    create_owned_sqlite_engine,
    finish_owned,
    owned_begin,
    owned_connect,
)


@pytest.fixture
def engine(tmp_path):
    value = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path}/owned.sqlite", pool_size=1, max_overflow=0, pool_timeout=0.05
    )
    with owned_begin(value) as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE proof (id INTEGER)")
        connection.exec_driver_sql("INSERT INTO proof VALUES (1)")
        connection.exec_driver_sql("PRAGMA busy_timeout=741")
    yield value
    checked_out = value.pool.checkedout()
    value.dispose()
    assert checked_out == 0


def reusable(engine, previous=None):
    with owned_connect(engine) as connection:
        raw = connection.connection.driver_connection
        if previous is not None:
            assert raw is not previous
        assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
        assert not raw.in_transaction
    assert engine.pool.checkedout() == 0


def test_failed_connection_controls_still_return_public_proxy(engine, monkeypatch):
    connection, receipt = connect_owned(engine)
    raw = connection.connection.driver_connection
    calls = []

    def refuse(*args, **kwargs):
        raise RuntimeError("PRIVATE-CONTROL")

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", refuse)
        patch.setattr(Connection, "invalidate", refuse)
        with pytest.raises(RuntimeError):
            close_owned(connection, receipt)
        with pytest.raises(SQLiteOwnershipError):
            finish_owned(connection, receipt, control_attempt=calls.append)
    assert calls == ["discard", "close", "discard"]
    assert engine.pool.checkedout() == 0
    assert receipt.returned and receipt.disposal_acknowledged and receipt.failed
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    reusable(engine, raw)


@contextmanager
def phase(engine, name):
    if name == "operation":
        with operation_connection(engine, OperationWork()) as connection:
            yield connection
    elif name == "listing":
        with listing_connection(engine, SQLWork()) as connection:
            yield connection
    else:
        with owned_connect(engine) as connection, _inspection(connection):
            yield connection


@pytest.mark.parametrize("order", list(permutations(("operation", "listing", "inspection"))))
def test_three_progress_consumers_sequentially_reuse_exact_native_connection(engine, order):
    seen = []
    for name in order:
        with phase(engine, name) as connection:
            seen.append(connection.connection.driver_connection)
            assert connection.exec_driver_sql("SELECT id FROM proof").all() == [(1,)]
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
        with owned_connect(engine) as connection:
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741
            assert connection.connection.driver_connection._ownership.lease is None
            assert "operation_work" not in connection.info
    assert all(raw is seen[0] for raw in seen)
    reusable(engine)


@pytest.mark.parametrize("outer", ["operation", "inspection"])
def test_nested_callback_borrower_refuses_without_mutating_outer_owner(engine, outer):
    with owned_connect(engine) as connection:
        raw = connection.connection.driver_connection
        work = OperationWork()
        if outer == "operation":
            work.attach(connection)
            lease = raw._ownership.lease
            before = raw.execute("PRAGMA busy_timeout").fetchone()[0]
            with pytest.raises(SQLiteOwnershipError), _inspection(connection):
                pytest.fail("nested inspection was entered")
            assert raw._ownership.lease is lease
            assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == before
            connection.exec_driver_sql(
                "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<2000) "
                "SELECT sum(n) FROM x"
            ).scalar_one()
            assert work.instructions > 0
            work.detach()
            connection.rollback()
            work.finish()
        else:
            with _inspection(connection):
                lease = raw._ownership.lease
                before = raw.execute("PRAGMA busy_timeout").fetchone()[0]
                with pytest.raises(SQLiteOwnershipError):
                    work.attach(connection)
                work.detach()
                work.finish()
                assert raw._ownership.lease is lease
                assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == before
                assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    reusable(engine)


@pytest.mark.parametrize("name", ["operation", "listing", "inspection", "migration"])
def test_registered_replaced_pool_cannot_downgrade_to_legacy(engine, name):
    original = engine.pool
    created = []
    replacement = QueuePool(lambda: created.append(1) or sqlite3.connect(":memory:"))
    engine.pool = replacement
    try:
        expected = {
            "operation": AdmissionError,
            "listing": Fault,
            "inspection": SQLiteOwnershipError,
            "migration": MigrationRefused,
        }[name]
        with pytest.raises(expected) as caught:
            if name == "migration":
                with migration_transaction(engine):
                    pytest.fail("replacement acquired")
            else:
                with phase(engine, name):
                    pytest.fail("replacement acquired")
        assert not created
        assert "PRIVATE" not in str(caught.value)
    finally:
        engine.pool = original
        replacement.dispose()


@pytest.mark.parametrize("mutation", [False, True])
@pytest.mark.parametrize("body_denial", [False, True])
def test_manual_close_and_discard_faults_use_bounded_proxy_recovery(
    engine, monkeypatch, mutation, body_denial
):
    work = OperationWork()
    outcome = TransactionOutcome()
    controls = []
    observed = []
    base_control = work.control_attempt
    primary = ResourceNotFound()
    raw_close = ownership._TrackedSQLite._native_close
    failures = 0

    def count(kind):
        controls.append(kind)
        base_control(kind)

    def refuse(*args, **kwargs):
        raise RuntimeError("PRIVATE-CONNECTION-CONTROL")

    def fail_physical_once(raw):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("PRIVATE-PHYSICAL-CLOSE")
        raw_close(raw)

    monkeypatch.setattr(work, "control_attempt", count)
    owner = (
        admission_transaction(engine, outcome, work=work)
        if mutation
        else operation_connection(engine, work)
    )
    with monkeypatch.context() as patch:
        with (
            pytest.raises(ResourceNotFound if body_denial else AdmissionError) as caught,
            owner as connection,
        ):
            observed.append(connection.connection.driver_connection)
            connection.exec_driver_sql("SELECT 1")
            patch.setattr(Connection, "close", refuse)
            patch.setattr(Connection, "invalidate", refuse)
            patch.setattr(ownership._TrackedSQLite, "_native_close", fail_physical_once)
            controls.clear()  # from this point count cleanup; commit stays ordinary work
            if body_denial:
                raise primary
        if body_denial:
            assert caught.value is primary
        else:
            assert caught.value.code == (
                "outcome_uncertain" if mutation else "dependency_unavailable"
            )
    cleanup = [kind for kind in controls if kind != "commit"]
    prefix = (
        (["rollback"] if body_denial else []) + ["restore"]
        if mutation
        else ["rollback", "restore", "restore"]
    )
    assert cleanup == prefix + ["close", "discard", "close", "discard", "close"]
    assert len(cleanup) == (7 if mutation and body_denial else 6 if mutation else 8)
    assert engine.pool.checkedout() == 0 and work._started is None
    if mutation:
        assert outcome.cleanup_failed
        assert outcome.commit_acknowledged is (not body_denial)
        assert outcome.rollback_acknowledged is body_denial
    reusable(engine, observed[0])


@pytest.mark.parametrize("mutation", [False, True])
def test_accounting_interruption_does_not_skip_mandatory_owned_cleanup(
    engine, monkeypatch, mutation
):
    work = OperationWork()
    outcome = TransactionOutcome()
    primary = ResourceNotFound()
    seen = []
    count = work.control_attempt

    def broken(kind):
        count(kind)
        if kind != "commit":
            seen.append(kind)
            raise KeyboardInterrupt("PRIVATE-ACCOUNT")

    monkeypatch.setattr(work, "control_attempt", broken)
    owner = (
        admission_transaction(engine, outcome, work=work)
        if mutation
        else operation_connection(engine, work)
    )
    with pytest.raises(ResourceNotFound) as caught, owner as connection:
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("SELECT 1")
        raise primary
    assert caught.value is primary and caught.value.__suppress_context__
    assert "rollback" in seen and "close" in seen
    assert engine.pool.checkedout() == 0 and work._started is None
    reusable(engine, raw)


@pytest.mark.parametrize("with_work", [False, True])
def test_owned_admission_commit_and_denial_preserve_effects_and_timeout(engine, with_work):
    work = OperationWork() if with_work else None
    state = TransactionOutcome()
    with admission_transaction(engine, state, work=work) as connection:
        connection.exec_driver_sql("INSERT INTO proof VALUES(2)")
    assert state.commit_acknowledged and not state.cleanup_failed
    denial = ResourceNotFound()
    state = TransactionOutcome()
    with (
        pytest.raises(ResourceNotFound) as caught,
        admission_transaction(engine, state, work=work) as connection,
    ):
        connection.exec_driver_sql("INSERT INTO proof VALUES(3)")
        raise denial
    assert caught.value is denial and state.confirmed_precommit_rollback
    with owned_connect(engine) as connection:
        assert connection.exec_driver_sql("SELECT id FROM proof ORDER BY id").all() == [(1,), (2,)]
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741


def test_database_factory_is_owned_and_injected_owned_callers_work(settings, engine):
    database = Database(settings)
    legacy = database.engine
    ownership.require_owned_sqlite(legacy)
    database.engine = engine
    try:
        with owned_begin(engine) as connection:
            connection.exec_driver_sql(
                "CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT, data JSON, created REAL)"
            )
        record = database.add("example", {"value": "safe"})
        assert database.get(record, "example")["value"] == "safe"
        assert database.list_records("example")[0]["id"] == record
    finally:
        legacy.dispose()


def test_persistently_failing_proxy_and_driver_retains_failed_unreturned_verdict(
    engine, monkeypatch
):
    connection, receipt = connect_owned(engine)
    raw = receipt.raw
    proxy_type = type(receipt.proxy)
    calls = []
    original_proxy_invalidate = proxy_type.invalidate
    original_raw_close = ownership._TrackedSQLite._native_close

    def refuse(*args, **kwargs):
        raise RuntimeError("PRIVATE-PERSISTENT")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(Connection, "invalidate", refuse)
            patch.setattr(Connection, "close", refuse)
            patch.setattr(proxy_type, "invalidate", refuse)
            patch.setattr(ownership._TrackedSQLite, "_native_close", refuse)
            with pytest.raises(RuntimeError):
                close_owned(connection, receipt)
            with pytest.raises(SQLiteOwnershipError):
                finish_owned(connection, receipt, control_attempt=calls.append)
            assert calls == ["discard", "close", "discard", "close"]
            verdict = ownership.cleanup_snapshot(receipt)
            assert verdict.failed and not verdict.clean
            assert not verdict.returned and not verdict.disposal_acknowledged
            assert engine.pool.checkedout() == 1
    finally:
        # The test owns its permanent injected fault and must not strand a slot.
        original_proxy_invalidate(receipt.proxy)
        if not raw._ownership.closed:
            original_raw_close(raw)
        connection.close()
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("name", ["operation", "listing", "inspection", "migration"])
@pytest.mark.parametrize("denial", [False, True])
def test_late_driver_close_failure_is_not_silent_and_primary_survives(
    engine, monkeypatch, name, denial
):
    native_close = ownership._TrackedSQLite._native_close
    primary = ResourceNotFound()
    calls = 0

    def once(raw):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KeyboardInterrupt("PRIVATE-CLOSE")
        native_close(raw)

    owner = migration_transaction(engine) if name == "migration" else phase(engine, name)
    try:
        with monkeypatch.context() as patch:
            with (
                pytest.raises(ResourceNotFound if denial else KeyboardInterrupt) as caught,
                owner as connection,
            ):
                raw = connection.connection.driver_connection
                connection.exec_driver_sql("SELECT 1")
                # Force actual physical disposal after logical close; the first
                # native failure is suppressed by SQLAlchemy but latched by raw.
                ownership.quarantine_owned(raw._ownership.receipt)
                patch.setattr(ownership._TrackedSQLite, "_native_close", once)
                if denial:
                    raise primary
            if denial:
                assert caught.value is primary
    finally:
        assert engine.pool.checkedout() == 0
    assert calls == 2
    reusable(engine, raw)


@pytest.mark.parametrize("mutation", [False, True])
def test_two_owned_cleanup_interruptions_preserve_first_and_finish(engine, monkeypatch, mutation):
    work = OperationWork()
    outcome = TransactionOutcome()
    first = KeyboardInterrupt("FIRST")
    second = SystemExit("SECOND")
    original_remove = ownership.event.remove
    calls = []

    def remove(target, name, callback):
        original_remove(target, name, callback)
        calls.append(name)
        raise first if len(calls) == 1 else second

    owner = (
        admission_transaction(engine, outcome, work=work)
        if mutation
        else operation_connection(engine, work)
    )
    with (
        monkeypatch.context() as patch,
        pytest.raises(KeyboardInterrupt) as caught,
        owner as connection,
    ):
        raw = connection.connection.driver_connection
        connection.exec_driver_sql("SELECT 1")
        patch.setattr(ownership.event, "remove", remove)
    assert caught.value is first
    assert calls == ["before_cursor_execute", "after_cursor_execute"]
    assert work._started is None and work._connection is None
    assert engine.pool.checkedout() == 0
    if mutation:
        assert outcome.commit_acknowledged and outcome.cleanup_failed
    reusable(engine, raw)


def test_migration_ownership_failure_is_fixed_without_database_error_fabrication(
    engine, monkeypatch
):
    original = Connection.close

    def once(connection):
        original(connection)
        raise RuntimeError("PRIVATE-CLOSE")

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "close", once)
        with (
            pytest.raises(MigrationRefused, match="^migration_database_failure$") as caught,
            migration_transaction(engine) as connection,
        ):
            connection.exec_driver_sql("SELECT 1")
    assert caught.value.__suppress_context__
    assert engine.pool.checkedout() == 0
    # A post-return failure cannot safely invalidate a record that another
    # generation may already borrow. The next checkout quarantines its closed
    # raw object before yielding; only a later fresh acquisition can succeed.
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine):
        pytest.fail("closed physical connection was yielded")
    reusable(engine)


def test_owned_installation_inspection_and_database_callers_keep_real_guard(tmp_path, settings):
    engine = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path}/installation.sqlite", pool_size=1, max_overflow=0
    )
    database = Database(settings)
    legacy = database.engine
    database.engine = engine
    try:
        database.migrate(installation_key="synthetic-owned-integration")
        assert database.ping()
        result = database.schema_compatibility()
        assert (result.status, result.code) == ("incompatible", "migration_only")
        record = database.add("example", {"value": "safe"})
        assert database.get(record)["value"] == "safe"
        database.audit("synthetic-user", "example.read", record)
        with owned_connect(engine) as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM audit").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert database.schema_compatibility().code == "migration_only"
    finally:
        assert engine.pool.checkedout() == 0
        engine.dispose()
        legacy.dispose()


@pytest.mark.parametrize("name", ["listing", "inspection"])
@pytest.mark.parametrize("after", [False, True])
def test_partial_callback_install_does_not_leave_lease_or_mutated_settings(
    engine, monkeypatch, name, after
):
    original = ownership.ProgressLease.install
    observed = []

    def refuse(lease, callback, interval):
        observed.append(lease._raw)
        if after:
            original(lease, callback, interval)
        raise RuntimeError("PRIVATE-INSTALL")

    expected = Fault if name == "listing" else RuntimeError
    with monkeypatch.context() as patch:
        patch.setattr(ownership.ProgressLease, "install", refuse)
        with pytest.raises(expected), phase(engine, name):
            pytest.fail("partial setup yielded")
    assert engine.pool.checkedout() == 0
    with owned_connect(engine) as connection:
        assert connection.connection.driver_connection._ownership.lease is None
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        current = connection.connection.driver_connection
        if name == "listing":
            assert current is not observed[0]
            with pytest.raises(sqlite3.ProgrammingError):
                observed[0].execute("SELECT 1")
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 3000
        else:
            assert current is observed[0]
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741
    reusable(engine)


@pytest.mark.parametrize("consumer", ["operation", "inspection"])
def test_optional_progress_refuses_substituted_pool_before_existing_connection_effects(
    engine, monkeypatch, consumer
):
    with owned_connect(engine) as connection:
        raw = connection.connection.driver_connection
        original_pool = engine.pool
        original_execute = ownership._TrackedSQLite.execute
        native_calls = []
        replacement = QueuePool(lambda: sqlite3.connect(":memory:"))

        def observe(*args, **kwargs):
            native_calls.append(1)
            return original_execute(*args, **kwargs)

        try:
            engine.pool = replacement
            with monkeypatch.context() as patch:
                patch.setattr(ownership._TrackedSQLite, "execute", observe)
                with pytest.raises(SQLiteOwnershipError):
                    if consumer == "operation":
                        OperationWork().attach(connection)
                    else:
                        with _inspection(connection):
                            pytest.fail("invalid ownership was accepted")
            assert native_calls == []
            assert raw._ownership.lease is None
            assert "operation_work" not in connection.info
        finally:
            engine.pool = original_pool
            replacement.dispose()
        assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == 741
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_exact_installed_component_smoke_helper(tmp_path):
    import ast
    from pathlib import Path

    source = Path(__file__).parents[1] / "scripts" / "ci_smoke.py"
    node = next(
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "operation_components_smoke"
    )
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    namespace["operation_components_smoke"](tmp_path)
