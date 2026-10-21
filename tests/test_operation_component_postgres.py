"""Actual PostgreSQL proof for operation work/raw receipts, not the P1 service.

The existing disposable fixture owns each synthetic database/role. Read sessions
use a genuinely SELECT-only role; mutation/native read-only controls use the
nonsuperuser owner. No HTTP, cancellation, final compound proof or schema-ready
profile is introduced. pg_sleep is only a native timeout target, never a barrier.
"""

import traceback
from dataclasses import replace

import pytest
import test_admission_repository_postgres as repository_pg
import test_migrations_postgres as migrations
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DataError
from sqlalchemy.pool import QueuePool
from test_admission_envelope import descriptor
from test_admission_schema import JOB, OPERATION, PROJECT
from test_listing_session_postgres import clean_pool, error_codes, sessions

from agent_rewind import operation_reads, operation_work
from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.artifact_metadata import ArtifactError, record_verified, register_ref
from agent_rewind.operation_reads import ReceiptBook, read_descriptor, read_job, read_operation
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound

pg = migrations.pg
storage_pg = repository_pg.storage_pg
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL operation components"
)
__all__ = ["pg", "storage_pg", "sessions"]


def safe_error(caught, code):
    assert caught.value.code == code and str(caught.value) == code
    assert caught.value.__suppress_context__
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


def sample(engine):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT value FROM listing_sample WHERE id=1"
        ).scalar_one()


def test_postgres_exact_attempt_ledger_and_connection_local_cleanup(sessions):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    work = OperationWork()
    statements = []

    def observe(_connection, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with operation_connection(engine, work) as connection:
            assert work.statements == 5  # BEGIN + four setup SET statements.
            assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
            assert work.statements == 8  # Two raw setters and one logical SELECT.
        assert work.statements == 10  # Rollback + close.
        assert statements[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY"
        outcome = TransactionOutcome()
        with admission_transaction(engine, outcome, work=work) as connection:
            assert work.statements == 15
            connection.exec_driver_sql("UPDATE listing_sample SET value=20 WHERE id=1")
            assert work.statements == 18
        assert outcome.commit_acknowledged and work.statements == 22
        with operation_connection(engine, work) as connection:
            assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 20
        assert work.statements == 32 and work.instructions == 0
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert work._started is None and work._connection is None
    clean_pool(engine, same=raw)
    assert work.statements == 32  # No accounting listeners leaked into pool.


def test_postgres_select_only_role_and_real_read_committed_barrier(pg, sessions):
    engine = sessions["app"]
    work = OperationWork()
    with operation_connection(engine, work) as reader:
        assert reader.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'listing_sample','SELECT'),"
            "has_table_privilege(current_user,'listing_sample','UPDATE'),"
            "has_table_privilege(current_user,'listing_sample','INSERT'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, False, False, False)
        assert reader.exec_driver_sql(
            "SELECT current_setting('transaction_read_only'),"
            "current_setting('transaction_isolation')"
        ).one() == ("on", "read committed")
        assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
        transaction = reader.get_transaction()
        with pg["owner"].connect() as writer:
            writer.exec_driver_sql("UPDATE listing_sample SET value=20")
            assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
            writer.commit()
        assert reader.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 20
        assert reader.get_transaction() is transaction
    clean_pool(engine)


@pytest.mark.parametrize(
    "statement", ["INSERT INTO listing_sample VALUES(2,20)", "CREATE TABLE forbidden(id integer)"]
)
def test_postgres_read_only_refuses_normally_permitted_writes(sessions, statement):
    engine = sessions["owner"]
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'listing_sample','INSERT'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, True, True)
    with (
        error_codes(engine) as codes,
        pytest.raises(AdmissionError) as caught,
        operation_connection(engine, OperationWork()) as connection,
    ):
        connection.exec_driver_sql(statement)
    safe_error(caught, "dependency_unavailable")
    assert codes == ["25006"]  # Transaction refusal, not role privilege denial.
    clean_pool(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM listing_sample").scalar_one() == 1
        assert (
            connection.exec_driver_sql("SELECT to_regclass('public.forbidden')").scalar_one()
            is None
        )


def test_postgres_remaining_statement_timeout_is_native(sessions):
    engine = sessions["owner"]
    work = OperationWork()
    work.seconds = 9.5
    with (
        error_codes(engine) as codes,
        pytest.raises(AdmissionError) as caught,
        operation_connection(engine, work) as connection,
    ):
        connection.exec_driver_sql("SELECT pg_sleep(30)").one()
    safe_error(caught, "dependency_unavailable")
    assert codes == ["57014"]
    assert 0 < work.statements <= 512 and work._started is None
    clean_pool(engine)


def test_postgres_native_lock_timeout_and_failed_work_are_retained(pg, sessions):
    engine = sessions["app"]
    work = OperationWork()
    with pg["owner"].connect() as blocker:
        blocker.exec_driver_sql("LOCK TABLE listing_sample IN ACCESS EXCLUSIVE MODE")
        with (
            error_codes(engine) as codes,
            pytest.raises(AdmissionError) as caught,
            operation_connection(engine, work) as connection,
        ):
            connection.exec_driver_sql("SELECT value FROM listing_sample").one()
        blocker.rollback()
    safe_error(caught, "dependency_unavailable")
    assert codes == ["55P03"]
    assert work.statements == 10 and 0 < work.seconds < 10
    spent = work.seconds
    clean_pool(engine)
    with operation_connection(engine, work) as connection:
        assert connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one() == 10
    assert work.statements == 20 and work.seconds >= spent


def test_postgres_remaining_caps_and_submillisecond_refusal(sessions, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    engine = sessions["owner"]
    work = OperationWork()
    work.seconds = 9.5
    with operation_connection(engine, work) as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT setting::int FROM pg_settings WHERE name='statement_timeout'"
            ).scalar_one()
            == 500
        )
        clock[0] = 0.25
    assert work.seconds == 9.75
    clock[0] = 100
    with pytest.raises(AdmissionError) as caught, operation_connection(engine, work) as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT setting::int FROM pg_settings WHERE name='lock_timeout'"
            ).scalar_one()
            == 250
        )
        clock[0] = 100.2495
        # No zero/unlimited SET or logical query may run with less than 1ms.
        before = work.statements
        connection.exec_driver_sql("SELECT 1")
    safe_error(caught, "dependency_unavailable")
    assert work.statements == before + 2  # Mandatory rollback and close only.
    clean_pool(engine)


