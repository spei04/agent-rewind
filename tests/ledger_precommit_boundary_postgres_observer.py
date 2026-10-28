"""Observe original PostgreSQL DDL/backfill returns before one typed interruption."""

import inspect
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy

import psycopg
from ledger_precommit_boundary_fixture import STAGES
from ledger_precommit_boundary_postgres_fixture import (
    ALL_PROBES,
    BACKFILL_SQL,
    REFLECTION_PARAMETERS,
    UPGRADE_HASHES,
    assert_native_span,
    assert_stage_rows,
    sql_hash,
)
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_physical_completion, native_identity

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.schema import MigrationRefused


@contextmanager
def observe_boundary(watch, fixture, stage, monkeypatch, record):
    assert stage in STAGES
    upgrade, write, execute = (
        ledger_service._upgrade,
        ledger_service._write,
        ledger_service._execute,
    )
    native_execute = psycopg.Cursor.execute
    caller = ledger_service.initialize_ledger.__code__
    first = MigrationRefused("migration_busy")
    receipt = {
        "stage": stage,
        "upgrades": [],
        "writes": [],
        "backfill_executions": [],
        "probes": [],
        "injections": [],
        "native_calls": [],
    }
    capturing = False

    def bound(connection):
        assert connection is watch.work._connection
        return native_identity(watch)

    def entry(connection):
        return {
            **bound(connection),
            "entered_at": len(watch.trace.events),
            "work_before": watch.work.observed_ordinary,
        }

    def returned(value):
        value.update(returned_at=len(watch.trace.events), work_after=watch.work.observed_ordinary)

    def inject(connection):
        receipt["identity"] = bound(connection)
        receipt["probe_start"] = len(watch.trace.events)
        before = watch.work.observed_ordinary
        for name, sql in ALL_PROBES:
            probe = {**entry(connection), "name": name, "sql": sql}
            receipt["probes"].append(probe)
            with connection.exec_driver_sql(sql) as result:
                probe["rows"] = [tuple(row) for row in result]
            returned(probe)
        receipt.update(
            probe_end=len(watch.trace.events), probe_work=watch.work.observed_ordinary - before
        )
        assert_stage_rows(receipt["probes"], fixture.jobs, stage)
        receipt["injections"].append(
            {
                **bound(connection),
                "position": len(watch.trace.events),
                "type": type(first).__name__,
                "code": first.code,
                "exception_id": id(first),
            }
        )
        # Timing belongs to this receipt. Do not change the shared native
        # rollback/physical-close/command-exit marker contract.
        raise first

    def upgrading(connection, manifest):
        nonlocal capturing
        frame = inspect.currentframe().f_back
        value = {
            **entry(connection),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "manifest": manifest.model_dump(mode="json"),
        }
        receipt["upgrades"].append(value)
        capturing = True
        result = upgrade(connection, manifest)
        returned(value)
        if stage == "after-ddl":
            inject(connection)
        return result

    def writing(connection, name, values):
        frame = inspect.currentframe().f_back
        value = {
            **entry(connection),
            "original_caller": frame.f_code is caller,
            "line": frame.f_lineno,
            "name": name,
            "values": deepcopy(values),
        }
        receipt["writes"].append(value)
        result = write(connection, name, values)
        returned(value)
        if stage == "first-backfill" and name == "jobs.backfill":
            assert len(receipt["writes"]) == 1
            inject(connection)
        return result

    def executing(connection, name, values=None):
        if name != "jobs.backfill":
            return execute(connection, name, values)
        value = {**entry(connection), "name": name, "values": deepcopy(values)}
        receipt["backfill_executions"].append(value)
        result = execute(connection, name, values)
        returned(value)
        value["rowcount"] = result.rowcount
        return result

    def native(cursor, query, *args, **kwargs):
        if not capturing or not watch.owns(cursor.connection):
            return native_execute(cursor, query, *args, **kwargs)
        parameters = args[0] if args else kwargs.get("params")
        value = {
            "entered_at": len(watch.trace.events),
            "phase": watch.trace.phase,
            "raw_id": id(cursor.connection),
            "sql": query.decode() if isinstance(query, bytes) else str(query),
            "parameter_type": type(parameters).__name__,
            "parameters": deepcopy(
                dict(parameters) if isinstance(parameters, Mapping) else parameters
            ),
            "outcome": "pending",
        }
        receipt["native_calls"].append(value)
        try:
            result = native_execute(cursor, query, *args, **kwargs)
        except BaseException:
            value.update(outcome="raise", returned_at=len(watch.trace.events))
            raise
        value.update(outcome="return", returned_at=len(watch.trace.events))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_upgrade", upgrading)
        patch.setattr(ledger_service, "_write", writing)
        patch.setattr(ledger_service, "_execute", executing)
        patch.setattr(psycopg.Cursor, "execute", native)
        try:
            yield receipt, first
        finally:
            record("boundary_receipt", receipt)


