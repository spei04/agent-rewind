"""Cancellation service on actual ar6 rows, owned SQLite and real transaction outcomes."""

from dataclasses import replace

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT, SECOND_JOB
from test_artifact_metadata import OTHER
from test_operation_service import (
    admission_engine,
    get_fixture,
    key_context,
    repository,
    stored,
)
from test_operation_sources import roots

from agent_rewind import operation_service, operation_work
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import configure_artifact_engine
from agent_rewind.errors import Fault
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_actions import ScopedActions
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["admission_engine", "repository", "stored", "get_fixture"]


@pytest.fixture
def cancel_fixture(get_fixture, monkeypatch):
    f = get_fixture
    configure_artifact_engine(f.reader_engine)
    f.sql, f.commits, f.owners = [], [], []
    original = operation_service.CancellationReceipts

    def owner(*args):
        value = original(*args)
        f.owners.append(value)
        return value

    monkeypatch.setattr(operation_service, "CancellationReceipts", owner)
    f.service.artifact_loader = lambda _value: pytest.fail("cancellation loaded an artifact")

    def before(_c, _u, sql, *_args):
        f.sql.append(sql)

    def commit(connection):
        f.commits.append(connection)

    event.listen(f.reader_engine, "before_cursor_execute", before)
    event.listen(f.reader_engine, "commit", commit)
    try:
        yield f
    finally:
        event.remove(f.reader_engine, "before_cursor_execute", before)
        event.remove(f.reader_engine, "commit", commit)
        assert all(owner._active is None for owner in f.owners)
        assert all(work._started is None for work in f.work)
        assert f.reader_engine.pool.checkedout() == 0


def cancel(f, **updates):
    args = dict(principal=f.principal, context=f.context, operation_id=OPERATION)
    args.update(updates)
    return f.service.cancel_operation(**args)


def change(f, sql, **parameters):
    with f.engine.begin() as connection:
        connection.execute(text(sql), parameters)


def state(f):
    with f.engine.connect() as connection:
        job = dict(
            connection.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": JOB})
            .mappings()
            .one()
        )
        audits = [
            dict(row)
            for row in connection.execute(text("SELECT * FROM audit ORDER BY id")).mappings()
        ]
    return job, audits


def fault(call, code="dependency_unavailable"):
    with pytest.raises(Fault) as caught:
        call()
    assert caught.value.code == code
    assert caught.value.__suppress_context__ and caught.value.__cause__ is None
    return caught.value


def effects(f):
    return [
        sql for sql in f.sql if sql.startswith("UPDATE jobs") or sql.startswith("INSERT INTO audit")
    ]


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed", "cancelled"])
def test_exact_response_effect_and_repeated_intent_preserve_worker_fields(cancel_fixture, status):
    f = cancel_fixture
    change(
        f,
        "UPDATE jobs SET status=:status,cancel=false,error=:error,reserved=:reserved,"
        "owner='worker',lease_until=1900000000,result=:result WHERE id=:id",
        status=status,
        error="private legacy error",
        reserved=2**53 + 1,
        result="c" * 64,
        id=JOB,
    )
    before, audits = state(f)
    expected = "cancelled" if status == "queued" else status
    for i in range(2):
        assert cancel(f) == {
            "operation_id": OPERATION,
            "cancel_requested": True,
            "status": expected,
        }
        after, observed = state(f)
        assert after == {**before, "cancel": 1, "status": expected}
        assert len(observed) == len(audits) + i + 1
        assert all(
            row["actor"] == PRINCIPAL and row["action"] == "job.cancel" and row["target"] == JOB
            for row in observed
        )
        assert len({row["id"] for row in observed}) == len(observed)
    assert len(f.commits) == 2 and len(effects(f)) == 4
    assert all(owner.source_visits == 3 and owner.edges == 0 for owner in f.owners)


