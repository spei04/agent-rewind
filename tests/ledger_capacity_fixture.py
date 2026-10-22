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

from ledger_fixture import OBSERVED, canonical_bytes, digest, identifier
from ledger_reader_fixture import append_provision, seed_ar7
from sqlalchemy import text

from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.schema import LEDGER

CURSOR_LIMIT = 16 * 1024 * 1024


def object_hashes(case):
    assert case.path is not None
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((case.path.parent / "objects").iterdir())
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


def capacity_history(case, *, accounts):
    """256 manifests; initial 64 rows and 255 nonempty adjacent provision batches."""
    assert accounts in {319, 4096}
    ciphertext = object_hashes(case)
    legacy_jobs = extend_opening(case)
    seed_ar7(case)
    assert len(case.manifest["accounts"]) == 64
    assert len(case.opening["jobs"]) == 48
    assert len(case.opening["project_totals"]) == 15
    assert case.opening["organization_opening_microusd"] == 245000
    initial = deepcopy(case.manifest)
    organization_template = deepcopy(initial["accounts"][0])
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
        append_provision(case, rows)
        remaining -= count
    assert remaining == 0
    return {
        "accounts": accounts,
        "manifests": 256,
        "initial": initial,
        "legacy_jobs": legacy_jobs,
        "ciphertext": ciphertext,
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
                    "SELECT phase,cursor,source_digest,rows_verified,status "
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
        legacy = [
            tuple(row)
            for row in connection.exec_driver_sql(
                "SELECT id,kind,created,payload,status,owner,lease_until,cancel,budget,reserved,"
                "result,error,actor FROM jobs ORDER BY id"
            )
            if row[0] in {old[0] for old in expected["legacy_jobs"]}
        ]
    assert legacy == expected["legacy_jobs"]
    assert object_hashes(case) == expected["ciphertext"]
    assert len(native) == expected["accounts"] and len(progress) == 257
    assert len(jobs) == 48 and len({row["project_id"] for row in jobs}) == 15
    assert sum(row["legacy_reserved_microusd"] for row in jobs) == 245000
    opening_row = next(row for row in progress if row["phase"] == "ledger_opening")
    opening = json.loads(opening_row["cursor"])
    assert opening["jobs"] == [
        {
            "job_id": row["id"],
            "project_id": row["project_id"],
            "budget_microusd": row["budget"],
            "legacy_reserved_microusd": row["legacy_reserved_microusd"],
        }
        for row in jobs
    ]
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
    cursors = [json.loads(row["cursor"]) for row in progress if row["phase"] != "ledger_opening"]
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
        assert cursor["database_role"] is None
        assert len(canonical_bytes(raw)) <= 32768
        projection = []
        for account in raw["accounts"]:
            assert account["id"] not in seen
            seen.add(account["id"])
            row = by_id[account["id"]]
            assert {key: row[key] for key in account} == account
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
        cursor = json.loads(row["cursor"])
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
        "canonical_cursor_bytes": sum(
            len(canonical_bytes(json.loads(row["cursor"]))) for row in progress
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
                    "SELECT phase,cursor FROM migration_progress "
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
