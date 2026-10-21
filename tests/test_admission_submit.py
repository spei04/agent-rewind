"""Synthetic policy/ready instance, actual SQLite and encrypted local publication."""

import hashlib
import json
import traceback
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest
import test_admission_repository as fixtures
from cryptography.fernet import Fernet
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from test_admission_configuration import configuration
from test_admission_request import at_task_size, submission

from agent_rewind import admission_coordinator
from agent_rewind.admission_adapters import AdmissionReady, ProcessorPermission
from agent_rewind.admission_configuration import NativeConfiguration, NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_journal import AdmissionJournal
from agent_rewind.admission_journal_state import MAX_CHILD_BYTES, JournalIdentity
from agent_rewind.admission_repository import AdmissionRepository
from agent_rewind.admission_request import MAX_CONFIG_BYTES, MAX_TASK_BYTES, parse_submit
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import record_verified
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.publication_journal import JournalSession
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import IdentityInvalid, VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

admission_engine = fixtures.admission_engine


class Policy:
    """Test-only SQL version tied to project exclusion; no product policy grant."""

    def __init__(self, f):
        self.f, self.calls = f, []

    def require_available(self):
        self.calls.append("available")

    def permission(self, principal, context, intent, candidate):
        assert self.f.engine.pool.checkedout() == 0
        assert principal == self.f.principal and context == self.f.context
        assert candidate == self.f.config
        self.calls.append("permission")
        return ProcessorPermission(candidate.digest, candidate.processor_profile)

    def prepare(self, principal, context, intent, config):
        assert self.f.engine.pool.checkedout() == 0
        self.calls.append("prepare")
        return dict(
            schema=1,
            organization_id=context.organization_id,
            project_id=context.project_id,
            principal_id=principal.principal_id,
            request_digest=intent.request_digest,
            task_digest=intent.task_digest,
            configuration_digest=config.digest,
            permitted_processor_profile=config.processor_profile,
            version="fixture-v1",
            state={"project_name": self.f.name},
        )

    def recheck(self, connection, principal, context, intent, config, evidence):
        assert connection.in_transaction() and self.f.engine.pool.checkedout() == 1
        self.calls.append("recheck")
        name = connection.execute(
            text("SELECT name FROM projects WHERE id=:id"), {"id": context.project_id}
        ).scalar_one()
        if (
            evidence["state"]["project_name"] != name
            or evidence["configuration_digest"] != config.digest
        ):
            raise AdmissionError("dependency_unavailable")


class Ready:
    def __init__(self, f):
        self.f, self.calls = f, 0

    def check(self, *args):
        assert self.f.engine.pool.checkedout() == 0
        self.calls += 1
        return AdmissionReady(True)


class Storage:
    def __init__(self, f, root):
        self.f, self.calls, self.after = f, [], None
        self.local = LocalArtifactStorage(
            root, Fernet(Fernet.generate_key()), plaintext_limit=MAX_TASK_BYTES
        )

    def put_verified(self, descriptor, content):
        assert self.f.engine.pool.checkedout() == 0
        self.calls.append(descriptor)
        result = self.local.put_verified(descriptor, content)
        if self.after is not None:
            self.after(descriptor, content)
        return result


