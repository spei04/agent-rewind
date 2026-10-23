"""Delegate real DDL/backfill, observe their native completion, then inject one fault."""

import inspect
import sqlite3
from contextlib import contextmanager
from copy import deepcopy

from ledger_precommit_boundary_fixture import (
    PROBES,
    STAGES,
    assert_probe_rows,
    assert_target,
    assert_upgrade_stage,
    returned_sql,
)

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.schema import MigrationRefused


def identity(watch):
    work = watch.work
    assert work._connection.engine is watch.engine
    assert work._raw is watch.trace.raws[0]
    return {
        "raw_id": id(work._raw),
        "work_id": id(work),
        "engine_id": id(watch.engine),
        "connection_id": id(work._connection),
    }


@contextmanager
def observe_boundary(watch, fixture, stage, monkeypatch, record):
    assert stage in STAGES
    upgrade, write, execute = (
        ledger_service._upgrade,
        ledger_service._write,
        ledger_service._execute,
    )
    caller = ledger_service.initialize_ledger.__code__
    first = MigrationRefused("migration_busy")
    receipt = {
        "stage": stage,
        "upgrades": [],
        "writes": [],
        "backfill_executions": [],
        "probes": [],
        "injections": [],
    }

    def bound(connection):
        result = identity(watch)
        assert connection is watch.work._connection
        return result

    def inject(connection):
        receipt["identity"] = bound(connection)
        receipt["probe_start"] = len(watch.trace.events)
        start = watch.work.observed_ordinary
        for name, sql in PROBES:
            entry = {
                **bound(connection),
                "name": name,
                "sql": sql,
                "entered_at": len(watch.trace.events),
            }
            receipt["probes"].append(entry)
            with connection.exec_driver_sql(sql) as result:
                entry["rows"] = [tuple(row) for row in result]
            entry["returned_at"] = len(watch.trace.events)
        receipt["probe_end"] = len(watch.trace.events)
        receipt["probe_work"] = watch.work.observed_ordinary - start
        assert_probe_rows(receipt["probes"], fixture.jobs, stage)
        receipt["injections"].append(
            {
                **bound(connection),
                "position": len(watch.trace.events),
                "type": type(first).__name__,
                "code": first.code,
                "exception_id": id(first),
            }
        )
        watch.mark("boundary.inject", watch.work._raw)
        raise first

    def upgrading(connection, manifest):
        frame = inspect.currentframe().f_back
        entry = {
            **bound(connection),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "manifest": manifest.model_dump(mode="json"),
            "entered_at": len(watch.trace.events),
            "authorizer_start": len(watch.actions),
        }
        receipt["upgrades"].append(entry)
        result = upgrade(connection, manifest)
        entry["returned_at"] = len(watch.trace.events)
        entry["authorizer_end"] = len(watch.actions)
        assert_upgrade_stage(
            watch.trace.events[entry["entered_at"] : entry["returned_at"]],
            watch.actions[entry["authorizer_start"] : entry["authorizer_end"]],
            entry["raw_id"],
        )
        if stage == "after-ddl":
            inject(connection)
        return result

    def writing(connection, name, values):
        frame = inspect.currentframe().f_back
        entry = {
            **bound(connection),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "name": name,
            "values": deepcopy(values),
            "entered_at": len(watch.trace.events),
            "authorizer_start": len(watch.actions),
        }
        receipt["writes"].append(entry)
        result = write(connection, name, values)
        entry["returned_at"] = len(watch.trace.events)
        entry["authorizer_end"] = len(watch.actions)
        if stage == "first-backfill" and name == "jobs.backfill":
            assert len(receipt["writes"]) == 1
            inject(connection)
        return result

    def executing(connection, name, values=None):
        if name != "jobs.backfill":
            return execute(connection, name, values)
        entry = {
            **bound(connection),
            "name": name,
            "values": deepcopy(values),
            "entered_at": len(watch.trace.events),
        }
        receipt["backfill_executions"].append(entry)
        result = execute(connection, name, values)
        entry.update(rowcount=result.rowcount, returned_at=len(watch.trace.events))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_upgrade", upgrading)
        patch.setattr(ledger_service, "_write", writing)
        patch.setattr(ledger_service, "_execute", executing)
        try:
            yield receipt, first
        finally:
            record("boundary_receipt", receipt)


