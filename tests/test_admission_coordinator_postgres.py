"""Actual PostgreSQL proof for the preparatory SQL-winner coordinator only.

The disposable fixture supplies a separately granted application role. Per-instance
ready observations are synthetic: the real ar6 profile remains migration-only.
No upload, new job, journal durability or full P3 publication proof is claimed.
"""

import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
import test_admission_repository_postgres as repository_pg
import test_migrations_postgres as migrations
from psycopg.pq import TransactionStatus
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from test_admission_coordinator import reconcile, snapshot, submit
from test_admission_repository import aliases, get, submission
from test_admission_schema import JOB, PRINCIPAL, PROJECT
from test_scoped_actions_postgres import observe_actor, wait_blocked

from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_request import parse_submit
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.artifact_storage import ArtifactStorage
from agent_rewind.database import Database
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.publication_journal import PublicationJournal
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
storage_pg = repository_pg.storage_pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL admission coordinator"
)
NEW_KEY = "8" * 64


def coordinator(engine, monkeypatch):
    value = AdmissionCoordinator(engine, RequestAuthority(engine))
    monkeypatch.setattr(
        value, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    return value


@pytest.fixture
def recovery(storage_pg, monkeypatch):
    f = storage_pg
    with f.engine.begin() as connection:
        role = f.pg["app_role"]  # Only the disposable fixture-generated role.
        connection.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
        for table in ("projects", "organizations", "jobs", "api_keys"):
            connection.exec_driver_sql(f"GRANT UPDATE(id) ON {table} TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(principal_id) ON project_memberships TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(resource_id) ON resource_scopes TO {role}")
        connection.exec_driver_sql(f"GRANT INSERT ON operation_keys TO {role}")

    def forbidden(*args, **kwargs):
        pytest.fail("SQL recovery invoked a new-work dependency")

    for source, method in (
        (NativeRegistry, "resolve_new"),
        (ArtifactStorage, "put_verified"),
        (PublicationJournal, "open"),
        (Database, "enqueue"),
    ):
        monkeypatch.setattr(source, method, forbidden)
    f.service = coordinator(f.pg["app"], monkeypatch)
    return f


def as_service_key(f):
    key = "e" * 32
    principal = VerifiedPrincipal.service_key(key)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO api_keys VALUES(:id,:hash,'operator','fixture',:expiry,false)"),
            {"id": key, "hash": "d" * 64, "expiry": 253402300799.0},
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"),
            {"id": key, "p": PROJECT},
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": principal.principal_id},
        )
        connection.execute(
            text("UPDATE jobs SET actor=:actor WHERE id=:id"),
            {"actor": principal.principal_id, "id": JOB},
        )
    f.principal = principal
    f.context = f.authority.named(principal, PROJECT).context
    return key


def safe_failure(caught, code):
    assert str(caught.value) == code
    assert caught.value.code == code
    assert caught.value.__suppress_context__
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


def test_postgres_real_schema_guard_precedes_operation_access(recovery):
    f = recovery
    service = AdmissionCoordinator(f.pg["app"], RequestAuthority(f.pg["app"]))
    selected = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        selected.append(statement.lower())

    event.listen(f.pg["app"], "before_cursor_execute", observe)
    try:
        with pytest.raises(AdmissionError, match="^schema_incompatible$"):
            submit(service, f)
    finally:
        event.remove(f.pg["app"], "before_cursor_execute", observe)
    assert not any("from operations " in sql or "from operation_keys " in sql for sql in selected)


def test_postgres_sql_winner_and_alias_need_only_declared_privileges(recovery):
    f = recovery
    original = repository_pg.persist(f)
    before = snapshot(f)
    with f.pg["app"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT has_schema_privilege(current_user,'public','CREATE'),"
                "has_table_privilege(current_user,'jobs','INSERT'),"
                "has_column_privilege(current_user,'jobs','reserved','UPDATE'),"
                "has_table_privilege(current_user,'operations','INSERT'),"
                "has_table_privilege(current_user,'audit','INSERT'),"
                "has_table_privilege(current_user,'artifact_objects','INSERT')"
            ).one()
            == (False,) * 6
        )
    assert submit(f.service, f) == original.accepted_response
    assert reconcile(f.service, f) == original.accepted_response
    assert snapshot(f) == before
    assert submit(f.service, f, key_hash=NEW_KEY) == original.accepted_response
    assert reconcile(f.service, f, key_hash=NEW_KEY) == original.accepted_response
    after = snapshot(f)
    assert len(after.pop("operation_keys")) == len(before.pop("operation_keys")) + 1
    assert after == before
    with f.engine.connect() as connection:
        assert get(f, connection) == original
        assert original.failure_correlation_id == "6" * 32
        assert original.execution_config_digest == f.value.configuration.digest