@pytest.fixture
def publication(admission_engine, tmp_path, monkeypatch):
    f = SimpleNamespace(engine=admission_engine, config=configuration())
    f.principal = VerifiedPrincipal(fixtures.PRINCIPAL)
    with f.engine.begin() as c:
        c.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": fixtures.PROJECT, "id": fixtures.PRINCIPAL},
        )
        f.name = c.execute(
            text("SELECT name FROM projects WHERE id=:p"), {"p": fixtures.PROJECT}
        ).scalar_one()
    f.authority = RequestAuthority(f.engine)
    f.context = f.authority.named(f.principal, fixtures.PROJECT).context
    f.intent = parse_submit(canonical(submission()))
    f.origin = OriginCorrelation("6" * 32)
    f.root = tmp_path / "journal"
    f.root.mkdir(mode=0o700)
    objects = tmp_path / "objects"
    objects.mkdir(mode=0o700)
    f.policy, f.ready = Policy(f), Ready(f)
    f.storage, f.journal = Storage(f, objects), AdmissionJournal(f.root)
    f.registry = NativeRegistry(f.config, ["fixture-image"])
    f.service = AdmissionCoordinator(
        f.engine,
        f.authority,
        policy=f.policy,
        readiness=f.ready,
        registry=f.registry,
        storage=f.storage,
        journal=f.journal,
    )
    monkeypatch.setattr(
        f.service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    # Durable calls are observable without a product hook; none may hold SQL.
    for name in ("freeze", "append"):
        original = getattr(JournalSession, name)

        def outside(session, *args, _original=original, **kwargs):
            assert f.engine.pool.checkedout() == 0
            return _original(session, *args, **kwargs)

        monkeypatch.setattr(JournalSession, name, outside)
    return f


def submit(f, **kwargs):
    values = dict(
        principal=f.principal,
        original_context=f.context,
        intent=f.intent,
        key_hash=fixtures.KEY,
        origin=f.origin,
    )
    values.update(kwargs)
    return f.service.submit(**values)


def identity(f):
    return JournalIdentity(
        f.context.organization_id,
        f.context.project_id,
        f.principal.principal_id,
        f.intent.client_operation_id,
        fixtures.KEY,
        f.intent.request_digest,
    )


def snapshot(f):
    with f.engine.connect() as c:
        return {
            name: c.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1,2").all()
            for name in (
                "jobs",
                "resource_scopes",
                "artifact_objects",
                "artifact_refs",
                "operations",
                "operation_keys",
                "audit",
            )
        }


def test_actual_new_publication_and_exact_sql_winner_without_dependencies(publication, monkeypatch):
    f = publication
    before = snapshot(f)
    accepted = submit(f)
    after = snapshot(f)
    assert set(accepted) == {"operation_id", "job_id"}
    assert len(after["jobs"]) == len(before["jobs"]) + 1
    assert len(after["artifact_refs"]) == 3 and len(after["artifact_objects"]) == 3
    assert len(after["operations"]) == len(after["operation_keys"]) == 1
    assert len(after["audit"]) == len(before["audit"]) + 1
    with f.engine.connect() as c:
        row = dict(
            c.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": accepted["job_id"]})
            .mappings()
            .one()
        )
        assert row == dict(
            id=accepted["job_id"],
            kind="run",
            created=row["created"],
            payload=f.storage.calls[2].digest,
            status="queued",
            owner=None,
            lease_until=None,
            cancel=0,
            budget=f.intent.budget_microusd,
            reserved=0,
            result=None,
            error=None,
            actor=f.principal.principal_id,
            payload_version=2,
            execution_config_ref=f.config.digest,
            execution_config_digest=f.config.digest,
        )
        assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert c.exec_driver_sql(
            "SELECT action,target FROM audit ORDER BY created DESC LIMIT 1"
        ).one() == ("job.create", accepted["job_id"])
    for descriptor, expected in zip(
        f.storage.calls, (f.intent.task_bytes, f.config.canonical_bytes, None), strict=True
    ):
        data = f.storage.local.read_verified(descriptor)
        if expected is not None:
            assert data == expected
        else:
            assert json.loads(data)["execution_config_digest"] == f.config.digest
    with f.journal.open(identity(f)) as session:
        assert session.states[0].commit_status == "CONFIRMED"
        assert session.states[0].write_requests == 3
        assert session.snapshot.data()["operation_id"] == accepted["operation_id"]

    def forbidden(*args, **kwargs):
        pytest.fail("SQL winner invoked new-work dependency")

    for target, name in (
        (f.policy, "require_available"),
        (f.ready, "check"),
        (f.storage, "put_verified"),
        (f.journal, "open"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    monkeypatch.setattr(NativeRegistry, "resolve_new", forbidden)
    assert submit(f, origin=OriginCorrelation("9" * 32)) == accepted
    assert snapshot(f) == after


def test_default_unavailable_policy_precedes_new_intents_and_readiness(publication):
    f = publication
    f.service = AdmissionCoordinator(
        f.engine,
        f.authority,
        journal=f.journal,
        storage=f.storage,
        registry=f.registry,
        readiness=f.ready,
    )
    f.service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
    before = snapshot(f)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    assert not list(f.root.rglob("*.json")) and not f.storage.calls and f.ready.calls == 0
    assert snapshot(f) == before


@pytest.mark.parametrize("with_journal", [False, True])
def test_default_policy_suppresses_callers_private_exception_context(publication, with_journal):
    f = publication
    f.service = AdmissionCoordinator(
        f.engine,
        f.authority,
        journal=f.journal if with_journal else None,
        storage=f.storage,
        registry=f.registry,
        readiness=f.ready,
    )
    f.service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
    before = snapshot(f)
    private = "private-caller-correlation-canary"
    try:
        raise RuntimeError(private)
    except RuntimeError:
        with pytest.raises(AdmissionError, match="^dependency_unavailable$") as caught:
            submit(f)
    assert caught.value.__suppress_context__ is True
    assert caught.value.__cause__ is None
    assert private not in "".join(traceback.format_exception(caught.value))
    assert snapshot(f) == before and f.engine.pool.checkedout() == 0
    assert not list(f.root.rglob("*.json")) and not f.storage.calls and f.ready.calls == 0


@pytest.mark.parametrize("with_journal", [False, True])
@pytest.mark.parametrize(
    "code",
    [
        "invalid_request",
        "idempotency_conflict",
        "dependency_unavailable",
        "schema_incompatible",
        "outcome_uncertain",
    ],
)
def test_policy_failure_suppresses_private_cause_without_reclassification(
    publication, monkeypatch, code, with_journal
):
    f = publication
    if not with_journal:
        f.service.journal = None
    before = snapshot(f)
    private = "private-policy-endpoint-canary"
    failure = AdmissionError(code)

    def unavailable():
        try:
            raise RuntimeError(private)
        except RuntimeError as cause:
            raise failure from cause

    monkeypatch.setattr(f.policy, "require_available", unavailable)
    with pytest.raises(AdmissionError, match="^" + code + "$") as caught:
        submit(f)
    assert caught.value is failure and caught.value.code == code
    assert caught.value.__suppress_context__ is True
    assert caught.value.__cause__ is None
    assert private not in "".join(traceback.format_exception(caught.value))
    assert snapshot(f) == before and f.engine.pool.checkedout() == 0
    assert not list(f.root.rglob("*.json")) and not f.storage.calls and f.ready.calls == 0


@pytest.mark.parametrize(
    "permission", [None, "fixture-processor", ProcessorPermission("0" * 64, "fixture-processor")]
)
def test_untrusted_or_wrong_configuration_permission_refuses_before_registry(
    publication, monkeypatch, permission
):
    f = publication
    monkeypatch.setattr(f.policy, "permission", lambda *_: permission)
    monkeypatch.setattr(
        NativeRegistry, "resolve_new", lambda *_a, **_k: pytest.fail("registry before permission")
    )
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    assert not f.storage.calls and not list(f.root.glob("*/00000000.json"))


@pytest.mark.parametrize(
    "result", [True, False, None, AdmissionReady(False), AdmissionReady(1), "coroutine"]
)
def test_readiness_requires_exact_synchronous_ready_result(publication, monkeypatch, result):
    async def async_ready():
        pytest.fail("coroutine must never run")

    f = publication
    monkeypatch.setattr(
        f.ready, "check", lambda *_: async_ready() if result == "coroutine" else result
    )
    before = snapshot(f)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    assert not f.storage.calls and snapshot(f) == before


def test_unfinished_upload_resumes_frozen_configuration_origin_and_unknown_work(
    publication, monkeypatch
):
    f = publication

    def interrupted(*args):
        f.storage.after = None
        raise RuntimeError("PRIVATE-UPLOAD-CANARY")

    f.storage.after = interrupted
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    f.service.registry = None
    monkeypatch.setattr(f.policy, "permission", lambda *_: pytest.fail("new permission on resume"))
    monkeypatch.setattr(f.policy, "prepare", lambda *_: pytest.fail("new evidence on resume"))
    result = submit(f, origin=OriginCorrelation("9" * 32))
    with f.journal.open(identity(f)) as session:
        assert session.origin == f.origin and session.states[0].unknown_work
        assert session.states[0].commit_status == "CONFIRMED"
        assert session.snapshot.data()["job_id"] == result["job_id"]
    assert len(f.storage.calls) == 4


@pytest.mark.parametrize("change", ["policy", "membership"])
def test_current_policy_and_authority_rechecked_after_storage(publication, change):
    f = publication
    before = snapshot(f)

    def changed(*args):
        f.storage.after = None
        with f.engine.begin() as c:
            c.exec_driver_sql(
                "UPDATE projects SET name='changed'"
                if change == "policy"
                else "UPDATE project_memberships SET revoked_at='2026-01-01'"
            )

    f.storage.after = changed
    with pytest.raises(AdmissionError if change == "policy" else ResourceNotFound):
        submit(f)
    after = snapshot(f)
    assert after == before and len(f.storage.calls) == 1


@pytest.mark.parametrize(
    "stage,number",
    [
        ("INSERT INTO jobs", 1),
        ("INSERT INTO resource_scopes", 1),
        ("INSERT INTO artifact_objects", 1),
        ("INSERT INTO artifact_objects", 2),
        ("INSERT INTO artifact_objects", 3),
        ("INSERT INTO artifact_refs", 1),
        ("INSERT INTO artifact_refs", 2),
        ("INSERT INTO artifact_refs", 3),
        ("INSERT INTO operations", 1),
        ("INSERT INTO operation_keys", 1),
        ("INSERT INTO audit", 1),
    ],
)
def test_each_real_publication_sql_stage_rolls_back_together(publication, stage, number):
    f, seen = publication, []
    before = snapshot(f)

    def fault(_c, _cursor, statement, _params, _context, _many):
        if statement.strip().startswith(stage):
            seen.append(statement)
            if len(seen) == number:
                raise RuntimeError("PRIVATE-SQL-STAGE")

    event.listen(f.engine, "after_cursor_execute", fault)
    try:
        with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
            submit(f)
    finally:
        event.remove(f.engine, "after_cursor_execute", fault)
    assert len(seen) == number and snapshot(f) == before
    count = len(f.storage.calls)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)
    assert len(f.storage.calls) == count  # Durable pending never restarts new work.


def test_actual_commit_ack_loss_recovers_exact_original_without_reupload(publication, monkeypatch):
    f, published = publication, [False]
    original_commit = Connection.commit

    def stage(_c, _cursor, statement, *_):
        if statement.startswith("INSERT INTO audit"):
            published[0] = True

    def lost(connection):
        original_commit(connection)
        if published[0]:
            published[0] = False
            raise RuntimeError("PRIVATE-ACK")

    event.listen(f.engine, "after_cursor_execute", stage)
    monkeypatch.setattr(Connection, "commit", lost)
    try:
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            submit(f)
    finally:
        event.remove(f.engine, "after_cursor_execute", stage)
    with f.engine.connect() as c:
        expected = dict(
            c.exec_driver_sql("SELECT id AS operation_id,job_id FROM operations").mappings().one()
        )
    assert submit(f) == expected and len(f.storage.calls) == 3


def test_acknowledged_commit_journal_failure_is_not_retryable(publication, monkeypatch):
    f = publication
    append = JournalSession.append

    def broken(session, kind, data):
        if kind == "commit_confirmed":
            raise OSError("PRIVATE-FSYNC")
        return append(session, kind, data)

    monkeypatch.setattr(JournalSession, "append", broken)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)
    assert submit(f) and len(f.storage.calls) == 3


def test_pending_restart_never_uses_current_new_work_adapters(publication, monkeypatch):
    f = publication

    def stop(*args, **kwargs):
        raise SystemExit("synthetic interrupt before publication SQL")

    monkeypatch.setattr(admission_coordinator, "publish_rows", stop)
    before = snapshot(f)
    with pytest.raises(SystemExit):
        submit(f)
    assert snapshot(f) == before
    f.service.registry = f.service.storage = f.service.readiness = None
    monkeypatch.setattr(
        f.policy, "require_available", lambda: pytest.fail("pending calls new adapter")
    )
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)


