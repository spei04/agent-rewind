"""Actual same-intent PostgreSQL contention, scoped cleanup, and fresh replay."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import psycopg
import pytest
import test_ledger_recovery_postgres as recovery
import test_migrations_postgres as migration_tests
from ledger_competing_native import NativeCommandGroup
from ledger_competing_postgres_observer import (
    TIMEOUT,
    assert_same_backend,
    attest_backend,
    install_cleanup_guard,
    natural_exit,
)
from ledger_postgres_competing_fixture import TRY_LOCK_SQL
from ledger_provisioning_postgres_fixture import (
    assert_stage,
    encrypted_files,
    native_snapshot,
    progress_diagnostic,
)
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning
from agent_rewind.migrations.service import MIGRATOR_LOCK

__all__ = ["controlled_database_name", "observed_reader"]
pg, legacy = migration_tests.pg, recovery.legacy
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in actual PostgreSQL competing ledger operators"
)


def assert_trace(message):
    raw = message["raw_id"]
    observed = message["witness"]["observation"]
    events = observed["native_trace"]
    assert observed["faults"] == []
    assert len(observed["work"]) == len(observed["outcomes"]) == 1
    assert [row[2] for row in events if row[1] == "connect-return"] == [raw]
    assert sum(row[1] == "connect-call" for row in events) == 1
    assert sum(row[1] == "internal-connect" for row in events) == 1
    calls = [
        (phase, actual_raw, hashlib.sha256(sql.encode()).hexdigest())
        for phase, kind, actual_raw, sql in events
        if kind == "sql-call"
    ]
    receipts = observed["native_parameters"]
    assert calls == [(row["phase"], row["raw_id"], row["sql_sha256"]) for row in receipts]
    assert all(row["outcome"] == "return" and 0 <= row["parameter_count"] <= 16 for row in receipts)
    assert 0 < observed["work"][0]["ordinary"] <= 2028
    assert all(row[1] == raw for row in observed["markers"])
    return observed, events


def assert_try_lock(message, expected):
    witness = message["witness"]
    observed, events = assert_trace(message)
    assert len(witness["try_locks"]) == 1
    fetched = witness["try_locks"][0]
    assert type(fetched["fetched"]) is bool and fetched["fetched"] is expected
    assert fetched["raw_id"] == message["raw_id"]
    assert fetched["sql"] == TRY_LOCK_SQL and fetched["parameters"] == {"key": MIGRATOR_LOCK}
    assert type(fetched["parameters"]["key"]) is int
    assert type(fetched["backend_pid"]) is int and fetched["backend_pid"] > 0
    execute, fetch = fetched["execute_return_trace_index"], fetched["fetch_return_trace_index"]
    assert execute < fetch
    assert events[execute] == ["ordinary", "sql-return", message["raw_id"], TRY_LOCK_SQL]
    assert events[fetch] == ["ordinary", "try-lock-fetched", message["raw_id"], expected]
    if message["phase"] == "held":
        for key in ("backend_pid", "database", "role"):
            assert fetched[key] == witness[key]
    return observed, events


def assert_held(message, *, winner):
    observed, events = assert_try_lock(message, winner)
    witness, raw = message["witness"], message["raw_id"]
    outcome = observed["outcomes"][0]
    assert outcome["begin_attempted"] and outcome["begun"]
    assert outcome["commit_attempted"] is winner
    assert not any(
        outcome[key]
        for key in (
            "commit_acknowledged",
            "rollback_attempted",
            "rollback_acknowledged",
            "cleanup_failed",
        )
    )
    assert observed["command_boundary"] is None and observed["work"][0]["cleanup"] == []
    assert observed["physical"] == []
    assert not any(
        witness[key]
        for key in ("raw_closed", "connection_closed", "work_detached", "claim_released")
    )
    assert witness["transaction_status"] == int(psycopg.pq.TransactionStatus.INTRANS)
    assert not any(row[0] in {"cleanup", "harness-dispose"} for row in events)
    assert not any(row[1] in {"commit-call", "close-call"} for row in events)
    marker = observed["markers"]
    expected = "competition.before_physical_commit" if winner else "competition.false_try_lock"
    assert len(marker) == 1 and marker[0][:2] == [expected, raw]
    if not winner:
        assert witness["boundary"] == "fetched_false_try_lock_before_cleanup"
        assert witness["stages"] == [] and witness["receipt"] is None
        assert observed["xids"] == [] and observed["observer_units"] == []
        assert_refusal_statements(observed)
        assert witness["try_locks"][0]["fetch_return_trace_index"] < marker[0][2]
        return
    assert witness["boundary"] == "final_proof_before_physical_commit"
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
    assert len(constraints) == 1 and classified[1] <= constraints[0] < marker[0][2]
    assert observed["xids"] and {row[0] for row in observed["xids"]} == {raw}
    assert len({row[1] for row in observed["xids"]}) == 1


def assert_refusal_statements(observed):
    ordinary = [
        sql
        for phase, kind, _, sql in observed["native_trace"]
        if phase == "ordinary" and kind == "sql-call"
    ]
    assert len(ordinary) == 9 and observed["work"][0]["ordinary"] == 10
    for offset in (0, 3, 6):
        assert ordinary[offset].startswith("SET LOCAL statement_timeout = '")
        assert ordinary[offset + 1].startswith("SET LOCAL lock_timeout = '")
    assert ordinary[2::3] == [
        "SET LOCAL search_path TO public,pg_temp",
        "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",
        TRY_LOCK_SQL,
    ]


def assert_result(message, *, busy=False, replay=False):
    witness, raw = message["witness"], message["raw_id"]
    observed, events = assert_try_lock(message, not busy)
    outcome, boundary = observed["outcomes"][0], observed["command_boundary"]
    assert boundary["raw_id"] == raw and not boundary["engine_poisoned"]
    assert all(
        boundary[key]
        for key in ("raw_closed", "connection_closed", "claim_released", "claim_absent")
    )
    assert not outcome["cleanup_failed"]
    assert any(
        row["action"] == "close"
        and not row["closed_before"]
        and row["closed_after"]
        and row["trace_end"] <= boundary["trace_end"]
        for row in observed["physical"]
    )
    assert all(row[0] != "harness-dispose" for row in events[: boundary["trace_end"]])
    assert witness["scoped_cleanup"] == {
        "raw_ids": [raw],
        "closed": [True],
        "rescued_raw_ids": [],
        "errors": [],
        "engine_id": message["engine_id"],
    }
    commits = [row for row in observed["physical"] if row["action"] == "commit"]
    if busy:
        assert witness["refusal"] == {"type": "MigrationRefused", "code": "migration_busy"}
        assert witness["receipt"] is None
        assert witness["native_errors"] == [
            {
                "type": "MigrationRefused",
                "code": "migration_busy",
                "mapped_type": "MigrationRefused",
                "mapped_code": "migration_busy",
                "same_error": True,
            }
        ]
        assert outcome["begin_attempted"] and outcome["begun"]
        assert outcome["rollback_attempted"] and outcome["rollback_acknowledged"]
        assert not outcome["commit_attempted"] and not outcome["commit_acknowledged"]
        assert commits == [] and observed["xids"] == []
        assert_refusal_statements(observed)
    else:
        assert witness["refusal"] is None and witness["native_errors"] == []
        assert outcome["commit_attempted"] and outcome["commit_acknowledged"]
        assert not outcome["rollback_attempted"] and not outcome["rollback_acknowledged"]
        assert len(commits) == 1 and commits[0]["raw_id"] == raw
        assert commits[0]["status_before"] == int(psycopg.pq.TransactionStatus.INTRANS)
        assert commits[0]["status_after"] == int(psycopg.pq.TransactionStatus.IDLE)
        assert witness["receipt"]["outcome"] == "complete"
    if replay:
        assert observed["observer_units"] == [6, 3] and observed["tuple_deltas"] == [[]]


def prove_absence(before, target):
    def rows(name):
        table = before["tables"].get(name, {"columns": (), "rows": ()})
        return [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]

    assert "ledger_manifest_" + target["manifest_id"] not in {
        row["phase"] for row in rows("migration_progress")
    }
    accounts = rows("budget_accounts")
    requested_ids = {row["id"] for row in target["accounts"]}
    periods = {
        (
            row["organization_id"],
            row["scope"],
            row["scope_id"],
            datetime.fromisoformat(row["period_start"].replace("Z", "+00:00")),
        )
        for row in target["accounts"]
    }
    assert requested_ids.isdisjoint(row["id"] for row in accounts)
    assert periods.isdisjoint(
        (row["organization_id"], row["scope"], row["scope_id"], row["period_start"])
        for row in accounts
    )
    return {
        "manifest_phase_absent": True,
        "requested_ids_absent": sorted(requested_ids),
        "requested_periods_absent": sorted(periods),
    }


@pytest.mark.parametrize("operation", ["initialize", "provision"])
def test_identical_postgres_operators_refuse_then_replay(
    legacy, pg, tmp_path, record_property, operation
):
    def record(name, value):
        record_property(name, json.dumps(value, default=progress_diagnostic, allow_nan=False))

    target, manifests, receipts = recovery.pending(legacy, pg, record_property, operation)
    before, protected = native_snapshot(legacy.case, pg), encrypted_files(legacy)
    digest = hashlib.sha256(validate_ledger_manifest(target).canonical_bytes).hexdigest()
    record("intent_absence", prove_absence(before, target))
    record("exact_before", before)
    record("protected_ciphertexts", protected)
    record("intent", {"manifest": target, "sha256": digest})
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
    group = None
    with pg["control"].connect().execution_options(isolation_level="AUTOCOMMIT") as control:
        control.exec_driver_sql(TIMEOUT).close()
        group = NativeCommandGroup(tmp_path)
        install_cleanup_guard(pg["control"], group, record)
        worker = Path(__file__).with_name("ledger_postgres_competing_fixture.py")
        configuration = {
            "url": legacy.case.engine.url.render_as_string(hide_password=False),
            "manifest": target,
        }

        def spawn(role):
            return group.spawn(
                worker=worker,
                case=operation,
                role=role,
                intent_sha256=digest,
                configuration=configuration,
            )

        try:
            winner = spawn("winner")
            held = winner.receive()
            record("winner_held", held)
            assert_held(held, winner=True)
            first_backend = attest_backend(
                control, held, pg, group.work_deadline, winner=True, table_ids=table_ids
            )
            record("winner_backend", first_backend)
            loser = spawn("loser")
            attested = loser.receive()
            record("loser_false_try_lock", attested)
            assert_held(attested, winner=False)
            loser_backend = attest_backend(control, attested, pg, group.work_deadline, winner=False)
            record("loser_backend", loser_backend)
            assert loser_backend["activity"][0]["pid"] != first_backend["activity"][0]["pid"]
            loser.resume()
            refused = loser.receive()
            record("loser_result", refused)
            assert_result(refused, busy=True)
            assert refused["witness"]["try_locks"] == attested["witness"]["try_locks"]
            natural_exit(control, loser_backend, loser.record, group.work_deadline, record)
            assert winner.process.poll() is None
            still_held = winner.probe()
            record("winner_after_loser_cleanup", still_held)
            assert_held(still_held, winner=True)
            assert still_held["witness"] == held["witness"]
            current_backend = attest_backend(
                control, still_held, pg, group.work_deadline, winner=True, table_ids=table_ids
            )
            record("winner_backend_after_loser_cleanup", current_backend)
            assert_same_backend(first_backend, current_backend)
            winner.resume()
            completed = winner.receive()
            record("winner_result", completed)
            assert_result(completed)
            original = LedgerProvisioning(**completed["witness"]["receipt"])
            assert (
                original.model_dump(mode="json", exclude={"outcome"}) == held["witness"]["receipt"]
            )
            assert_stage(
                legacy,
                pg,
                [*manifests, target],
                [*receipts, original],
                record_property=record_property,
                observation="winner_committed",
            )
            after = native_snapshot(legacy.case, pg)
            assert encrypted_files(legacy) == protected == legacy.encrypted
            replay = spawn("replay")
            recovered = replay.receive()
            record("explicit_replay_result", recovered)
            assert_result(recovered, replay=True)
            assert recovered["witness"]["receipt"] == completed["witness"]["receipt"]
            assert len({child.process.pid for child in group.children}) == 3
            assert len(group.messages) == 12 and all(row["completed"] for row in group.messages)
            assert native_snapshot(legacy.case, pg) == after
            assert encrypted_files(legacy) == protected
            record("exact_after", after)
        except BaseException as error:
            record("first_failure", {"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            try:
                group.close()
            finally:
                record("command_group", group.record)
