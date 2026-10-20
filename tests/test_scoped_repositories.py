"""Synthetic repository authorization; not authenticated routes or customer admission."""

import hashlib
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, insert, text, update

from agent_rewind.database import events, jobs, keys, records
from agent_rewind.migrations import service
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.ownership import ROLE_ACTIONS, oidc_principal_id
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import (
    ProjectContext,
    RepositoryUnavailable,
    ScopedRepositories,
)

ORG = "8" * 32
A, B = "9" * 32, "7" * 32
ALICE = oidc_principal_id("https://synthetic.invalid", "alice")
BOB = oidc_principal_id("https://synthetic.invalid", "bob")
CA, CB = ProjectContext(ORG, A, ALICE), ProjectContext(ORG, B, BOB)
RUN_A, RUN_B, JOB_A, JOB_B = "1" * 32, "2" * 32, "a" * 32, "b" * 32
STUDY, STUDY_JOB, TRIAL = "5" * 32, "d" * 32, "6" * 32
CONTENT = b"identical synthetic bytes"
HASH = hashlib.sha256(CONTENT).hexdigest()


def scope(connection, kind, resource_id, project=A):
    connection.execute(
        text("INSERT INTO resource_scopes VALUES (:kind,:id,:project)"),
        {"kind": kind, "id": resource_id, "project": project},
    )


def put_job(connection, resource_id, kind, project=A):
    connection.execute(
        insert(jobs).values(
            id=resource_id,
            kind=kind,
            created=1,
            payload=HASH,
            status="failed",
            cancel=False,
            budget=10,
            reserved=3,
        )
    )
    scope(connection, "job", resource_id, project)


def put_record(connection, resource_id, kind, body, project=A):
    connection.execute(insert(records).values(id=resource_id, kind=kind, created=1, data=body))
    scope(connection, kind, resource_id, project)


def populate(engine):
    """Test-only second project; no admitted runtime release is created."""
    service.install(engine, "synthetic-scoped")
    initialize_ownership(
        engine,
        {
            "schema_version": 1,
            "installation_key": "synthetic-scoped",
            "organization_id": ORG,
            "project_id": A,
            "project_name": "Synthetic A",
            "principal_grants": [
                {"principal_id": ALICE, "role": "maintainer", "legacy_default": True}
            ],
        },
    )
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO projects VALUES (:id,:org,'Synthetic B',:created)"),
            {"id": B, "org": ORG, "created": datetime.now(UTC).isoformat()},
        )
        connection.execute(
            text(
                "INSERT INTO project_memberships VALUES (:project,:principal,'viewer',NULL,false)"
            ),
            {"project": B, "principal": BOB},
        )
        put_job(connection, JOB_A, "run")
        put_job(connection, JOB_B, "run", B)
        put_record(connection, RUN_A, "run", {"job_id": JOB_A, "parent_id": None})
        put_record(connection, RUN_B, "run", {"job_id": JOB_B, "parent_id": None}, B)
        connection.execute(insert(events).values(run_id=RUN_A, step=1, artifact=HASH, hash=HASH))


@pytest.fixture
def scoped(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scoped.sqlite'}")
    populate(engine)
    yield engine, ScopedRepositories(engine)
    engine.dispose()


def edit(engine, resource_id, **changes):
    with engine.begin() as connection:
        row = connection.execute(select_record(resource_id)).scalar_one()
        connection.execute(
            update(records).where(records.c.id == resource_id).values(data={**row, **changes})
        )


def select_record(resource_id):
    from sqlalchemy import select

    return select(records.c.data).where(records.c.id == resource_id)


def add_study(engine, *, claimed=True):
    with engine.begin() as connection:
        put_job(connection, STUDY_JOB, "study")
        put_record(
            connection,
            TRIAL,
            "run",
            {
                "job_id": STUDY_JOB,
                "parent_id": RUN_A,
                "status": "failed",
            },
        )
        pair = {"control_success": None, "treatment_success": None, "error": "JobStopped"}
        if claimed:
            pair["control_run"] = TRIAL
        put_record(
            connection,
            STUDY,
            "study",
            {
                "job_id": STUDY_JOB,
                "source_run": RUN_A,
                "request": {"run_id": RUN_A},
                "candidates": [{"pairs": [pair]}],
                "confirmation": None,
            },
        )


@dataclass(frozen=True)
class Object:
    id: str
    project_id: str
    digest: str = HASH
    locator: str = "synthetic-locator"
    format_version: int = 1
    byte_count: int = len(CONTENT)
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


class Objects:
    def __init__(self):
        self.refs = {
            (A, "run", RUN_A, "task", HASH): Object("3" * 32, A),
            (B, "run", RUN_B, "task", HASH): Object("4" * 32, B),
        }
        self.resolved = []
        self.loaded = []

    def resolve(self, connection, *, project_id, owner_kind, owner_id, role, digest):
        key = project_id, owner_kind, owner_id, role, digest
        self.resolved.append(key)
        return self.refs.get(key)

    def load(self, value):
        self.loaded.append(value)
        return CONTENT


@pytest.mark.parametrize("role", ["viewer", "operator", "maintainer"])
def test_c05_matrix_comes_from_current_membership(scoped, role):
    engine, repo = scoped
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE project_memberships SET role=:role WHERE project_id=:p"),
            {"role": role, "p": A},
        )
    for action in set.union(*(set(v) for v in ROLE_ACTIONS.values())) | {"admin", "unknown"}:
        if action in ROLE_ACTIONS[role]:
            repo.require_action(CA, action, kind="run", resource_id=RUN_A)
        else:
            with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
                repo.require_action(CA, action, kind="run", resource_id=RUN_A)


