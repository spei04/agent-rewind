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
from agent_rewind.sqlite_ownership import acquire_progress, owned_begin, owned_connect


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
    with owned_begin(capture.db.engine) as connection:
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
    with owned_connect(capture.db.engine) as connection:
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
        with owned_begin(capture.db.engine) as connection:
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
    with owned_begin(capture.db.engine) as connection:
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
    with owned_begin(capture.db.engine) as connection:
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
        with owned_begin(capture.db.engine) as connection:
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
    with owned_begin(capture.db.engine) as connection:
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
            with owned_begin(capture.db.engine) as connection:
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


@pytest.mark.parametrize("kind", ["run", "job"])
@pytest.mark.parametrize("change", ["scope", "body", "phantom"])
def test_final_whole_source_receipts_refuse_earlier_mutation(published, monkeypatch, kind, change):
    import json

    from agent_rewind.legacy_reads import LegacyReads

    capture, first, _, _ = published
    other_job, second = "9" * 32, "8" * 32
    with owned_begin(capture.db.engine) as connection:
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
                "VALUES(:id,'run',5,:d,'queued',false,1,0)"
            ),
            {"id": other_job, "d": "0" * 64},
        )
        connection.execute(
            text("INSERT INTO records(id,kind,created,data) VALUES(:id,'run',5,:d)"),
            {"id": second, "d": json.dumps({"parent_id": None, "job_id": other_job})},
        )
        for k, ident in (("job", other_job), ("run", second)):
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:k,:id,:p)"),
                {"k": k, "id": ident, "p": CONTEXT.project_id},
            )
        connection.execute(text("UPDATE records SET created=10 WHERE id=:id"), {"id": first})
        connection.execute(text("UPDATE jobs SET created=10 WHERE id=:id"), {"id": JOB})
    original = LegacyReads.resource
    calls = 0

    def changed(self, k, ident):
        nonlocal calls
        result = original(self, k, ident)
        calls += 1
        if calls == 4:  # Second root of the final sequential closure pass.
            # Commit the injected test mutation after the final selected query.
            # The returned earlier Python value remains the original expectation.
            if change == "scope":
                self.connection.execute(
                    text("DELETE FROM artifact_refs WHERE owner_kind='run' AND owner_id=:id"),
                    {"id": first},
                )
                self.connection.execute(
                    text(
                        "DELETE FROM resource_scopes WHERE resource_kind='run' AND resource_id=:id"
                    ),
                    {"id": first},
                )
            elif change == "body":
                self.connection.execute(
                    text("UPDATE records SET data=json_set(data,'$.name','changed') WHERE id=:id"),
                    {"id": first},
                )
            else:
                new = "7" * 32
                self.connection.execute(
                    text("INSERT INTO records VALUES(:id,'run',1,:d)"),
                    {"id": new, "d": json.dumps({"parent_id": None, "job_id": JOB})},
                )
                self.connection.execute(
                    text("INSERT INTO resource_scopes VALUES('run',:id,:p)"),
                    {"id": new, "p": CONTEXT.project_id},
                )
            self.connection.commit()
        return result

    monkeypatch.setattr(LegacyReads, "resource", changed)
    with pytest.raises(ResourceNotFound):
        (view(published).runs if kind == "run" else view(published).jobs)(CONTEXT)
    assert calls == 4


def test_job_pre_post_artifact_closures_share_request_work_limit(published, monkeypatch):
    from agent_rewind import legacy_reads

    capture, run, _, reader = published
    result_object(capture, JOB, {"run_id": run})
    original_row = legacy_reads.ReadBudget.row
    budgets = []

    def counted(self, value):
        budgets.append(self)
        return original_row(self, value)

    monkeypatch.setattr(legacy_reads.ReadBudget, "row", counted)
    original_load = reader.repositories.artifact_loader

    def load(value):
        data = original_load(value)
        assert budgets and len({id(b) for b in budgets}) == 1
        monkeypatch.setattr(legacy_reads, "MAX_NODES", budgets[0].nodes)
        return data

    monkeypatch.setattr(reader.repositories, "artifact_loader", load)
    with pytest.raises(ResourceNotFound):
        view(published).jobs(CONTEXT)


def test_maximum_matching_relational_rowset_has_bounded_sql_work(published):
    import json

    from sqlalchemy import event

    from agent_rewind.legacy_reads import MAX_NODES, ReadBudget

    capture, _, _, _ = published
    budget = ReadBudget()
    entries = []
    for index in range(MAX_NODES):
        ident = f"{index:032x}"
        body = json.dumps({"job_id": JOB, "parent_id": None})
        entries.append({"id": ident, "body": body})
        budget.remember("run", {"id": ident, "created": 1.0, "body": body})
    with owned_begin(capture.db.engine) as connection:
        connection.execute(text("INSERT INTO records VALUES(:id,'run',1,:body)"), entries)
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:p)"),
            [{"id": v["id"], "p": CONTEXT.project_id} for v in entries],
        )
    binds = []

    def statement(conn, cursor, sql, parameters, context, many):
        if "source_receipts AS MATERIALIZED" in sql:
            binds.append(len(parameters))

    event.listen(capture.db.engine, "before_cursor_execute", statement)
    with owned_connect(capture.db.engine) as connection:
        count = 0

        def progress():
            nonlocal count
            count += 1000
            return int(count > 4_000_000)

        lease = acquire_progress(connection, owner=progress)
        lease.install(progress, 1000)
        try:
            budget.final(connection, CONTEXT)
        finally:
            lease.release()
        assert count < 4_000_000 and binds and max(binds) <= 64
        connection.execute(
            text("DELETE FROM resource_scopes WHERE resource_kind='run' AND resource_id=:id"),
            {"id": entries[0]["id"]},
        )
        with pytest.raises(ResourceNotFound):
            budget.final(connection, CONTEXT)
    event.remove(capture.db.engine, "before_cursor_execute", statement)
