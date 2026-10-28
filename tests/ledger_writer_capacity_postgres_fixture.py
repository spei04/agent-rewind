"""Native producer and passive observations for two writer-valid capacity cohorts."""

import hashlib
import os
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy

import psycopg
from ledger_capacity_fixture import strict_json_value
from ledger_eligibility_fixture import file_hashes, rows
from ledger_eligibility_postgres_fixture import refreshed
from ledger_overflow_postgres_fixture import raw_progress
from ledger_precommit_boundary_postgres_fixture import (
    REFLECTION_PARAMETERS,
    UPGRADE_HASHES,
    assert_native_span,
)
from ledger_provisioning_fixture import (
    ROLLOVER,
    START,
    canonical,
    digest,
    identity,
    source_fingerprint,
)
from ledger_provisioning_postgres_fixture import encrypted_files, source_rows
from ledger_restore_authority import typed
from ledger_source_boundary_postgres import assert_hash_span, native_identity
from ledger_writer_capacity_fixture import SHAPES, table_value
from sqlalchemy import text
from test_run_projection_postgres import drain

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.schema import ADMISSION, LEDGER, installed_profile

# Exact original native statements in the retained admitted initialization.
# This is historical SQL provenance, not evidence that these new cases executed.
WRITE_HASHES = {
    "jobs.backfill": "6c700e6d8035a02540857e0b2017762668b23a3128e68cd2bad5ff1bda2ae28e",
    "accounts.insert": "4176a6d11543806ca87ed00cbea21f4a2e89f83bbf2c4e1d4ea08f2e21994c1d",
    "progress.insert": "5ee35c7f3de6460c08124abbeb6d5f5829e1e093e19b734fab11c45f27a5702e",
    "adoption.publish_fingerprint": (
        "46785579bf620bcdc0956ea24ce25df9f01f611ce06d8d551ea0f875ba50f8e5"
    ),
}
SHAPE_IDS = ("projects15-jobs48", "projects16-jobs47")


def expansion_rows(before, original_project, shape):
    """Only explicit project/job/scope inserts; no ar7 or historical cursor seed."""
    project_count, job_count = shape
    assert shape in SHAPES
    (project,) = rows(before, "projects")
    assert project["id"] == original_project and len(rows(before, "jobs")) == 4
    projects = [
        {
            **project,
            "id": identity(50_000_000 + i),
            "name": f"writer-capacity-{i}",
            "run_sequence": 0,
        }
        for i in range(project_count - 1)
    ]
    project_ids = [original_project, *[row["id"] for row in projects]]
    jobs, scopes = [], []
    for index in range(job_count - 4):
        job = {column: None for column in before["tables"]["jobs"]["columns"]}
        job.update(
            id=identity(60_000_000 + index),
            kind="run",
            created=1700000000.125,
            payload="c" * 64,
            status="succeeded",
            cancel=False,
            budget=1000000,
            reserved=0,
            payload_version=1,
        )
        jobs.append(job)
        scopes.append(
            {
                "resource_kind": "job",
                "resource_id": job["id"],
                "project_id": project_ids[index % project_count],
            }
        )
    return {"projects": projects, "jobs": jobs, "resource_scopes": scopes}


def assert_expansion(before, after, additions):
    expected = deepcopy(before)
    for name, added in additions.items():
        previous = rows(before, name)
        columns = before["tables"][name]["columns"]
        assert all(set(row) == set(columns) for row in added)
        expected["tables"][name] = table_value(columns, previous + added)
    assert typed(after) == typed(expected)


def expand_predecessor(fixture, pg, shape, record):
    before = fixture.before
    additions = expansion_rows(before, fixture.project, shape)
    progress = raw_progress(fixture, pg)
    writes = []
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            owner = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert owner == (pg["owner_role"], pg["owner"].url.database)
            for name, added in additions.items():
                columns = before["tables"][name]["columns"]
                statement = text(
                    f"INSERT INTO {name}("
                    + ",".join(columns)
                    + ") VALUES("
                    + ",".join(":" + column for column in columns)
                    + ")"
                )
                for row in added:
                    count = connection.execute(statement, row).rowcount
                    writes.append({"table": name, "values": deepcopy(row), "rowcount": count})
                    assert type(count) is int and count == 1
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        record(
            "cohort_setup_commit",
            {"identity": owner, "writes": typed(writes), "acknowledged": True},
        )
    finally:
        drain(pg)
    result = refreshed(fixture, pg)
    assert_expansion(before, result.before, additions)
    after_progress = raw_progress(result, pg)
    assert typed(after_progress) == typed(progress)
    record(
        "cohort_setup",
        {
            "shape": shape,
            "before": typed(before),
            "after": typed(result.before),
            "additions": typed(additions),
            "raw_progress_before": progress,
            "raw_progress_after": after_progress,
            "scope": "Synthetic terminal-v1/project inserts after genuine predecessor admission",
        },
    )
    return result, progress