@pytest.mark.parametrize("key", [False, True])
@pytest.mark.parametrize("count,distractors", [(0, False), (84, False), (84, True)])
def test_full_service_capacity_and_final_work_trace(cancel_fixture, key, count, distractors):
    f = cancel_fixture
    if count:
        roots(f, count)
    if distractors:
        roots(f, 2000, start=1000, job=SECOND_JOB)
        roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "bad"})
    principal, context = key_context(f, "operator") if key else (f.principal, f.context)
    response = cancel(f, principal=principal, context=context)
    assert response["cancel_requested"] is True
    owner, work = f.owners[0], f.work[0]
    assert owner.source_visits == 3 * (1 + count) and owner.edges == 6 * count
    assert work.statements < 512 and work.instructions < 20_000_000 and work.seconds < 10
    assert work._started is None and f.reader_engine.pool.checkedout() == 0
    assert len(f.commits) == 1 and len(effects(f)) == 2
    print(
        f"CANCEL SQLite roots={count} distractors={distractors} key={key} "
        f"attempts={work.statements} vm={work.instructions} seconds={work.seconds:.6f}"
    )


def test_85_roots_refuse_before_effect_audit_or_commit(cancel_fixture):
    f = cancel_fixture
    roots(f, 85)
    before = state(f)
    fault(lambda: cancel(f))
    assert state(f) == before and not effects(f) and not f.commits
    assert f.owners[0].source_visits == 172 and f.owners[0].edges == 340
    assert f.owners[0]._failed


@pytest.mark.parametrize("when", ["before_mutation", "before_disclosure"])
def test_worker_progress_allowed_and_response_captured_at_effect(cancel_fixture, monkeypatch, when):
    f = cancel_fixture
    change(f, "UPDATE jobs SET status='queued' WHERE id=:id", id=JOB)
    name = "_cancel_mutate" if when == "before_mutation" else "_cancel_disclose"
    original = getattr(f.service, name)

    def advance(*args):
        assert f.reader_engine.pool.checkedout() == 0
        change(
            f,
            "UPDATE jobs SET status='succeeded',reserved=:n,result=:digest,error='legacy',"
            "owner='worker',lease_until=1900000000 WHERE id=:id",
            n=2**53 + 1,
            digest="d" * 64,
            id=JOB,
        )
        roots(f, 1)
        return original(*args)

    monkeypatch.setattr(f.service, name, advance)
    response = cancel(f)
    assert response["status"] == ("succeeded" if when == "before_mutation" else "cancelled")
    job, audits = state(f)
    assert job["status"] == "succeeded" and job["cancel"] == 1 and len(audits) == 1
    assert len(f.commits) == 1


def test_late_cohort_growth_after_ack_is_uncertain_without_repeat(cancel_fixture, monkeypatch):
    f = cancel_fixture
    roots(f, 84)
    original = f.service._cancel_disclose

    def grow(*args):
        assert len(f.commits) == 1 and f.reader_engine.pool.checkedout() == 0
        roots(f, 2, start=100)
        return original(*args)

    monkeypatch.setattr(f.service, "_cancel_disclose", grow)
    fault(lambda: cancel(f), "outcome_uncertain")
    assert state(f)[0]["cancel"] == 1 and len(state(f)[1]) == 1
    assert len(effects(f)) == 2 and len(f.commits) == 1


@pytest.mark.parametrize(
    "role,operation_id,error",
    [
        ("viewer", OPERATION, ActionForbidden),
        ("viewer", "f" * 32, ResourceNotFound),
        ("operator", "f" * 32, ResourceNotFound),
        ("viewer", "invalid", ResourceNotFound),
    ],
)
def test_visibility_precedes_cancel_permission(cancel_fixture, role, operation_id, error):
    f = cancel_fixture
    change(
        f,
        "UPDATE project_memberships SET role=:role WHERE principal_id=:id",
        role=role,
        id=PRINCIPAL,
    )
    before = state(f)
    with pytest.raises(error):
        cancel(f, operation_id=operation_id)
    assert state(f) == before and not effects(f) and not f.commits


def test_noncreator_operator_can_cancel_original_named_project(cancel_fixture):
    f = cancel_fixture
    actor = VerifiedPrincipal("oidc:" + "f" * 64)
    change(
        f,
        "INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)",
        p=PROJECT,
        id=actor.principal_id,
    )
    context = replace(f.context, principal_id=actor.principal_id)
    assert cancel(f, principal=actor, context=context)["operation_id"] == OPERATION
    assert state(f)[1][0]["actor"] == actor.principal_id


