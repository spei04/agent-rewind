"""Real PostgreSQL ar6 exclusion, preservation, rollback and separate-object restore."""

import hashlib
import json
from types import SimpleNamespace

import pytest
import test_admission_schema_postgres as admission_tests
import test_migration_recovery_postgres as recovery_tests
import test_migrations_postgres as migrations
import test_run_projection_postgres as projection_tests
from legacy_fixture import FIXTURE_ROOT, canonical_bytes, read_manifest
from sqlalchemy import text
from test_admission_repository import aliases, config_refs, get, insert, prepared, resolve
from test_admission_schema import PROJECT, job
from test_admission_service import snapshot

from agent_rewind.admission_records import AdmissionStorageError, verify_job_configuration
from agent_rewind.admission_repository import AdmissionRepository
from agent_rewind.migrations import admission_service
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import (
    ReleaseProfile,
    check_schema_compatibility,
    load_release_profile,
    runtime_schema_compatibility,
)
from agent_rewind.migrations.projection_service import backfill_run_index
from agent_rewind.migrations.schema import ADMISSION, COLUMNS, MigrationRefused, catalog
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal

pg = migrations.pg
recovery = recovery_tests.recovery
observed_reader = projection_tests.observed_reader
projection_profile = projection_tests.projection_profile
projected_legacy = projection_tests.projected_legacy
admission_profile = admission_tests.admission_profile
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL admission migration/recovery"
)


@pytest.fixture
def complete_legacy(admission_profile, projected_legacy):
    state = projected_legacy
    backfill_run_index(state["owner"], projection_tests.source())
    projection_tests.drain(state)
    return state


@pytest.mark.parametrize("completed_rows", [0, 1])
def test_postgres_admission_requires_completed_frozen_projection(
    admission_profile, projected_legacy, completed_rows
):
    state = projected_legacy
    engine = state["owner"]
    if completed_rows:
        backfill_run_index(engine, projection_tests.source(), batch_size=completed_rows)
    before = snapshot(engine)
    projection_tests.drain(state)
    with pytest.raises(MigrationRefused, match="^completed_projection_required$"):
        initialize_admission(engine)
    assert snapshot(engine) == before
    projection_tests.preserved(engine)


@pytest.mark.parametrize("mutation", ["created", "scope", "late"])
def test_postgres_admission_rejects_completed_source_or_scope_drift(complete_legacy, mutation):
    state = complete_legacy
    engine = state["owner"]
    with engine.begin() as connection:
        if mutation == "created":
            connection.execute(
                text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": "2" * 32}
            )
        elif mutation == "scope":
            # This job scope is not protected by the run_index parent/scope FK.
            connection.execute(
                text(
                    "DELETE FROM resource_scopes WHERE resource_kind='job' "
                    "AND resource_id=(SELECT MIN(id) FROM jobs)"
                )
            )
        else:
            connection.execute(
                text(
                    "INSERT INTO records SELECT :id,kind,created-10,data FROM records WHERE id=:old"
                ),
                {"id": "0" * 32, "old": "1" * 32},
            )
            connection.execute(
                text("INSERT INTO resource_scopes SELECT 'run',:id,id FROM projects"),
                {"id": "0" * 32},
            )
    before = snapshot(engine)
    projection_tests.drain(state)
    with pytest.raises(
        MigrationRefused, match="^(projection_cohort_changed|projection_source_invalid)$"
    ):
        initialize_admission(engine)
    assert snapshot(engine) == before


@pytest.mark.parametrize("phase", ["ddl", "fingerprint"])
def test_postgres_admission_failure_rolls_back_schema_fingerprint_and_progress(
    complete_legacy, monkeypatch, phase
):
    state = complete_legacy
    engine = state["owner"]
    before = snapshot(engine)
    if phase == "ddl":
        original = admission_service._alembic

        def stop(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic admission migration interruption")

        monkeypatch.setattr(admission_service, "_alembic", stop)
    else:
        original = admission_service._installed

        def stop(connection, shape):
            value = original(connection, shape)
            if value["_revision"] == ADMISSION:
                raise RuntimeError("synthetic admission migration interruption")
            return value

        monkeypatch.setattr(admission_service, "_installed", stop)
    projection_tests.drain(state)
    with pytest.raises(RuntimeError, match="^synthetic admission migration interruption$"):
        initialize_admission(engine)
    assert snapshot(engine) == before
    projection_tests.preserved(engine)


@pytest.mark.parametrize("mode", ["runtime-role", "autocommit"])
def test_postgres_admission_rejects_unowned_or_nontransactional_install(complete_legacy, mode):
    state = complete_legacy
    engine = state["owner"]
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {state['app_role']}"
        )
    before = snapshot(engine)
    target = (
        state["app"]
        if mode == "runtime-role"
        else engine.execution_options(isolation_level="AUTOCOMMIT")
    )
    error = "^migration_owner_required$" if mode == "runtime-role" else "transaction"
    projection_tests.drain(state)
    with pytest.raises(MigrationRefused, match=error):
        initialize_admission(target)
    assert snapshot(engine) == before
    projection_tests.preserved(engine)


