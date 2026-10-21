"""Actual SELECT-only source receipts; separate owner commits at deterministic barriers."""

import json

import pytest
import test_migrations_postgres as migrations
import test_published_reader_postgres as reader_tests
from publication_fixture import CONTEXT, JOB
from sqlalchemy import event, text
from test_legacy_views import result_object

from agent_rewind.legacy_reads import MAX_NODES, LegacyReads, ReadBudget
from agent_rewind.legacy_views import LegacyViews
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
published_pg = reader_tests.published_pg
pytestmark = pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL views")


def add_second(connection):
    other_job, second = "9" * 32, "8" * 32
    connection.execute(
        text(
            "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
            "VALUES(:id,'run',5,:d,'queued',false,1,0)"
        ),
        {"id": other_job, "d": "0" * 64},
    )
    connection.execute(
        text("INSERT INTO records VALUES(:id,'run',5,CAST(:d AS JSON))"),
        {"id": second, "d": json.dumps({"parent_id": None, "job_id": other_job})},
    )
    for kind, ident in (("job", other_job), ("run", second)):
        connection.execute(
            text("INSERT INTO resource_scopes VALUES(:kind,:id,:p)"),
            {"kind": kind, "id": ident, "p": CONTEXT.project_id},
        )


@pytest.mark.parametrize("kind", ["run", "job"])
@pytest.mark.parametrize("change", ["scope", "body", "phantom"])
def test_postgres_final_statement_refuses_earlier_closure_change(
    pg, published_pg, monkeypatch, kind, change
):
    capture, first, _, reader = published_pg
    with pg["owner"].begin() as writer:
        add_second(writer)
        writer.execute(text("UPDATE records SET created=10 WHERE id=:id"), {"id": first})
        writer.execute(text("UPDATE jobs SET created=10 WHERE id=:id"), {"id": JOB})
    views = LegacyViews(reader, 64 * 1024 * 1024)
    method = views.runs if kind == "run" else views.jobs
    assert len(method(CONTEXT)) == 2
    original = LegacyReads.resource
    calls = 0

    def changed(self, k, ident):
        nonlocal calls
        result = original(self, k, ident)
        calls += 1
        if calls == 4:
            with pg["owner"].begin() as writer:
                if change == "scope":
                    # This owner scope is required by the already validated run.
                    writer.execute(
                        text(
                            "DELETE FROM resource_scopes "
                            "WHERE resource_kind='job' AND resource_id=:id"
                        ),
                        {"id": JOB},
                    )
                elif change == "body":
                    writer.execute(
                        text(
                            "UPDATE records SET data=(data::jsonb || CAST(:patch AS jsonb))::json "
                            "WHERE id=:id"
                        ),
                        {"id": first, "patch": json.dumps({"name": "changed"})},
                    )
                else:
                    new = "7" * 32
                    writer.execute(
                        text("INSERT INTO records VALUES(:id,'run',1,CAST(:d AS JSON))"),
                        {"id": new, "d": json.dumps({"parent_id": None, "job_id": JOB})},
                    )
                    writer.execute(
                        text("INSERT INTO resource_scopes VALUES('run',:id,:p)"),
                        {"id": new, "p": CONTEXT.project_id},
                    )
        return result

    monkeypatch.setattr(LegacyReads, "resource", changed)
    with pytest.raises(ResourceNotFound):
        method(CONTEXT)
    assert calls == 4


def test_postgres_maximum_matching_source_receipts_and_missing_scope(pg, published_pg):
    _, _, _, reader = published_pg
    budget = ReadBudget()
    entries = []
    for index in range(MAX_NODES):
        ident = f"{index:032x}"
        body = json.dumps({"parent_id": None, "job_id": JOB})
        entries.append({"id": ident, "body": body})
        budget.remember("run", {"id": ident, "created": 1.0, "body": body})
    with pg["owner"].begin() as writer:
        writer.execute(text("INSERT INTO records VALUES(:id,'run',1,CAST(:body AS JSON))"), entries)
        writer.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:p)"),
            [{"id": item["id"], "p": CONTEXT.project_id} for item in entries],
        )
    statements = []

    def observed(conn, cursor, sql, parameters, context, many):
        if "source_receipts AS MATERIALIZED" in sql:
            statements.append((sql, len(parameters)))

    event.listen(pg["app"], "before_cursor_execute", observed)
    try:
        with reader._connection() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            budget.final(connection, CONTEXT)
            with pg["owner"].begin() as writer:
                writer.execute(
                    text(
                        "DELETE FROM resource_scopes WHERE resource_kind='run' AND resource_id=:id"
                    ),
                    {"id": entries[0]["id"]},
                )
            with pytest.raises(ResourceNotFound):
                budget.final(connection, CONTEXT)
    finally:
        event.remove(pg["app"], "before_cursor_execute", observed)
    assert len(statements) == 2 and max(count for _, count in statements) <= 64
    assert all("jsonb_to_recordset" in sql and "FOR UPDATE" not in sql for sql, _ in statements)


def test_postgres_job_result_original_receipt_and_fresh_final_grant(pg, published_pg, monkeypatch):
    capture, run, _, reader = published_pg
    value = result_object(capture, JOB, {"run_id": run})
    views = LegacyViews(reader, 64 * 1024 * 1024)
    assert views.jobs(CONTEXT)[0]["result"] == {"run_id": run}
    original = ReadBudget.final

    def revoked(self, connection, context):
        original(self, connection, context)
        with pg["owner"].begin() as writer:
            writer.execute(
                text(
                    "UPDATE project_memberships SET revoked_at='2026-01-01' WHERE principal_id=:id"
                ),
                {"id": context.principal_id},
            )

    monkeypatch.setattr(ReadBudget, "final", revoked)
    with pytest.raises(ResourceNotFound):
        views.jobs(CONTEXT)
    assert value.project_id == CONTEXT.project_id
