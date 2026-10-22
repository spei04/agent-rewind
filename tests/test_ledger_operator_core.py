"""Authored positive controls for the dormant ledger operator seam."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection

from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused


@pytest.fixture
def engine(tmp_path):
    value = create_ledger_engine(f"sqlite:///{tmp_path}/ledger.sqlite")
    yield value
    assert value.pool.checkedout() == 0
    value.dispose()


def test_read_only_commit_and_sequential_owned_reuse(engine):
    raw = None
    for _ in range(2):
        work, outcome = LedgerWork(), LedgerOutcome()
        with ledger_transaction(engine, outcome, work=work) as connection:
            current = connection.connection.driver_connection
            assert connection.in_transaction() and current.in_transaction
            assert raw is None or raw is current
            raw = current
            assert connection.exec_driver_sql("SELECT 41 + 1").scalar_one() == 42
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert outcome.begun and outcome.begin_attempted
        assert outcome.commit_attempted and outcome.commit_acknowledged
        assert not outcome.cleanup_failed
        assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
        assert 0 < work.observed_ordinary <= 2028


def test_typed_body_refusal_has_confirmed_rollback_and_clean_reuse(engine):
    outcome = LedgerOutcome()
    error = MigrationRefused("source_digest_mismatch")
    with (
        pytest.raises(MigrationRefused) as caught,
        ledger_transaction(engine, outcome, work=LedgerWork()) as connection,
    ):
        assert connection.exec_driver_sql("SELECT 17").scalar_one() == 17
        raise error
    assert caught.value is error
    assert outcome.confirmed_precommit_rollback
    assert not outcome.cleanup_failed
    with ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()) as connection:
        assert connection.exec_driver_sql("SELECT 19").scalar_one() == 19


def test_work_and_outcome_are_consumed(engine):
    work, outcome = LedgerWork(), LedgerOutcome()
    with ledger_transaction(engine, outcome, work=work):
        pass
    for other_work, other_outcome in ((work, LedgerOutcome()), (LedgerWork(), outcome)):
        with (
            pytest.raises(MigrationRefused, match="migration_database_failure"),
            ledger_transaction(engine, other_outcome, work=other_work),
        ):
            pytest.fail("consumed records must not yield")


def test_plain_engine_refuses_before_database_creation(tmp_path):
    path = tmp_path / "plain.sqlite"
    plain = create_engine(f"sqlite:///{path}")
    try:
        with (
            pytest.raises(MigrationRefused, match="schema_incompatible"),
            ledger_transaction(plain, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("unowned engine must not yield")
        assert not path.exists()
    finally:
        plain.dispose()


def test_added_instance_hook_refuses_before_checkout(engine):
    def unreviewed(*args):
        pytest.fail("unreviewed hook executed")

    event.listen(engine, "connect", unreviewed)
    try:
        with (
            pytest.raises(MigrationRefused, match="schema_incompatible"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("hooked engine must not yield")
    finally:
        event.remove(engine, "connect", unreviewed)


def test_class_hook_refuses_before_factory_creation(tmp_path):
    def unreviewed(*args):
        pytest.fail("unreviewed hook executed")

    event.listen(Connection, "before_cursor_execute", unreviewed)
    try:
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            create_ledger_engine(f"sqlite:///{tmp_path}/unopened.sqlite")
    finally:
        event.remove(Connection, "before_cursor_execute", unreviewed)


@pytest.mark.parametrize("value", [True, 0, 31, 1.0, "5"])
def test_invalid_timeouts_refuse(value):
    with pytest.raises(MigrationRefused, match="invalid_lock_timeout"):
        LedgerWork(value)


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "postgresql://x/db"])
def test_unsupported_factory_inputs(url):
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        create_ledger_engine(url)


def test_postgres_factory_retains_only_its_internal_adapter_context():
    from agent_rewind.migrations.ledger_engine import claim_ledger_engine, release_ledger_engine

    value = create_ledger_engine("postgresql+psycopg://postgres@/postgres?host=/tmp")
    try:
        work = LedgerWork()
        work._consume()
        claim = claim_ledger_engine(value, work)
        _, params = value.dialect.create_connect_args(value.url)
        assert params["context"] is value.dialect._psycopg_adapters_map
        release_ledger_engine(claim, clean=True)
    finally:
        value.dispose()


@pytest.mark.parametrize(
    "query",
    [
        "plugin=unreviewed",
        "context=unreviewed",
        "host=/tmp&host=/other",
        "client_encoding=utf8",
        "unknown=value",
    ],
)
def test_postgres_url_refuses_before_constructor(monkeypatch, query):
    from agent_rewind.migrations import ledger_engine

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("unreviewed URL reached constructor")

    monkeypatch.setattr(ledger_engine, "create_engine", forbidden)
    with pytest.raises(MigrationRefused, match="unsupported_runtime_endpoint"):
        create_ledger_engine(f"postgresql+psycopg://postgres@/postgres?{query}")
    assert calls == []


@pytest.mark.parametrize("driver", ["sqlite", "postgres"])
def test_raw_native_timeout_preserves_busy_classification(driver):
    import sqlite3

    import psycopg

    from agent_rewind.migrations.ledger_transaction import _ordinary_error

    if driver == "sqlite":
        raw = sqlite3.connect(":memory:")
        try:
            raw.set_progress_handler(lambda: 1, 1)
            with pytest.raises(sqlite3.OperationalError) as caught:
                raw.execute("SELECT 1")
            error = caught.value
            assert error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
        finally:
            raw.close()
    else:
        error = psycopg.errors.QueryCanceled("synthetic-native-timeout")
    assert str(_ordinary_error(error)) == "migration_busy"


def test_detach_preserves_first_accounting_interruption(engine, monkeypatch):
    from agent_rewind import sqlite_ownership as ownership

    first, later = KeyboardInterrupt("first-detach"), SystemExit("later-release")
    original = ownership.ProgressLease.release
    calls = []

    def interrupted_release(self):
        calls.append(True)
        original(self)
        if len(calls) == 1:
            raise later

    monkeypatch.setattr(ownership.ProgressLease, "release", interrupted_release)
    work = LedgerWork()
    observe = work.observe_cleanup

    def interrupted_observe(kind):
        observe(kind)
        if kind == "detach":
            raise first

    monkeypatch.setattr(work, "observe_cleanup", interrupted_observe)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        ledger_transaction(engine, LedgerOutcome(), work=work) as connection,
    ):
        assert connection.exec_driver_sql("SELECT 47").scalar_one() == 47
    assert caught.value is first
    assert calls


def test_final_deadline_failure_is_classified_before_clean_release(engine, monkeypatch):
    from agent_rewind.migrations import ledger_transaction as transaction

    work = LedgerWork()
    original = work.check
    releases = []
    release = transaction.release_ledger_engine

    def check():
        original()
        if work._detached:
            raise MigrationRefused("migration_busy")

    def tracked_release(claim, *, clean):
        releases.append(clean)
        return release(claim, clean=clean)

    monkeypatch.setattr(work, "check", check)
    monkeypatch.setattr(transaction, "release_ledger_engine", tracked_release)
    with (
        pytest.raises(MigrationRefused, match="ledger_outcome_uncertain"),
        ledger_transaction(engine, LedgerOutcome(), work=work),
    ):
        pass
    assert releases == [False]
    with (
        pytest.raises(MigrationRefused, match="schema_incompatible"),
        ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("uncertain engine must remain poisoned")