@pytest.mark.parametrize("entry", ["submit", "reconcile"])
def test_postgres_absent_identity_has_no_new_work_or_mutations(recovery, entry):
    f = recovery
    before = snapshot(f)
    code = "dependency_unavailable" if entry == "submit" else "outcome_uncertain"
    with pytest.raises(AdmissionError) as caught:
        (submit if entry == "submit" else reconcile)(f.service, f)
    safe_failure(caught, code)
    assert snapshot(f) == before


@pytest.mark.parametrize("change", ["body", "client"])
def test_postgres_both_identity_conflicts_precede_alias_work(recovery, change):
    f = recovery
    repository_pg.persist(f)
    before = snapshot(f)
    raw = submission()
    if change == "body":
        raw["seed"] += 1
    else:
        raw["client_operation_id"] = "b" * 32
    with pytest.raises(AdmissionError, match="^idempotency_conflict$"):
        submit(f.service, f, intent=parse_submit(canonical(raw)))
    assert snapshot(f) == before


def test_postgres_eight_concurrent_missing_aliases_have_one_atomic_winner(recovery):
    f = recovery
    original = repository_pg.persist(f)
    before = snapshot(f)
    barrier = Barrier(8)

    def contender():
        barrier.wait(timeout=10)
        return submit(f.service, f, key_hash=NEW_KEY)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(contender) for _ in range(8)]
        results = [future.result(timeout=30) for future in futures]
    assert results == [original.accepted_response] * 8
    after = snapshot(f)
    assert len(after.pop("operation_keys")) == len(before.pop("operation_keys")) + 1
    assert after == before
    assert reconcile(f.service, f, key_hash=NEW_KEY) == original.accepted_response


@pytest.mark.parametrize("change", ["member_revoke", "member_role", "key_revoke", "key_expiry"])
def test_postgres_lock_wait_rechecks_creator_before_alias(recovery, change):
    f = recovery
    key = as_service_key(f) if change.startswith("key_") else None
    repository_pg.persist(f)
    before = snapshot(f)
    ready, pids, listener = observe_actor(f.pg["app"])
    statements = {
        "member_revoke": (
            "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
            "WHERE project_id=:p AND principal_id=:id"
        ),
        "member_role": (
            "UPDATE project_memberships SET role='viewer' WHERE project_id=:p AND principal_id=:id"
        ),
        "key_revoke": "UPDATE api_keys SET revoked=true WHERE id=:key",
        "key_expiry": "UPDATE api_keys SET expires=1 WHERE id=:key",
    }
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with f.engine.connect() as writer:
                blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                writer.exec_driver_sql("SET LOCAL statement_timeout='8s'")
                writer.execute(
                    text(statements[change]),
                    {"p": PROJECT, "id": f.principal.principal_id, "key": key},
                )
                future = pool.submit(submit, f.service, f, key_hash=NEW_KEY)
                try:
                    assert ready.wait(5)
                    assert pids[0] != blocker
                    wait_blocked(f.pg, pids[0], blocker)
                    writer.commit()
                finally:
                    writer.rollback()
            with pytest.raises(ActionForbidden if change == "member_role" else ResourceNotFound):
                future.result(timeout=10)
    finally:
        event.remove(f.pg["app"], "checkout", listener)
    assert snapshot(f) == before


@pytest.mark.parametrize("change", ["member", "key", "viewer"])
def test_postgres_committed_alias_is_not_disclosed_after_fresh_revocation(
    recovery, monkeypatch, change
):
    f = recovery
    key = as_service_key(f) if change == "key" else None
    repository_pg.persist(f)
    disclose = f.service._disclose
    committed = False

    def revoke(*args, **kwargs):
        nonlocal committed
        # Independent owner update succeeds only after the first transaction
        # has released the held caller rows. No arbitrary synchronization sleep.
        with f.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout='500ms'")
            assert (
                connection.execute(
                    text("SELECT count(*) FROM operation_keys WHERE key_hash=:key"),
                    {"key": NEW_KEY},
                ).scalar_one()
                == 1
            )
            if key is not None:
                connection.execute(
                    text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key}
                )
            else:
                statement = (
                    "UPDATE project_memberships SET role='viewer' "
                    if change == "viewer"
                    else "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
                )
                connection.execute(
                    text(statement + "WHERE project_id=:p AND principal_id=:id"),
                    {"p": PROJECT, "id": f.principal.principal_id},
                )
        committed = True
        return disclose(*args, **kwargs)

    monkeypatch.setattr(f.service, "_disclose", revoke)
    with pytest.raises(ActionForbidden if change == "viewer" else ResourceNotFound):
        submit(f.service, f, key_hash=NEW_KEY)
    assert committed
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


