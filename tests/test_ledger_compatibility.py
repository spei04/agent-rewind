"""Complete seeded-history compatibility tests, separate from writer integration."""

import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_reader_fixture import (
    append_provision,
    complete_ar6,
    cursor_for,
    identifier,
    later_admitted_call,
    seed_ar7,
    sqlite_snapshot,
)
from sqlalchemy import event, text

from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations import ledger_compatibility as adapter
from agent_rewind.migrations.ledger_compatibility_sql import SQL
from agent_rewind.migrations.schema import checksum


@pytest.fixture
def legacy(tmp_path):
    case = seed_ar7(complete_ar6(tmp_path / "legacy.sqlite", legacy=True))
    yield case
    case.dispose()


def inspect_case(case):
    before = sqlite_snapshot(case.path)
    statements = []
    native = []
    with case.engine.connect() as connection:
        raw = connection.connection.driver_connection
        raw.set_trace_callback(native.append)

        def observe(c, cu, statement, parameters, context, many):
            statements.append((statement, len(parameters)))
            assert c.connection.driver_connection is raw
            if statement != "BEGIN":
                assert raw.in_transaction

        event.listen(connection, "before_cursor_execute", observe)
        try:
            result = guard.check_schema_compatibility(connection, guard.load_release_profile())
        finally:
            event.remove(connection, "before_cursor_execute", observe)
            raw.set_trace_callback(None)
        assert not raw.in_transaction and not connection.in_transaction()
        assert raw.execute("PRAGMA query_only").fetchone() == (0,)
    assert case.engine.pool.checkedout() == 0
    assert sqlite_snapshot(case.path) == before
    assert "BEGIN" in native and "ROLLBACK" in native
    assert not any(sql.startswith(("INSERT ", "UPDATE ", "DELETE ", "COMMIT")) for sql in native)
    return result, statements


def body_statements(case, statements):
    bodies = {
        str(text(SQL["sqlite_" + family + "_body"]).compile(dialect=case.engine.dialect))
        for family in ("immutable_accounts", "original_jobs")
    }
    return [sql for sql, _ in statements if sql in bodies]


@pytest.mark.parametrize("history", ["fresh", "empty", "legacy", "provision", "evolved"])
def test_complete_seeded_history_stays_nonready_and_readonly(tmp_path, history):
    case = seed_ar7(
        complete_ar6(tmp_path / "state.sqlite", legacy=history == "legacy"),
        empty_accounts=history == "empty",
    )
    try:
        if history == "provision":
            account = deepcopy(case.manifest["accounts"][0])
            account.update(
                id=identifier(7_000_000),
                period_start="2030-01-01T00:00:00.000000Z",
                period_end="2031-01-01T00:00:00.000000Z",
            )
            append_provision(case, [account])
        if history == "evolved":
            later_admitted_call(case, effect="reserved", future_zero_period=True)
        result, statements = inspect_case(case)
        assert (result.status, result.code, result.installation_key) == (
            "incompatible",
            "migration_only",
            None,
        )
        assert body_statements(case, statements) or history == "empty"
        projected = [
            count
            for sql, count in statements
            if sql
            in {str(text(value).compile(dialect=case.engine.dialect)) for value in SQL.values()}
        ]
        assert max(projected) <= 16
        if history == "legacy":
            assert case.opening["organization_opening_microusd"] == 245000
    finally:
        case.dispose()


@pytest.mark.parametrize("mutation", ["missing", "extra", "limit", "opening", "same_count"])
def test_native_immutable_account_drift_is_not_hidden_by_history(legacy, mutation):
    with legacy.engine.begin() as connection:
        row = dict(
            connection.exec_driver_sql("SELECT * FROM budget_accounts ORDER BY id LIMIT 1")
            .mappings()
            .one()
        )
        if mutation == "missing":
            connection.execute(text("DELETE FROM budget_accounts WHERE id=:id"), {"id": row["id"]})
        elif mutation == "limit":
            connection.execute(
                text("UPDATE budget_accounts SET limit_microusd=limit_microusd+1 WHERE id=:id"),
                {"id": row["id"]},
            )
        elif mutation == "opening":
            connection.execute(
                text(
                    "UPDATE budget_accounts SET opening_held_microusd=opening_held_microusd-1 "
                    "WHERE id=:id"
                ),
                {"id": row["id"]},
            )
        elif mutation == "same_count":
            connection.execute(
                text("UPDATE budget_accounts SET id=:new WHERE id=:id"),
                {"new": identifier(8_000_000), "id": row["id"]},
            )
        else:
            row.update(
                id=identifier(8_000_000),
                period_start="2030-01-01T00:00:00.000000Z",
                period_end="2031-01-01T00:00:00.000000Z",
                held_microusd=0,
                accounted_microusd=0,
                opening_held_microusd=0,
            )
            connection.execute(
                text(
                    "INSERT INTO budget_accounts "
                    "(id,organization_id,scope,scope_id,project_id,job_id,period_start,period_end,"
                    "limit_microusd,held_microusd,accounted_microusd,opening_held_microusd) VALUES "
                    "(:id,:organization_id,:scope,:scope_id,:project_id,:job_id,"
                    ":period_start,:period_end,:limit_microusd,:held_microusd,"
                    ":accounted_microusd,:opening_held_microusd)"
                ),
                row,
            )
    result, statements = inspect_case(legacy)
    assert result.code == "schema_incompatible"
    if mutation in {"missing", "extra"}:
        assert not body_statements(legacy, statements)


