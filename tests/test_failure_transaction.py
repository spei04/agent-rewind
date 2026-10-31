"""Native transaction truth for the fixed dormant failure migration boundary."""

import json
import sqlite3
from contextlib import closing

import pytest
from ledger_operator_fixture import assert_closed
from ledger_reader_fixture import complete_ar6, seed_ar7, sqlite_snapshot
from sqlalchemy.engine import Connection
from test_failure_schema import rows

from agent_rewind.migrations import ledger_transaction as transaction
from agent_rewind.migrations.failure_catalog import inspect_failure_catalog
from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.failure_transaction import failure_transaction
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, _require_ledger_body
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, catalog, installed_profile


@pytest.fixture
def predecessor(tmp_path):
    case = seed_ar7(complete_ar6(tmp_path / "failure-transaction.sqlite", legacy=False))
    try:
        yield case
    finally:
        case.dispose()


def present(path):
    with closing(sqlite3.connect(path)) as raw:
        return raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='job_failure_evidence'"
        ).fetchall() == [("job_failure_evidence",)]


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_atomic_20_to_21_and_reentry_keep_history_and_owned_body(tmp_path, legacy, record_property):
    case = seed_ar7(complete_ar6(tmp_path / "transition.sqlite", legacy=legacy))
    engine = case.operator_engine()
    try:
        with case.engine.connect() as connection:
            original = rows(connection)
        first, work = LedgerOutcome(), LedgerWork()
        with failure_transaction(engine, first, work=work) as connection:
            saved = connection
            assert _require_ledger_body(connection) is work
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.connection.driver_connection.in_transaction
            # A distinct native writer cannot enter while the owned body exists.
            with closing(sqlite3.connect(case.path, timeout=0)) as other:
                with pytest.raises(sqlite3.OperationalError) as caught:
                    other.execute("BEGIN IMMEDIATE")
                assert caught.value.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                assert not other.in_transaction
            create_failure_schema(connection)
            observed = inspect_failure_catalog(connection, work)
            assert observed.retained_ar7 == installed_profile("sqlite", LEDGER)
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == LEDGER
            )
            assert rows(connection) == original | {"job_failure_evidence": []}
        assert first.commit_attempted and first.commit_acknowledged and not first.cleanup_failed
        assert present(case.path)
        with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
            _require_ledger_body(saved)
        after = sqlite_snapshot(case.path)
        second, next_work = LedgerOutcome(), LedgerWork()
        with failure_transaction(engine, second, work=next_work) as connection:
            assert _require_ledger_body(connection) is next_work
            assert inspect_failure_catalog(connection, next_work) == observed
            # No fake predecessor revision/profile makes the old catalog accept21.
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                catalog(connection)
        assert second.commit_acknowledged and not second.cleanup_failed
        assert sqlite_snapshot(case.path) == after
        assert engine.pool.checkedout() == 0
        record_property(
            "transaction_work",
            json.dumps(
                {
                    "create_ordinary": work.observed_ordinary,
                    "reentry_ordinary": next_work.observed_ordinary,
                    "bootstrap": work.prepaid_bootstrap,
                    "cleanup_reserved": work.prepaid_cleanup,
                    "cleanup_observed": work.cleanup_observations,
                    "revision_unchanged": True,
                    "component_only": True,
                },
                sort_keys=True,
            ),
        )
    finally:
        engine.dispose()
        case.dispose()


