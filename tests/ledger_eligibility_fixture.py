"""Admitted ar6 predecessors and independent SQL-derived eligibility expectations."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

from ledger_provisioning_fixture import (
    build_case,
    ciphertexts,
    identity,
    initial_manifest,
    reader,
    snapshot,
    source_fingerprint,
    source_rows,
)
from sqlalchemy import text
from test_admission_configuration import configuration
from test_admission_request import submission
from test_admission_submit import Policy, Ready, Storage

from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_journal import AdmissionJournal
from agent_rewind.admission_request import parse_submit
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal

CASES = ("admitted", "running", "queued-owner", "queued-lease", "queued-reserved", "queued-v1")
CHANGES = {
    "running": ("status", "running"),
    "queued-owner": ("owner", "eligibility-owner"),
    "queued-lease": ("lease_until", 1700000000.25),
    "queued-reserved": ("reserved", 1),
    "queued-v1": ("status", "queued"),
}


def rows(state, table):
    value = state["tables"][table]
    return [dict(zip(value["columns"], raw, strict=True)) for raw in value["rows"]]


def file_hashes(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(directory).rglob("*"))
        if path.is_file()
    }


def refreshed(fixture):
    original = source_rows(fixture.case.path)
    with reader(fixture.case.path) as connection:
        jobs = [
            dict(row)
            for row in connection.execute(
                "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                "ORDER BY j.id"
            )
        ]
        assert len(jobs) == connection.execute("SELECT count(*) FROM jobs").fetchone()[0]
    return replace(
        fixture,
        before=snapshot(fixture.case.path),
        original=original,
        source=source_fingerprint(original),
        jobs=jobs,
        encrypted=ciphertexts(fixture.case),
    )


def cohort_manifest(fixture):
    """Every job, including zero-reserved jobs, contributes its actual SQL row."""
    target = initial_manifest(fixture)
    totals = {}
    for row in fixture.jobs:
        assert type(row["reserved"]) is int and 0 <= row["reserved"] <= row["budget"]
        totals[row["project_id"]] = totals.get(row["project_id"], 0) + row["reserved"]
    for account in target["accounts"]:
        if account["scope"] == "organization":
            account["limit_microusd"] = sum(totals.values())
        elif account["scope"] == "project":
            account["limit_microusd"] = totals[account["project_id"]]
    return target


def assert_admitted(state, accepted, *, project, principal, config_digest, budget):
    (job,) = [row for row in rows(state, "jobs") if row["id"] == accepted["job_id"]]
    assert (
        job["status"],
        job["payload_version"],
        job["reserved"],
        job["owner"],
        job["lease_until"],
    ) == ("queued", 2, 0, None, None)
    assert job["budget"] == budget and job["actor"] == principal
    assert job["execution_config_ref"] == job["execution_config_digest"] == config_digest
    (operation,) = [row for row in rows(state, "operations") if row["job_id"] == accepted["job_id"]]
    assert operation["id"] == accepted["operation_id"]
    assert operation["project_id"] == project and operation["principal_id"] == principal
    assert operation["execution_config_digest"] == config_digest
    assert operation["payload_version"] == 2 and operation["kind"] == "run"
    assert json.loads(operation["accepted_response"]) == accepted
    (scope,) = [
        row
        for row in rows(state, "resource_scopes")
        if row["resource_kind"] == "job" and row["resource_id"] == accepted["job_id"]
    ]
    assert scope["project_id"] == project
    (reference,) = [
        row
        for row in rows(state, "artifact_refs")
        if row["owner_kind"] == "job"
        and row["owner_id"] == accepted["job_id"]
        and row["role"] == "admission_config"
    ]
    assert reference["project_id"] == project
    (descriptor,) = [
        row for row in rows(state, "artifact_objects") if row["id"] == reference["artifact_id"]
    ]
    assert descriptor["project_id"] == project and descriptor["digest"] == config_digest
    return {
        "job": job,
        "operation": operation,
        "scope": scope,
        "reference": reference,
        "descriptor": descriptor,
    }


def admitted_predecessor(path, monkeypatch):
    # The accepted builder's three-legacy-job assertions remain unchanged.
    fixture = build_case(path)
    try:
        f = SimpleNamespace(engine=fixture.case.engine, config=configuration())
        f.principal = VerifiedPrincipal("oidc:" + identity(9001) * 2)
        with f.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO project_memberships VALUES(:p,:id,'operator',NULL,false)"),
                {"p": fixture.project, "id": f.principal.principal_id},
            )
            f.name = connection.execute(
                text("SELECT name FROM projects WHERE id=:p"), {"p": fixture.project}
            ).scalar_one()
        f.authority = RequestAuthority(f.engine)
        f.context = f.authority.named(f.principal, fixture.project).context
        f.intent = parse_submit(canonical(submission()))
        f.root = fixture.case.path.parent / "admission-journal"
        objects = fixture.case.path.parent / "admission-objects"
        f.root.mkdir(mode=0o700)
        objects.mkdir(mode=0o700)
        f.policy, f.ready = Policy(f), Ready(f)
        f.storage, f.journal = Storage(f, objects), AdmissionJournal(f.root)
        f.service = AdmissionCoordinator(
            f.engine,
            f.authority,
            policy=f.policy,
            readiness=f.ready,
            registry=NativeRegistry(f.config, ["fixture-image"]),
            storage=f.storage,
            journal=f.journal,
        )
        compatibility = f.service.schema_compatibility()
        assert compatibility == CompatibilityResult("incompatible", "migration_only")
        # Only predecessor admission uses the established synthetic readiness
        # adapter. Ledger initialization receives no compatibility override.
        with monkeypatch.context() as patch:
            patch.setattr(
                f.service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
            )
            accepted = f.service.submit(
                f.principal, f.context, f.intent, "7" * 64, OriginCorrelation("6" * 32)
            )
        assert len(f.storage.calls) == 3 and f.ready.calls == 1
        for descriptor in f.storage.calls:
            data = f.storage.local.read_verified(descriptor)
            assert hashlib.sha256(data).hexdigest() == descriptor.digest
        result = refreshed(fixture)
        assert result.source != fixture.source
        association = assert_admitted(
            result.before,
            accepted,
            project=result.project,
            principal=f.principal.principal_id,
            config_digest=f.config.digest,
            budget=f.intent.budget_microusd,
        )
        assert len(result.jobs) == len(fixture.jobs) + 1
        assert [
            row for row in rows(result.before, "jobs") if row["id"] != accepted["job_id"]
        ] == rows(fixture.before, "jobs")
        assert ciphertexts(result.case) == fixture.encrypted
        return result, SimpleNamespace(
            accepted=accepted,
            association=association,
            objects=objects,
            journal=f.root,
            ciphertexts=file_hashes(objects),
            journal_hashes=file_hashes(f.root),
            original_legacy_ciphertexts=fixture.encrypted,
            original_legacy_jobs=rows(fixture.before, "jobs"),
            compatibility=asdict(compatibility),
            adapter_scope="Synthetic policy/readiness/schema only for predecessor admission; "
            "actual encrypted publication and actual ledger initialization",
        )
    except BaseException:
        fixture.close()
        raise


def assert_single_cell_change(before, after, job_id, field, value):
    assert before["schema"] == after["schema"]
    assert set(before["tables"]) == set(after["tables"])
    for table in before["tables"]:
        if table != "jobs":
            assert before["tables"][table] == after["tables"][table], table
    old, new = rows(before, "jobs"), rows(after, "jobs")
    expected = [{**row, field: value} if row["id"] == job_id else row for row in old]
    assert sorted(new, key=lambda row: row["id"]) == sorted(expected, key=lambda row: row["id"])
    assert [row["id"] for row in old if row["id"] == job_id] == [job_id]
    assert next(row for row in old if row["id"] == job_id)[field] != value


def change_eligibility(fixture, case, job_id):
    field, value = CHANGES[case]
    before = snapshot(fixture.case.path)
    with fixture.case.engine.begin() as connection:
        connection.exec_driver_sql(f"UPDATE jobs SET {field}=? WHERE id=?", (value, job_id))
    result = refreshed(fixture)
    assert_single_cell_change(before, result.before, job_id, field, value)
    return result
