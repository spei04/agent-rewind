"""Real PostgreSQL new-admission publication and process-death evidence.

Only the opt-in disposable ar6 fixture is used. Adapters are explicit synthetic
permission/readiness producers; the real customer profile stays migration-only.
Storage and journals are real private local files, never fake upload receipts.
"""

import json
import os
import re
import selectors
import signal
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event, Lock, local
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migrations
from cryptography.fernet import Fernet
from postgres_control import wait_for_database_drain
from psycopg.pq import TransactionStatus
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool
from test_admission_configuration import configuration
from test_admission_repository import KEY, PRINCIPAL, PROJECT
from test_admission_request import submission
from test_artifact_postgres import prepare_postgres
from test_scoped_actions_postgres import wait_blocked

from agent_rewind import admission_coordinator
from agent_rewind.admission_adapters import AdmissionReady, ProcessorPermission
from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_journal import AdmissionJournal, AdmissionJournalSession
from agent_rewind.admission_journal_state import JournalIdentity, metadata
from agent_rewind.admission_request import MAX_TASK_BYTES, parse_submit
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import record_verified
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.models import canonical
from agent_rewind.publication_journal import JournalSession
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL new admission publication"
)
TABLES = (
    "jobs",
    "resource_scopes",
    "artifact_objects",
    "artifact_refs",
    "operations",
    "operation_keys",
    "audit",
)
STAGES = [
    ("jobs", 1),
    ("resource_scopes", 1),
    ("artifact_objects", 1),
    ("artifact_objects", 2),
    ("artifact_objects", 3),
    ("artifact_refs", 1),
    ("artifact_refs", 2),
    ("artifact_refs", 3),
    ("operations", 1),
    ("operation_keys", 1),
    ("audit", 1),
]


class Policy:
    """Synthetic SQL policy version changed under the same project exclusion."""

    def __init__(self, f):
        self.f = f
        self.calls = []

    def require_available(self):
        self.f.outside()
        self.calls.append("available")

    def permission(self, principal, context, intent, candidate):
        self.f.outside()
        assert candidate == self.f.config
        self.calls.append("permission")
        return ProcessorPermission(candidate.digest, candidate.processor_profile)

    def prepare(self, principal, context, intent, config):
        self.f.outside()
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
            version="synthetic-project-exclusion-v1",
            state={"project_name": self.f.name},
        )

    def recheck(self, connection, principal, context, intent, config, evidence):
        assert connection.engine is self.f.engine and connection.in_transaction()
        assert getattr(self.f.active, "depth", 0) == 1
        assert connection.connection.driver_connection.info.transaction_status == (
            TransactionStatus.INTRANS
        )
        self.calls.append("recheck")
        name = connection.execute(
            text("SELECT name FROM projects WHERE id=:id"), {"id": context.project_id}
        ).scalar_one()
        if (
            name != evidence["state"]["project_name"]
            or evidence["configuration_digest"] != config.digest
        ):
            raise AdmissionError("dependency_unavailable")


class Ready:
    def __init__(self, f):
        self.f, self.calls = f, 0

    def check(self, *args):
        self.f.outside()
        self.calls += 1
        return AdmissionReady(True)


class Storage:
    def __init__(self, f, root, key):
        self.f, self.calls, self.after, self.lock = f, [], None, Lock()
        self.local = LocalArtifactStorage(root, Fernet(key), plaintext_limit=MAX_TASK_BYTES)

    def put_verified(self, descriptor, content):
        self.f.outside()
        result = self.local.put_verified(descriptor, content)
        with self.lock:
            self.calls.append(descriptor)
        if self.after is not None:
            self.after(descriptor, content)
        return result


def runtime(engine, *, principal, context, name, root, objects, key):
    """Reusable by the real child process; this adds no SQL or permission grant."""
    f = SimpleNamespace(
        engine=engine,
        principal=principal,
        context=context,
        name=name,
        root=root,
        objects=objects,
        key=key,
        config=configuration(),
        active=local(),
    )

    def checkout(*args):
        f.active.depth = getattr(f.active, "depth", 0) + 1

    def checkin(*args):
        f.active.depth -= 1
        assert f.active.depth == 0

    def outside():
        # Per-request/thread, not a global pool count that forbids other writers.
        assert getattr(f.active, "depth", 0) == 0

    f.outside = outside
    f.listeners = (("checkout", checkout), ("checkin", checkin))
    for name_, callback in f.listeners:
        event.listen(engine, name_, callback)
    for directory in (root, objects):
        directory.mkdir(mode=0o700, exist_ok=True)
        assert directory.stat().st_mode & 0o777 == 0o700
    f.authority = RequestAuthority(engine)
    f.intent = parse_submit(canonical(submission()))
    f.origin = OriginCorrelation("6" * 32)
    f.policy, f.ready = Policy(f), Ready(f)
    f.storage = Storage(f, objects, key)
    f.journal = AdmissionJournal(root)
    f.registry = NativeRegistry(f.config, ["fixture-image"])
    f.service = AdmissionCoordinator(
        engine,
        f.authority,
        policy=f.policy,
        readiness=f.ready,
        registry=f.registry,
        storage=f.storage,
        journal=f.journal,
    )
    # Per-instance synthetic admission only; a separate test exercises real refusal.
    f.service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
    return f