def historical_rows(engine):
    """Read exact original fields/IDs, allowing only separately asserted new jobs."""
    manifest = read_manifest()
    result = {}
    with engine.connect() as connection:
        for name, expected in manifest["expected_rows"].items():
            columns = ",".join(column[0] for column in COLUMNS[name])
            order = "run_id,step" if name == "events" else "id"
            rows = [
                dict(row)
                for row in connection.execute(
                    text(f"SELECT {columns} FROM {name} ORDER BY {order}")
                ).mappings()
            ]
            if name == "jobs":
                ids = {row["id"] for row in expected}
                rows = [row for row in rows if row["id"] in ids]
            for row in rows:
                for field in ("cancel", "revoked"):
                    if field in row and row[field] is not None:
                        row[field] = int(row[field])
            assert rows == expected
            assert [hashlib.sha256(canonical_bytes(row)).hexdigest() for row in rows] == manifest[
                "row_sha256"
            ][name]
            result[name] = rows
    assert sum(len(rows) for rows in result.values()) == 14
    assert sum(row["reserved"] for row in result["jobs"]) == 245000
    return result


def admission_rows(engine):
    with engine.connect() as connection:
        return {
            name: [
                dict(row)
                for row in connection.exec_driver_sql(
                    f"SELECT * FROM {name} ORDER BY {order}"
                ).mappings()
            ]
            for name, order in (
                ("operations", "id"),
                ("operation_keys", "project_id,principal_id,kind,key_hash"),
                ("artifact_objects", "id"),
                ("artifact_refs", "project_id,owner_kind,owner_id,artifact_id,role"),
                ("jobs", "id"),
                ("resource_scopes", "resource_kind,resource_id"),
                ("project_memberships", "project_id,principal_id"),
                ("installation_adoptions", "installation_key"),
            )
        }


def test_postgres_admission_restore_preserves_history_aliases_and_config_associations(
    complete_legacy, recovery, tmp_path
):
    state = complete_legacy
    engine = state["owner"]
    assert recovery["owner"] is engine
    projection_tests.drain(state)
    initialize_admission(engine)
    before_history = historical_rows(engine)
    before_projection = projection_tests.snapshot(engine)
    value, payload = prepared("f" * 32)
    # Retain the migration's frozen grant inventory: this is the already-adopted
    # maintainer, not a new grant or dynamic customer-activation fixture.
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    with engine.begin() as connection:
        job(connection, identifier=value.job_id)
        connection.execute(text("UPDATE jobs SET reserved=0 WHERE id=:id"), {"id": value.job_id})
        config_refs(connection, value, payload)
        connection.execute(
            text("UPDATE jobs SET actor=:actor WHERE id=:id"),
            {"actor": principal.principal_id, "id": value.job_id},
        )
    authority = RequestAuthority(engine)
    fixture = SimpleNamespace(
        principal=principal,
        context=authority.named(principal, PROJECT).context,
        value=value,
        payload=payload,
        repo=AdmissionRepository(authority),
    )
    with engine.begin() as connection:
        expected = insert(fixture, connection)
        assert aliases(fixture, connection)
    before = admission_rows(engine)
    assert len(before["operations"]) == len(before["operation_keys"]) == 1
    assert len(before["jobs"]) == 4 and len(before["artifact_refs"]) == 3
    assert historical_rows(engine) == before_history
    assert projection_tests.snapshot(engine) == before_projection
    objects = recovery_tests._object_copy(FIXTURE_ROOT / "objects", tmp_path / "backup-objects")
    archive = recovery_tests._dump(recovery)
    archive_digest = hashlib.sha256(archive).hexdigest()
    recovery_tests._run(recovery_tests._restore_command(recovery), archive=archive)
    assert hashlib.sha256(archive).hexdigest() == archive_digest
    target = recovery["target"]
    assert target.url.database != engine.url.database != recovery["control"].url.database
    assert admission_rows(target) == before
    assert historical_rows(target) == before_history
    assert projection_tests.snapshot(target) == before_projection
    with target.connect() as connection:
        assert catalog(connection) == json.loads(admission_tests.PROFILE.read_text())
        profile = load_release_profile().model_dump(mode="json")
        profile["revisions"] = [r for r in profile["revisions"] if r["revision"] != ADMISSION]
        assert (
            check_schema_compatibility(
                connection, ReleaseProfile.model_validate_json(json.dumps(profile))
            ).code
            == "schema_incompatible"
        )
    restored = recovery_tests._object_copy(objects, tmp_path / "restored-objects")
    assert {p.name: p.read_bytes() for p in restored.iterdir()} == {
        p.name: p.read_bytes() for p in (FIXTURE_ROOT / "objects").iterdir()
    }
    fixture.repo = AdmissionRepository(RequestAuthority(target))
    with target.connect() as connection:
        assert get(fixture, connection) == expected
        result = resolve(fixture, connection)
        assert result.operation == expected and not result.needs_alias
        assert (
            verify_job_configuration(
                connection,
                context=fixture.context,
                job_id=value.job_id,
                payload_version=2,
            ).descriptor
            == value.configuration_binding.descriptor
        )
        for old in read_manifest()["expected_rows"]["jobs"]:
            with pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"):
                verify_job_configuration(
                    connection,
                    context=fixture.context,
                    job_id=old["id"],
                    payload_version=1,
                )
    projection_tests.drain(recovery, target)
    assert initialize_admission(target)["revision"] == ADMISSION
    assert runtime_schema_compatibility(target).code == "migration_only"
    assert admission_rows(target) == before
    assert historical_rows(engine) == before_history
    # New metadata is a SQL association fixture, not a verified-upload receipt.
    # pg_dump does not contain objects, keys or roles; those 18 objects are checked separately.


def test_postgres_admission_eighteenth_table_refuses_without_accepting_new_catalog(complete_legacy):
    state = complete_legacy
    engine = state["owner"]
    initialize_admission(engine)
    before = snapshot(engine)
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        engine.begin() as connection,
    ):
        connection.exec_driver_sql("CREATE TABLE eighteenth(value INTEGER)")
        catalog(connection)
    assert snapshot(engine) == before
    with engine.connect() as connection:
        admission_tests.original_rows(connection)
