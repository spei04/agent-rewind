"""Actual SELECT-only PostgreSQL GET composition; opt in to the shared synthetic instance."""

from types import SimpleNamespace

import pytest
import test_migrations_postgres as migrations
from cryptography.fernet import Fernet
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT
from test_artifact_metadata import OTHER
from test_artifact_postgres import prepare_postgres
from test_operation_service import expect_dependency, invoke, key_context, publish_result
from test_operation_sources import roots
from test_operation_sources_postgres import source_pg, storage_pg
from test_run_projection_postgres import drain

from agent_rewind import operation_service
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.errors import Fault
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import CompatibilityResult, load_release_profile
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.models import canonical
from agent_rewind.operation_service import OperationService
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import ProjectContext

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL GET operation service"
)
__all__ = ["pg", "storage_pg", "source_pg"]


@pytest.fixture
def get_pg(source_pg, monkeypatch, tmp_path):
    f = SimpleNamespace(**vars(source_pg))
    with f.engine.begin() as connection:
        connection.exec_driver_sql(
            "GRANT SELECT ON projects,organizations,project_memberships,api_keys "
            f"TO {f.pg['app_role']}"
        )
    f.reader_engine = f.pg["app"]
    f.service = OperationService(f.reader_engine, RequestAuthority(f.reader_engine))
    monkeypatch.setattr(
        f.service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    f.work, f.connections, f.loads = [], [], []

    def work():
        value = OperationWork()
        f.work.append(value)
        return value

    monkeypatch.setattr(operation_service, "OperationWork", work)

    def connected(connection):
        f.connections.append(connection)

    event.listen(f.reader_engine, "engine_connect", connected)
    root = tmp_path / "encrypted"
    root.mkdir(mode=0o700)
    f.storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    try:
        yield f
    finally:
        event.remove(f.reader_engine, "engine_connect", connected)
        assert all(c.closed for c in f.connections)
        assert all(w._started is None for w in f.work)


def encrypted_result(f, run_id, *, invalid=False):
    body = canonical({"run_id": run_id}) if not invalid else b'{"run_id":"bad"}'
    value = publish_result(f, body)

    def load(observed):
        assert all(c.closed for c in f.connections)
        f.loads.append(observed)
        return f.storage.read_verified(observed)

    f.service.artifact_loader = load
    return value


@pytest.mark.parametrize(
    "count,distractors,key",
    [(0, False, False), (255, False, False), (255, True, False), (255, True, True)],
)
def test_postgres_whole_get_matching_native_trace_and_restricted_role(
    get_pg, count, distractors, key
):
    f = get_pg
    ids = roots(f, count) if count else []
    if distractors:
        roots(f, 2000, start=1000, job="e" * 32)
        roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "bad"})
        roots(f, 1, start=7000, job="e" * 32, update={"padding": "x" * (2 * 1024 * 1024)})
    if ids:
        encrypted_result(f, ids[-1])
    principal, context = key_context(f) if key else (f.principal, f.context)
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET reserved=:v WHERE id=:id"), {"v": 2**53 + 1, "id": JOB}
        )
    with f.reader_engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'operations','SELECT'),"
            "has_table_privilege(current_user,'operations','UPDATE'),"
            "has_table_privilege(current_user,'jobs','UPDATE'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, False, False, False)
    response = invoke(f, principal=principal, context=context)
    assert response["result_run_id"] == (ids[-1] if ids else None)
    assert response["reserved_microusd"] == 2**53 + 1
    assert f.work[0].statements == (62 if key else 50)
    assert f.work[0].seconds < 10 and f.work[0]._started is None
    print(
        f"GET PG roots={count} distractors={distractors} key={key} "
        f"attempts={f.work[0].statements} seconds={f.work[0].seconds:.6f}"
    )