def test_postgres_statement_allowance_is_shared_across_reconnections(sessions):
    engine = sessions["owner"]
    work = OperationWork()
    work.statements = 490
    with operation_connection(engine, work) as connection:
        connection.exec_driver_sql("SELECT 1")
    assert work.statements == 500
    with pytest.raises(AdmissionError) as caught, operation_connection(engine, work):
        pytest.fail("setup exceeded retained ordinary allowance")
    safe_error(caught, "dependency_unavailable")
    assert 500 < work.statements <= 512 and work._started is None
    clean_pool(engine)


@pytest.mark.parametrize("stage", ["precommit", "after_ack", "disclosure"])
def test_postgres_deadline_distinguishes_rollback_ack_and_disclosure(sessions, monkeypatch, stage):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    engine = sessions["owner"]
    work = OperationWork()
    outcome = TransactionOutcome()
    commit = Connection.commit

    def late_ack(connection):
        commit(connection)
        if stage == "after_ack":
            clock[0] = 11.0

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", late_ack)
        if stage == "disclosure":
            with admission_transaction(engine, outcome, work=work) as connection:
                connection.exec_driver_sql("UPDATE listing_sample SET value=20")
            with (
                pytest.raises(AdmissionError) as caught,
                operation_connection(engine, work) as connection,
            ):
                assert (
                    connection.exec_driver_sql("SELECT value FROM listing_sample").scalar_one()
                    == 20
                )
                clock[0] = 11.0
            # This primitive reports read failure. The future service must map a
            # post-ACK disclosure failure to uncertainty; no service claim here.
            safe_error(caught, "dependency_unavailable")
        else:
            with (
                pytest.raises(AdmissionError) as caught,
                admission_transaction(engine, outcome, work=work) as connection,
            ):
                connection.exec_driver_sql("UPDATE listing_sample SET value=20")
                if stage == "precommit":
                    clock[0] = 11.0
            safe_error(
                caught, "dependency_unavailable" if stage == "precommit" else "outcome_uncertain"
            )
    assert outcome.commit_acknowledged is (stage != "precommit")
    assert outcome.confirmed_precommit_rollback is (stage == "precommit")
    assert sample(engine) == (10 if stage == "precommit" else 20)
    assert work._started is None
    clean_pool(engine)


