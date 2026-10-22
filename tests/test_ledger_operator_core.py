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
