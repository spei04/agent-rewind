"""Actual PostgreSQL admission primitives; no coordinator/receipt/commit-replay claim."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import text
from test_admission_repository import aliases, config_refs, get, insert, prepared, resolve
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT, job
from test_admission_schema_postgres import PROFILE
from test_artifact_postgres import prepare_postgres
from test_run_projection_postgres import drain

from agent_rewind.admission_records import AdmissionStorageError, verify_job_configuration
from agent_rewind.admission_repository import AdmissionRepository
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL admission repositories"
)


@pytest.fixture
def storage_pg(pg):
    if not PROFILE.is_file():
        pytest.skip("Mandatory catalog capture must receive independent literal approval first")
    prepare_postgres(pg)
    drain(pg)
    initialize_projection(pg["owner"])
    drain(pg)
    initialize_admission(pg["owner"])
    value, payload = prepared()
    with pg["owner"].begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": PRINCIPAL},
        )
        job(connection)
        config_refs(connection, value, payload)
    authority = RequestAuthority(pg["owner"])
    principal = VerifiedPrincipal(PRINCIPAL)
    return SimpleNamespace(
        engine=pg["owner"],
        pg=pg,
        value=value,
        payload=payload,
        principal=principal,
        context=authority.named(principal, PROJECT).context,
        authority=authority,
        repo=AdmissionRepository(authority),
    )


def persist(f):
    with f.engine.begin() as connection:
        operation = insert(f, connection)
        aliases(f, connection)
    return operation


def test_postgres_operation_alias_read_and_select_only_authority(storage_pg):
    f = storage_pg
    expected = persist(f)
    with f.engine.begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {f.pg['app_role']}"
        )
    with f.pg["app"].connect() as connection:
        assert get(f, connection) == expected
        result = resolve(f, connection)
        assert result.operation == expected and not result.needs_alias
        assert expected.accepted_response == {"job_id": JOB, "operation_id": OPERATION}
        assert expected.failure_correlation_id == "6" * 32


def test_postgres_caller_rollback_and_unique_identity_conflict(storage_pg):
    f = storage_pg
    with pytest.raises(RuntimeError, match="synthetic stop"), f.engine.begin() as connection:
        insert(f, connection)
        aliases(f, connection)
        raise RuntimeError("synthetic stop")
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 0
    persist(f)
    with (
        pytest.raises(AdmissionStorageError, match="^admission_conflict$"),
        f.engine.begin() as connection,
    ):
        insert(f, connection)


def test_postgres_concurrent_insert_has_one_constrained_winner(storage_pg):
    f = storage_pg
    ready = Barrier(2)

    def contender():
        ready.wait(timeout=5)
        try:
            with f.engine.begin() as connection:
                insert(f, connection)
                aliases(f, connection)
            return "inserted"
        except AdmissionStorageError as error:
            assert error.code == "admission_conflict"
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(contender) for _ in range(2)]
        assert sorted(result.result(timeout=15) for result in outcomes) == ["conflict", "inserted"]
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 1
    # The losing primitive did not retry or return another publisher's acceptance.


@pytest.mark.parametrize("field", ["created_at", "retain_until"])
def test_postgres_infinite_timestamp_is_fixed_metadata_refusal(storage_pg, field):
    f = storage_pg
    persist(f)
    with f.engine.begin() as connection:
        if field == "created_at":
            connection.execute(text("UPDATE operations SET created_at='-infinity'::timestamptz"))
        else:
            connection.execute(text("UPDATE operations SET retain_until='infinity'::timestamptz"))
    with (
        f.engine.connect() as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        get(f, connection)


@pytest.mark.parametrize("mutation", ["missing", "digest", "extra", "timestamp"])
def test_postgres_config_candidate_association_and_receipt_refusal(storage_pg, mutation):
    from test_admission_envelope import descriptor

    from agent_rewind.artifact_metadata import record_verified, register_ref

    f = storage_pg
    with f.engine.begin() as connection:
        if mutation == "missing":
            connection.execute(text("DELETE FROM artifact_refs WHERE role='admission_config'"))
        elif mutation == "digest":
            connection.execute(
                text(
                    "UPDATE jobs SET execution_config_ref=:d,execution_config_digest=:d "
                    "WHERE id=:id"
                ),
                {"d": "0" * 64, "id": JOB},
            )
        elif mutation == "extra":
            value = descriptor(b"other", project=PROJECT, object_id="7" * 32)
            record_verified(connection, value)
            register_ref(
                connection,
                project_id=PROJECT,
                owner_kind="job",
                owner_id=JOB,
                role="admission_config",
                artifact_id=value.id,
            )
        else:
            connection.execute(
                text(
                    "UPDATE artifact_objects SET created_at=created_at+interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": f.value.configuration_binding.descriptor.id},
            )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            insert(f, connection)
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


@pytest.mark.parametrize("mutation", ["revoke", "expire", "viewer", "scope"])
def test_postgres_creator_service_key_is_fresh_and_scope_bound(storage_pg, mutation):
    f = storage_pg
    key_id = "e" * 32
    key = VerifiedPrincipal.service_key(key_id)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO api_keys VALUES(:id,:hash,'operator','fixture',:expires,false)"),
            {"id": key_id, "hash": "d" * 64, "expires": time.time() + 3600},
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"), {"id": key_id, "p": PROJECT}
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": key.principal_id},
        )
        connection.execute(
            text("UPDATE jobs SET actor=:actor WHERE id=:id"),
            {"actor": key.principal_id, "id": JOB},
        )
    f.principal = key
    f.context = f.authority.named(key, PROJECT).context
    persist(f)
    with f.engine.begin() as connection:
        if mutation == "revoke":
            connection.execute(
                text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key_id}
            )
        elif mutation == "expire":
            connection.execute(text("UPDATE api_keys SET expires=1 WHERE id=:id"), {"id": key_id})
        elif mutation == "viewer":
            connection.execute(
                text("UPDATE api_keys SET role='viewer' WHERE id=:id"), {"id": key_id}
            )
        else:
            connection.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at) "
                    "SELECT :id,organization_id,'Other',created_at FROM projects WHERE id=:p"
                ),
                {"id": "7" * 32, "p": PROJECT},
            )
            connection.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:p "
                    "WHERE resource_kind='key' AND resource_id=:id"
                ),
                {"p": "7" * 32, "id": key_id},
            )
    denial = ActionForbidden if mutation == "viewer" else ResourceNotFound
    with f.engine.connect() as connection, pytest.raises(denial):
        resolve(f, connection)


def test_postgres_revocation_committed_after_lookup_prevents_return(storage_pg, monkeypatch):
    f = storage_pg
    persist(f)
    original = f.repo._operation
    changed = False

    def revoke(*args, **kwargs):
        nonlocal changed
        value = original(*args, **kwargs)
        if not changed:
            changed = True
            with f.engine.begin() as other:
                other.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
                        "WHERE project_id=:p AND principal_id=:id"
                    ),
                    {"p": PROJECT, "id": PRINCIPAL},
                )
        return value

    monkeypatch.setattr(f.repo, "_operation", revoke)
    with f.engine.connect() as connection, pytest.raises(ResourceNotFound):
        get(f, connection)
    assert changed


def test_postgres_effective_autocommit_refuses_before_insert(storage_pg):
    f = storage_pg
    autocommit = f.engine.execution_options(isolation_level="AUTOCOMMIT")
    with (
        autocommit.connect() as connection,
        connection.begin(),
        pytest.raises(AdmissionStorageError, match="^admission_transaction_required$"),
    ):
        insert(f, connection)
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


def test_postgres_common_legacy_configuration_and_original_context(storage_pg):
    f = storage_pg
    with f.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET payload_version=1 WHERE id=:id"), {"id": JOB})
        assert (
            verify_job_configuration(
                connection, context=f.context, job_id=JOB, payload_version=1
            ).digest
            == f.value.configuration.digest
        )
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0
        connection.execute(
            text(
                "UPDATE jobs SET execution_config_ref=NULL,execution_config_digest=NULL "
                "WHERE id=:id"
            ),
            {"id": JOB},
        )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            verify_job_configuration(connection, context=f.context, job_id=JOB, payload_version=1)
    foreign = replace(f.context, project_id="7" * 32)
    with f.engine.connect() as connection, pytest.raises(ResourceNotFound):
        f.repo.resolve_identities(
            connection,
            f.principal,
            foreign,
            client_operation_id=f.value.intent.client_operation_id,
            key_hash="7" * 64,
            request_digest=f.value.intent.request_digest,
        )


def test_postgres_shared_client_and_key_names_are_separate_principal_namespaces(storage_pg):
    f = storage_pg
    first = persist(f)
    second_principal = VerifiedPrincipal("oidc:" + "f" * 64)
    value, payload = prepared("3" * 32)
    with f.engine.begin() as connection:
        job(connection, identifier="3" * 32)
        config_refs(connection, value, payload)
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
            {"p": PROJECT, "id": second_principal.principal_id},
        )
        connection.execute(
            text("UPDATE jobs SET actor=:actor WHERE id=:id"),
            {"actor": second_principal.principal_id, "id": "3" * 32},
        )
    f.principal = second_principal
    f.context = f.authority.named(second_principal, PROJECT).context
    f.value, f.payload = value, payload
    with f.engine.begin() as connection:
        second = insert(f, connection, operation_id="b" * 32)
        aliases(f, connection, operation_id="b" * 32)
        assert resolve(f, connection).operation == second
        assert second.client_operation_id == first.client_operation_id
        assert second.id != first.id and second.job_id != first.job_id
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2
