"""Authored full PostgreSQL writer controls; execution requires the native slot."""

import hashlib
import json
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import complete_postgres_ar6, original_rows, postgres_snapshot
from ledger_service_fixture import apply_postgres_service, invoke_postgres, provision_after
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_ledger_operator_postgres import PostgresTrace
from test_ledger_reader_native import (
    NativeParameterWatch,
    _assert_reviewed_ctes,
    _transaction_write_counters,
    _tuple_write_delta,
)
from test_ledger_service import intent
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import (
    LEDGER,
    MigrationRefused,
    catalog,
    checksum,
    installed_profile,
)

__all__ = ["observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in complete PostgreSQL ledger service"
)


@pytest.fixture(autouse=True)
def controlled_database_name(monkeypatch):
    """The reviewed controller selects one absent, exact fixture namespace."""
    token = os.getenv("REWIND_LEDGER_SERVICE_DATABASE_TOKEN")
    if token is not None:
        assert len(token) == 32 and all(value in "0123456789abcdef" for value in token)
        monkeypatch.setattr(migration_tests, "uuid4", lambda: SimpleNamespace(hex=token))


class ServiceWatch:
    def __init__(self, patch):
        self.trace = PostgresTrace(patch)
        self.parameters = NativeParameterWatch(patch, self.trace)
        self.works, self.outcomes = [], []
        work_type, outcome_type = ledger_service.LedgerWork, ledger_service.LedgerOutcome

        def work(timeout_seconds):
            value = work_type(timeout_seconds)
            self.works.append(value)
            return value

        def outcome():
            value = outcome_type()
            self.outcomes.append(value)
            return value

        patch.setattr(ledger_service, "LedgerWork", work)
        patch.setattr(ledger_service, "LedgerOutcome", outcome)

    def verify(self, *, committed):
        assert len(self.works) == len(self.outcomes) == len(committed)
        summaries = []
        for work, outcome, success in zip(self.works, self.outcomes, committed, strict=True):
            raw = work._raw
            assert raw is not None and raw.closed
            events = [event for event in self.trace.events if event[2] == id(raw)]
            receipts = [row for row in self.parameters.receipts if row["raw_id"] == id(raw)]
            sql_calls = [event for event in events if event[1] == "sql-call"]
            assert receipts and sql_calls
            assert [(row["phase"], row["sql_sha256"]) for row in receipts] == [
                (phase, hashlib.sha256(sql.encode()).hexdigest()) for phase, _, _, sql in sql_calls
            ]
            assert all(
                type(row["parameter_count"]) is int and 0 <= row["parameter_count"] <= 16
                for row in receipts
            )
            ordinary = [sql for phase, _, _, sql in sql_calls if phase == "ordinary"]
            # Every target uses the actual two-setter bundle. COMMIT is a native
            # command, leaving its final two setters outside cursor triplets.
            body = ordinary[:-2] if outcome.commit_attempted else ordinary
            assert len(body) % 3 == 0
            for offset in range(0, len(body), 3):
                assert body[offset].startswith("SET LOCAL statement_timeout = '")
                assert body[offset + 1].startswith("SET LOCAL lock_timeout = '")
                assert not body[offset + 2].startswith("SET LOCAL statement_timeout = '")
            if outcome.commit_attempted:
                assert ordinary[-2].startswith("SET LOCAL statement_timeout = '")
                assert ordinary[-1].startswith("SET LOCAL lock_timeout = '")
            assert work.observed_ordinary == 1 + len(ordinary) + int(outcome.commit_attempted)
            assert work.prepaid_bootstrap == 12 and work.prepaid_cleanup == 8
            assert work.observed_ordinary <= 2028 and len(work.cleanup_observations) <= 8
            assert work._detached and not outcome.cleanup_failed
            assert outcome.commit_acknowledged is success
            assert outcome.rollback_acknowledged is (not success)
            bootstrap_commands = [
                sql.strip().upper()
                for phase, kind, _, sql in events
                if phase == "bootstrap" and kind == "command"
            ]
            commands = [
                sql.strip().upper()
                for phase, kind, _, sql in events
                if phase != "bootstrap" and kind == "command"
            ]
            assert bootstrap_commands == ["BEGIN", "ROLLBACK"]
            assert commands == ["BEGIN", "COMMIT" if success else "ROLLBACK"]
            assert not [row for row in receipts if row["phase"] == "cleanup"]
            assert all(row["outcome"] != "pending" for row in receipts)
            if success:
                assert all(row["outcome"] == "return" for row in receipts)
            summaries.append(
                {
                    "ordinary": work.observed_ordinary,
                    "max_binds": max(row["parameter_count"] for row in receipts),
                    "cursor_attempts": len(sql_calls),
                    "bootstrap_cursor_attempts": sum(
                        row["phase"] == "bootstrap" for row in receipts
                    ),
                    "ordinary_cursor_attempts": len(ordinary),
                    "cleanup": work.cleanup_observations,
                    "commit_acknowledged": success,
                    "native_timeout": work.timeout_seconds,
                }
            )
        return summaries


