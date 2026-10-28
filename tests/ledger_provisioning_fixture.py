"""Independent native oracles for real ledger initialization and provisioning.

Only predecessor setup is reused. Expected manifests, source framing, accounts,
opening cursors and receipts do not call the writer's preparation/serialization
helpers. These small states establish no capacity claim; execution evidence is recorded separately.
"""

import hashlib
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from ledger_reader_fixture import complete_ar6

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_service import initialize_ledger
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, catalog, installed_profile

# Frozen original five-table projection, including precisely thirteen job fields.
SOURCE_FIELDS = {
    "api_keys": ("id", "hash", "role", "name", "expires", "revoked"),
    "audit": ("id", "created", "actor", "action", "target"),
    "events": ("run_id", "step", "artifact", "hash"),
    "jobs": (
        "id",
        "kind",
        "created",
        "payload",
        "status",
        "owner",
        "lease_until",
        "cancel",
        "budget",
        "reserved",
        "result",
        "error",
        "actor",
    ),
    "records": ("id", "kind", "created", "data"),
}
ACCOUNT_FIELDS = (
    "id",
    "organization_id",
    "scope",
    "scope_id",
    "project_id",
    "job_id",
    "period_start",
    "period_end",
    "limit_microusd",
)
START = "2000-01-01T00:00:00.000000Z"
ROLLOVER = "2100-01-01T00:00:00.000000Z"
END = "2200-01-01T00:00:00.000000Z"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(number):
    return f"{number:032x}"


@contextmanager
def reader(path):
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        yield connection


def snapshot(path):
    """All actual table cells, column identities and native schema, after cleanup."""
    with reader(path) as connection:
        schema = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            )
        )
        names = [row[1] for row in schema if row[0] == "table"]
        tables = {}
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = connection.execute(f"SELECT * FROM {quoted}")
            tables[name] = {
                "columns": tuple(item[0] for item in cursor.description),
                "rows": tuple(sorted((tuple(row) for row in cursor), key=repr)),
            }
    return {"schema": schema, "tables": tables}


def source_rows(path):
    with reader(path) as connection:
        return {
            table: [
                tuple(row)
                for row in connection.execute(
                    f"SELECT {','.join(fields)} FROM {table} ORDER BY "
                    + ("run_id,step" if table == "events" else "id")
                )
            ]
            for table, fields in SOURCE_FIELDS.items()
        }


def source_fingerprint(rows):
    result = hashlib.sha256()
    for table, fields in SOURCE_FIELDS.items():
        result.update(canonical([table, list(fields)]) + b"\n")
        for raw in rows[table]:
            row = list(raw)
            if table == "records" and isinstance(row[3], str):
                row[3] = json.loads(row[3])
            row = [int(value) if isinstance(value, bool) else value for value in row]
            result.update(canonical(row) + b"\n")
    return result.hexdigest()


def ciphertexts(case):
    directory = case.path.parent / "objects"
    return (
        {
            file.name: hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(directory.iterdir())
        }
        if directory.exists()
        else {}
    )


@dataclass
class ProvisioningFixture:
    case: object
    before: dict
    original: dict
    source: str
    encrypted: dict
    jobs: list
    organization: str
    project: str

    def close(self):
        self.case.dispose()


def build_case(path, *, legacy=True):
    case = complete_ar6(path, legacy=legacy)
    try:
        original = source_rows(case.path)
        with reader(case.path) as connection:
            organization = connection.execute("SELECT id FROM organizations").fetchone()[0]
            project = connection.execute("SELECT id FROM projects").fetchone()[0]
            jobs = [
                dict(row)
                for row in connection.execute(
                    "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                    "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                    "ORDER BY j.id"
                )
            ]
        result = ProvisioningFixture(
            case,
            snapshot(case.path),
            original,
            source_fingerprint(original),
            ciphertexts(case),
            jobs,
            organization,
            project,
        )
        assert result.source == case.original_digest
        if legacy:
            assert sorted(row["reserved"] for row in jobs) == [35000, 85000, 125000]
            assert len(jobs) == 3 and {row["project_id"] for row in jobs} == {project}
            assert result.encrypted
        else:
            assert jobs == [] and not result.encrypted
        return result
    except BaseException:
        case.dispose()
        raise


def initial_manifest(fixture, *, empty=False):
    def account(number, scope, target, *, project=None, job=None, cap=245000):
        return {
            "id": identity(number),
            "organization_id": fixture.organization,
            "scope": scope,
            "scope_id": target,
            "project_id": project,
            "job_id": job,
            "period_start": START,
            "period_end": ROLLOVER,
            "limit_microusd": cap,
        }

    accounts = (
        []
        if empty
        else [
            account(100, "organization", fixture.organization),
            account(200, "project", fixture.project, project=fixture.project),
            *[
                account(
                    300 + i,
                    "job",
                    row["id"],
                    project=row["project_id"],
                    job=row["id"],
                    cap=row["budget"],
                )
                for i, row in enumerate(fixture.jobs)
            ],
        ]
    )
    return {
        "schema_version": 1,
        "installation_key": fixture.case.adoption["installation_key"],
        "manifest_id": identity(1000),
        "operation": "initialize",
        "source_digest": fixture.source,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": accounts,
        "opening_accounts": {
            "organization_account_id": None if empty else identity(100),
            "projects": []
            if empty
            else [{"project_id": fixture.project, "account_id": identity(200)}],
        },
    }


