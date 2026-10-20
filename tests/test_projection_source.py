"""Bounded SQL capture and actual interrupted Engine evidence, without migration writes."""

import json

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
    original = json.loads(source.captures[run][1])
    prepared = prepare_evidence(source, reader(capture))
    row = prepared.rows[0]
    assert row.status == ("failed" if when in {"propose", "event-error"} else "incomplete")
    assert not row.branchable
    assert original["manifest"]["steps"] == 0 and original["manifest"]["head"] is None
    events = capture.db.event_refs(run)
    assert row.event_head == (events[-1]["hash"] if events else None)
    assert json.loads(cohort(capture).captures[run][1]) == original


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
    manifest = json.loads(source.captures[source.order[0]][1])["manifest"]
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


@pytest.mark.parametrize("target", ["resource_scopes", "projects"])
def test_nul_suffix_identity_refuses_before_identity_materialization(capture, task, target):
    from sqlalchemy import event

    capture.run(task)
    with capture.db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        value = "e" * 32 + "\0" + "x" * 4096
        if target == "resource_scopes":
            connection.execute(
                text("UPDATE resource_scopes SET resource_id=:value WHERE resource_kind='run'"),
                {"value": value},
            )
        else:
            connection.execute(text("UPDATE projects SET id=:value"), {"value": value})
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    def before(connection, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        assert not normalized.startswith(
            "select resource_kind,resource_id,project_id from resource_scopes"
        )
        assert not normalized.startswith("select id,organization_id from projects")

    event.listen(capture.db.engine, "before_cursor_execute", before)
    try:
        with pytest.raises(ArtifactError, match="projection_source_invalid"):
            cohort(capture)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", before)


@pytest.mark.parametrize("mutation", ["future_capture", "project", "order"])
def test_reader_cannot_mutate_later_cohort_evidence(capture, task, mutation):
    from dataclasses import FrozenInstanceError

    parent = capture.run(task)
    child = capture.run(task, parent, Intervention(step=2, kind="tool_result", result={"x": 1}))
    source = cohort(capture)
    before = source.captures[child]
    attempted = False

    def fetch(project, owner, role, key, limit):
        nonlocal attempted
        if not attempted:
            attempted = True
            if mutation == "order":
                with pytest.raises(FrozenInstanceError):
                    source.order = tuple(reversed(source.order))
            else:
                project_id, encoded = before
                body = json.loads(encoded)
                if mutation == "future_capture":
                    body["manifest"]["created"] += 1000
                else:
                    project_id = "e" * 32
                with pytest.raises(TypeError):
                    source.captures[child] = (project_id, json.dumps(body).encode())
        return reader(capture)(project, owner, role, key, limit)

    prepared = prepare_evidence(source, fetch)
    assert attempted and source.captures[child] == before
    expected = json.loads(before[1])["manifest"]["created"]
    from agent_rewind.run_projection import utc_created

    assert prepared.rows[1].created_at == utc_created(expected)
    assert prepared.rows[1].project_id == before[0]
    assert prepared.identity == cohort(capture).identity


def test_decoded_capture_counts_toward_combined_metadata_cap(capture, task, monkeypatch):
    import agent_rewind.projection_evidence as module

    capture.run(task)
    source = cohort(capture)
    encoded = source.captures[source.order[0]][1]
    monkeypatch.setattr(module, "MAX_COHORT_BYTES", source.retained_bytes + len(encoded) - 1)
    with pytest.raises(ArtifactError, match="projection_cohort_limit"):
        prepare_evidence(source, lambda *_: pytest.fail("metadata overflow reached reader"))


@pytest.mark.parametrize("mode", ["isolation_none", "driver_autocommit", "driver_autocommit_false"])
def test_read_snapshot_refuses_and_discards_sqlite_autocommit(capture, mode):
    import sqlite3

    with capture.db.engine.connect() as connection:
        raw = connection.connection.driver_connection
        if mode.startswith("driver_autocommit"):
            if not hasattr(raw, "autocommit"):
                pytest.skip("sqlite3 driver autocommit is a Python3.12 boundary")
            raw.autocommit = mode == "driver_autocommit"
        else:
            raw.isolation_level = None
    with (
        pytest.raises(ArtifactError, match="projection_transaction_required"),
        readonly_source(capture.db.engine, QueryBudget()),
    ):
        pytest.fail("unsupported transaction reached cohort reader")
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")
    with capture.db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
        assert not connection.connection.driver_connection.in_transaction