def capacity_manifest(fixture):
    before = fixture.before
    projects = sorted(rows(before, "projects"), key=lambda row: row["id"])
    jobs = sorted(rows(before, "jobs"), key=lambda row: row["id"])
    scopes = {
        row["resource_id"]: row["project_id"]
        for row in rows(before, "resource_scopes")
        if row["resource_kind"] == "job"
    }
    assert (len(projects), len(jobs)) in SHAPES and set(scopes) == {row["id"] for row in jobs}
    totals = {
        row["id"]: sum(job["reserved"] for job in jobs if scopes[job["id"]] == row["id"])
        for row in projects
    }

    def account(number, scope, target, limit, project=None, job=None):
        return {
            "id": identity(number),
            "organization_id": fixture.organization,
            "scope": scope,
            "scope_id": target,
            "project_id": project,
            "job_id": job,
            "period_start": START,
            "period_end": ROLLOVER,
            "limit_microusd": limit,
        }

    accounts = [account(10000, "organization", fixture.organization, 245000)]
    accounts += [
        account(20000 + i, "project", row["id"], totals[row["id"]], project=row["id"])
        for i, row in enumerate(projects)
    ]
    accounts += [
        account(30000 + i, "job", row["id"], row["budget"], scopes[row["id"]], row["id"])
        for i, row in enumerate(jobs)
    ]
    return {
        "schema_version": 1,
        "installation_key": fixture.case.adoption["installation_key"],
        "manifest_id": identity(1000000),
        "operation": "initialize",
        "source_digest": fixture.source,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": accounts,
        "opening_accounts": {
            "organization_account_id": identity(10000),
            "projects": [
                {"project_id": row["id"], "account_id": identity(20000 + i)}
                for i, row in enumerate(projects)
            ],
        },
    }