@pytest.mark.parametrize("second", [False, True])
def test_real_shared_metadata_collision_reverifies_one_linked_attempt(publication, second):
    f = publication
    injected = []

    def race(*args):
        count = len(f.storage.calls)
        if count == 3 or (second and count == 6):
            original = f.storage.calls[0 if count == 3 else 4]
            winner = replace(original, id=("e" if count == 3 else "f") * 32)
            with f.engine.begin() as c:
                record_verified(c, winner)
            injected.append(winner)

    f.storage.after = race
    if second:
        with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
            submit(f)
        with f.engine.connect() as c:
            assert c.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0
    else:
        assert submit(f)
    assert len(f.storage.calls) == 6
    assert f.storage.calls[3] == injected[0] and f.storage.calls[0] != injected[0]
    with f.journal.open(identity(f)) as session:
        assert len(session.states) == 2 and session.route == "reconcile"
        assert sum(s.logical_writes for s in session.states) == 6
        assert session.states[-1].commit_status == ("PENDING" if second else "CONFIRMED")
        assert session.snapshot.data()["predecessor"]["collision"]["winner"]["id"] == injected[0].id


def test_late_sql_winner_does_not_confirm_abandoned_intended_ids(publication):
    f = publication
    expected = []

    def race(*args):
        if len(f.storage.calls) == 3:
            value, payload = fixtures.prepared()
            with fixtures.transaction(f.engine) as c:
                fixtures.config_refs(c, value, payload)
                repo = AdmissionRepository(f.authority)
                stored = repo.insert_operation(
                    c,
                    f.principal,
                    f.context,
                    operation_id=fixtures.OPERATION,
                    prepared=value,
                    payload_binding=payload,
                    created_at=fixtures.CREATED,
                    retain_until=fixtures.UNTIL,
                )
                repo.bind_alias(
                    c,
                    f.principal,
                    f.context,
                    operation_id=stored.id,
                    key_hash=fixtures.KEY,
                    request_digest=f.intent.request_digest,
                )
                expected.append(stored.accepted_response)

    f.storage.after = race
    assert submit(f) == expected[0]
    with f.journal.open(identity(f)) as session:
        assert session.states[0].commit_status == "PENDING"
        assert session.snapshot.data()["job_id"] != expected[0]["job_id"]


