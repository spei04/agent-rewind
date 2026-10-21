"""Actual PostgreSQL cancellation service proof; synthetic instance and narrow grants only.

The owner models independent authority/worker writers. Every race observes a
real lock dependency or a completed service phase; no elapsed sleep is proof.
No HTTP, worker failure-envelope or production readiness claim is made here.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_admission_coordinator import snapshot
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT
from test_admission_schema import job as seed_job
from test_artifact_metadata import OTHER
from test_artifact_postgres import prepare_postgres
from test_operation_service import key_context
from test_operation_service_postgres import get_pg
from test_operation_sources import result_ref, roots
from test_operation_sources_postgres import source_pg, storage_pg
from test_run_projection_postgres import drain
from test_scoped_actions_postgres import wait_blocked

from agent_rewind import operation_service
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.errors import Fault
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import load_release_profile
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.operation_service import OperationService
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import ProjectContext

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL cancellation service"
)
__all__ = ["pg", "storage_pg", "source_pg", "get_pg"]


@pytest.fixture
def cancel_pg(get_pg):
    f = get_pg
    with f.engine.begin() as connection:
        role = f.pg["app_role"]  # Generated synthetic identifier, never request input.
        for table in ("projects", "organizations"):
            connection.exec_driver_sql(f"GRANT UPDATE(id) ON {table} TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(cancel,status) ON jobs TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(revoked) ON api_keys TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(revoked_at) ON project_memberships TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(resource_id) ON resource_scopes TO {role}")
        connection.exec_driver_sql(f"GRANT UPDATE(kind) ON operations TO {role}")
        connection.exec_driver_sql(f"GRANT INSERT ON audit TO {role}")

    def forbidden_loader(_descriptor):
        pytest.fail("Cancellation must never load a result or configuration artifact")

    f.service.artifact_loader = forbidden_loader
    return f


def invoke(f, *, principal=None, context=None, operation_id=OPERATION):
    return f.service.cancel_operation(principal or f.principal, context or f.context, operation_id)


def fault(call, code="dependency_unavailable"):
    with pytest.raises(Fault, match=f"^{code}$") as caught:
        call()
    assert caught.value.__suppress_context__ is True
    assert caught.value.__cause__ is None
    return caught.value


def state(f):
    with f.engine.connect() as connection:
        row = dict(
            connection.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": JOB})
            .mappings()
            .one()
        )
        audits = connection.execute(text("SELECT actor,action,target FROM audit ORDER BY id")).all()
    return row, audits


def expected(status):
    return {
        "operation_id": OPERATION,
        "cancel_requested": True,
        "status": "cancelled" if status == "queued" else status,
    }


def released(f):
    assert all(connection.closed for connection in f.connections)
    assert all(work._started is None for work in f.work)


def before_disclosure(f, monkeypatch, action):
    original = f.service._cancel_disclose

    def disclose(*args, **kwargs):
        # Mutation committed and released its Connection before this callback.
        assert all(connection.closed for connection in f.connections)
        action()
        return original(*args, **kwargs)

    monkeypatch.setattr(f.service, "_cancel_disclose", disclose)


def grant_change(f, kind, principal):
    with f.engine.begin() as connection:
        if kind == "role":
            connection.execute(
                text("UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"),
                {"id": principal.principal_id},
            )
        elif kind == "member":
            connection.execute(
                text("UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"),
                {"id": principal.principal_id},
            )
        elif kind == "key_role":
            connection.execute(
                text("UPDATE api_keys SET role='viewer' WHERE id=:id"), {"id": "d" * 32}
            )
        elif kind == "key_expiry":
            connection.execute(text("UPDATE api_keys SET expires=1 WHERE id=:id"), {"id": "d" * 32})
        else:
            connection.execute(
                text("UPDATE api_keys SET revoked=TRUE WHERE id=:id"), {"id": "d" * 32}
            )


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed", "cancelled"])
@pytest.mark.parametrize("key", [False, True])
def test_postgres_exact_response_all_statuses_and_narrow_effect(cancel_pg, status, key):
    f = cancel_pg
    principal, context = key_context(f, role="operator") if key else (f.principal, f.context)
    with f.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE jobs SET status=:status,reserved=:reserved,error=:error,"
                "owner='preserved-worker',lease_until=1900000000 WHERE id=:id"
            ),
            {"status": status, "reserved": 2**53 + 1, "error": "legacy bounded error", "id": JOB},
        )
    original, _ = state(f)
    assert invoke(f, principal=principal, context=context) == expected(status)
    after, audits = state(f)
    assert after == {**original, "cancel": True, "status": expected(status)["status"]}
    assert audits == [(principal.principal_id, "job.cancel", JOB)]
    assert len(f.work) == 1 and f.work[0].statements <= 512
    released(f)
    print(
        f"CANCEL PG status={status} key={key} attempts={f.work[0].statements} "
        f"seconds={f.work[0].seconds:.6f}"
    )


def test_postgres_noncreator_operator_and_repeated_intent_audit(cancel_pg):
    f = cancel_pg
    principal = VerifiedPrincipal("oidc:" + "c" * 64)
    context = replace(f.context, principal_id=principal.principal_id)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": principal.principal_id},
        )
    assert invoke(f, principal=principal, context=context) == expected("succeeded")
    assert invoke(f, principal=principal, context=context) == expected("succeeded")
    assert state(f)[1] == [(principal.principal_id, "job.cancel", JOB)] * 2
    assert len(f.work) == 2
    released(f)


def test_postgres_minimal_lock_grant_and_association_write_denial(cancel_pg):
    f = cancel_pg
    with f.reader_engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,"
            "has_column_privilege(current_user,'operations','kind','UPDATE'),"
            "has_column_privilege(current_user,'operations','job_id','UPDATE'),"
            "has_column_privilege(current_user,'operations','project_id','UPDATE'),"
            "has_column_privilege(current_user,'jobs','payload','UPDATE'),"
            "has_table_privilege(current_user,'records','UPDATE'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, False, False, False, False, False)
    with pytest.raises(DBAPIError) as caught, f.reader_engine.begin() as connection:
        connection.execute(
            text("UPDATE operations SET job_id=job_id WHERE id=:id"), {"id": OPERATION}
        )
    assert caught.value.orig.sqlstate == "42501"
    assert invoke(f) == expected("succeeded")  # Real FOR SHARE succeeds with UPDATE(kind).
    assert len(state(f)[1]) == 1


def test_postgres_audit_privilege_failure_rolls_back_effect_then_granted_control(cancel_pg):
    f = cancel_pg
    with f.engine.begin() as connection:
        connection.exec_driver_sql(f"REVOKE INSERT ON audit FROM {f.pg['app_role']}")
    previous = snapshot(f)
    observed = []

    def error(context):
        observed.append(context.original_exception.sqlstate)

    event.listen(f.reader_engine, "handle_error", error)
    try:
        fault(lambda: invoke(f))
    finally:
        event.remove(f.reader_engine, "handle_error", error)
    assert observed == ["42501"] and snapshot(f) == previous
    with f.engine.begin() as connection:
        connection.exec_driver_sql(f"GRANT INSERT ON audit TO {f.pg['app_role']}")
    assert invoke(f) == expected("succeeded")
    assert len(state(f)[1]) == 1
    released(f)


@pytest.mark.parametrize("stage", ["UPDATE jobs", "INSERT INTO audit"])
def test_postgres_after_effect_sql_fault_has_positive_rollback(cancel_pg, monkeypatch, stage):
    f = cancel_pg
    previous, seen, commits = snapshot(f), [], []
    original_commit = Connection.commit

    def commit(connection):
        if connection.engine is f.reader_engine:
            commits.append(True)
        return original_commit(connection)

    def fail(_connection, _cursor, statement, *_args):
        if statement.startswith(stage) and not seen:
            seen.append(statement)
            raise RuntimeError("private SQL-stage canary")

    monkeypatch.setattr(Connection, "commit", commit)
    event.listen(f.reader_engine, "after_cursor_execute", fail)
    try:
        fault(lambda: invoke(f))
    finally:
        event.remove(f.reader_engine, "after_cursor_execute", fail)
    assert len(seen) == 1 and commits == [] and snapshot(f) == previous
    released(f)


@pytest.mark.parametrize("acknowledged", [False, True])
def test_postgres_commit_attempt_uncertainty_never_retries(cancel_pg, monkeypatch, acknowledged):
    f = cancel_pg
    original_commit, attempts = Connection.commit, []

    def commit(connection):
        if connection.engine is f.reader_engine:
            attempts.append(connection)
            if acknowledged:
                original_commit(connection)
            raise RuntimeError("private commit canary")
        return original_commit(connection)

    monkeypatch.setattr(Connection, "commit", commit)
    fault(lambda: invoke(f), "outcome_uncertain")
    row, audits = state(f)
    assert len(attempts) == 1
    assert row["cancel"] is acknowledged and len(audits) == int(acknowledged)
    released(f)


def test_postgres_after_ack_close_failure_is_uncertain_and_released(cancel_pg, monkeypatch):
    f = cancel_pg
    original_commit, original_close = Connection.commit, Connection.close
    acknowledged, faults = [], []

    def commit(connection):
        result = original_commit(connection)
        if connection.engine is f.reader_engine:
            acknowledged.append(connection)
        return result

    def close(connection):
        if connection in acknowledged and not faults:
            faults.append(connection)
            raise RuntimeError("private close canary")
        return original_close(connection)

    monkeypatch.setattr(Connection, "commit", commit)
    monkeypatch.setattr(Connection, "close", close)
    fault(lambda: invoke(f), "outcome_uncertain")
    assert len(acknowledged) == len(faults) == len(state(f)[1]) == 1
    assert state(f)[0]["cancel"] is True
    released(f)


def test_postgres_preflight_readonly_is_native_not_acl_denial(cancel_pg, monkeypatch):
    f = cancel_pg
    original, observed = operation_service.read_operation, []

    def write(connection, *args, **kwargs):
        try:
            connection.execute(text("UPDATE jobs SET cancel=TRUE WHERE id=:id"), {"id": JOB})
        except DBAPIError as error:
            observed.append(error.orig.sqlstate)
            raise
        return original(connection, *args, **kwargs)

    previous = snapshot(f)
    monkeypatch.setattr(operation_service, "read_operation", write)
    fault(lambda: invoke(f))
    assert observed == ["25006"] and snapshot(f) == previous
    monkeypatch.setattr(operation_service, "read_operation", original)
    assert invoke(f) == expected("succeeded")


@pytest.mark.parametrize(
    "count,distractors,key",
    [(0, False, False), (84, False, False), (84, True, True), (85, False, False)],
)
def test_postgres_capacity_trace_includes_cleanup_and_pre_effect_refusal(
    cancel_pg, monkeypatch, count, distractors, key
):
    f = cancel_pg
    if count:
        roots(f, count)
    if distractors:
        roots(f, 2000, start=1000, job="e" * 32)
        roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "malformed"})
        roots(f, 1, start=7000, job="e" * 32, update={"padding": "x" * (2 * 1024 * 1024)})
    principal, context = key_context(f, role="operator") if key else (f.principal, f.context)
    original_commit, commits = Connection.commit, []
    original_effect, effects = f.service._actions._cancel_effect, []

    def commit(connection):
        if connection.engine is f.reader_engine:
            commits.append(True)
        return original_commit(connection)

    def effect(*args):
        effects.append(True)
        return original_effect(*args)

    monkeypatch.setattr(Connection, "commit", commit)
    monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    if count == 85:
        previous = snapshot(f)
        fault(lambda: invoke(f, principal=principal, context=context))
        assert effects == commits == [] and snapshot(f) == previous
    else:
        assert invoke(f, principal=principal, context=context) == expected("succeeded")
        assert effects == commits == [True]
    work = f.work[0]
    assert len(f.work) == 1 and work.statements <= 512 and work.seconds < 10
    released(f)
    print(
        f"CANCEL PG roots={count} distractors={distractors} key={key} "
        f"attempts={work.statements} seconds={work.seconds:.6f}"
    )


def test_postgres_post_ack_cohort_growth_exhausts_same_owner_without_repeating_effect(
    cancel_pg, monkeypatch
):
    f = cancel_pg
    roots(f, 84)
    before_disclosure(f, monkeypatch, lambda: roots(f, 2, start=100))
    fault(lambda: invoke(f), "outcome_uncertain")
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    assert len(f.work) == 1
    released(f)


def test_postgres_worker_progress_and_result_refs_do_not_replace_captured_response(
    cancel_pg, monkeypatch
):
    f = cancel_pg
    with f.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET status='running' WHERE id=:id"), {"id": JOB})
    roots(f, 1)

    def progress():
        ids = roots(f, 2, start=2)
        result_ref(f, ids[0], object_id="8" * 32)
        result_ref(f, ids[1], object_id="7" * 32)
        with f.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE jobs SET status='failed',owner='new-worker',lease_until=1900000000,"
                    "reserved=:v,error='bounded legacy failure' WHERE id=:id"
                ),
                {"v": 2**53 + 1, "id": JOB},
            )

    before_disclosure(f, monkeypatch, progress)
    assert invoke(f) == expected("running")
    assert state(f)[0]["status"] == "failed" and len(state(f)[1]) == 1
    assert len(f.work) == 1


@pytest.mark.parametrize("change", ["created", "config", "operation"])
def test_postgres_post_ack_immutable_association_change_is_uncertain(
    cancel_pg, monkeypatch, change
):
    f = cancel_pg

    def mutate():
        with f.engine.begin() as connection:
            if change == "created":
                connection.execute(
                    text("UPDATE jobs SET created=created+1 WHERE id=:id"), {"id": JOB}
                )
            elif change == "config":
                connection.execute(
                    text(
                        "UPDATE jobs SET execution_config_ref=:v,"
                        "execution_config_digest=:v WHERE id=:id"
                    ),
                    {"v": "e" * 64, "id": JOB},
                )
            else:
                connection.execute(
                    text("UPDATE operations SET client_operation_id=:value WHERE id=:id"),
                    {"id": OPERATION, "value": "e" * 32},
                )

    before_disclosure(f, monkeypatch, mutate)
    fault(lambda: invoke(f), "outcome_uncertain")
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    assert len(f.work) == 1


@pytest.mark.parametrize("change", ["role", "member", "key_role", "key_expiry", "key_revoke"])
def test_postgres_fresh_authority_after_ack_preserves_denial_without_rollback(
    cancel_pg, monkeypatch, change
):
    f = cancel_pg
    principal, context = (
        key_context(f, role="operator") if change.startswith("key_") else (f.principal, f.context)
    )
    before_disclosure(f, monkeypatch, lambda: grant_change(f, change, principal))
    denial = ActionForbidden if change in {"role", "key_role"} else ResourceNotFound
    with pytest.raises(denial):
        invoke(f, principal=principal, context=context)
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    assert len(f.work) == 1
    released(f)


@pytest.mark.parametrize("after_ack", [False, True])
@pytest.mark.parametrize("revoked", [False, True])
def test_postgres_secondary_ref_failure_rechecks_fresh_authority_after_release(
    cancel_pg, monkeypatch, after_ack, revoked
):
    f = cancel_pg
    original = f.service._cancel_disclose if after_ack else f.service._cancel_mutate
    descriptor, check = operation_service.read_descriptor, f.service.authority.check
    failed_connections, fresh_connections, owners = [], [], []

    def observed_descriptor(connection, *args, **kwargs):
        try:
            return descriptor(connection, *args, **kwargs)
        except AdmissionStorageError:
            failed_connections.append(connection)
            raise

    def fresh_check(connection, *args, **kwargs):
        if failed_connections and not fresh_connections:
            assert failed_connections[0].closed
            assert owners[0]._failed and owners[0]._active is None
            assert connection is not failed_connections[0]
            fresh_connections.append(connection)
            # Only now revoke: the bounded secondary read has already failed
            # and its original transaction/locks have been released.
            if revoked:
                grant_change(f, "member", f.principal)
        return check(connection, *args, **kwargs)

    def change(*args, **kwargs):
        owners.append(args[2])
        assert all(connection.closed for connection in f.connections)
        with f.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM artifact_refs WHERE owner_kind='job' "
                    "AND owner_id=:id AND role='admission_config'"
                ),
                {"id": JOB},
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(operation_service, "read_descriptor", observed_descriptor)
    monkeypatch.setattr(f.service.authority, "check", fresh_check)
    monkeypatch.setattr(f.service, "_cancel_disclose" if after_ack else "_cancel_mutate", change)
    if revoked:
        with pytest.raises(ResourceNotFound):
            invoke(f)
    else:
        fault(lambda: invoke(f), "outcome_uncertain" if after_ack else "dependency_unavailable")
    assert len(failed_connections) == len(fresh_connections) == 1
    assert state(f)[0]["cancel"] is after_ack and len(state(f)[1]) == int(after_ack)
    assert len(f.work) == 1
    released(f)


@pytest.mark.parametrize("change", ["role", "member", "key_expiry", "reassociate"])
def test_postgres_project_wait_rechecks_original_association_and_current_authority(
    cancel_pg, monkeypatch, change
):
    f = cancel_pg
    principal, context = (
        key_context(f, role="operator") if change.startswith("key_") else (f.principal, f.context)
    )
    replacement = "6" * 32
    if change == "reassociate":
        with f.engine.begin() as connection:
            seed_job(connection, identifier=replacement)
    arrived, actor_pid = Event(), []
    original = operation_service.lock_authority

    def lock(authority, connection, *args, **kwargs):
        actor_pid.append(connection.connection.driver_connection.info.backend_pid)
        arrived.set()
        return original(authority, connection, *args, **kwargs)

    monkeypatch.setattr(operation_service, "lock_authority", lock)
    with f.engine.connect() as writer:
        writer.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        writer_pid = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        writer.execute(text("SELECT id FROM projects WHERE id=:id FOR UPDATE"), {"id": PROJECT})
        with ThreadPoolExecutor(max_workers=1) as pool:
            action = pool.submit(invoke, f, principal=principal, context=context)
            try:
                assert arrived.wait(3)
                wait_blocked(f.pg, actor_pid[0], writer_pid)
                if change == "reassociate":
                    writer.execute(
                        text("UPDATE operations SET job_id=:j,accepted_response=:a WHERE id=:id"),
                        {
                            "j": replacement,
                            "id": OPERATION,
                            "a": json.dumps(
                                {"job_id": replacement, "operation_id": OPERATION},
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    )
                elif change == "key_expiry":
                    writer.execute(
                        text("UPDATE api_keys SET expires=1 WHERE id=:id"), {"id": "d" * 32}
                    )
                elif change == "role":
                    writer.execute(
                        text("UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"),
                        {"id": principal.principal_id},
                    )
                else:
                    writer.execute(
                        text(
                            "UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"
                        ),
                        {"id": principal.principal_id},
                    )
                writer.commit()
                if change == "reassociate":
                    fault(lambda: action.result(timeout=8))
                else:
                    denial = ActionForbidden if change == "role" else ResourceNotFound
                    with pytest.raises(denial):
                        action.result(timeout=8)
            finally:
                writer.rollback()
    assert state(f)[0]["cancel"] is False and state(f)[1] == []
    if change == "reassociate":
        with f.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT cancel FROM jobs WHERE id=:id"), {"id": replacement}
                ).scalar_one()
                is False
            )
    released(f)


@pytest.mark.parametrize(
    "kind", ["organization", "membership", "key", "scope", "job", "operation", "operation_delete"]
)
def test_postgres_grant_target_and_operation_locks_survive_effect_until_commit(
    cancel_pg, monkeypatch, kind
):
    f = cancel_pg
    principal, context = (
        key_context(f, role="operator") if kind == "key" else (f.principal, f.context)
    )
    effect_done, release, writer_started, writer_done = Event(), Event(), Event(), Event()
    actor_pid, writer_pid = [], []
    original_effect = f.service._actions._cancel_effect
    original_disclose = f.service._cancel_disclose

    def effect(connection, *args):
        result = original_effect(connection, *args)
        actor_pid.append(connection.connection.driver_connection.info.backend_pid)
        effect_done.set()
        assert release.wait(8), "Observed lock test did not release the actor"
        return result

    def disclose(*args, **kwargs):
        assert writer_done.wait(5), "Owner writer did not finish after mutation commit"
        return original_disclose(*args, **kwargs)

    statements = {
        "organization": "UPDATE organizations SET id=id WHERE id=:org",
        "membership": (
            "UPDATE project_memberships SET role='viewer' WHERE project_id=:p AND principal_id=:id"
        ),
        "key": "UPDATE api_keys SET revoked=TRUE WHERE id=:key",
        "scope": (
            "UPDATE resource_scopes SET resource_id=resource_id "
            "WHERE resource_kind='job' AND resource_id=:job"
        ),
        "job": "UPDATE jobs SET reserved=reserved+1 WHERE id=:job",
        "operation": "UPDATE operations SET kind=kind WHERE id=:op",
        "operation_delete": "DELETE FROM operations WHERE id=:op",
    }

    def writer():
        try:
            with f.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
                writer_pid.append(
                    connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                )
                writer_started.set()
                connection.execute(
                    text(statements[kind]),
                    {
                        "org": context.organization_id,
                        "p": PROJECT,
                        "id": principal.principal_id,
                        "key": "d" * 32,
                        "job": JOB,
                        "op": OPERATION,
                    },
                )
        finally:
            writer_done.set()

    monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    monkeypatch.setattr(f.service, "_cancel_disclose", disclose)
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(invoke, f, principal=principal, context=context)
        try:
            if not effect_done.wait(5):
                action.result(timeout=1)
                pytest.fail("Cancellation did not reach its staged effect")
            mutation = pool.submit(writer)
            assert writer_started.wait(3)
            if writer_done.is_set():
                mutation.result(timeout=1)
            try:
                wait_blocked(f.pg, writer_pid[0], actor_pid[0])
            except BaseException:
                if writer_done.is_set():
                    mutation.result(timeout=1)
                raise
        finally:
            release.set()
        assert mutation.result(timeout=8) is None
        if kind in {"membership", "key", "operation_delete"}:
            denial = ActionForbidden if kind == "membership" else ResourceNotFound
            with pytest.raises(denial):
                action.result(timeout=8)
        else:
            assert action.result(timeout=8) == expected("succeeded")
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    released(f)


@pytest.mark.parametrize(
    "identifier,exists", [("bad", False), ("f" * 32, False), (OPERATION, True)]
)
def test_postgres_viewer_visibility_precedes_cancel_permission(cancel_pg, identifier, exists):
    f = cancel_pg
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE project_memberships SET role='viewer' WHERE principal_id=:id"),
            {"id": PRINCIPAL},
        )
    previous = snapshot(f)
    with pytest.raises(ActionForbidden if exists else ResourceNotFound):
        invoke(f, operation_id=identifier)
    assert snapshot(f) == previous
    released(f)


def test_postgres_real_fresh_ar6_guard_has_zero_target_effects(pg, monkeypatch):
    prepare_postgres(pg)
    drain(pg)
    initialize_projection(pg["owner"])
    drain(pg)
    initialize_admission(pg["owner"])
    service = OperationService(pg["owner"], RequestAuthority(pg["owner"]))
    assert service.schema_compatibility().code == "migration_only"
    profile = load_release_profile().model_dump()
    monkeypatch.setattr(
        service, "_cancel", lambda *_a: pytest.fail("cancel before real schema guard")
    )
    principal = VerifiedPrincipal(PRINCIPAL)
    context = ProjectContext("8" * 32, PROJECT, PRINCIPAL)
    with pg["owner"].connect() as connection:
        before = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM audit)"
        ).one()
    fault(lambda: service.cancel_operation(principal, context, OPERATION), "schema_incompatible")
    with pg["owner"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM audit)"
            ).one()
            == before
        )
    assert load_release_profile().model_dump() == profile


@pytest.mark.parametrize("cleanup", ["close", "finish"])
def test_postgres_acknowledged_rollback_cleanup_failure_remains_dependency(
    cancel_pg, monkeypatch, cleanup
):
    f = cancel_pg
    original_effect = f.service._actions._cancel_effect
    original_rollback, original_close = Connection.rollback, Connection.close
    staged, mutation_connections, rollback_acks, cleanup_faults = [], [], [], []

    def effect(*args):
        result = original_effect(*args)
        staged.append(result)
        mutation_connections.append(args[0])
        raise RuntimeError("private precommit effect failure")

    def rollback(connection):
        result = original_rollback(connection)
        if connection.engine is f.reader_engine and staged:
            rollback_acks.append(connection)
        return result

    def close(connection):
        if connection.engine is f.reader_engine and staged and not cleanup_faults:
            cleanup_faults.append(connection)
            raise RuntimeError("private post-rollback close failure")
        return original_close(connection)

    original_mutate = f.service._cancel_mutate

    def mutate(principal, context, owner, *args):
        if cleanup == "finish":
            original_finish = owner.work.finish

            def finish():
                original_finish()
                if staged and not cleanup_faults:
                    cleanup_faults.append(True)
                    raise RuntimeError("private post-rollback finish failure")

            monkeypatch.setattr(owner.work, "finish", finish)
        return original_mutate(principal, context, owner, *args)

    previous = snapshot(f)
    monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    monkeypatch.setattr(f.service, "_cancel_mutate", mutate)
    monkeypatch.setattr(Connection, "rollback", rollback)
    if cleanup == "close":
        monkeypatch.setattr(Connection, "close", close)
    fault(lambda: invoke(f))
    assert len(staged) == len(cleanup_faults) == len(mutation_connections) == 1
    assert mutation_connections[0] in rollback_acks
    if cleanup == "close":
        assert cleanup_faults == mutation_connections
    assert snapshot(f) == previous
    released(f)


@pytest.mark.parametrize("failure", ["connect", "spent_work", "finish"])
def test_postgres_failed_fresh_recheck_after_ack_preserves_uncertainty(
    cancel_pg, monkeypatch, failure
):
    from contextlib import contextmanager

    from sqlalchemy.exc import SQLAlchemyError

    from agent_rewind.admission_transaction import AdmissionError

    f = cancel_pg
    read_scope, scopes, injected = operation_service.operation_connection, [], []

    def remove_config():
        with f.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM artifact_refs WHERE owner_kind='job' "
                    "AND owner_id=:id AND role='admission_config'"
                ),
                {"id": JOB},
            )

    @contextmanager
    def connection(engine, work):
        scopes.append(work)
        if len(scopes) == 3:
            injected.append(failure)
            assert all(c.closed for c in f.connections)
            if failure == "connect":

                def unavailable():
                    raise SQLAlchemyError("private failure-classification acquisition")

                monkeypatch.setattr(engine, "connect", unavailable)
            elif failure == "spent_work":
                work.seconds = 10.0
            else:
                original_finish = work.finish

                def finish():
                    original_finish()
                    raise AdmissionError("dependency_unavailable") from None

                monkeypatch.setattr(work, "finish", finish)
        with read_scope(engine, work) as current:
            yield current

    monkeypatch.setattr(operation_service, "operation_connection", connection)
    before_disclosure(f, monkeypatch, remove_config)
    fault(lambda: invoke(f), "outcome_uncertain")
    assert injected == [failure] and len(scopes) == 3
    assert len(f.work) == 1 and all(work is f.work[0] for work in scopes)
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    released(f)


@pytest.mark.parametrize("change", ["role", "member"])
def test_postgres_after_ack_typed_authority_denial_survives_cleanup_failure(
    cancel_pg, monkeypatch, change
):
    f = cancel_pg
    check, close = f.service.authority.check, Connection.close
    denials, cleanup_faults = [], []

    def checked(*args, **kwargs):
        try:
            return check(*args, **kwargs)
        except (ActionForbidden, ResourceNotFound) as error:
            denials.append(error)
            raise

    def failed_close(connection):
        if connection.engine is f.reader_engine and denials and not cleanup_faults:
            cleanup_faults.append(connection)
            raise RuntimeError("private denial cleanup")
        return close(connection)

    monkeypatch.setattr(f.service.authority, "check", checked)
    monkeypatch.setattr(Connection, "close", failed_close)
    before_disclosure(f, monkeypatch, lambda: grant_change(f, change, f.principal))
    with pytest.raises(ActionForbidden if change == "role" else ResourceNotFound) as caught:
        invoke(f)
    assert len(denials) == len(cleanup_faults) == 1
    assert caught.value is denials[0]
    assert state(f)[0]["cancel"] is True and len(state(f)[1]) == 1
    released(f)


@pytest.mark.parametrize("after_ack", [False, True])
def test_postgres_queuepool_cleanup_failure_discards_physical_connection_then_reuses(
    cancel_pg, monkeypatch, after_ack
):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import QueuePool

    from agent_rewind.migrations.compatibility import (
        CompatibilityResult,
        configure_runtime_engine,
    )

    f = cancel_pg
    engine = create_engine(
        f.reader_engine.url, poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=1
    )
    configure_runtime_engine(engine)
    service = OperationService(
        engine, RequestAuthority(engine), artifact_loader=f.service.artifact_loader
    )
    monkeypatch.setattr(
        service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    original_close, original_commit = Connection.close, Connection.commit
    original_effect = service._actions._cancel_effect
    staged, raw, commits, close_faults, connections = [], [], [], [], [], []

    def connected(connection):
        connections.append(connection)

    def effect(connection, *args):
        result = original_effect(connection, *args)
        staged.append(connection)
        raw.append(connection.connection.driver_connection)
        if not after_ack:
            raise RuntimeError("private staged-effect failure")
        return result

    def commit(connection):
        result = original_commit(connection)
        if connection.engine is engine:
            commits.append(connection)
        return result

    def close(connection):
        if staged and connection is staged[0] and not close_faults:
            close_faults.append(connection)
            raise RuntimeError("private pooled pre-close failure")
        return original_close(connection)

    event.listen(engine, "engine_connect", connected)
    monkeypatch.setattr(service._actions, "_cancel_effect", effect)
    monkeypatch.setattr(Connection, "commit", commit)
    monkeypatch.setattr(Connection, "close", close)
    try:
        fault(
            lambda: service.cancel_operation(f.principal, f.context, OPERATION),
            "outcome_uncertain" if after_ack else "dependency_unavailable",
        )
        assert len(staged) == len(raw) == len(close_faults) == 1
        assert len(commits) == int(after_ack)
        assert state(f)[0]["cancel"] is after_ack and len(state(f)[1]) == int(after_ack)
        assert engine.pool.checkedout() == 0
        assert raw[0].closed and all(connection.closed for connection in connections)
        assert all(work._started is None for work in f.work)

        # Public pool checkout proves usable capacity and a different physical
        # PostgreSQL connection, not merely a closed SQLAlchemy wrapper.
        with engine.connect() as connection:
            current = connection.connection.driver_connection
            assert current is not raw[0] and not current.closed
            assert current.info.transaction_status == 0
            assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "off"
            assert (
                connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
                == "read committed"
            )
        assert engine.pool.checkedout() == 0
        monkeypatch.setattr(service._actions, "_cancel_effect", original_effect)
        monkeypatch.setattr(Connection, "commit", original_commit)
        monkeypatch.setattr(Connection, "close", original_close)
        assert service.cancel_operation(f.principal, f.context, OPERATION) == expected("succeeded")
        assert len(state(f)[1]) == 1 + int(after_ack)
        assert engine.pool.checkedout() == 0
        assert all(connection.closed for connection in connections)
        assert all(work._started is None for work in f.work)
    finally:
        event.remove(engine, "engine_connect", connected)
        engine.dispose()
