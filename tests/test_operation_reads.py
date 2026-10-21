"""Raw receipts use actual scoped ar6 rows; no operation-service/PG claim."""

from dataclasses import replace

import pytest
from sqlalchemy import text
from test_admission_repository import (
    admission_engine,
    insert,
    repository,
    transaction,
)
from test_admission_schema import JOB, OPERATION, PROJECT

from agent_rewind import operation_reads
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.operation_reads import (
    JOB_LIMITS,
    ReceiptBook,
    read_descriptor,
    read_job,
    read_operation,
)
from agent_rewind.scoped_lineage import ResourceNotFound

__all__ = ["admission_engine", "repository"]


@pytest.fixture
def stored(repository):
    with transaction(repository.engine) as connection:
        insert(repository, connection)
    return repository


def test_original_operation_all_sixteen_job_fields_and_config_receipt(stored):
    f = stored
    book = ReceiptBook()
    with f.engine.connect() as connection:
        value, operation = read_operation(connection, f.context, OPERATION, book)
        job = read_job(connection, f.context, JOB, book)
        descriptor, config = read_descriptor(connection, f.context, JOB, "admission_config", book)
    assert value.principal_id == f.principal.principal_id
    assert len(operation.fields) == 14 and len(job.fields) == 16 and len(config.fields) == 8
    assert job.fields == tuple(JOB_LIMITS)
    assert job.row()["error"] is None and job.row()["result"] is None
    assert type(job.row()["cancel"]) is int  # never Boolean-coerced on SQLite
    assert descriptor == f.value.configuration_binding.descriptor
    assert config.row()["reference_id"] == descriptor.id
    assert book.receipts == (operation, job, config)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "running"),
        ("reserved", 700000),
        ("error", ""),
        ("result", "b" * 64),
        ("execution_config_digest", "a" * 64),
        ("lease_until", 1800000000.125),
    ],
)
def test_second_read_cannot_replace_original_job_receipt(stored, field, value):
    f = stored
    book = ReceiptBook()
    with f.engine.connect() as connection:
        original = read_job(connection, f.context, JOB, book)
    with f.engine.begin() as connection:
        # Fixed allowlisted test field, not product SQL.
        if field == "execution_config_digest":
            connection.execute(
                text(
                    "UPDATE jobs SET execution_config_ref=:v,execution_config_digest=:v "
                    "WHERE id=:id"
                ),
                {"v": value, "id": JOB},
            )
        else:
            connection.execute(
                text(f"UPDATE jobs SET {field}=:v WHERE id=:id"), {"v": value, "id": JOB}
            )
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        read_job(connection, f.context, JOB, book)
    assert book.receipts == (original,)


def test_error_null_empty_and_json_text_are_retained_without_parsing(stored):
    f = stored
    for error in (None, "", '{"code":"outcome_uncertain"}'):
        with f.engine.begin() as connection:
            connection.execute(
                text("UPDATE jobs SET error=:v WHERE id=:id"), {"v": error, "id": JOB}
            )
        with f.engine.connect() as connection:
            receipt = read_job(connection, f.context, JOB, ReceiptBook())
        assert receipt.row()["error"] == error


@pytest.mark.parametrize(
    "field,value",
    [
        ("error", "x" * 1201),
        ("error", b"\x00" * 2000),
        ("cancel", 7),
        ("reserved", 0.25),
        ("owner", "o" * 65),
        ("created", "not-number"),
    ],
)
def test_malformed_job_cells_refuse_and_oversize_is_null_before_parser(
    stored, monkeypatch, field, value
):
    f = stored
    with f.engine.begin() as connection:
        connection.execute(
            text(f"UPDATE jobs SET {field}=:v WHERE id=:id"), {"v": value, "id": JOB}
        )
    seen = []
    original = operation_reads._columns
    # Observe the actual SQLAlchemy body result immediately after execute,
    # before read_job's Python validators, rather than inspecting SQL text.
    from sqlalchemy.engine import Connection

    execute = Connection.execute

    def observe(connection, statement, *args, **kwargs):
        result = execute(connection, statement, *args, **kwargs)
        if getattr(statement, "is_select", False):
            rows = result.mappings().all()
            seen.extend(dict(row) for row in rows)

            class Rows:
                def mappings(self):
                    return self

                def all(self):
                    return rows

            return Rows()
        return result

    monkeypatch.setattr(Connection, "execute", observe)
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        read_job(connection, f.context, JOB, ReceiptBook())
    assert seen
    if field == "error" or field == "owner":
        assert all(item is None for item in seen[0].values())
    assert operation_reads._columns is original