@pytest.fixture
def publication_pg(pg, tmp_path, monkeypatch):
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    initialize_projection(pg["owner"])
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    initialize_admission(pg["owner"])
    role = pg["app_role"]
    assert re.fullmatch(r"ar_migration_[0-9a-f]{32}_app", role)
    with pg["owner"].begin() as c:
        c.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": PRINCIPAL},
        )
        name = c.execute(text("SELECT name FROM projects WHERE id=:p"), {"p": PROJECT}).scalar_one()
        for table in (
            "projects",
            "organizations",
            "project_memberships",
            "resource_scopes",
            "api_keys",
            "jobs",
            # Fresh job authorization discovers associated records even when empty.
            "records",
            "artifact_objects",
            "artifact_refs",
            "operations",
            "operation_keys",
        ):
            c.exec_driver_sql(f"GRANT SELECT ON {table} TO {role}")
        for table, column in (
            ("projects", "id"),
            ("organizations", "id"),
            ("project_memberships", "principal_id"),
            ("resource_scopes", "resource_id"),
            ("api_keys", "id"),
            ("jobs", "id"),
        ):
            c.exec_driver_sql(f"GRANT UPDATE({column}) ON {table} TO {role}")
        for table in TABLES:
            c.exec_driver_sql(f"GRANT INSERT ON {table} TO {role}")
    engine = create_engine(
        pg["app"].url,
        pool_size=12,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"options": "-c statement_timeout=7000 -c lock_timeout=900"},
    )
    principal = VerifiedPrincipal(PRINCIPAL)
    context = RequestAuthority(engine).named(principal, PROJECT).context
    f = runtime(
        engine,
        principal=principal,
        context=context,
        name=name,
        root=tmp_path / "journal",
        objects=tmp_path / "objects",
        key=Fernet.generate_key(),
    )
    f.owner, f.pg = pg["owner"], pg
    for method in ("freeze", "append"):
        original = getattr(JournalSession, method)

        def outside(session, *args, _original=original, **kwargs):
            f.outside()
            return _original(session, *args, **kwargs)

        monkeypatch.setattr(JournalSession, method, outside)
    initial = snapshot(f)
    assert not any(initial[table] for table in TABLES if table != "resource_scopes")
    assert not any(row["resource_kind"] == "job" for row in initial["resource_scopes"])
    try:
        yield f
    finally:
        assert engine.pool.checkedout() == 0
        for name_, callback in f.listeners:
            event.remove(engine, name_, callback)
        engine.dispose()


def submit(f, **overrides):
    args = dict(
        principal=f.principal,
        original_context=f.context,
        intent=f.intent,
        key_hash=KEY,
        origin=f.origin,
    )
    args.update(overrides)
    return f.service.submit(**args)


def reconcile(f):
    return f.service.reconcile(
        f.principal, f.context, f.intent.client_operation_id, KEY, f.intent.request_digest
    )


def identity(f):
    return JournalIdentity(
        f.context.organization_id,
        f.context.project_id,
        f.principal.principal_id,
        f.intent.client_operation_id,
        KEY,
        f.intent.request_digest,
    )


def snapshot(f):
    with f.owner.connect() as c:
        return {
            name: [
                dict(row)
                for row in c.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1,2").mappings()
            ]
            for name in TABLES
        }


def safe_failure(caught, code):
    assert caught.value.code == code and str(caught.value) == code
    assert caught.value.__suppress_context__
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


def clean_pool(f):
    assert f.engine.pool.checkedout() == 0
    with f.engine.connect() as c:
        raw = c.connection.driver_connection
        assert raw.info.transaction_status == TransactionStatus.IDLE and not raw.autocommit
        assert c.exec_driver_sql(
            "SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),"
            "current_setting('transaction_read_only'),current_setting('transaction_isolation')"
        ).one() == ("7s", "900ms", "off", "read committed")
    assert raw.info.transaction_status == TransactionStatus.IDLE
    assert f.engine.pool.checkedout() == 0