@pytest.mark.parametrize(
    "context",
    [
        ProjectContext("0" * 32, A, ALICE),
        ProjectContext(ORG, B, ALICE),
        ProjectContext(ORG, A, "alice"),
        ProjectContext(ORG, A, "administrator"),
        ProjectContext(ORG, A, "bootstrap"),
        ProjectContext(ORG, A, oidc_principal_id("https://other.invalid", "alice")),
    ],
)
def test_unverified_issuerless_foreign_and_admin_contexts_deny(scoped, context):
    _, repo = scoped
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        repo.get_run(context, RUN_A)


def test_revoked_membership_applies_to_next_call_without_cached_grant(scoped):
    engine, repo = scoped
    assert repo.get_run(CA, RUN_A)["id"] == RUN_A
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE project_memberships SET revoked_at=:at WHERE project_id=:p"),
            {"at": datetime.now(UTC).isoformat(), "p": A},
        )
    with pytest.raises(ResourceNotFound):
        repo.get_run(CA, RUN_A)


def add_key(engine, *, key_role="operator", member_role="operator", project=A):
    with engine.begin() as connection:
        connection.execute(
            insert(keys).values(
                id=RUN_A,
                hash="f" * 64,
                role=key_role,
                name="synthetic",
                expires=time.time() + 60,
                revoked=False,
            )
        )
        scope(connection, "key", RUN_A, project)
        connection.execute(
            text("INSERT INTO project_memberships VALUES (:p,:principal,:role,NULL,false)"),
            {"p": A, "principal": "api-key:" + RUN_A, "role": member_role},
        )
    return ProjectContext(ORG, A, "api-key:" + RUN_A)


@pytest.mark.parametrize(
    "key_role,member_role,allowed",
    [
        ("viewer", "operator", False),
        ("operator", "viewer", False),
        ("operator", "operator", True),
        ("administrator", "operator", True),
        ("maintainer", "maintainer", False),
        ("unknown", "operator", False),
    ],
)
def test_live_key_role_intersects_membership_and_never_grants_key_management(
    scoped,
    key_role,
    member_role,
    allowed,
):
    engine, repo = scoped
    context = add_key(engine, key_role=key_role, member_role=member_role)
    if allowed:
        repo.require_action(context, "branch", kind="run", resource_id=RUN_A)
    else:
        with pytest.raises(ResourceNotFound):
            repo.require_action(context, "branch", kind="run", resource_id=RUN_A)
    with pytest.raises(ResourceNotFound):
        repo.require_action(context, "create_key")


@pytest.mark.parametrize("change", ["revoked", "expired", "unmapped", "foreign"])
def test_key_live_state_and_scope_are_rechecked(scoped, change):
    engine, repo = scoped
    context = add_key(engine)
    assert repo.get_run(context, RUN_A)["id"] == RUN_A
    with engine.begin() as connection:
        if change == "revoked":
            connection.execute(update(keys).values(revoked=True))
        elif change == "expired":
            connection.execute(update(keys).values(expires=time.time() - 1))
        elif change == "unmapped":
            connection.execute(text("DELETE FROM resource_scopes WHERE resource_kind='key'"))
        else:
            connection.execute(
                text("UPDATE resource_scopes SET project_id=:p WHERE resource_kind='key'"), {"p": B}
            )
    with pytest.raises(ResourceNotFound):
        repo.get_run(context, RUN_A)


