"""Original-source and bounded catalog checks before literal ar6 acceptance."""

import json

import pytest
import test_run_projection_backfill as backfill_tests
from legacy_fixture import assert_preserved_rows, read_manifest, sha256
from sqlalchemy import inspect, text

from agent_rewind import projection_source
from agent_rewind.migrations import service
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.inputs import SOURCE_QUERIES, source_digest
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.migrations.schema import ADMISSION, COLUMNS, MigrationRefused, catalog

legacy = backfill_tests.legacy


def test_historical_digest_rows_objects_and_projection_survive_additive_ddl(legacy):
    path, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source, batch_size=1)
    backfill_run_index(engine, source, batch_size=1)
    with engine.connect() as connection:
        before = source_digest(connection)
        previous = catalog(connection)
        projection = connection.exec_driver_sql("SELECT * FROM run_index ORDER BY run_id").all()
        progress = connection.exec_driver_sql(
            "SELECT * FROM migration_progress ORDER BY revision,phase"
        ).all()
        counters = connection.exec_driver_sql("SELECT id,run_sequence FROM projects").all()
    with service.migration_transaction(engine) as connection:
        service._alembic(connection, "upgrade", ADMISSION)
        current = catalog(connection)
        assert len(current) == 17
        assert set(current) - set(previous) == {"operations", "operation_keys"}
        for table in previous:
            if table != "jobs":
                assert current[table] == previous[table]
        assert current["jobs"]["columns"][:13] == previous["jobs"]["columns"]
        assert source_digest(connection) == before
        assert (
            connection.exec_driver_sql("SELECT * FROM run_index ORDER BY run_id").all()
            == projection
        )
        assert (
            connection.exec_driver_sql(
                "SELECT * FROM migration_progress ORDER BY revision,phase"
            ).all()
            == progress
        )
        assert connection.exec_driver_sql("SELECT id,run_sequence FROM projects").all() == counters
        assert connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 245000
        assert [c["name"] for c in inspect(connection).get_columns("jobs")][:13] == [
            column[0] for column in COLUMNS["jobs"]
        ]
    assert_preserved_rows(path)
    for value in read_manifest()["objects"].values():
        assert (
            sha256((path.parent / "objects" / value["address"]).read_bytes())
            == value["ciphertext_sha256"]
        )
    # The original query must not fetch any later configuration text at all.
    assert "*" not in SOURCE_QUERIES["jobs"]


def test_eighteenth_table_is_refused_by_catalog(legacy):
    _, engine, _ = legacy
    with service.migration_transaction(engine) as connection:
        service._alembic(connection, "upgrade", ADMISSION)
        connection.exec_driver_sql("CREATE TABLE eighteenth(value INTEGER)")
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)


def test_job_extension_is_not_accepted_under_an_old_revision(legacy):
    _, engine, _ = legacy
    with service.migration_transaction(engine) as connection:
        service._alembic(connection, "upgrade", ADMISSION)
        connection.execute(text("UPDATE alembic_version SET version_num='ar_0005_run_index'"))
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)


def test_oversized_completed_cohort_returns_fixed_migration_refusal(legacy):
    body = json.dumps("x" * (2 * 1024 * 1024 + 1))
    _, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET data=:body WHERE id=:id"), {"body": body, "id": "1" * 32}
        )
    with engine.connect() as connection:
        before = catalog(connection)
    with pytest.raises(MigrationRefused) as refused:
        initialize_admission(engine)
    assert refused.value.code in {"projection_source_invalid", "projection_source_limit"}
    assert refused.value.__suppress_context__ is True
    assert body not in str(refused.value)
    with engine.connect() as connection:
        assert catalog(connection) == before
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == "ar_0005_run_index"
        )
        assert (
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": "1" * 32}
            ).scalar_one()
            == body
        )


def test_capture_query_exhaustion_returns_fixed_refusal_without_ddl(legacy, monkeypatch):
    _, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source)
    with engine.connect() as connection:
        before = catalog(connection), source_digest(connection)
    monkeypatch.setattr(projection_source, "MAX_CAPTURE_QUERIES", 0)
    with pytest.raises(MigrationRefused, match="^projection_query_limit$") as refused:
        initialize_admission(engine)
    assert refused.value.__suppress_context__ is True
    with engine.connect() as connection:
        assert (catalog(connection), source_digest(connection)) == before
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == "ar_0005_run_index"
        )
