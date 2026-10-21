"""Real SQLite admission identity/config associations, without a coordinator."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import test_admission_schema as schema_tests
from sqlalchemy import text
from test_admission_configuration import configuration
from test_admission_envelope import binding, descriptor
from test_admission_request import submission
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT

from agent_rewind import admission_records
from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_envelope import OriginCorrelation, prepare_admission
from agent_rewind.admission_records import AdmissionStorageError, verify_job_configuration
from agent_rewind.admission_repository import AdmissionRepository
from agent_rewind.admission_request import parse_submit
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.models import canonical
from agent_rewind.request_authority import ActionForbidden, RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

admission_engine = schema_tests.admission_engine

KEY = "7" * 64
CREATED = datetime(2000, 1, 1, tzinfo=UTC)
UNTIL = CREATED + timedelta(days=90)


@contextmanager
def transaction(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        yield connection


def prepared(job=JOB, *, client="a" * 32, ids=("3" * 32, "4" * 32, "5" * 32)):
    raw = submission()
    raw["client_operation_id"] = client
    intent = parse_submit(canonical(raw))
    entry = configuration()
    value = prepare_admission(
        intent=intent,
        registry=NativeRegistry(entry, ["fixture-image"]),
        project_id=PROJECT,
        job_id=job,
        origin=OriginCorrelation("6" * 32),
        task_binding=binding(intent.task_bytes, project=PROJECT, job=job, object_id=ids[0]),
        configuration_binding=binding(
            entry.canonical_bytes,
            role="admission_config",
            project=PROJECT,
            job=job,
            object_id=ids[1],
        ),
        permitted_processor_profile="fixture-processor",
    )
    return value, value.bind_payload(
        descriptor(value.envelope_bytes, object_id=ids[2], project=PROJECT)
    )


def config_refs(connection, value, payload):
    # Synthetic metadata only. P3 must supply actual verified upload receipts.
    connection.execute(
        text(
            "UPDATE jobs SET payload=:payload,budget=:budget,actor=:actor,payload_version=2,"
            "execution_config_ref=:config,execution_config_digest=:config WHERE id=:job"
        ),
        dict(
            payload=value.envelope_digest,
            budget=value.intent.budget_microusd,
            actor=PRINCIPAL,
            config=value.configuration.digest,
            job=value.job_id,
        ),
    )
    for item in (value.task_binding, value.configuration_binding, payload):
        record_verified(connection, item.descriptor)
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=value.job_id,
            role=item.role,
            artifact_id=item.descriptor.id,
        )


@pytest.fixture
def repository(admission_engine):
    value, payload = prepared()
    principal = VerifiedPrincipal(PRINCIPAL)
    with transaction(admission_engine) as connection:
        connection.execute(
            text(
                "INSERT INTO project_memberships VALUES(:project,:principal,'operator',NULL,false)"
            ),
            dict(project=PROJECT, principal=PRINCIPAL),
        )
        config_refs(connection, value, payload)
    authority = RequestAuthority(admission_engine)
    yield SimpleNamespace(
        engine=admission_engine,
        value=value,
        payload=payload,
        principal=principal,
        context=authority.named(principal, PROJECT).context,
        authority=authority,
        repo=AdmissionRepository(authority),
    )


def insert(fixture, connection, **updates):
    args = dict(
        operation_id=OPERATION,
        prepared=fixture.value,
        payload_binding=fixture.payload,
        created_at=CREATED,
        retain_until=UNTIL,
    )
    args.update(updates)
    return fixture.repo.insert_operation(connection, fixture.principal, fixture.context, **args)


def resolve(fixture, connection, **updates):
    args = dict(
        client_operation_id=fixture.value.intent.client_operation_id,
        key_hash=KEY,
        request_digest=fixture.value.intent.request_digest,
    )
    args.update(updates)
    return fixture.repo.resolve_identities(connection, fixture.principal, fixture.context, **args)


def aliases(fixture, connection, **updates):
    args = dict(
        operation_id=OPERATION, key_hash=KEY, request_digest=fixture.value.intent.request_digest
    )
    args.update(updates)
    return fixture.repo.bind_alias(connection, fixture.principal, fixture.context, **args)


def get(fixture, connection, **updates):
    return fixture.repo.get_operation(
        connection,
        fixture.principal,
        fixture.context,
        operation_id=updates.get("operation_id", OPERATION),
    )


def test_dual_identity_recovery_alias_and_original_origin_are_stable(repository, monkeypatch):
    f = repository
    with f.engine.connect() as connection:
        assert resolve(f, connection).operation is None
    with transaction(f.engine) as connection:
        stored = insert(f, connection)
        assert stored.accepted_response == {"job_id": JOB, "operation_id": OPERATION}
        assert resolve(f, connection).needs_alias is True
        assert aliases(f, connection) is True
        assert aliases(f, connection) is False
        assert connection.in_transaction()
    # Recovery never invokes the current registry, storage or another connection.
    monkeypatch.setattr(NativeRegistry, "resolve_new", lambda *_a, **_k: pytest.fail("registry"))
    with f.engine.connect() as connection:
        monkeypatch.setattr(f.engine, "connect", lambda: pytest.fail("another connection"))
        again = resolve(f, connection)
        assert again.operation == stored and not again.needs_alias
        assert get(f, connection) == stored
        assert again.operation.failure_correlation_id == "6" * 32
        # A past retain-until is not an eligibility or expiry cutoff.
        assert again.operation.retain_until.year == 2000


def test_viewer_status_read_is_not_creator_replay_authority(repository):
    f = repository
    viewer = VerifiedPrincipal("oidc:" + "f" * 64)
    with transaction(f.engine) as connection:
        insert(f, connection)
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
            {"p": PROJECT, "id": viewer.principal_id},
        )
    context = f.authority.named(viewer, PROJECT).context
    with f.engine.connect() as connection:
        assert (
            f.repo.get_operation(connection, viewer, context, operation_id=OPERATION).job_id == JOB
        )
        with pytest.raises(ActionForbidden):
            f.repo.resolve_identities(
                connection,
                viewer,
                context,
                client_operation_id=f.value.intent.client_operation_id,
                key_hash=KEY,
                request_digest=f.value.intent.request_digest,
            )
    with transaction(f.engine) as connection:
        connection.execute(
            text("UPDATE project_memberships SET role='operator' WHERE principal_id=:id"),
            {"id": viewer.principal_id},
        )
        assert (
            f.repo.resolve_identities(
                connection,
                viewer,
                context,
                client_operation_id=f.value.intent.client_operation_id,
                key_hash=KEY,
                request_digest=f.value.intent.request_digest,
            ).operation
            is None
        )
        with pytest.raises(ResourceNotFound):
            f.repo.bind_alias(
                connection,
                viewer,
                context,
                operation_id=OPERATION,
                key_hash=KEY,
                request_digest=f.value.intent.request_digest,
            )


@pytest.mark.parametrize("mutation", ["member", "scope", "missing"])
def test_replay_revalidates_current_scope_and_grant(repository, mutation):
    f = repository
    with transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
    with f.engine.connect() as connection:
        # Simulate out-of-contract administrative corruption; normal FK writes refuse.
        if mutation == "scope":
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if mutation == "member":
            connection.execute(
                text(
                    "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id"
                ),
                {"id": PRINCIPAL},
            )
        elif mutation == "scope":
            connection.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:other "
                    "WHERE resource_kind='job' AND resource_id=:id"
                ),
                {"other": "7" * 32, "id": JOB},
            )
        else:
            connection.execute(text("DELETE FROM operation_keys"))
            connection.execute(text("DELETE FROM operations"))
        connection.commit()
        if mutation == "scope":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    with f.engine.connect() as connection:
        if mutation == "missing":
            assert resolve(f, connection).operation is None
            with pytest.raises(ResourceNotFound):
                get(f, connection)
        else:
            with pytest.raises(ResourceNotFound):
                resolve(f, connection)


@pytest.mark.parametrize("change", ["client", "request"])
def test_existing_alias_rejects_changed_intent(repository, change):
    f = repository
    with transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
        with pytest.raises(AdmissionStorageError, match="^admission_conflict$"):
            resolve(
                f,
                connection,
                **{
                    "client_operation_id" if change == "client" else "request_digest": "e"
                    * (32 if change == "client" else 64)
                },
            )


def test_alias_digest_must_match_operation_even_when_owner_fk_is_valid(repository):
    f = repository
    with transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
        connection.execute(
            text("UPDATE operation_keys SET request_digest=:digest"), {"digest": "0" * 64}
        )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            resolve(f, connection)


@pytest.mark.parametrize("version", [1, 2])
def test_common_config_requires_no_operation_but_checks_exact_job_ref(repository, version):
    f = repository
    with transaction(f.engine) as connection:
        connection.execute(
            text("UPDATE jobs SET payload_version=:v WHERE id=:id"), {"v": version, "id": JOB}
        )
        result = verify_job_configuration(
            connection, context=f.context, job_id=JOB, payload_version=version
        )
        assert result.descriptor == f.value.configuration_binding.descriptor
        assert result.reference == result.digest == f.value.configuration.digest
        assert result.reference != result.descriptor.id
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


def test_legacy_null_configuration_is_preserved_but_not_new_writer_eligible(repository):
    f = repository
    with transaction(f.engine) as connection:
        connection.execute(
            text(
                "UPDATE jobs SET payload_version=1,execution_config_ref=NULL,"
                "execution_config_digest=NULL WHERE id=:id"
            ),
            {"id": JOB},
        )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            verify_job_configuration(connection, context=f.context, job_id=JOB, payload_version=1)
        assert connection.execute(
            text(
                "SELECT payload_version,execution_config_ref,execution_config_digest "
                "FROM jobs WHERE id=:id"
            ),
            {"id": JOB},
        ).one() == (1, None, None)


@pytest.mark.parametrize("mutation", ["missing", "second", "digest", "timestamp", "wrong_role"])
def test_config_candidate_count_and_original_descriptor_are_required(repository, mutation):
    f = repository
    with transaction(f.engine) as connection:
        if mutation == "missing":
            connection.execute(text("DELETE FROM artifact_refs WHERE role='admission_config'"))
        elif mutation == "second":
            value = descriptor(b"second", object_id="8" * 32, project=PROJECT)
            record_verified(connection, value)
            register_ref(
                connection,
                project_id=PROJECT,
                owner_kind="job",
                owner_id=JOB,
                role="admission_config",
                artifact_id=value.id,
            )
        elif mutation == "wrong_role":
            connection.execute(
                text("UPDATE artifact_refs SET role='result' WHERE role='admission_config'")
            )
        elif mutation == "digest":
            connection.execute(
                text(
                    "UPDATE jobs SET execution_config_ref=:d,execution_config_digest=:d "
                    "WHERE id=:id"
                ),
                {"d": "0" * 64, "id": JOB},
            )
        else:
            connection.execute(
                text("UPDATE artifact_objects SET created_at=:d WHERE id=:id"),
                {
                    "d": "2026-10-22T00:00:00+00:00",
                    "id": f.value.configuration_binding.descriptor.id,
                },
            )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            insert(f, connection)
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("created_at", "not-a-date"),
        ("retain_until", "infinity"),
        ("created_at", b"x"),
        ("retain_until", "2000-01-02T00:00:00+00:00"),
        ("created_at", "2000-01-01T00:00:00"),
        ("retain_until", "x" * 8192),
        ("created_at", "2000-01-01T00:00:00+00:00\0" + "x" * 8192),
    ],
    ids=["garbage", "infinity", "blob", "short-retention", "naive", "huge", "nul-huge"],
)
def test_corrupt_timestamp_refuses_before_materializing_oversized_cells(
    repository, monkeypatch, field, value
):
    f = repository
    with transaction(f.engine) as connection:
        insert(f, connection)
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        connection.execute(text(f"UPDATE operations SET {field}=:value"), {"value": value})
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
    original = admission_records.timestamp
    seen = []

    def bounded(value, **kwargs):
        if isinstance(value, str | bytes):
            assert len(value) <= 64
        seen.append(value)
        return original(value, **kwargs)

    monkeypatch.setattr(admission_records, "timestamp", bounded)
    with (
        f.engine.connect() as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        get(f, connection)
    if len(value) > 64:
        assert seen == []  # CASE NULL invalidates identity before timestamp parsing.


@pytest.mark.parametrize("delta", [-1, 0])
def test_retention_initial_floor_and_utc_storage(repository, delta):
    f = repository
    offset = timezone(timedelta(hours=5))
    created = CREATED.astimezone(offset)
    until = UNTIL.astimezone(offset) + timedelta(microseconds=delta)
    with transaction(f.engine) as connection:
        if delta < 0:
            with pytest.raises(AdmissionStorageError, match="^admission_input_invalid$"):
                insert(f, connection, created_at=created, retain_until=until)
        else:
            value = insert(f, connection, created_at=created, retain_until=until)
            assert value.created_at == CREATED and value.created_at.tzinfo == UTC
            assert (
                connection.exec_driver_sql("SELECT created_at FROM operations").scalar_one()
                == CREATED.isoformat()
            )


def test_caller_rollback_preserves_no_partial_operation_or_alias(repository):
    f = repository
    with pytest.raises(RuntimeError, match="fixture failure"), transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
        raise RuntimeError("fixture failure")
    with f.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 0


def test_no_actual_transaction_or_fk_enforcement_refuses(repository):
    f = repository
    with f.engine.connect() as connection:
        with pytest.raises(AdmissionStorageError, match="^admission_transaction_required$"):
            insert(f, connection)
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with pytest.raises(AdmissionStorageError, match="^admission_transaction_required$"):
            insert(f, connection)
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def test_same_key_alias_cannot_move_to_another_operation(repository):
    f = repository
    with transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
        assert aliases(f, connection) is False
        with pytest.raises(AdmissionStorageError, match="^admission_conflict$"):
            aliases(f, connection, request_digest="f" * 64)
        assert get(f, connection).failure_correlation_id == f.value.origin.correlation_id


@pytest.mark.parametrize("field", ["payload", "budget", "actor"])
def test_operation_requires_exact_common_job_payload_budget_and_actor(repository, field):
    f = repository
    value = {"payload": "e" * 64, "budget": 2, "actor": "oidc:" + "a" * 64}[field]
    with transaction(f.engine) as connection:
        connection.execute(
            text(f"UPDATE jobs SET {field}=:value WHERE id=:id"), {"value": value, "id": JOB}
        )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            insert(f, connection)
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


def test_both_existing_identities_must_select_the_same_operation(repository):
    f = repository
    second, payload = prepared("3" * 32, client="b" * 32, ids=("3" * 32, "4" * 32, "8" * 32))
    with transaction(f.engine) as connection:
        insert(f, connection)
        aliases(f, connection)
        config_refs(connection, second, payload)
        insert(f, connection, operation_id="b" * 32, prepared=second, payload_binding=payload)
        f.repo.bind_alias(
            connection,
            f.principal,
            f.context,
            operation_id="b" * 32,
            key_hash="8" * 64,
            request_digest=second.intent.request_digest,
        )
        with pytest.raises(AdmissionStorageError, match="^admission_conflict$"):
            resolve(f, connection, key_hash="8" * 64)
        assert resolve(f, connection).operation.id == OPERATION
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM operation_keys").scalar_one() == 2


@pytest.mark.parametrize("role", ["task", "payload"])
def test_published_task_and_envelope_receipts_must_match_every_field(repository, role):
    f = repository
    target = f.value.task_binding if role == "task" else f.payload
    with transaction(f.engine) as connection:
        connection.execute(
            text("UPDATE artifact_objects SET created_at=:created WHERE id=:id"),
            {"created": "2026-10-22T00:00:00+00:00", "id": target.descriptor.id},
        )
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            insert(f, connection)
        assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0


def test_bounded_config_descriptor_preserves_malformed_candidate(repository, monkeypatch):
    f = repository
    with transaction(f.engine) as connection:
        connection.execute(
            text("UPDATE artifact_objects SET created_at=:created WHERE id=:id"),
            {"created": "x" * 8192, "id": f.value.configuration_binding.descriptor.id},
        )
    original = admission_records._object
    seen = []

    def bounded(row):
        assert row["created_at"] is None
        seen.append(row["created_at"])
        return original(row)

    monkeypatch.setattr(admission_records, "_object", bounded)
    with (
        f.engine.connect() as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        verify_job_configuration(connection, context=f.context, job_id=JOB, payload_version=2)
    assert seen == [None]


def test_missing_config_object_is_not_filtered_into_absence_or_uniqueness(repository):
    f = repository
    with f.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(
            text("DELETE FROM artifact_objects WHERE id=:id"),
            {"id": f.value.configuration_binding.descriptor.id},
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
            verify_job_configuration(connection, context=f.context, job_id=JOB, payload_version=2)
