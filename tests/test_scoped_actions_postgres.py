"""Actual PostgreSQL mutation, exclusion and rollback evidence; opt-in only.

The synthetic application role gets only the DML/row-lock privileges required
here, no DDL or original record/event writes. Separate owner transactions model
administrative updates that do not cooperate with the project lock: existing
grant/target row locks must still serialize them. No production role is changed.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import event, insert, select, text
from sqlalchemy.exc import OperationalError
from test_scoped_actions import HUMAN, snapshot
from test_scoped_repositories import (
    ALICE,
    CA,
    JOB_A,
    JOB_B,
    RUN_A,
    RUN_B,
    A,
    B,
    add_key,
)
from test_scoped_repositories_postgres import prepare as prepare_scoped

from agent_rewind.database import audit, jobs, keys
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_actions import ScopedActionError, ScopedActions
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")


@pytest.fixture
def actions(pg):
    prepare_scoped(pg)
    with pg["owner"].begin() as connection:
        role = pg["app_role"]  # Fixture-generated identifier, never a request value.
        for table in ("projects", "organizations", "records"):
            connection.exec_driver_sql(f"GRANT UPDATE(id) ON {table} TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(cancel,status) ON jobs TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(revoked) ON api_keys TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(revoked_at) ON project_memberships TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(resource_id) ON resource_scopes TO {role}")
        connection.exec_driver_sql(
            f"GRANT INSERT ON api_keys,resource_scopes,project_memberships,audit TO {role}"
        )
    return ScopedActions(pg["app"], RequestAuthority(pg["app"]))


def key_caller(pg):
    context = add_key(pg["owner"], key_role="operator", member_role="maintainer")
    return VerifiedPrincipal.service_key(RUN_A), context


def target_key(pg, *, foreign=False):
    key_id = RUN_B if foreign else RUN_A
    project = B if foreign else A
    with pg["owner"].begin() as connection:
        connection.execute(
            insert(keys).values(
                id=key_id,
                hash=key_id * 2,
                role="operator",
                name="synthetic",
                expires=253402300799.0,
                revoked=False,
            )
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:project)"),
            {"id": key_id, "project": project},
        )
    return key_id


def wait_blocked(pg, blocked, blocker):
    deadline = time.monotonic() + 2
    with pg["control"].connect() as connection:
        while time.monotonic() < deadline:
            if connection.execute(
                text("SELECT :blocker = ANY(pg_blocking_pids(:blocked))"),
                {"blocked": blocked, "blocker": blocker},
            ).scalar_one():
                return
            time.sleep(0.01)  # Poll an observed lock condition; never assume a sleep is proof.
    pytest.fail("Expected PostgreSQL lock dependency was not observed")


def observe_actor(engine):
    ready, pids = Event(), []

    def checkout(raw, record, proxy):
        pids.append(raw.info.backend_pid)
        ready.set()

    event.listen(engine, "checkout", checkout)
    return ready, pids, checkout


def deny_sql(kind):
    if kind == "member_role":
        return (
            "UPDATE project_memberships SET role='viewer' WHERE project_id=:p AND principal_id=:id"
        )
    if kind in {"member_revoke", "key_member"}:
        return (
            "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
            "WHERE project_id=:p AND principal_id=:id"
        )
    if kind == "key_revoke":
        return "UPDATE api_keys SET revoked=true WHERE id=:key"
    if kind == "key_expiry":
        return "UPDATE api_keys SET expires=1 WHERE id=:key"
    if kind == "key_scope":
        return (
            "UPDATE resource_scopes SET project_id=:other "
            "WHERE resource_kind='key' AND resource_id=:key"
        )
    return (
        "UPDATE resource_scopes SET project_id=:other "
        "WHERE resource_kind='job' AND resource_id=:job"
    )


def denial(kind):
    return ActionForbidden if kind == "member_role" else ResourceNotFound


def test_postgres_actions_need_only_declared_dml_and_preserve_other_sources(pg, actions):
    with pg["app"].connect() as connection:
        assert connection.execute(
            text(
                "SELECT has_schema_privilege(current_user,'public','CREATE'),"
                "has_table_privilege(current_user,'records','INSERT'),"
                "has_table_privilege(current_user,'events','UPDATE'),"
                "has_column_privilege(current_user,'jobs','reserved','UPDATE'),"
                "has_column_privilege(current_user,'records','data','UPDATE')"
            )
        ).one() == (False, False, False, False, False)
    issued = actions.issue_key(HUMAN, CA, "viewer", "synthetic", 30)
    assert (
        actions.authority.legacy(VerifiedPrincipal.service_key(issued.id)).context.project_id == A
    )
    actions.cancel(HUMAN, CA, JOB_A)
    actions.record_run_read(HUMAN, CA, RUN_A)
    actions.revoke_key(HUMAN, CA, issued.id)
    with pytest.raises(ResourceNotFound):
        actions.authority.legacy(VerifiedPrincipal.service_key(issued.id))
    with pg["owner"].connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT revoked_at IS NOT NULL FROM project_memberships WHERE principal_id=:id"
                ),
                {"id": "api-key:" + issued.id},
            ).scalar_one()
            is True
        )
        assert connection.execute(
            select(jobs.c.status, jobs.c.reserved).where(jobs.c.id == JOB_A)
        ).one() == ("failed", 3)
        assert connection.execute(
            select(audit.c.actor, audit.c.action).order_by(audit.c.created)
        ).all() == [
            (ALICE, "key.create"),
            (ALICE, "job.cancel"),
            (ALICE, "run.read"),
            (ALICE, "key.revoke"),
        ]


@pytest.mark.parametrize("service_key", [False, True])
def test_postgres_action_denial_does_not_disclose_known_foreign_key_or_job(
    pg, actions, service_key
):
    target_key(pg, foreign=True)
    if service_key:
        principal, context = key_caller(pg)
        with pg["owner"].begin() as connection:
            connection.execute(
                text("UPDATE api_keys SET role='viewer' WHERE id=:id"), {"id": RUN_A}
            )
    else:
        principal, context = HUMAN, CA
        target_key(pg)
        with pg["owner"].begin() as connection:
            connection.execute(
                text("UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"),
                {"id": ALICE},
            )
    before = snapshot(pg["owner"])
    for method, known, foreign in [
        (actions.cancel, JOB_A, JOB_B),
        (actions.revoke_key, RUN_A, RUN_B),
    ]:
        with pytest.raises(ActionForbidden):
            method(principal, context, known)
        for resource_id in (foreign, "0" * 32):
            with pytest.raises(ResourceNotFound):
                method(principal, context, resource_id)
    assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize(
    "operation,kind",
    [
        ("cancel", kind)
        for kind in (
            "member_role",
            "member_revoke",
            "key_member",
            "key_revoke",
            "key_expiry",
            "key_scope",
            "target_scope",
        )
    ]
    + [("read", "member_revoke"), ("read", "key_revoke")],
)
def test_postgres_prior_uncommitted_revocation_wins_before_effect(pg, actions, operation, kind):
    principal, context = key_caller(pg) if kind.startswith("key_") else (HUMAN, CA)
    action = actions.cancel if operation == "cancel" else actions.record_run_read
    target = JOB_A if operation == "cancel" else RUN_A
    ready, pids, listener = observe_actor(pg["app"])
    try:
        with pg["owner"].connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
            blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            writer.execute(
                text(deny_sql(kind)),
                {"p": A, "id": principal.principal_id, "key": RUN_A, "job": JOB_A, "other": B},
            )
            future = pool.submit(action, principal, context, target)
            try:
                assert ready.wait(3)
                wait_blocked(pg, pids[0], blocker)
                writer.commit()
                with pytest.raises(denial(kind)):
                    future.result(timeout=8)
            finally:
                writer.rollback()
    finally:
        event.remove(pg["app"], "checkout", listener)
    with pg["owner"].connect() as connection:
        assert (
            connection.execute(select(jobs.c.cancel).where(jobs.c.id == JOB_A)).scalar_one()
            is False
        )
        assert connection.execute(select(audit.c.id)).all() == []


@pytest.mark.parametrize(
    "operation,kind",
    [("cancel", kind) for kind in ("member_role", "member_revoke", "key_member", "key_revoke")]
    + [("read", "member_revoke"), ("read", "key_revoke")],
)
def test_postgres_existing_grant_locks_hold_through_action_commit(
    pg, actions, monkeypatch, operation, kind
):
    principal, context = key_caller(pg) if kind.startswith("key_") else (HUMAN, CA)
    execute = actions.cancel if operation == "cancel" else actions.record_run_read
    target = JOB_A if operation == "cancel" else RUN_A
    effect, release, revoker_started = Event(), Event(), Event()
    actor_pid, revoker_pid = [], []
    audit_write = actions._audit

    def paused_audit(connection, *args):
        audit_write(connection, *args)
        actor_pid.append(connection.connection.driver_connection.info.backend_pid)
        effect.set()
        assert release.wait(8), "Timed out awaiting observed grant-lock test"

    def revoke():
        with pg["owner"].begin() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
            revoker_pid.append(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
            revoker_started.set()
            connection.execute(
                text(deny_sql(kind)),
                {"p": A, "id": principal.principal_id, "key": RUN_A},
            )

    monkeypatch.setattr(actions, "_audit", paused_audit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(execute, principal, context, target)
        try:
            if not effect.wait(5):
                action.result(timeout=1)
                pytest.fail("Action did not reach the held audit boundary")
            revoker = pool.submit(revoke)
            assert revoker_started.wait(3)
            wait_blocked(pg, revoker_pid[0], actor_pid[0])
        finally:
            release.set()
        assert action.result(timeout=8) is None
        assert revoker.result(timeout=8) is None
    monkeypatch.setattr(actions, "_audit", audit_write)
    with pytest.raises(denial(kind)):
        execute(principal, context, target)
    with pg["owner"].connect() as connection:
        assert connection.execute(select(jobs.c.cancel).where(jobs.c.id == JOB_A)).scalar_one() is (
            operation == "cancel"
        )
        expected_action = "job.cancel" if operation == "cancel" else "run.read"
        assert connection.execute(select(audit.c.action, audit.c.target)).all() == [
            (expected_action, target)
        ]


def test_postgres_default_switch_while_waiting_cannot_retarget_effect(pg, actions):
    decision = actions.authority.legacy(HUMAN)
    ready, pids, listener = observe_actor(pg["app"])
    try:
        with pg["owner"].connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
            blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            writer.execute(text("SELECT id FROM projects WHERE id=:p FOR UPDATE"), {"p": A})
            writer.execute(
                text("UPDATE project_memberships SET legacy_default=false WHERE principal_id=:id"),
                {"id": ALICE},
            )
            writer.execute(
                text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,true)"),
                {"p": B, "id": ALICE},
            )
            future = pool.submit(actions.cancel, HUMAN, decision.context, JOB_A)
            try:
                assert ready.wait(3)
                wait_blocked(pg, pids[0], blocker)
                writer.commit()
                assert future.result(timeout=8) is None
            finally:
                writer.rollback()
    finally:
        event.remove(pg["app"], "checkout", listener)
    assert actions.authority.legacy(HUMAN).context.project_id == B
    with pg["owner"].connect() as connection:
        assert (
            connection.execute(select(jobs.c.cancel).where(jobs.c.id == JOB_A)).scalar_one() is True
        )
        assert (
            connection.execute(select(jobs.c.cancel).where(jobs.c.id == JOB_B)).scalar_one()
            is False
        )
        assert connection.execute(select(audit.c.target)).all() == [(JOB_A,)]


def test_postgres_worker_terminal_commit_while_cancel_waits_preserves_result_and_holds(pg, actions):
    with pg["owner"].begin() as connection:
        connection.execute(
            text(
                "UPDATE jobs SET status='running',owner='worker',lease_until=9999999999 "
                "WHERE id=:id"
            ),
            {"id": JOB_A},
        )
    ready, pids, listener = observe_actor(pg["app"])
    try:
        with pg["owner"].connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
            blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            writer.execute(
                text("UPDATE jobs SET status='succeeded',result=:result WHERE id=:id"),
                {"id": JOB_A, "result": "e" * 64},
            )
            future = pool.submit(actions.cancel, HUMAN, CA, JOB_A)
            try:
                assert ready.wait(3)
                wait_blocked(pg, pids[0], blocker)
                writer.commit()
                assert future.result(timeout=8) is None
            finally:
                writer.rollback()
    finally:
        event.remove(pg["app"], "checkout", listener)
    with pg["owner"].connect() as connection:
        assert connection.execute(
            select(
                jobs.c.status,
                jobs.c.result,
                jobs.c.owner,
                jobs.c.lease_until,
                jobs.c.budget,
                jobs.c.reserved,
                jobs.c.cancel,
            ).where(jobs.c.id == JOB_A)
        ).one() == ("succeeded", "e" * 64, "worker", 9999999999.0, 10, 3, True)


@pytest.mark.parametrize("stage", ["api_keys", "resource_scopes", "project_memberships", "audit"])
def test_postgres_real_permission_failure_rolls_back_key_scope_membership_audit(pg, actions, stage):
    before = snapshot(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(f"REVOKE INSERT ON {stage} FROM {pg['app_role']}")
    with pytest.raises(ScopedActionError, match="^action_unavailable$"):
        actions.issue_key(HUMAN, CA, "operator", "synthetic", 30)
    assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize("operation", ["cancel", "revoke", "read"])
def test_postgres_audit_permission_failure_rolls_back_effect(pg, actions, operation):
    target_key(pg)
    before = snapshot(pg["owner"])
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(f"REVOKE INSERT ON audit FROM {pg['app_role']}")
    with pytest.raises(ScopedActionError, match="^action_unavailable$"):
        if operation == "cancel":
            actions.cancel(HUMAN, CA, JOB_A)
        elif operation == "read":
            actions.record_run_read(HUMAN, CA, RUN_A)
        else:
            actions.revoke_key(HUMAN, CA, RUN_A)
    assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize("committed", [False, True])
def test_postgres_failed_commit_acknowledgment_withholds_secret_without_retry(
    pg, actions, monkeypatch, committed
):
    before = snapshot(pg["owner"])
    original = pg["app"].dialect.do_commit
    attempts = []

    def failure(raw):
        attempts.append(1)
        if committed:
            original(raw)
        raise OperationalError("private-commit-canary", {}, RuntimeError("private-commit-canary"))

    with monkeypatch.context() as patch:
        patch.setattr(pg["app"].dialect, "do_commit", failure)
        with pytest.raises(ScopedActionError, match="^outcome_uncertain$"):
            actions.issue_key(HUMAN, CA, "viewer", "synthetic", 30)
    assert attempts == [1]
    if committed:
        current = snapshot(pg["owner"])
        assert len(current["api_keys"]) == len(before["api_keys"]) + 1
        assert len(current["audit"]) == len(before["audit"]) + 1
    else:
        assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize("mode", ["engine", "pooled_dbapi"])
def test_postgres_effective_autocommit_refuses_before_mutation(pg, actions, mode):
    before = snapshot(pg["owner"])
    used = []
    if mode == "engine":
        engine = pg["app"].execution_options(isolation_level="AUTOCOMMIT")
        actions = ScopedActions(engine, RequestAuthority(engine))
        listener = None
    else:

        def listener(raw, record, proxy):
            used.append(raw)
            raw.autocommit = True

        event.listen(pg["app"], "checkout", listener)
    try:
        with pytest.raises(ScopedActionError, match="^action_unavailable$"):
            actions.cancel(HUMAN, CA, JOB_A)
    finally:
        if listener is not None:
            event.remove(pg["app"], "checkout", listener)
    assert all(raw.closed for raw in used)
    assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize("changed", ["job_scope", "run_identity"])
def test_postgres_run_read_audit_keeps_validated_closure_locked_until_commit(
    pg, actions, monkeypatch, changed
):
    audited, release, writer_started = Event(), Event(), Event()
    actor_pid, writer_pid = [], []
    original = actions._audit

    def paused(connection, *args):
        original(connection, *args)
        actor_pid.append(connection.connection.driver_connection.info.backend_pid)
        audited.set()
        assert release.wait(8), "Timed out awaiting closure-lock observation"

    def mutate():
        with pg["owner"].begin() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
            writer_pid.append(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
            writer_started.set()
            if changed == "job_scope":
                connection.execute(
                    text(
                        "UPDATE resource_scopes SET project_id=:p "
                        "WHERE resource_kind='job' AND resource_id=:id"
                    ),
                    {"p": B, "id": JOB_A},
                )
            else:
                connection.execute(
                    text("UPDATE records SET data=CAST(:body AS json) WHERE id=:id"),
                    {"body": '{"job_id":"' + JOB_B + '","parent_id":null}', "id": RUN_A},
                )

    monkeypatch.setattr(actions, "_audit", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(actions.record_run_read, HUMAN, CA, RUN_A)
        try:
            if not audited.wait(5):
                reader.result(timeout=1)
                pytest.fail("Read audit did not reach the held transaction")
            writer = pool.submit(mutate)
            assert writer_started.wait(3)
            wait_blocked(pg, writer_pid[0], actor_pid[0])
        finally:
            release.set()
        assert reader.result(timeout=8) is None
        assert writer.result(timeout=8) is None
    monkeypatch.setattr(actions, "_audit", original)
    with pytest.raises(ResourceNotFound):
        actions.record_run_read(HUMAN, CA, RUN_A)
    with pg["owner"].connect() as connection:
        assert connection.execute(select(audit.c.action, audit.c.target)).all() == [
            ("run.read", RUN_A)
        ]
