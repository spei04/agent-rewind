"""Independent complete-history fixtures for whole compatibility capacity checks.

The ar7 history is explicit fixture SQL, not service-write evidence. Original
legacy rows and ciphertext are preserved; added jobs are zero-exposure fixtures.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from ledger_fixture import OBSERVED, canonical_bytes, cursor_for, digest, identifier
from ledger_reader_fixture import (
    _insert_provision,
    _provision_expected,
    _provision_manifest,
    append_provision,
    seed_ar7,
)
from sqlalchemy import text

from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.schema import LEDGER

CURSOR_LIMIT = 16 * 1024 * 1024


def strict_json_value(raw):
    """Decode fixture JSON without losing duplicate members or nonfinite values."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate fixture JSON member")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite fixture JSON number")

    assert type(raw) is str
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def object_hashes(case, *, directory=None):
    if directory is None:
        assert case.path is not None
        directory = case.path.parent / "objects"
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
    }


def extend_opening(case):
    """Keep the real three-job 245000 opening and add 45 terminal zero-held v1 jobs."""
    with case.engine.begin() as connection:
        organization = connection.exec_driver_sql("SELECT id FROM organizations").scalar_one()
        original = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id,kind,created,payload,status,owner,lease_until,cancel,budget,reserved,"
                "result,error,actor FROM jobs ORDER BY id"
            )
        ]
        assert len(original) == 3 and sum(row[9] for row in original) == 245000
        projects = [connection.exec_driver_sql("SELECT id FROM projects").scalar_one()]
        for index in range(14):
            project = identifier(50_000_000 + index)
            connection.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at) "
                    "VALUES(:id,:organization,:name,:created)"
                ),
                {
                    "id": project,
                    "organization": organization,
                    "name": f"capacity-project-{index}",
                    "created": OBSERVED,
                },
            )
            projects.append(project)
        for index in range(45):
            job = identifier(60_000_000 + index)
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
                    "VALUES(:id,'run',1700000000.125,:payload,'succeeded',false,1000000,0)"
                ),
                {"id": job, "payload": "c" * 64},
            )
            connection.execute(
                text(
                    "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
                    "VALUES('job',:job,:project)"
                ),
                {"job": job, "project": projects[index % 15]},
            )
        added = [
            dict(row)
            for row in connection.exec_driver_sql(
                "SELECT id,status,payload_version,reserved,owner,lease_until,"
                "execution_config_ref,execution_config_digest FROM jobs ORDER BY id"
            ).mappings()
            if row["id"] not in {old[0] for old in original}
        ]
        assert len(added) == 45
        assert all(
            row["status"] == "succeeded"
            and row["payload_version"] == 1
            and row["reserved"] == 0
            and row["owner"] is None
            and row["lease_until"] is None
            and row["execution_config_ref"] is None
            and row["execution_config_digest"] is None
            for row in added
        )
        assert [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id,kind,created,payload,status,owner,lease_until,cancel,budget,reserved,"
                "result,error,actor FROM jobs ORDER BY id"
            )
            if row[0] in {old[0] for old in original}
        ] == original
        case.original_digest = source_digest(connection)
    return original


def _capacity_batches(organization_template, accounts):
    remaining = accounts - 64
    offset = 0
    origin = datetime(2030, 1, 1, tzinfo=UTC)
    for sequence in range(1, 256):
        count = min(16, remaining - (255 - sequence))
        assert 1 <= count <= 16
        rows = []
        for _ in range(count):
            start = origin + timedelta(days=offset)
            end = start + timedelta(days=1)
            rows.append(
                {
                    **organization_template,
                    "id": identifier(70_000_000 + offset),
                    "period_start": start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "period_end": end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                }
            )
            offset += 1
        yield rows
        remaining -= count
    assert remaining == 0


def _append_sqlite_capacity(case, batches):
    """Seed synthetic history atomically; no service-commit proof is replaced."""
    assert case.engine.dialect.name == "sqlite"
    assert case.manifest is not None and case.opening is not None
    manifest, cursor, expected = case.manifest, case.cursor, case.expected
    with case.engine.begin() as connection:
        # SQLite otherwise defers BEGIN until the first write. Both source reads
        # must share the same native transaction as all fixture inserts.
        connection.exec_driver_sql("BEGIN")
        assert (
            connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1"
            ).first()
            is None
        )
        source = source_digest(connection)
        count = 0
        for rows in batches:
            count += 1
            assert count <= 255 and 1 <= len(rows) <= 16
            sequence = expected["manifest_count"]
            raw = _provision_manifest(manifest, sequence, rows)
            raw["source_digest"] = source
            cursor = cursor_for(raw, sequence=sequence, role=None)
            _insert_provision(connection, raw, cursor)
            manifest = raw
            expected = _provision_expected(expected, raw, sequence)
        assert count > 0
        assert source_digest(connection) == source
    # A failed insert, source check or commit must leave Python state unchanged.
    case.manifest, case.cursor, case.expected = manifest, cursor, expected