def assert_boundary(receipt, fixture, manifest, first, raised, watch):
    stage = receipt["stage"]
    assert stage in STAGES
    identity = native_identity(watch)
    assert typed(receipt["identity"]) == typed(identity)
    assert type(first) is MigrationRefused and raised is first and first.code == "migration_busy"
    (upgrade,) = receipt["upgrades"]
    assert upgrade["original_caller"] is True and type(upgrade["line"]) is int
    assert upgrade["line"] == 251
    assert typed(upgrade["manifest"]) == typed(manifest)
    spans = [upgrade]
    assert_native_span(
        upgrade,
        watch.trace.events,
        receipt["native_calls"],
        identity["raw_id"],
        watch.work.timeout_seconds,
        UPGRADE_HASHES,
        [REFLECTION_PARAMETERS, *({} for _ in UPGRADE_HASHES[1:])],
    )
    if stage == "after-ddl":
        assert receipt["writes"] == receipt["backfill_executions"] == []
        stage_end = upgrade["returned_at"]
    else:
        (write,) = receipt["writes"]
        (execution,) = receipt["backfill_executions"]
        values = {"id": fixture.jobs[0]["id"], "opening": fixture.jobs[0]["reserved"]}
        assert type(values["id"]) is str and type(values["opening"]) is int
        for value in (write, execution):
            assert value["name"] == "jobs.backfill" and typed(value["values"]) == typed(values)
        assert write["original_caller"] is True and type(write["line"]) is int
        assert write["line"] == 254
        assert type(execution["rowcount"]) is int and execution["rowcount"] == 1
        assert (
            upgrade["returned_at"]
            == write["entered_at"]
            == execution["entered_at"]
            < execution["returned_at"]
            == write["returned_at"]
        )
        assert execution["work_before"] == write["work_before"]
        assert execution["work_after"] == write["work_after"]
        assert_native_span(
            write,
            watch.trace.events,
            receipt["native_calls"],
            identity["raw_id"],
            watch.work.timeout_seconds,
            [sql_hash(BACKFILL_SQL)],
            [values],
        )
        spans.extend([write, execution])
        stage_end = write["returned_at"]
    assert type(receipt["probe_start"]) is int and stage_end == receipt["probe_start"]
    assert_stage_rows(receipt["probes"], fixture.jobs, stage)
    for probe in receipt["probes"]:
        assert probe["entered_at"] == stage_end
        assert_native_span(
            probe,
            watch.trace.events,
            receipt["native_calls"],
            identity["raw_id"],
            watch.work.timeout_seconds,
            [sql_hash(probe["sql"])],
            [{}],
        )
        stage_end = probe["returned_at"]
        spans.append(probe)
    assert type(receipt["probe_end"]) is int and receipt["probe_end"] == stage_end
    assert type(receipt["probe_work"]) is int and receipt["probe_work"] == 3 * len(ALL_PROBES)
    for value in spans:
        assert typed({key: value[key] for key in identity}) == typed(identity)
        assert all(
            type(value[key]) is int
            for key in ("entered_at", "returned_at", "work_before", "work_after")
        )
    (injection,) = receipt["injections"]
    assert typed(injection) == typed(
        {
            **identity,
            "position": stage_end,
            "type": "MigrationRefused",
            "code": "migration_busy",
            "exception_id": id(first),
        }
    )
    assert receipt["native_calls"][0]["entered_at"] == upgrade["entered_at"]
    assert receipt["native_calls"][-1]["returned_at"] == stage_end
    assert all(
        upgrade["entered_at"] <= row["entered_at"] < stage_end for row in receipt["native_calls"]
    )
    assert all(type(row[1]) is int and type(row[2]) is int for row in watch.markers)
    assert all(
        type(row["raw_id"]) is int and type(row["trace_end"]) is int for row in watch.physical
    )
    assert type(watch.command_boundary["trace_end"]) is int
    assert_physical_completion(watch, "rollback")
    assert injection["position"] <= watch.markers[0][2]
    assert not any(
        row[0] == "ordinary" and row[1] == "sql-call"
        for row in watch.trace.events[stage_end : watch.command_boundary["trace_end"]]
    )
