"""Real SQLite/pool ownership, without production factory activation."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import StatementError

from agent_rewind import sqlite_ownership as ownership
from agent_rewind.sqlite_ownership import (
    SQLiteOwnershipError,
    acquire_progress,
    cleanup_snapshot,
    close_owned,
    connect_owned,
    create_owned_sqlite_engine,
    owned_begin,
    owned_connect,
    require_clean,
    require_owned_sqlite,
)


@pytest.fixture
def engine(tmp_path):
    value = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path}/owned.sqlite", pool_size=1, max_overflow=0, pool_timeout=0.05
    )
    yield value
    assert value.pool.checkedout() == 0
    value.dispose()


def raw(connection):
    return connection.connection.driver_connection


def assert_reusable(engine, *, previous=None):
    with owned_connect(engine) as connection:
        if previous is not None:
            assert raw(connection) is not previous
        assert connection.exec_driver_sql("SELECT 41+1").scalar_one() == 42
        assert not raw(connection).in_transaction
    assert engine.pool.checkedout() == 0


def test_success_commit_rollback_clean_reuse_and_settings(engine):
    with owned_begin(engine) as connection:
        original = raw(connection)
        connection.exec_driver_sql("CREATE TABLE sample (value INTEGER)")
        connection.exec_driver_sql("PRAGMA busy_timeout=741")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("INSERT INTO sample VALUES (1)")
    primary = ValueError("private-body")
    with pytest.raises(ValueError) as caught, owned_begin(engine) as connection:
        assert raw(connection) is original
        connection.exec_driver_sql("INSERT INTO sample VALUES (2)")
        raise primary
    assert caught.value is primary
    with owned_connect(engine) as connection:
        assert connection.exec_driver_sql("SELECT value FROM sample").all() == [(1,)]
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 741
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


@pytest.mark.parametrize(
    "url",
    ["sqlite://", "sqlite:///:memory:", "sqlite:///file:x?mode=memory", "sqlite:///x?uri=true"],
)
def test_unsupported_factory_urls(url):
    with pytest.raises(SQLiteOwnershipError):
        create_owned_sqlite_engine(url)


def test_untracked_passthrough_and_no_false_capability(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.sqlite")
    try:
        with pytest.raises(SQLiteOwnershipError):
            require_owned_sqlite(engine)
        with owned_begin(engine) as connection:
            connection.exec_driver_sql("CREATE TABLE sample (id INTEGER)")
        connection, receipt = connect_owned(engine)
        assert receipt is None
        close_owned(connection, receipt)
        require_clean(cleanup_snapshot(receipt))
    finally:
        engine.dispose()


def test_bare_checkout_and_automatic_revalidation_refuse(engine):
    with pytest.raises(SQLiteOwnershipError):
        engine.connect()
    with owned_connect(engine) as connection:
        connection.invalidate()
        with pytest.raises(StatementError) as caught:
            connection.exec_driver_sql("SELECT 1")
        assert isinstance(caught.value.orig, SQLiteOwnershipError)
    assert_reusable(engine)


def test_no_ambient_permission_for_nested_engine_checkout(tmp_path):
    engine = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path}/nested.sqlite", pool_size=2, max_overflow=0
    )
    try:
        with owned_connect(engine) as connection:
            first = raw(connection)
            with pytest.raises(SQLiteOwnershipError):
                engine.connect()
            assert raw(connection) is first
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    finally:
        assert engine.pool.checkedout() == 0
        engine.dispose()


def test_lease_nested_refusal_keeps_owner_and_callback(engine):
    with owned_connect(engine) as connection:
        calls = []
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: calls.append(1) or 0, 1)
        with pytest.raises(SQLiteOwnershipError):
            acquire_progress(connection, owner=object())
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert calls
        lease.release()
        lease.release()
        count = len(calls)
        connection.exec_driver_sql("SELECT 2")
        assert len(calls) == count


@pytest.mark.parametrize("clear", [False, True])
def test_direct_handler_attempt_keeps_native_callback_and_forces_replacement(engine, clear):
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
        calls = []
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: calls.append(1) or 0, 1)
        with pytest.raises(SQLiteOwnershipError):
            original.set_progress_handler(None if clear else lambda: 0, 0 if clear else 1)
        connection.exec_driver_sql("SELECT 1")
        assert calls
        lease.release()
    assert_reusable(engine, previous=original)


def test_retained_idle_raw_attempt_does_not_rewrite_old_verdict(engine):
    connection, receipt = connect_owned(engine)
    original = raw(connection)
    close_owned(connection, receipt)
    old = cleanup_snapshot(receipt)
    require_clean(old)
    with pytest.raises(SQLiteOwnershipError):
        original.set_progress_handler(None, 0)
    assert cleanup_snapshot(receipt) == old
    with pytest.raises(SQLiteOwnershipError):
        connect_owned(engine)
    assert_reusable(engine, previous=original)


@pytest.mark.parametrize("method", ["rollback", "close"])
def test_premature_control_while_leased_never_rolls_back_under_callback(engine, method):
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS sample (id INTEGER)")
        connection.exec_driver_sql("INSERT INTO sample VALUES (1)")
        lease = acquire_progress(connection, owner=object())
        calls = []
        lease.install(lambda: calls.append(1) or 0, 1)
        with pytest.raises(SQLiteOwnershipError):
            getattr(connection, method)()
        assert original.in_transaction
        assert calls == []
        lease.release()
    assert_reusable(engine, previous=original)


def test_untracked_raw_begin_is_discarded_without_success(engine):
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
        original.execute("BEGIN")
    assert_reusable(engine, previous=original)


@pytest.mark.parametrize("stage", ["install", "release"])
def test_partial_native_handler_failure_is_removed_or_discarded(engine, monkeypatch, stage):
    original_method = ownership._TrackedSQLite._native_progress
    seen = False

    def failing(self, callback, interval):
        nonlocal seen
        original_method(self, callback, interval)
        if not seen and ((callback is not None) == (stage == "install")):
            seen = True
            raise sqlite3.OperationalError("private-handler")

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_progress", failing)
    with pytest.raises(sqlite3.OperationalError), owned_connect(engine) as connection:
        original = raw(connection)
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: 0, 1)
        lease.release()
    assert seen
    assert_reusable(engine, previous=original)


@pytest.mark.parametrize("new_record", [False, True])
@pytest.mark.parametrize("after_close", [False, True])
def test_bootstrap_failure_with_suppressed_close_retains_raw_cleanup(
    engine, monkeypatch, new_record, after_close
):
    if not new_record:
        connection, receipt = connect_owned(engine)
        connection.invalidate()
        close_owned(connection, receipt)
    handles = []

    def bootstrap(dbapi, record):
        handles.append(dbapi)
        raise RuntimeError("private-bootstrap")

    native_close = ownership._TrackedSQLite._native_close
    failed = False

    def broken_close(self):
        nonlocal failed
        if not failed:
            failed = True
            if after_close:
                native_close(self)
            raise RuntimeError("private-close")
        native_close(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", broken_close)
    event.listen(engine, "connect", bootstrap)
    try:
        with pytest.raises(SQLiteOwnershipError) as caught:
            connect_owned(engine)
        assert "private" not in str(caught.value)
        assert handles and failed
        with pytest.raises(sqlite3.ProgrammingError):
            handles[0].execute("SELECT 1")
        assert engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "connect", bootstrap)
    assert_reusable(engine, previous=handles[0])


@pytest.mark.parametrize("close_fault", [False, True])
def test_engine_connect_failure_releases_captured_public_proxy(engine, monkeypatch, close_fault):
    handles = []

    def constructor(connection):
        handles.append(raw(connection))
        raise ValueError("private-constructor")

    native_close = ownership._TrackedSQLite._native_close
    failed = False

    def broken_close(self):
        nonlocal failed
        if close_fault and not failed:
            failed = True
            raise RuntimeError("private-close")
        native_close(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", broken_close)
    event.listen(engine, "engine_connect", constructor)
    try:
        with pytest.raises(SQLiteOwnershipError):
            connect_owned(engine)
        assert engine.pool.checkedout() == 0
        with pytest.raises(sqlite3.ProgrammingError):
            handles[0].execute("SELECT 1")
    finally:
        event.remove(engine, "engine_connect", constructor)
    assert_reusable(engine, previous=handles[0])


def test_overflow_native_close_failure_after_checkin_cannot_report_success(tmp_path, monkeypatch):
    engine = create_owned_sqlite_engine(
        f"sqlite:///{tmp_path}/overflow.sqlite", pool_size=1, max_overflow=1
    )
    native_close = ownership._TrackedSQLite._native_close
    try:
        first, receipt1 = connect_owned(engine)
        second, receipt2 = connect_owned(engine)
        original = raw(second)
        close_owned(first, receipt1)
        failed = False

        def broken_close(self):
            nonlocal failed
            if self is original and not failed:
                failed = True
                raise RuntimeError("private-overflow-close")
            native_close(self)

        monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", broken_close)
        close_owned(second, receipt2)
        assert failed
        with pytest.raises(SQLiteOwnershipError):
            require_clean(cleanup_snapshot(receipt2))
        # A manual owner, like the contexts, must finish bounded disposal.
        ownership._cleanup(receipt2, second)
        assert engine.pool.checkedout() == 0
        with pytest.raises(sqlite3.ProgrammingError):
            original.execute("SELECT 1")
    finally:
        engine.dispose()


@pytest.mark.parametrize("primary_kind", ["denial", "interrupt", "none"])
def test_cleanup_interruption_preserves_primary_and_finishes_pool(
    engine, monkeypatch, primary_kind
):
    first_interrupt = KeyboardInterrupt("first-cleanup")
    native_close = ownership._TrackedSQLite._native_close
    seen = False

    def broken_close(self):
        nonlocal seen
        if not seen:
            seen = True
            raise first_interrupt
        native_close(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", broken_close)
    primary = {"denial": PermissionError("denied"), "interrupt": SystemExit("body")}.get(
        primary_kind
    )
    expected = primary if primary is not None else first_interrupt
    with pytest.raises(type(expected)) as caught, owned_connect(engine) as connection:
        original = raw(connection)
        original.execute("BEGIN")  # forces quarantine/disposal, not a normal pool return
        if primary is not None:
            raise primary
    assert caught.value is expected
    assert seen and engine.pool.checkedout() == 0
    assert_reusable(engine, previous=original)


def test_connection_close_failure_before_action_is_bounded_and_replaced(engine, monkeypatch):
    real_close = Connection.close
    seen = False

    def fail_once(self):
        nonlocal seen
        if not seen:
            seen = True
            raise RuntimeError("private-close-before")
        real_close(self)

    monkeypatch.setattr(Connection, "close", fail_once)
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
    assert seen
    assert_reusable(engine, previous=original)


def test_postcommit_cleanup_failure_retains_commit_observations(engine, monkeypatch):
    real_close = Connection.close
    seen = False

    def fail_once(self):
        nonlocal seen
        if not seen:
            seen = True
            raise RuntimeError("private-after-ack")
        real_close(self)

    monkeypatch.setattr(Connection, "close", fail_once)
    with pytest.raises(SQLiteOwnershipError) as caught, owned_begin(engine) as connection:
        connection.exec_driver_sql("CREATE TABLE committed (id INTEGER)")
        connection.exec_driver_sql("INSERT INTO committed VALUES (7)")
    assert caught.value.verdict.commit_attempted
    assert caught.value.verdict.commit_acknowledged
    with owned_connect(engine) as connection:
        assert connection.exec_driver_sql("SELECT id FROM committed").scalar_one() == 7


def test_prior_verdict_and_stale_lease_are_independent_of_concurrent_next_owner(engine):
    connection, receipt = connect_owned(engine)
    original = raw(connection)
    lease = acquire_progress(connection, owner=object())
    lease.install(lambda: 0, 1)
    lease.release()
    close_owned(connection, receipt)
    entered, release = Event(), Event()

    def next_owner():
        with owned_connect(engine) as second:
            assert raw(second) is original
            next_lease = acquire_progress(second, owner=object())
            hits = []
            next_lease.install(lambda: hits.append(1) or 0, 1)
            entered.set()
            assert release.wait(5)
            second.exec_driver_sql("SELECT 3")
            assert hits
            next_lease.release()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(next_owner)
        try:
            assert entered.wait(5)
            require_clean(cleanup_snapshot(receipt))
            lease.release()  # released old lease is inert
            with pytest.raises(SQLiteOwnershipError):
                lease.install(lambda: 1, 1)
            close_owned(connection, receipt)  # old closed Connection is inert
        finally:
            release.set()
        future.result(timeout=5)
    assert_reusable(engine)


def test_lifecycle_reuse_performs_no_sql_or_hardcoded_pragma_restore(engine):
    connection, receipt = connect_owned(engine)
    original = raw(connection)
    original.execute("PRAGMA busy_timeout=741")
    statements = []
    original.set_trace_callback(statements.append)
    close_owned(connection, receipt)
    second, second_receipt = connect_owned(engine)
    assert raw(second) is original
    close_owned(second, second_receipt)
    assert statements == []
    original.set_trace_callback(None)
    require_clean(cleanup_snapshot(second_receipt))


@pytest.mark.parametrize("stage", ["install", "release"])
def test_partial_callback_interruption_preserves_identity_and_capacity(engine, monkeypatch, stage):
    method = ownership._TrackedSQLite._native_progress
    interrupt = KeyboardInterrupt("callback-interruption")
    raised = False

    def fail_once(self, callback, interval):
        nonlocal raised
        method(self, callback, interval)
        if not raised and ((callback is not None) == (stage == "install")):
            raised = True
            raise interrupt

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_progress", fail_once)
    with pytest.raises(KeyboardInterrupt) as caught, owned_connect(engine) as connection:
        original = raw(connection)
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: 0, 1)
        lease.release()
    assert caught.value is interrupt
    assert_reusable(engine, previous=original)


def test_native_callback_cancellation_releases_before_rollback(engine):
    with owned_connect(engine) as connection:
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: 1, 1)
        try:
            with pytest.raises(ownership.SQLAlchemyError):
                connection.exec_driver_sql("SELECT 1")
        finally:
            lease.release()
    assert_reusable(engine)


@pytest.mark.parametrize("primary", [False, True])
def test_native_rollback_interruption_is_not_replaced_by_cleanup(engine, monkeypatch, primary):
    interrupt = KeyboardInterrupt("rollback-interrupt")
    body = PermissionError("original-denial")
    method = ownership._TrackedSQLite._native_rollback
    raised = False

    def fail_once(self):
        nonlocal raised
        if not raised and self.in_transaction:
            raised = True
            raise interrupt
        method(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_rollback", fail_once)
    with (
        pytest.raises(PermissionError if primary else KeyboardInterrupt) as caught,
        owned_begin(engine) as connection,
    ):
        original = raw(connection)
        connection.exec_driver_sql("CREATE TABLE sample (id INTEGER)")
        connection.exec_driver_sql("INSERT INTO sample VALUES (1)")
        if primary:
            raise body
        connection.rollback()
    assert caught.value is (body if primary else interrupt)
    assert raised
    assert_reusable(engine, previous=original)


def test_two_distinct_cleanup_interruptions_keep_first(engine, monkeypatch):
    method = ownership._TrackedSQLite._native_close
    interruptions = [KeyboardInterrupt("first"), SystemExit("second")]
    calls = 0

    def fail_twice(self):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise interruptions[calls - 1]
        method(self)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", fail_twice)
    with pytest.raises(KeyboardInterrupt) as caught, owned_connect(engine) as connection:
        original = raw(connection)
        original.execute("BEGIN")
    assert caught.value is interruptions[0]
    assert calls == 3
    assert_reusable(engine, previous=original)


def test_repeated_native_close_failure_is_finite_and_never_claims_disposal(engine, monkeypatch):
    method = ownership._TrackedSQLite._native_close
    attempts = []

    def fail(self):
        attempts.append(self)
        raise RuntimeError("persistent-private-close")

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", fail)
    original = None
    try:
        with pytest.raises(SQLiteOwnershipError) as caught, owned_connect(engine) as connection:
            original = raw(connection)
            original.execute("BEGIN")
        verdict = caught.value.verdict
        assert verdict.failed and verdict.disposal_required
        assert not verdict.disposal_acknowledged
        assert engine.pool.checkedout() == 0
        assert 1 <= len(attempts) <= 5
    finally:
        # Persistent driver failure cannot prove resource reclamation. The test
        # owns this synthetic handle and releases it after restoring the driver.
        monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", method)
        if original is not None:
            original.close()
    assert_reusable(engine, previous=original)


def test_noop_logical_close_is_not_terminal_proof(engine, monkeypatch):
    real_close = Connection.close
    calls = 0

    def noop_first(self):
        nonlocal calls
        calls += 1
        if calls != 1:
            real_close(self)

    monkeypatch.setattr(Connection, "close", noop_first)
    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
    assert calls >= 2
    assert_reusable(engine, previous=original)


def test_failed_old_generation_receipt_survives_successful_new_borrower(engine):
    first, receipt = connect_owned(engine)
    old = raw(first)
    old.execute("BEGIN")
    close_owned(first, receipt)
    prior = cleanup_snapshot(receipt)
    assert prior.failed
    with owned_connect(engine) as second:
        assert raw(second) is not old
        lease = acquire_progress(second, owner=object())
        lease.install(lambda: 0, 1)
        with pytest.raises(SQLiteOwnershipError):
            require_clean(cleanup_snapshot(receipt))
        close_owned(first, receipt)
        assert cleanup_snapshot(receipt) == prior
        assert second.exec_driver_sql("SELECT 1").scalar_one() == 1
        lease.release()


@pytest.mark.parametrize("new_record", [False, True])
def test_bootstrap_primary_interruption_and_no_fabricated_connection_close(engine, new_record):
    if not new_record:
        connection, receipt = connect_owned(engine)
        connection.invalidate()
        close_owned(connection, receipt)
    interrupt = SystemExit("bootstrap-primary")

    def fail(dbapi, record):
        raise interrupt

    event.listen(engine, "connect", fail)
    try:
        with pytest.raises(SystemExit) as caught:
            connect_owned(engine)
        assert caught.value is interrupt
        assert engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "connect", fail)
    assert_reusable(engine)


def test_dead_handle_refuses_and_is_replaced(engine):
    connection, receipt = connect_owned(engine)
    original = raw(connection)
    close_owned(connection, receipt)
    original.close()
    with pytest.raises(SQLiteOwnershipError):
        connect_owned(engine)
    assert_reusable(engine, previous=original)


def test_post_return_close_error_does_not_dispose_concurrent_new_owner(engine, monkeypatch):
    returned, acquired, release = Event(), Event(), Event()
    real_close = Connection.close
    first = None
    first_raw = None

    def close_then_fail(self):
        real_close(self)
        if self is first:
            returned.set()
            assert acquired.wait(5)
            raise RuntimeError("private-after-return")

    monkeypatch.setattr(Connection, "close", close_then_fail)

    def next_owner():
        assert returned.wait(5)
        with owned_connect(engine) as connection:
            assert raw(connection) is first_raw
            lease = acquire_progress(connection, owner=object())
            hits = []
            lease.install(lambda: hits.append(1) or 0, 1)
            acquired.set()
            assert release.wait(5)
            connection.exec_driver_sql("SELECT 1")
            assert hits
            lease.release()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(next_owner)
        try:
            with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
                first = connection
                first_raw = raw(connection)
        finally:
            release.set()
        future.result(timeout=5)
    assert_reusable(engine)


def test_persistent_unknown_callback_removal_discards_without_sql(engine, monkeypatch):
    native = ownership._TrackedSQLite._native_progress
    calls = []

    def failing_clear(self, callback, interval):
        calls.append(callback is None)
        if callback is None:
            raise sqlite3.OperationalError("private-clear-failed")
        native(self, callback, interval)

    monkeypatch.setattr(ownership._TrackedSQLite, "_native_progress", failing_clear)
    with pytest.raises(sqlite3.OperationalError), owned_connect(engine) as connection:
        original = raw(connection)
        lease = acquire_progress(connection, owner=object())
        lease.install(lambda: 1, 1)
        lease.release()
    # Reset quarantines by physical close; it must not call the failed setter
    # again on a closed handle or issue rollback SQL through its callback.
    assert calls == [False, True]
    with pytest.raises(sqlite3.ProgrammingError):
        original.execute("SELECT 1")
    assert_reusable(engine, previous=original)


def test_native_property_failure_at_return_cannot_skip_quarantine(engine, monkeypatch):
    descriptor = sqlite3.Connection.in_transaction
    original = None
    failed = False

    def in_transaction(self):
        nonlocal failed
        if self is original and not failed:
            failed = True
            raise sqlite3.OperationalError("private-property")
        return descriptor.__get__(self)

    with pytest.raises(SQLiteOwnershipError), owned_connect(engine) as connection:
        original = raw(connection)
        monkeypatch.setattr(ownership._TrackedSQLite, "in_transaction", property(in_transaction))
    assert failed
    assert_reusable(engine, previous=original)


def test_option_engine_cannot_retroactively_certify_the_owned_pool(engine):
    alias = engine.execution_options()
    with pytest.raises(SQLiteOwnershipError):
        require_owned_sqlite(alias)
    with pytest.raises(SQLiteOwnershipError):
        connect_owned(alias)
    assert_reusable(engine)


@pytest.mark.parametrize("url", ["secret malformed URL", "sqlite://bad:secret@host/x", None])
def test_factory_input_errors_are_fixed_and_do_not_echo_values(url):
    with pytest.raises(SQLiteOwnershipError) as caught:
        create_owned_sqlite_engine(url)
    assert str(caught.value) == "Owned SQLite connection unavailable."
    assert caught.value.__suppress_context__ or caught.value.__context__ is None


@pytest.mark.parametrize("context", [owned_connect, owned_begin])
@pytest.mark.parametrize("dispose_replacement", [None, False, True])
def test_replaced_pool_refuses_before_body_or_caller_sql(engine, context, dispose_replacement):
    from sqlalchemy.pool import QueuePool

    original_pool = engine.pool
    statements, connections = [], []

    def creator():
        handle = sqlite3.connect(":memory:")
        connections.append(handle)
        handle.set_trace_callback(statements.append)
        return handle

    replacement = QueuePool(creator, pool_size=1, max_overflow=0)
    engine.pool = replacement
    entered = False
    try:
        if dispose_replacement is not None:
            engine.dispose(close=dispose_replacement)
        with pytest.raises(SQLiteOwnershipError), context(engine) as connection:
            entered = True
            connection.exec_driver_sql("SELECT 'must-not-run'")
        assert not entered
        assert statements == []
        assert connections == []
        assert engine.pool.checkedout() == 0
        with pytest.raises(SQLiteOwnershipError):
            require_owned_sqlite(engine)
    finally:
        engine.pool.dispose()
        replacement.dispose()
        engine.pool = original_pool
    assert_reusable(engine)


@pytest.mark.parametrize("close", [False, True])
def test_supported_engine_dispose_preserves_factory_pool_generations(engine, close):
    connection, receipt = connect_owned(engine)
    first = raw(connection)
    close_owned(connection, receipt)
    old_pool = engine.pool
    engine.dispose(close=close)
    try:
        assert engine.pool is not old_pool
        require_owned_sqlite(engine)
        assert_reusable(engine, previous=first)
    finally:
        old_pool.dispose()


@pytest.mark.parametrize("close", [False, True])
def test_dispose_keeps_outstanding_owned_checkout_and_new_pool_independent(engine, close):
    connection, receipt = connect_owned(engine)
    first = raw(connection)
    lease = acquire_progress(connection, owner=object())
    lease.install(lambda: 0, 1)
    old_pool = engine.pool
    engine.dispose(close=close)
    try:
        assert_reusable(engine, previous=first)
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        lease.release()
        close_owned(connection, receipt)
        require_clean(cleanup_snapshot(receipt))
        assert connection.closed
        assert not receipt.proxy.is_valid
        assert engine.pool.checkedout() == 0
    finally:
        old_pool.dispose()


@pytest.mark.parametrize("state", ["transaction", "lease", "foreign", "closed", "invalidated"])
def test_pre_yield_attestation_refuses_constructor_dirty_checkout_and_releases(engine, state):
    handles = []
    callbacks = []

    def constructor(connection):
        handle = raw(connection)
        handles.append(handle)
        if state == "transaction":
            handle.execute("BEGIN")
        elif state == "lease":
            lease = acquire_progress(connection, owner=object())
            lease.install(lambda: callbacks.append(1) or 0, 1)
        elif state == "foreign":
            with pytest.raises(SQLiteOwnershipError):
                handle.set_progress_handler(lambda: 0, 1)
        elif state == "closed":
            connection.close()
        else:
            connection.invalidate()

    event.listen(engine, "engine_connect", constructor)
    entered = False
    try:
        with pytest.raises(SQLiteOwnershipError) as caught, owned_connect(engine):
            entered = True
        assert not entered
        assert callbacks == []
        assert caught.value.verdict.failed
        assert caught.value.verdict.returned
        assert engine.pool.checkedout() == 0
        with pytest.raises(sqlite3.ProgrammingError):
            handles[0].execute("SELECT 1")
    finally:
        event.remove(engine, "engine_connect", constructor)
    if state == "closed":
        # The constructor returned its record before attestation; cleanup must
        # not invalidate a potentially reused record. Its closed raw is refused
        # at the next checkout, rather than silently retried for that caller.
        with pytest.raises(SQLiteOwnershipError):
            connect_owned(engine)
        assert engine.pool.checkedout() == 0
    assert_reusable(engine, previous=handles[0])


def test_missing_checkout_receipt_refuses_before_body_with_bounded_native_cleanup(
    engine, monkeypatch
):
    # Simulate missing checkout instrumentation through the public event API.
    # A factory-created raw handle alone must not certify a complete checkout.
    checkout = next(iter(engine.pool.dispatch.checkout))
    event.remove(engine, "checkout", checkout)
    handles = []
    close_calls = []
    native_close = ownership._TrackedSQLite._native_close

    def capture(connection):
        handles.append(raw(connection))

    def fail_once(self):
        close_calls.append(self)
        if len(close_calls) == 1:
            raise RuntimeError("private-native-close")
        native_close(self)

    event.listen(engine, "engine_connect", capture)
    monkeypatch.setattr(ownership._TrackedSQLite, "_native_close", fail_once)
    entered = False
    try:
        with pytest.raises(SQLiteOwnershipError) as caught, owned_connect(engine):
            entered = True
        assert not entered
        assert len(close_calls) == 2
        assert caught.value.verdict.generation == 0
        assert caught.value.verdict.failed
        assert caught.value.verdict.returned
        assert caught.value.verdict.disposal_acknowledged
        assert engine.pool.checkedout() == 0
        with pytest.raises(sqlite3.ProgrammingError):
            handles[0].execute("SELECT 1")
    finally:
        event.remove(engine, "engine_connect", capture)
        event.listen(engine, "checkout", checkout)
    assert_reusable(engine, previous=handles[0])


def test_pool_changed_during_constructor_refuses_before_body_and_closes_original_checkout(engine):
    from sqlalchemy.pool import QueuePool

    original_pool = engine.pool
    creations = []
    handles = []

    def creator():
        creations.append(1)
        return sqlite3.connect(":memory:")

    replacement = QueuePool(creator, pool_size=1, max_overflow=0)

    def constructor(connection):
        handles.append(raw(connection))
        engine.pool = replacement

    event.listen(engine, "engine_connect", constructor)
    entered = False
    try:
        with pytest.raises(SQLiteOwnershipError) as caught, owned_connect(engine):
            entered = True
        assert not entered
        assert creations == []
        assert original_pool.checkedout() == replacement.checkedout() == 0
        assert caught.value.verdict.failed
        assert caught.value.verdict.returned
        with pytest.raises(sqlite3.ProgrammingError):
            handles[0].execute("SELECT 1")
    finally:
        event.remove(engine, "engine_connect", constructor)
        replacement.dispose()
        engine.pool = original_pool
    assert_reusable(engine, previous=handles[0])
