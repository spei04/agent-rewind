"""Actual PostgreSQL process death around COMMIT; no service retry or fixture seeding."""

import hashlib
import json
from pathlib import Path

import psycopg
import pytest
import test_ledger_recovery_postgres as recovery
import test_migrations_postgres as migration_tests
from ledger_process_fixture import HeldProcess
from ledger_process_postgres_observer import held_backend, natural_backend_exit
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    encrypted_files,
    native_snapshot,
    progress_diagnostic,
)
from ledger_recovery_postgres_fixture import fresh_reentry
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations.ledger_state import LedgerProvisioning

__all__ = ["controlled_database_name", "observed_reader"]
pg, legacy = migration_tests.pg, recovery.legacy
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in actual PostgreSQL ledger process death"
)


def assert_physical_barrier(marker):
    witness, raw = marker["witness"], marker["raw_id"]
    observation = witness["observation"]
    events = observation["native_trace"]
    assert observation["command_boundary"] is None and observation["faults"] == []
    assert len(observation["work"]) == len(observation["outcomes"]) == 1
    outcome = observation["outcomes"][0]
    assert outcome["begin_attempted"] and outcome["begun"] and outcome["commit_attempted"]
    assert not any(
        outcome[key]
        for key in (
            "commit_acknowledged",
            "rollback_attempted",
            "rollback_acknowledged",
            "cleanup_failed",
        )
    )
    assert observation["work"][0]["cleanup"] == []
    assert 0 < observation["work"][0]["ordinary"] <= 2028
    assert [row[2] for row in events if row[1] == "connect-return"] == [raw]
    assert sum(row[1] == "connect-call" for row in events) == 1
    assert sum(row[1] == "internal-connect" for row in events) == 1
    calls = [
        (stage, actual_raw, hashlib.sha256(sql.encode()).hexdigest())
        for stage, kind, actual_raw, sql in events
        if kind == "sql-call"
    ]
    receipts = observation["native_parameters"]
    assert calls == [(row["phase"], row["raw_id"], row["sql_sha256"]) for row in receipts]
    assert all(row["outcome"] == "return" and 0 <= row["parameter_count"] <= 16 for row in receipts)
    final, classified = witness["stages"]
    assert final[0] == "finalize.return" and classified[0] == "classify.return"
    inserted = [
        i
        for i, (_, kind, actual_raw, sql) in enumerate(events)
        if kind == "sql-return"
        and actual_raw == raw
        and sql.lstrip().startswith("INSERT INTO migration_progress")
    ]
    assert inserted and inserted[-1] < final[1] <= classified[1]
    constraints = [
        i
        for i, (_, kind, actual_raw, sql) in enumerate(events)
        if kind == "sql-return"
        and actual_raw == raw
        and sql.strip() == "SET CONSTRAINTS ALL IMMEDIATE"
    ]
    gate = observation["markers"][0]
    assert len(constraints) == 1 and classified[1] <= constraints[0] < gate[2]
    expected = (
        [
            "death.before_physical_commit",
            "commit.before_native",
            "commit.native_ack",
            "death.physical_commit_ack",
        ]
        if marker["phase"] == "after"
        else ["death.before_physical_commit"]
    )
    assert [row[0] for row in observation["markers"]] == expected
    assert all(row[1] == raw for row in observation["markers"])
    commits = [row for row in observation["physical"] if row["action"] == "commit"]
    assert len(commits) == int(marker["phase"] == "after")
    if commits:
        assert commits[0]["raw_id"] == raw
        assert commits[0]["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
        assert commits[0]["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)
        assert not commits[0]["closed_before"] and not commits[0]["closed_after"]
    assert [
        row[1] for row in events if row[1] in {"commit-call", "commit-return", "commit-raise"}
    ] == (["commit-call", "commit-return"] if commits else [])
    commands = [
        sql.strip()
        for stage, kind, actual_raw, sql in events
        if kind == "command" and stage != "bootstrap" and actual_raw == raw
    ]
    assert commands == (["BEGIN", "COMMIT"] if commits else ["BEGIN"])
    assert not any(row[0] in {"cleanup", "harness-dispose"} for row in events)
    assert not any(row[1] == "close-call" for row in events)
    for key in ("raw_closed", "connection_closed", "work_detached", "claim_released"):
        assert witness[key] is False
    assert witness["transaction_status"] == int(
        psycopg.pq.TransactionStatus.IDLE if commits else psycopg.pq.TransactionStatus.INTRANS
    )
    assert observation["xids"] and {row[0] for row in observation["xids"]} == {raw}
    assert len({row[1] for row in observation["xids"]}) == 1


@pytest.mark.parametrize("operation", ["initialize", "provision"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_postgres_actual_child_death_at_physical_commit(
    legacy, pg, tmp_path, monkeypatch, record_property, operation, phase
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    target, manifests, receipts = recovery.pending(legacy, pg, record_property, operation)
    before = native_snapshot(legacy.case, pg)
    protected = encrypted_files(legacy)
    record("exact_before", before)
    record("protected_ciphertexts", protected)
    with legacy.case.engine.connect() as connection:
        table_ids = dict(
            connection.exec_driver_sql(
                "SELECT c.relname,c.oid FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname"
            ).all()
        )
    assert set(table_ids) == set(before["tables"])
    record("predecessor_table_ids", table_ids)
    legacy.close()
    drain(pg)
    process = HeldProcess(
        tmp_path,
        worker=Path(__file__).with_name("ledger_postgres_process_fixture.py"),
        case=operation,
        phase=phase,
        configuration={
            "url": legacy.case.engine.url.render_as_string(hide_password=False),
            "control_url": pg["control"].url.render_as_string(hide_password=False),
            "manifest": target,
        },
    )
    try:
        marker = process.barrier()
        record("child_barrier", marker)
        # Control uses another database; it cannot become a target writer.
        held = held_backend(pg, marker, table_ids, record)
        lifecycle = process.kill_and_reap()
    finally:
        process.close()
        record("child_lifecycle", process.record)
    natural_backend_exit(pg, held, lifecycle, record)
    assert_physical_barrier(marker)
    # No administrative termination preceded this target-wide absence check.
    drain(pg)
    after = native_snapshot(legacy.case, pg)
    record("exact_after", after)
    if phase == "before":
        assert after == before
    else:
        original = LedgerProvisioning(**marker["witness"]["receipt"], outcome="complete")
        assert_stage(
            legacy,
            pg,
            [*manifests, target],
            [*receipts, original],
            record_property=record_property,
            observation="after_process_death",
        )
    assert encrypted_files(legacy) == protected == legacy.encrypted
    recovered, _ = fresh_reentry(legacy, pg, target, monkeypatch, record_property)
    if phase == "before":
        assert recovered is None
    else:
        assert recovered.model_dump(mode="json") == marker["witness"]["receipt"]
    assert native_snapshot(legacy.case, pg) == after
    assert encrypted_files(legacy) == protected
