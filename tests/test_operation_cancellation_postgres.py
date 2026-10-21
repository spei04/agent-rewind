"""Actual SELECT-only PostgreSQL phase proofs; no cancellation effect or lock grant."""

import pytest
import test_migrations_postgres as migrations
from sqlalchemy import text
from test_admission_schema import JOB, OPERATION
from test_operation_cancellation import (
    association,
    canonical_expansion,
    capture,
    caught_active_failure,
    distractor_phases,
    extra_config,
    ignored_results,
    overflow_phases,
    progress,
    reserve_transfer,
    successful_phases,
    transaction_outcomes,
)
from test_operation_sources import roots
from test_operation_sources_postgres import pg, source_pg, storage_pg

from agent_rewind.admission_records import AdmissionStorageError
from agent_rewind.operation_cancellation import CancellationReceipts
from agent_rewind.operation_reads import read_operation
from agent_rewind.operation_work import OperationWork, operation_connection

__all__ = ["pg", "source_pg", "storage_pg"]
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL cancellation phases"
)


@pytest.mark.parametrize("count,phases", [(0, 3), (84, 3), (255, 1)])
def test_postgres_exact_phase_capacity_and_final_accounting(source_pg, count, phases):
    f = source_pg
    owner = successful_phases(f, f.pg["app"], count, phases)
    with operation_connection(f.pg["app"], owner.work) as connection:
        assert connection.exec_driver_sql(
            "SELECT has_table_privilege(current_user,'operations','UPDATE'),"
            "has_table_privilege(current_user,'jobs','UPDATE'),"
            "has_table_privilege(current_user,'artifact_refs','INSERT')"
        ).one() == (False, False, False)
    assert owner.work._started is None and owner.work.statements < 512


def test_postgres_three_85_root_phases_refuse_before_transfer(source_pg):
    overflow_phases(source_pg, source_pg.pg["app"])


def test_postgres_worker_progress_keeps_original_association(source_pg):
    progress(source_pg, source_pg.pg["app"])


def test_postgres_config_filter_precedes_limit_and_ignores_result_refs(source_pg):
    ignored_results(source_pg, source_pg.pg["app"])


@pytest.mark.parametrize("change", ["result", "created", "config_count", "phantom"])
def test_postgres_fresh_phase_or_original_association_refuses_drift(source_pg, change):
    f = source_pg
    roots(f, 1)
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    if change == "created":
        with owner.phase() as phase, operation_connection(f.pg["app"], owner.work) as connection:
            phase.verify(connection, capture(f, phase, connection))
    with pytest.raises(AdmissionStorageError), owner.phase() as phase:
        if change != "created":
            with operation_connection(f.pg["app"], owner.work) as connection:
                cohort = capture(f, phase, connection)
        if change == "phantom":
            roots(f, 1, start=2)
        else:
            with f.engine.begin() as connection:
                statements = {
                    "result": "UPDATE jobs SET result=:v WHERE id=:id",
                    "created": "UPDATE jobs SET created=created+1 WHERE id=:id",
                    "config_count": "DELETE FROM artifact_refs WHERE owner_id=:id "
                    "AND role='admission_config'",
                }
                connection.execute(text(statements[change]), {"id": JOB, "v": "e" * 64})
        with operation_connection(f.pg["app"], owner.work) as connection:
            if change == "created":
                association(f, phase, connection)
            else:
                phase.verify(connection, cohort)
    assert owner._failed and owner.work._started is None


def test_postgres_stale_and_nested_owner_have_zero_sql_and_no_lock_grant(source_pg):
    f = source_pg
    owner = CancellationReceipts(OperationWork(), f.context, OPERATION)
    with owner.phase() as old, operation_connection(f.pg["app"], owner.work) as connection:
        cohort = capture(f, old, connection)
        book = old.book
        old.verify(connection, cohort)
    with owner.phase() as current, operation_connection(f.pg["app"], owner.work) as connection:
        before = owner.work.statements
        with pytest.raises(AdmissionStorageError):
            read_operation(connection, f.context, OPERATION, book)
        with pytest.raises(AdmissionStorageError), owner.phase():
            pytest.fail("nested owner entered")
        assert owner.work.statements == before and not owner._failed
        current.verify(connection, capture(f, current, connection))


def test_postgres_three_phases_scan_nonmatching_scoped_and_foreign_rows(source_pg):
    distractor_phases(source_pg, source_pg.pg["app"])


def test_postgres_extra_config_candidate_refuses(source_pg):
    extra_config(source_pg, source_pg.pg["app"])


def test_postgres_live_reservation_blocks_transfer(source_pg):
    reserve_transfer(source_pg, source_pg.pg["app"])


def test_postgres_canonical_expansion_refuses(source_pg):
    canonical_expansion(source_pg, source_pg.pg["app"])


@pytest.mark.parametrize("stage", ["success", "before_commit", "after_ack"])
def test_postgres_phase_preserves_real_transaction_outcomes(source_pg, monkeypatch, stage):
    transaction_outcomes(source_pg, source_pg.pg["app"], monkeypatch, stage)


@pytest.mark.parametrize("kind", ["operation", "job", "config", "cohort"])
def test_postgres_caught_active_failure_cannot_repair_and_retry(source_pg, kind):
    caught_active_failure(source_pg, source_pg.pg["app"], kind)