@pytest.mark.parametrize("mutation", ["role", "revoked", "expiry", "scope"])
def test_actual_key_ceiling_and_revocation_precede_effect(cancel_fixture, mutation):
    f = cancel_fixture
    principal, context = key_context(f, "viewer" if mutation == "role" else "operator")
    expected = ActionForbidden if mutation == "role" else ResourceNotFound
    if mutation == "revoked":
        change(f, "UPDATE api_keys SET revoked=true")
    elif mutation == "expiry":
        change(f, "UPDATE api_keys SET expires=1")
    elif mutation == "scope":
        change(f, "DELETE FROM resource_scopes WHERE resource_kind='key'")
    with pytest.raises(expected):
        cancel(f, principal=principal, context=context)
    assert not effects(f) and not f.commits


@pytest.mark.parametrize("case", ["identity", "foreign", "revoked", "viewer", "sql", "cleanup"])
def test_malformed_identifier_only_checks_original_authority(cancel_fixture, monkeypatch, case):
    f = cancel_fixture
    principal, context = f.principal, f.context
    expected = ResourceNotFound
    if case == "identity":
        principal, expected = object(), IdentityInvalid
    elif case == "foreign":
        context = replace(context, project_id=OTHER)
    elif case == "revoked":
        change(
            f,
            "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id",
            id=PRINCIPAL,
        )
    elif case == "viewer":
        change(
            f, "UPDATE project_memberships SET role='viewer' WHERE principal_id=:id", id=PRINCIPAL
        )
    elif case == "sql":
        monkeypatch.setattr(
            f.service.authority,
            "check",
            lambda *_a, **_k: (_ for _ in ()).throw(AdmissionError("dependency_unavailable")),
        )
        expected = Fault
    else:
        original = operation_work.close_owned

        def close(connection, receipt):
            original(connection, receipt)
            raise RuntimeError("private close detail")

        monkeypatch.setattr(operation_work, "close_owned", close)
        expected = Fault
    with pytest.raises(expected) as caught:
        cancel(f, principal=principal, context=context, operation_id="bad")
    if expected is Fault:
        assert caught.value.code == "dependency_unavailable"
    assert not f.owners and not effects(f) and not f.commits
    assert not any(
        word in sql
        for sql in f.sql
        for word in (
            "FROM operations",
            "FROM jobs",
            "FROM records",
            "artifact_objects",
            "artifact_refs",
        )
    )


@pytest.mark.parametrize("when", ["before_mutation", "before_disclosure"])
@pytest.mark.parametrize("mutation", ["reassociate", "created", "config"])
def test_original_association_changes_refuse_without_replacement_target(
    cancel_fixture, monkeypatch, when, mutation
):
    f = cancel_fixture
    name = "_cancel_mutate" if when == "before_mutation" else "_cancel_disclose"
    original = getattr(f.service, name)

    def mutate(*args):
        if mutation == "reassociate":
            change(
                f,
                "UPDATE operations SET job_id=:job,accepted_response=:body WHERE id=:op",
                job=SECOND_JOB,
                body='{"operation_id":"' + OPERATION + '","job_id":"' + SECOND_JOB + '"}',
                op=OPERATION,
            )
        elif mutation == "created":
            change(f, "UPDATE jobs SET created=created+1 WHERE id=:id", id=JOB)
        else:
            change(f, "DELETE FROM artifact_refs WHERE role='admission_config'")
        return original(*args)

    monkeypatch.setattr(f.service, name, mutate)
    fault(
        lambda: cancel(f),
        "outcome_uncertain" if when == "before_disclosure" else "dependency_unavailable",
    )
    assert len(f.commits) == (1 if when == "before_disclosure" else 0)
    with f.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT cancel FROM jobs WHERE id=:id"), {"id": SECOND_JOB}
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("secondary", ["config", "cohort", "post_ack"])
@pytest.mark.parametrize("denial", ["revoked", "viewer"])
def test_secondary_failure_fresh_typed_authority_after_cleanup(
    cancel_fixture, monkeypatch, secondary, denial
):
    f = cancel_fixture
    if secondary == "config":
        change(f, "DELETE FROM artifact_refs WHERE role='admission_config'")
    elif secondary == "cohort":
        roots(f, 1, update={"parent_id": "f" * 32})
    original_check = f.service.authority.check
    failed_connections = []
    source_name = "read_run_cohort" if secondary == "cohort" else "read_descriptor"
    original_source = getattr(operation_service, source_name)

    def failed_source(connection, *args, **kwargs):
        try:
            return original_source(connection, *args, **kwargs)
        except AdmissionStorageError:
            failed_connections.append(connection)
            raise

    monkeypatch.setattr(operation_service, source_name, failed_source)
    changed = False

    def check(connection, principal, context, action="read", **kwargs):
        nonlocal changed
        # Observe the actual secondary refusal, then prove its Connection was
        # released before revoking authority in the independent classifier.
        if failed_connections and not changed:
            assert len(failed_connections) == 1 and failed_connections[0].closed
            assert connection is not failed_connections[0]
            assert f.owners[0]._failed and f.owners[0]._active is None
            changed = True
            if denial == "revoked":
                change(
                    f,
                    "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id",
                    id=PRINCIPAL,
                )
            else:
                change(
                    f,
                    "UPDATE project_memberships SET role='viewer' WHERE principal_id=:id",
                    id=PRINCIPAL,
                )
        return original_check(connection, principal, context, action, **kwargs)

    monkeypatch.setattr(f.service.authority, "check", check)
    if secondary == "post_ack":
        original = f.service._cancel_disclose

        def disclose(*args):
            change(f, "DELETE FROM artifact_refs WHERE role='admission_config'")
            return original(*args)

        monkeypatch.setattr(f.service, "_cancel_disclose", disclose)
    with pytest.raises(ResourceNotFound if denial == "revoked" else ActionForbidden):
        cancel(f)
    assert changed and len(failed_connections) == 1
    assert len(f.commits) == (1 if secondary == "post_ack" else 0)


