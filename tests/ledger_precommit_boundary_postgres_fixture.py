"""Independent native stage and complete predecessor oracles for early rollback."""

import hashlib
import re

from ledger_precommit_boundary_fixture import INDEXES, PROBES, STAGES, TABLES, assert_probe_rows
from ledger_provisioning_fixture import source_fingerprint
from ledger_provisioning_postgres_fixture import encrypted_files, native_snapshot, source_rows
from ledger_restore_authority import typed
from test_run_projection_postgres import drain

# Original PostgreSQL upgrade targets from the accepted native staged-finalizer
# witness: two Alembic reads, two alters, three tables, five indexes and revision.
# Keep this independent of the runtime DDL builder.
UPGRADE_HASHES = (
    "b36a42e7c918b8bc95d068f8a28ee1a4b9408bf04a91c0da5dcabb6eb20d4361",
    "5694fb3dd7a7ef408b69d7bb07752dc2c3dd00840409d63405e49c8aa0b14099",
    "6263c479c8a727dd28e6c1e849ed9b408043e39dbdb94efd6a9536b38ab3dd43",
    "6423f0d0db575d11cd4ff699f3957d8ed5e9ed6c387b57241440b8433c612761",
    "070cce495cf0245f4fe2a71679f33de7bc17c1522e9b44232748a2496732f541",
    "c878ac09948fbfa83432f6b83a03ea26fd55751ed9dd163210561c0a70a00729",
    "aea6345217e70c47606b57c2441be8e0f8766e2b28a03609b361d91c95ddab66",
    "f358b0e79809fe7a0a828d4d44ba3d268d07c380675c77de1510153a1e51e7ce",
    "17331a85189a15166bafce3f61fba4e1b67cd1a506711e954b54f2377eb0055f",
    "8388cb6a37159a3f3ce1fcdc1fee21ae3df2573d1447ed8d70aff1eedfdb650f",
    "0a954756edd7cb91b99ead551393025efe73af4b5db2fe3c7b7b957a82900b32",
    "db1fd2d62c3b3cfb23155f810ad76d51230e926d051e3d592f4e1540c8f285e5",
    "d6bec8a09ce5a1ea3a3d3fbea06eb86e12d8bfaf208a4db109197e8e5b27099f",
)
REFLECTION_PARAMETERS = {
    "table_names_1": "alembic_version",
    "param_1": "r",
    "param_2": "p",
    "param_3": "f",
    "param_4": "v",
    "param_5": "m",
    "nspname_1": "pg_catalog",
}
CATALOG_PROBES = (
    (
        "relations",
        """SELECT c.relname,c.relkind::text FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN (
'budget_accounts','provider_calls','budget_entries','ar7_calls_job_id',
'ar7_calls_organization_account_id','ar7_calls_project_account_id',
'ar7_calls_job_account_id','ar7_entries_account_id') ORDER BY c.relname""",
    ),
    (
        "columns",
        """SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a
JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
WHERE n.nspname='public' AND c.relname='jobs' AND a.attnum>0 AND NOT a.attisdropped
AND a.attname IN ('lease_generation','legacy_reserved_microusd') ORDER BY a.attname""",
    ),
    (
        "executables",
        """SELECT
(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='ar7_ledger_constraint'),
(SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgname LIKE 'ar7_%')""",
    ),
)
ALL_PROBES = (*PROBES, *CATALOG_PROBES)
BACKFILL_SQL = (
    "UPDATE jobs SET legacy_reserved_microusd=%(opening)s::BIGINT, lease_generation=0 "
    "WHERE id=%(id)s::VARCHAR"
)


def sql_hash(sql):
    return hashlib.sha256(sql.encode()).hexdigest()


def assert_native_span(entry, events, calls, raw_id, timeout_seconds, hashes, parameters):
    """Require original target returns and both bounded setters, not only SQL text."""
    start, end = entry["entered_at"], entry["returned_at"]
    assert type(timeout_seconds) is int and timeout_seconds > 0
    assert all(type(entry[key]) is int for key in ("work_before", "work_after"))
    assert type(start) is int and type(end) is int and 0 <= start < end <= len(events)
    selected = [row for row in calls if start <= row["entered_at"] < end]
    assert len(selected) == 3 * len(hashes)
    assert len(events[start:end]) == 2 * len(selected)
    assert entry["work_after"] - entry["work_before"] == len(selected)
    for index, row in enumerate(selected):
        position = start + 2 * index
        assert all(type(row[key]) is int for key in ("entered_at", "returned_at", "raw_id"))
        assert row["entered_at"] == position and row["returned_at"] == position + 2
        assert row["phase"] == "ordinary" and row["raw_id"] == raw_id
        assert row["outcome"] == "return"
        sql = row["sql"]
        assert type(row["parameters"]) in (dict, type(None))
        assert typed(events[position : position + 2]) == typed(
            [
                ("ordinary", "sql-call", raw_id, sql),
                ("ordinary", "sql-return", raw_id, sql),
            ]
        )
        ordinal, part = divmod(index, 3)
        if part < 2:
            name = "statement_timeout" if part == 0 else "lock_timeout"
            match = re.fullmatch(r"SET LOCAL " + name + r" = '([1-9][0-9]*)ms'", sql)
            assert match and int(match[1]) <= min(
                timeout_seconds * 1000, 20000 if part == 0 else 5000
            )
            assert row["parameters"] in (None, {})
        else:
            assert sql_hash(sql) == hashes[ordinal]
            assert typed(row["parameters"] or {}) == typed(parameters[ordinal])


def assert_stage_rows(probes, jobs, stage):
    assert stage in STAGES and [row["name"] for row in probes] == [name for name, _ in ALL_PROBES]
    assert [row["sql"] for row in probes] == [sql for _, sql in ALL_PROBES]
    assert_probe_rows(probes[: len(PROBES)], jobs, stage)
    relations, columns, executables = [row["rows"] for row in probes[len(PROBES) :]]
    assert typed(relations) == typed(
        sorted([(table, "r") for table in TABLES] + [(name, "i") for name, _ in INDEXES])
    )
    assert typed(columns) == typed(
        [
            ("lease_generation", "bigint", True, "0"),
            ("legacy_reserved_microusd", "bigint", True, "0"),
        ]
    )
    assert typed(executables) == typed([(0, 0)])


def assert_preservation_values(fixture, after, original, encrypted):
    assert typed(after) == typed(fixture.before)
    assert typed(original) == typed(fixture.original)
    assert source_fingerprint(original) == fixture.source
    assert len(encrypted) == 18 and encrypted == fixture.encrypted


def assert_preserved(fixture, pg):
    """Re-read native tables/catalog/authority and all retained ciphertext files."""
    after = native_snapshot(fixture.case, pg)
    try:
        with fixture.case.engine.connect() as connection:
            original = source_rows(connection)
    finally:
        drain(pg)
    encrypted = encrypted_files(fixture)
    assert_preservation_values(fixture, after, original, encrypted)
    return {
        "snapshot": typed(after),
        "source_rows": typed(original),
        "source_fingerprint": fixture.source,
        "ciphertexts": encrypted,
    }