def assert_publication(f, accepted):
    rows = snapshot(f)
    assert len(rows["jobs"]) == len(rows["operations"]) == len(rows["operation_keys"]) == 1
    assert len(rows["artifact_refs"]) == len(rows["artifact_objects"]) == 3
    assert len(rows["audit"]) == 1
    job = rows["jobs"][0]
    assert set(job) == {
        "id",
        "kind",
        "created",
        "payload",
        "status",
        "owner",
        "lease_until",
        "cancel",
        "budget",
        "reserved",
        "result",
        "error",
        "actor",
        "payload_version",
        "execution_config_ref",
        "execution_config_digest",
    }
    assert job == dict(
        id=accepted["job_id"],
        kind="run",
        created=job["created"],
        payload=job["payload"],
        status="queued",
        owner=None,
        lease_until=None,
        cancel=False,
        budget=f.intent.budget_microusd,
        reserved=0,
        result=None,
        error=None,
        actor=f.principal.principal_id,
        payload_version=2,
        execution_config_ref=f.config.digest,
        execution_config_digest=f.config.digest,
    )
    assert job["cancel"] is False and type(job["budget"]) is int
    op = rows["operations"][0]
    assert op["id"] == accepted["operation_id"] and op["job_id"] == accepted["job_id"]
    assert op["accepted_response"] == canonical(accepted).decode("utf-8")
    assert op["failure_correlation_id"] == f.origin.correlation_id
    assert op["execution_config_digest"] == f.config.digest and op["payload_version"] == 2
    assert op["created_at"].utcoffset() == timedelta(0)
    assert op["retain_until"] - op["created_at"] >= timedelta(days=90)
    assert rows["audit"][0]["action"] == "job.create"
    assert rows["audit"][0]["target"] == job["id"]
    assert {r["role"] for r in rows["artifact_refs"]} == {"task", "admission_config", "payload"}
    assert all(
        r["project_id"] == PROJECT and r["owner_id"] == job["id"] for r in rows["artifact_refs"]
    )
    return rows


def poison_new_work(f, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Original SQL identity invoked a new-work dependency")

    for target, method in (
        (f.policy, "require_available"),
        (f.policy, "permission"),
        (f.policy, "prepare"),
        (f.ready, "check"),
        (f.storage, "put_verified"),
        (f.journal, "open"),
    ):
        monkeypatch.setattr(target, method, forbidden)
    monkeypatch.setattr(NativeRegistry, "resolve_new", forbidden)


def test_postgres_new_work_real_guard_and_default_policy_refuse_before_side_effects(publication_pg):
    f = publication_pg
    before = snapshot(f)
    # The restricted publication role intentionally cannot inspect alembic_version.
    # Use the existing schema-capable owner for this real guard observation only.
    real = AdmissionCoordinator(f.owner, RequestAuthority(f.owner))
    observed = real.schema_compatibility()
    assert (observed.status, observed.code) == ("incompatible", "migration_only")
    with pytest.raises(AdmissionError, match="^schema_incompatible$"):
        real.submit(f.principal, f.context, f.intent, KEY, f.origin)
    unavailable = AdmissionCoordinator(
        f.engine,
        f.authority,
        readiness=f.ready,
        journal=f.journal,
        registry=f.registry,
        storage=f.storage,
    )
    unavailable.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        unavailable.submit(f.principal, f.context, f.intent, KEY, f.origin)
    assert not f.storage.calls and not f.ready.calls and snapshot(f) == before
    assert not list(f.root.rglob("intent.json"))


def test_postgres_real_publication_exact_columns_privileges_and_replay(publication_pg, monkeypatch):
    f = publication_pg
    with f.engine.connect() as c:
        assert (
            c.exec_driver_sql(
                "SELECT has_table_privilege(current_user,'records','SELECT')"
            ).scalar_one()
            is True
        )
        assert (
            c.exec_driver_sql(
                "SELECT has_schema_privilege(current_user,'public','CREATE'),"
                "has_table_privilege(current_user,'jobs','DELETE'),"
                "has_column_privilege(current_user,'jobs','reserved','UPDATE'),"
                "has_column_privilege(current_user,'jobs','status','UPDATE'),"
                "has_table_privilege(current_user,'records','INSERT'),"
                "has_table_privilege(current_user,'records','UPDATE'),"
                "has_table_privilege(current_user,'records','DELETE'),"
                "has_table_privilege(current_user,'events','INSERT')"
            ).one()
            == (False,) * 8
        )
    accepted = submit(f)
    before = assert_publication(f, accepted)
    for descriptor in f.storage.calls:
        assert len(f.storage.local.read_verified(descriptor)) == descriptor.byte_count
    with f.journal.open(identity(f)) as session:
        assert session.states[0].commit_status == "CONFIRMED"
        assert session.states[0].logical_writes == 3
        assert session.snapshot.data()["operation_id"] == accepted["operation_id"]
    poison_new_work(f, monkeypatch)
    assert submit(f, origin=OriginCorrelation("9" * 32)) == accepted
    assert reconcile(f) == accepted and snapshot(f) == before
    clean_pool(f)


def test_postgres_eight_new_same_identity_calls_commit_once(publication_pg, monkeypatch):
    f, barrier = publication_pg, Barrier(8)
    assert not snapshot(f)["jobs"] and not snapshot(f)["artifact_refs"]

    def contender():
        barrier.wait(timeout=10)
        try:
            return submit(f)
        except AdmissionError as error:
            assert error.code in {"dependency_unavailable", "outcome_uncertain"}
            return error.code  # Nonblocking durable identity ownership may be busy.

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(contender) for _ in range(8)]
        results = [future.result(timeout=45) for future in futures]
    winners = [result for result in results if isinstance(result, dict)]
    assert winners and all(result == winners[0] for result in winners)
    before = assert_publication(f, winners[0])
    poison_new_work(f, monkeypatch)
    for _ in results:
        assert submit(f) == reconcile(f) == winners[0]
    assert snapshot(f) == before
    clean_pool(f)