def test_postgres_viewer_status_does_not_grant_creator_recovery_or_foreign_context(recovery):
    f = recovery
    original = repository_pg.persist(f)
    with f.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE project_memberships SET role='viewer' "
                "WHERE project_id=:p AND principal_id=:id"
            ),
            {"p": PROJECT, "id": PRINCIPAL},
        )
    with f.engine.connect() as connection:
        assert get(f, connection) == original
    before = snapshot(f)
    with pytest.raises(ActionForbidden):
        submit(f.service, f, key_hash=NEW_KEY)
    with pytest.raises(ResourceNotFound):
        submit(f.service, f, original_context=replace(f.context, project_id="0" * 32))
    assert snapshot(f) == before


def test_postgres_original_named_context_survives_changed_default(recovery):
    f = recovery
    original = repository_pg.persist(f)
    with f.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE project_memberships SET legacy_default=true "
                "WHERE project_id=:p AND principal_id=:id"
            ),
            {"p": PROJECT, "id": PRINCIPAL},
        )
    assert f.service.authority.legacy(f.principal).context.project_id == PROJECT
    with f.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,'Other',created_at FROM projects WHERE id=:p"
            ),
            {"other": "7" * 32, "p": PROJECT},
        )
        connection.execute(
            text(
                "UPDATE project_memberships SET legacy_default=false "
                "WHERE project_id=:p AND principal_id=:id"
            ),
            {"p": PROJECT, "id": PRINCIPAL},
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,true)"),
            {"p": "7" * 32, "id": PRINCIPAL},
        )
    assert f.service.authority.legacy(f.principal).context.project_id == "7" * 32
    assert submit(f.service, f) == original.accepted_response


def test_postgres_postcommit_disclosure_privilege_loss_is_uncertain(recovery, monkeypatch):
    f = recovery
    repository_pg.persist(f)
    disclose = f.service._disclose
    codes = []

    def revoke(*args, **kwargs):
        with f.engine.begin() as connection:
            connection.exec_driver_sql(f"REVOKE SELECT ON operations FROM {f.pg['app_role']}")
        return disclose(*args, **kwargs)

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    monkeypatch.setattr(f.service, "_disclose", revoke)
    event.listen(f.pg["app"], "handle_error", observed)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f.service, f, key_hash=NEW_KEY)
    finally:
        event.remove(f.pg["app"], "handle_error", observed)
    safe_failure(caught, "outcome_uncertain")
    assert codes == ["42501"]
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


def test_postgres_real_alias_permission_failure_rolls_back_and_is_not_conflict(recovery):
    f = recovery
    original = repository_pg.persist(f)
    before = snapshot(f)
    with f.engine.begin() as connection:
        connection.exec_driver_sql(f"REVOKE INSERT ON operation_keys FROM {f.pg['app_role']}")
    codes = []

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    event.listen(f.pg["app"], "handle_error", observed)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f.service, f, key_hash=NEW_KEY)
    finally:
        event.remove(f.pg["app"], "handle_error", observed)
    safe_failure(caught, "dependency_unavailable")
    assert codes == ["42501"]
    assert snapshot(f) == before
    with f.engine.begin() as connection:
        connection.exec_driver_sql(f"GRANT INSERT ON operation_keys TO {f.pg['app_role']}")
    assert submit(f.service, f, key_hash=NEW_KEY) == original.accepted_response


@pytest.fixture
def pooled(recovery, monkeypatch):
    f = recovery
    engine = create_engine(
        f.pg["app"].url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"options": "-c statement_timeout=7000 -c lock_timeout=900"},
    )
    f.service = coordinator(engine, monkeypatch)
    try:
        yield f, engine
    finally:
        engine.dispose()


def clean_pool(engine, *, discarded=None):
    assert engine.pool.checkedout() == 0
    if discarded is not None:
        assert discarded.closed
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        assert raw.info.transaction_status == TransactionStatus.IDLE
        assert raw.autocommit is False
        if discarded is not None:
            assert raw is not discarded
        assert connection.exec_driver_sql(
            "SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),"
            "current_setting('transaction_read_only'),current_setting('transaction_isolation')"
        ).one() == ("7s", "900ms", "off", "read committed")
    assert raw.info.transaction_status == TransactionStatus.IDLE
    assert engine.pool.checkedout() == 0
    return raw