@pytest.mark.parametrize("change", ["scope", "config", "unknown", "oversize"])
def test_invalid_policy_evidence_is_dependency_before_child_or_upload(
    publication, monkeypatch, change
):
    f = publication
    prepare = f.policy.prepare

    def malformed(*args):
        evidence = prepare(*args)
        if change == "scope":
            evidence["project_id"] = "0" * 32
        elif change == "config":
            evidence["configuration_digest"] = "0" * 64
        elif change == "unknown":
            evidence["unrecognized"] = "PRIVATE"
        else:
            evidence["state"] = {"value": "x" * (16 * 1024)}
        return evidence

    monkeypatch.setattr(f.policy, "prepare", malformed)
    before = snapshot(f)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    assert snapshot(f) == before and not f.storage.calls and not f.ready.calls
    assert all(not (f.root / child / "intent.json").exists() for child in identity(f).children)


@pytest.mark.parametrize("change", ["object", "counter"])
def test_invalid_returned_receipt_preserves_unknown_work_and_no_sql(
    publication, monkeypatch, change
):
    f = publication
    original = f.storage.put_verified

    def invalid(*args):
        receipt = original(*args)
        return (
            replace(receipt, object=replace(receipt.object, id="0" * 32))
            if change == "object"
            else replace(receipt, write_requests=-1)
        )

    monkeypatch.setattr(f.storage, "put_verified", invalid)
    before = snapshot(f)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f)
    assert snapshot(f) == before
    with f.journal.open(identity(f)) as session:
        assert session.route == "resume" and session.states[0].unknown_work
    monkeypatch.setattr(f.storage, "put_verified", original)
    assert submit(f) and len(f.storage.calls) == 4