@pytest.mark.parametrize("stage", ["effect", "audit"])
def test_sql_effect_and_audit_failure_roll_back_every_row(cancel_fixture, monkeypatch, stage):
    f = cancel_fixture
    before = state(f)
    if stage == "effect":
        original = f.service._actions._cancel_effect

        def effect(*args):
            original(*args)
            raise RuntimeError("private post-effect detail")

        monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    else:
        monkeypatch.setattr(
            f.service._actions,
            "_audit",
            lambda *_a: (_ for _ in ()).throw(RuntimeError("private audit detail")),
        )
    fault(lambda: cancel(f))
    assert state(f) == before and not f.commits
    assert f.owners[0]._failed


@pytest.mark.parametrize("ack", [False, True])
def test_commit_acknowledgement_loss_never_retries(cancel_fixture, monkeypatch, ack):
    f = cancel_fixture
    original = Connection.commit
    calls = []

    def commit(connection):
        if connection.engine is f.reader_engine:
            calls.append(connection)
            if ack:
                original(connection)
            raise RuntimeError("private lost acknowledgement")
        return original(connection)

    monkeypatch.setattr(Connection, "commit", commit)
    fault(lambda: cancel(f), "outcome_uncertain")
    job, audits = state(f)
    assert len(calls) == 1 and len(effects(f)) == 2
    assert job["cancel"] == int(ack) and len(audits) == int(ack)


@pytest.mark.parametrize("failure", ["budget", "cleanup", "sql", "connect", "finish"])
def test_post_ack_classifier_failure_cannot_become_retryable(cancel_fixture, monkeypatch, failure):
    f = cancel_fixture

    def disclose(_principal, _context, owner, _job):
        assert len(f.commits) == 1
        if failure == "budget":
            owner.work.statements = 512
        elif failure == "cleanup":
            original = operation_work.close_owned

            def close(connection, receipt):
                original(connection, receipt)
                raise RuntimeError("private close failure")

            monkeypatch.setattr(operation_work, "close_owned", close)
        elif failure == "connect":
            monkeypatch.setattr(
                operation_work,
                "connect_owned",
                lambda *_a, **_k: (_ for _ in ()).throw(AdmissionError("dependency_unavailable")),
            )
        elif failure == "finish":
            original_finish = operation_work.OperationWork.finish

            def finish(work):
                original_finish(work)
                raise AdmissionError("dependency_unavailable")

            monkeypatch.setattr(operation_work.OperationWork, "finish", finish)
        else:
            monkeypatch.setattr(
                f.service.authority,
                "check",
                lambda *_a, **_k: (_ for _ in ()).throw(AdmissionError("dependency_unavailable")),
            )
        raise AdmissionError("dependency_unavailable")

    monkeypatch.setattr(f.service, "_cancel_disclose", disclose)
    fault(lambda: cancel(f), "outcome_uncertain")
    assert state(f)[0]["cancel"] == 1 and len(state(f)[1]) == 1 and len(f.commits) == 1


