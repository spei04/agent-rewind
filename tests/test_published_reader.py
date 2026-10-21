"""Shared complete-graph reads; every successful fixture uses actual publication."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from publication_fixture import CONTEXT, make_capture
from sqlalchemy import event, text

from agent_rewind import published_reader
from agent_rewind.artifact_metadata import ArtifactError, record_verified, register_ref
from agent_rewind.artifact_publication import UnavailableLiveWriter
from agent_rewind.models import Action, Intervention
from agent_rewind.published_reader import PublishedRunReader, RunRead
from agent_rewind.scoped_lineage import ResourceNotFound


@pytest.fixture
def published(settings, task):
    capture = make_capture(settings)
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    reader = PublishedRunReader(capture.db.engine, capture.publisher.storage)
    yield capture, run, intent, reader
    capture.db.engine.dispose()


def test_journal_free_unique_root_and_explicit_compatibility(published, monkeypatch):
    capture, run, intent, reader = published
    capture.publisher.writer = UnavailableLiveWriter()
    monkeypatch.setattr(capture.journal, "open", Mock(side_effect=AssertionError("journal read")))
    direct = reader.read_current(CONTEXT, run)
    assert capture.publisher.read(CONTEXT, run, intent.root_digest) == direct
    assert direct.root_digest == intent.root_digest
    assert not hasattr(reader, "journal") and not hasattr(reader, "writer")


def test_publisher_delegates_the_actual_shared_reader(published, monkeypatch):
    capture, run, intent, _ = published
    sentinel = object()
    delegated = Mock(return_value=sentinel)
    monkeypatch.setattr(capture.publisher.reader, "read", delegated)
    assert capture.publisher.read(CONTEXT, run, intent.root_digest) is sentinel
    delegated.assert_called_once_with(CONTEXT, run, intent.root_digest)


@pytest.mark.parametrize("case", ["missing_run", "foreign_project", "missing_refs"])
def test_unavailable_root_refuses_before_backend(published, monkeypatch, case):
    capture, run, _, reader = published
    context = CONTEXT
    if case == "missing_run":
        run = "f" * 32
    elif case == "foreign_project":
        context = replace(CONTEXT, project_id="f" * 32)
    else:
        with capture.db.engine.begin() as c:
            c.exec_driver_sql("DELETE FROM artifact_refs WHERE role='result'")
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("I/O"))
    )
    with pytest.raises(ResourceNotFound):
        reader.read_current(context, run)
    reader.repositories.artifact_loader.assert_not_called()


def test_multiple_roots_have_no_first_or_latest_fallback(published, monkeypatch):
    capture, run, first, reader = published
    second = capture.intent(run, expected_root=first.root_digest)
    capture.publisher.publish(second, capture.source)
    assert reader.read(CONTEXT, run, first.root_digest).root_digest == first.root_digest
    assert reader.read(CONTEXT, run, second.root_digest).root_digest == second.root_digest
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("I/O"))
    )
    with pytest.raises(ResourceNotFound):
        reader.read_current(CONTEXT, run)
    reader.repositories.artifact_loader.assert_not_called()


def test_compound_parent_branch_keeps_ancestor_owners_and_no_sql_during_io(
    published, task, monkeypatch
):
    capture, parent, first, reader = published
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
    second = capture.intent(branch)
    capture.publisher.publish(second, capture.source)
    load = reader.repositories.artifact_loader

    def checked(value):
        assert capture.db.engine.pool.checkedout() == 0
        return load(value)

    monkeypatch.setattr(reader.repositories, "artifact_loader", checked)
    graphs = reader.read_many(CONTEXT, (RunRead(parent), RunRead(branch)))
    assert [g.root_digest for g in graphs] == [first.root_digest, second.root_digest]
    assert any(ref.owner_id == parent for ref in graphs[1].refs)


def test_first_graph_ref_removed_during_second_graph_io_refuses_compound(
    published, task, monkeypatch
):
    capture, first_run, first, reader = published
    second_run = capture.run(task)
    second = capture.intent(second_run)
    capture.publisher.publish(second, capture.source)
    load = reader.repositories.artifact_loader

    def changed(value):
        result = load(value)
        if value.digest == second.root_digest:
            with capture.db.engine.begin() as c:
                c.execute(
                    text("DELETE FROM artifact_refs WHERE owner_id=:owner AND role='task'"),
                    {"owner": first_run},
                )
        return result

    monkeypatch.setattr(reader.repositories, "artifact_loader", changed)
    with pytest.raises(ArtifactError, match="publication_reference_changed"):
        reader.read_many(
            CONTEXT,
            (RunRead(first_run, first.root_digest), RunRead(second_run, second.root_digest)),
        )


@pytest.mark.parametrize("change", ["ref", "timestamp", "membership"])
def test_final_phase_change_refuses_bytes(published, monkeypatch, change):
    capture, run, intent, reader = published
    original = reader._final_refs
    victim = next(obj for obj in intent.objects if obj.digest != intent.root_digest)

    def changed(connection, context, identities):
        # The final ref statement follows the completed owner traversal.
        if change != "membership":
            with capture.db.engine.begin() as c:
                if change == "ref":
                    c.execute(
                        text("DELETE FROM artifact_refs WHERE artifact_id=:id"), {"id": victim.id}
                    )
                else:
                    c.execute(
                        text("UPDATE artifact_objects SET created_at=:at WHERE id=:id"),
                        {
                            "id": victim.id,
                            "at": (victim.created_at + timedelta(seconds=1)).isoformat(),
                        },
                    )
        original(connection, context, identities)
        if change == "membership":
            with capture.db.engine.begin() as c:
                c.execute(
                    text("UPDATE project_memberships SET revoked_at=:at"),
                    {"at": datetime.now(UTC).isoformat()},
                )

    monkeypatch.setattr(reader, "_final_refs", changed)
    with pytest.raises((ArtifactError, ResourceNotFound)):
        reader.read(CONTEXT, run, intent.root_digest)


def test_unique_root_is_rechecked_after_last_io(published, monkeypatch):
    capture, run, intent, reader = published
    original = reader._final_refs
    # Add ambiguity during the final owner check, before discovery recheck.
    original_root = reader._unique_root
    calls = 0

    def changed(connection, context, owner):
        nonlocal calls
        calls += 1
        if calls == 2:
            root = next(obj for obj in intent.objects if obj.digest == intent.root_digest)
            other = replace(
                root,
                id="e" * 32,
                digest="e" * 64,
                locator=f"objects/{context.project_id}/v1/{'e' * 64}",
            )
            with capture.db.engine.begin() as c:
                record_verified(c, other)
                register_ref(
                    c,
                    project_id=context.project_id,
                    owner_kind="run",
                    owner_id=run,
                    role="result",
                    artifact_id=other.id,
                )
        return original_root(connection, context, owner)

    monkeypatch.setattr(reader, "_unique_root", changed)
    monkeypatch.setattr(reader, "_final_refs", Mock(wraps=original))
    with pytest.raises(ResourceNotFound):
        reader.read_current(CONTEXT, run)
    reader._final_refs.assert_not_called()


def test_final_statement_uses_constant_binds_and_bounded_metadata(published, monkeypatch):
    capture, run, intent, reader = published
    observed = []

    def record(conn, cursor, statement, parameters, ctx, many):
        if statement.startswith("WITH wanted"):
            observed.append((statement, parameters))

    event.listen(capture.db.engine, "before_cursor_execute", record)
    try:
        reader.read(CONTEXT, run, intent.root_digest)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", record)
    assert len(observed) == 1 and len(observed[0][1]) <= 64
    assert "LIMIT ?" in observed[0][0] and "CASE WHEN" in observed[0][0]
    rowset = next(
        value for value in observed[0][1] if isinstance(value, str) and value.startswith("[{")
    )
    assert len(rowset.encode()) <= published_reader.MAX_REF_INPUT_BYTES


def test_final_input_bound_refuses_before_statement(published, monkeypatch):
    capture, run, intent, reader = published
    monkeypatch.setattr(published_reader, "MAX_REF_INPUT_BYTES", 1)
    statements = []

    def record(conn, cursor, statement, parameters, ctx, many):
        statements.append(statement)

    event.listen(capture.db.engine, "before_cursor_execute", record)
    try:
        with pytest.raises(ArtifactError, match="artifact_graph_limit"):
            reader.read(CONTEXT, run, intent.root_digest)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", record)
    assert not any(s.startswith("WITH wanted") for s in statements)


@pytest.mark.parametrize("count", [0, 3])
def test_compound_count_bound_precedes_io(published, monkeypatch, count):
    _, run, _, reader = published
    monkeypatch.setattr(reader, "scoped_bytes", Mock(side_effect=AssertionError("I/O")))
    with pytest.raises(ArtifactError, match="artifact_graph_limit"):
        reader.read_many(CONTEXT, (RunRead(run),) * count)
    reader.scoped_bytes.assert_not_called()


def test_compound_aggregate_bytes_cannot_multiply_graph_bound(published, monkeypatch):
    _, run, intent, reader = published
    graph = reader.read(CONTEXT, run, intent.root_digest)
    # Each graph alone fits. The combined fetch/retention budget must not double.
    monkeypatch.setattr(
        published_reader,
        "MAX_BYTES",
        sum(len(value) for value in graph.objects.values()) + len(graph.envelope) + 1,
    )
    with pytest.raises(ArtifactError, match="artifact_graph_limit"):
        reader.read_many(CONTEXT, (RunRead(run, intent.root_digest),) * 2)


def test_full_supported_ref_set_fits_one_actual_sqlite_statement(published):
    capture, _, _, reader = published
    from agent_rewind.artifact_graph import GraphRef

    identities = {
        GraphRef("f" * 32, "file_blob", f"{n:064x}"): ()
        for n in range(published_reader.MAX_OBJECTS)
    }
    # No fake SQL runner: the max-sized JSON rowset executes against the actual
    # driver without expanding bind count. It then refuses every absent ref.
    with (
        capture.db.engine.connect() as connection,
        pytest.raises(ArtifactError, match="publication_reference_changed"),
    ):
        reader._final_refs(connection, CONTEXT, identities)


def test_final_metadata_bound_precedes_python_materialization(published, monkeypatch):
    capture, run, intent, reader = published
    original = reader._final_refs
    object_parser = published_reader._object
    oversized = "x" * 8192
    saw_null = False

    def inspect(row):
        nonlocal saw_null
        assert oversized not in row.values()
        if row["created_at"] is None:
            saw_null = True
        return object_parser(row)

    def changed(connection, context, identities):
        with capture.db.engine.begin() as c:
            c.execute(text("UPDATE artifact_objects SET created_at=:value"), {"value": oversized})
        return original(connection, context, identities)

    monkeypatch.setattr(published_reader, "_object", inspect)
    monkeypatch.setattr(reader, "_final_refs", changed)
    with pytest.raises(ArtifactError, match="publication_reference_changed"):
        reader.read(CONTEXT, run, intent.root_digest)
    assert saw_null


def test_read_never_mutates_metadata_or_counters(published):
    capture, run, intent, reader = published
    statements = []

    def record(conn, cursor, statement, parameters, ctx, many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(capture.db.engine, "before_cursor_execute", record)
    try:
        reader.read_current(CONTEXT, run)
        reader.read(CONTEXT, run, intent.root_digest)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", record)
    assert set(statements) <= {"SELECT", "WITH"}


@pytest.mark.parametrize("second", ["missing", "unpublished"])
def test_all_compound_inputs_authorize_before_any_storage(published, task, monkeypatch, second):
    capture, first, _, reader = published
    other = "f" * 32 if second == "missing" else capture.run(task)
    monkeypatch.setattr(reader, "scoped_bytes", Mock(side_effect=AssertionError("early storage")))
    with pytest.raises(ResourceNotFound):
        reader.read_many(CONTEXT, (RunRead(first), RunRead(other)))
    reader.scoped_bytes.assert_not_called()