@contextmanager
def observe_writer(watch, monkeypatch, record):
    """Delegate every original operation; no extra SQL or work counter changes."""
    names = (
        "_inspect_ledger_context",
        "_prepare_ledger",
        "_upgrade",
        "_write",
        "_execute",
        "_provenance",
        "_ledger_cursors",
        "_finalize",
    )
    originals = {name: getattr(ledger_service, name) for name in names}
    evidence = {
        "contexts": [],
        "preparation": [],
        "upgrade": [],
        "writes": [],
        "provenance": [],
        "cursors": [],
        "finalization": [],
        "native_calls": [],
    }
    active = []

    def enter(group, **values):
        entry = {
            **native_identity(watch),
            "entered_at": len(watch.trace.events),
            "work_before": watch.work.observed_ordinary,
            **values,
        }
        evidence[group].append(entry)
        return entry

    def returned(entry):
        entry.update(returned_at=len(watch.trace.events), work_after=watch.work.observed_ordinary)

    def context(connection):
        entry = enter("contexts")
        result = originals["_inspect_ledger_context"](connection)
        entry["state"] = result.state.model_dump(mode="json")
        returned(entry)
        return result

    def preparation(context, manifest, work):
        assert work is watch.work
        entry = enter("preparation")
        result = originals["_prepare_ledger"](context, manifest, work)
        entry["prepared"] = {
            "jobs": [row.model_dump(mode="json") for row in result.jobs],
            "project_totals": [row.model_dump(mode="json") for row in result.project_totals],
            "organization_opening": result.organization_opening,
        }
        returned(entry)
        return result

    def upgrade(connection, manifest):
        entry = enter("upgrade")
        active.append(entry)
        try:
            result = originals["_upgrade"](connection, manifest)
            returned(entry)
            return result
        finally:
            active.pop()

    def write(connection, name, values):
        entry = enter("writes", name=name, values=deepcopy(values))
        active.append(entry)
        try:
            result = originals["_write"](connection, name, values)
            returned(entry)
            return result
        finally:
            active.pop()

    def execute(connection, name, values=None):
        result = originals["_execute"](connection, name, values)
        if active and active[-1].get("name") == name:
            active[-1]["rowcount"] = result.rowcount
        return result

    def provenance(connection):
        entry = enter("provenance")
        result = originals["_provenance"](connection)
        entry["value"] = result
        returned(entry)
        return result

    def cursors(connection, manifest, prepared, observed, role, uid, work):
        entry = enter("cursors")
        result = originals["_ledger_cursors"](
            connection, manifest, prepared, observed, role, uid, work
        )
        entry["value"] = [None if row is None else row.model_dump(mode="json") for row in result]
        returned(entry)
        return result

    def finalize(connection, manifest, previous_fingerprint, work):
        entry = enter("finalization", previous_fingerprint=previous_fingerprint)
        result = originals["_finalize"](connection, manifest, previous_fingerprint, work)
        entry["state"] = result.state.model_dump(mode="json")
        returned(entry)
        return result

    native_execute = psycopg.Cursor.execute

    def native(cursor, query, *args, **kwargs):
        if not active or not watch.owns(cursor.connection):
            return native_execute(cursor, query, *args, **kwargs)
        parameters = args[0] if args else kwargs.get("params")
        entry = {
            "entered_at": len(watch.trace.events),
            "phase": watch.trace.phase,
            "raw_id": id(cursor.connection),
            "sql": query.decode() if isinstance(query, bytes) else str(query),
            "parameters": deepcopy(dict(parameters))
            if isinstance(parameters, Mapping)
            else parameters,
            "outcome": "pending",
        }
        evidence["native_calls"].append(entry)
        try:
            result = native_execute(cursor, query, *args, **kwargs)
        except BaseException:
            entry.update(outcome="raise", returned_at=len(watch.trace.events))
            raise
        entry.update(outcome="return", returned_at=len(watch.trace.events))
        return result

    with monkeypatch.context() as patch:
        for name, replacement in (
            ("_inspect_ledger_context", context),
            ("_prepare_ledger", preparation),
            ("_upgrade", upgrade),
            ("_write", write),
            ("_execute", execute),
            ("_provenance", provenance),
            ("_ledger_cursors", cursors),
            ("_finalize", finalize),
        ):
            patch.setattr(ledger_service, name, replacement)
        patch.setattr(psycopg.Cursor, "execute", native)
        try:
            yield evidence
        finally:
            record("writer_observation", typed(evidence))


def expected_writes(before, manifest, expected):
    """Independent complete typed values in original writer order."""
    jobs = expected["inspection"]["opening"]["jobs"]
    accounts = {row["id"]: row for row in rows(expected, "budget_accounts")}
    progress = {
        row["phase"]: row
        for row in rows(expected, "migration_progress")
        if row["revision"] == LEDGER
    }
    result = [
        ("jobs.backfill", {"id": row["job_id"], "opening": row["legacy_reserved_microusd"]})
        for row in jobs
    ]
    for account in manifest["accounts"]:
        row = accounts[account["id"]]
        result.append(
            (
                "accounts.insert",
                {
                    **account,
                    "opening_held_microusd": row["opening_held_microusd"],
                    "held_microusd": row["held_microusd"],
                    "accounted_microusd": 0,
                },
            )
        )
    for phase in ("ledger_manifest_" + manifest["manifest_id"], "ledger_opening"):
        row = progress[phase]
        result.append(
            (
                "progress.insert",
                {
                    **row,
                    "cursor": canonical(row["cursor"]).decode(),
                    "updated_at": expected["receipt"]["initialized_at"],
                },
            )
        )
    (old,) = rows(before, "installation_adoptions")
    result.append(
        (
            "adoption.publish_fingerprint",
            {
                "fingerprint": digest(installed_profile("postgresql", LEDGER)),
                "installation_key": manifest["installation_key"],
                "previous_fingerprint": old["installed_schema_fingerprint"],
            },
        )
    )
    return result


def assert_write_records(records, before, manifest, expected):
    targets = expected_writes(before, manifest, expected)
    assert len(records) == len(targets)
    for entry, (name, values) in zip(records, targets, strict=True):
        assert entry["name"] == name and typed(entry["values"]) == typed(values)
        assert type(entry["rowcount"]) is int and entry["rowcount"] == 1


