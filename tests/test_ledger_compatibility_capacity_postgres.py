"""Four native seeded-reader capacity cases; execution requires a reviewed slot.

These use the real runtime wrapper, unlike the SQLite already-connected entry.
The count and trailing-padding maxima are separate, shape-specific fixtures.
"""

import hashlib
import json
import time
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime

import ledger_capacity_fixture as capacity
import pytest
import test_ledger_compatibility_postgres as native
from ledger_capacity_fixture import (
    CURSOR_LIMIT,
    assert_capacity_history,
    capacity_history,
    pad_cursor_bytes,
    strict_json_value,
)
from ledger_fixture import canonical_bytes, digest
from ledger_provisioning_postgres_fixture import native_snapshot
from ledger_reader_fixture import complete_postgres_ar6
from legacy_fixture import FIXTURE_ROOT, read_manifest
from sqlalchemy import text
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.ledger_history_sql import SQL as HISTORY_SQL
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, installed_profile

__all__ = ["controlled_database_name", "observed_reader"]
pg = native.pg
pytestmark = native.pytestmark


def strict_native_snapshot(case, pg):
    """Keep non-JSON native cells and exact JSON bytes as well as strict values."""
    snapshot = native_snapshot(case, pg)
    try:
        with case.engine.connect() as connection:
            quote = connection.dialect.identifier_preparer.quote_identifier
            for table, state in snapshot["tables"].items():
                json_columns = {
                    column[0]
                    for column in snapshot["catalog"][table]["columns"]
                    if column[1] == "JSON"
                }
                if not json_columns:
                    continue
                fields = [
                    f"CAST({quote(column)} AS TEXT)" if column in json_columns else quote(column)
                    for column in state["columns"]
                ]
                rows = []
                for raw in connection.exec_driver_sql(
                    f"SELECT {','.join(fields)} FROM {quote(table)}"
                ):
                    row = tuple(
                        (value, canonical_bytes(strict_json_value(value)))
                        if column in json_columns and value is not None
                        else value
                        for column, value in zip(state["columns"], raw, strict=True)
                    )
                    rows.append(row)
                state["rows"] = tuple(sorted(rows, key=repr))
        return snapshot
    finally:
        drain(pg)


def projection_observation(trace, receipts, transfers, statements, *, accounts, jobs, overflow):
    """Count ordered SQL executions independently from individual fetch observations."""
    bodies = {statement: name for statement, name in statements.items() if name.endswith("_body")}
    hashes = {
        hashlib.sha256(statement.encode()).hexdigest(): name for statement, name in bodies.items()
    }
    executions = [
        (raw_id, hashlib.sha256(statement.encode()).hexdigest(), bodies[statement])
        for phase, kind, raw_id, statement in trace
        if phase == "compatibility" and kind == "sql-call" and statement in bodies
    ]
    parameters = [
        (row["raw_id"], row["sql_sha256"])
        for row in receipts
        if row["phase"] == "compatibility" and row["sql_sha256"] in hashes
    ]
    assert [(raw_id, sql_hash) for raw_id, sql_hash, _ in executions] == parameters
    calls = Counter(name for _, _, name in executions)
    assert dict(calls) == (
        {} if overflow else {"pg_immutable_accounts_body": 1, "pg_original_jobs_body": 4}
    )
    fetches = [row for row in transfers if row["name"] in hashes.values()]
    assert all(
        row["method"] == "fetchone" and type(row["rows"]) is int and row["rows"] in (0, 1)
        for row in fetches
    )
    rows, exhausted = Counter(), Counter()
    for fetch in fetches:
        rows[fetch["name"]] += fetch["rows"]
        if fetch["rows"] == 0:
            exhausted[fetch["name"]] += 1
    assert dict(rows) == (
        {} if overflow else {"pg_immutable_accounts_body": accounts, "pg_original_jobs_body": jobs}
    )
    assert dict(exhausted) == dict(calls)
    return {
        "projection_body_calls": len(executions),
        "projection_body_calls_by_name": dict(calls),
        "projection_fetch_receipts": len(fetches),
        "projection_rows": dict(rows),
        "projection_zero_row_fetches": dict(exhausted),
    }