def test_postgres_distinct_concurrent_admissions_share_exact_metadata(publication_pg):
    f, ready, calls = publication_pg, Barrier(8), local()

    def uploaded(*_):
        calls.count = getattr(calls, "count", 0) + 1
        if calls.count == 3:
            ready.wait(timeout=20)  # Every original descriptor predates publication.

    f.storage.after = uploaded

    def contender(number):
        raw = submission()
        raw["client_operation_id"] = f"{number + 1:032x}"
        return submit(f, intent=parse_submit(canonical(raw)), key_hash=f"{number + 1:064x}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(contender, number) for number in range(8)]
        results = [future.result(timeout=60) for future in futures]
    rows = snapshot(f)
    assert len({r["job_id"] for r in results}) == len({r["operation_id"] for r in results}) == 8
    assert all(len(rows[t]) == 8 for t in ("jobs", "operations", "operation_keys", "audit"))
    assert len(rows["artifact_refs"]) == 24 and len(rows["artifact_objects"]) == 10
    for role in ("task", "admission_config"):
        refs = [row for row in rows["artifact_refs"] if row["role"] == role]
        assert len({r["artifact_id"] for r in refs}) == 1
        stored = next(r for r in rows["artifact_objects"] if r["id"] == refs[0]["artifact_id"])
        expected = next(d for d in f.storage.calls if d.id == stored["id"])
        assert stored == vars(expected)  # All seven fields, including original timestamp.
    clean_pool(f)


@pytest.mark.parametrize("table,number", STAGES)
def test_postgres_each_successful_sql_stage_rolls_back_atomic_publication(
    publication_pg, table, number
):
    f, seen = publication_pg, []
    before = snapshot(f)

    def stop(c, cursor, statement, parameters, context, many):
        if statement.strip().startswith("INSERT INTO " + table):
            seen.append(statement)
            if len(seen) == number:
                assert c.in_transaction()
                raise RuntimeError("PRIVATE-PUBLICATION-STAGE")

    event.listen(f.engine, "after_cursor_execute", stop)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f)
    finally:
        event.remove(f.engine, "after_cursor_execute", stop)
    safe_failure(caught, "dependency_unavailable")
    assert len(seen) == number and snapshot(f) == before
    assert len(f.storage.calls) == 3  # Uploaded objects may remain; no SQL publication.
    with f.journal.open(identity(f)) as session:
        assert session.route == "reconcile" and session.states[0].commit_pending
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)
    assert snapshot(f) == before and len(f.storage.calls) == 3
    clean_pool(f)


def test_postgres_real_missing_audit_privilege_rolls_back_without_collision_retry(publication_pg):
    f, codes = publication_pg, []
    before = snapshot(f)
    with f.owner.begin() as c:
        c.exec_driver_sql(f"REVOKE INSERT ON audit FROM {f.pg['app_role']}")

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    event.listen(f.engine, "handle_error", observed)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f)
    finally:
        event.remove(f.engine, "handle_error", observed)
    safe_failure(caught, "dependency_unavailable")
    assert codes == ["42501"] and snapshot(f) == before
    with f.journal.open(identity(f)) as session:
        assert len(session.states) == 1 and session.states[0].commit_pending
    assert len(f.storage.calls) == 3
    clean_pool(f)


