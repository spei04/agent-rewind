"""Real coordinator/storage/SQL integration with an explicitly synthetic future fence."""

from dataclasses import replace

import pytest
from publication_fixture import CONTEXT, JOB, make_capture
from sqlalchemy import text

from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.artifact_publication import UnavailableLiveWriter
from agent_rewind.models import Action, Intervention
from agent_rewind.scoped_lineage import ResourceNotFound


@pytest.fixture
def capture(settings):
    value = make_capture(settings)
    yield value
    value.db.engine.dispose()


def counts(capture):
    with capture.db.engine.connect() as c:
        return tuple(
            c.exec_driver_sql("SELECT count(*) FROM " + name).scalar_one()
            for name in ("artifact_objects", "artifact_refs", "publication_roots")
        )


def test_complete_parent_and_successful_branch_keep_real_ancestor_refs(capture, task):
    parent = capture.run(task)
    intent = capture.intent(parent)
    root = capture.publisher.publish(intent, capture.source)
    graph = capture.publisher.read(CONTEXT, parent, root)
    assert graph.root_digest == root
    assert {ref.role for ref in graph.refs} == {
        "task",
        "event",
        "checkpoint",
        "workspace",
        "file_blob",
        "evaluation",
        "result",
    }
    assert capture.db.get(parent)["success"] is False
    assert b"\x00\xff" in graph.objects.values()
    branch = capture.run(
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
        seed=99,
    )
    child = capture.intent(branch)
    child_root = capture.publisher.publish(child, capture.source)
    loaded = capture.publisher.read(CONTEXT, branch, child_root)
    assert capture.db.get(branch)["success"] is True
    inherited = capture.db.event_refs(parent)[0]["artifact"]
    assert any(ref.owner_id == parent and ref.digest == inherited for ref in loaded.refs)
    assert not any(ref.owner_id == branch and ref.digest == inherited for ref in loaded.refs)
    before = counts(capture)
    assert (
        capture.publisher.publish(
            child, lambda *_: pytest.fail("retry must inspect SQL before source")
        )
        == child_root
    )
    assert counts(capture) == before


def test_live_adapter_refuses_before_capture_or_storage(capture, task):
    run = capture.run(task)
    capture.publisher.writer = UnavailableLiveWriter()
    with pytest.raises(ArtifactError, match="live_fence_unavailable"):
        capture.publisher.prepare(
            CONTEXT, run, worker_id="w", generation=1, source=lambda *_: pytest.fail("no source")
        )
    assert counts(capture) == (0, 0, 0)


def test_missing_last_child_never_publishes(capture, task):
    run = capture.run(task)
    key = capture.db.get(run)["evaluation_ref"]

    def missing(ref, limit):
        if ref.digest == key:
            raise ArtifactError("artifact_missing")
        return capture.source(ref, limit)

    with pytest.raises(ArtifactError, match="artifact_missing"):
        capture.publisher.prepare(CONTEXT, run, worker_id="w", generation=1, source=missing)
    assert counts(capture) == (0, 0, 0)


def test_sql_failure_rolls_back_refs_and_retains_orphan_evidence(capture, task, monkeypatch):
    run = capture.run(task)
    intent = capture.intent(run)
    original = capture.publisher.writer.publish_root

    def crash(connection, value):
        original(connection, value)
        raise ArtifactError("synthetic_transaction_failure")

    monkeypatch.setattr(capture.publisher.writer, "publish_root", crash)
    with pytest.raises(ArtifactError, match="synthetic_transaction_failure"):
        capture.publisher.publish(intent, capture.source)
    assert counts(capture) == (0, 0, 0)
    with capture.journal.open(intent.publication_id) as journal:
        assert len([r for r in journal.records if r["kind"] == "upload_verified"]) == len(
            intent.objects
        )
        assert journal.records[-1]["kind"] == "commit_unknown"
        assert {obj["id"] for obj in journal.intent["objects"]} == {
            obj.id for obj in intent.objects
        }
    for obj in intent.objects:
        assert len(capture.publisher.storage.read_verified(obj)) == obj.byte_count
    monkeypatch.setattr(capture.publisher.writer, "publish_root", original)
    assert capture.publisher.publish(intent, capture.source) == intent.root_digest


