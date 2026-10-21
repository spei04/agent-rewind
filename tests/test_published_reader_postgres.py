"""PostgreSQL SELECT-only complete graph reads with deterministic concurrent commits.

Publication setup uses the explicit future-contract fixture. No test enables a
customer release or treats fixture roots as a production publication adapter.
"""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
import test_migrations_postgres as migrations
from publication_fixture import CONTEXT, make_capture
from sqlalchemy import event, text
from test_artifact_postgres import prepare_postgres

from agent_rewind import published_reader
from agent_rewind.artifact_graph import GraphRef
from agent_rewind.artifact_metadata import ArtifactError, record_verified, register_ref
from agent_rewind.artifact_publication import UnavailableLiveWriter
from agent_rewind.models import Action, Intervention
from agent_rewind.published_reader import PublishedRunReader, RunRead
from agent_rewind.scoped_repositories import ResourceNotFound

pg = migrations.pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL published reader"
)


@pytest.fixture
def published_pg(pg, settings, task):
    prepare_postgres(pg)
    capture = make_capture(settings, prepared_engine=pg["owner"])
    run = capture.run(task)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    reader = PublishedRunReader(pg["app"], capture.publisher.storage)
    yield capture, run, intent, reader
    capture.db.engine.dispose()


def publish(capture, task, *args, **kwargs):
    run = capture.run(task, *args, **kwargs)
    intent = capture.intent(run)
    capture.publisher.publish(intent, capture.source)
    return run, intent


def add_root(connection, intent):
    root = next(value for value in intent.objects if value.digest == intent.root_digest)
    other = replace(
        root,
        id="e" * 32,
        digest="e" * 64,
        locator=f"objects/{CONTEXT.project_id}/v1/{'e' * 64}",
    )
    # Metadata-only malformed/ambiguous root injection, not a verified graph.
    record_verified(connection, other)
    register_ref(
        connection,
        project_id=CONTEXT.project_id,
        owner_kind="run",
        owner_id=intent.run_id,
        role="result",
        artifact_id=other.id,
    )


def key_context(pg):
    key = "d" * 32
    principal = "api-key:" + key
    with pg["owner"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO api_keys(id,hash,role,name,expires,revoked) "
                "VALUES (:id,:hash,'operator','synthetic-reader',253402300799,false)"
            ),
            {"id": key, "hash": "d" * 64},
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:project)"),
            {"id": key, "project": CONTEXT.project_id},
        )
        connection.execute(
            text(
                "INSERT INTO project_memberships VALUES (:project,:principal,'operator',NULL,false)"
            ),
            {"project": CONTEXT.project_id, "principal": principal},
        )
    return replace(CONTEXT, principal_id=principal), key


def test_postgres_journal_free_select_only_compound_reader_releases_connections(
    pg, published_pg, task, monkeypatch
):
    capture, parent, first, reader = published_pg
    branch, second = publish(
        capture,
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
        seed=99,
    )
    capture.publisher.writer = UnavailableLiveWriter()
    capture.publisher.reader = reader
    monkeypatch.setattr(capture.journal, "open", Mock(side_effect=AssertionError("journal access")))
    with pg["app"].connect() as connection:
        assert connection.execute(
            text(
                "SELECT has_table_privilege(current_user,'public.artifact_refs','UPDATE'),"
                "has_table_privilege(current_user,'public.artifact_objects','INSERT'),"
                "has_schema_privilege(current_user,'public','CREATE')"
            )
        ).one() == (False, False, False)
    active, statements, loads = set(), [], []

    def checkout(dbapi, record, proxy):
        active.add(id(record))

    def checkin(dbapi, record):
        active.remove(id(record))

    def statement(connection, cursor, sql, parameters, context, many):
        statements.append(sql)

    load = reader.repositories.artifact_loader

    def checked(value):
        assert active == set(), "Reader held an application connection during storage I/O"
        loads.append(value.id)
        return load(value)

    event.listen(pg["app"], "checkout", checkout)
    event.listen(pg["app"], "checkin", checkin)
    event.listen(pg["app"], "before_cursor_execute", statement)
    monkeypatch.setattr(reader.repositories, "artifact_loader", checked)
    try:
        graphs = reader.read_many(CONTEXT, (RunRead(parent), RunRead(branch)))
        assert [graph.root_digest for graph in graphs] == [first.root_digest, second.root_digest]
        assert any(ref.owner_id == parent for ref in graphs[1].refs)
        assert capture.publisher.read(CONTEXT, parent, first.root_digest) == graphs[0]
    finally:
        event.remove(pg["app"], "checkout", checkout)
        event.remove(pg["app"], "checkin", checkin)
        event.remove(pg["app"], "before_cursor_execute", statement)
    assert loads and active == set()
    assert set(sql.lstrip().split()[0].upper() for sql in statements) <= {"SELECT", "WITH"}
    assert not any("FOR UPDATE" in sql or "publication_roots" in sql for sql in statements)
    capture.journal.open.assert_not_called()