def service_key(f):
    identifier = "e" * 32
    principal = VerifiedPrincipal.service_key(identifier)
    with f.owner.begin() as c:
        c.execute(
            text("INSERT INTO api_keys VALUES(:id,:hash,'operator','fixture',:expiry,false)"),
            {"id": identifier, "hash": "d" * 64, "expiry": 253402300799.0},
        )
        c.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"),
            {"id": identifier, "p": PROJECT},
        )
        c.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": principal.principal_id},
        )
    f.principal = principal
    f.context = f.authority.named(principal, PROJECT).context
    return identifier


def change_authority(connection, f, change, key):
    # Every participating writer shares project-first exclusion, including policy.
    connection.execute(text("SELECT id FROM projects WHERE id=:p FOR UPDATE"), {"p": PROJECT})
    statement = {
        "policy": "UPDATE projects SET name='changed-policy' WHERE id=:p",
        "member": "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
        "WHERE project_id=:p AND principal_id=:principal",
        "key": "UPDATE api_keys SET revoked=true WHERE id=:key",
    }[change]
    connection.execute(
        text(statement), {"p": PROJECT, "principal": f.principal.principal_id, "key": key}
    )


@pytest.mark.parametrize("change", ["member", "key", "policy"])
def test_postgres_owner_change_wins_observed_publication_lock_wait(
    publication_pg, monkeypatch, change
):
    f, pending, continue_publish, checked_out, actors = (
        publication_pg,
        Event(),
        Event(),
        Event(),
        [],
    )
    key = service_key(f) if change == "key" else None
    before = snapshot(f)
    original = AdmissionJournalSession.commit

    def pause(session, kind):
        result = original(session, kind)
        if kind == "commit_pending":
            f.outside()
            pending.set()
            assert continue_publish.wait(10)
        return result

    def actor(raw, *_):
        if continue_publish.is_set():
            actors.append(raw.info.backend_pid)
            checked_out.set()

    monkeypatch.setattr(AdmissionJournalSession, "commit", pause)
    event.listen(f.engine, "checkout", actor)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit, f)
            try:
                assert pending.wait(15)
                with f.owner.connect() as writer:
                    writer.exec_driver_sql("SET LOCAL statement_timeout='8s'")
                    blocker = writer.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                    change_authority(writer, f, change, key)
                    continue_publish.set()
                    # The event is registered before the worker starts; no sleep race.
                    assert checked_out.wait(5)
                    wait_blocked(f.pg, actors[-1], blocker)
                    writer.commit()
                expected = AdmissionError if change == "policy" else ResourceNotFound
                with pytest.raises(expected):
                    future.result(timeout=15)
            finally:
                continue_publish.set()
    finally:
        event.remove(f.engine, "checkout", actor)
    assert snapshot(f) == before and len(f.storage.calls) == 3
    clean_pool(f)


