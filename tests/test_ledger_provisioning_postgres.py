"""Authored PostgreSQL provisioning oracles; native execution requires a reviewed slot."""

import json
from contextlib import contextmanager

import pytest
import test_migrations_postgres as migration_tests
from ledger_provisioning_fixture import digest, initial_manifest, next_manifest
from ledger_provisioning_postgres_fixture import (
    assert_append_only,
    assert_stage,
    build_postgres_case,
    inspect,
    invoke,
    native_snapshot,
)
from ledger_service_fixture import invoke_postgres
from test_ledger_reader_native import (
    _assert_reviewed_ctes,
    _transaction_write_counters,
    _tuple_write_delta,
)
from test_ledger_service_postgres import controlled_database_name, observe_service
from test_run_projection_postgres import observed_reader

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["controlled_database_name", "observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in independent PostgreSQL ledger provisioning"
)


@pytest.fixture
def legacy(pg, observed_reader):
    fixture = build_postgres_case(pg)
    try:
        yield fixture
    finally:
        fixture.close()


@contextmanager
def observe_no_writes(monkeypatch, record_property, *, injected_update=None):
    counters, units = [], []
    delegate = ledger_service.ledger_transaction

    @contextmanager
    def transaction(engine, outcome, *, work):
        with delegate(engine, outcome, work=work) as connection:
            start = work.observed_ordinary
            assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
            first = _transaction_write_counters(connection)
            units.append(work.observed_ordinary - start)
            if injected_update is not None:
                # Only negative controls execute this explicit test-owned statement.
                connection.exec_driver_sql(injected_update)
            try:
                yield connection
            finally:
                start = work.observed_ordinary
                last = _transaction_write_counters(connection)
                units.append(work.observed_ordinary - start)
                counters.append(_tuple_write_delta(first, last))

    with observe_service(monkeypatch, record_property) as watch, monkeypatch.context() as patch:
        patch.setattr(ledger_service, "ledger_transaction", transaction)
        try:
            yield watch, counters, units
        finally:
            record_property("provisioning_tuple_deltas", repr(counters))
            record_property("provisioning_observer_units", json.dumps(units))


def assert_no_writes(watch, counters, units, *, committed):
    metrics = watch.verify(committed=[committed])
    assert units == [6, 3]
    assert counters == [{}], "native tuple writes observed"
    raw = watch.works[0]._raw
    commands = [
        sql
        for phase, kind, raw_id, sql in watch.trace.events
        if phase == "ordinary" and kind == "sql-call" and raw_id == id(raw)
    ]
    _assert_reviewed_ctes(commands)
    assert commands and all(
        sql.lstrip().upper().startswith(("SELECT", "WITH", "SET", "SHOW", "LOCK"))
        for sql in commands
    ), "native write-capable statement observed"
    return metrics


def test_postgres_real_s0_m0_s1_m1_s2_and_older_replay(legacy, pg, monkeypatch, record_property):
    assert inspect(legacy, pg).status == "absent"
    first = initial_manifest(legacy)
    with observe_service(monkeypatch, record_property) as watch:
        original = invoke(legacy, pg, first)
        record_property("initial_work", json.dumps(watch.verify(committed=[True])))
    assert_stage(
        legacy, pg, [first], [original], record_property=record_property, observation="initialized"
    )
    s1 = native_snapshot(legacy.case, pg)

    later = next_manifest(first)
    assert later["parent_manifest_digest"] == digest(first)
    with observe_service(monkeypatch, record_property) as watch:
        second = invoke(legacy, pg, later)
        record_property("provision_work", json.dumps(watch.verify(committed=[True])))
    assert_stage(
        legacy,
        pg,
        [first, later],
        [original, second],
        record_property=record_property,
        observation="provisioned",
    )
    s2 = native_snapshot(legacy.case, pg)
    assert {key: value for key, value in s2.items() if key != "tables"} == {
        key: value for key, value in s1.items() if key != "tables"
    }
    for table, before in s1["tables"].items():
        if table not in {"budget_accounts", "migration_progress"}:
            assert s2["tables"][table] == before, table
    assert_append_only(s1["tables"]["budget_accounts"], s2["tables"]["budget_accounts"], ("id",))
    assert_append_only(
        s1["tables"]["migration_progress"],
        s2["tables"]["migration_progress"],
        ("revision", "phase"),
    )
    assert len(s2["tables"]["budget_accounts"]["rows"]) == 7
    assert len(s2["tables"]["migration_progress"]["rows"]) == (
        len(s1["tables"]["migration_progress"]["rows"]) + 1
    )

    def forbidden(*args, **kwargs):
        pytest.fail("known replay entered new-intent work")

    with monkeypatch.context() as patch:
        for name in ("source_digest", "_provenance", "_prepare_ledger"):
            patch.setattr(ledger_service, name, forbidden)
        with observe_no_writes(patch, record_property) as (watch, counters, units):
            replay = invoke_postgres(legacy.case, pg, validate_ledger_manifest(first))
            assert replay == original
            record_property(
                "replay_work", json.dumps(assert_no_writes(watch, counters, units, committed=True))
            )
    assert native_snapshot(legacy.case, pg) == s2
    assert inspect(legacy, pg).head.manifest_digest == second.manifest_digest