def assert_boundary(receipt, fixture, manifest, first, raised, watch):
    stage = receipt["stage"]
    expected_identity = identity(watch)
    assert receipt["identity"] == expected_identity
    assert type(first) is MigrationRefused and raised is first and first.code == "migration_busy"
    (upgrade,) = receipt["upgrades"]
    assert {key: upgrade[key] for key in expected_identity} == expected_identity
    assert upgrade["original_caller"] is True and upgrade["line"] == 251
    assert upgrade["manifest"] == manifest
    assert_upgrade_stage(
        watch.trace.events[upgrade["entered_at"] : upgrade["returned_at"]],
        watch.actions[upgrade["authorizer_start"] : upgrade["authorizer_end"]],
        expected_identity["raw_id"],
    )
    if stage == "after-ddl":
        assert receipt["writes"] == receipt["backfill_executions"] == []
        stage_end = upgrade["returned_at"]
    else:
        assert stage == "first-backfill"
        (write,) = receipt["writes"]
        (execution,) = receipt["backfill_executions"]
        values = {"id": fixture.jobs[0]["id"], "opening": fixture.jobs[0]["reserved"]}
        assert type(values["opening"]) is int and values["opening"] == 125000
        for entry in (write, execution):
            assert {key: entry[key] for key in expected_identity} == expected_identity
            assert entry["name"] == "jobs.backfill" and entry["values"] == values
        assert write["original_caller"] is True and write["line"] == 254
        assert type(execution["rowcount"]) is int and execution["rowcount"] == 1
        assert (
            upgrade["returned_at"]
            <= write["entered_at"]
            <= execution["entered_at"]
            < execution["returned_at"]
            <= write["returned_at"]
        )
        assert_target(
            watch.trace.events[write["entered_at"] : write["returned_at"]],
            expected_identity["raw_id"],
            "UPDATE jobs SET legacy_reserved_microusd=125000, lease_generation=0 "
            f"WHERE id='{values['id']}'",
            watch.work.timeout_seconds,
        )
        actions = watch.actions[write["authorizer_start"] : write["authorizer_end"]]
        assert [
            (first, second)
            for action, first, second, _, _ in actions
            if action == sqlite3.SQLITE_UPDATE
        ] == [("jobs", "legacy_reserved_microusd"), ("jobs", "lease_generation")]
        assert all(trigger is None for _, _, _, _, trigger in actions)
        stage_end = write["returned_at"]
    assert_probe_rows(receipt["probes"], fixture.jobs, stage)
    assert stage_end == receipt["probe_start"] < receipt["probe_end"]
    assert receipt["probe_work"] == 2 * len(PROBES)
    for probe in receipt["probes"]:
        assert {key: probe[key] for key in expected_identity} == expected_identity
        assert_target(
            watch.trace.events[probe["entered_at"] : probe["returned_at"]],
            expected_identity["raw_id"],
            probe["sql"],
            watch.work.timeout_seconds,
        )
    (injection,) = receipt["injections"]
    assert injection == {
        **expected_identity,
        "position": receipt["probe_end"],
        "type": "MigrationRefused",
        "code": "migration_busy",
        "exception_id": id(first),
    }
    tail = watch.trace.events[injection["position"] : watch.command_boundary["trace_end"]]
    statements = [row[3].strip() for row in tail if row[0] == "sql"]
    assert type(watch.work.previous_timeout) is int and watch.work.previous_timeout >= 0
    assert statements == ["ROLLBACK", f"PRAGMA busy_timeout={watch.work.previous_timeout}"]
    assert_rollback(watch, injection["position"])


def assert_rollback(watch, injection_position):
    watch.assert_single_attempt()
    assert watch.outcome.confirmed_precommit_rollback
    assert watch.outcome.rollback_attempted and watch.outcome.rollback_acknowledged
    assert not watch.outcome.commit_attempted and not watch.outcome.commit_acknowledged
    assert not watch.outcome.cleanup_failed and watch.faults == []
    names = [
        "boundary.inject",
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    selected = [row for row in watch.markers if row[0] in names]
    assert [row[0] for row in selected] == names
    assert all(row[1] == id(watch.work._raw) for row in selected)
    assert [row[2] for row in selected] == sorted(row[2] for row in selected)
    assert selected[0][2] == injection_position
    assert "commit.before_native" not in [row[0] for row in watch.markers]
    boundary = watch.command_boundary
    assert not boundary["raw_closed"] and boundary["in_transaction"] is False
    assert boundary["receipt_clean"] and boundary["receipt_completed"]
    assert boundary["checkedout"] == 0
    sql = watch.trace.sql()
    assert sql.count("BEGIN EXCLUSIVE") == sql.count("ROLLBACK") == 1
    assert "COMMIT" not in sql
    rollback = watch.trace.events[selected[1][2] : selected[2][2]]
    assert returned_sql(rollback, id(watch.work._raw)) == ["ROLLBACK"]