@pytest.mark.parametrize("change", ["member", "key", "policy"])
def test_postgres_publication_wins_exclusion_then_fresh_disclosure(
    publication_pg, monkeypatch, change
):
    f, staged, release, writer_done, writer_ready = (
        publication_pg,
        Event(),
        Event(),
        Event(),
        Event(),
    )
    key = service_key(f) if change == "key" else None
    publisher_pids, writer_pids = [], []
    publish, disclose = admission_coordinator.publish_rows, f.service._disclose

    def hold(connection, *args, **kwargs):
        result = publish(connection, *args, **kwargs)
        publisher_pids.append(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
        staged.set()
        assert release.wait(10)
        return result

    def after_commit(*args, **kwargs):
        f.outside()
        assert writer_done.wait(10)
        return disclose(*args, **kwargs)

    def writer():
        with f.owner.begin() as c:
            c.exec_driver_sql("SET LOCAL statement_timeout='8s'")
            writer_pids.append(c.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
            writer_ready.set()
            change_authority(c, f, change, key)
        writer_done.set()

    monkeypatch.setattr(admission_coordinator, "publish_rows", hold)
    monkeypatch.setattr(f.service, "_disclose", after_commit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publish_future = pool.submit(submit, f)
        try:
            assert staged.wait(15)
            writer_future = pool.submit(writer)
            assert writer_ready.wait(5)
            wait_blocked(f.pg, writer_pids[0], publisher_pids[0])
            release.set()
            writer_future.result(timeout=15)
            if change == "policy":
                accepted = publish_future.result(timeout=15)
                assert_publication(f, accepted)
            else:
                with pytest.raises(ResourceNotFound):
                    publish_future.result(timeout=15)
                rows = snapshot(f)
                assert all(
                    len(rows[t]) == 1 for t in ("jobs", "operations", "operation_keys", "audit")
                )
        finally:
            release.set()
            writer_done.set()
    clean_pool(f)


def test_postgres_final_policy_recheck_after_all_rows_is_atomic(publication_pg, monkeypatch):
    f, seen = publication_pg, []
    before = snapshot(f)
    publish = admission_coordinator.publish_rows

    def mutate(connection, *args, **kwargs):
        result = publish(connection, *args, **kwargs)
        seen.append(connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one())
        # Same Connection and existing project lock; no unsynchronized Python flag.
        connection.exec_driver_sql("UPDATE projects SET name='changed-in-publication'")
        return result

    # Only this fault fixture adds the one permission used by the injected mutation.
    with f.owner.begin() as c:
        c.exec_driver_sql(f"GRANT UPDATE(name) ON projects TO {f.pg['app_role']}")
    monkeypatch.setattr(admission_coordinator, "publish_rows", mutate)
    with pytest.raises(AdmissionError) as caught:
        submit(f)
    safe_failure(caught, "dependency_unavailable")
    assert seen == [1] and snapshot(f) == before
    with f.owner.connect() as c:
        assert (
            c.execute(text("SELECT name FROM projects WHERE id=:p"), {"p": PROJECT}).scalar_one()
            == f.name
        )
    clean_pool(f)


@pytest.mark.parametrize("second", [False, True])
def test_postgres_proved_metadata_collision_reuses_exact_winner_once(
    publication_pg, monkeypatch, second
):
    f, winners, releases = publication_pg, [], []
    prove = admission_coordinator.prove_replacement

    def checked(connection, *args):
        # This fresh proof follows a completed rollback and a fresh transaction.
        assert f.engine.pool.checkedout() == 1 and f.active.depth == 1
        releases.append(snapshot(f))
        assert not releases[-1]["jobs"] and not releases[-1]["operations"]
        return prove(connection, *args)

    def race(*_):
        count = len(f.storage.calls)
        if count == 3 or (second and count == 6):
            f.outside()
            prior = f.storage.calls[0 if count == 3 else 4]
            winner = replace(prior, id=("e" if count == 3 else "f") * 32)
            with f.owner.begin() as c:
                record_verified(c, winner)
            winners.append(winner)

    monkeypatch.setattr(admission_coordinator, "prove_replacement", checked)
    f.storage.after = race
    if second:
        with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
            submit(f)
        assert not snapshot(f)["jobs"] and not snapshot(f)["operations"]
    else:
        accepted = submit(f)
        assert accepted and len(snapshot(f)["jobs"]) == 1
    assert len(releases) == 1 and len(f.storage.calls) == 6
    assert f.storage.calls[3] == winners[0]
    with f.owner.connect() as c:
        stored = dict(
            c.execute(text("SELECT * FROM artifact_objects WHERE id=:id"), {"id": winners[0].id})
            .mappings()
            .one()
        )
    assert stored == vars(winners[0])
    with f.journal.open(identity(f)) as session:
        assert len(session.states) == 2 and session.route == "reconcile"
        assert sum(s.logical_writes for s in session.states) == 6
        assert session.states[-1].commit_status == ("PENDING" if second else "CONFIRMED")
        assert metadata(session.snapshot.data()["descriptors"]["task"]) == winners[0]
    clean_pool(f)


@pytest.mark.parametrize("phase", ["before_ack", "after_ack", "journal"])
def test_postgres_new_publication_uncertainty_has_only_original_sql_recovery(
    publication_pg, monkeypatch, phase
):
    f, staged = publication_pg, set()
    before = snapshot(f)
    commit, append = Connection.commit, JournalSession.append

    def written(connection, cursor, statement, *args):
        if statement.strip().startswith("INSERT INTO audit"):
            staged.add(id(connection))

    def uncertain(connection):
        if connection.engine is f.engine and id(connection) in staged:
            staged.remove(id(connection))
            if phase == "after_ack":
                commit(connection)
            if phase != "journal":
                raise RuntimeError("PRIVATE-COMMIT-ACK")
        return commit(connection)

    def journal(session, kind, data):
        if phase == "journal" and kind == "commit_confirmed":
            raise OSError("PRIVATE-CONFIRMATION")
        return append(session, kind, data)

    monkeypatch.setattr(Connection, "commit", uncertain)
    monkeypatch.setattr(JournalSession, "append", journal)
    event.listen(f.engine, "after_cursor_execute", written)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f)
    finally:
        event.remove(f.engine, "after_cursor_execute", written)
    safe_failure(caught, "outcome_uncertain")
    if phase == "before_ack":
        assert snapshot(f) == before
        # Keep the journal available for suppression; every new-work adapter is unavailable.
        f.service.registry = f.service.storage = f.service.readiness = None
        monkeypatch.setattr(
            f.policy, "require_available", lambda: pytest.fail("new work after pending")
        )
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            submit(f)
        with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
            reconcile(f)
        assert snapshot(f) == before
    else:
        with f.owner.connect() as c:
            accepted = dict(
                c.exec_driver_sql("SELECT id AS operation_id,job_id FROM operations")
                .mappings()
                .one()
            )
        after = assert_publication(f, accepted)
        poison_new_work(f, monkeypatch)
        assert submit(f) == reconcile(f) == accepted and snapshot(f) == after
    assert len(f.storage.calls) == 3
    clean_pool(f)


def test_postgres_replay_retains_original_project_after_default_change(publication_pg, monkeypatch):
    f = publication_pg
    accepted = submit(f)
    before = snapshot(f)
    other = "7" * 32
    with f.owner.begin() as c:
        c.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,'Other',created_at FROM projects WHERE id=:p"
            ),
            {"other": other, "p": PROJECT},
        )
        c.execute(
            text(
                "UPDATE project_memberships SET legacy_default=false "
                "WHERE project_id=:p AND principal_id=:id"
            ),
            {"p": PROJECT, "id": f.principal.principal_id},
        )
        c.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,true)"),
            {"p": other, "id": f.principal.principal_id},
        )
    assert f.authority.legacy(f.principal).context.project_id == other
    poison_new_work(f, monkeypatch)
    assert submit(f) == accepted and snapshot(f) == before
    # A different accessible project is a new namespace, never this SQL winner.
    f.service = AdmissionCoordinator(f.engine, f.authority)
    f.service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
    foreign = replace(f.context, project_id=other)
    with pytest.raises(AdmissionError, match="^dependency_unavailable$"):
        submit(f, original_context=foreign)
    with pytest.raises(ResourceNotFound):
        submit(f, original_context=replace(f.context, project_id="0" * 32))
    assert snapshot(f) == before