def assert_upgrade(entry, events, calls, raw_id, timeout_seconds):
    assert_native_span(
        entry,
        events,
        calls,
        raw_id,
        timeout_seconds,
        UPGRADE_HASHES,
        [REFLECTION_PARAMETERS, *({} for _ in UPGRADE_HASHES[1:])],
    )


def assert_writer(evidence, source, source_calls, watch, fixture, manifest, expected):
    bound = native_identity(watch)
    for group in ("contexts", "preparation", "upgrade", "provenance", "cursors", "finalization"):
        (entry,) = evidence[group]
        assert typed({key: entry[key] for key in bound}) == typed(bound)
        assert type(entry["work_before"]) is type(entry["work_after"]) is int
        assert entry["work_before"] <= entry["work_after"]
    assert evidence["contexts"][0]["state"] == {
        "status": "absent",
        "installation_key": manifest["installation_key"],
        "revision": ADMISSION,
        "head": None,
        "manifest_count": 0,
        "account_count": 0,
        "opening": None,
    }
    opening = expected["inspection"]["opening"]
    assert typed(evidence["preparation"][0]["prepared"]) == typed(
        {
            "jobs": opening["jobs"],
            "project_totals": opening["project_totals"],
            "organization_opening": 245000,
        }
    )
    (provenance,) = evidence["provenance"]
    observed, role, uid = provenance["value"]
    assert typed((observed, role, uid)) == typed(
        (expected["receipt"]["initialized_at"], fixture.before["role"], os.getuid())
    )
    progress = {
        row["phase"]: row["cursor"]
        for row in rows(expected, "migration_progress")
        if row["revision"] == LEDGER
    }
    assert typed(evidence["cursors"][0]["value"]) == typed(
        [progress["ledger_manifest_" + manifest["manifest_id"]], progress["ledger_opening"]]
    )
    assert typed(evidence["finalization"][0]["state"]) == typed(expected["inspection"])
    assert source["refusals"] == [] and len(source["preparation"]) == 1
    prepared = source["preparation"][0]
    assert prepared["original_caller"] is True and prepared["completed"] is True
    assert typed(prepared["financial"]["job"]) == typed(
        sorted(rows(fixture.before, "jobs"), key=lambda row: row["id"])
    )
    assert prepared["financial"]["account"] == []
    assert typed(prepared["manifest"]) == typed(manifest)
    assert len(source["hashes"]) == 2
    for index, hashed in enumerate(source["hashes"]):
        assert hashed["original_caller"] is (index == 0) and hashed["result"] == fixture.source
        assert typed({key: hashed[key] for key in bound}) == typed(bound)
        selected = [
            row
            for row in source_calls
            if hashed["entered_at"] <= row["entered_at"] < hashed["returned_at"]
        ]
        assert_hash_span(
            hashed,
            fixture.original,
            bound["raw_id"],
            watch.trace.events,
            watch.parameters.receipts,
            selected,
        )
    first, last = source["hashes"]
    assert evidence["preparation"][0]["returned_at"] <= first["entered_at"]
    assert first["returned_at"] <= evidence["upgrade"][0]["entered_at"]
    assert (
        evidence["finalization"][0]["entered_at"]
        <= last["entered_at"]
        < last["returned_at"]
        <= evidence["finalization"][0]["returned_at"]
    )
    assert_write_records(evidence["writes"], fixture.before, manifest, expected)
    positions = [entry["entered_at"] for entry in evidence["writes"]]
    assert positions == sorted(set(positions))
    assert evidence["upgrade"][0]["returned_at"] <= positions[0]
    assert evidence["writes"][-2]["returned_at"] <= evidence["finalization"][0]["entered_at"]
    assert last["returned_at"] <= evidence["writes"][-1]["entered_at"]
    assert evidence["writes"][-1]["returned_at"] <= evidence["finalization"][0]["returned_at"]
    for entry in evidence["writes"]:
        assert typed({key: entry[key] for key in bound}) == typed(bound)
        assert_native_span(
            entry,
            watch.trace.events,
            evidence["native_calls"],
            bound["raw_id"],
            watch.work.timeout_seconds,
            [WRITE_HASHES[entry["name"]]],
            [entry["values"]],
        )
    assert_upgrade(
        evidence["upgrade"][0],
        watch.trace.events,
        evidence["native_calls"],
        bound["raw_id"],
        watch.work.timeout_seconds,
    )
    assert watch.observer_units == [] and watch.counters == []
    assert watch.work.timeout_seconds == 5 and watch.work.observed_ordinary <= 2028