def test_actual_schema_guard_precedes_all_new_work_dependencies(publication):
    f = publication
    f.service = AdmissionCoordinator(
        f.engine,
        f.authority,
        policy=f.policy,
        readiness=f.ready,
        registry=f.registry,
        journal=f.journal,
        storage=f.storage,
    )
    with pytest.raises(AdmissionError, match="^schema_incompatible$"):
        submit(f)
    assert f.policy.calls == [] and not f.ready.calls and not f.storage.calls
    assert list(f.root.iterdir()) == []


@pytest.mark.parametrize("denied", [False, True])
def test_new_commit_disclosure_failure_cannot_become_retryable(publication, monkeypatch, denied):
    f = publication
    original = f.service._disclose

    def fail(*args):
        if denied:
            with f.engine.begin() as c:
                c.exec_driver_sql("UPDATE project_memberships SET revoked_at='2026-01-01'")
            return original(*args)
        raise AdmissionError("dependency_unavailable")

    monkeypatch.setattr(f.service, "_disclose", fail)
    with pytest.raises(ResourceNotFound if denied else AdmissionError) as caught:
        submit(f)
    if not denied:
        assert caught.value.code == "outcome_uncertain"
    with f.engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
        assert (
            c.exec_driver_sql("SELECT count(*) FROM audit WHERE action='job.create'").scalar_one()
            == 1
        )