@pytest.mark.parametrize("after_commit", [False, True])
def test_postgres_commit_ack_fault_requires_original_identity_recovery(
    pooled, monkeypatch, after_commit
):
    f, engine = pooled
    original = repository_pg.persist(f)
    before = snapshot(f)
    commit = Connection.commit
    once = True

    def fail(connection):
        nonlocal once
        if connection.engine is engine and once:
            once = False
            if after_commit:
                commit(connection)
            raise RuntimeError("PRIVATE-ACK")
        return commit(connection)

    monkeypatch.setattr(Connection, "commit", fail)
    with pytest.raises(AdmissionError) as caught:
        submit(f.service, f, key_hash=NEW_KEY)
    safe_failure(caught, "outcome_uncertain")
    after = snapshot(f)
    assert len(after.pop("operation_keys")) == len(before.pop("operation_keys")) + int(after_commit)
    assert after == before
    clean_pool(engine)
    assert reconcile(f.service, f, key_hash=NEW_KEY) == original.accepted_response
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2
    clean_pool(engine)


@pytest.mark.parametrize("fault", ["rollback", "close"])
def test_postgres_cleanup_fault_discards_physical_connection_and_preserves_uncertainty(
    pooled, monkeypatch, fault
):
    f, engine = pooled
    original = repository_pg.persist(f)
    raw = clean_pool(engine)
    method = getattr(Connection, fault)
    once = True

    def fail(connection):
        nonlocal once
        if connection.engine is engine and once:
            once = False
            raise RuntimeError("PRIVATE-CLEANUP")
        return method(connection)

    monkeypatch.setattr(Connection, fault, fail)
    if fault == "rollback":
        bind = f.service.repository.bind_alias

        def abort(*args, **kwargs):
            bind(*args, **kwargs)
            raise RuntimeError("PRIVATE-PRECOMMIT")

        monkeypatch.setattr(f.service.repository, "bind_alias", abort)
    with pytest.raises(AdmissionError) as caught:
        submit(f.service, f, key_hash=NEW_KEY)
    safe_failure(caught, "outcome_uncertain")
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == (
            1 if fault == "rollback" else 2
        )
    clean_pool(engine, discarded=raw)
    if fault == "rollback":
        monkeypatch.setattr(f.service.repository, "bind_alias", bind)
    assert reconcile(f.service, f, key_hash=NEW_KEY) == original.accepted_response
    clean_pool(engine)


@pytest.mark.parametrize("mode", ["engine_autocommit", "driver_autocommit", "dirty"])
def test_postgres_unsupported_native_mode_refuses_before_body(pooled, mode):
    _, engine = pooled
    raw = clean_pool(engine)
    selected = engine
    if mode == "engine_autocommit":
        selected = engine.execution_options(isolation_level="AUTOCOMMIT")
    elif mode == "driver_autocommit":
        raw.autocommit = True
    else:
        raw.execute("SELECT 1")
        assert raw.info.transaction_status == TransactionStatus.INTRANS
    outcome = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(selected, outcome),
    ):
        pytest.fail("Unsupported native mode reached transaction body")
    assert not outcome.begun and not outcome.commit_attempted
    clean_pool(engine, discarded=raw)


def test_postgres_transaction_read_committed_native_timeout_and_reuse(pooled):
    f, engine = pooled
    repository_pg.persist(f)
    state = TransactionOutcome()
    with admission_transaction(engine, state) as connection:
        assert connection.exec_driver_sql("SHOW transaction_isolation").scalar_one() == (
            "read committed"
        )
        assert connection.exec_driver_sql("SHOW lock_timeout").scalar_one() == "3s"
        assert connection.exec_driver_sql("SHOW statement_timeout").scalar_one() == "5s"
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 1
        with f.engine.begin() as writer:
            aliases(f, writer, key_hash=NEW_KEY)
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2
    assert state.commit_acknowledged and not state.confirmed_precommit_rollback
    clean_pool(engine)
    codes = []

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    event.listen(engine, "handle_error", observed)
    state = TransactionOutcome()
    try:
        with (
            pytest.raises(AdmissionError) as caught,
            admission_transaction(engine, state) as connection,
        ):
            connection.exec_driver_sql("SET LOCAL statement_timeout='50ms'")
            # A bounded native timeout target, not a synchronization delay.
            connection.exec_driver_sql("SELECT pg_sleep(1)")
    finally:
        event.remove(engine, "handle_error", observed)
    safe_failure(caught, "dependency_unavailable")
    assert codes == ["57014"]
    assert state.confirmed_precommit_rollback and not state.commit_attempted
    clean_pool(engine)
