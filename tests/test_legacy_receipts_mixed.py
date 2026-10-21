"""Mixed job/record receipt work bounds on SQLite and opt-in PostgreSQL.

Fixtures use the existing frozen ownership setup. These tests exercise the real
single-statement reader, not HTTP activation, publication or a compatible release.
"""

from contextlib import contextmanager

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import Text, cast, create_engine, event, insert, select, text, update
from test_scoped_repositories import CA, A, B, populate
from test_scoped_repositories_postgres import prepare as prepare_postgres

from agent_rewind.database import jobs, records
from agent_rewind.legacy_reads import MAX_NODES, MAX_RECEIPT_BYTES, ReadBudget
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
VM_LIMIT = 4_000_000


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite://")
    populate(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def mixed_receipts(engine, pairs):
    job_ids = [f"{index + 0x10000:032x}" for index in range(pairs)]
    run_ids = [f"{index + 0x20000:032x}" for index in range(pairs)]
    with engine.begin() as connection:
        connection.execute(
            insert(jobs),
            [
                {
                    "id": ident,
                    "kind": "run",
                    "created": 1.25,
                    "payload": "0" * 64,
                    "status": "queued",
                    "cancel": False,
                    "budget": 10,
                    "reserved": 3,
                    "owner": None,
                    "lease_until": None,
                    "result": None,
                    "error": None,
                    "actor": "synthetic-reader",
                }
                for ident in job_ids
            ],
        )
        connection.execute(
            insert(records),
            [
                {
                    "id": run_id,
                    "kind": "run",
                    "created": 2.5,
                    "data": {"job_id": job_id, "parent_id": None},
                }
                for run_id, job_id in zip(run_ids, job_ids, strict=True)
            ],
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
            [{"kind": "job", "id": ident, "project": A} for ident in job_ids]
            + [{"kind": "run", "id": ident, "project": A} for ident in run_ids],
        )
    budget = ReadBudget()
    # Capture the exact raw driver values used by LegacyReads; do not regenerate
    # JSON bodies or coerce nullable/Boolean/float job fields for the expectation.
    with engine.connect() as connection:
        for row in connection.execute(select(jobs).where(jobs.c.id.in_(job_ids))).mappings():
            budget.remember("job", dict(row))
        for row in connection.execute(
            select(records.c.id, records.c.created, cast(records.c.data, Text).label("body")).where(
                records.c.id.in_(run_ids)
            )
        ).mappings():
            budget.remember("run", dict(row))
    assert len(budget.receipts) == 2 * pairs and budget.receipt_bytes < MAX_RECEIPT_BYTES
    return budget, job_ids, run_ids


@contextmanager
def sqlite_statement_budget(engine, connection):
    steps, calls = [0], []

    def progress():
        steps[0] += 1000
        return int(steps[0] > VM_LIMIT)

    def observed(conn, cursor, sql, parameters, context, many):
        if "source_receipts AS MATERIALIZED" in sql:
            calls.append((sql, len(parameters)))

    raw = connection.connection.driver_connection
    event.listen(engine, "before_cursor_execute", observed)
    raw.set_progress_handler(progress, 1000)
    try:
        yield steps, calls
    finally:
        raw.set_progress_handler(None, 0)
        event.remove(engine, "before_cursor_execute", observed)


@pytest.mark.parametrize("pairs", [64, MAX_NODES // 2])
def test_sqlite_matching_mixed_receipts_stay_within_original_work_budget(sqlite_engine, pairs):
    budget, _, _ = mixed_receipts(sqlite_engine, pairs)
    with sqlite_engine.connect() as connection:
        with sqlite_statement_budget(sqlite_engine, connection) as (steps, calls):
            budget.final(connection, CA)
        assert 0 < steps[0] < VM_LIMIT
    assert len(calls) == 1 and calls[0][1] <= 64
    assert "unexpected_jobs AS MATERIALIZED" in calls[0][0]
    assert "FOR UPDATE" not in calls[0][0] and "FOR SHARE" not in calls[0][0]


def change_membership(connection, change, job_ids, run_ids):
    if change == "missing":
        connection.execute(
            text("DELETE FROM resource_scopes WHERE resource_kind='run' AND resource_id=:id"),
            {"id": run_ids[0]},
        )
    elif change == "foreign":
        connection.execute(
            text(
                "UPDATE resource_scopes SET project_id=:p "
                "WHERE resource_kind='run' AND resource_id=:id"
            ),
            {"p": B, "id": run_ids[0]},
        )
    elif change == "reassigned":
        connection.execute(
            update(records)
            .where(records.c.id == run_ids[0])
            .values(data={"job_id": job_ids[1], "parent_id": None})
        )
    else:
        assert change in {"new", "foreign_incoming"}
        ident = "e" * 32
        connection.execute(
            insert(records).values(
                id=ident,
                kind="run",
                created=1.0,
                data={"job_id": job_ids[0], "parent_id": None},
            )
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('run',:id,:p)"),
            {"id": ident, "p": A if change == "new" else B},
        )


@pytest.mark.parametrize("change", ["missing", "foreign", "new", "reassigned", "foreign_incoming"])
def test_sqlite_maximum_mixed_membership_refusal_preserves_scope_filter(sqlite_engine, change):
    budget, job_ids, run_ids = mixed_receipts(sqlite_engine, MAX_NODES // 2)
    with sqlite_engine.begin() as connection:
        change_membership(connection, change, job_ids, run_ids)
    with sqlite_engine.connect() as connection:
        with sqlite_statement_budget(sqlite_engine, connection) as (steps, calls):
            if change == "foreign_incoming":
                # Foreign incoming references cannot deny this project's job.
                budget.final(connection, CA)
            else:
                with pytest.raises(ResourceNotFound):
                    budget.final(connection, CA)
        assert 0 < steps[0] < VM_LIMIT
    assert len(calls) == 1 and calls[0][1] <= 64


@pytest.mark.parametrize(
    "field,value",
    [("owner", "changed"), ("lease_until", 5.25), ("result", "1" * 64), ("error", "changed")],
)
def test_mixed_receipts_preserve_original_null_job_fields(sqlite_engine, field, value):
    budget, job_ids, _ = mixed_receipts(sqlite_engine, 2)
    with sqlite_engine.connect() as connection:
        budget.final(connection, CA)
    with sqlite_engine.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == job_ids[0]).values({field: value}))
    with sqlite_engine.connect() as connection, pytest.raises(ResourceNotFound):
        budget.final(connection, CA)


@pytest.mark.skipif(not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL")
@pytest.mark.parametrize("change", ["missing", "foreign", "new", "reassigned", "foreign_incoming"])
def test_postgres_maximum_mixed_receipts_with_select_only_role(pg, change):
    prepare_postgres(pg)
    budget, job_ids, run_ids = mixed_receipts(pg["owner"], MAX_NODES // 2)
    calls = []

    def observed(conn, cursor, sql, parameters, context, many):
        if "source_receipts AS MATERIALIZED" in sql:
            calls.append((sql, len(parameters)))

    event.listen(pg["app"], "before_cursor_execute", observed)
    try:
        with pg["app"].connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
            assert connection.execute(
                text(
                    "SELECT has_table_privilege(current_user,'records','UPDATE'),"
                    "has_table_privilege(current_user,'jobs','INSERT'),"
                    "has_schema_privilege(current_user,'public','CREATE')"
                )
            ).one() == (False, False, False)
            budget.final(connection, CA)
            with pg["owner"].begin() as writer:
                change_membership(writer, change, job_ids, run_ids)
            if change == "foreign_incoming":
                budget.final(connection, CA)
            else:
                with pytest.raises(ResourceNotFound):
                    budget.final(connection, CA)
    finally:
        event.remove(pg["app"], "before_cursor_execute", observed)
    assert len(calls) == 2 and all(count <= 64 for _, count in calls)
    assert all(
        "jsonb_to_recordset" in sql
        and "unexpected_jobs AS MATERIALIZED" in sql
        and "FOR UPDATE" not in sql
        and "FOR SHARE" not in sql
        for sql, _ in calls
    )