@pytest.mark.parametrize("denied", [False, True])
def test_journal_close_failure_preserves_commit_uncertainty_or_typed_denial(
    publication, monkeypatch, denied
):
    f = publication
    original_open = f.journal._journal.open

    @contextmanager
    def bad_close(*args, **kwargs):
        with original_open(*args, **kwargs) as session:
            try:
                yield session
            finally:
                raise OSError("PRIVATE_CLOSE")

    monkeypatch.setattr(f.journal._journal, "open", bad_close)
    if denied:
        original_disclose = f.service._disclose

        def revoke(*args):
            with f.engine.begin() as connection:
                connection.exec_driver_sql("UPDATE project_memberships SET revoked_at='2026-01-01'")
            return original_disclose(*args)

        monkeypatch.setattr(f.service, "_disclose", revoke)
    with pytest.raises(ResourceNotFound if denied else AdmissionError) as caught:
        submit(f)
    if not denied:
        assert caught.value.code == "outcome_uncertain"
    assert "PRIVATE" not in str(caught.value)
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM audit WHERE action='job.create'"
            ).scalar_one()
            == 1
        )
    assert f.engine.pool.checkedout() == 0


def freeze_pending(f, monkeypatch):
    original = admission_coordinator.publish_rows

    def interrupted(*args, **kwargs):
        raise SystemExit("before publication")

    monkeypatch.setattr(admission_coordinator, "publish_rows", interrupted)
    with pytest.raises(SystemExit):
        submit(f)
    monkeypatch.setattr(admission_coordinator, "publish_rows", original)
    with f.journal.open(identity(f)) as session:
        assert session.route == "reconcile" and session.states[0].commit_pending
    return snapshot(f)


@pytest.mark.parametrize("failure", ["schema", "connect", "read", "second_read"])
def test_pending_submit_sql_unavailability_is_uncertain_before_new_work(
    publication, monkeypatch, failure
):
    f = publication
    before = freeze_pending(f, monkeypatch)
    calls = len(f.storage.calls)
    journal_before = {
        p.relative_to(f.root): p.read_bytes() for p in f.root.rglob("*") if p.is_file()
    }
    opened = []
    original_open, original_recover = f.journal.open, f.service._recover
    lookups = []

    def observed_open(*args, **kwargs):
        opened.append(True)
        return original_open(*args, **kwargs)

    def observed_recover(*args, **kwargs):
        lookups.append(True)
        return original_recover(*args, **kwargs)

    def denied_read(_connection, _cursor, statement, *_):
        if "FROM operations" in statement and (failure == "read" or len(lookups) == 2):
            raise RuntimeError("PRIVATE-DATABASE")

    def unavailable(*args, **kwargs):
        raise RuntimeError("PRIVATE-CONNECT")

    def forbidden(*args, **kwargs):
        pytest.fail("Unproven SQL absence reached a new-work dependency")

    with monkeypatch.context() as patch:
        patch.setattr(f.journal, "open", observed_open)
        patch.setattr(f.service, "_recover", observed_recover)
        for target, name in (
            (f.policy, "require_available"),
            (f.ready, "check"),
            (f.storage, "put_verified"),
        ):
            patch.setattr(target, name, forbidden)
        if failure == "schema":
            patch.setattr(
                f.service,
                "schema_compatibility",
                lambda: CompatibilityResult("unavailable", "schema_unavailable"),
            )
        elif failure == "connect":
            patch.setattr(f.engine, "connect", unavailable)
        else:
            event.listen(f.engine, "before_cursor_execute", denied_read)
        try:
            with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
                submit(f)
        finally:
            if failure in {"read", "second_read"}:
                event.remove(f.engine, "before_cursor_execute", denied_read)
    assert len(opened) == (1 if failure == "second_read" else 0)
    assert len(f.storage.calls) == calls and snapshot(f) == before
    assert {
        p.relative_to(f.root): p.read_bytes() for p in f.root.rglob("*") if p.is_file()
    } == journal_before
    assert f.engine.pool.checkedout() == 0