@pytest.mark.parametrize("scope", ["read", "mutation"])
@pytest.mark.parametrize("stage", ["accounting", "rollback", "close"])
def test_postgres_cleanup_interruption_preserves_denial_and_releases(
    sessions, monkeypatch, scope, stage
):
    engine = sessions["owner"]
    raw = clean_pool(engine)
    work = OperationWork()
    outcome = TransactionOutcome()
    expected = ResourceNotFound()
    target, fired = [], []
    method = Connection.close if stage == "close" else Connection.rollback
    control = work.control_attempt

    def interrupted(connection):
        if target and connection is target[0] and not fired:
            fired.append(True)
            raise KeyboardInterrupt("PRIVATE-CLEANUP")
        return method(connection)

    def accounting(kind):
        if kind == "rollback" and not fired:
            fired.append(True)
            raise KeyboardInterrupt("PRIVATE-ACCOUNT")
        control(kind)

    with monkeypatch.context() as patch:
        if stage == "accounting":
            patch.setattr(work, "control_attempt", accounting)
        else:
            patch.setattr(Connection, stage, interrupted)
        manager = (
            operation_connection(engine, work)
            if scope == "read"
            else admission_transaction(engine, outcome, work=work)
        )
        with pytest.raises(ResourceNotFound) as caught, manager as connection:
            target.append(connection)
            if scope == "mutation":
                connection.exec_driver_sql("UPDATE listing_sample SET value=20")
            raise expected
    assert caught.value is expected and caught.value.__suppress_context__
    assert fired == [True] and work._started is None
    assert target[0].closed and engine.pool.checkedout() == 0
    assert sample(engine) == 10
    if scope == "mutation":
        assert outcome.cleanup_failed and not outcome.commit_attempted
        assert outcome.rollback_acknowledged is (stage != "rollback")
    clean_pool(engine, discarded=raw if stage != "accounting" or scope == "read" else None)


@pytest.fixture
def receipts(storage_pg):
    f = storage_pg
    f.operation = repository_pg.persist(f)
    with f.engine.begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {f.pg['app_role']}"
        )
    f.reader = create_engine(
        f.pg["app"].url, poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=2
    )
    try:
        yield f
    finally:
        f.reader.dispose()


def load(f, kind, connection, book):
    if kind == "operation":
        return read_operation(connection, f.context, OPERATION, book)[1]
    if kind == "job":
        return read_job(connection, f.context, JOB, book)
    return read_descriptor(connection, f.context, JOB, "admission_config", book)[1]


def test_postgres_original_receipts_with_select_only_noncreator_viewer(receipts):
    f = receipts
    viewer = VerifiedPrincipal("oidc:" + "d" * 64)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
            {"p": PROJECT, "id": viewer.principal_id},
        )
    context = f.authority.named(viewer, PROJECT).context
    book = ReceiptBook()
    with operation_connection(f.reader, OperationWork()) as connection:
        assert connection.exec_driver_sql(
            "SELECT rolsuper,has_table_privilege(current_user,'operations','UPDATE'),"
            "has_table_privilege(current_user,'jobs','INSERT'),"
            "has_schema_privilege(current_user,'public','CREATE') "
            "FROM pg_roles WHERE rolname=current_user"
        ).one() == (False, False, False, False)
        f.authority.check(connection, viewer, context, resource_kind="job", resource_id=JOB)
        value, operation = read_operation(connection, context, OPERATION, book)
        job = read_job(connection, context, JOB, book)
        config, receipt = read_descriptor(connection, context, JOB, "admission_config", book)
        assert value == f.operation and value.principal_id != viewer.principal_id
        assert (len(operation.fields), len(job.fields), len(receipt.fields)) == (14, 16, 8)
        assert type(job.row()["cancel"]) is bool
        assert job.row()["error"] is None and job.row()["result"] is None
        assert config == f.value.configuration_binding.descriptor
        assert type(receipt.row()["created_at"]) is str  # bounded before psycopg decoding
        assert book.receipts == (operation, job, receipt)
    assert f.reader.pool.checkedout() == 0


@pytest.mark.parametrize("kind", ["operation", "job", "config"])
def test_postgres_original_receipts_refuse_changed_raw_values(receipts, kind):
    f, book = receipts, ReceiptBook()
    with operation_connection(f.reader, OperationWork()) as connection:
        original = load(f, kind, connection, book)
    sql = {
        "operation": "UPDATE operations SET failure_correlation_id=repeat('c',32)",
        "job": "UPDATE jobs SET error='' WHERE id=:id",
        "config": (
            "UPDATE artifact_objects SET created_at=created_at+interval '1 second' WHERE id=:id"
        ),
    }[kind]
    with f.engine.begin() as connection:
        connection.execute(
            text(sql),
            {"id": f.value.configuration_binding.descriptor.id if kind == "config" else JOB},
        )
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        load(f, kind, connection, book)
    assert book.receipts == (original,)


