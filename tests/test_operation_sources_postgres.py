"""Actual PG source/receipt SQL with a SELECT-only principal; no service gate."""

import pytest
import test_admission_repository_postgres as repository_pg
import test_migrations_postgres as migrations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_admission_repository import insert
from test_admission_schema import JOB, PROJECT
from test_artifact_metadata import OTHER
from test_operation_sources import result_ref, roots, snapshot

from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.operation_reads import ReceiptBook, observe_result
from agent_rewind.operation_sources import (
    cohort_query,
    matching_query,
    read_run_cohort,
    verify_read_snapshot,
)
from agent_rewind.operation_work import OperationWork, operation_connection

pg = migrations.pg
storage_pg = repository_pg.storage_pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL operation source primitives"
)
__all__ = ["pg", "storage_pg"]


@pytest.fixture
def source_pg(storage_pg):
    f = storage_pg
    with f.engine.begin() as connection:
        insert(f, connection)
        connection.execute(
            text(
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "SELECT :other,organization_id,'Other',created_at FROM projects WHERE id=:project"
            ),
            {"other": OTHER, "project": PROJECT},
        )
        connection.exec_driver_sql(
            "GRANT SELECT ON operations,jobs,records,resource_scopes,artifact_objects,"
            f"artifact_refs TO {f.pg['app_role']}"
        )
    return f


@pytest.mark.parametrize("count,distractors", [(0, 0), (255, 0), (0, 2000), (255, 2000)])
def test_postgres_max_matching_native_types_and_scan_trace(source_pg, count, distractors):
    f = source_pg
    ids = roots(f, count) if count else []
    if distractors:
        roots(f, distractors, start=1000, job="e" * 32)
        roots(f, distractors, start=4000, project=OTHER, update={"parent_id": "malformed"})
        roots(f, 1, start=7000, job="e" * 32, update={"padding": "x" * (2 * 1024 * 1024)})
    if ids:
        result_ref(f, ids[-1])
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET reserved=:value WHERE id=:id"), {"value": 2**53 + 1, "id": JOB}
        )
    work = OperationWork()
    with operation_connection(f.pg["app"], work) as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'jobs','SELECT'),"
            "has_table_privilege(current_user,'jobs','UPDATE'),"
            "has_table_privilege(current_user,'operations','UPDATE'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, False, False, False)
        book, cohort, _, job, _ = snapshot(f, connection)
        assert job.row()["reserved"] == 2**53 + 1
        assert type(job.row()["cancel"]) is bool
        query, params = matching_query(connection, f.context, book, cohort)
        compiled = query.compile(dialect=connection.dialect)
        assert len(compiled.params) <= 64 and len(params) == 1
        verify_read_snapshot(connection, f.context, book, cohort)
        assert len(book.receipts) == count + (4 if count else 3)
        assert book.source_visits == count + 1 and book.edges == 2 * count
        print(
            f"PG count={count} distractors={distractors} binds={len(compiled.params)} "
            f"attempts={work.statements} seconds={work._elapsed():.6f}"
        )
    assert work.statements < 512 and work.seconds < 10 and work._started is None


@pytest.mark.parametrize("change", ["phantom", "body", "scope", "result", "extra", "created"])
def test_postgres_final_read_committed_owner_changes_refuse(source_pg, change):
    f = source_pg
    ids = roots(f, 1)
    if change in ("extra", "created"):
        value = result_ref(f, ids[0], publish=False)
    work = OperationWork()
    with operation_connection(f.pg["app"], work) as connection:
        book, cohort, *_ = snapshot(f, connection)
    if change == "phantom":
        roots(f, 1, start=2)
    elif change in ("result", "extra"):
        result_ref(f, "e" * 32, publish=False, object_id="8" * 32)
    else:
        with f.engine.begin() as connection:
            if change == "body":
                connection.execute(
                    text("UPDATE records SET data=CAST(:body AS JSON) WHERE id=:id"),
                    {
                        "body": '{"job_id":"' + JOB + '","parent_id":null,"changed":true}',
                        "id": ids[0],
                    },
                )
            elif change == "scope":
                connection.execute(
                    text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": ids[0]}
                )
            else:
                connection.execute(
                    text("UPDATE artifact_objects SET created_at='infinity' WHERE id=:id"),
                    {"id": value.id},
                )
    with (
        operation_connection(f.pg["app"], work) as connection,
        pytest.raises(AdmissionStorageError),
    ):
        verify_read_snapshot(connection, f.context, book, cohort)


