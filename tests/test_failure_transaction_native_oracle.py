"""Independent PostgreSQL evidence for the dormant failure transaction.

These fixtures construct physical ar7/ar8 shapes directly. They do not install a
registered successor, establish readiness, or activate an application producer.
"""

import json
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
import test_ledger_constraints_postgres as ledger_tests
import test_migrations_postgres as migration_tests
from postgres_control import wait_for_database_drain
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_failure_catalog_native_oracle import full_shape, native_snapshot
from test_failure_schema import rows

from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.failure_transaction import failure_transaction
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, _require_ledger_body
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, MigrationRefused
from agent_rewind.migrations.service import MIGRATOR_LOCK

pg = migration_tests.pg
ledger_pg = ledger_tests.ledger_pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure transaction"
)
SUCCESSOR = "ar_0008_failure_evidence"
PROFILE = (
    Path(__file__).parents[1]
    / "agent_rewind/migrations/profiles/postgresql16_failure_evidence.json"
)


def drain(case):
    wait_for_database_drain(case.control, case.verifier.url.database)


@pytest.fixture
def native_case(ledger_pg):
    engine = create_ledger_engine(ledger_pg["owner"].url.render_as_string(hide_password=False))
    case = SimpleNamespace(
        engine=engine,
        verifier=ledger_pg["owner"],
        app=ledger_pg["app"],
        control=ledger_pg["control"],
        owner_role=ledger_pg["owner_role"],
        app_role=ledger_pg["app_role"],
    )
    try:
        drain(case)
        yield case
    finally:
        engine.dispose()
        drain(case)


def visible_state(case, count):
    """Read all physical schema metadata and all rows on an independent connection."""
    with case.verifier.connect() as connection:
        observed = {"native": native_snapshot(connection, count), "rows": rows(connection)}
    drain(case)
    return observed


def physical_successor(case):
    with case.verifier.begin() as connection:
        create_failure_schema(connection)
    drain(case)


def write_successor(connection):
    create_failure_schema(connection)
    connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": SUCCESSOR})
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() == [
        (SUCCESSOR,)
    ]


def assert_committed_successor(case, before):
    after = visible_state(case, 21)
    assert set(after["rows"]) == set(before["rows"]) | {"job_failure_evidence"}
    assert after["rows"]["job_failure_evidence"] == []
    for name, old_rows in before["rows"].items():
        assert after["rows"][name] == ([(SUCCESSOR,)] if name == "alembic_version" else old_rows)
    with case.verifier.connect() as connection:
        assert full_shape(connection, after["native"]) == json.loads(PROFILE.read_text())
    drain(case)
    return after


def record_outcome(record_property, outcome, work, **facts):
    record_property(
        "native_transaction_outcome",
        json.dumps(
            {
                "outcome": asdict(outcome),
                "work": {
                    "prepaid_bootstrap": work.prepaid_bootstrap,
                    "prepaid_cleanup": work.prepaid_cleanup,
                    "observed_ordinary": work.observed_ordinary,
                    "cleanup_observations": work.cleanup_observations,
                },
                **facts,
            },
            sort_keys=True,
        ),
    )


@pytest.mark.parametrize("table_count", [20, 21], ids=["predecessor20", "successor21"])
def test_real_inventory_owns_rc_body_and_excludes_native_table_access(
    native_case, table_count, record_property
):
    case = native_case
    if table_count == 21:
        physical_successor(case)
    before = visible_state(case, table_count)
    expected_tables = [row[0] for row in before["native"]["table_names"]]
    work, outcome = LedgerWork(), LedgerOutcome()
    with failure_transaction(case.engine, outcome, work=work) as connection:
        raw = connection.connection.driver_connection
        assert connection.exec_driver_sql("SHOW transaction_isolation").scalar_one() == (
            "read committed"
        )
        assert connection.exec_driver_sql("SELECT current_user").scalar_one() == case.owner_role
        assert _require_ledger_body(connection) is work
        locked = list(
            connection.exec_driver_sql(
                """
                SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid=l.relation
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE l.pid=pg_backend_pid() AND l.granted
                  AND l.mode='AccessExclusiveLock' AND n.nspname='public' AND c.relkind='r'
                ORDER BY c.relname
                """
            ).scalars()
        )
        assert locked == expected_tables
        # A real second backend starts only after entry exclusion has completed.
        with case.verifier.connect() as contender:
            contender.exec_driver_sql("SET LOCAL lock_timeout='1ms'")
            with pytest.raises(DBAPIError) as blocked:
                contender.exec_driver_sql("LOCK TABLE public.jobs IN ACCESS SHARE MODE")
            assert blocked.value.orig.sqlstate == "55P03"
            contender.rollback()
    assert raw.closed and outcome.commit_acknowledged and not outcome.cleanup_failed
    with pytest.raises(MigrationRefused, match="^transactional_connection_required$"):
        _require_ledger_body(connection)
    with case.verifier.begin() as contender:
        contender.exec_driver_sql("SET LOCAL lock_timeout='1ms'")
        contender.exec_driver_sql("LOCK TABLE public.jobs IN ACCESS SHARE MODE")
    assert visible_state(case, table_count) == before
    record_outcome(
        record_property, outcome, work, table_count=table_count, locked=locked, blocked="55P03"
    )