def test_postgres_pending_submit_with_unavailable_identity_stays_uncertain(
    publication_pg, monkeypatch
):
    # Completes the independently found initial-SQL-unavailable classification gap.
    f, codes = publication_pg, []
    before = snapshot(f)
    publish = admission_coordinator.publish_rows

    def stop(*args, **kwargs):
        raise SystemExit("synthetic precommit interruption")

    monkeypatch.setattr(admission_coordinator, "publish_rows", stop)
    with pytest.raises(SystemExit):
        submit(f)
    monkeypatch.setattr(admission_coordinator, "publish_rows", publish)
    assert snapshot(f) == before and len(f.storage.calls) == 3
    with f.journal.open(identity(f)) as session:
        assert session.route == "reconcile" and session.states[0].commit_pending
    with f.owner.begin() as c:
        c.exec_driver_sql(f"REVOKE SELECT ON operations FROM {f.pg['app_role']}")

    def observed(context):
        codes.append(getattr(context.original_exception, "sqlstate", None))

    def unavailable(*args, **kwargs):
        pytest.fail("Unresolved identity invoked new-work preparation")

    for target, method in (
        (f.policy, "require_available"),
        (f.ready, "check"),
        (f.storage, "put_verified"),
    ):
        monkeypatch.setattr(target, method, unavailable)
    event.listen(f.engine, "handle_error", observed)
    try:
        with pytest.raises(AdmissionError) as caught:
            submit(f)
    finally:
        event.remove(f.engine, "handle_error", observed)
        with f.owner.begin() as c:
            c.exec_driver_sql(f"GRANT SELECT ON operations TO {f.pg['app_role']}")
    safe_failure(caught, "outcome_uncertain")
    assert codes == ["42501"] and snapshot(f) == before
    with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
        submit(f)
    assert snapshot(f) == before and len(f.storage.calls) == 3
    clean_pool(f)