@pytest.mark.parametrize("change", ["revoke", "scope", "phantom", "reassociate", "descriptor"])
@pytest.mark.parametrize("invalid", [False, True])
def test_postgres_release_then_owner_race_and_failure_recheck(get_pg, change, invalid):
    f = get_pg
    ids = roots(f, 1)
    value = encrypted_result(f, ids[0], invalid=invalid)
    original = f.service.artifact_loader

    def racing(descriptor):
        data = original(descriptor)
        if change == "phantom":
            roots(f, 1, start=2)
        else:
            with f.engine.begin() as connection:
                if change == "revoke":
                    connection.execute(
                        text(
                            "UPDATE project_memberships SET revoked_at=now() WHERE principal_id=:id"
                        ),
                        {"id": PRINCIPAL},
                    )
                elif change == "scope":
                    connection.execute(
                        text("DELETE FROM artifact_refs WHERE owner_kind='job' AND owner_id=:id"),
                        {"id": JOB},
                    )
                    connection.execute(
                        text("DELETE FROM operations WHERE id=:id"), {"id": OPERATION}
                    )
                    connection.execute(
                        text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": JOB}
                    )
                elif change == "reassociate":
                    import json

                    from test_admission_schema import job

                    job(connection, identifier="6" * 32)
                    connection.execute(
                        text("UPDATE operations SET job_id=:j,accepted_response=:a WHERE id=:id"),
                        {
                            "j": "6" * 32,
                            "id": OPERATION,
                            "a": json.dumps(
                                {"job_id": "6" * 32, "operation_id": OPERATION},
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    )
                else:
                    connection.execute(
                        text("UPDATE artifact_objects SET created_at='infinity' WHERE id=:id"),
                        {"id": value.id},
                    )
        return data

    f.service.artifact_loader = racing
    if change in {"revoke", "scope"}:
        with pytest.raises(ResourceNotFound):
            invoke(f)
    else:
        expect_dependency(lambda: invoke(f))
    assert len(f.loads) == 1 and len(f.work) == 1
    assert all(c.closed for c in f.connections)


def test_postgres_native_readonly_and_real_update_denial_then_reuse(get_pg, monkeypatch):
    f = get_pg
    original = f.service.authority.check
    observed = []

    def check(connection, *args, **kwargs):
        observed.append(connection.exec_driver_sql("SHOW transaction_read_only").scalar_one())
        assert (
            connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
            == "read committed"
        )
        return original(connection, *args, **kwargs)

    monkeypatch.setattr(f.service.authority, "check", check)
    assert invoke(f)["id"] == OPERATION
    assert observed == ["on"] * 4
    with pytest.raises(DBAPIError) as caught, f.reader_engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET cancel=TRUE WHERE id=:id"), {"id": JOB})
    assert caught.value.orig.sqlstate == "42501"
    assert invoke(f)["id"] == OPERATION


def test_postgres_real_clean_ar6_guard_without_synthetic_profile(pg, monkeypatch):
    prepare_postgres(pg)
    drain(pg)
    initialize_projection(pg["owner"])
    drain(pg)
    initialize_admission(pg["owner"])
    service = OperationService(pg["owner"], RequestAuthority(pg["owner"]))
    assert service.schema_compatibility().code == "migration_only"
    previous = load_release_profile().model_dump()
    monkeypatch.setattr(service, "_read", lambda *_a: pytest.fail("customer read before guard"))
    principal = VerifiedPrincipal(PRINCIPAL)
    context = ProjectContext("8" * 32, PROJECT, principal.principal_id)
    with pytest.raises(Fault, match="^schema_incompatible$"):
        service.read_operation(principal, context, OPERATION)
    assert load_release_profile().model_dump() == previous


@pytest.mark.parametrize("revoke", [False, True])
def test_postgres_loader_not_found_rechecks_fresh_authority(get_pg, revoke):
    f = get_pg
    ids = roots(f, 1)
    encrypted_result(f, ids[0])

    def missing(_value):
        assert all(c.closed for c in f.connections)
        if revoke:
            with f.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM project_memberships WHERE principal_id=:id"),
                    {"id": PRINCIPAL},
                )
        raise ResourceNotFound()

    f.service.artifact_loader = missing
    if revoke:
        with pytest.raises(ResourceNotFound):
            invoke(f)
    else:
        expect_dependency(lambda: invoke(f))
    assert len(f.work) == 1 and all(c.closed for c in f.connections)


def test_postgres_owner_readonly_is_not_merely_privilege_denial(get_pg, monkeypatch):
    f = get_pg
    service = OperationService(f.engine, RequestAuthority(f.engine))
    monkeypatch.setattr(
        service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    observed = []
    original = operation_service.read_operation

    def write(connection, *args, **kwargs):
        try:
            connection.execute(text("UPDATE jobs SET cancel=TRUE WHERE id=:id"), {"id": JOB})
        except DBAPIError as error:
            observed.append(error.orig.sqlstate)
            raise
        return original(connection, *args, **kwargs)

    monkeypatch.setattr(operation_service, "read_operation", write)
    expect_dependency(lambda: service.read_operation(f.principal, f.context, OPERATION))
    assert observed == ["25006"]
    monkeypatch.setattr(operation_service, "read_operation", original)
    assert service.read_operation(f.principal, f.context, OPERATION)["cancel_requested"] is False