@pytest.mark.parametrize("case", ["missing", "multiple"])
def test_postgres_unique_root_refuses_before_storage(pg, published_pg, monkeypatch, case):
    _, run, intent, reader = published_pg
    with pg["owner"].begin() as connection:
        if case == "missing":
            connection.execute(
                text("DELETE FROM artifact_refs WHERE owner_id=:id AND role='result'"),
                {"id": run},
            )
        else:
            add_root(connection, intent)
    monkeypatch.setattr(
        reader.repositories, "artifact_loader", Mock(side_effect=AssertionError("early storage"))
    )
    with pytest.raises(ResourceNotFound):
        reader.read_current(CONTEXT, run)
    reader.repositories.artifact_loader.assert_not_called()


@pytest.mark.parametrize("case", ["missing", "unpublished", "foreign", "explicit_missing"])
def test_postgres_every_compound_input_is_visible_before_storage(
    pg, published_pg, task, monkeypatch, case
):
    capture, first, _, reader = published_pg
    second = "f" * 32 if case == "missing" else capture.run(task)
    if case == "foreign":
        with pg["owner"].begin() as connection:
            connection.execute(
                text("INSERT INTO projects VALUES (:id,:org,'Other',CURRENT_TIMESTAMP)"),
                {"id": "7" * 32, "org": CONTEXT.organization_id},
            )
            connection.execute(
                text(
                    "UPDATE resource_scopes SET project_id=:project "
                    "WHERE resource_kind='run' AND resource_id=:id"
                ),
                {"project": "7" * 32, "id": second},
            )
    monkeypatch.setattr(reader, "scoped_bytes", Mock(side_effect=AssertionError("early storage")))
    requested = RunRead(second, "f" * 64) if case == "explicit_missing" else RunRead(second)
    with pytest.raises(ResourceNotFound):
        reader.read_many(CONTEXT, (RunRead(first), requested))
    reader.scoped_bytes.assert_not_called()


@pytest.mark.parametrize("change", ["root_removed", "root_added", "ref_removed", "descriptor"])
def test_postgres_first_graph_changes_during_second_storage_refuse_all_bytes(
    pg, published_pg, task, monkeypatch, change
):
    capture, first_run, first, reader = published_pg
    second_run, second = publish(capture, task)
    load = reader.repositories.artifact_loader
    changed = False

    def mutate(value):
        nonlocal changed
        content = load(value)
        if value.digest == second.root_digest:
            assert not changed
            changed = True
            with pg["owner"].begin() as connection:
                if change == "root_added":
                    add_root(connection, first)
                elif change == "descriptor":
                    connection.execute(
                        text(
                            "UPDATE artifact_objects SET created_at=created_at+INTERVAL '1 second' "
                            "WHERE project_id=:project AND digest=:digest"
                        ),
                        {"project": CONTEXT.project_id, "digest": first.root_digest},
                    )
                else:
                    connection.execute(
                        text("DELETE FROM artifact_refs WHERE owner_id=:owner AND role=:role"),
                        {
                            "owner": first_run,
                            "role": "result" if change == "root_removed" else "task",
                        },
                    )
        return content

    monkeypatch.setattr(reader.repositories, "artifact_loader", mutate)
    if change in {"root_removed", "root_added"}:
        failure = ResourceNotFound
        message = "^Resource not found.$"
    else:
        failure = ArtifactError
        message = "^publication_reference_changed$"
    with pytest.raises(failure, match=message):
        reader.read_many(CONTEXT, (RunRead(first_run), RunRead(second_run)))
    assert changed