@contextmanager
def observe_service(monkeypatch, record_property):
    with monkeypatch.context() as patch:
        watch = ServiceWatch(patch)
        try:
            yield watch
        finally:
            watch.trace.stop()
            record_property("service_native_trace", json.dumps(watch.trace.events))
            record_property("service_native_parameters", json.dumps(watch.parameters.receipts))


def assert_real_state(state, pg):
    case = state.case
    receipt = state.later_receipt or state.initial_receipt
    assert receipt.outcome == "complete"
    assert state.initial_receipt.imported_opening_microusd == (245000 if case.legacy else 0)
    assert original_rows(case.engine) == case.original_rows
    with case.engine.connect() as connection:
        shape = catalog(connection)
        assert shape == installed_profile("postgresql", LEDGER)
        adoption = dict(
            connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
        )
        assert adoption["installed_schema_fingerprint"] == checksum(shape)
        assert {k: v for k, v in adoption.items() if k != "installed_schema_fingerprint"} == {
            k: v for k, v in case.adoption.items() if k != "installed_schema_fingerprint"
        }
        rows = list(
            connection.execute(
                text(
                    "SELECT * FROM migration_progress WHERE revision<>:revision "
                    "ORDER BY revision,phase"
                ),
                {"revision": LEDGER},
            )
        )
        assert [tuple(row) for row in rows] == case.previous_progress
        accounts = list(
            connection.exec_driver_sql(
                "SELECT opening_held_microusd,held_microusd,accounted_microusd FROM budget_accounts"
            )
        )
        assert all(opening == held and accounted == 0 for opening, held, accounted in accounts)
        assert sum(row[0] for row in accounts) == (735000 if case.legacy else 0)
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM migration_progress WHERE revision='ar_0007_ledger'"
        ).scalar_one() == (3 if state.later_receipt else 2)
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND NOT t.tgisinternal "
                "AND t.tgdeferrable AND t.tginitdeferred"
            ).scalar_one()
            > 0
        )
    drain(pg)


@pytest.mark.parametrize("history", ["empty", "legacy", "later"])
def test_postgres_actual_initialize_provision_and_shared_work(
    pg, observed_reader, monkeypatch, record_property, history
):
    case = complete_postgres_ar6(pg, legacy=history != "empty")
    try:
        with observe_service(monkeypatch, record_property) as watch:
            state = apply_postgres_service(case, pg, history=history)
            metrics = watch.verify(committed=[True] * (2 if history == "later" else 1))
            for work in watch.works:
                events = [event for event in watch.trace.events if event[2] == id(work._raw)]
                immediate = next(
                    i
                    for i, event in enumerate(events)
                    if event[1] == "sql-return" and event[3] == "SET CONSTRAINTS ALL IMMEDIATE"
                )
                commit = next(i for i, event in enumerate(events) if event[1] == "commit-call")
                assert immediate < commit
            record_property("service_work", json.dumps(metrics))
        assert_real_state(state, pg)
    finally:
        case.dispose()


def test_postgres_older_replay_has_no_ddl_or_tuple_writes(
    pg, observed_reader, monkeypatch, record_property
):
    case = complete_postgres_ar6(pg, legacy=True)
    try:
        state = apply_postgres_service(case, pg, history="later")
        before = postgres_snapshot(case.engine)
        drain(pg)
        counters, units = [], []
        original = ledger_service.ledger_transaction

        @contextmanager
        def transaction(engine, outcome, *, work):
            with original(engine, outcome, work=work) as connection:
                start = work.observed_ordinary
                assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
                first = _transaction_write_counters(connection)
                units.append(work.observed_ordinary - start)
                yield connection
                start = work.observed_ordinary
                last = _transaction_write_counters(connection)
                units.append(work.observed_ordinary - start)
                counters.append(_tuple_write_delta(first, last))

        with observe_service(monkeypatch, record_property) as watch, monkeypatch.context() as patch:
            patch.setattr(ledger_service, "ledger_transaction", transaction)
            patch.setattr(
                ledger_service,
                "source_digest",
                lambda *_args: pytest.fail("older replay must not fingerprint current source"),
            )
            replay = invoke_postgres(case, pg, state.initial_manifest)
            assert replay == state.initial_receipt
            assert counters == [{}] and units == [6, 3]
            metrics = watch.verify(committed=[True])
            raw = watch.works[0]._raw
            commands = [
                sql
                for phase, kind, raw_id, sql in watch.trace.events
                if phase == "ordinary" and kind == "sql-call" and raw_id == id(raw)
            ]
            _assert_reviewed_ctes(commands)
            assert all(
                sql.lstrip().upper().startswith(("SELECT", "WITH", "SET", "SHOW", "LOCK"))
                for sql in commands
            )
            record_property("replay_observer_units", json.dumps(units))
            record_property("service_work", json.dumps(metrics))
        assert postgres_snapshot(case.engine) == before
        drain(pg)
    finally:
        case.dispose()


