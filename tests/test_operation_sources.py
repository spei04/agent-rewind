"""Actual ar6 source/receipt primitives; no service/authentication claim."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import event, text
from test_admission_envelope import descriptor
from test_admission_schema import JOB, OPERATION, PROJECT, SECOND_JOB
from test_artifact_metadata import OTHER
from test_operation_reads import admission_engine, repository, stored

from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.database import records
from agent_rewind.models import canonical
from agent_rewind.operation_reads import (
    CancellationAssociation,
    ReceiptBook,
    observe_result,
    read_descriptor,
    read_job,
    read_job_state,
    read_operation,
    validate_job_row,
)
from agent_rewind.operation_sources import (
    cohort_query,
    matching_query,
    read_run_cohort,
    validate_result_member,
    verify_read_snapshot,
)
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.scoped_lineage import Lineage, ResourceNotFound
from agent_rewind.scoped_repositories import _Reads
from agent_rewind.sqlite_ownership import create_owned_sqlite_engine

__all__ = ["admission_engine", "repository", "stored"]


def roots(f, count, *, start=1, project=PROJECT, job=JOB, update=None, kind="run"):
    values = []
    for i in range(start, start + count):
        body = {"job_id": job, "parent_id": None, "source": "preserved"}
        body.update(update or {})
        values.append(dict(id=f"{i:032x}", kind=kind, created=1700000000.125, data=body))
    with f.engine.begin() as connection:
        connection.execute(records.insert(), values)
        connection.execute(
            text(
                "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
                "VALUES(:kind,:id,:project)"
            ),
            [dict(kind=kind, id=v["id"], project=project) for v in values],
        )
    return [v["id"] for v in values]


def result_ref(f, run_id, *, publish=True, object_id="9" * 32):
    value = descriptor(canonical({"run_id": run_id}), object_id=object_id, project=PROJECT)
    with f.engine.begin() as connection:
        record_verified(connection, value)
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=JOB,
            role="result",
            artifact_id=value.id,
        )
        if publish:
            connection.execute(
                text("UPDATE jobs SET result=:value WHERE id=:id"), dict(value=value.digest, id=JOB)
            )
    return value


def snapshot(f, connection, book=None):
    book = book or ReceiptBook()
    _, operation = read_operation(connection, f.context, OPERATION, book)
    job = read_job(connection, f.context, JOB, book)
    _, config = read_descriptor(connection, f.context, JOB, "admission_config", book)
    observe_result(connection, f.context, JOB, book)
    cohort = read_run_cohort(connection, f.context, job, book)
    return book, cohort, operation, job, config


@pytest.mark.parametrize("count", [0, 1, 255])
def test_matching_complete_cohort_and_native_work_trace(stored, count):
    f = stored
    ids = roots(f, count) if count else []
    if ids:
        result_ref(f, ids[-1])
    engine = create_owned_sqlite_engine(str(f.engine.url), connect_timeout=3, pool_timeout=1)
    work = OperationWork()
    logical = []
    event.listen(engine, "before_cursor_execute", lambda _c, _u, s, *_a: logical.append(s))
    try:
        with operation_connection(engine, work) as connection:
            book, cohort, *_ = snapshot(f, connection)
            query, params = matching_query(connection, f.context, book, cohort)
            assert len(query.compile(dialect=connection.dialect).params) <= 64
            verify_read_snapshot(connection, f.context, book, cohort)
            assert book.source_visits == count + 1 and book.edges == 2 * count
            assert len(book.receipts) == count + (4 if ids else 3)
            assert len(book.encoded()) <= 4 * 1024 * 1024
            if ids:
                validate_result_member(cohort, ids[-1])
            assert len(params) == 1
        assert work.instructions < 20_000_000 and work.statements < 512
        assert work._started is None and engine.pool.checkedout() == 0
        print(
            f"TRACE cohort={count} vm={work.instructions} "
            f"attempts={work.statements} sql={len(logical)}"
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("matches", [0, 255])
def test_matching_and_empty_discovery_with_scoped_foreign_distractors(stored, matches):
    f = stored
    ids = roots(f, matches) if matches else []
    roots(f, 2000, start=1000, job=SECOND_JOB)
    roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "bad"})
    # These are intentionally irrelevant to this project's original-job cohort.
    roots(f, 2, start=7000, job=SECOND_JOB, update={"padding": "x" * (2 * 1024 * 1024)})
    roots(f, 2, start=7100, project=OTHER, update={"padding": "x" * (2 * 1024 * 1024)})
    if ids:
        result_ref(f, ids[0])
    work = OperationWork()
    with operation_connection(f.engine, work) as connection:
        book, cohort, *_ = snapshot(f, connection)
        first = work.instructions
        verify_read_snapshot(connection, f.context, book, cohort)
        print(
            f"DISTRACTORS matches={matches} discovery_vm={first} "
            f"total_vm={work.instructions} attempts={work.statements}"
        )
    assert work.instructions < 20_000_000 and work.statements < 512
    assert cohort.ids == tuple(ids)


def test_overflow_candidate_is_counted_before_body_transfer(stored):
    f = stored
    roots(f, 256)
    book = ReceiptBook()
    with f.engine.connect() as connection:
        job = read_job(connection, f.context, JOB, book)
        rows = connection.execute(cohort_query(connection, f.context, JOB, book)).mappings().all()
        assert len(rows) == 256 and all(all(v is None for v in row.values()) for row in rows)
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, book)
    assert not any(r.domain == "run" for r in book.receipts)


@pytest.mark.parametrize("count,size", [(3, 1500000), (1, 2 * 1024 * 1024 + 1)])
def test_sum_and_single_body_gates_before_materialization(stored, count, size):
    f = stored
    roots(f, count, update={"padding": "x" * size})
    book = ReceiptBook()
    with f.engine.connect() as connection:
        read_job(connection, f.context, JOB, book)
        rows = connection.execute(cohort_query(connection, f.context, JOB, book)).all()
    assert len(rows) == count
    assert all(all(value is None for value in row) for row in rows)


def test_raw_transfer_fits_but_canonical_expansion_refuses(stored):
    f = stored
    roots(f, 2, update={"padding": "\x01" * 320000})
    book = ReceiptBook()
    with f.engine.connect() as connection:
        job = read_job(connection, f.context, JOB, book)
        # Raw JSON <=4MiB, but receipt encoding escapes its existing backslashes.
        assert all(
            row.body is not None
            for row in connection.execute(cohort_query(connection, f.context, JOB, book))
        )
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, book)


@pytest.mark.parametrize("mutation", ["parent", "missing_parent", "study", "blob", "duplicate"])
def test_complete_cohort_rejects_the_same_invalid_lineage(stored, mutation):
    f = stored
    kind = "study" if mutation == "study" else "run"
    ids = roots(f, 1, kind=kind)
    body = {"job_id": JOB, "parent_id": None}
    if mutation == "parent":
        body["parent_id"] = "f" * 32
    if mutation == "missing_parent":
        del body["parent_id"]
    value = json.dumps(body)
    if mutation == "duplicate":
        value = '{"job_id":"' + JOB + '","parent_id":null,"parent_id":null}'
    if mutation == "blob":
        value = value.encode()
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE records SET data=:value WHERE id=:id"), dict(value=value, id=ids[0])
        )
    with f.engine.connect() as connection:
        reads = _Reads(connection, f.context)
        if mutation == "blob":
            # Legacy lineage casts JSON to text; the new native-type contract
            # deliberately rejects this additional SQLite representation.
            assert Lineage(reads.record, reads.job, reads.by_job).validate("job", JOB)
        else:
            with pytest.raises(ResourceNotFound):
                Lineage(reads.record, reads.job, reads.by_job).validate("job", JOB)
        book = ReceiptBook()
        job = read_job(connection, f.context, JOB, book)
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, book)


@pytest.mark.parametrize("mutation", ["body", "body_blob", "scope", "phantom", "created"])
def test_final_original_source_scope_type_and_phantom_comparison(stored, mutation):
    f = stored
    ids = roots(f, 1)
    with f.engine.connect() as connection:
        book, cohort, *_ = snapshot(f, connection)
    if mutation == "phantom":
        roots(f, 1, start=2)
    else:
        with f.engine.begin() as connection:
            if mutation == "scope":
                connection.execute(
                    text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": ids[0]}
                )
            elif mutation == "body_blob":
                connection.execute(
                    text("UPDATE records SET data=CAST(data AS BLOB) WHERE id=:id"), {"id": ids[0]}
                )
            elif mutation == "created":
                connection.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": ids[0]}
                )
            else:
                connection.execute(
                    text("UPDATE records SET data=:body WHERE id=:id"),
                    {
                        "id": ids[0],
                        "body": json.dumps({"job_id": JOB, "parent_id": None, "changed": True}),
                    },
                )
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        verify_read_snapshot(connection, f.context, book, cohort)


@pytest.mark.parametrize("transition", ["0to1", "1to0", "1to2", "swap", "created", "blob"])
def test_optional_result_ref_count_and_seven_field_drift(stored, transition):
    f = stored
    ids = roots(f, 1)
    if transition != "0to1":
        value = result_ref(f, ids[0], publish=False)
    with f.engine.connect() as connection:
        book, cohort, *_ = snapshot(f, connection)
        assert read_job_state(connection, f.context, JOB, book).row()["result"] is None
        verify_read_snapshot(connection, f.context, book, cohort)
    if transition == "0to1":
        result_ref(f, ids[0], publish=False)
    elif transition == "1to2":
        result_ref(
            f, "e" * 32, publish=False, object_id="8" * 32
        )  # distinct descriptor, same owner/role
    else:
        with f.engine.begin() as connection:
            if transition == "1to0":
                connection.execute(text("DELETE FROM artifact_refs WHERE role='result'"))
            elif transition == "swap":
                connection.execute(
                    text("UPDATE artifact_refs SET artifact_id=:id WHERE role='result'"),
                    {"id": f.value.task_binding.descriptor.id},
                )
            elif transition == "blob":
                connection.execute(
                    text(
                        "UPDATE artifact_objects SET created_at=CAST(created_at AS BLOB) "
                        "WHERE id=:id"
                    ),
                    {"id": value.id},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE artifact_objects SET created_at='2001-01-01T00:00:00+00:00' "
                        "WHERE id=:id"
                    ),
                    {"id": value.id},
                )
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        verify_read_snapshot(connection, f.context, book, cohort)


def test_final_integer_real_expected_type_is_not_sql_equality(stored):
    f = stored
    with f.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET created=1.0 WHERE id=:id"), {"id": JOB})
    with f.engine.connect() as connection:
        book, cohort, *_ = snapshot(f, connection)
    # Both native types pass the pure decoder, but only the original matches SQL.
    receipt = book._receipts["job", JOB]
    values = receipt.row()
    assert type(values["created"]) is float and values["created"] == 1
    values["created"] = 1
    validate_job_row(values, JOB)
    book._receipts["job", JOB] = replace(receipt, values=tuple(values[k] for k in receipt.fields))
    with f.engine.connect() as connection:
        query, parameters = matching_query(connection, f.context, book, cohort)
        returned = set(connection.execute(query, parameters).all())
        assert ("job", JOB) not in returned
        assert returned == {("operation", OPERATION), ("admission_config", JOB)}
        with pytest.raises(AdmissionStorageError):
            verify_read_snapshot(connection, f.context, book, cohort)


def test_cancellation_mutable_progress_and_large_integer_never_replace_get_receipt(stored):
    f = stored
    with f.engine.connect() as connection:
        book, _, op, original, config = snapshot(f, connection)
    association = CancellationAssociation.capture(op, original, config)
    with f.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE jobs SET status='running',owner='worker',lease_until=1800000000.5,"
                "cancel=true,reserved=:reserved,result=:result,error='legacy failure' WHERE id=:id"
            ),
            dict(reserved=2**53 + 1, result="b" * 64, id=JOB),
        )
    with f.engine.connect() as connection:
        current = read_job_state(connection, f.context, JOB, book)
        assert current.row()["reserved"] == 2**53 + 1 > current.row()["budget"]
        association.require_matches(op, current, config)
        assert book._receipts["job", JOB] is original
        assert book.source_visits == 2
        with pytest.raises(AdmissionStorageError):
            read_job(connection, f.context, JOB, book)


@pytest.mark.parametrize(
    "field,value",
    [
        ("created", 1800000000.5),
        ("payload", "b" * 64),
        ("budget", 12),
        ("actor", "oidc:" + "c" * 64),
        ("payload_version", 1),
        ("kind", "branch"),
        ("execution_config_ref", "b" * 64),
        ("execution_config_digest", "b" * 64),
        ("status", "unknown"),
        ("reserved", 0.5),
    ],
)
def test_cancellation_immutable_change_or_malformed_fresh_state_refuses(stored, field, value):
    f = stored
    with f.engine.connect() as connection:
        _, _, op, job, config = snapshot(f, connection)
    association = CancellationAssociation.capture(op, job, config)
    values = job.row()
    values[field] = value
    changed = replace(job, values=tuple(values[k] for k in job.fields))
    with pytest.raises(AdmissionStorageError):
        association.require_matches(op, changed, config)


def test_repeated_source_work_never_resets(stored):
    f = stored
    with f.engine.connect() as connection:
        book = ReceiptBook()
        for _ in range(256):
            read_job_state(connection, f.context, JOB, book)
        with pytest.raises(AdmissionStorageError):
            read_job_state(connection, f.context, JOB, book)
    assert book.source_visits == 256


def test_remaining_native_work_refuses_without_leaked_owned_callbacks(stored):
    from agent_rewind.admission_transaction import AdmissionError
    from agent_rewind.sqlite_ownership import owned_connect

    f = stored
    roots(f, 255)
    engine = create_owned_sqlite_engine(str(f.engine.url), connect_timeout=3, pool_timeout=1)
    work = OperationWork()
    # Prior phases consume this same fixed20M allowance; no ceiling is patched.
    work.instructions = 19_999_000
    try:
        with pytest.raises(AdmissionError), operation_connection(engine, work) as connection:
            snapshot(f, connection)
        assert work.instructions >= 20_000_000
        assert work._started is None and engine.pool.checkedout() == 0
        with owned_connect(engine) as connection:
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0
            assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("candidate", ["missing", "foreign", "oversize"])
def test_bad_second_result_candidate_never_becomes_unique(stored, candidate):
    f = stored
    ids = roots(f, 1)
    result_ref(f, ids[0], publish=False)
    if candidate == "foreign":
        foreign = descriptor(canonical({"run_id": "e" * 32}), object_id="f" * 32, project=OTHER)
        with f.engine.begin() as connection:
            record_verified(connection, foreign)
    with f.engine.connect() as connection:
        # Deliberate corruption, never a production setup or read policy.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        if candidate == "oversize":
            target = f.value.task_binding.descriptor.id
            connection.execute(
                text("UPDATE artifact_objects SET locator=:value WHERE id=:id"),
                {"value": "x" * 20000, "id": target},
            )
        elif candidate == "foreign":
            target = foreign.id
        else:
            target = "f" * 32
        connection.execute(
            text(
                "INSERT INTO artifact_refs(project_id,owner_kind,owner_id,role,artifact_id)"
                " VALUES(:project,'job',:job,'result',:target)"
            ),
            {"project": PROJECT, "job": JOB, "target": target},
        )
        connection.commit()
    with f.engine.connect() as connection, pytest.raises(AdmissionStorageError):
        observe_result(connection, f.context, JOB, ReceiptBook())


def test_exact_result_membership_never_chooses_first_or_foreign_alias(stored):
    f = stored
    own = roots(f, 2)
    foreign = roots(f, 1, start=10, project=OTHER)
    with f.engine.connect() as connection:
        _, cohort, *_ = snapshot(f, connection)
        assert cohort.ids == tuple(own)
        for identifier in own:
            validate_result_member(cohort, identifier)
        with pytest.raises(AdmissionStorageError):
            validate_result_member(cohort, foreign[0])


def test_matching_query_rejects_nonnull_result_without_matching_digest(stored):
    f = stored
    roots(f, 1)
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET result=:digest WHERE id=:id"), {"digest": "b" * 64, "id": JOB}
        )
    with f.engine.connect() as connection:
        book, cohort, *_ = snapshot(f, connection)
        with pytest.raises(AdmissionStorageError):
            matching_query(connection, f.context, book, cohort)


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "x" * 65),
        ("error", "x" * 1201),
        ("error", "é" * 601),
        ("owner", b"worker"),
        ("lease_until", float("inf")),
        ("created", float("nan")),
    ],
)
def test_pure_job_decoder_preserves_sql_cell_and_native_limits(stored, field, value):
    with stored.engine.connect() as connection:
        job = read_job(connection, stored.context, JOB, ReceiptBook())
    row = job.row()
    row[field] = value
    with pytest.raises(AdmissionStorageError):
        validate_job_row(row, JOB)


@pytest.mark.parametrize(
    "domain,field,value",
    [
        ("operation", "client_operation_id", "changed"),
        ("operation", "request_digest", "d" * 64),
        ("operation", "failure_correlation_id", "d" * 32),
        ("admission_config", "created_at", "2026-01-02T00:00:00+00:00"),
        ("admission_config", "byte_count", 4),
        ("admission_config", "reference_id", "c" * 32),
    ],
)
def test_cancellation_original_operation_and_config_receipts_are_immutable(
    stored, domain, field, value
):
    with stored.engine.connect() as connection:
        _, _, op, job, config = snapshot(stored, connection)
    original = CancellationAssociation.capture(op, job, config)
    receipt = op if domain == "operation" else config
    row = receipt.row()
    assert field in row
    row[field] = value
    changed = replace(receipt, values=tuple(row[k] for k in receipt.fields))
    with pytest.raises(AdmissionStorageError):
        original.require_matches(
            changed if domain == "operation" else op,
            job,
            changed if domain == "admission_config" else config,
        )


def test_selected_unknown_kind_corruption_is_not_filtered_from_cohort(stored):
    f = stored
    identity = roots(f, 1)[0]
    with f.engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
        connection.execute(text("UPDATE records SET kind='unknown' WHERE id=:id"), {"id": identity})
        connection.execute(
            text("UPDATE resource_scopes SET resource_kind='unknown' WHERE resource_id=:id"),
            {"id": identity},
        )
    with f.engine.connect() as connection:
        book = ReceiptBook()
        job = read_job(connection, f.context, JOB, book)
        candidates = connection.execute(cohort_query(connection, f.context, JOB, book)).all()
        assert len(candidates) == 1 and candidates[0].kind == "unknown"
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, book)


def test_final_extra_configuration_candidate_cannot_be_filtered(stored):
    f = stored
    with f.engine.connect() as connection:
        book, cohort, *_ = snapshot(f, connection)
    with f.engine.begin() as connection:
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=JOB,
            role="admission_config",
            artifact_id=f.value.task_binding.descriptor.id,
        )
    with f.engine.connect() as connection:
        query, params = matching_query(connection, f.context, book, cohort)
        assert connection.execute(query, params).all() == []
        with pytest.raises(AdmissionStorageError):
            verify_read_snapshot(connection, f.context, book, cohort)