@pytest.mark.parametrize("denial", ["identity", "scope", "action", "schema"])
def test_pending_submit_preserves_typed_denial_and_explicit_schema_refusal(
    publication, monkeypatch, denial
):
    f = publication
    freeze_pending(f, monkeypatch)
    expected = dict(
        identity=IdentityInvalid,
        scope=ResourceNotFound,
        action=ActionForbidden,
        schema=AdmissionError,
    )[denial]
    if denial in {"scope", "action"}:
        with f.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE project_memberships SET revoked_at='2026-01-01'"
                if denial == "scope"
                else "UPDATE project_memberships SET role='viewer'"
            )
    elif denial == "schema":
        monkeypatch.setattr(
            f.service,
            "schema_compatibility",
            lambda: CompatibilityResult("incompatible", "migration_only"),
        )
    before = snapshot(f)

    def forbidden(*args, **kwargs):
        pytest.fail("Denied submit reached journal or new work")

    monkeypatch.setattr(f.journal, "open", forbidden)
    monkeypatch.setattr(f.policy, "require_available", forbidden)
    with pytest.raises(expected) as caught:
        submit(f, **({"principal": None} if denial == "identity" else {}))
    if denial == "schema":
        assert caught.value.code == "schema_incompatible"
    assert snapshot(f) == before and len(f.storage.calls) == 3 and f.ready.calls == 1


@pytest.mark.parametrize(
    "variant", ["new-client", "new-key", "changed-body", "one-sided", "truncated", "busy"]
)
def test_unresolved_locators_never_authorize_new_preparation(publication, monkeypatch, variant):
    f = publication
    before = freeze_pending(f, monkeypatch)
    arguments = {}
    if variant in {"new-client", "changed-body"}:
        changed = json.loads(f.intent.canonical_bytes)
        if variant == "new-client":
            changed["client_operation_id"] = "b" * 32
        else:
            changed["task"]["files"]["main.py"] += " "
        arguments["intent"] = parse_submit(canonical(changed))
    elif variant == "new-key":
        arguments["key_hash"] = "8" * 64
    elif variant == "one-sided":
        (f.root / sorted(identity(f).locators)[0] / "intent.json").unlink()
    elif variant == "truncated":
        (f.root / identity(f).children[0] / "intent.json").write_bytes(b"{")

    def records():
        return {p.relative_to(f.root): p.read_bytes() for p in f.root.rglob("*.json")}

    retained = records()

    def forbidden(*args, **kwargs):
        pytest.fail("Unresolved journal authorized preparation or mutation")

    held = f.journal.open(identity(f)) if variant == "busy" else nullcontext()
    with held:
        for target, name in (
            (f.policy, "require_available"),
            (f.ready, "check"),
            (f.storage, "put_verified"),
            (f.service.repository, "bind_alias"),
            (NativeRegistry, "resolve_new"),
            (JournalSession, "freeze"),
            (admission_coordinator, "publish_rows"),
        ):
            monkeypatch.setattr(target, name, forbidden)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            submit(f, **arguments)
    assert snapshot(f) == before and records() == retained
    assert len(f.storage.calls) == 3 and f.ready.calls == 1
    assert f.engine.pool.checkedout() == 0


@pytest.mark.parametrize("persisted", [False, True])
def test_pending_append_failure_cannot_publish_and_reload_obeys_actual_history(
    publication, monkeypatch, persisted
):
    f = publication
    before = snapshot(f)
    append, publish = JournalSession.append, admission_coordinator.publish_rows
    publications = []

    def failed_append(session, kind, data):
        if kind == "commit_pending":
            if persisted:
                append(session, kind, data)  # Actual append and fsync completed.
            raise OSError("PRIVATE-PENDING")
        return append(session, kind, data)

    def observed_publish(*args, **kwargs):
        publications.append(True)
        return publish(*args, **kwargs)

    monkeypatch.setattr(JournalSession, "append", failed_append)
    monkeypatch.setattr(admission_coordinator, "publish_rows", observed_publish)
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)
    assert snapshot(f) == before and not publications and len(f.storage.calls) == 3
    monkeypatch.setattr(JournalSession, "append", append)
    with f.journal.open(identity(f)) as session:
        proposed = session.snapshot.data()
        assert session.route == ("reconcile" if persisted else "resume")
        assert session.states[0].commit_pending is persisted
    if persisted:

        def forbidden(*args, **kwargs):
            pytest.fail("Durable pending resumed external work")

        monkeypatch.setattr(f.policy, "require_available", forbidden)
        monkeypatch.setattr(f.storage, "put_verified", forbidden)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            submit(f)
        assert not publications and len(f.storage.calls) == 3 and snapshot(f) == before
    else:
        accepted = submit(f)
        assert accepted == {"operation_id": proposed["operation_id"], "job_id": proposed["job_id"]}
        assert len(publications) == 1 and len(f.storage.calls) == 6
        with f.journal.open(identity(f)) as session:
            assert session.states[0].commit_status == "CONFIRMED"
            assert session.states[0].logical_writes == 6
            assert session.states[0].write_requests == 3
            # Three initial miss+verification pairs, then three cache-hit reads.
            assert session.states[0].read_requests == 9