def capacity_history(case, *, accounts, object_directory=None, database_role=None):
    """256 manifests; initial 64 rows and 255 nonempty adjacent provision batches."""
    assert accounts in {319, 4096}
    if case.engine.dialect.name == "postgresql":
        assert object_directory is not None and type(database_role) is str
        assert database_role and len(database_role.encode()) <= 63
    else:
        assert case.engine.dialect.name == "sqlite" and database_role is None
    ciphertext = object_hashes(case, directory=object_directory)
    legacy_jobs = extend_opening(case)
    seed_ar7(case)
    assert len(case.manifest["accounts"]) == 64
    assert len(case.opening["jobs"]) == 48
    assert len(case.opening["project_totals"]) == 15
    assert case.opening["organization_opening_microusd"] == 245000
    initial = deepcopy(case.manifest)
    organization_template = deepcopy(initial["accounts"][0])
    batches = _capacity_batches(organization_template, accounts)
    if case.engine.dialect.name == "sqlite":
        _append_sqlite_capacity(case, batches)
    else:
        for rows in batches:
            append_provision(case, rows)
    return {
        "accounts": accounts,
        "manifests": 256,
        "initial": initial,
        "legacy_jobs": legacy_jobs,
        "ciphertext": ciphertext,
        "object_directory": object_directory,
        "database_role": database_role,
    }