def next_manifest(first):
    result = deepcopy(first)
    result.update(
        manifest_id=identity(1001),
        operation="provision",
        parent_manifest_digest=digest(first),
        opening_accounts=None,
        accounts=[
            {**row, "id": identity(400 + index), "period_start": ROLLOVER, "period_end": END}
            for index, row in enumerate(first["accounts"][:2])
        ],
    )
    assert [row["scope"] for row in result["accounts"]] == ["organization", "project"]
    return result


def invoke(fixture, manifest):
    checked = validate_ledger_manifest(manifest)
    assert checked.canonical_bytes == canonical(manifest)
    assert checked.digest == digest(manifest)
    engine = fixture.case.operator_engine()
    before = datetime.now(UTC)
    try:
        receipt = initialize_ledger(engine, checked)
        after = datetime.now(UTC)
        observed = datetime.fromisoformat(receipt.initialized_at.replace("Z", "+00:00"))
        # SQLite's real timestamp observation has millisecond precision.
        assert before.timestamp() - 0.001 <= observed.timestamp() <= after.timestamp()
        assert engine.pool.checkedout() == 0
        return receipt
    finally:
        engine.dispose()


def inspect(fixture):
    engine = fixture.case.operator_engine()
    outcome = LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            result = inspect_ledger_state(connection)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        assert engine.pool.checkedout() == 0
        return result
    finally:
        engine.dispose()


def expected_opening(fixture, first, observed):
    jobs = [
        {
            "job_id": row["id"],
            "project_id": row["project_id"],
            "budget_microusd": row["budget"],
            "legacy_reserved_microusd": row["reserved"],
        }
        for row in fixture.jobs
    ]
    total = sum(row["reserved"] for row in fixture.jobs)
    return {
        "schema_version": 1,
        "manifest_id": first["manifest_id"],
        "manifest_digest": digest(first),
        "source_digest": fixture.source,
        "initialized_at": observed,
        "jobs": jobs,
        "jobs_digest": digest(jobs),
        "project_totals": [
            {
                **row,
                "opening_held_microusd": sum(
                    job["reserved"]
                    for job in fixture.jobs
                    if job["project_id"] == row["project_id"]
                ),
            }
            for row in first["opening_accounts"]["projects"]
        ],
        "organization_account_id": first["opening_accounts"]["organization_account_id"],
        "organization_opening_microusd": total,
        "job_count": len(jobs),
    }


def expected_stage(fixture, manifests, receipts, *, database_role=None):
    """Pure expected values derived from intent and original native rows."""
    assert len(manifests) == len(receipts) and manifests
    first = manifests[0]
    opening = expected_opening(fixture, first, receipts[0].initialized_at)
    expected_accounts, expected_progress = [], {}
    total = sum(row["reserved"] for row in fixture.jobs)
    job_amounts = {row["id"]: row["reserved"] for row in fixture.jobs}
    for sequence, (manifest, receipt) in enumerate(zip(manifests, receipts, strict=True)):
        accounts = []
        for account in manifest["accounts"]:
            amount = 0
            if sequence == 0:
                amount = job_amounts[account["job_id"]] if account["scope"] == "job" else total
            accounts.append({**account, "opening_held_microusd": amount})
            expected_accounts.append(
                {
                    **account,
                    "opening_held_microusd": amount,
                    "held_microusd": amount,
                    "accounted_microusd": 0,
                }
            )
        imported, exposure = (len(fixture.jobs), total) if sequence == 0 else (0, 0)
        expected_receipt = {
            "installation_key": manifest["installation_key"],
            "revision": LEDGER,
            "manifest_id": manifest["manifest_id"],
            "manifest_digest": digest(manifest),
            "sequence": sequence,
            "operation": manifest["operation"],
            "source_digest": manifest["source_digest"],
            "account_rows": len(accounts),
            "imported_jobs": imported,
            "imported_opening_microusd": exposure,
            "initialized_at": receipt.initialized_at,
            "outcome": "complete",
        }
        assert receipt.model_dump(mode="json") == expected_receipt
        cursor = {
            "schema_version": 1,
            "manifest": manifest,
            "manifest_digest": digest(manifest),
            "sequence": sequence,
            "parent_manifest_digest": manifest["parent_manifest_digest"],
            "database_role": database_role,
            "os_uid": os.getuid(),
            "initialized_at": receipt.initialized_at,
            "account_projection_digest": digest(accounts),
            "account_count": len(accounts),
            "imported_jobs": imported,
            "imported_opening_microusd": exposure,
        }
        expected_progress["ledger_manifest_" + manifest["manifest_id"]] = (
            cursor,
            len(accounts),
            manifest["source_digest"],
        )
    expected_progress["ledger_opening"] = (opening, len(fixture.jobs), fixture.source)
    expected_head = receipts[-1].model_dump(mode="json")
    del expected_head["outcome"]
    state = {
        "status": "complete",
        "installation_key": first["installation_key"],
        "revision": LEDGER,
        "head": expected_head,
        "manifest_count": len(manifests),
        "account_count": len(expected_accounts),
        "opening": opening,
    }
    return expected_accounts, expected_progress, state