@pytest.mark.parametrize(
    "problem,code",
    [
        ("wrong_owner", "migration_owner_required"),
        ("writer_grant", "writer_privileges_present"),
        ("live_session", "writers_not_drained"),
        ("advisory_owner", "migration_busy"),
    ],
    ids=["wrong-owner", "writer-grant", "live-session", "advisory-owner"],
)
def test_real_authority_and_competing_owners_refuse_before_body(
    native_case, problem, code, record_property
):
    case = native_case
    physical_successor(case)
    with ExitStack() as resources:
        engine = case.engine
        if problem == "wrong_owner":
            engine = create_ledger_engine(case.app.url.render_as_string(hide_password=False))
            resources.callback(engine.dispose)
        elif problem == "writer_grant":
            with case.verifier.begin() as connection:
                role = connection.dialect.identifier_preparer.quote_identifier(case.app_role)
                connection.exec_driver_sql(f"GRANT UPDATE ON public.jobs TO {role}")
        before = visible_state(case, 21)
        if problem == "live_session":
            blocker = resources.enter_context(case.app.connect())
            assert blocker.exec_driver_sql("SELECT current_user").scalar_one() == case.app_role
        elif problem == "advisory_owner":
            blocker = resources.enter_context(case.verifier.connect())
            assert blocker.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MIGRATOR_LOCK}
            ).scalar_one()
        work, outcome = LedgerWork(), LedgerOutcome()
        entered = []
        with (
            pytest.raises(MigrationRefused, match=f"^{code}$"),
            failure_transaction(engine, outcome, work=work),
        ):
            entered.append(True)
        assert entered == []
        assert outcome.begin_attempted and outcome.begun
        assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed
    assert visible_state(case, 21) == before
    record_outcome(
        record_property, outcome, work, problem=problem, refusal=code, body_entered=False
    )


@pytest.mark.parametrize("commit", [True, False], ids=["commit", "typed-rollback"])
def test_ddl_and_version_write_are_one_native_transaction(native_case, commit, record_property):
    case = native_case
    before = visible_state(case, 20)
    assert before["rows"]["alembic_version"] == [(LEDGER,)]
    refusal = MigrationRefused("schema_incompatible")
    work, outcome = LedgerWork(), LedgerOutcome()
    if commit:
        with failure_transaction(case.engine, outcome, work=work) as connection:
            raw = connection.connection.driver_connection
            write_successor(connection)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed and raw.closed
        assert_committed_successor(case, before)
    else:
        with (
            pytest.raises(MigrationRefused) as caught,
            failure_transaction(case.engine, outcome, work=work) as connection,
        ):
            raw = connection.connection.driver_connection
            write_successor(connection)
            raise refusal
        assert caught.value is refusal
        assert outcome.confirmed_precommit_rollback and not outcome.cleanup_failed and raw.closed
        assert not outcome.commit_attempted
        assert visible_state(case, 20) == before
    record_outcome(record_property, outcome, work, version_write_attempted=True, committed=commit)