@pytest.mark.parametrize("change", ["membership", "key_revoked", "key_expired"])
@pytest.mark.parametrize("phase", ["storage", "after_final_refs"])
def test_postgres_revocation_before_return_rechecks_fresh_authority(
    pg, published_pg, monkeypatch, change, phase
):
    _, run, intent, reader = published_pg
    context, key = (CONTEXT, None) if change == "membership" else key_context(pg)
    changed = False

    def revoke():
        nonlocal changed
        assert not changed
        changed = True
        with pg["owner"].begin() as connection:
            if change == "membership":
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at=CURRENT_TIMESTAMP "
                        "WHERE project_id=:project AND principal_id=:principal"
                    ),
                    {"project": context.project_id, "principal": context.principal_id},
                )
            elif change == "key_revoked":
                connection.execute(
                    text("UPDATE api_keys SET revoked=true WHERE id=:key"), {"key": key}
                )
            else:
                connection.execute(
                    text("UPDATE api_keys SET expires=0 WHERE id=:key"), {"key": key}
                )

    if phase == "storage":
        load = reader.repositories.artifact_loader

        def during_storage(value):
            content = load(value)
            revoke()
            return content

        monkeypatch.setattr(reader.repositories, "artifact_loader", during_storage)
    else:
        final = reader._final_refs

        def after_refs(connection, bound_context, identities):
            final(connection, bound_context, identities)
            revoke()

        monkeypatch.setattr(reader, "_final_refs", after_refs)
    with pytest.raises(ResourceNotFound, match="^Resource not found.$"):
        reader.read(context, run, intent.root_digest)
    assert changed