def observe_native_capacity(pg, monkeypatch, record_property, *, overflow, accounts, jobs):
    measurements = []

    def configure(local, probe):
        entry = guard.runtime_schema_compatibility
        inspection = guard._inspection
        counters = native._transaction_write_counters
        snapshots = []

        def timed(engine):
            started = time.monotonic()
            result = None
            try:
                result = entry(engine)
                return result
            finally:
                measurement = {
                    "entry": "runtime_schema_compatibility",
                    "runtime_wrapper_elapsed_seconds": time.monotonic() - started,
                    "inspection_timeout_seconds": guard.INSPECTION_TIMEOUT_SECONDS,
                    "result": None
                    if result is None
                    else {"status": result.status, "code": result.code},
                }
                measurements.append(measurement)
                record_property("native_capacity_timing", json.dumps(measurement))

        def observed_counters(connection):
            value = counters(connection)
            snapshots.append((id(connection.connection.driver_connection), value))
            return value

        @contextmanager
        def checked_inspection(connection, **kwargs):
            with inspection(connection, **kwargs) as checks:
                try:
                    yield checks
                except MigrationRefused:
                    # The existing observer's successful-yield counter path is
                    # skipped on refusal. Observe its same transaction before
                    # cleanup, using the same still-active deadline and caps.
                    assert snapshots and snapshots[0][0] == id(
                        connection.connection.driver_connection
                    )
                    phase = probe.trace.phase
                    probe.trace.phase = "oracle"
                    try:
                        checks.check()
                        last = counters(connection)
                        checks.check()
                        probe.counters = native._tuple_write_delta(snapshots[0][1], last)
                        assert probe.counters == {}
                    finally:
                        probe.trace.phase = phase
                    raise

        local.setattr(native, "_transaction_write_counters", observed_counters)
        local.setattr(guard, "_inspection", checked_inspection)
        local.setattr(guard, "runtime_schema_compatibility", timed)

    probe = native._observe(
        pg,
        monkeypatch,
        record_property,
        code="schema_incompatible" if overflow else "migration_only",
        configure=configure,
    )
    assert len(measurements) == 1 and measurements[0]["inspection_timeout_seconds"] == 2
    assert measurements[0]["runtime_wrapper_elapsed_seconds"] < 2
    assert probe.modes == ("on", "repeatable read") and probe.counters == {}
    assert all(row["outcome"] == "return" for row in probe.parameters.receipts)
    assert probe.raw.closed and not probe.invalidated
    events = [
        kind
        for phase, kind, raw_id, _ in probe.trace.events
        if phase == "cleanup" and raw_id == id(probe.raw)
    ]
    assert "rollback-call" in events and "rollback-return" in events
    assert not any(kind == "commit-call" for _, kind, _, _ in probe.trace.events)
    history_body = str(
        text(HISTORY_SQL[("all", "postgresql", "H60_ledger_progress_body")]).compile(
            dialect=pg["owner"].dialect
        )
    )
    history_bodies = probe.trace.sql("compatibility").count(history_body)
    projection = projection_observation(
        probe.trace.events,
        probe.parameters.receipts,
        probe.transfer.statement_hits,
        native._statements(pg["owner"]),
        accounts=accounts,
        jobs=jobs,
        overflow=overflow,
    )
    assert history_bodies == (0 if overflow else 1)
    projection_hashes = {
        hashlib.sha256(statement.encode()).hexdigest()
        for statement in native._statements(pg["owner"])
    }
    maximum_binds = max(
        (
            row["parameter_count"]
            for row in probe.parameters.receipts
            if row["sql_sha256"] in projection_hashes
        ),
        default=0,
    )
    assert maximum_binds <= 16
    record_property(
        "native_capacity_boundary",
        json.dumps(
            {
                "history_body_calls": history_bodies,
                **projection,
                "maximum_projection_binds": maximum_binds,
                "tuple_write_delta": probe.counters,
                "raw_closed": probe.raw.closed,
                "rollback_acknowledged": True,
            }
        ),
    )