@pytest.mark.parametrize("mutation", ["generation", "cancel", "lease", "owner", "membership"])
def test_lost_authority_after_storage_has_no_root(capture, task, monkeypatch, mutation):
    run = capture.run(task)
    intent = capture.intent(run)
    put = capture.publisher.storage.put_verified
    seen = 0

    def mutate(obj, content):
        nonlocal seen
        result = put(obj, content)
        seen += 1
        if seen == len(intent.objects):
            with capture.db.engine.begin() as c:
                query = {
                    "generation": "UPDATE publication_fences SET generation=2",
                    "cancel": "UPDATE jobs SET cancel=true",
                    "lease": "UPDATE jobs SET lease_until=1",
                    "owner": "UPDATE jobs SET owner='another-worker'",
                    "membership": "UPDATE project_memberships SET role='viewer'",
                }[mutation]
                c.exec_driver_sql(query)
        return result

    monkeypatch.setattr(capture.publisher.storage, "put_verified", mutate)
    with pytest.raises((ArtifactError, ResourceNotFound)):
        capture.publisher.publish(intent, capture.source)
    assert counts(capture) == (0, 0, 0)


def test_exact_committed_reentry_after_lease_loss(capture, task):
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    with capture.db.engine.begin() as c:
        c.execute(text("UPDATE jobs SET status='complete',lease_until=1 WHERE id=:id"), {"id": JOB})
    assert (
        capture.publisher.publish(intent, lambda *_: pytest.fail("already committed"))
        == intent.root_digest
    )


def test_new_intent_reuses_immutable_descriptor_identity(capture, task):
    run = capture.run(task)
    first = capture.intent(run)
    capture.publisher.publish(first, capture.source)
    second = capture.intent(run, expected_root=first.root_digest)
    old = {obj.digest: obj for obj in first.objects}
    assert all(old[obj.digest] == obj for obj in second.objects if obj.digest in old)
    capture.publisher.publish(second, capture.source)
    assert (
        capture.publisher.read(CONTEXT, run, second.root_digest).root_digest == second.root_digest
    )


def test_scoped_graph_denial_before_storage(capture, task, monkeypatch):
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    monkeypatch.setattr(
        capture.publisher.repositories,
        "artifact_loader",
        lambda *_: pytest.fail("foreign storage read"),
    )
    with pytest.raises(ResourceNotFound):
        capture.publisher.read(replace(CONTEXT, project_id="7" * 32), run, intent.root_digest)


def test_reload_frozen_intent_after_failed_upload_keeps_all_identities(capture, task, monkeypatch):
    run = capture.run(task)
    intent = capture.intent(run)
    real = capture.publisher.storage.put_verified
    monkeypatch.setattr(
        capture.publisher.storage,
        "put_verified",
        lambda *_: (_ for _ in ()).throw(OSError("synthetic interruption")),
    )
    with pytest.raises(ArtifactError, match="publication_upload_failed"):
        capture.publisher.publish(intent, capture.source)
    recovered = capture.publisher.load_intent(CONTEXT, intent.publication_id)
    assert recovered == intent
    monkeypatch.setattr(capture.publisher.storage, "put_verified", real)
    assert capture.publisher.publish(recovered, capture.source) == intent.root_digest


def test_committed_sql_without_journal_ack_reconciles_without_live_lease(
    capture, task, monkeypatch
):
    from agent_rewind.publication_journal import JournalSession

    run = capture.run(task)
    intent = capture.intent(run)
    real = JournalSession.append

    def fail_ack(self, kind, data):
        if kind == "commit_confirmed":
            raise ArtifactError("publication_journal_unavailable")
        return real(self, kind, data)

    monkeypatch.setattr(JournalSession, "append", fail_ack)
    with pytest.raises(ArtifactError, match="journal_unavailable"):
        capture.publisher.publish(intent, capture.source)
    assert counts(capture)[2] == 1
    with capture.db.engine.begin() as c:
        c.exec_driver_sql("UPDATE jobs SET status='complete',lease_until=1")
    monkeypatch.setattr(JournalSession, "append", real)
    recovered = capture.publisher.load_intent(CONTEXT, intent.publication_id)
    assert (
        capture.publisher.publish(recovered, lambda *_: pytest.fail("committed retry source"))
        == intent.root_digest
    )


def test_reader_rechecks_earlier_child_ref_after_later_io(capture, task, monkeypatch):
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    victim = next(
        obj
        for obj in intent.objects
        if any(ref.role == "task" and ref.digest == obj.digest for ref in intent.refs)
    )
    original = capture.publisher.repositories.artifact_loader
    evaluation = capture.db.get(run)["evaluation_ref"]

    def loader(obj):
        result = original(obj)
        if obj.digest == evaluation:
            with capture.db.engine.begin() as c:
                c.execute(
                    text("DELETE FROM artifact_refs WHERE role='task' AND artifact_id=:id"),
                    {"id": victim.id},
                )
        return result

    monkeypatch.setattr(capture.publisher.repositories, "artifact_loader", loader)
    with pytest.raises(ArtifactError, match="publication_reference_changed"):
        capture.publisher.read(CONTEXT, run, intent.root_digest)