def test_postgres_ancestor_closure_changed_during_branch_storage_denies(
    pg, published_pg, task, monkeypatch
):
    capture, parent, _, reader = published_pg
    branch, intent = publish(
        capture,
        task,
        parent,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    load = reader.repositories.artifact_loader
    changed = False

    def mutate(value):
        nonlocal changed
        content = load(value)
        if value.digest == intent.root_digest:
            changed = True
            with pg["owner"].begin() as connection:
                connection.execute(
                    text(
                        "UPDATE records SET data=jsonb_set(data::jsonb,'{job_id}',"
                        "to_jsonb(CAST(:job AS text)))::json WHERE id=:parent"
                    ),
                    {"job": "f" * 32, "parent": parent},
                )
        return content

    monkeypatch.setattr(reader.repositories, "artifact_loader", mutate)
    with pytest.raises(ResourceNotFound):
        reader.read(CONTEXT, branch, intent.root_digest)
    assert changed


@pytest.mark.parametrize("change", ["ref", "descriptor"])
def test_postgres_final_jsonb_statement_sees_change_after_owner_traversal(
    pg, published_pg, monkeypatch, change
):
    _, run, intent, reader = published_pg
    original = reader._final_refs

    def before_refs(connection, context, identities):
        with pg["owner"].begin() as writer:
            if change == "ref":
                writer.execute(
                    text("DELETE FROM artifact_refs WHERE owner_id=:id AND role='task'"),
                    {"id": run},
                )
            else:
                writer.execute(
                    text(
                        "UPDATE artifact_objects SET created_at=created_at+INTERVAL '1 second' "
                        "WHERE project_id=:project AND digest=:digest"
                    ),
                    {"project": CONTEXT.project_id, "digest": intent.root_digest},
                )
        original(connection, context, identities)

    monkeypatch.setattr(reader, "_final_refs", before_refs)
    with pytest.raises(ArtifactError, match="^publication_reference_changed$"):
        reader.read(CONTEXT, run, intent.root_digest)


def test_postgres_full_16000_ref_statement_matches_then_refuses_missing_row(
    pg, published_pg, monkeypatch
):
    _, run, _, reader = published_pg
    count = published_reader.MAX_OBJECTS
    assert count == 16000
    created = datetime(2026, 1, 1, tzinfo=UTC)
    # Only the bounded final SQL statement is under test here. These synthetic
    # descriptors are not claimed to have storage receipts or valid graph bytes.
    with pg["owner"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO artifact_objects "
                "(id,project_id,digest,locator,format_version,byte_count,created_at) "
                "SELECT 'feedface'||lpad(to_hex(n),24,'0'),CAST(:project AS VARCHAR(32)),"
                "lpad(to_hex(n),64,'0'),'objects/'||CAST(:project AS VARCHAR(32))"
                "||'/v1/'||lpad(to_hex(n),64,'0'),"
                "1,0,:created FROM generate_series(1,:count) AS n"
            ),
            {"project": CONTEXT.project_id, "created": created, "count": count},
        )
        connection.execute(
            text(
                "INSERT INTO artifact_refs(project_id,owner_kind,owner_id,artifact_id,role) "
                "SELECT :project,'run',:owner,'feedface'||lpad(to_hex(n),24,'0'),'file_blob' "
                "FROM generate_series(1,:count) AS n"
            ),
            {"project": CONTEXT.project_id, "owner": run, "count": count},
        )
    identities = {
        GraphRef(run, "file_blob", f"{number:064x}"): (
            f"feedface{number:024x}",
            CONTEXT.project_id,
            f"{number:064x}",
            f"objects/{CONTEXT.project_id}/v1/{number:064x}",
            1,
            0,
            created,
        )
        for number in range(1, count + 1)
    }
    observed, parsed = [], []
    parse = published_reader._object

    def statement(connection, cursor, sql, parameters, context, many):
        if sql.startswith("WITH wanted"):
            observed.append((sql, parameters))

    def checked(row):
        parsed.append(row["id"])
        return parse(row)

    event.listen(pg["app"], "before_cursor_execute", statement)
    monkeypatch.setattr(published_reader, "_object", checked)
    try:
        with pg["app"].connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            reader._final_refs(connection, CONTEXT, identities)
        assert len(parsed) == count and len(set(parsed)) == count
        assert len(observed) == 1
        sql, parameters = observed[0]
        assert "jsonb_to_recordset" in sql and "CASE WHEN" in sql and "LIMIT " in sql
        assert len(parameters) <= 64
        assert len(parameters["expected"].encode()) <= published_reader.MAX_REF_INPUT_BYTES
        with pg["owner"].begin() as connection:
            connection.execute(
                text("DELETE FROM artifact_refs WHERE owner_id=:owner AND artifact_id=:artifact"),
                {"owner": run, "artifact": "feedface" + f"{count:024x}"},
            )
        parsed.clear()
        with (
            pg["app"].connect() as connection,
            pytest.raises(ArtifactError, match="^publication_reference_changed$"),
        ):
            reader._final_refs(connection, CONTEXT, identities)
        assert len(parsed) == count - 1
        # Both input bounds refuse before a driver statement is issued.
        before = len(observed)
        excessive = {**identities, GraphRef(run, "file_blob", "f" * 64): ()}
        with (
            pg["app"].connect() as connection,
            pytest.raises(ArtifactError, match="^artifact_graph_limit$"),
        ):
            reader._final_refs(connection, CONTEXT, excessive)
        monkeypatch.setattr(published_reader, "MAX_REF_INPUT_BYTES", 1)
        with (
            pg["app"].connect() as connection,
            pytest.raises(ArtifactError, match="^artifact_graph_limit$"),
        ):
            reader._final_refs(connection, CONTEXT, identities)
        assert len(observed) == before
    finally:
        event.remove(pg["app"], "before_cursor_execute", statement)


@pytest.mark.parametrize("role", ["result", "task"])
def test_postgres_declared_object_budget_refuses_before_target_storage(
    pg, published_pg, monkeypatch, role
):
    _, run, _, reader = published_pg
    # PostgreSQL's real descriptor columns cannot hold SQLite's oversized
    # timestamp text. A large positive BIGINT is legal and exercises the
    # independent declared-read budget without weakening the frozen schema.
    with pg["owner"].begin() as connection:
        target = connection.execute(
            text(
                "SELECT artifact_id FROM artifact_refs "
                "WHERE project_id=:project AND owner_id=:owner AND role=:role"
            ),
            {"project": CONTEXT.project_id, "owner": run, "role": role},
        ).scalar_one()
        connection.execute(
            text("UPDATE artifact_objects SET byte_count=:size WHERE id=:id"),
            {"size": published_reader.MAX_BYTES + 1, "id": target},
        )
    loaded = []
    load = reader.repositories.artifact_loader

    def checked(value):
        assert value.id != target, "Over-budget object reached storage"
        loaded.append(value.id)
        return load(value)

    monkeypatch.setattr(reader.repositories, "artifact_loader", checked)
    with pytest.raises(ArtifactError, match="^artifact_graph_limit$"):
        reader.read_current(CONTEXT, run)
    if role == "result":
        assert loaded == []
    else:
        assert loaded
