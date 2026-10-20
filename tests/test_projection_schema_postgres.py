"""Real PostgreSQL catalog/constraint gate, separate from cohort backfill."""

import json
from pathlib import Path

import pytest
import test_migrations_postgres as migration_tests
from postgres_control import wait_for_database_drain
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_artifact_postgres import prepare_postgres
from test_projection_schema import FOREIGN, OTHER, PARENT, PROJECT, RUN, insert

from agent_rewind.migrations import service
from agent_rewind.migrations.compatibility import (
    ReleaseProfile,
    check_schema_compatibility,
    load_release_profile,
)
from agent_rewind.migrations.projection_schema import create_projection_schema
from agent_rewind.migrations.schema import ARTIFACTS, PROJECTION, catalog

pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL projection schema"
)
PROFILE = (
    Path(__file__).parents[1] / "agent_rewind/migrations/profiles/postgresql16_projection.json"
)


def test_postgres_projection_profile_requires_independent_freeze(pg):
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    with service.migration_transaction(pg["owner"]) as connection:
        create_projection_schema(connection)
        shape = catalog(connection)
        if not PROFILE.is_file():
            encoded = json.dumps(shape, sort_keys=True, separators=(",", ":"))
            assert len(encoded.encode()) <= 128 * 1024
            pytest.fail(
                "SYNTHETIC_PROJECTION_POSTGRES16_CATALOG_REVIEW_REQUIRED=" + encoded,
                pytrace=False,
            )
        assert shape == json.loads(PROFILE.read_text())


@pytest.fixture
def projected(pg):
    if not PROFILE.is_file():
        pytest.skip("Hosted capture requires independent literal profile review")
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    with service.migration_transaction(pg["owner"]) as connection:
        service._alembic(connection, "upgrade", PROJECTION)
    with pg["owner"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,'Other',created_at FROM projects WHERE id=:project"
            ),
            {"other": OTHER, "project": PROJECT},
        )
        for run, project in ((RUN, PROJECT), (PARENT, PROJECT), (FOREIGN, OTHER)):
            connection.execute(
                text("INSERT INTO records VALUES(:id,'run',1700000000.125,'{}')"),
                {"id": run},
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
                {"id": run, "project": project},
            )
    return pg["owner"]


def test_postgres_scope_parent_sequence_and_checks(projected):
    with projected.begin() as connection:
        insert(connection, run_id=FOREIGN, project_id=OTHER)
        insert(connection, run_id=PARENT, published_seq=2)
    for updates in (
        {"project_id": OTHER},
        {"resource_kind": "job"},
        {"parent_id": FOREIGN},
        {"run_id": "g" * 32},
        {"event_head": "a" * 63},
        {"published_seq": 0},
        {"published_seq": 2},
        {"status": "failed"},
        {"projection_reason": "raw error"},
    ):
        with pytest.raises(IntegrityError), projected.begin() as connection:
            insert(connection, **updates)
    with projected.begin() as connection:
        insert(connection, parent_id=PARENT)
    with projected.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM run_index").scalar_one() == 3


def test_postgres_ddl_rollback_and_old_reader_refusal(pg):
    prepare_postgres(pg)
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    with (
        pytest.raises(RuntimeError, match="synthetic"),
        service.migration_transaction(pg["owner"]) as connection,
    ):
        before = catalog(connection)
        service._alembic(connection, "upgrade", PROJECTION)
        raise RuntimeError("synthetic stop")
    with pg["owner"].connect() as connection:
        assert catalog(connection) == before
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == ARTIFACTS
        )
    wait_for_database_drain(pg["control"], pg["owner"].url.database)
    with service.migration_transaction(pg["owner"]) as connection:
        service._alembic(connection, "upgrade", PROJECTION)
    value = load_release_profile().model_dump(mode="json")
    value["revisions"] = [r for r in value["revisions"] if r["revision"] != PROJECTION]
    old = ReleaseProfile.model_validate_json(json.dumps(value))
    with pg["owner"].connect() as connection:
        assert check_schema_compatibility(connection, old).code == "schema_incompatible"