@pytest.mark.parametrize("count,size", [(256, 0), (3, 1500000), (1, 2 * 1024 * 1024 + 1)])
def test_postgres_aggregate_markers_precede_body_decode(source_pg, count, size):
    f = source_pg
    roots(f, count, update={"padding": "x" * size})
    from agent_rewind.operation_reads import read_job

    book = ReceiptBook()
    with operation_connection(f.pg["app"], OperationWork()) as connection:
        job = read_job(connection, f.context, JOB, book)
        rows = connection.execute(cohort_query(connection, f.context, JOB, book)).all()
        assert len(rows) == count and all(all(value is None for value in row) for row in rows)
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, book)


@pytest.mark.parametrize("timestamp", ["infinity", "-infinity"])
def test_postgres_timestamp_text_refusal_not_driver_datetime_decode(source_pg, timestamp):
    f = source_pg
    value = result_ref(f, "1" * 32, publish=False)
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE artifact_objects SET created_at=CAST(:value AS TIMESTAMPTZ) WHERE id=:id"),
            {"value": timestamp, "id": value.id},
        )
    with (
        operation_connection(f.pg["app"], OperationWork()) as connection,
        pytest.raises(ArtifactError),
    ):
        observe_result(connection, f.context, JOB, ReceiptBook())


@pytest.mark.parametrize("project", [PROJECT, OTHER])
def test_postgres_reassigned_member_respects_original_project_snapshot(source_pg, project):
    f = source_pg
    original_ids = roots(f, 1)
    incoming = roots(f, 1, start=2, project=project, job="e" * 32)[0]
    work = OperationWork()
    with operation_connection(f.pg["app"], work) as connection:
        book, cohort, *_ = snapshot(f, connection)
        original = book.encoded()
        assert cohort.ids == tuple(original_ids)
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET data=CAST(:body AS JSON) WHERE id=:id"),
            {
                "body": '{"job_id":"' + JOB + '","parent_id":null,"source":"preserved"}',
                "id": incoming,
            },
        )
    with operation_connection(f.pg["app"], work) as connection:
        raw = connection.connection.driver_connection
        if project == PROJECT:
            with pytest.raises(AdmissionStorageError):
                verify_read_snapshot(connection, f.context, book, cohort)
        else:
            verify_read_snapshot(connection, f.context, book, cohort)
    assert book.encoded() == original
    assert cohort.ids == tuple(original_ids)
    assert work._started is None and connection.closed and raw.closed


def test_postgres_select_role_denies_real_mutations_then_reads_cleanly(source_pg):
    f = source_pg
    roots(f, 1)
    statements = (
        "UPDATE jobs SET cancel=TRUE WHERE id=:id",
        "UPDATE operations SET kind='run' WHERE job_id=:id",
    )
    for statement in statements:
        with pytest.raises(DBAPIError) as caught, f.pg["app"].begin() as denied:
            denied_raw = denied.connection.driver_connection
            denied.execute(text(statement), {"id": JOB})
        assert caught.value.orig.sqlstate == "42501"
        assert denied.closed and denied_raw.closed
        with operation_connection(f.pg["app"], OperationWork()) as connection:
            raw = connection.connection.driver_connection
            book, cohort, _, job, _ = snapshot(f, connection)
            assert job.row()["cancel"] is False
            verify_read_snapshot(connection, f.context, book, cohort)
        assert connection.closed and raw.closed