def assert_stage(fixture, manifests, receipts):
    """Compare every new cursor/account field against native predecessor facts."""
    expected_accounts, expected_progress, expected_state = expected_stage(
        fixture, manifests, receipts
    )
    with reader(fixture.case.path) as connection:
        actual_accounts = [
            dict(row) for row in connection.execute("SELECT * FROM budget_accounts ORDER BY id")
        ]
        assert actual_accounts == sorted(expected_accounts, key=lambda row: row["id"])
        progress = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM migration_progress WHERE revision=? ORDER BY phase", (LEDGER,)
            )
        ]
        assert {row["phase"] for row in progress} == set(expected_progress)
        for row in progress:
            cursor, count, source = expected_progress[row["phase"]]
            assert row == {
                "revision": LEDGER,
                "phase": row["phase"],
                "source_digest": source,
                "cursor": canonical(cursor).decode(),
                "rows_verified": count,
                "status": "complete",
                "updated_at": cursor["initialized_at"],
            }
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id,legacy_reserved_microusd,lease_generation FROM jobs ORDER BY id"
            )
        ] == [(row["id"], row["reserved"], 0) for row in fixture.jobs]
        assert connection.execute("SELECT count(*) FROM provider_calls").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM budget_entries").fetchone()[0] == 0
        adoption = dict(connection.execute("SELECT * FROM installation_adoptions").fetchone())
        previous = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM migration_progress WHERE revision<>? ORDER BY revision,phase",
                (LEDGER,),
            )
        ]
    assert previous == fixture.case.previous_progress
    assert adoption == {
        **fixture.case.adoption,
        "installed_schema_fingerprint": digest(installed_profile("sqlite", LEDGER)),
    }
    with fixture.case.engine.connect() as connection:
        assert catalog(connection) == installed_profile("sqlite", LEDGER)
    after = snapshot(fixture.case.path)
    assert after["tables"]["alembic_version"] == {
        "columns": ("version_num",),
        "rows": ((LEDGER,),),
    }
    assert_preserved_jobs(fixture.before, after)
    for table, before in fixture.before["tables"].items():
        if table not in {"jobs", "alembic_version", "installation_adoptions", "migration_progress"}:
            assert after["tables"][table] == before, table
    assert source_rows(fixture.case.path) == fixture.original
    assert source_fingerprint(source_rows(fixture.case.path)) == fixture.source
    assert ciphertexts(fixture.case) == fixture.encrypted
    assert inspect(fixture).model_dump(mode="json") == expected_state


def assert_preserved_jobs(before, after):
    """All predecessor values survive; only the two ar7 fields are added."""
    previous_jobs = before["tables"]["jobs"]
    current_jobs = after["tables"]["jobs"]
    assert current_jobs["columns"] == (
        *previous_jobs["columns"],
        "lease_generation",
        "legacy_reserved_microusd",
    )
    original_jobs_by_id = {
        dict(zip(previous_jobs["columns"], row, strict=True))["id"]: dict(
            zip(previous_jobs["columns"], row, strict=True)
        )
        for row in previous_jobs["rows"]
    }
    for raw in current_jobs["rows"]:
        job = dict(zip(current_jobs["columns"], raw, strict=True))
        assert {name: job[name] for name in previous_jobs["columns"]} == original_jobs_by_id[
            job["id"]
        ]
    assert len(current_jobs["rows"]) == len(original_jobs_by_id)


WRITE_ACTIONS = {
    getattr(sqlite3, name)
    for name in (
        "SQLITE_INSERT",
        "SQLITE_UPDATE",
        "SQLITE_DELETE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_ALTER_TABLE",
        "SQLITE_REINDEX",
        "SQLITE_ANALYZE",
        "SQLITE_ATTACH",
        "SQLITE_DETACH",
    )
}


@contextmanager
def native_actions(monkeypatch):
    """Observe real authorizer actions without denying or rewriting native work."""
    actions = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        raw = original(*args, **kwargs)

        def authorize(action, first, second, database, trigger):
            actions.append((action, first, second, database, trigger))
            return sqlite3.SQLITE_OK

        raw.set_authorizer(authorize)
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        yield actions


def assert_no_writes(actions):
    assert actions
    assert not [row for row in actions if row[0] in WRITE_ACTIONS]
