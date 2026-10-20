"""Bounded SQL capture and actual interrupted Engine evidence, without migration writes."""

from copy import deepcopy

import pytest
from cryptography.fernet import Fernet
from publication_fixture import CONTEXT, make_capture
from sqlalchemy import text

from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.models import Intervention
from agent_rewind.projection_evidence import FrozenLegacySource, prepare_evidence
from agent_rewind.projection_source import QueryBudget, read_cohort, readonly_source


@pytest.fixture
def capture(settings):
    value = make_capture(settings)
    yield value
    value.db.engine.dispose()


def cohort(capture):
    with readonly_source(capture.db.engine, QueryBudget()) as connection:
        return read_cohort(connection)


def reader(capture):
    def fetch(project, owner, role, key, limit):
        assert project == CONTEXT.project_id
        assert capture.db.engine.pool.checkedout() == 0
        data = capture.artifacts.get(key)
        assert len(data) <= limit
        return data

    return fetch


def scope_interrupted(capture, run):
    with capture.db.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('run',:run,:project)"),
            {"run": run, "project": CONTEXT.project_id},
        )


def test_cohort_is_parent_first_and_rechecks_original_identity(capture, task):
    parent = capture.run(task)
    child = capture.run(
        task, parent, Intervention(step=2, kind="tool_result", result={"output": "changed"})
    )
    source = cohort(capture)
    assert source.order == (parent, child)
    prepared = prepare_evidence(source, reader(capture))
    assert [r.run_id for r in prepared.rows] == [parent, child]
    assert all(r.status == "complete" and r.branchable for r in prepared.rows)
    assert prepared.identity == cohort(capture).identity
    assert prepared.bytes_read > 0
    with capture.db.engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": parent}
        )
    assert cohort(capture).identity != prepared.identity


@pytest.mark.parametrize("when", ["initial", "propose", "event-crash", "event-error"])
def test_actual_engine_interruption_shapes(capture, task, monkeypatch, when):
    stored = []
    original_add = capture.db.add
    original_save = capture.db.save_event

    class Stopped(BaseException):
        pass

    def add(kind, data, record_id=None):
        result = original_add(kind, data, record_id)
        stored.append(result)
        if when == "initial":
            raise Stopped()
        return result

    def propose(*_):
        raise RuntimeError("synthetic failure")

    def save(*args):
        original_save(*args)
        if when == "event-crash":
            raise Stopped()
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(capture.db, "add", add)
    if when == "propose":
        monkeypatch.setattr(capture.engine.policy, "propose", propose)
    elif when.startswith("event"):
        monkeypatch.setattr(capture.db, "save_event", save)
    with pytest.raises((Stopped, RuntimeError)):
        capture.run(task)
    run = stored[0]
    scope_interrupted(capture, run)
    source = cohort(capture)
    original = deepcopy(source.captures[run][1])
    prepared = prepare_evidence(source, reader(capture))
    row = prepared.rows[0]
    assert row.status == ("failed" if when in {"propose", "event-error"} else "incomplete")
    assert not row.branchable
    assert original["manifest"]["steps"] == 0 and original["manifest"]["head"] is None
    events = capture.db.event_refs(run)
    assert row.event_head == (events[-1]["hash"] if events else None)
    assert cohort(capture).captures[run][1] == original


def test_foreign_parent_scope_refuses_before_any_operator_reader(capture, task):
    parent = capture.run(task)
    child = capture.run(task, parent, Intervention(step=2, kind="tool_result", result={"x": 1}))
    with capture.db.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": parent}
        )
    with pytest.raises(ArtifactError, match="projection_source_invalid"):
        cohort(capture)
    assert capture.db.get(child, "run")["parent_id"] == parent


def test_cohort_query_and_metadata_limits(capture, task, monkeypatch):
    import agent_rewind.projection_source as module

    capture.run(task)
    with (
        readonly_source(capture.db.engine, QueryBudget()) as connection,
        pytest.raises(ArtifactError, match="projection_cohort_limit"),
    ):
        read_cohort(connection, byte_limit=10)
    monkeypatch.setattr(module, "MAX_CAPTURE_QUERIES", 1)
    with pytest.raises(ArtifactError, match="projection_query_limit"):
        cohort(capture)
    with capture.db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0


def test_oversized_dynamic_source_cell_refuses_before_parser(capture, task, monkeypatch):
    import agent_rewind.projection_source as module

    capture.run(task)
    with capture.db.engine.begin() as connection:
        connection.execute(text("UPDATE records SET created=:value"), {"value": "x" * 4096})
    monkeypatch.setattr(module, "MAX_RECORD_BYTES", 2048)
    monkeypatch.setattr(
        module, "source_digest", lambda *_: pytest.fail("oversized row reached source parser")
    )
    with pytest.raises(ArtifactError, match="projection_source_limit"):
        cohort(capture)


def test_operator_byte_reader_is_bounded_and_corruption_refuses(capture, settings, task):
    capture.run(task)
    source = cohort(capture)
    local = FrozenLegacySource(
        settings.data_dir, Fernet(settings.encryption_key.get_secret_value().encode())
    )
    prepared = prepare_evidence(source, local)
    assert prepared.rows[0].status == "complete"
    manifest = source.captures[source.order[0]][1]["manifest"]
    path = settings.data_dir / "objects" / manifest["task_ref"]
    with pytest.raises(ArtifactError, match="projection_evidence_invalid"):
        local(CONTEXT.project_id, source.order[0], "task", manifest["task_ref"], 1)
    path.write_bytes(b"synthetic corrupt ciphertext")
    with pytest.raises(ArtifactError, match="projection_evidence_invalid"):
        prepare_evidence(source, local)


def test_aggregate_evidence_limit_is_passed_before_reader(capture, task, monkeypatch):
    import agent_rewind.projection_evidence as module

    capture.run(task)
    source = cohort(capture)
    monkeypatch.setattr(module, "MAX_CAPTURE_BYTES", 1)
    seen = []

    def limited(project, owner, role, key, limit):
        seen.append(limit)
        assert limit == 1
        return b"xx"

    with pytest.raises(ArtifactError, match="projection_evidence_limit"):
        prepare_evidence(source, limited)
    assert seen == [1]