@pytest.mark.parametrize("mutation", ["missing_job", "amount", "scope", "project"])
def test_original_native_opening_binding_is_required(legacy, mutation):
    job = legacy.opening["jobs"][0]
    if mutation == "project":
        # Corrupt-snapshot negative: historical SQLite FK enforcement is not proof.
        with closing(sqlite3.connect(legacy.path)) as raw:
            assert raw.execute("PRAGMA foreign_keys").fetchone() == (0,)
            raw.execute("DELETE FROM projects WHERE id=?", (job["project_id"],))
            raw.commit()
    with legacy.engine.begin() as connection:
        if mutation == "missing_job":
            connection.execute(text("DELETE FROM jobs WHERE id=:id"), {"id": job["job_id"]})
        elif mutation == "amount":
            connection.execute(
                text(
                    "UPDATE jobs SET legacy_reserved_microusd=legacy_reserved_microusd-1 "
                    "WHERE id=:id"
                ),
                {"id": job["job_id"]},
            )
        elif mutation == "scope":
            connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_kind='job' AND resource_id=:id"),
                {"id": job["job_id"]},
            )
    result, _ = inspect_case(legacy)
    assert result.code == "schema_incompatible"


def test_self_consistent_forged_manifest_cannot_replace_actual_account_equality(legacy):
    raw = deepcopy(legacy.manifest)
    raw["accounts"][0]["limit_microusd"] += 1
    cursor = cursor_for(raw, sequence=0, role=None)
    # Preserve actual opening projection in the altered self-consistent receipt.
    cursor["account_projection_digest"] = checksum(
        [
            {
                **row,
                "opening_held_microusd": (
                    legacy.opening["organization_opening_microusd"]
                    if row["scope"] == "organization"
                    else next(
                        (
                            j["legacy_reserved_microusd"]
                            for j in legacy.opening["jobs"]
                            if j["job_id"] == row["job_id"]
                        ),
                        legacy.opening["project_totals"][0]["opening_held_microusd"],
                    )
                ),
            }
            for row in raw["accounts"]
        ]
    )
    cursor.update(
        imported_jobs=legacy.cursor["imported_jobs"],
        imported_opening_microusd=legacy.cursor["imported_opening_microusd"],
    )
    opening = deepcopy(legacy.opening)
    opening["manifest_digest"] = checksum(raw)
    with legacy.engine.begin() as connection:
        connection.execute(
            text("UPDATE migration_progress SET cursor=:cursor WHERE phase=:phase"),
            {"cursor": json.dumps(cursor), "phase": "ledger_manifest_" + raw["manifest_id"]},
        )
        connection.execute(
            text("UPDATE migration_progress SET cursor=:cursor WHERE phase='ledger_opening'"),
            {"cursor": json.dumps(opening)},
        )
    result, statements = inspect_case(legacy)
    assert result.code == "schema_incompatible"
    # History passed: this refusal follows actual immutable account body transfer.
    assert body_statements(legacy, statements)


def test_current_balances_and_budget_are_outside_nonready_immutable_proof(legacy):
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE budget_accounts SET held_microusd=0,accounted_microusd=0"
        )
        connection.exec_driver_sql("UPDATE jobs SET budget=budget+100,reserved=0")
    result, _ = inspect_case(legacy)
    assert result.code == "migration_only"


@pytest.mark.parametrize("receipt", ["candidate_rows", "native_bytes", "utf8_bytes"])
def test_receipt_mismatch_never_publishes_partial_state(legacy, monkeypatch, receipt):
    query = adapter._query

    def corrupted(connection, name, parameters, checks):
        rows = query(connection, name, parameters, checks)
        if name == "immutable_accounts_gate":
            rows[0][receipt] += 1
        return rows

    monkeypatch.setattr(adapter, "_query", corrupted)
    result, statements = inspect_case(legacy)
    assert result.code == "schema_incompatible"
    if receipt == "candidate_rows":
        assert not body_statements(legacy, statements)


@pytest.mark.parametrize("expired", [False, True])
def test_complete_adapter_checks_after_actual_projection_serialization(
    legacy, monkeypatch, expired
):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(guard, "time", SimpleNamespace(monotonic=lambda: clock.now))
    serialize = adapter.canonical
    seen = []

    def delayed(value):
        result = serialize(value)
        if isinstance(value, dict) and "opening_held_microusd" in value:
            seen.append(value["id"])
            if expired:
                clock.now = 2.0
        return result

    monkeypatch.setattr(adapter, "canonical", delayed)
    result, _ = inspect_case(legacy)
    assert seen
    assert result.code == ("schema_unavailable" if expired else "migration_only")
    if expired:
        assert len(seen) == 1


@pytest.mark.parametrize("position", ["first", "last"])
def test_malformed_native_account_at_either_edge_refuses_before_any_projection_body(
    legacy, position
):
    order = "ASC" if position == "first" else "DESC"
    with closing(sqlite3.connect(legacy.path)) as raw:
        # Deliberately invalid stored row, without changing the exact schema profile.
        raw.execute("PRAGMA ignore_check_constraints=ON")
        identifier_value = raw.execute(
            "SELECT id FROM budget_accounts ORDER BY id " + order + " LIMIT 1"
        ).fetchone()[0]
        raw.execute(
            "UPDATE budget_accounts SET scope_id=? WHERE id=?",
            ("a" * 31 + "\x00", identifier_value),
        )
        raw.commit()
    result, statements = inspect_case(legacy)
    assert result.code == "schema_incompatible"
    assert not body_statements(legacy, statements)