@pytest.mark.parametrize("replacement", ["logical_root", "native_idle", "native_restart"])
def test_replaced_body_or_native_transaction_cannot_publish_ddl(
    native_case, replacement, record_property
):
    case = native_case
    before = visible_state(case, 20)
    work, outcome = LedgerWork(), LedgerOutcome()
    identities = []
    with (
        pytest.raises(MigrationRefused, match="^transactional_connection_required$"),
        failure_transaction(case.engine, outcome, work=work) as connection,
    ):
        raw = connection.connection.driver_connection
        root, proxy = connection.get_transaction(), connection.connection
        assert _require_ledger_body(connection) is work
        write_successor(connection)
        with raw.cursor() as cursor:
            cursor.execute("SELECT pg_current_xact_id()::text")
            identities.append(cursor.fetchone()[0])
        if replacement == "logical_root":
            connection.rollback()
            connection.begin()
            assert connection.get_transaction() is not root
        else:
            raw.rollback()
            assert raw.info.transaction_status is psycopg.pq.TransactionStatus.IDLE
            if replacement == "native_restart":
                with raw.cursor() as cursor:
                    cursor.execute("BEGIN")
                    cursor.execute("SELECT pg_current_xact_id()::text")
                    identities.append(cursor.fetchone()[0])
                assert identities[0] != identities[1]
            assert connection.get_transaction() is root
        assert connection.connection is proxy
        _require_ledger_body(connection)
    assert raw.closed and outcome.confirmed_precommit_rollback
    assert not outcome.commit_attempted and not outcome.cleanup_failed
    assert visible_state(case, 20) == before
    record_outcome(
        record_property, outcome, work, replacement=replacement, transaction_ids=identities
    )


@pytest.mark.parametrize(
    "boundary",
    ["before_commit", "after_commit", "after_rollback", "after_close"],
)
def test_native_visibility_does_not_turn_lost_ack_or_cleanup_into_certainty(
    native_case, monkeypatch, boundary, record_property
):
    case = native_case
    before = visible_state(case, 20)
    work, outcome = LedgerWork(), LedgerOutcome()
    commit, rollback, close = (
        psycopg.Connection.commit,
        psycopg.Connection.rollback,
        Connection.close,
    )
    targets, failures = [], []

    def commit_ack(raw):
        if boundary in {"before_commit", "after_commit"} and targets and raw is targets[0][1]:
            assert failures == []
            failures.append(boundary)
            if boundary == "after_commit":
                commit(raw)
            raise RuntimeError("synthetic-private-commit-ack")
        return commit(raw)

    def rollback_ack(raw):
        if boundary == "after_rollback" and targets and raw is targets[0][1] and not failures:
            rollback(raw)
            failures.append(boundary)
            raise RuntimeError("synthetic-private-rollback-ack")
        return rollback(raw)

    def close_ack(connection):
        result = close(connection)
        if boundary == "after_close" and targets and connection is targets[0][0] and not failures:
            failures.append(boundary)
            raise RuntimeError("synthetic-private-close-ack")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection, "commit", commit_ack)
        patch.setattr(psycopg.Connection, "rollback", rollback_ack)
        patch.setattr(Connection, "close", close_ack)
        with (
            pytest.raises(MigrationRefused, match="^ledger_outcome_uncertain$") as caught,
            failure_transaction(case.engine, outcome, work=work) as connection,
        ):
            raw = connection.connection.driver_connection
            targets.append((connection, raw))
            write_successor(connection)
            if boundary == "after_rollback":
                raise MigrationRefused("schema_incompatible")
    assert failures == [boundary] and raw.closed
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "synthetic-private" not in str(caught.value)
    assert not outcome.confirmed_precommit_rollback
    if boundary == "after_rollback":
        assert not outcome.commit_attempted and not outcome.commit_acknowledged
        assert outcome.rollback_attempted and not outcome.rollback_acknowledged
        assert outcome.cleanup_failed
    elif boundary == "after_close":
        assert outcome.commit_attempted and outcome.commit_acknowledged
        assert not outcome.rollback_attempted and outcome.cleanup_failed
    else:
        assert outcome.commit_attempted and not outcome.commit_acknowledged
    visible_commit = boundary in {"after_commit", "after_close"}
    if visible_commit:
        assert_committed_successor(case, before)
    else:
        assert visible_state(case, 20) == before
    record_outcome(
        record_property, outcome, work, boundary=boundary, native_commit_visible=visible_commit
    )