def test_full_accepted_task_publishes_encrypted_with_bounded_journal(publication):
    f = publication
    f.intent = parse_submit(canonical(at_task_size(MAX_TASK_BYTES)))
    assert len(f.intent.task_bytes) == MAX_TASK_BYTES
    maximum = json.loads(f.config.canonical_bytes)
    for field in (
        "endpoint_profile",
        "endpoint_revision",
        "model_revision",
        "processor_profile",
        "price_version",
    ):
        maximum[field] = "p" * 128
    maximum.update(
        max_input_tokens=1000000,
        max_output_tokens=128000,
        input_microusd_per_million_tokens=2**63 - 1,
        output_microusd_per_million_tokens=2**63 - 1,
        reasoning_effort="minimal",
    )
    encoded = canonical(maximum)
    # The strict native-v1 fields cannot fill 64 KiB. Preserve their real maxima;
    # the existing preparse/overflow tests separately cover the outer byte cap.
    assert len(encoded) < MAX_CONFIG_BYTES
    f.config = NativeConfiguration(encoded, expected_digest=hashlib.sha256(encoded).hexdigest())
    f.registry = f.service.registry = NativeRegistry(f.config, ["fixture-image"])
    accepted = submit(f)
    assert len(f.storage.calls) == 3
    task = f.storage.calls[0]
    assert task.byte_count == MAX_TASK_BYTES
    assert f.storage.local.read_verified(task) == f.intent.task_bytes
    assert f.storage.local.read_verified(f.storage.calls[1]) == encoded
    with f.journal.open(identity(f)) as session:
        frozen = session.snapshot.data()
        assert len(session.snapshot.encoded) <= MAX_CHILD_BYTES
        assert frozen["job_id"] == accepted["job_id"]
        assert frozen["task_digest"] == f.intent.task_digest
        assert frozen["configuration"] == maximum
        assert "task_plaintext" not in frozen and "files" not in frozen
        assert session.states[0].commit_status == "CONFIRMED"
        assert session.states[0].logical_writes == 3


def test_parsed_default_equivalence_replays_but_source_whitespace_conflicts(
    publication, monkeypatch
):
    f = publication
    accepted = submit(f)
    explicit_defaults = parse_submit(canonical(json.loads(f.intent.canonical_bytes)))
    assert explicit_defaults == f.intent

    def forbidden(*args, **kwargs):
        pytest.fail("Canonical replay or conflict invoked new work")

    f.service.registry = f.service.readiness = f.service.storage = None
    monkeypatch.setattr(f.policy, "require_available", forbidden)
    monkeypatch.setattr(f.journal, "open", forbidden)
    assert (
        submit(f, intent=explicit_defaults, key_hash="8" * 64, origin=OriginCorrelation("9" * 32))
        == accepted
    )
    after_alias = snapshot(f)
    assert len(after_alias["operation_keys"]) == 2 and len(after_alias["operations"]) == 1
    changed = json.loads(f.intent.canonical_bytes)
    changed["task"]["files"]["main.py"] += " "
    different_source = parse_submit(canonical(changed))
    assert different_source.request_digest != f.intent.request_digest
    with pytest.raises(AdmissionError, match="^idempotency_conflict$"):
        submit(f, intent=different_source, key_hash="9" * 64)
    assert snapshot(f) == after_alias and len(f.storage.calls) == 3
    with f.engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM audit WHERE action='job.create'"
            ).scalar_one()
            == 1
        )