@pytest.mark.parametrize("where", ["preflight", "effect", "disclosure"])
def test_primary_interruption_identity_survives_cleanup(cancel_fixture, monkeypatch, where):
    f = cancel_fixture
    primary = KeyboardInterrupt("private interruption")
    if where == "preflight":
        monkeypatch.setattr(
            f.service.authority, "check", lambda *_a, **_k: (_ for _ in ()).throw(primary)
        )
    elif where == "effect":
        monkeypatch.setattr(
            f.service._actions, "_cancel_effect", lambda *_a: (_ for _ in ()).throw(primary)
        )
    else:
        monkeypatch.setattr(
            f.service, "_cancel_disclose", lambda *_a: (_ for _ in ()).throw(primary)
        )
    with pytest.raises(KeyboardInterrupt) as caught:
        cancel(f)
    assert caught.value is primary
    assert len(f.commits) == (1 if where == "disclosure" else 0)


def test_legacy_cancel_preserves_instance_audit_dispatch(cancel_fixture, monkeypatch):
    f = cancel_fixture
    actions = ScopedActions(f.reader_engine, RequestAuthority(f.reader_engine))
    calls = []
    original = actions._audit

    def audit(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(actions, "_audit", audit)
    assert actions.cancel(f.principal, f.context, JOB) is None
    assert len(calls) == 1 and calls[0][3:] == ("job.cancel", JOB)
    assert state(f)[0]["cancel"] == 1


@pytest.mark.parametrize(
    "state,code",
    [("incompatible", "schema_incompatible"), ("unavailable", "dependency_unavailable")],
)
def test_schema_guard_precedes_malformed_identity_and_every_sink(
    cancel_fixture, monkeypatch, state, code
):
    f = cancel_fixture
    monkeypatch.setattr(f.service, "schema_compatibility", lambda: CompatibilityResult(state, code))
    fault(lambda: cancel(f, operation_id="bad"), code)
    assert not f.sql and not f.owners and not f.work and not f.commits


def test_unrelated_programming_error_outside_transaction_stays_internal_boundary(
    cancel_fixture, monkeypatch
):
    f = cancel_fixture
    error = TypeError("programming error")
    monkeypatch.setattr(f.service, "_cancel_disclose", lambda *_a: (_ for _ in ()).throw(error))
    with pytest.raises(TypeError) as caught:
        cancel(f)
    assert caught.value is error and len(f.commits) == 1


def test_result_artifact_refs_change_without_cancellation_observation(cancel_fixture, monkeypatch):
    from test_operation_sources import result_ref

    f = cancel_fixture
    original = f.service._cancel_disclose

    def change_refs(*args):
        for number in range(3, 7):
            result_ref(f, str(number) * 32, publish=False, object_id=f"{100 + number:032x}")
        return original(*args)

    monkeypatch.setattr(f.service, "_cancel_disclose", change_refs)
    assert cancel(f)["cancel_requested"] is True
    assert not f.loads and len(state(f)[1]) == 1


def test_within_mutation_job_drift_refuses_before_intent_and_rolls_back(
    cancel_fixture, monkeypatch
):
    from agent_rewind.operation_cancellation import CancellationPhase

    f = cancel_fixture
    before = state(f)
    original = CancellationPhase.verify

    def drift(phase, connection, cohort):
        if phase._generation == 2:
            connection.execute(text("UPDATE jobs SET owner='changed' WHERE id=:id"), {"id": JOB})
        return original(phase, connection, cohort)

    monkeypatch.setattr(CancellationPhase, "verify", drift)
    fault(lambda: cancel(f))
    assert state(f) == before and not f.commits
    assert f.owners[0]._failed


def test_changed_legacy_default_does_not_redirect_original_context(cancel_fixture, monkeypatch):
    f = cancel_fixture
    original = f.service._cancel_mutate

    def change_default(*args):
        change(
            f,
            "UPDATE project_memberships SET legacy_default=false WHERE principal_id=:id",
            id=PRINCIPAL,
        )
        return original(*args)

    monkeypatch.setattr(f.service, "_cancel_mutate", change_default)
    assert cancel(f)["operation_id"] == OPERATION
    assert len(state(f)[1]) == 1


def test_real_schema_guard_refuses_before_any_cancellation_scope(settings, monkeypatch):
    from agent_rewind.database import Database
    from agent_rewind.migrations.compatibility import load_release_profile
    from agent_rewind.operation_service import OperationService
    from agent_rewind.scoped_repositories import ProjectContext

    database = Database(settings)
    try:
        database.migrate(installation_key="operation-cancel-real-guard")
        service = OperationService(database.engine, RequestAuthority(database.engine))
        assert service.schema_compatibility().code == "migration_only"
        original = load_release_profile().model_dump()
        monkeypatch.setattr(service, "_cancel", lambda *_a: pytest.fail("customer cancellation"))
        principal = VerifiedPrincipal(PRINCIPAL)
        context = ProjectContext("8" * 32, PROJECT, principal.principal_id)
        fault(
            lambda: service.cancel_operation(principal, context, OPERATION), "schema_incompatible"
        )
        assert load_release_profile().model_dump() == original
        assert database.engine.pool.checkedout() == 0
    finally:
        database.engine.dispose()


def test_unowned_sqlite_cannot_enter_cancellation_schema_inspection(stored, monkeypatch):
    from agent_rewind.operation_service import OperationService

    service = OperationService(stored.engine, stored.authority)
    monkeypatch.setattr(service, "schema_compatibility", lambda: pytest.fail("inspection"))
    fault(lambda: service.cancel_operation(stored.principal, stored.context, OPERATION))


@pytest.mark.parametrize("cleanup", ["close", "finish"])
def test_acknowledged_precommit_rollback_with_cleanup_failure_is_dependency(
    cancel_fixture, monkeypatch, cleanup
):
    import agent_rewind.admission_transaction as transaction_module

    f = cancel_fixture
    before = state(f)
    original_effect = f.service._actions._cancel_effect

    def effect(*args):
        original_effect(*args)
        if cleanup == "close":
            original = transaction_module.close_owned

            def close(connection, receipt):
                original(connection, receipt)
                raise RuntimeError("private close failure")

            monkeypatch.setattr(transaction_module, "close_owned", close)
        else:
            original = operation_work.OperationWork.finish

            def finish(work):
                original(work)
                raise RuntimeError("private finish failure")

            monkeypatch.setattr(operation_work.OperationWork, "finish", finish)
        raise RuntimeError("private effect failure")

    monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    fault(lambda: cancel(f))
    assert state(f) == before and not f.commits and len(effects(f)) == 2


def test_work_exhaustion_at_commit_preparation_rolls_back_without_commit_attempt(
    cancel_fixture, monkeypatch
):
    f = cancel_fixture
    before = state(f)
    original = f.service._actions._cancel_effect

    def effect(*args):
        result = original(*args)
        f.work[0].statements = 504  # ordinary allowance; mandatory cleanup retains its reserve
        return result

    monkeypatch.setattr(f.service._actions, "_cancel_effect", effect)
    fault(lambda: cancel(f))
    assert state(f) == before and not f.commits and len(effects(f)) == 2
    assert f.work[0].statements <= 512 and f.work[0]._started is None


@pytest.mark.parametrize("denial", [ResourceNotFound(), ActionForbidden()])
def test_post_ack_typed_denial_identity_survives_cleanup_fault(cancel_fixture, monkeypatch, denial):
    f = cancel_fixture
    original = f.service._cancel_disclose

    def disclose(*args):
        def check(*_a, **_k):
            raise denial

        real_close = operation_work.close_owned

        def close(connection, receipt):
            real_close(connection, receipt)
            raise RuntimeError("private secondary cleanup")

        monkeypatch.setattr(f.service.authority, "check", check)
        monkeypatch.setattr(operation_work, "close_owned", close)
        return original(*args)

    monkeypatch.setattr(f.service, "_cancel_disclose", disclose)
    with pytest.raises(type(denial)) as caught:
        cancel(f)
    assert caught.value is denial and len(f.commits) == 1
    assert state(f)[0]["cancel"] == 1 and len(state(f)[1]) == 1