def assert_capacity_history(case, expected):
    """Independent canonical hashes, joins, chain, projections, and nonoverlap."""
    with case.engine.connect() as connection:
        native = [
            dict(row)
            for row in connection.exec_driver_sql(
                "SELECT id,organization_id,scope,scope_id,project_id,job_id,period_start,"
                "period_end,limit_microusd,opening_held_microusd "
                "FROM budget_accounts ORDER BY id"
            ).mappings()
        ]
        progress = [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT phase,CAST(cursor AS TEXT) AS cursor,"
                    "source_digest,rows_verified,status "
                    "FROM migration_progress WHERE revision=:revision ORDER BY phase"
                ),
                {"revision": LEDGER},
            ).mappings()
        ]
        jobs = [
            dict(row)
            for row in connection.exec_driver_sql(
                "SELECT j.id,j.budget,j.reserved,j.legacy_reserved_microusd,s.project_id,"
                "p.organization_id FROM jobs j JOIN resource_scopes s "
                "ON s.resource_kind='job' AND s.resource_id=j.id "
                "JOIN projects p ON p.id=s.project_id ORDER BY j.id"
            ).mappings()
        ]
        balances = list(
            connection.exec_driver_sql(
                "SELECT held_microusd,accounted_microusd,opening_held_microusd "
                "FROM budget_accounts ORDER BY id"
            )
        )
        legacy = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id,kind,created,payload,status,owner,lease_until,cancel,budget,reserved,"
                "result,error,actor FROM jobs ORDER BY id"
            )
            if row[0] in {old[0] for old in expected["legacy_jobs"]}
        ]
    assert legacy == expected["legacy_jobs"]
    assert all(held == opening and accounted == 0 for held, accounted, opening in balances)
    assert object_hashes(case, directory=expected["object_directory"]) == expected["ciphertext"]
    if case.engine.dialect.name == "postgresql":
        for row in native:
            for field in ("period_start", "period_end"):
                value = row[field]
                assert type(value) is datetime and value.utcoffset() is not None
                row[field] = value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert len(native) == expected["accounts"] and len(progress) == 257
    assert len(jobs) == 48 and len({row["project_id"] for row in jobs}) == 15
    assert sum(row["legacy_reserved_microusd"] for row in jobs) == 245000
    opening_row = next(row for row in progress if row["phase"] == "ledger_opening")
    opening = strict_json_value(opening_row["cursor"])
    assert canonical_bytes(opening["jobs"]) == canonical_bytes(
        [
            {
                "job_id": row["id"],
                "project_id": row["project_id"],
                "budget_microusd": row["budget"],
                "legacy_reserved_microusd": row["legacy_reserved_microusd"],
            }
            for row in jobs
        ]
    )
    assert opening["jobs_digest"] == digest(opening["jobs"])
    assert opening["organization_opening_microusd"] == 245000
    totals = defaultdict(int)
    for job in jobs:
        assert job["reserved"] == job["legacy_reserved_microusd"]
        totals[job["project_id"]] += job["legacy_reserved_microusd"]
    assert {
        row["project_id"]: row["opening_held_microusd"] for row in opening["project_totals"]
    } == dict(totals)
    exposure = {opening["organization_account_id"]: 245000}
    exposure.update(
        (row["account_id"], row["opening_held_microusd"]) for row in opening["project_totals"]
    )
    job_amounts = {row["id"]: row["legacy_reserved_microusd"] for row in jobs}
    for account in expected["initial"]["accounts"]:
        if account["scope"] == "job":
            exposure[account["id"]] = job_amounts[account["job_id"]]
    assert all(row["opening_held_microusd"] == exposure.get(row["id"], 0) for row in native)
    cursors = [
        strict_json_value(row["cursor"]) for row in progress if row["phase"] != "ledger_opening"
    ]
    cursors.sort(key=lambda row: row["sequence"])
    assert [row["sequence"] for row in cursors] == list(range(256))
    by_id = {row["id"]: row for row in native}
    assert len(by_id) == len(native)
    seen = set()
    periods = defaultdict(list)
    previous = None
    for cursor in cursors:
        raw = cursor["manifest"]
        assert cursor["manifest_digest"] == digest(raw)
        assert raw["parent_manifest_digest"] == cursor["parent_manifest_digest"] == previous
        previous = cursor["manifest_digest"]
        assert raw["installation_key"] == expected["initial"]["installation_key"]
        assert cursor["account_count"] == len(raw["accounts"]) <= 64
        assert cursor["database_role"] == expected["database_role"]
        assert len(canonical_bytes(raw)) <= 32768
        projection = []
        for account in raw["accounts"]:
            assert account["id"] not in seen
            seen.add(account["id"])
            row = by_id[account["id"]]
            assert canonical_bytes({key: row[key] for key in account}) == canonical_bytes(account)
            if cursor["sequence"] > 0:
                assert row["opening_held_microusd"] == 0
            projection.append(row)
            periods[(account["scope"], account["scope_id"])].append(
                (account["period_start"], account["period_end"])
            )
        assert cursor["account_projection_digest"] == digest(projection)
        assert len(canonical_bytes(projection)) <= 26625
    for cohort in periods.values():
        ordered = sorted(cohort)
        assert all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:], strict=False))
    assert seen == set(by_id)
    assert opening["manifest_digest"] == cursors[0]["manifest_digest"]
    assert opening["manifest_id"] == cursors[0]["manifest"]["manifest_id"]
    assert sum(row["opening_held_microusd"] for row in native) == 735000
    for row in progress:
        cursor = strict_json_value(row["cursor"])
        assert row["status"] == "complete"
        is_opening = row["phase"] == "ledger_opening"
        assert row["source_digest"] == (
            cursor["source_digest"] if is_opening else cursor["manifest"]["source_digest"]
        )
        assert row["rows_verified"] == (
            cursor["job_count"] if is_opening else cursor["account_count"]
        )
        assert len(row["cursor"].encode()) <= 65536
    return {
        "accounts": len(native),
        "manifests": len(cursors),
        "opening_jobs": len(jobs),
        "opening_projects": len(opening["project_totals"]),
        "opening_microusd": 245000,
        "native_projection_sha256": digest(native),
        "cursor_bytes": sum(len(row["cursor"].encode()) for row in progress),
        "canonical_cursors_sha256": digest([strict_json_value(row["cursor"]) for row in progress]),
        "canonical_cursor_bytes": sum(
            len(canonical_bytes(strict_json_value(row["cursor"]))) for row in progress
        ),
        "head": previous,
    }


def pad_cursor_bytes(case, *, total):
    """Whitespace changes stored bytes only; every individual cursor stays <=64 KiB."""
    assert total in {CURSOR_LIMIT, CURSOR_LIMIT + 1}
    with case.engine.begin() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT phase,CAST(cursor AS TEXT) AS cursor FROM migration_progress "
                    "WHERE revision=:revision ORDER BY phase"
                ),
                {"revision": LEDGER},
            )
        )
        needed = total - sum(len(row.cursor.encode()) for row in rows)
        assert 0 < needed <= sum(65536 - len(row.cursor.encode()) for row in rows)
        for row in rows:
            added = min(needed, 65536 - len(row.cursor.encode()))
            connection.execute(
                text(
                    "UPDATE migration_progress SET cursor=:cursor "
                    "WHERE revision=:revision AND phase=:phase"
                ),
                {"cursor": row.cursor + " " * added, "revision": LEDGER, "phase": row.phase},
            )
            needed -= added
        assert needed == 0