@pytest.mark.parametrize("kind", ["operation", "job", "config"])
def test_postgres_remaining_byte_cap_applies_before_python_materialization(
    receipts, monkeypatch, kind
):
    f, book, observed = receipts, ReceiptBook(), []
    book.byte_count = 4 * 1024 * 1024 - 1
    execute = Connection.execute

    def observe(connection, statement, *args, **kwargs):
        result = execute(connection, statement, *args, **kwargs)
        if connection.engine is f.reader and getattr(statement, "is_select", False):
            rows = result.mappings().all()
            observed.extend(dict(row) for row in rows)

            class Rows:
                def mappings(self):
                    return self

                def all(self):
                    return rows

            return Rows()
        return result

    monkeypatch.setattr(Connection, "execute", observe)
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises((AdmissionStorageError, ArtifactError)),
    ):
        load(f, kind, connection, book)
    assert len(observed) == 1
    assert all(value is None for key, value in observed[0].items() if key != "reference_id")
    assert book.receipts == ()


@pytest.mark.parametrize("field", ["created_at", "retain_until", "descriptor"])
def test_postgres_infinity_is_fixed_refusal_before_driver_datetime_decode(
    receipts, monkeypatch, field
):
    f = receipts
    observed = []
    parser = operation_reads._object if field == "descriptor" else operation_reads.operation_value

    def observe(row):
        observed.append(dict(row))
        return parser(row)

    monkeypatch.setattr(
        operation_reads, "_object" if field == "descriptor" else "operation_value", observe
    )
    with f.engine.begin() as connection:
        if field == "descriptor":
            connection.execute(
                text("UPDATE artifact_objects SET created_at='infinity'::timestamptz WHERE id=:id"),
                {"id": f.value.configuration_binding.descriptor.id},
            )
        else:
            sql = (
                "UPDATE operations SET created_at='-infinity'::timestamptz"
                if field == "created_at"
                else "UPDATE operations SET retain_until='infinity'::timestamptz"
            )
            connection.exec_driver_sql(sql)
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises((AdmissionStorageError, ArtifactError)),
    ):
        load(f, "config" if field == "descriptor" else "operation", connection, ReceiptBook())
    assert len(observed) == 1
    assert observed[0]["created_at" if field == "descriptor" else field] in (
        "infinity",
        "-infinity",
    )


def test_postgres_malformed_timestamp_is_rejected_by_native_type_not_faked_fixture(receipts):
    f = receipts
    with pytest.raises(DataError) as caught, f.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE artifact_objects SET created_at='not-a-timestamp'")
    assert caught.value.orig.sqlstate == "22007"
    with operation_connection(f.reader, OperationWork()) as connection:
        value, _ = read_descriptor(connection, f.context, JOB, "admission_config", ReceiptBook())
    assert value == f.value.configuration_binding.descriptor


@pytest.mark.parametrize("change", ["missing", "second_invalid", "oversize"])
def test_postgres_descriptor_candidates_are_not_filtered_to_false_success(receipts, change):
    f = receipts
    with f.engine.begin() as connection:
        if change == "missing":
            connection.exec_driver_sql("DELETE FROM artifact_refs WHERE role='admission_config'")
        elif change == "second_invalid":
            other = descriptor(b"other", object_id="7" * 32, project=PROJECT)
            record_verified(connection, other)
            register_ref(
                connection,
                project_id=PROJECT,
                owner_kind="job",
                owner_id=JOB,
                role="admission_config",
                artifact_id=other.id,
            )
            connection.execute(
                text("UPDATE artifact_objects SET created_at='infinity'::timestamptz WHERE id=:id"),
                {"id": other.id},
            )
        else:
            connection.execute(
                text("UPDATE artifact_objects SET byte_count=65537 WHERE id=:id"),
                {"id": f.value.configuration_binding.descriptor.id},
            )
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises((AdmissionStorageError, ArtifactError)),
    ):
        read_descriptor(connection, f.context, JOB, "admission_config", ReceiptBook())


