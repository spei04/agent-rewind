"""Scoped SQL identity, duplicate/concurrent refs and immutable metadata methods."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import column, create_engine, event, select, table, text
from sqlalchemy.exc import IntegrityError
from test_ownership import FRESH

from agent_rewind import artifact_metadata
from agent_rewind.artifact_metadata import (
    ArtifactError,
    ArtifactObject,
    record_verified,
    register_ref,
    resolve_ref,
)
from agent_rewind.migrations import service
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.ownership_service import initialize_ownership

PROJECT = FRESH["project_id"]
OTHER = "7" * 32
OWNER = "2" * 32


def prepare(engine):
    service.install(engine, FRESH["installation_key"])
    initialize_ownership(engine, FRESH)
    initialize_artifacts(engine)


def owners(connection):
    connection.execute(
        text(
            "INSERT INTO projects(id,organization_id,name,created_at) "
            "SELECT :id,organization_id,'Other',created_at FROM projects WHERE id=:source"
        ),
        {"id": OTHER, "source": PROJECT},
    )
    for project, owner in [(PROJECT, OWNER), (OTHER, "3" * 32)]:
        connection.execute(
            text(
                "INSERT INTO resource_scopes(project_id,resource_kind,resource_id) "
                "VALUES(:project,'run',:id)"
            ),
            {"project": project, "id": owner},
        )


def object_value(project=PROJECT, *, legacy=False):
    digest = hashlib.sha256(b"frozen-content").hexdigest()
    return ArtifactObject(
        id=("a" if project == PROJECT else "b") * 32,
        project_id=project,
        digest=digest,
        locator=f"objects/{digest}" if legacy else f"objects/{project}/v1/{digest}",
        format_version=1,
        byte_count=14,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def reference(connection, value, **overrides):
    return register_ref(
        connection,
        **{
            "project_id": value.project_id,
            "owner_kind": "run",
            "owner_id": OWNER,
            "role": "task",
            "artifact_id": value.id,
            **overrides,
        },
    )


def resolve(connection, value, **overrides):
    return resolve_ref(
        connection,
        **{
            "project_id": value.project_id,
            "owner_kind": "run",
            "owner_id": OWNER,
            "role": "task",
            "digest": value.digest,
            **overrides,
        },
    )


@pytest.fixture
def object_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'objects.sqlite'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi, record):
        dbapi.execute("PRAGMA foreign_keys=ON")

    prepare(engine)
    with engine.begin() as connection:
        owners(connection)
    yield engine
    engine.dispose()


def test_verified_metadata_exact_reentry_and_duplicate_ref(object_db):
    value = object_value()
    with object_db.begin() as c:
        assert record_verified(c, value) == value
        assert record_verified(c, value) == value
        assert resolve(c, value) is None
        assert reference(c, value) is True
        assert reference(c, value) is False
        assert resolve(c, value) == value
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 1


@pytest.mark.parametrize(
    "field,changed",
    [
        ("id", "f" * 32),
        ("byte_count", 15),
        ("created_at", datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_reentry_conflict_never_mutates_original(object_db, field, changed):
    value = object_value()
    with object_db.begin() as c:
        record_verified(c, value)
    with pytest.raises(ArtifactError, match="artifact_metadata_conflict"), object_db.begin() as c:
        record_verified(c, replace(value, **{field: changed}))
    with object_db.connect() as c:
        row = c.execute(text("SELECT id,byte_count,created_at FROM artifact_objects")).one()
        assert row[0] == value.id and row[1] == value.byte_count


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_id": OTHER},
        {"owner_id": "3" * 32},
        {"owner_kind": "job"},
        {"artifact_id": "f" * 32},
    ],
)
def test_composite_constraints_reject_foreign_or_missing_object_owner(object_db, overrides):
    value = object_value()
    with object_db.begin() as c:
        record_verified(c, value)
    with pytest.raises(IntegrityError), object_db.begin() as c:
        reference(c, value, **overrides)


def test_equal_bytes_have_independent_project_identity_and_scoped_reads(object_db):
    left, right = object_value(legacy=True), object_value(OTHER, legacy=True)
    with object_db.begin() as c:
        record_verified(c, left)
        record_verified(c, right)
        reference(c, left)
        reference(c, right, owner_id="3" * 32)
        assert left.id != right.id and left.locator == right.locator
        assert resolve(c, left) == left
        assert resolve(c, left, project_id=OTHER) is None
        assert resolve(c, left, owner_id="3" * 32) is None
        assert resolve(c, left, role="workspace") is None
        assert resolve(c, right, owner_id="3" * 32) == right


def test_concurrent_same_object_and_ref_are_single_logical_rows(object_db):
    value = object_value()
    gate = Barrier(2)

    def contender():
        gate.wait(timeout=5)
        with object_db.begin() as c:
            record_verified(c, value)
            return reference(c, value)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(contender) for _ in range(2)]
        assert sorted(f.result(10) for f in futures) == [False, True]
    with object_db.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_objects").scalar_one() == 1
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 1


def test_disabled_sqlite_constraints_cannot_publish(object_db):
    with object_db.connect() as c:
        c.exec_driver_sql("PRAGMA foreign_keys=OFF")
        with pytest.raises(ArtifactError, match="constraints_required"):
            record_verified(c, object_value())


def test_fresh_default_off_connection_refuses_ref_without_inserting(object_db):
    value = object_value()
    with object_db.begin() as connection:
        record_verified(connection, value)
    fresh_engine = create_engine(object_db.url)
    try:
        with fresh_engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            with pytest.raises(ArtifactError, match="constraints_required"):
                reference(connection, value, project_id=OTHER, owner_id="3" * 32)
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0
            )
    finally:
        fresh_engine.dispose()


def test_configure_before_first_use_enables_each_new_connection(object_db):
    from agent_rewind.artifact_metadata import configure_artifact_engine

    fresh_engine = create_engine(object_db.url)
    configure_artifact_engine(fresh_engine)
    configure_artifact_engine(fresh_engine)
    try:
        with fresh_engine.connect() as first, fresh_engine.connect() as second:
            assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        fresh_engine.dispose()


@pytest.mark.parametrize(
    "field,corrupt",
    [
        ("id", "a" * 32 + "\0" + "x" * 1024 * 1024),
        ("project_id", "x" * 1024 * 1024),
        ("digest", "x" * 1024 * 1024),
        ("locator", "x" * 1024 * 1024),
        ("format_version", "x" * 1024 * 1024),
        ("byte_count", "x" * 1024 * 1024),
        ("created_at", "2026-01-01T00:00:00+00:00" + "\0" + "x" * 1024 * 1024),
        ("created_at", b"x" * 1024 * 1024),
    ],
    ids=("id-nul", "project", "digest", "locator", "version", "size", "date-nul", "date-blob"),
)
def test_readback_bounds_every_cell_without_dropping_candidate(
    object_db, monkeypatch, field, corrupt
):
    value = object_value()
    with object_db.begin() as connection:
        record_verified(connection, value)
    # Model corrupt persisted metadata, including historical SQLite dynamic cells.
    # Enforcement is restored before invoking the production write primitive.
    with object_db.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        objects = table("artifact_objects", column(field))
        connection.execute(objects.update().values({field: corrupt}))
        connection.commit()
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        seen = []
        original = artifact_metadata._object

        def bounded(row):
            seen.append(dict(row))
            assert set(row) == {
                "id",
                "project_id",
                "digest",
                "locator",
                "format_version",
                "byte_count",
                "created_at",
            }
            assert all(item is None for item in row.values())
            return original(row)

        monkeypatch.setattr(artifact_metadata, "_object", bounded)
        with pytest.raises(ArtifactError, match="^artifact_metadata_invalid$"):
            record_verified(connection, value)
        assert len(seen) == 1  # The invalid row was not filtered into apparent absence.
        assert connection.exec_driver_sql("SELECT count(*) FROM artifact_objects").scalar_one() == 1
        assert connection.execute(select(objects.c[field])).scalar_one() == corrupt


@pytest.mark.parametrize("corrupt_first", [False, True])
def test_both_id_and_scoped_content_candidates_remain_conflicts(
    object_db, monkeypatch, corrupt_first
):
    expected = object_value()
    foreign_id = replace(object_value(OTHER), id=expected.id)
    scoped_content = replace(expected, id="f" * 32)
    with object_db.begin() as connection:
        record_verified(connection, foreign_id)
        record_verified(connection, scoped_content)
        if corrupt_first:
            connection.execute(
                text("UPDATE artifact_objects SET created_at=:bad WHERE id=:id"),
                {"bad": "x" * 1024 * 1024, "id": foreign_id.id},
            )

        def unexpected_parse(row):
            pytest.fail("Both collision candidates must survive until the cardinality check")

        with monkeypatch.context() as patch:
            patch.setattr(artifact_metadata, "_object", unexpected_parse)
            with pytest.raises(ArtifactError, match="^artifact_metadata_conflict$"):
                record_verified(connection, expected)
        rows = connection.execute(
            text("SELECT id,project_id,digest FROM artifact_objects ORDER BY id")
        ).all()
        assert rows == [
            (foreign_id.id, OTHER, expected.digest),
            (scoped_content.id, PROJECT, expected.digest),
        ]
        # Identical content in another project is not a scoped-content candidate.
        assert record_verified(connection, scoped_content) == scoped_content


@pytest.mark.parametrize(
    "field,bad",
    [("created_at", "not-a-timestamp"), ("created_at", b"bad"), ("byte_count", 1.5)],
)
def test_bounded_malformed_candidate_preserves_fixed_invalid_error(object_db, field, bad):
    value = object_value()
    with object_db.begin() as connection:
        record_verified(connection, value)
        objects = table("artifact_objects", column(field))
        connection.execute(objects.update().values({field: bad}))
        with pytest.raises(ArtifactError, match="^artifact_metadata_invalid$"):
            record_verified(connection, value)
