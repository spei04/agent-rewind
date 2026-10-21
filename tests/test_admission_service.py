"""Initializer/catalog rollback and exact predecessor binding."""

import json

import pytest
import test_run_projection_backfill as backfill_tests
from legacy_fixture import assert_preserved_rows, read_manifest, sha256
from sqlalchemy import text

from agent_rewind.migrations import admission_service, service
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import (
    ReleaseProfile,
    check_schema_compatibility,
    load_release_profile,
    runtime_schema_compatibility,
)
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused, catalog
from agent_rewind.projection_rows import read_index

legacy = backfill_tests.legacy


def snapshot(engine):
    with engine.connect() as connection:
        return (
            catalog(connection),
            source_digest(connection),
            read_index(connection, limit=10001),
            connection.exec_driver_sql(
                "SELECT * FROM migration_progress ORDER BY revision,phase"
            ).all(),
            connection.exec_driver_sql("SELECT id,run_sequence FROM projects ORDER BY id").all(),
        )


def preserved(path):
    assert_preserved_rows(path)
    for value in read_manifest()["objects"].values():
        assert (
            sha256((path.parent / "objects" / value["address"]).read_bytes())
            == value["ciphertext_sha256"]
        )


def complete(legacy):
    _, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    return engine


def test_admission_exact_initializer_preserves_history_and_reentry(legacy):
    path, _, _ = legacy
    engine = complete(legacy)
    before = snapshot(engine)
    first = initialize_admission(engine)
    assert first["revision"] == ADMISSION
    assert first["customer_ready"] is False
    after = snapshot(engine)
    assert after[1:] == before[1:]
    assert len(after[0]) == 17
    assert initialize_admission(engine) == first
    assert snapshot(engine) == after
    preserved(path)
    assert runtime_schema_compatibility(engine).code == "migration_only"
    assert service.schema_status(engine) == first
    profile = load_release_profile().model_dump(mode="json")
    profile["revisions"] = [r for r in profile["revisions"] if r["revision"] != ADMISSION]
    with engine.connect() as connection:
        assert (
            check_schema_compatibility(
                connection, ReleaseProfile.model_validate_json(json.dumps(profile))
            ).code
            == "schema_incompatible"
        )


@pytest.mark.parametrize("completed_rows", [0, 1])
def test_incomplete_projection_cannot_become_new_admission_baseline(legacy, completed_rows):
    path, engine, source = legacy
    initialize_projection(engine)
    if completed_rows:
        backfill_run_index(engine, source, batch_size=completed_rows)
    before = snapshot(engine)
    with pytest.raises(MigrationRefused, match="^completed_projection_required$"):
        initialize_admission(engine)
    assert snapshot(engine) == before
    preserved(path)


@pytest.mark.parametrize("mutation", ["created", "scope", "late"])
def test_completed_source_or_scope_drift_cannot_be_accepted_as_new_baseline(legacy, mutation):
    engine = complete(legacy)
    with engine.begin() as connection:
        if mutation == "created":
            connection.execute(
                text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": "2" * 32}
            )
        elif mutation == "scope":
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
    with pytest.raises(
        MigrationRefused, match="^(projection_cohort_changed|projection_source_invalid)$"
    ):
        initialize_admission(engine)
    assert snapshot(engine) == before


@pytest.mark.parametrize("phase", ["ddl", "fingerprint"])
def test_admission_migration_failure_rolls_back_all_new_schema_and_progress(
    legacy, monkeypatch, phase
):
    path, _, _ = legacy
    engine = complete(legacy)
    before = snapshot(engine)
    if phase == "ddl":
        original = admission_service._alembic

        def stop(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic migration stop")

        monkeypatch.setattr(admission_service, "_alembic", stop)
    else:
        original = admission_service._installed

        def stop(connection, shape):
            value = original(connection, shape)
            if value["_revision"] == ADMISSION:
                raise RuntimeError("synthetic migration stop")
            return value

        monkeypatch.setattr(admission_service, "_installed", stop)
    with pytest.raises(RuntimeError, match="^synthetic migration stop$"):
        initialize_admission(engine)
    assert snapshot(engine) == before
    preserved(path)