_CRASH_CHILD = """
import importlib.util, os, select, sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

path = Path(os.environ["SYNTHETIC_PUBLICATION_TEST"])
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location("publication_proof", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
phase = os.environ["SYNTHETIC_PUBLICATION_PHASE"]
assert phase in {"before", "after"}
engine = create_engine(os.environ["SYNTHETIC_PUBLICATION_DSN"], poolclass=NullPool)
principal = m.VerifiedPrincipal(m.PRINCIPAL)
context = m.RequestAuthority(engine).named(principal, m.PROJECT).context
f = m.runtime(
    engine, principal=principal, context=context, name=os.environ["SYNTHETIC_PROJECT_NAME"],
    root=Path(os.environ["SYNTHETIC_JOURNAL_ROOT"]),
    objects=Path(os.environ["SYNTHETIC_OBJECT_ROOT"]),
    key=os.environ["SYNTHETIC_OBJECT_KEY"].encode("ascii"),
)
native_commit, publish = Connection.commit, m.admission_coordinator.publish_rows
staged = set()

def publication(connection, *args, **kwargs):
    result = publish(connection, *args, **kwargs)
    assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
    staged.add(id(connection))
    return result

def boundary(connection):
    if connection.engine is engine and id(connection) in staged:
        staged.remove(id(connection))
        if phase == "after":
            native_commit(connection)
        print("publication_boundary=" + phase, flush=True)
        # Wait for parent observation and SIGKILL, never infer timing from sleep.
        readable, _, _ = select.select([sys.stdin], [], [], 15)
        if not readable:
            raise SystemExit(4)
        raise SystemExit(5)
    return native_commit(connection)

m.admission_coordinator.publish_rows = publication
Connection.commit = boundary
try:
    m.submit(f)
    raise SystemExit(6)
except Exception:
    # No submitted content, DSNs, local paths or raw driver output.
    print("publication_boundary=unavailable", flush=True)
    raise SystemExit(1) from None
finally:
    engine.dispose()
"""


@pytest.mark.parametrize("phase", ["before", "after"])
def test_postgres_actual_sigkill_preserves_atomic_original_identity(
    publication_pg, monkeypatch, phase
):
    f = publication_pg
    before = snapshot(f)
    f.engine.dispose()
    wait_for_database_drain(f.pg["control"], f.owner.url.database)
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "SYNTHETIC_PUBLICATION_TEST": str(Path(__file__).resolve()),
        "SYNTHETIC_PUBLICATION_DSN": f.engine.url.render_as_string(hide_password=False),
        "SYNTHETIC_PUBLICATION_PHASE": phase,
        "SYNTHETIC_PROJECT_NAME": f.name,
        "SYNTHETIC_JOURNAL_ROOT": str(f.root),
        "SYNTHETIC_OBJECT_ROOT": str(f.objects),
        "SYNTHETIC_OBJECT_KEY": f.key.decode("ascii"),
    }
    environment.pop("PYTHONPATH", None)
    child = subprocess.Popen(
        [sys.executable, "-c", _CRASH_CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=25):
                pytest.fail("Synthetic publication child missed its bounded phase", pytrace=False)
            marker = child.stdout.readline(128)
        if marker != ("publication_boundary=" + phase + "\n").encode():
            pytest.fail("Synthetic publication child missed exact phase", pytrace=False)
        # Inspect bounded immutable journal records without taking the child's lock.
        child_root = f.root / identity(f).children[0]
        records = sorted(child_root.glob("0*.json"))
        assert 1 <= len(records) <= 64
        assert sum(path.stat().st_size for path in records) <= 128 * 1024
        values = [json.loads(path.read_bytes()) for path in records]
        assert any(value["kind"] == "commit_pending" for value in values)
        assert not any(value["kind"] == "commit_confirmed" for value in values)
        visible = snapshot(f)
        if phase == "before":
            assert visible == before
        else:
            assert len(visible["operations"]) == len(visible["jobs"]) == len(visible["audit"]) == 1
        child.kill()
        try:
            code = child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pytest.fail("Synthetic publication child did not exit after kill", pytrace=False)
        assert code == -signal.SIGKILL
    finally:
        try:
            if child.poll() is None:
                child.kill()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pytest.fail("Synthetic publication child cleanup timed out", pytrace=False)
        finally:
            for pipe in (child.stdin, child.stdout):
                pipe.close()
    wait_for_database_drain(f.pg["control"], f.owner.url.database)
    after = snapshot(f)
    fresh = create_engine(f.engine.url, poolclass=NullPool)
    try:
        service = AdmissionCoordinator(fresh, RequestAuthority(fresh), journal=f.journal)
        service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
        f.service = service
        if phase == "before":
            assert after == before
            with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
                reconcile(f)
            with pytest.raises(AdmissionError, match="^outcome_uncertain$"):
                submit(f)
            assert snapshot(f) == before
        else:
            accepted = {
                "operation_id": after["operations"][0]["id"],
                "job_id": after["jobs"][0]["id"],
            }
            assert_publication(f, accepted)
            # SQL winner must bypass even the durable journal on fresh restart.
            monkeypatch.setattr(f.journal, "open", lambda *_: pytest.fail("winner opened journal"))
            assert reconcile(f) == submit(f, origin=OriginCorrelation("9" * 32)) == accepted
            assert snapshot(f) == after
    finally:
        fresh.dispose()
