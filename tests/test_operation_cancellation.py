"""Cancellation phase ownership only; no effect, service or HTTP acceptance."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import event, text
from test_admission_schema import JOB, OPERATION, PROJECT
from test_artifact_metadata import OTHER
from test_operation_sources import admission_engine, repository, result_ref, roots, stored

from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.artifact_metadata import configure_artifact_engine, register_ref
from agent_rewind.operation_cancellation import CancellationReceipts, _association_rows
from agent_rewind.operation_reads import (
    MAX_RECEIPT_BYTES,
    ReceiptBook,
    observe_result,
    read_descriptor,
    read_job,
    read_job_state,
    read_operation,
    receipt_bytes,
)
from agent_rewind.operation_sources import (
    RunCohort,
    _matching_query,
    cohort_query,
    matching_query,
    read_run_cohort,
    verify_read_snapshot,
)
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.sqlite_ownership import create_owned_sqlite_engine

__all__ = ["admission_engine", "repository", "stored"]


@pytest.fixture
def cancellation(stored):
    engine = create_owned_sqlite_engine(str(stored.engine.url), connect_timeout=3, pool_timeout=1)
    configure_artifact_engine(engine)
    try:
        yield stored, engine
    finally:
        engine.dispose()


def association(f, phase, connection):
    book = phase.book
    _, operation = read_operation(connection, f.context, OPERATION, book)
    job = read_job(connection, f.context, JOB, book)
    _, config = read_descriptor(connection, f.context, JOB, "admission_config", book)
    phase.associate(operation, job, config)
    return job


def capture(f, phase, connection):
    return read_run_cohort(connection, f.context, association(f, phase, connection), phase.book)


def successful_phases(f, engine, count, phases):
    roots(f, count) if count else None
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    attempts = []
    previous = None
    for _ in range(phases):
        with owner.phase() as phase:
            with operation_connection(engine, owner.work) as connection:
                cohort = capture(f, phase, connection)
                book = phase.book
                retained = receipt_bytes(
                    {"original": _association_rows(phase._association), "phase": book._payload()},
                    MAX_RECEIPT_BYTES,
                )
                assert book.remaining == MAX_RECEIPT_BYTES - len(retained)
                assert book._wire_bytes == len(book.encoded())
                query, parameters = _matching_query(
                    connection, f.context, book, cohort, cancellation=True
                )
                binds = len(query.compile(dialect=connection.dialect).params)
                assert binds <= 64 and len(parameters) == 1
                phase.verify(connection, cohort)
                if previous is not None:
                    assert owner.original is previous
                previous = owner.original
            # Cleanup completes while the phase still owns its receipts.
            assert owner.work._started is None
        assert book._receipts == {} and book.observations == {}
        attempts.append(owner.work.statements)
    assert attempts == sorted(set(attempts))
    assert owner.source_visits == phases * (count + 1)
    assert owner.edges == phases * 2 * count
    assert owner.work.statements < 512 and owner.work.instructions < 20_000_000
    print(
        f"CANCEL final phases={phases} roots={count} attempts={attempts} "
        f"vm={owner.work.instructions} binds={binds}"
    )
    return owner


@pytest.mark.parametrize("count,phases", [(0, 3), (84, 3), (255, 1)])
def test_exact_phase_capacity_and_postcleanup_counters(cancellation, count, phases):
    f, engine = cancellation
    successful_phases(f, engine, count, phases)
    assert engine.pool.checkedout() == 0


def overflow_phases(f, engine):
    roots(f, 85)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    for _ in range(2):
        with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
            phase.verify(connection, capture(f, phase, connection))
    assert owner.source_visits == 172 and owner.edges == 340
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        job = association(f, phase, connection)
        rows = connection.execute(cohort_query(connection, f.context, JOB, phase.book)).all()
        assert len(rows) == 84 and all(all(v is None for v in row) for row in rows)
        read_run_cohort(connection, f.context, job, phase.book)
    assert owner.source_visits == 173 and owner.edges == 340
    with pytest.raises(AdmissionStorageError), owner.phase():
        pytest.fail("failed phase restarted")
    return owner


def test_three_85_root_phases_refuse_before_third_transfer(cancellation):
    f, engine = cancellation
    overflow_phases(f, engine)
    assert engine.pool.checkedout() == 0


def progress(f, engine):
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    original = None
    for i in range(3):
        if i:
            roots(f, 1, start=i + 1)
            with f.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE jobs SET status='running',result=:digest,reserved=:reserved "
                        "WHERE id=:job"
                    ),
                    {"digest": str(i) * 64, "reserved": 2**53 + i, "job": JOB},
                )
        with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
            cohort = capture(f, phase, connection)
            assert len(cohort.ids) == i + 1
            phase.verify(connection, cohort)
        if original is None:
            original = owner.original
        assert owner.original is original
    assert owner.source_visits == 9 and owner.edges == 12


def test_worker_result_and_cohort_progress_between_phases(cancellation):
    progress(*cancellation)


def ignored_results(f, engine):
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as phase:
        with operation_connection(engine, owner.work) as connection:
            cohort = capture(f, phase, connection)
        # Config filtering must precede LIMIT even with many malformed result refs.
        values = [
            result_ref(f, str(i) * 32, publish=False, object_id=f"{100 + i:032x}")
            for i in range(3, 7)
        ]
        with f.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text("UPDATE artifact_objects SET created_at='infinity' WHERE id=:id"),
                    {"id": values[0].id},
                )
            else:
                connection.execute(
                    text("UPDATE artifact_objects SET created_at=:v WHERE id=:id"),
                    {"v": b"not-a-timestamp", "id": values[0].id},
                )
        with operation_connection(engine, owner.work) as connection:
            phase.verify(connection, cohort)
    assert owner.original.operation.identity == OPERATION


def test_result_refs_are_ignored_even_when_extra_or_malformed(cancellation):
    ignored_results(*cancellation)


@pytest.mark.parametrize("change", ["result", "status", "phantom", "config"])
def test_within_phase_full_snapshot_refuses_changes(cancellation, change):
    f, engine = cancellation
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with pytest.raises(AdmissionStorageError), owner.phase() as phase:
        with operation_connection(engine, owner.work) as connection:
            cohort = capture(f, phase, connection)
        if change == "phantom":
            roots(f, 1, start=2)
        else:
            with f.engine.begin() as connection:
                statements = {
                    "result": "UPDATE jobs SET result=:v WHERE id=:id",
                    "status": "UPDATE jobs SET status=:v WHERE id=:id",
                    "config": "DELETE FROM artifact_refs WHERE owner_id=:id "
                    "AND role='admission_config'",
                }
                connection.execute(
                    text(statements[change]),
                    {"id": JOB, "v": "f" * 64 if change == "result" else "running"},
                )
        with operation_connection(engine, owner.work) as connection:
            phase.verify(connection, cohort)
    assert owner._failed and engine.pool.checkedout() == 0


@pytest.mark.parametrize("change", ["created", "budget", "payload", "correlation"])
def test_immutable_association_survives_between_phases(cancellation, change):
    f, engine = cancellation
    owner = successful_phases(f, engine, 0, 1)
    with f.engine.begin() as connection:
        statements = {
            "created": "UPDATE jobs SET created=created+1 WHERE id=:id",
            "budget": "UPDATE jobs SET budget=budget+1 WHERE id=:id",
            "payload": "UPDATE jobs SET payload=:v WHERE id=:id",
            "correlation": "UPDATE operations SET failure_correlation_id=:v WHERE job_id=:id",
        }
        connection.execute(
            text(statements[change]),
            {"id": JOB, "v": "f" * (32 if change == "correlation" else 64)},
        )
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        association(f, phase, connection)
    assert owner._failed


@pytest.mark.parametrize(
    "entry",
    [
        "operation",
        "job",
        "state",
        "config",
        "result",
        "cohort_query",
        "cohort",
        "matching",
        "verify",
        "phase",
    ],
)
def test_retained_stale_book_rejected_before_sql_without_tainting_new_phase(cancellation, entry):
    f, engine = cancellation
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as old, operation_connection(engine, owner.work) as connection:
        cohort = capture(f, old, connection)
        book = old.book
        job = next(r for r in book.receipts if r.domain == "job")
        old.verify(connection, cohort)
    with owner.phase() as current, operation_connection(engine, owner.work) as connection:
        calls = []

        def listener(*_args):
            calls.append(1)

        event.listen(connection, "before_cursor_execute", listener)
        try:
            attempts = {
                "operation": lambda: read_operation(connection, f.context, OPERATION, book),
                "job": lambda: read_job(connection, f.context, JOB, book),
                "state": lambda: read_job_state(connection, f.context, JOB, book),
                "config": lambda: read_descriptor(
                    connection, f.context, JOB, "admission_config", book
                ),
                "result": lambda: observe_result(connection, f.context, JOB, book),
                "cohort_query": lambda: cohort_query(connection, f.context, JOB, book),
                "cohort": lambda: read_run_cohort(connection, f.context, job, book),
                "matching": lambda: matching_query(connection, f.context, book, cohort),
                "verify": lambda: verify_read_snapshot(connection, f.context, book, cohort),
                "phase": lambda: old.verify(connection, cohort),
            }
            with pytest.raises(AdmissionStorageError):
                attempts[entry]()
            assert calls == [] and not owner._failed
        finally:
            event.remove(connection, "before_cursor_execute", listener)
        current.verify(connection, capture(f, current, connection))
    assert engine.pool.checkedout() == 0


def test_nested_acquisition_sealed_book_and_unverified_exit(cancellation):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as phase:
        with pytest.raises(AdmissionStorageError), owner.phase():
            pytest.fail("nested phase entered")
        with operation_connection(engine, owner.work) as connection:
            cohort = capture(f, phase, connection)
            book = phase.book
            phase.verify(connection, cohort)
            with pytest.raises(AdmissionStorageError):
                read_operation(connection, f.context, OPERATION, book)
        assert not owner._failed
    with pytest.raises(AdmissionStorageError), owner.phase():
        pass
    assert owner._failed


@pytest.mark.parametrize("error", [RuntimeError("private"), KeyboardInterrupt("private")])
def test_phase_cleanup_preserves_primary_and_never_resets_work(cancellation, error):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with pytest.raises(type(error)) as caught, owner.phase() as phase:
        with operation_connection(engine, owner.work) as connection:
            capture(f, phase, connection)
        before = owner.work.statements
        raise error
    assert caught.value is error and owner._failed
    assert owner.work.statements == before and owner.source_visits == 1
    with pytest.raises(AdmissionStorageError), owner.phase():
        pytest.fail("failed owner reused")
    assert engine.pool.checkedout() == 0


def test_cohort_exact_raw_identity_not_just_ids(cancellation):
    f, engine = cancellation
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        cohort = capture(f, phase, connection)
        row = cohort.records[0]
        forged = replace(row, values=(*row.values[:-1], "{}"))
        before = owner.work.statements
        try:
            phase.verify(connection, replace(cohort, records=(forged,)))
        finally:
            assert owner.work.statements == before


def reserve_transfer(f, engine):
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with pytest.raises(AdmissionStorageError), owner.phase() as phase:
        with operation_connection(engine, owner.work) as connection:
            job = association(f, phase, connection)
            remaining = phase.book.remaining
        roots(f, 3, update={"padding": "x" * (remaining // 3)})
        with operation_connection(engine, owner.work) as connection:
            rows = connection.execute(cohort_query(connection, f.context, JOB, phase.book)).all()
            assert len(rows) == 3 and all(all(v is None for v in row) for row in rows)
            assert remaining < MAX_RECEIPT_BYTES - 500
            read_run_cohort(connection, f.context, job, phase.book)


def test_large_mutable_bytes_release_but_decode_and_work_counters_do_not_reset(cancellation):
    f, engine = cancellation
    roots(f, 1, update={"padding": "x" * 1500000})
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    retained = []
    attempts = []
    for _ in range(3):
        with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
            job = association(f, phase, connection)
            retained.append(phase.book.remaining)
            phase.verify(connection, read_run_cohort(connection, f.context, job, phase.book))
        attempts.append(owner.work.statements)
    assert retained[0] == retained[1] == retained[2]
    assert attempts == sorted(set(attempts)) and owner.source_visits == 6


def canonical_expansion(f, engine):
    roots(f, 2, update={"padding": "\x01" * 320000})
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        job = association(f, phase, connection)
        book = phase.book
        assert all(
            row.body is not None
            for row in connection.execute(cohort_query(connection, f.context, JOB, phase.book))
        )
        try:
            read_run_cohort(connection, f.context, job, phase.book)
        finally:
            # Only fully charged rows are retained when expansion refuses.
            assert (
                len(
                    receipt_bytes(
                        {
                            "original": _association_rows(phase._association),
                            "phase": book._payload(),
                        },
                        MAX_RECEIPT_BYTES,
                    )
                )
                <= MAX_RECEIPT_BYTES
            )
            assert book._wire_bytes == len(receipt_bytes(book._payload(), MAX_RECEIPT_BYTES))
            assert owner._failed
            with pytest.raises(AdmissionStorageError):
                _ = phase.book


def test_identity_union_and_wrapper_size_are_exact(cancellation):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        association(f, phase, connection)
        book = phase.book
        for i in range(256):
            book.remember("run", f"{i:032x}", ("id",), {"id": f"{i:032x}"})
        assert len(book.receipts) == 259
        retained = receipt_bytes(
            {"original": _association_rows(phase._association), "phase": book._payload()},
            MAX_RECEIPT_BYTES,
        )
        assert book.remaining == MAX_RECEIPT_BYTES - len(retained)
        with pytest.raises(AdmissionStorageError):
            book.remember("run", "f" * 32, ("id",), {"id": "f" * 32})
        assert len(book.receipts) == 259
        # This synthetic book cannot be verified against SQL; exit must fail.


def test_unassociated_cohort_and_cross_work_connection_refuse_before_sql(cancellation):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
        _, op = read_operation(connection, f.context, OPERATION, phase.book)
        job = read_job(connection, f.context, JOB, phase.book)
        _, config = read_descriptor(connection, f.context, JOB, "admission_config", phase.book)
        before = owner.work.statements
        with pytest.raises(AdmissionStorageError):
            read_run_cohort(connection, f.context, job, phase.book)
        with f.engine.connect() as foreign, pytest.raises(AdmissionStorageError):
            read_operation(foreign, f.context, OPERATION, phase.book)
        assert owner.work.statements == before
        phase.associate(op, job, config)
        phase.verify(connection, read_run_cohort(connection, f.context, job, phase.book))


@pytest.mark.parametrize("identity", ["project", "operation", "job", "result"])
def test_original_scope_and_ignored_result_reader_reject_before_sql(cancellation, identity):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
        before = owner.work.statements
        with pytest.raises(AdmissionStorageError):
            if identity == "project":
                read_operation(
                    connection, replace(f.context, project_id="f" * 32), OPERATION, phase.book
                )
            elif identity == "operation":
                read_operation(connection, f.context, "f" * 32, phase.book)
            elif identity == "job":
                read_job(connection, f.context, JOB, phase.book)
            else:
                observe_result(connection, f.context, JOB, phase.book)
        assert owner.work.statements == before
        phase.verify(connection, capture(f, phase, connection))


def test_phase_must_enclose_connection_cleanup(cancellation):
    f, engine = cancellation
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    # Starting after acquisition would omit the ownership/cleanup boundary.
    with (
        operation_connection(engine, owner.work),
        pytest.raises(AdmissionStorageError),
        owner.phase(),
    ):
        pytest.fail("phase entered after connection")
    with owner.phase() as phase, operation_connection(engine, owner.work) as connection:
        phase.verify(connection, capture(f, phase, connection))


def distractor_phases(f, engine):
    roots(f, 2000, start=1000, job="e" * 32)
    roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "foreign"})
    return successful_phases(f, engine, 84, 3)


def test_three_max_phases_with_nonmatching_scoped_and_foreign_scans(cancellation):
    distractor_phases(*cancellation)


def extra_config(f, engine):
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with pytest.raises(AdmissionStorageError), owner.phase() as phase:
        with operation_connection(engine, owner.work) as connection:
            cohort = capture(f, phase, connection)
        value = result_ref(f, "b" * 32, publish=False, object_id="000000000000000000000000000000ff")
        with f.engine.begin() as connection:
            register_ref(
                connection,
                project_id=PROJECT,
                owner_kind="job",
                owner_id=JOB,
                role="admission_config",
                artifact_id=value.id,
            )
        with operation_connection(engine, owner.work) as connection:
            phase.verify(connection, cohort)
    assert owner._failed


def test_extra_configuration_candidate_remains_fatal(cancellation):
    extra_config(*cancellation)


def transaction_outcomes(f, engine, monkeypatch, stage):
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    outcome = TransactionOutcome()
    if stage == "after_ack":
        finish = owner.work.finish

        def fail_after_close():
            finish()
            raise RuntimeError("private cleanup")

        monkeypatch.setattr(owner.work, "finish", fail_after_close)
    error = None
    try:
        with (
            owner.phase() as phase,
            admission_transaction(engine, outcome, work=owner.work) as conn,
        ):
            raw = conn.connection.driver_connection
            cohort = capture(f, phase, conn)
            phase.verify(conn, cohort)
            assert owner._active is phase and not outcome.commit_attempted
            if stage == "before_commit":
                raise AdmissionError("invalid_request")
    except AdmissionError as caught:
        error = caught
    assert owner._active is None and owner.work._started is None
    assert conn.closed
    if engine.dialect.name == "sqlite":
        assert engine.pool.checkedout() == 0
    else:
        assert raw.closed
    if stage == "success":
        assert error is None and outcome.commit_acknowledged and not owner._failed
    elif stage == "before_commit":
        assert error.code == "invalid_request" and outcome.confirmed_precommit_rollback
        assert owner._failed
    else:
        assert error.code == "outcome_uncertain" and outcome.commit_acknowledged
        assert outcome.cleanup_failed and owner._failed


def test_reservation_limits_sql_transfer_before_cohort(cancellation):
    reserve_transfer(*cancellation)


def test_canonical_expansion_is_charged_before_retention(cancellation):
    canonical_expansion(*cancellation)


@pytest.mark.parametrize("stage", ["success", "before_commit", "after_ack"])
def test_phase_encloses_transaction_outcome_without_reclassifying_it(
    cancellation, monkeypatch, stage
):
    transaction_outcomes(*cancellation, monkeypatch, stage)


def caught_active_failure(f, engine, kind):
    """Real malformed SQL rows cannot be repaired into success in one phase."""
    with f.engine.begin() as connection:
        if kind == "operation":
            original = connection.execute(
                text("SELECT retain_until FROM operations WHERE id=:id"), {"id": OPERATION}
            ).scalar_one()
            connection.execute(
                text("UPDATE operations SET retain_until=created_at WHERE id=:id"),
                {"id": OPERATION},
            )
            repair = text("UPDATE operations SET retain_until=:value WHERE id=:id")
            parameters = {"id": OPERATION, "value": original}
        elif kind in ("job", "job_bound"):
            field = "status" if kind == "job" else "error"
            statements = {
                "status": (
                    "SELECT status FROM jobs WHERE id=:id",
                    "UPDATE jobs SET status=:value WHERE id=:id",
                ),
                "error": (
                    "SELECT error FROM jobs WHERE id=:id",
                    "UPDATE jobs SET error=:value WHERE id=:id",
                ),
            }
            original = connection.execute(text(statements[field][0]), {"id": JOB}).scalar_one()
            repair = text(statements[field][1])
            connection.execute(
                repair, {"id": JOB, "value": "malformed" if kind == "job" else "x" * 1201}
            )
            parameters = {"id": JOB, "value": original}
        elif kind == "config":
            original = connection.execute(
                text(
                    "SELECT artifact_id FROM artifact_refs "
                    "WHERE owner_id=:id AND role='admission_config'"
                ),
                {"id": JOB},
            ).scalar_one()
            connection.execute(
                text("DELETE FROM artifact_refs WHERE owner_id=:id AND role='admission_config'"),
                {"id": JOB},
            )
        else:
            original = None
    if kind == "cohort":
        ids = roots(f, 1)
        with f.engine.begin() as connection:
            original = connection.execute(
                text("SELECT CAST(data AS TEXT) FROM records WHERE id=:id"), {"id": ids[0]}
            ).scalar_one()
            body = json.loads(original)
            body["parent_id"] = "f" * 32
            update = "UPDATE records SET data=CAST(:value AS JSON) WHERE id=:id"
            if connection.dialect.name == "sqlite":
                update = "UPDATE records SET data=:value WHERE id=:id"
            repair = text(update)
            connection.execute(repair, {"id": ids[0], "value": json.dumps(body)})
            parameters = {"id": ids[0], "value": original}
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    seen = []
    with pytest.raises(AdmissionStorageError), owner.phase() as phase:
        book = phase.book
        with (
            pytest.raises(AdmissionStorageError) as caught,
            operation_connection(engine, owner.work) as connection,
        ):
            try:
                capture(f, phase, connection)
            except AdmissionStorageError as error:
                seen.append(error)
                raise
        assert caught.value is seen[0]
        assert owner.work._started is None
        with f.engine.begin() as connection:
            if kind == "config":
                register_ref(
                    connection,
                    project_id=PROJECT,
                    owner_kind="job",
                    owner_id=JOB,
                    role="admission_config",
                    artifact_id=original,
                )
            else:
                connection.execute(repair, parameters)
        assert owner._failed
        # Retain the old book deliberately: property-only fencing is insufficient.
        with operation_connection(engine, owner.work) as connection:
            before = owner.work.statements
            calls = [
                lambda: read_operation(connection, f.context, OPERATION, book),
                lambda: read_job(connection, f.context, JOB, book),
                lambda: read_descriptor(connection, f.context, JOB, "admission_config", book),
                lambda: cohort_query(connection, f.context, JOB, book),
                lambda: phase.verify(connection, RunCohort(JOB, ())),
                lambda: owner.original,
                lambda: phase.book,
            ]
            for call in calls:
                with pytest.raises(AdmissionStorageError):
                    call()
            assert owner.work.statements == before
        with pytest.raises(AdmissionStorageError), owner.phase():
            pytest.fail("aborted owner started another phase")
    assert owner._failed and owner._active is None
    with pytest.raises(AdmissionStorageError), owner.phase():
        pytest.fail("aborted owner survived phase cleanup")


@pytest.mark.parametrize("kind", ["operation", "job", "job_bound", "config", "cohort"])
def test_caught_active_failure_cannot_repair_and_retry(cancellation, kind):
    caught_active_failure(*cancellation, kind)


@pytest.mark.parametrize("stage", ["operation", "job_retention", "cohort_retention"])
@pytest.mark.parametrize("interruption", [False, True])
def test_active_failure_preserves_exact_exception_and_get_stays_unscoped(
    cancellation, monkeypatch, stage, interruption
):
    import agent_rewind.operation_reads as reads

    f, engine = cancellation
    roots(f, 1)
    error = (
        KeyboardInterrupt("private")
        if interruption
        else AdmissionStorageError("admission_metadata_invalid")
    )
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with (
        pytest.raises(AdmissionStorageError),
        owner.phase() as phase,
        operation_connection(engine, owner.work) as connection,
    ):
        book = phase.book
        target = "operation_value" if stage == "operation" else "remember"
        obj = reads if stage == "operation" else book
        original = getattr(obj, target)

        def fail(*args, **kwargs):
            if stage == "operation" or args[0] == ("job" if stage == "job_retention" else "run"):
                raise error
            return original(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(obj, target, fail)
            with pytest.raises(type(error)) as caught:
                capture(f, phase, connection)
        assert caught.value is error and owner._failed
    # The same optional hook must be a no-op for a normal GET receipt book.
    with operation_connection(engine, OperationWork()) as connection:
        book = ReceiptBook()
        original = reads.operation_value
        with monkeypatch.context() as patch:
            patch.setattr(reads, "operation_value", lambda *_: (_ for _ in ()).throw(error))
            with pytest.raises(type(error)) as caught:
                read_operation(connection, f.context, OPERATION, book)
        assert caught.value is error
        assert reads.operation_value is original
        assert read_operation(connection, f.context, OPERATION, book)[0].id == OPERATION