def test_missing_or_foreign_job_scope_never_returns_body(stored):
    f = stored
    for context, job_id in ((f.context, "f" * 32), (replace(f.context, project_id="f" * 32), JOB)):
        with f.engine.connect() as connection, pytest.raises(ResourceNotFound):
            read_job(connection, context, job_id, ReceiptBook())


def test_remaining_aggregate_bytes_are_applied_in_sql_before_transfer(stored, monkeypatch):
    f = stored
    book = ReceiptBook()
    book.byte_count = 4 * 1024 * 1024 - 10
    observed = []
    original = operation_reads.operation_value

    def parser(row):
        observed.append(dict(row))
        return original(row)

    monkeypatch.setattr(operation_reads, "operation_value", parser)
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        read_operation(connection, f.context, OPERATION, book)
    assert observed == [{name: None for name in operation_reads.OPERATION_LIMITS}]
    assert book.receipts == ()


def test_operation_retains_original_accepted_and_correlation_fields(stored):
    f = stored
    book = ReceiptBook()
    with f.engine.connect() as connection:
        value, original = read_operation(connection, f.context, OPERATION, book)
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE operations SET failure_correlation_id=:v WHERE id=:id"),
            {"v": "c" * 32, "id": OPERATION},
        )
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        read_operation(connection, f.context, OPERATION, book)
    assert original.row()["failure_correlation_id"] == value.failure_correlation_id
    assert book.receipts == (original,)


@pytest.mark.parametrize("change", ["created", "oversize", "second"])
def test_config_candidate_retains_all_seven_fields_and_cardinality(stored, monkeypatch, change):
    f = stored
    book = ReceiptBook()
    with f.engine.connect() as connection:
        descriptor, original = read_descriptor(connection, f.context, JOB, "admission_config", book)
    with f.engine.begin() as connection:
        if change == "second":
            connection.execute(
                text(
                    "INSERT INTO artifact_refs(project_id,owner_kind,owner_id,role,artifact_id)"
                    " VALUES(:p,'job',:j,'admission_config',:a)"
                ),
                {"p": PROJECT, "j": JOB, "a": f.value.task_binding.descriptor.id},
            )
        else:
            connection.execute(
                text("UPDATE artifact_objects SET created_at=:v WHERE id=:id"),
                {
                    "v": "2001-01-01T00:00:00+00:00"
                    if change == "created"
                    else "x" * (1024 * 1024),
                    "id": descriptor.id,
                },
            )
    observed = []
    parse = operation_reads._object

    def check(row):
        observed.append(dict(row))
        return parse(row)

    monkeypatch.setattr(operation_reads, "_object", check)
    with f.engine.connect() as connection, pytest.raises((AdmissionStorageError, ValueError)):
        read_descriptor(connection, f.context, JOB, "admission_config", book)
    if change == "oversize":
        assert observed[0]["created_at"] is None
    assert book.receipts == (original,)


def test_type_change_cannot_hide_behind_python_equality():
    book = ReceiptBook()
    book.remember("job", JOB, ("cancel",), {"cancel": 1})
    with pytest.raises(AdmissionStorageError):
        book.remember("job", JOB, ("cancel",), {"cancel": True})


def test_receipt_identity_and_byte_limits_fail_without_partial_insertion():
    book = ReceiptBook()
    for i in range(259):
        book.remember("job", f"{i:032x}", ("id",), {"id": f"{i:032x}"})
    before = book.receipts, book.byte_count
    with pytest.raises(AdmissionStorageError):
        book.remember("job", "f" * 32, ("id",), {"id": "f" * 32})
    assert (book.receipts, book.byte_count) == before
    other = ReceiptBook()
    with pytest.raises(AdmissionStorageError):
        other.remember("job", JOB, ("error",), {"error": "x" * (4 * 1024 * 1024)})
    assert other.receipts == () and other.byte_count == 2
