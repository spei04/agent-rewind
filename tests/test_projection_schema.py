"""Run index DDL constraints and literal-catalog boundary, independent of backfill."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from test_artifact_metadata import OTHER, PROJECT, prepare

from agent_rewind.migrations import service
from agent_rewind.migrations.compatibility import (
    ReleaseProfile,
    check_schema_compatibility,
    load_release_profile,
)
from agent_rewind.migrations.schema import (
    ARTIFACTS,
    PROJECTION,
    MigrationRefused,
    catalog,
    installed_profile,
    verify_baseline,
)

RUN = "2" * 32
PARENT = "3" * 32
FOREIGN = "4" * 32


@pytest.fixture
def projection_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'projection.sqlite'}")
    prepare(engine)
    with service.migration_transaction(engine) as connection:
        service._alembic(connection, "upgrade", PROJECTION)
    with engine.begin() as connection:
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
    yield engine
    engine.dispose()


def insert(connection, **updates):
    values = {
        "run_id": RUN,
        "project_id": PROJECT,
        "resource_kind": "run",
        "created_at": "2026-01-01T00:00:00+00:00",
        "status": "complete",
        "branchable": True,
        "parent_id": None,
        "event_head": "a" * 64,
        "published_seq": 1,
        "projection_reason": None,
    }
    values.update(updates)
    connection.execute(
        text(
            "INSERT INTO run_index ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )


def test_only_projection_and_counter_are_added(projection_engine):
    with projection_engine.connect() as connection:
        shape = catalog(connection)
        verify_baseline(shape, "sqlite", versioned=True, projection=True)
        assert shape == installed_profile("sqlite", PROJECTION)
        old = installed_profile("sqlite", ARTIFACTS)
        assert set(shape) - set(old) == {"run_index"}
        for table, fields in old.items():
            if table != "projects":
                assert shape[table] == fields
        assert shape["projects"]["columns"][:-1] == old["projects"]["columns"]
        assert shape["projects"]["columns"][-1][:4] == ["run_sequence", "BIGINT", False, "0"]
        assert connection.exec_driver_sql(
            "SELECT run_sequence FROM projects ORDER BY id"
        ).all() == [(0,), (0,)]
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == PROJECTION
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"resource_kind": None},
        {"resource_kind": "job"},
        {"run_id": "G" * 32},
        {"run_id": b"2" * 32},
        {"project_id": OTHER},
        {"project_id": None},
        {"parent_id": FOREIGN},
        {"parent_id": "g" * 32},
        {"event_head": "f" * 63},
        {"event_head": b"a" * 64},
        {"status": "success"},
        {"status": "failed"},
        {"branchable": 2},
        {"published_seq": 0},
        {"published_seq": -1},
        {"published_seq": 1.5},
        {"published_seq": "bad"},
        {"projection_reason": "raw error"},
    ],
)
def test_invalid_projection_fails_before_publication(projection_engine, updates):
    with pytest.raises(IntegrityError), projection_engine.begin() as connection:
        insert(connection, **updates)
    with projection_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM run_index").scalar_one() == 0


def test_parent_scope_and_unique_commit_sequence(projection_engine):
    with projection_engine.begin() as connection:
        insert(connection, run_id=PARENT)
        insert(connection, parent_id=PARENT, published_seq=2)
        insert(connection, run_id=FOREIGN, project_id=OTHER)
    with pytest.raises(IntegrityError), projection_engine.begin() as connection:
        connection.execute(
            text("UPDATE run_index SET published_seq=1 WHERE run_id=:id"), {"id": RUN}
        )


@pytest.mark.parametrize("value", [-1, 0.5, "invalid", None])
def test_project_counter_rejects_invalid_values(projection_engine, value):
    with pytest.raises(IntegrityError), projection_engine.begin() as connection:
        connection.execute(
            text("UPDATE projects SET run_sequence=:value WHERE id=:project"),
            {"value": value, "project": PROJECT},
        )


@pytest.mark.parametrize(
    "definition",
    [
        "project_id,created_at,run_id",
        "project_id DESC,created_at DESC,run_id DESC",
        "project_id,run_id DESC,created_at DESC",
        "project_id,created_at DESC,run_id DESC,branchable",
        "project_id,created_at COLLATE NOCASE DESC,run_id DESC",
    ],
)
def test_sqlite_direction_allowance_is_exact(projection_engine, definition):
    with projection_engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX run_index_project_created_run")
        connection.exec_driver_sql(
            "CREATE INDEX run_index_project_created_run ON run_index(" + definition + ")"
        )
    with (
        pytest.raises(MigrationRefused, match="schema_incompatible"),
        projection_engine.connect() as connection,
    ):
        catalog(connection)


def test_unrelated_desc_index_is_not_enabled(projection_engine):
    with projection_engine.begin() as connection:
        connection.exec_driver_sql("CREATE INDEX wrong_direction ON projects(name DESC)")
    with (
        pytest.raises(MigrationRefused, match="schema_incompatible"),
        projection_engine.connect() as connection,
    ):
        catalog(connection)


def test_ddl_rollback_retains_previous_shape(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.sqlite'}")
    try:
        prepare(engine)
        with engine.connect() as connection:
            before = catalog(connection)
        with (
            pytest.raises(RuntimeError, match="synthetic"),
            service.migration_transaction(engine) as connection,
        ):
            service._alembic(connection, "upgrade", PROJECTION)
            raise RuntimeError("synthetic stop before commit")
        with engine.connect() as connection:
            assert catalog(connection) == before
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == ARTIFACTS
            )
    finally:
        engine.dispose()


def test_old_reader_refuses_new_revision_without_writes(projection_engine):
    profile = load_release_profile()
    old = ReleaseProfile.model_validate_json(
        json.dumps(
            {
                **profile.model_dump(),
                "revisions": [
                    r.model_dump() for r in profile.revisions if r.revision != PROJECTION
                ],
            }
        )
    )
    with projection_engine.connect() as connection:
        before = catalog(connection)
        result = check_schema_compatibility(connection, old)
        assert result.code == "schema_incompatible"
        assert catalog(connection) == before


@pytest.mark.parametrize("mutation", ["missing_ownership", "missing_projection", "mode"])
def test_new_manifest_cannot_omit_backfill_or_enable_admission(mutation):
    value = load_release_profile().model_dump(mode="json")
    profile = next(p for p in value["revisions"] if p["revision"] == PROJECTION)
    if mutation == "mode":
        profile["mode"] = "ready"
    else:
        profile["required_completed_backfills"].pop(0 if mutation == "missing_ownership" else 1)
    with pytest.raises(ValidationError):
        ReleaseProfile.model_validate_json(json.dumps(value))


def test_existing_foreign_parent_cannot_cross_project(projection_engine):
    with projection_engine.begin() as connection:
        insert(connection, run_id=FOREIGN, project_id=OTHER)
    with pytest.raises(IntegrityError), projection_engine.begin() as connection:
        insert(connection, parent_id=FOREIGN)


def test_scope_does_not_replace_required_source_record(projection_engine):
    with projection_engine.begin() as connection:
        connection.execute(text("DELETE FROM records WHERE id=:id"), {"id": RUN})
    with pytest.raises(IntegrityError), projection_engine.begin() as connection:
        insert(connection)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_head", "a" * 64),
        ("run_id", RUN),
        ("project_id", PROJECT),
        ("parent_id", PARENT),
    ],
)
@pytest.mark.parametrize("location", ["suffix", "earlier", "terminal"])
def test_nul_cannot_bypass_new_hexadecimal_checks(projection_engine, field, value, location):
    with projection_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    with pytest.raises(IntegrityError) as error, projection_engine.begin() as connection:
        malformed = {
            "suffix": value + chr(0) + "not-hex",
            "earlier": value[:1] + chr(0) + value[2:],
            "terminal": value[:-1] + chr(0),
        }[location]
        insert(connection, **{field: malformed})
    # The new CHECK itself refuses, rather than relying on a missing FK target.
    assert error.value.orig.sqlite_errorname == "SQLITE_CONSTRAINT_CHECK"
    with projection_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM run_index").scalar_one() == 0


@pytest.mark.parametrize("modifiers", [("desc",), ("asc", "nulls_first")])
def test_reflected_index_sorting_preserves_modifiers_through_json(
    projection_engine, monkeypatch, modifiers
):
    from agent_rewind.migrations import schema

    original_inspect = schema.inspect

    def reflected(connection):
        inspector = original_inspect(connection)
        original_indexes = inspector.get_indexes

        def indexes(table, **kwargs):
            values = [dict(value) for value in original_indexes(table, **kwargs)]
            if table == "run_index":
                assert len(values) == 1
                # Same tuple-valued reflection boundary observed in PostgreSQL CI.
                values[0]["column_sorting"] = {"created_at": modifiers}
            return values

        monkeypatch.setattr(inspector, "get_indexes", indexes)
        return inspector

    monkeypatch.setattr(schema, "inspect", reflected)
    with projection_engine.connect() as connection:
        shape = schema.catalog(connection)
    assert shape["run_index"]["indexes"][0]["column_sorting"] == {"created_at": list(modifiers)}
    assert json.loads(json.dumps(shape)) == shape