@pytest.mark.parametrize("shape", ["control", "account-maximum", "cursor-limit", "cursor-over"])
def test_postgres_complete_capacity_and_cursor_gate(
    pg, observed_reader, monkeypatch, record_property, shape
):
    fixture_started = time.monotonic()
    case = complete_postgres_ar6(pg, legacy=True)
    try:
        expected = capacity_history(
            case,
            accounts=4096 if shape == "account-maximum" else 319,
            object_directory=FIXTURE_ROOT / "objects",
            database_role=pg["owner_role"],
        )
        assert expected["ciphertext"] == {
            spec["address"]: spec["ciphertext_sha256"]
            for spec in read_manifest()["objects"].values()
        }
        original = assert_capacity_history(case, expected)
        if shape in {"cursor-limit", "cursor-over"}:
            pad_cursor_bytes(case, total=CURSOR_LIMIT + (shape == "cursor-over"))
        witness = assert_capacity_history(case, expected)
        if shape in {"cursor-limit", "cursor-over"}:
            assert witness["cursor_bytes"] == CURSOR_LIMIT + (shape == "cursor-over")
            assert witness["canonical_cursor_bytes"] == original["canonical_cursor_bytes"]
            assert witness["canonical_cursors_sha256"] == original["canonical_cursors_sha256"]
        record_property("native_capacity_fixture", json.dumps({"shape": shape, **witness}))
        native._grant_runtime(pg)
        before = strict_native_snapshot(case, pg)
        assert before["catalog"] == installed_profile("postgresql", LEDGER)
        adoption = before["tables"]["installation_adoptions"]
        fingerprint = adoption["columns"].index("installed_schema_fingerprint")
        assert adoption["rows"][0][fingerprint] == digest(before["catalog"])
        record_property("native_capacity_fixture_seconds", time.monotonic() - fixture_started)
        observe_native_capacity(
            pg,
            monkeypatch,
            record_property,
            overflow=shape == "cursor-over",
            accounts=witness["accounts"],
            jobs=witness["opening_jobs"],
        )
        assert strict_native_snapshot(case, pg) == before
        assert assert_capacity_history(case, expected) == witness
        record_property(
            "native_capacity_preservation",
            json.dumps(
                {
                    "native_rows_unchanged": True,
                    "strict_json_values_and_bytes_unchanged": True,
                    "owner_acl_catalog_unchanged": True,
                    "ciphertexts_unchanged": True,
                }
            ),
        )
    finally:
        case.dispose()
        drain(pg)