@pytest.mark.parametrize("kind", ["operation", "job"])
def test_postgres_foreign_or_absent_resource_never_returns_receipt(receipts, kind):
    f = receipts
    for context in (replace(f.context, project_id="f" * 32), f.context):
        book = ReceiptBook()
        with (
            operation_connection(f.reader, OperationWork()) as connection,
            pytest.raises(ResourceNotFound),
        ):
            if kind == "operation":
                read_operation(
                    connection, context, OPERATION if context != f.context else "f" * 32, book
                )
            else:
                read_job(connection, context, JOB if context != f.context else "f" * 32, book)
        assert book.receipts == ()


@pytest.mark.parametrize("after_commit", [False, True])
def test_postgres_lost_commit_ack_is_uncertain_with_actual_effect_or_rollback(
    sessions, monkeypatch, after_commit
):
    engine = sessions["owner"]
    work, outcome = OperationWork(), TransactionOutcome()
    commit = Connection.commit
    target = []

    def lost_ack(connection):
        if target and connection is target[0]:
            if after_commit:
                commit(connection)
            raise RuntimeError("PRIVATE-COMMIT-ACK")
        return commit(connection)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "commit", lost_ack)
        with (
            pytest.raises(AdmissionError) as caught,
            admission_transaction(engine, outcome, work=work) as connection,
        ):
            target.append(connection)
            connection.exec_driver_sql("UPDATE listing_sample SET value=20")
    safe_error(caught, "outcome_uncertain")
    assert outcome.commit_attempted and not outcome.commit_acknowledged
    assert not outcome.confirmed_precommit_rollback and outcome.rollback_acknowledged
    assert sample(engine) == (20 if after_commit else 10)
    assert work._started is None
    clean_pool(engine)


def test_postgres_one_millisecond_native_setters_are_not_zero_or_unlimited(sessions, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    engine = sessions["owner"]
    work = OperationWork()
    with operation_connection(engine, work) as connection:
        clock[0] = 9.9985
        assert work.remaining_timeouts_ms() == (1, 1)
        # Both native setters must be acknowledged by PostgreSQL. Inspect the
        # resulting GUCs on the same transaction; never substitute zero/unlimited.
        assert connection.exec_driver_sql(
            "SELECT current_setting('statement_timeout'),current_setting('lock_timeout')"
        ).one() == ("1ms", "1ms")
    clean_pool(engine)


@pytest.mark.parametrize("field,value", [("created", "Infinity"), ("lease_until", "NaN")])
def test_postgres_nonfinite_job_numbers_refuse_without_receipts(receipts, field, value):
    f, book = receipts, ReceiptBook()
    with f.engine.begin() as connection:
        connection.execute(
            text(f"UPDATE jobs SET {field}=CAST(:v AS double precision) WHERE id=:id"),
            {"v": value, "id": JOB},
        )
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        read_job(connection, f.context, JOB, book)
    assert book.receipts == ()


def test_postgres_exact_error_byte_boundary_is_retained_not_interpreted(receipts):
    f = receipts
    error = "😀" * 300  # Native VARCHAR(300), exactly 1200 encoded bytes.
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET error=:error WHERE id=:id"), {"error": error, "id": JOB}
        )
    with operation_connection(f.reader, OperationWork()) as connection:
        receipt = read_job(connection, f.context, JOB, ReceiptBook())
    assert receipt.row()["error"] == error and len(error.encode("utf-8")) == 1200
    # This proves only raw bounded preservation, not a supported Error envelope.


def test_postgres_multibyte_cell_bound_nulls_row_before_python_validation(receipts, monkeypatch):
    f, observed = receipts, []
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET actor=:actor WHERE id=:id"),
            {"actor": "😀" * 256, "id": JOB},
        )
    execute = Connection.execute

    def observe(connection, statement, *args, **kwargs):
        result = execute(connection, statement, *args, **kwargs)
        if connection.engine is f.reader and getattr(statement, "is_select", False):
            rows = result.mappings().all()
            observed.extend(dict(row) for row in rows)

            class Rows:
                def mappings(self):
                    return self

                def all(self):
                    return rows

            return Rows()
        return result

    monkeypatch.setattr(Connection, "execute", observe)
    with (
        operation_connection(f.reader, OperationWork()) as connection,
        pytest.raises(AdmissionStorageError, match="^admission_metadata_invalid$"),
    ):
        read_job(connection, f.context, JOB, ReceiptBook())
    assert len(observed) == 1 and all(value is None for value in observed[0].values())
