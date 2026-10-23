"""Independent native stage and exact predecessor oracles for two early writer faults."""

import re
import sqlite3

from ledger_provisioning_fixture import (
    ciphertexts,
    snapshot,
    source_fingerprint,
    source_rows,
)

from agent_rewind.migrations.schema import ADMISSION, LEDGER

STAGES = ("after-ddl", "first-backfill")
ALTERS = (
    "ALTER TABLE jobs ADD COLUMN lease_generation BIGINT NOT NULL DEFAULT 0 "
    "CONSTRAINT ar7_jobs_generation CHECK(typeof(lease_generation)='integer' "
    "AND lease_generation BETWEEN 0 AND 9223372036854775807)",
    "ALTER TABLE jobs ADD COLUMN legacy_reserved_microusd BIGINT NOT NULL DEFAULT 0 "
    "CONSTRAINT ar7_jobs_legacy_reserved CHECK(typeof(legacy_reserved_microusd)='integer' "
    "AND legacy_reserved_microusd BETWEEN 0 AND 9223372036854775807)",
)
QUICK_CHECK = "-- PRAGMA 'main'.quick_check='jobs'"
PROBES = (
    ("version", "SELECT version_num FROM alembic_version ORDER BY version_num"),
    (
        "jobs",
        "SELECT id,lease_generation,legacy_reserved_microusd FROM jobs ORDER BY id",
    ),
    (
        "counts",
        "SELECT (SELECT count(*) FROM budget_accounts),"
        "(SELECT count(*) FROM provider_calls),(SELECT count(*) FROM budget_entries)",
    ),
)
TABLES = ("budget_accounts", "provider_calls", "budget_entries")
INDEXES = (
    ("ar7_calls_job_id", "provider_calls"),
    ("ar7_calls_organization_account_id", "provider_calls"),
    ("ar7_calls_project_account_id", "provider_calls"),
    ("ar7_calls_job_account_id", "provider_calls"),
    ("ar7_entries_account_id", "budget_entries"),
)


def native_statements(events, raw_id):
    """Pair SQL with the same raw handle's actual execute return, not a helper visit."""
    rows, pending = [], None
    for position, event in enumerate(events):
        if len(event) < 4 or event[2] != raw_id:
            continue
        kind, _, _, value = event
        if kind == "c_call" and value in {"execute", "executemany", "commit", "rollback"}:
            assert pending is None, "nested native execute"
            pending = {"call": position, "method": value, "sql": []}
        elif kind == "sql":
            assert pending is not None, "SQL without native execute"
            pending["sql"].append(value)
        elif kind in {"c_return", "c_exception"} and value in {
            "execute",
            "executemany",
            "commit",
            "rollback",
        }:
            assert pending is not None and pending["method"] == value
            rows.append({**pending, "end": position, "outcome": kind})
            pending = None
    assert pending is None, "native execute did not finish"
    return rows


def returned_sql(events, raw_id, *, allow_alter_internal=False):
    rows = native_statements(events, raw_id)
    assert rows and all(row["outcome"] == "c_return" for row in rows)
    result = []
    for row in rows:
        statements = row["sql"]
        assert statements, "native call without SQL"
        if allow_alter_internal and statements[0] in ALTERS:
            # This exact SQLite validation callback shares the ALTER's execute.
            # It is retained in the raw trace; no arbitrary extra SQL is ignored.
            assert statements[1:] == [QUICK_CHECK]
        else:
            assert len(statements) == 1, "ambiguous native statement"
        result.append(" ".join(statements[0].split()))
    return result


def assert_target(events, raw_id, sql, timeout_seconds):
    statements = returned_sql(events, raw_id)
    assert len(statements) == 2
    setter = re.fullmatch(r"PRAGMA busy_timeout=([0-9]+)", statements[0])
    assert setter is not None and 1 <= int(setter[1]) <= timeout_seconds * 1000
    assert statements[1] == " ".join(sql.split())


def assert_upgrade_stage(events, actions, raw_id):
    statements = returned_sql(events, raw_id, allow_alter_internal=True)
    writes = [
        sql
        for sql in statements
        if sql.startswith(("ALTER ", "CREATE ", "UPDATE ", "INSERT ", "DELETE ", "DROP "))
    ]
    assert len(writes) == 11
    assert writes[:2] == list(ALTERS)
    for sql, table in zip(writes[2:5], TABLES, strict=True):
        assert sql.startswith("CREATE TABLE " + table + " (")
    assert writes[5:10] == [
        f"CREATE INDEX {name} ON {table}({name.removeprefix('ar7_calls_')})"
        if table == "provider_calls"
        else "CREATE INDEX ar7_entries_account_id ON budget_entries(account_id)"
        for name, table in INDEXES
    ]
    assert writes[10] == (
        f"UPDATE alembic_version SET version_num='{LEDGER}' "
        f"WHERE alembic_version.version_num = '{ADMISSION}'"
    )
    assert [
        (first, second)
        for action, first, second, _, _ in actions
        if action == sqlite3.SQLITE_ALTER_TABLE
    ] == [("main", "jobs"), ("main", "jobs")]
    assert [
        first for action, first, _, _, _ in actions if action == sqlite3.SQLITE_CREATE_TABLE
    ] == list(TABLES)
    assert [
        (first, second)
        for action, first, second, _, _ in actions
        if action == sqlite3.SQLITE_CREATE_INDEX and first.startswith("ar7_")
    ] == list(INDEXES)
    assert all(trigger is None for _, _, _, _, trigger in actions)


def assert_probe_rows(probes, jobs, stage):
    assert stage in STAGES and len(jobs) == 3
    assert [row["name"] for row in probes] == [name for name, _ in PROBES]
    assert [row["sql"] for row in probes] == [sql for _, sql in PROBES]
    assert probes[0]["rows"] == [(LEDGER,)]
    expected = [
        (job["id"], 0, job["reserved"] if stage == "first-backfill" and i == 0 else 0)
        for i, job in enumerate(jobs)
    ]
    assert probes[1]["rows"] == expected
    assert all(type(value) is int for row in probes[1]["rows"] for value in row[1:])
    assert probes[2]["rows"] == [(0, 0, 0)]
    assert all(type(value) is int for value in probes[2]["rows"][0])


def assert_preserved(fixture):
    """Re-read every original table and schema after rollback and fresh classification."""
    after = snapshot(fixture.case.path)
    original = source_rows(fixture.case.path)
    encrypted = ciphertexts(fixture.case)
    assert after == fixture.before
    assert original == fixture.original and source_fingerprint(original) == fixture.source
    assert len(encrypted) == 18 and encrypted == fixture.encrypted
    return {
        "snapshot": after,
        "source_rows": original,
        "source_fingerprint": fixture.source,
        "ciphertexts": encrypted,
    }