def test_cross_kind_identity_and_key_outputs_never_expose_hashes(scoped):
    engine, repo = scoped
    add_key(engine)
    assert repo.get_run(CA, RUN_A)["id"] == repo.get_key(CA, RUN_A)["id"]
    assert "hash" not in repo.get_key(CA, RUN_A)
    assert all("hash" not in row for row in repo.list_resources(CA, "key"))
    assert repo.list_resources(CB, "key") == []


def test_lists_and_event_refs_are_project_scoped(scoped):
    _, repo = scoped
    assert [row["id"] for row in repo.list_resources(CA, "run")] == [RUN_A]
    assert [row["id"] for row in repo.list_resources(CB, "run")] == [RUN_B]
    assert [row["id"] for row in repo.list_resources(CA, "job")] == [JOB_A]
    assert len(repo.event_refs(CA, RUN_A)) == 1
    with pytest.raises(ResourceNotFound):
        repo.event_refs(CB, RUN_A)


@pytest.mark.parametrize("foreign", [RUN_B, "f" * 32, "bad", "' OR 1=1 --"])
def test_foreign_missing_invalid_resources_have_identical_denial_before_resolver(scoped, foreign):
    engine, _ = scoped
    objects = Objects()
    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        repo.read_artifact(CA, "run", foreign, "task", HASH)
    assert objects.resolved == objects.loaded == []


@pytest.mark.parametrize("change", ["foreign_parent", "foreign_job", "missing_parent", "cycle"])
def test_forged_run_lineage_denies_before_artifact_resolution(scoped, change):
    engine, _ = scoped
    if change == "foreign_parent":
        edit(engine, RUN_A, parent_id=RUN_B)
    elif change == "foreign_job":
        edit(engine, RUN_A, job_id=JOB_B)
    elif change == "missing_parent":
        edit(engine, RUN_A, parent_id="f" * 32)
    else:
        edit(engine, RUN_A, parent_id=RUN_A)
        with engine.begin() as connection:
            connection.execute(update(jobs).where(jobs.c.id == JOB_A).values(kind="branch"))
    objects = Objects()
    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
    assert objects.resolved == objects.loaded == []


@pytest.mark.parametrize("claimed", [True, False])
def test_incomplete_study_preserves_zero_or_one_arm_evidence(scoped, claimed):
    engine, repo = scoped
    add_study(engine, claimed=claimed)
    result = repo.get_study(CA, STUDY)
    assert result["candidates"][0]["pairs"][0]["error"] == "JobStopped"
    assert repo.get_run(CA, TRIAL)["status"] == "failed"
    assert repo.get_job(CA, STUDY_JOB)["id"] == STUDY_JOB


@pytest.mark.parametrize(
    "change", ["request", "foreign_trial", "duplicate_trial", "missing_owner", "ambiguous_owner"]
)
def test_forged_study_lineage_refuses(scoped, change):
    engine, repo = scoped
    add_study(engine)
    if change == "request":
        edit(engine, STUDY, request={"run_id": RUN_B})
    elif change in {"foreign_trial", "duplicate_trial"}:
        pair = (
            {"control_run": RUN_B}
            if change == "foreign_trial"
            else {
                "control_run": TRIAL,
                "treatment_run": TRIAL,
            }
        )
        edit(engine, STUDY, candidates=[{"pairs": [pair]}])
    elif change == "missing_owner":
        with engine.begin() as connection:
            connection.execute(records.delete().where(records.c.id == STUDY))
    else:
        with engine.begin() as connection:
            body = connection.execute(select_record(STUDY)).scalar_one()
            put_record(connection, "e" * 32, "study", body)
    with pytest.raises(ResourceNotFound):
        repo.get_run(CA, TRIAL)


def test_same_digest_needs_distinct_project_owner_and_role_reference(scoped):
    engine, _ = scoped
    objects = Objects()
    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    assert repo.read_artifact(CA, "run", RUN_A, "task", HASH) == CONTENT
    assert repo.read_artifact(CB, "run", RUN_B, "task", HASH) == CONTENT
    assert objects.loaded[0].project_id == A and objects.loaded[1].project_id == B
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "event", HASH)
    objects.refs.pop((A, "run", RUN_A, "task", HASH))
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
    assert len(objects.loaded) == 2


def test_descriptor_project_or_digest_confusion_refuses_before_load(scoped):
    engine, _ = scoped
    objects = Objects()
    objects.refs[(A, "run", RUN_A, "task", HASH)] = Object("4" * 32, B)
    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
    assert objects.loaded == []


def test_no_adapter_or_missing_scope_never_falls_back_to_hash_storage(scoped):
    engine, repo = scoped
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM resource_scopes WHERE resource_kind='run' AND resource_id=:id"),
            {"id": RUN_A},
        )
    with pytest.raises(ResourceNotFound):
        repo.get_run(CA, RUN_A)