def test_postgres_capacity_final_source_mismatch_preserves_acknowledged_prefix(
    pg, monkeypatch, record_property
):
    """Fixture-only source drift rolls back batch 255, without erasing 254 commits."""
    case = complete_postgres_ar6(pg, legacy=True)
    original_batches = capacity._capacity_batches
    original_insert = capacity._insert_provision
    snapshots = {}
    acknowledged = []
    writer_xids = []
    roles = []
    injected = {}

    def observed_batches(template, accounts):
        assert accounts == 319
        snapshots["initial"] = strict_native_snapshot(case, pg)
        snapshots["initial_python"] = deepcopy((case.manifest, case.cursor, case.expected))
        snapshots["ciphertext"] = capacity.object_hashes(case, directory=FIXTURE_ROOT / "objects")
        for sequence, rows in enumerate(original_batches(template, accounts), 1):
            assert len(rows) == 1
            if sequence == 255:
                assert len(acknowledged) == 254
                snapshots["prefix"] = strict_native_snapshot(case, pg)
                snapshots["prefix_python"] = deepcopy((case.manifest, case.cursor, case.expected))
            yield rows
            # Resumption occurs only after the preceding real transaction exits.
            assert case.cursor["sequence"] == sequence
            assert case.manifest == case.cursor["manifest"]
            assert case.expected["manifest_count"] == sequence + 1
            assert case.expected["account_count"] == 64 + sequence
            assert case.expected["head"]["manifest_digest"] == digest(case.manifest)
            assert case.manifest["parent_manifest_digest"] == (
                digest(acknowledged[-1][0])
                if acknowledged
                else digest(snapshots["initial_python"][0])
            )
            with case.engine.connect() as connection:
                stored = connection.execute(
                    text(
                        "SELECT CAST(cursor AS TEXT),source_digest,rows_verified,status "
                        "FROM migration_progress WHERE revision=:revision AND phase=:phase"
                    ),
                    {
                        "revision": LEDGER,
                        "phase": "ledger_manifest_" + case.manifest["manifest_id"],
                    },
                ).one()
                assert stored == (
                    canonical_bytes(case.cursor).decode(),
                    case.original_digest,
                    1,
                    "complete",
                )
                account = dict(
                    connection.execute(
                        text("SELECT * FROM budget_accounts WHERE id=:id"),
                        {"id": rows[0]["id"]},
                    )
                    .mappings()
                    .one()
                )
                for field, value in rows[0].items():
                    if field in {"period_start", "period_end"}:
                        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    assert account[field] == value
                assert (
                    account["held_microusd"],
                    account["accounted_microusd"],
                    account["opening_held_microusd"],
                ) == (0, 0, 0)
            acknowledged.append(deepcopy((case.manifest, case.cursor, case.expected)))

    def insert_then_change_source(connection, raw, cursor):
        sequence = cursor["sequence"]
        assert sequence == len(writer_xids) + 1
        xid, role = connection.exec_driver_sql("SELECT txid_current(),current_user").one()
        writer_xids.append(xid)
        roles.append(role)
        original_insert(connection, raw, cursor)
        if sequence == 255:
            job, actor = connection.exec_driver_sql(
                "SELECT id,actor FROM jobs ORDER BY id LIMIT 1"
            ).one()
            changed = "capacity-source-drift"
            assert actor != changed
            result = connection.execute(
                text("UPDATE jobs SET actor=:actor WHERE id=:job"),
                {"actor": changed, "job": job},
            )
            assert type(result.rowcount) is int and result.rowcount == 1
            assert (
                connection.execute(
                    text("SELECT actor FROM jobs WHERE id=:job"), {"job": job}
                ).scalar_one()
                == changed
            )
            changed_digest = source_digest(connection)
            assert changed_digest != case.original_digest
            injected.update(job=job, actor=actor, changed_digest=changed_digest, raw=deepcopy(raw))

    try:
        with monkeypatch.context() as local:
            local.setattr(capacity, "_capacity_batches", observed_batches)
            local.setattr(capacity, "_insert_provision", insert_then_change_source)
            with pytest.raises(AssertionError) as caught:
                capacity_history(
                    case,
                    accounts=319,
                    object_directory=FIXTURE_ROOT / "objects",
                    database_role=pg["owner_role"],
                )
        assert injected and len(writer_xids) == len(set(writer_xids)) == 255
        assert roles == [pg["owner_role"]] * 255
        traceback = caught.value.__traceback__
        assert traceback is not None
        while traceback.tb_next is not None:
            traceback = traceback.tb_next
        assert traceback.tb_frame.f_code is capacity._append_postgres_capacity.__code__
        assert traceback.tb_frame.f_locals["count"] == 255
        assert traceback.tb_frame.f_locals["source"] == case.original_digest
        assert len(acknowledged) == 254
        assert (case.manifest, case.cursor, case.expected) == snapshots["prefix_python"]
        assert snapshots["prefix_python"] == acknowledged[-1]
        assert case.expected["manifest_count"] == 255
        assert case.expected["account_count"] == 318
        prefix = snapshots["prefix"]
        initial = snapshots["initial"]
        assert prefix["catalog"] == initial["catalog"] == installed_profile("postgresql", LEDGER)
        assert prefix["authority"] == initial["authority"] and prefix["role"] == initial["role"]
        for name, state in initial["tables"].items():
            if name not in {"budget_accounts", "migration_progress"}:
                assert prefix["tables"][name] == state
            else:
                assert prefix["tables"][name]["columns"] == state["columns"]
                assert set(state["rows"]) <= set(prefix["tables"][name]["rows"])
        assert len(prefix["tables"]["budget_accounts"]["rows"]) == 318
        assert len(prefix["tables"]["migration_progress"]["rows"]) == (
            len(initial["tables"]["migration_progress"]["rows"]) + 254
        )
        assert strict_native_snapshot(case, pg) == prefix
        with case.engine.connect() as connection:
            assert source_digest(connection) == case.original_digest
            assert (
                connection.execute(
                    text("SELECT actor FROM jobs WHERE id=:job"), {"job": injected["job"]}
                ).scalar_one()
                == injected["actor"]
            )
            assert (
                connection.execute(
                    text("SELECT 1 FROM budget_accounts WHERE id=:id"),
                    {"id": injected["raw"]["accounts"][0]["id"]},
                ).first()
                is None
            )
            assert (
                connection.execute(
                    text(
                        "SELECT 1 FROM migration_progress WHERE revision=:revision AND phase=:phase"
                    ),
                    {
                        "revision": LEDGER,
                        "phase": "ledger_manifest_" + injected["raw"]["manifest_id"],
                    },
                ).first()
                is None
            )
        assert (
            capacity.object_hashes(case, directory=FIXTURE_ROOT / "objects")
            == snapshots["ciphertext"]
        )
        record_property(
            "native_capacity_source_failure",
            json.dumps(
                {
                    "provision_transactions": len(writer_xids),
                    "acknowledged_prefix": len(acknowledged),
                    "rolled_back_final_batch": True,
                    "python_prefix_preserved": True,
                    "full_native_prefix_preserved": True,
                    "source_restored": True,
                    "ciphertexts_preserved": True,
                }
            ),
        )
    finally:
        case.dispose()
        drain(pg)
