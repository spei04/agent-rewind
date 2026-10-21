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
        GraphRef("f" * 32, "file_blob", f"{n:064x}"): (
            f"{n:032x}",
            CONTEXT.project_id,
            f"{n:064x}",
            f"objects/{CONTEXT.project_id}/v1/{n:064x}",
            1,
            0,
            datetime(2026, 1, 1, tzinfo=UTC),
        )
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


@pytest.mark.parametrize("second_digest", ["missing", "foreign_owner"])
def test_all_explicit_roots_are_scoped_before_first_storage(
    published, task, monkeypatch, second_digest
):
    capture, first, first_intent, reader = published
    second = capture.run(task)
    second_intent = capture.intent(second)
    capture.publisher.publish(second_intent, capture.source)
    digest = "f" * 64 if second_digest == "missing" else first_intent.root_digest
    monkeypatch.setattr(reader, "scoped_bytes", Mock(side_effect=AssertionError("early storage")))
    with pytest.raises(ResourceNotFound):
        reader.read_many(
            CONTEXT, (RunRead(first, first_intent.root_digest), RunRead(second, digest))
        )
    reader.scoped_bytes.assert_not_called()


@pytest.mark.parametrize("phase", ["preflight", "child", "post_io"])
def test_initial_and_post_io_descriptors_are_sql_bounded(published, monkeypatch, phase):
    capture, run, intent, reader = published
    root = next(obj for obj in intent.objects if obj.digest == intent.root_digest)
    child = next(obj for obj in intent.objects if obj.digest != intent.root_digest)
    target = child if phase == "child" else root
    oversized = "x" * (1024 * 1024)
    original_parser = published_reader._object
    original_loader = reader.repositories.artifact_loader
    parsed_null = False
    loaded = []

    def mutate():
        with capture.db.engine.begin() as connection:
            connection.execute(
                text("UPDATE artifact_objects SET created_at=:value WHERE id=:id"),
                {"value": oversized, "id": target.id},
            )

    def inspect(row):
        nonlocal parsed_null
        assert not any(
            isinstance(value, str | bytes) and len(value) > 160 for value in row.values()
        )
        if row["created_at"] is None:
            parsed_null = True
        return original_parser(row)

    def loader(value):
        loaded.append(value.id)
        result = original_loader(value)
        if phase == "post_io" and value.id == target.id:
            mutate()
        return result

    if phase != "post_io":
        mutate()
    monkeypatch.setattr(published_reader, "_object", inspect)
    monkeypatch.setattr(reader.repositories, "artifact_loader", loader)
    with pytest.raises(ArtifactError, match="artifact_metadata_invalid"):
        reader.read(CONTEXT, run, intent.root_digest)
    assert parsed_null
    if phase == "preflight":
        assert loaded == []
    elif phase == "child":
        assert target.id not in loaded
    else:
        assert loaded == [root.id]


def test_full_matching_ref_set_has_bounded_sqlite_work(published):
    capture, run, _, reader = published
    from agent_rewind.artifact_graph import GraphRef

    count = published_reader.MAX_OBJECTS
    assert count == 16000
    created = datetime(2026, 1, 1, tzinfo=UTC)
    objects = [
        (
            f"feedface{n:024x}",
            CONTEXT.project_id,
            f"{n:064x}",
            f"objects/{CONTEXT.project_id}/v1/{n:064x}",
            1,
            0,
            created.isoformat(),
        )
        for n in range(1, count + 1)
    ]
    with capture.db.engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO artifact_objects VALUES (?,?,?,?,?,?,?)", objects)
        connection.exec_driver_sql(
            "INSERT INTO artifact_refs VALUES (?,?,?,?,?)",
            [(CONTEXT.project_id, "run", run, row[0], "file_blob") for row in objects],
        )
    identities = {GraphRef(run, "file_blob", row[2]): (*row[:6], created) for row in objects}
    observed = []

    def statement(connection, cursor, sql, parameters, context, many):
        if sql.startswith("WITH wanted"):
            observed.append((sql, parameters))

    def verify(expected):
        # Bound VM work rather than elapsed time. This generous ceiling permits
        # indexed lookup/CASE work but interrupts the old repeated JSON scans.
        instructions = 0

        def progress():
            nonlocal instructions
            instructions += 1000
            return instructions > 20_000_000

        with capture.db.engine.connect() as connection:
            raw = connection.connection.driver_connection
            raw.set_progress_handler(progress, 1000)
            try:
                reader._final_refs(connection, CONTEXT, expected)
            finally:
                raw.set_progress_handler(None, 0)
        assert instructions <= 20_000_000

    event.listen(capture.db.engine, "before_cursor_execute", statement)
    try:
        verify(identities)
        assert len(observed) == 1
        sql, parameters = observed[0]
        assert "AS MATERIALIZED" in sql and len(parameters) <= 64
        rowset = next(p for p in parameters if isinstance(p, str) and p.startswith("[{"))
        assert len(rowset.encode()) <= published_reader.MAX_REF_INPUT_BYTES
        # A different existing object ID cannot replace the same digest/owner.
        changed = dict(identities)
        ref = next(iter(changed))
        changed[ref] = (objects[1][0], *changed[ref][1:])
        with pytest.raises(ArtifactError, match="^publication_reference_changed$"):
            verify(changed)
        with capture.db.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM artifact_refs WHERE owner_id=:owner AND artifact_id=:id"),
                {"owner": run, "id": objects[-1][0]},
            )
        with pytest.raises(ArtifactError, match="^publication_reference_changed$"):
            verify(identities)
    finally:
        event.remove(capture.db.engine, "before_cursor_execute", statement)


@pytest.mark.parametrize("field", range(7))
def test_final_ref_keeps_every_descriptor_field_comparison(published, field):
    capture, run, intent, reader = published
    from agent_rewind.artifact_graph import GraphRef

    root = next(obj for obj in intent.objects if obj.digest == intent.root_digest)
    identity = list(published_reader._identity(root))
    alternatives = [
        "f" * 32,
        "f" * 32,
        "f" * 64,
        "objects/" + root.digest,
        2,
        root.byte_count + 1,
        root.created_at + timedelta(seconds=1),
    ]
    assert identity[field] != alternatives[field]
    identity[field] = alternatives[field]
    with (
        capture.db.engine.connect() as connection,
        pytest.raises(ArtifactError, match="^publication_reference_changed$"),
    ):
        reader._final_refs(
            connection,
            CONTEXT,
            {GraphRef(run, "result", intent.root_digest): tuple(identity)},
        )


@pytest.mark.parametrize("version", [None, (3, 34, 1)])
def test_unsupported_sqlite_materialization_refuses_before_storage(published, monkeypatch, version):
    capture, run, intent, reader = published
    monkeypatch.setattr(capture.db.engine.dialect, "server_version_info", version)
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("early storage"))
    )
    with pytest.raises(ArtifactError, match="^artifact_database_unsupported$"):
        reader.read(CONTEXT, run, intent.root_digest)
    reader.repositories.artifact_loader.assert_not_called()