@pytest.mark.parametrize("kind", ["typed", "unexpected", "interruption"])
def test_body_failure_rolls_back_actual_ddl_without_rewriting_history(predecessor, kind):
    case = predecessor
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    error = {
        "typed": MigrationRefused("schema_incompatible"),
        "unexpected": RuntimeError("private-body-canary"),
        "interruption": KeyboardInterrupt("private-interruption-canary"),
    }[kind]
    outcome = LedgerOutcome()
    try:
        expected = KeyboardInterrupt if kind == "interruption" else MigrationRefused
        with (
            pytest.raises(expected) as caught,
            failure_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            create_failure_schema(connection)
            raise error
        if kind in {"typed", "interruption"}:
            assert caught.value is error
        else:
            assert str(caught.value) == "migration_database_failure"
        assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("after_commit", [False, True], ids=["before_native", "after_native"])
def test_lost_commit_ack_keeps_actual_ddl_effect_distinct_from_outcome(
    predecessor, monkeypatch, after_commit
):
    case = predecessor
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    outcome = LedgerOutcome()
    original = Connection.commit
    target, calls = [], []

    def lose_ack(connection):
        if target and connection is target[0]:
            calls.append(connection)
            if after_commit:
                original(connection)
            raise RuntimeError("private-commit-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "commit", lose_ack)
    try:
        with (
            pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
            failure_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            target.append(connection)
            create_failure_schema(connection)
        assert len(calls) == 1
        assert outcome.commit_attempted and not outcome.commit_acknowledged
        assert not outcome.confirmed_precommit_rollback
        assert present(case.path) is after_commit
        if not after_commit:
            assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_lost_rollback_ack_quarantines_without_claiming_confirmed_absence(predecessor, monkeypatch):
    case = predecessor
    before = sqlite_snapshot(case.path)
    engine = case.operator_engine()
    outcome = LedgerOutcome()
    original = Connection.rollback
    target, calls = [], []

    def lose_ack(connection):
        if target and connection is target[0]:
            calls.append(connection)
            raise RuntimeError("private-rollback-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "rollback", lose_ack)
    try:
        with (
            pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
            failure_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            target.append(connection)
            raw = connection.connection.driver_connection
            create_failure_schema(connection)
            raise MigrationRefused("schema_incompatible")
        assert len(calls) == 1
        assert outcome.rollback_attempted and not outcome.rollback_acknowledged
        assert outcome.cleanup_failed and not outcome.confirmed_precommit_rollback
        assert not outcome.commit_attempted
        assert_closed(raw)
        assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("after_close", [False, True], ids=["before_native", "after_native"])
def test_acknowledged_commit_with_close_failure_never_returns_completion(
    predecessor, monkeypatch, after_close
):
    case = predecessor
    engine = case.operator_engine()
    outcome = LedgerOutcome()
    original = Connection.close
    target, calls = [], []

    def fail_once(connection):
        if target and connection is target[0] and not calls:
            calls.append(connection)
            if after_close:
                original(connection)
            raise RuntimeError("private-close-canary")
        return original(connection)

    monkeypatch.setattr(Connection, "close", fail_once)
    try:
        with (
            pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$"),
            failure_transaction(engine, outcome, work=LedgerWork()) as connection,
        ):
            target.append(connection)
            raw = connection.connection.driver_connection
            create_failure_schema(connection)
        assert len(calls) == 1
        assert outcome.commit_acknowledged and outcome.cleanup_failed
        assert present(case.path)
        assert_closed(raw)
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "mutation", ["missing", "renamed", "unexpected21", "overflow22", "long_name"]
)
def test_exact_inventory_refuses_before_body_without_data_changes(predecessor, mutation):
    case = predecessor
    with case.engine.begin() as connection:
        if mutation == "missing":
            connection.exec_driver_sql("DROP TABLE audit")
        elif mutation == "renamed":
            connection.exec_driver_sql("ALTER TABLE audit RENAME TO unknown_inventory_table")
        elif mutation == "overflow22":
            create_failure_schema(connection)
            connection.exec_driver_sql("CREATE TABLE extra_inventory_table(value INTEGER)")
        elif mutation == "long_name":
            connection.exec_driver_sql('CREATE TABLE "' + "x" * 129 + '"(value INTEGER)')
        else:
            connection.exec_driver_sql("CREATE TABLE extra_inventory_table(value INTEGER)")
    before = sqlite_snapshot(case.path)
    engine, outcome = case.operator_engine(), LedgerOutcome()
    try:
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            failure_transaction(engine, outcome, work=LedgerWork()),
        ):
            pytest.fail("unverified inventory entered the migration body")
        assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_unregistered_engine_refuses_before_connect(predecessor, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unregistered engine reached connection acquisition")

    monkeypatch.setattr(transaction, "connect_owned", forbidden)
    outcome = LedgerOutcome()
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        failure_transaction(predecessor.engine, outcome, work=LedgerWork()),
    ):
        pytest.fail("unregistered engine entered migration body")
    assert not outcome.begin_attempted and not outcome.commit_attempted


@pytest.mark.parametrize("reuse", ["work", "outcome"])
def test_one_shot_state_cannot_be_reused_for_successor(predecessor, reuse):
    case = predecessor
    engine = case.operator_engine()
    outcome, work = LedgerOutcome(), LedgerWork()
    try:
        with failure_transaction(engine, outcome, work=work) as connection:
            create_failure_schema(connection)
        before = sqlite_snapshot(case.path)
        with (
            pytest.raises(MigrationRefused, match="^migration_database_failure$"),
            failure_transaction(
                engine,
                outcome if reuse == "outcome" else LedgerOutcome(),
                work=work if reuse == "work" else LedgerWork(),
            ),
        ):
            pytest.fail("used invocation state entered the body")
        assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_body_budget_exhaustion_precedes_ddl_and_keeps_rollback_truth(predecessor):
    case = predecessor
    before = sqlite_snapshot(case.path)
    engine, outcome, work = case.operator_engine(), LedgerOutcome(), LedgerWork()
    try:
        with (
            pytest.raises(MigrationRefused, match="^ledger_limit_exceeded$"),
            failure_transaction(engine, outcome, work=work) as connection,
        ):
            work.reserve_ordinary(2028 - work.observed_ordinary)
            create_failure_schema(connection)
        assert outcome.confirmed_precommit_rollback and not outcome.commit_attempted
        assert not outcome.cleanup_failed
        assert sqlite_snapshot(case.path) == before
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