def test_postgres_real_empty_initialize_exact_zero_opening(
    pg, observed_reader, monkeypatch, record_property
):
    fixture = build_postgres_case(pg, legacy=False)
    try:
        manifest = initial_manifest(fixture, empty=True)
        with observe_service(monkeypatch, record_property) as watch:
            receipt = invoke(fixture, pg, manifest)
            record_property("initial_work", json.dumps(watch.verify(committed=[True])))
        assert_stage(
            fixture,
            pg,
            [manifest],
            [receipt],
            record_property=record_property,
            observation="initialized",
        )
        assert (receipt.account_rows, receipt.imported_jobs, receipt.imported_opening_microusd) == (
            0,
            0,
            0,
        )
    finally:
        fixture.close()


@pytest.mark.parametrize("scope", ["organization", "project"])
@pytest.mark.parametrize("stage", ["initialize", "provision"])
def test_postgres_exact_244999_cap_refuses_245000_without_writes(
    legacy, pg, monkeypatch, record_property, scope, stage
):
    first = initial_manifest(legacy)
    manifest = first
    original = None
    if stage == "provision":
        original = invoke(legacy, pg, first)
        assert_stage(
            legacy,
            pg,
            [first],
            [original],
            record_property=record_property,
            observation="initialized",
        )
        manifest = next_manifest(first)
    else:
        assert inspect(legacy, pg).status == "absent"
    assert sum(job["reserved"] for job in legacy.jobs) == 245000
    next(row for row in manifest["accounts"] if row["scope"] == scope)["limit_microusd"] = 244999
    validate_ledger_manifest(manifest)
    before = native_snapshot(legacy.case, pg)
    with observe_no_writes(monkeypatch, record_property) as (watch, counters, units):
        with pytest.raises(MigrationRefused, match="^ledger_exposure_refused$"):
            invoke(legacy, pg, manifest)
        record_property(
            "refusal_work", json.dumps(assert_no_writes(watch, counters, units, committed=False))
        )
    assert native_snapshot(legacy.case, pg) == before
    if original is not None:
        assert_stage(
            legacy,
            pg,
            [first],
            [original],
            record_property=record_property,
            observation="after_refusal",
        )


@pytest.mark.parametrize("predicate", ["true", "false"])
def test_postgres_actual_replay_write_observer_rejects_same_value_and_zero_row_dml(
    legacy, pg, monkeypatch, record_property, predicate
):
    first = initial_manifest(legacy)
    original = invoke(legacy, pg, first)
    before = native_snapshot(legacy.case, pg)
    statement = "UPDATE api_keys SET name=name WHERE " + predicate
    with observe_no_writes(monkeypatch, record_property, injected_update=statement) as (
        watch,
        counters,
        units,
    ):
        replay = invoke_postgres(legacy.case, pg, validate_ledger_manifest(first))
        assert replay == original
        expected = (
            "native tuple writes observed"
            if predicate == "true"
            else ("native write-capable statement observed")
        )
        with pytest.raises(AssertionError, match=expected):
            assert_no_writes(watch, counters, units, committed=True)
    assert native_snapshot(legacy.case, pg) == before