def test_authoritative_row_id_cannot_be_overwritten_by_record_json(scoped):
    engine, repo = scoped
    edit(engine, RUN_A, id=RUN_B, created=999)
    result = repo.get_run(CA, RUN_A)
    assert result["id"] == RUN_A and result["created"] == 1


@pytest.mark.parametrize("limit", [0, 101, True, -1])
def test_list_bound_is_explicit(scoped, limit):
    with pytest.raises(ResourceNotFound):
        scoped[1].list_resources(CA, "run", limit=limit)


def test_oversized_metadata_fails_before_json_decode(scoped, monkeypatch):
    engine, repo = scoped
    edit(engine, RUN_A, huge="x" * 4096)
    monkeypatch.setattr("agent_rewind.scoped_repositories.MAX_RECORD_BYTES", 100)

    def no_decode(*args, **kwargs):
        pytest.fail("Oversize JSON reached client parser")

    monkeypatch.setattr("agent_rewind.scoped_repositories.json.loads", no_decode)
    with pytest.raises(ResourceNotFound):
        repo.get_run(CA, RUN_A)


@pytest.mark.parametrize(
    "limit", ["MAX_NODES", "MAX_EDGES", "MAX_RETAINED_BYTES", "MAX_PARENT_DEPTH"]
)
def test_lineage_work_bounds_fail_closed(scoped, monkeypatch, limit):
    engine, repo = scoped
    add_study(engine)
    monkeypatch.setattr("agent_rewind.scoped_lineage." + limit, 0)
    with pytest.raises(ResourceNotFound):
        repo.get_study(CA, STUDY)


def test_repository_does_not_issue_ddl_or_change_disabled_release(scoped):
    engine, repo = scoped
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        repo.get_run(CA, RUN_A)
        repo.list_resources(CA, "job")
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert runtime_schema_compatibility(engine).status == "incompatible"


def test_database_failure_is_fixed_unavailable_without_sql_or_secrets(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'absent.sqlite'}")
    try:
        with pytest.raises(RepositoryUnavailable, match="^Resource service unavailable.$"):
            ScopedRepositories(engine).get_run(CA, RUN_A)
    finally:
        engine.dispose()


@pytest.mark.parametrize("change", ["membership", "key", "scope", "reference"])
def test_revocation_during_storage_io_prevents_return_and_holds_no_db_connection(scoped, change):
    engine, _ = scoped
    objects = Objects()
    context = add_key(engine) if change == "key" else CA
    checked_out = []

    def checkout(*args):
        checked_out.append(True)

    def checkin(*args):
        checked_out.pop()

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)

    def revoke(value):
        assert checked_out == []
        with engine.begin() as connection:
            if change == "membership":
                connection.execute(
                    text("UPDATE project_memberships SET revoked_at=:now"),
                    {"now": datetime.now(UTC).isoformat()},
                )
            elif change == "key":
                connection.execute(update(keys).values(revoked=True))
            elif change == "scope":
                connection.execute(text("DELETE FROM resource_scopes WHERE resource_kind='run'"))
            else:
                objects.refs.clear()
        return CONTENT

    try:
        repo = ScopedRepositories(engine, artifact_resolver=objects.resolve, artifact_loader=revoke)
        with pytest.raises(ResourceNotFound):
            repo.read_artifact(context, "run", RUN_A, "task", HASH)
        assert checked_out == []
    finally:
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "checkin", checkin)


def test_legacy_administrator_key_without_explicit_project_grant_never_grants_access(scoped):
    engine, repo = scoped
    context = add_key(engine, key_role="administrator")
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM project_memberships WHERE principal_id=:id"),
            {"id": context.principal_id},
        )
    with pytest.raises(ResourceNotFound):
        repo.get_run(context, RUN_A)


@pytest.mark.parametrize(
    "kind,resource_id", [("run", RUN_A), ("job", JOB_A), ("study", STUDY), ("key", RUN_A)]
)
def test_every_repository_kind_denies_foreign_project(scoped, kind, resource_id):
    engine, repo = scoped
    add_study(engine)
    add_key(engine)
    lookup = getattr(repo, "get_" + kind)
    assert lookup(CA, resource_id)["id"] == resource_id
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        lookup(CB, resource_id)
    assert repo.list_resources(CB, kind) == (
        []
        if kind in {"study", "key"}
        else [repo.get_run(CB, RUN_B)]
        if kind == "run"
        else [repo.get_job(CB, JOB_B)]
    )


