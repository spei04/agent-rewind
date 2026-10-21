"""Bounded legacy presentations over actual synthetic publication/SQL scope."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from publication_fixture import CONTEXT, JOB, make_capture
from sqlalchemy import text

from agent_rewind.artifact_metadata import (
    ArtifactError,
    ArtifactObject,
    object_locator,
    record_verified,
    register_ref,
)
from agent_rewind.compare import compare
from agent_rewind.legacy_views import LegacyViews
from agent_rewind.models import Action, Intervention, canonical, digest
from agent_rewind.published_reader import PublishedRunReader
from agent_rewind.scoped_lineage import ResourceNotFound


@pytest.fixture
def published(settings, task):
    capture = make_capture(settings)
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    yield capture, run, intent, PublishedRunReader(capture.db.engine, capture.publisher.storage)
    capture.db.engine.dispose()


def view(published):
    return LegacyViews(published[3], 64 * 1024 * 1024)


def test_published_detail_files_and_failed_evaluation_shape(published):
    capture, run, _, _ = published
    views = view(published)
    value = views.run(CONTEXT, run)
    assert value["status"] == "complete" and value["success"] is False
    assert len(value["events"]) == 3 and value["evaluation"]["exit_code"] == 1
    assert value["id"] == run and value["locations"]
    assert "publication_schema" not in value and "generation" not in value
    assert views.files(CONTEXT, run, 2, "binary") == {
        "path": "binary",
        "content": "\x00�",
        "truncated": False,
    }
    items = {item["path"]: item for item in views.files(CONTEXT, run, 2)}
    assert items["script"]["mode"] == "0o755" and items["folder"]["bytes"] == 0
    for step, path in ((0, None), (4, None), (1, "absent")):
        with pytest.raises(ResourceNotFound):
            views.files(CONTEXT, run, step, path)


def test_comparison_is_pure_and_preserves_supported_response(published, task):
    capture, parent, _, reader = published
    branch = capture.run(
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    capture.publisher.publish(capture.intent(branch), capture.source)
    expected = compare(capture.db, capture.artifacts, parent, branch, 64 * 1024 * 1024)
    assert view(published).compare(CONTEXT, parent, branch) == expected
    assert expected["left_success"] is False and expected["right_success"] is True


def test_metadata_list_is_sql_only_even_when_unpublished(published, monkeypatch):
    capture, run, _, reader = published
    with capture.db.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM artifact_refs")
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("storage"))
    )
    rows = view(published).runs(CONTEXT)
    assert len(rows) == 1 and rows[0]["id"] == run
    assert "events" not in rows[0] and "evaluation" not in rows[0]
    with pytest.raises(ResourceNotFound):
        view(published).run(CONTEXT, run)
    reader.repositories.artifact_loader.assert_not_called()


@pytest.mark.parametrize(
    "column,value",
    [("created", "x" * 4096), ("created", b"short"), ("id", "a" * 32 + "\0" + "x" * 4096)],
)
def test_selected_list_identity_is_bounded_and_invalid_never_skipped(published, column, value):
    capture, run, _, _ = published
    with capture.db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(
            text(f"UPDATE records SET {column}=:v WHERE id=:r"), {"v": value, "r": run}
        )
        if column == "id":
            connection.execute(
                text("UPDATE resource_scopes SET resource_id=:v WHERE resource_id=:r"),
                {"v": value, "r": run},
            )
        connection.commit()
    with pytest.raises(ResourceNotFound):
        view(published).runs(CONTEXT)


def test_list_aggregate_limit_and_fresh_final_authority(published, monkeypatch):
    from agent_rewind import legacy_reads

    capture, run, _, _ = published
    monkeypatch.setattr(legacy_reads, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(ResourceNotFound):
        view(published).runs(CONTEXT)
    monkeypatch.undo()
    views = view(published)
    original = views._snapshot

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        with capture.db.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE project_memberships SET revoked_at='2026-01-01'")
        return result

    monkeypatch.setattr(views, "_snapshot", changed)
    with pytest.raises(ResourceNotFound):
        views.runs(CONTEXT)


def result_object(capture, job_id, result):
    data = canonical(result)
    key = digest(result)
    value = ArtifactObject(
        uuid4().hex,
        CONTEXT.project_id,
        key,
        object_locator(CONTEXT.project_id, key),
        1,
        len(data),
        datetime.now(UTC),
    )
    capture.publisher.storage.put_verified(value, data)
    with capture.db.engine.begin() as connection:
        record_verified(connection, value)
        register_ref(
            connection,
            project_id=CONTEXT.project_id,
            owner_kind="job",
            owner_id=job_id,
            role="result",
            artifact_id=value.id,
        )
        connection.execute(
            text("UPDATE jobs SET result=:digest WHERE id=:job"), {"digest": key, "job": job_id}
        )
    return value


def test_job_result_requires_scoped_descriptor_and_exact_target(published, monkeypatch):
    capture, run, _, reader = published
    result_object(capture, JOB, {"run_id": run})
    assert view(published).jobs(CONTEXT)[0]["result"] == {"run_id": run}
    with capture.db.engine.begin() as connection:
        connection.execute(text("DELETE FROM artifact_refs WHERE owner_kind='job'"))
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("storage"))
    )
    with pytest.raises(ResourceNotFound):
        view(published).jobs(CONTEXT)
    reader.repositories.artifact_loader.assert_not_called()


@pytest.mark.parametrize(
    "body", [{"run_id": "f" * 32}, {"study_id": "f" * 32}, {"run_id": "f" * 32, "extra": "private"}]
)
def test_job_result_unknown_or_wrong_target_refuses(published, body):
    capture, _, _, _ = published
    result_object(capture, JOB, body)
    with pytest.raises((ResourceNotFound, ArtifactError)):
        view(published).jobs(CONTEXT)


def test_job_final_receipt_retains_original_created_at(published, monkeypatch):
    capture, run, _, reader = published
    value = result_object(capture, JOB, {"run_id": run})
    original = reader.repositories.artifact_loader

    def changed(descriptor):
        data = original(descriptor)
        with capture.db.engine.begin() as connection:
            connection.execute(
                text("UPDATE artifact_objects SET created_at=:created WHERE id=:id"),
                {"created": (value.created_at + timedelta(seconds=1)).isoformat(), "id": value.id},
            )
        return data

    monkeypatch.setattr(reader.repositories, "artifact_loader", changed)
    with pytest.raises(ResourceNotFound):
        view(published).jobs(CONTEXT)


@pytest.mark.parametrize("change", ["descriptor", "target"])
def test_first_job_receipt_or_target_changed_during_second_load_refuses(
    published, task, monkeypatch, change
):
    capture, first_run, _, reader = published
    second_run = capture.run(
        task,
        first_run,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    second_job = capture.db.get(second_run, "run")["job_id"]
    first = result_object(capture, JOB, {"run_id": first_run})
    second = result_object(capture, second_job, {"run_id": second_run})
    with capture.db.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET created=CASE WHEN id=:first THEN 10 ELSE 5 END"), {"first": JOB}
        )
    original = reader.repositories.artifact_loader
    loads = []

    def changed(descriptor):
        assert capture.db.engine.pool.checkedout() == 0
        loads.append(descriptor.digest)
        data = original(descriptor)
        if descriptor.digest == second.digest:
            with capture.db.engine.begin() as connection:
                if change == "descriptor":
                    connection.execute(
                        text("UPDATE artifact_objects SET created_at=:created WHERE id=:id"),
                        {
                            "created": (first.created_at + timedelta(seconds=1)).isoformat(),
                            "id": first.id,
                        },
                    )
                else:
                    connection.execute(
                        text(
                            "UPDATE records SET data=json_set(data,'$.job_id',:job) WHERE id=:run"
                        ),
                        {"job": second_job, "run": first_run},
                    )
        return data

    monkeypatch.setattr(reader.repositories, "artifact_loader", changed)
    with pytest.raises((ResourceNotFound, ArtifactError)):
        view(published).jobs(CONTEXT)
    assert loads == [first.digest, second.digest]
