"""Real coordinator composition with a required test-only future SQL fence."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from publication_fixture import CONTEXT, SQLFixtureWriter, make_capture
from sqlalchemy import create_engine, text
from test_artifact_metadata import prepare

from agent_rewind.artifact_metadata import ArtifactError, configure_artifact_engine
from agent_rewind.artifact_publication import UnavailableLiveWriter
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.models import Intervention
from agent_rewind.projection_publication import ProjectionPublicationWriter
from agent_rewind.projection_rows import insert_projection, read_index
from agent_rewind.run_projection import RunProjection


@pytest.fixture
def capture(settings):
    engine = create_engine(settings.database_url)
    configure_artifact_engine(engine)
    prepare(engine)
    initialize_projection(engine)
    value = make_capture(settings, prepared_engine=engine)
    value.publisher.writer = ProjectionPublicationWriter(SQLFixtureWriter())
    yield value
    engine.dispose()


def counts(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(text("SELECT count(*) FROM " + table)).scalar_one()
            for table in ("artifact_objects", "artifact_refs", "publication_roots", "run_index")
        )


def test_actual_graph_refs_root_projection_and_retry_share_one_commit(capture, task):
    parent = capture.run(task)
    intent = capture.intent(parent)
    capture.publisher.publish(intent, capture.source)
    with capture.db.engine.connect() as connection:
        first = read_index(connection, limit=3)
        assert first[0]["run_id"] == parent and first[0]["published_seq"] == 1
        assert first[0]["event_head"] == capture.db.get(parent, "run")["head"]
    before = counts(capture.db.engine)
    capture.publisher.publish(intent, capture.source)
    assert counts(capture.db.engine) == before
    child = capture.run(
        task, parent, Intervention(step=2, kind="tool_result", result={"output": "changed"})
    )
    child_root = capture.publisher.publish(capture.intent(child), capture.source)
    with capture.db.engine.connect() as connection:
        rows = read_index(connection, limit=3)
        by_id = {row["run_id"]: row for row in rows}
        assert by_id[parent] == first[0]
        assert by_id[child]["published_seq"] == 2
        assert by_id[child]["parent_id"] == parent
    assert capture.publisher.read(CONTEXT, child, child_root).root_digest


def test_projection_failure_rolls_back_all_refs_root_and_counter(capture, task, monkeypatch):
    import agent_rewind.projection_publication as module

    run = capture.run(task)
    intent = capture.intent(run)
    original = module.insert_projection

    def fail(connection, projection):
        original(connection, projection)
        assert connection.execute(text("SELECT count(*) FROM publication_roots")).scalar_one() == 1
        assert connection.execute(text("SELECT run_sequence FROM projects")).scalar_one() == 1
        raise ArtifactError("synthetic_projection_stop")

    monkeypatch.setattr(module, "insert_projection", fail)
    with pytest.raises(ArtifactError, match="synthetic_projection_stop"):
        capture.publisher.publish(intent, capture.source)
    assert counts(capture.db.engine) == (0, 0, 0, 0)
    with capture.db.engine.connect() as connection:
        assert connection.execute(text("SELECT run_sequence FROM projects")).scalar_one() == 0
    monkeypatch.setattr(module, "insert_projection", original)
    capture.publisher.publish(intent, capture.source)
    assert counts(capture.db.engine)[-2:] == (1, 1)


def test_unavailable_live_delegate_refuses_before_capture_or_byte_io(capture, task, monkeypatch):
    run = capture.run(task)
    capture.publisher.writer = ProjectionPublicationWriter(UnavailableLiveWriter())
    monkeypatch.setattr(
        capture.publisher, "_scoped_bytes", lambda *_: pytest.fail("unavailable writer read bytes")
    )
    with pytest.raises(ArtifactError, match="publication_live_fence_unavailable"):
        capture.intent(run)
    assert counts(capture.db.engine) == (0, 0, 0, 0)


def test_initial_projection_primitive_preserves_exact_sequence_and_refuses_changes(capture, task):
    run = capture.run(task)
    value = RunProjection(
        run,
        CONTEXT.project_id,
        datetime(2020, 1, 1, tzinfo=UTC),
        "incomplete",
        False,
        None,
        None,
        "unfenced_execution",
    )
    with capture.db.engine.begin() as connection:
        assert insert_projection(connection, value) == 1
    with capture.db.engine.begin() as connection:
        assert insert_projection(connection, value) == 1
    with (
        pytest.raises(ArtifactError, match="projection_conflict"),
        capture.db.engine.begin() as connection,
    ):
        insert_projection(connection, replace(value, status="failed"))
    with capture.db.engine.connect() as connection:
        assert connection.execute(text("SELECT run_sequence FROM projects")).scalar_one() == 1


def test_sqlite_fk_off_and_effective_autocommit_refuse_initial_writes(capture, task):
    run = capture.run(task)
    value = RunProjection(
        run, CONTEXT.project_id, datetime(2020, 1, 1, tzinfo=UTC), "failed", False, None, None, None
    )
    with capture.db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        with pytest.raises(ArtifactError, match="projection_constraints_required"):
            insert_projection(connection, value)
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    with (
        capture.db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection,
        connection.begin(),
        pytest.raises(ArtifactError, match="projection_transaction_required"),
    ):
        insert_projection(connection, value)
    assert counts(capture.db.engine) == (0, 0, 0, 0)


def test_equivalent_instants_persist_utc_and_sql_orders_by_time(capture, task):
    from datetime import timedelta, timezone

    first = capture.run(task)
    # Distinct scoped run identity; this primitive test does not claim graph publication.
    second = "e" * 32
    with capture.db.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO records SELECT :id,kind,created,data FROM records WHERE id=:original"
            ),
            {"id": second, "original": first},
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
            {"id": second, "project": CONTEXT.project_id},
        )
    earlier = RunProjection(
        first,
        CONTEXT.project_id,
        datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=2))),
        "failed",
        False,
        None,
        None,
        None,
    )
    later = replace(earlier, run_id=second, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    with capture.db.engine.begin() as connection:
        assert insert_projection(connection, earlier) == 1
        assert insert_projection(connection, later) == 2
    with capture.db.engine.begin() as connection:
        assert (
            insert_projection(
                connection, replace(earlier, created_at=earlier.created_at.astimezone(UTC))
            )
            == 1
        )
        stored = connection.execute(
            text("SELECT run_id,created_at FROM run_index ORDER BY created_at DESC,run_id DESC")
        ).all()
        assert [row[0] for row in stored] == [second, first]
        assert all(row[1].endswith("+00:00") for row in stored)