def test_postgres_authorized_different_writer_owner_refuses_without_writes(
    pg, observed_reader, monkeypatch, record_property
):
    case = complete_postgres_ar6(pg, legacy=False)
    try:
        manifest = validate_ledger_manifest(intent(case))
        before = postgres_snapshot(case.engine)
        with pg["admin"].connect() as connection:
            current, table_owner, superuser = connection.exec_driver_sql(
                "SELECT current_user,pg_get_userbyid(c.relowner),r.rolsuper "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_roles r ON r.rolname=current_user "
                "WHERE n.nspname='public' AND c.relname='installation_adoptions'"
            ).one()
            assert superuser and current != table_owner == pg["owner_role"]
        drain(pg)
        engine = create_ledger_engine(pg["admin"].url.render_as_string(hide_password=False))
        with observe_service(monkeypatch, record_property) as watch:
            with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                invoke_postgres(case, pg, manifest, engine=engine)
            metrics = watch.verify(committed=[False])
            sql = watch.trace.sql("ordinary")
            assert any("owner_compatible" in statement for statement in sql)
            assert not any(
                statement.lstrip()
                .upper()
                .startswith(
                    ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "GRANT", "REVOKE")
                )
                for statement in sql
            )
            record_property("service_work", json.dumps(metrics))
        assert postgres_snapshot(case.engine) == before
        drain(pg)
    finally:
        case.dispose()


@pytest.mark.parametrize(
    "stage", ["accounts.insert", "progress.insert", "adoption.publish_fingerprint"]
)
def test_postgres_staged_finalizer_failure_rolls_back(
    pg, observed_reader, monkeypatch, record_property, stage
):
    case = complete_postgres_ar6(pg, legacy=False)
    try:
        manifest = validate_ledger_manifest(intent(case))
        before = postgres_snapshot(case.engine)
        drain(pg)
        delegate = ledger_service._write
        visits = []

        def write(connection, name, values):
            delegate(connection, name, values)
            visits.append(name)
            if name == stage:
                raise MigrationRefused("migration_busy")

        with observe_service(monkeypatch, record_property) as watch, monkeypatch.context() as patch:
            patch.setattr(ledger_service, "_write", write)
            with pytest.raises(MigrationRefused, match="^migration_busy$"):
                invoke_postgres(case, pg, manifest)
            assert visits.count(stage) == 1
            record_property("service_work", json.dumps(watch.verify(committed=[False])))
        assert postgres_snapshot(case.engine) == before
        drain(pg)
    finally:
        case.dispose()


def test_postgres_actual_deferred_constraint_refuses_before_commit(
    pg, observed_reader, monkeypatch, record_property
):
    case = complete_postgres_ar6(pg, legacy=True)
    try:
        state = apply_postgres_service(case, pg, history="legacy")
        manifest = provision_after(state.initial_manifest, state.initial_receipt)
        before = postgres_snapshot(case.engine)
        drain(pg)
        finalize, execute = ledger_service._finalize, ledger_service._execute
        prepared, errors = [], []
        old = state.initial_manifest.accounts[0]

        def transient_change(connection, *args):
            result = finalize(connection, *args)
            for limit in (old.limit_microusd + 1, old.limit_microusd):
                connection.execute(
                    text("UPDATE budget_accounts SET limit_microusd=:limit WHERE id=:id"),
                    {"limit": limit, "id": old.id},
                )
            prepared.append(result.state.head.manifest_digest)
            return result

        def observe_immediate(connection, name, values=None):
            try:
                return execute(connection, name, values)
            except DBAPIError as error:
                if name == "constraints.immediate":
                    errors.append(error.orig.sqlstate)
                raise

        with observe_service(monkeypatch, record_property) as watch, monkeypatch.context() as patch:
            patch.setattr(ledger_service, "_finalize", transient_change)
            patch.setattr(ledger_service, "_execute", observe_immediate)
            with pytest.raises(MigrationRefused, match="^migration_database_failure$"):
                invoke_postgres(case, pg, manifest)
            assert prepared == [manifest.digest] and errors == ["23514"]
            record_property("service_work", json.dumps(watch.verify(committed=[False])))
        assert postgres_snapshot(case.engine) == before
        drain(pg)
    finally:
        case.dispose()