def assert_native_metadata(before, after):
    assert typed(after["catalog"]) == typed(installed_profile("postgresql", LEDGER))
    assert typed(after["role"]) == typed(before["role"])
    assert typed(after["authority"]["schema"]) == typed(before["authority"]["schema"])
    old = before["authority"]
    new = after["authority"]
    assert set(old) == set(new) == {"schema", "relations", "functions"}
    previous = {row[0]: row for row in old["relations"]}
    current = {row[0]: row for row in new["relations"]}
    assert len(current) == len(new["relations"]) and len(previous) == len(old["relations"])
    added = {
        "budget_accounts",
        "provider_calls",
        "budget_entries",
        "ar7_calls_job_id",
        "ar7_calls_organization_account_id",
        "ar7_calls_project_account_id",
        "ar7_calls_job_account_id",
        "ar7_entries_account_id",
        "ar7_accounts_pk",
        "ar7_accounts_scope_period",
        "ar7_accounts_job_window",
        "ar7_calls_pk",
        "ar7_calls_logical_unique",
        "ar7_calls_project_unique",
        "ar7_entries_pk",
    }
    assert set(current) == set(previous) | added and not (set(previous) & added)
    for key, row in previous.items():
        assert typed(current[key]) == typed(row)
    assert all(typed(current[key][1:]) == typed((after["role"], None)) for key in added)
    function = (
        "ar7_ledger_constraint",
        "",
        after["role"],
        "{" + after["role"] + "=X/" + after["role"] + "}",
    )
    assert not any(row[:2] == function[:2] for row in old["functions"])
    assert typed(new["functions"]) == typed(tuple(sorted((*old["functions"], function))))


def assert_progress(before_raw, after_raw, after, expected):
    old = {(row["revision"], row["phase"]): row for row in before_raw}
    current = {(row["revision"], row["phase"]): row for row in after_raw}
    assert len(old) == len(before_raw) and len(current) == len(after_raw)
    assert all(typed(current[key]) == typed(value) for key, value in old.items())
    added = {key: row for key, row in current.items() if key not in old}
    manifest_id = expected["receipt"]["manifest_id"]
    assert set(added) == {(LEDGER, "ledger_opening"), (LEDGER, "ledger_manifest_" + manifest_id)}
    values = {
        row["phase"]: row["cursor"]
        for row in rows(after, "migration_progress")
        if row["revision"] == LEDGER
    }
    sizes = {}
    for (_, phase), row in added.items():
        raw = row["raw_cursor"]
        value = strict_json_value(raw)
        assert typed(value) == typed(values[phase])
        assert len(raw.encode()) <= 65536 and len(canonical(value)) <= 65536
        sizes[phase] = {"native_bytes": len(raw.encode()), "canonical_bytes": len(canonical(value))}
    assert sum(len(row["raw_cursor"].encode()) for row in after_raw) <= 16 * 1024 * 1024
    return sizes


@contextmanager
def capture_fresh_context(monkeypatch):
    values = []
    original = ledger_service._inspect_ledger_context

    def inspect_context(connection):
        result = original(connection)
        values.append(result.state.model_dump(mode="json"))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ledger_service, "_inspect_ledger_context", inspect_context)
        yield values


def preservation(fixture, admission, pg):
    try:
        with fixture.case.engine.connect() as connection:
            original = source_rows(connection)
    finally:
        drain(pg)
    assert typed(original) == typed(fixture.original)
    assert source_fingerprint(original) == fixture.source
    legacy = encrypted_files(fixture)
    assert len(legacy) == 18 and legacy == admission.original_legacy_ciphertexts
    assert file_hashes(admission.objects) == admission.ciphertexts
    assert file_hashes(admission.journal) == admission.journal_hashes
    for descriptor in admission.descriptors:
        assert (
            hashlib.sha256(admission.storage.read_verified(descriptor)).hexdigest()
            == descriptor.digest
        )
    return {
        "source_rows": typed(original),
        "source_fingerprint": fixture.source,
        "legacy_ciphertexts": legacy,
        "admission_ciphertexts": admission.ciphertexts,
        "admission_journal": admission.journal_hashes,
    }