def test_reader_checks_descriptor_bound_before_backend(capture, task, monkeypatch):
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    target = next(ref for ref in intent.refs if ref.role == "task")
    with capture.db.engine.begin() as c:
        c.execute(
            text("UPDATE artifact_objects SET byte_count=67108865 WHERE digest=:digest"),
            {"digest": target.digest},
        )
    original = capture.publisher.repositories.artifact_loader

    def loader(value):
        if value.digest == target.digest:
            pytest.fail("oversized descriptor reached backend")
        return original(value)

    monkeypatch.setattr(capture.publisher.repositories, "artifact_loader", loader)
    with pytest.raises(ArtifactError, match="artifact_graph_limit"):
        capture.publisher.read(CONTEXT, run, intent.root_digest)


def test_no_storage_or_journal_io_holds_database_connection(capture, task, monkeypatch):
    from agent_rewind.publication_journal import JournalSession

    run = capture.run(task)
    intent = capture.intent(run)
    put = capture.publisher.storage.put_verified
    append = JournalSession.append

    def check_put(obj, content):
        assert capture.db.engine.pool.checkedout() == 0
        return put(obj, content)

    def check_append(self, kind, data):
        assert capture.db.engine.pool.checkedout() == 0
        return append(self, kind, data)

    monkeypatch.setattr(capture.publisher.storage, "put_verified", check_put)
    monkeypatch.setattr(JournalSession, "append", check_append)
    capture.publisher.publish(intent, capture.source)
    capture.publisher.publish(intent, lambda *_: pytest.fail("duplicate upload"))


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_process_death_reloads_exact_intent_and_resolves_sql(capture, task, point):
    import multiprocessing
    import os

    from agent_rewind.publication_journal import JournalSession

    run = capture.run(task)
    intent = capture.intent(run)
    capture.db.engine.dispose()

    def killed_publisher():
        if point == "before_commit":
            original = capture.publisher.writer.publish_root

            def stop(connection, value):
                original(connection, value)
                os._exit(73)

            capture.publisher.writer.publish_root = stop
        else:
            original_append = JournalSession.append

            def stop_ack(self, kind, data):
                if kind == "commit_confirmed":
                    os._exit(73)
                return original_append(self, kind, data)

            JournalSession.append = stop_ack
        capture.publisher.publish(intent, capture.source)

    child = multiprocessing.get_context("fork").Process(target=killed_publisher)
    child.start()
    child.join(15)
    if child.is_alive():
        child.kill()
        child.join(5)
        pytest.fail("synthetic publisher did not exit")
    assert child.exitcode == 73
    capture.db.engine.dispose()
    assert counts(capture)[2] == (0 if point == "before_commit" else 1)
    recovered = capture.publisher.load_intent(CONTEXT, intent.publication_id)
    assert recovered == intent
    if point == "after_commit":
        with capture.db.engine.begin() as c:
            c.exec_driver_sql("UPDATE jobs SET status='complete',lease_until=1")

        def source(*_):
            pytest.fail("completed commit must not replay upload")
    else:
        source = capture.source
    assert capture.publisher.publish(recovered, source) == intent.root_digest
    assert (
        capture.publisher.read(CONTEXT, run, intent.root_digest).root_digest == intent.root_digest
    )


@pytest.mark.parametrize("field", ["artifact", "hash"])
def test_oversized_sql_event_cells_refuse_before_materialization(capture, task, field):
    from sqlalchemy import event

    run = capture.run(task)
    with capture.db.engine.begin() as c:
        c.execute(text("UPDATE events SET " + field + "=:value"), {"value": "x" * 10000})
    fetched = []

    def inspect(connection, cursor, statement, parameters, context, executemany):
        if "SELECT events.run_id, events.step, events.artifact, events.hash" in statement:
            fetched.append(statement)

    event.listen(capture.db.engine, "before_cursor_execute", inspect)
    try:
        with pytest.raises(ArtifactError, match="artifact_graph_invalid"):
            capture.intent(run)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", inspect)
    assert fetched == []
    assert counts(capture) == (0, 0, 0)