@pytest.mark.parametrize(
    "body",
    [
        '{"job_id":"a","job_id":"b","parent_id":null}',
        '{"job_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","parent_id":null,"value":NaN}',
        "[]",
    ],
)
def test_corrupt_record_json_refuses_without_artifact_access(scoped, body):
    engine, _ = scoped
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET data=:body WHERE id=:id"), {"body": body, "id": RUN_A}
        )
    objects = Objects()
    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=objects.load
    )
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)
    assert objects.resolved == objects.loaded == []


def test_dynamic_sqlite_job_width_cannot_bypass_read_bound(scoped, monkeypatch):
    engine, repo = scoped
    with engine.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == JOB_A).values(payload="x" * 4096))
    monkeypatch.setattr("agent_rewind.scoped_repositories.MAX_RECORD_BYTES", 1024)
    with pytest.raises(ResourceNotFound):
        repo.get_job(CA, JOB_A)


@pytest.mark.parametrize(
    "change", [{"id": "e" * 32}, {"created_at": Object.created_at + timedelta(seconds=1)}]
)
def test_object_descriptor_change_during_io_does_not_return_old_bytes(scoped, change):
    engine, _ = scoped
    objects = Objects()

    def replace_during_io(value):
        objects.refs[(A, "run", RUN_A, "task", HASH)] = replace(value, **change)
        return CONTENT

    repo = ScopedRepositories(
        engine, artifact_resolver=objects.resolve, artifact_loader=replace_during_io
    )
    with pytest.raises(ResourceNotFound):
        repo.read_artifact(CA, "run", RUN_A, "task", HASH)


def test_foreign_incoming_job_reference_does_not_contaminate_project_discovery(scoped, monkeypatch):
    from agent_rewind.scoped_repositories import _Reads

    engine, repo = scoped
    edit(engine, RUN_B, job_id=JOB_A)
    loaded = []
    original = _Reads.record

    def track(self, kind, resource_id):
        loaded.append((kind, resource_id))
        return original(self, kind, resource_id)

    monkeypatch.setattr(_Reads, "record", track)
    assert repo.get_job(CA, JOB_A)["id"] == JOB_A
    assert loaded == [("run", RUN_A)]
    with pytest.raises(ResourceNotFound):
        repo.get_run(CB, RUN_B)


def test_event_row_width_and_digest_validation_refuse_whole_result(scoped):
    engine, repo = scoped
    with engine.begin() as connection:
        connection.execute(update(events).values(artifact="x" * 4096))
    with pytest.raises(ResourceNotFound):
        repo.event_refs(CA, RUN_A)
    with engine.begin() as connection:
        connection.execute(update(events).values(artifact="not-a-digest"))
    with pytest.raises(ResourceNotFound):
        repo.event_refs(CA, RUN_A)


def test_retained_job_bytes_count_towards_graph_bound(scoped, monkeypatch):
    engine, repo = scoped
    with engine.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == JOB_A).values(payload="x" * 4096))
    monkeypatch.setattr("agent_rewind.scoped_lineage.MAX_RETAINED_BYTES", 2048)
    with pytest.raises(ResourceNotFound):
        repo.get_run(CA, RUN_A)


@pytest.mark.parametrize("depth,allowed", [(64, True), (65, False)])
def test_exact_parent_depth_bound(scoped, depth, allowed):
    engine, repo = scoped
    parent = RUN_A
    with engine.begin() as connection:
        for n in range(depth):
            job_id, run_id = f"{n + 100:032x}", f"{n + 1000:032x}"
            put_job(connection, job_id, "branch")
            put_record(connection, run_id, "run", {"job_id": job_id, "parent_id": parent})
            parent = run_id
    if allowed:
        assert repo.get_run(CA, parent)["id"] == parent
    else:
        with pytest.raises(ResourceNotFound):
            repo.get_run(CA, parent)


@pytest.mark.parametrize("created", ["x" * 4096, b"x" * 4096])
def test_dynamic_sqlite_record_created_is_bounded_before_decode(scoped, monkeypatch, created):
    engine, repo = scoped
    # SQLite FLOAT affinity accepts text/blob cells in retained historical rows.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET created=:created WHERE id=:id"),
            {"created": created, "id": RUN_A},
        )
    monkeypatch.setattr("agent_rewind.scoped_repositories.MAX_RECORD_BYTES", 1024)

    def no_decode(*args, **kwargs):
        pytest.fail("Oversize record row crossed the SQL-side read bound")

    monkeypatch.setattr("agent_rewind.scoped_repositories.json.loads", no_decode)
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        repo.get_run(CA, RUN_A)
