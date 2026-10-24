"""Actual admitted PostgreSQL predecessors and strict native eligibility oracles."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from types import SimpleNamespace

from ledger_eligibility_fixture import (
    CHANGES,
    assert_admitted,
    file_hashes,
    predecessor_compatibility,
    rows,
)
from ledger_provisioning_fixture import digest, expected_stage, source_fingerprint
from ledger_provisioning_postgres_fixture import (
    build_postgres_case,
    encrypted_files,
    native_snapshot,
    source_rows,
)
from ledger_restore_authority import typed
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from test_admission_configuration import configuration
from test_admission_request import submission
from test_admission_submit import Policy, Ready, Storage
from test_run_projection_postgres import drain

from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_journal import AdmissionJournal
from agent_rewind.admission_request import parse_submit
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.migrations.schema import LEDGER, installed_profile
from agent_rewind.models import canonical
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal


def native_handle(watch):
    (raw,) = watch.trace.handles
    return raw


def native_principal(fixture):
    mapping = fixture.case.adoption["mapping"]
    if type(mapping) is str:
        mapping = json.loads(mapping)
    (grant,) = mapping["principal_grants"]
    (member,) = rows(fixture.before, "project_memberships")
    assert grant["role"] == "maintainer" and grant["legacy_default"] is True
    assert typed(member) == typed(
        {
            "project_id": fixture.project,
            "principal_id": grant["principal_id"],
            "role": grant["role"],
            "revoked_at": None,
            "legacy_default": True,
        }
    )
    principal = VerifiedPrincipal(grant["principal_id"])
    return principal, {"mapping_grant": grant, "persisted_membership": member}


def assert_native_jobs(state):
    for job in rows(state, "jobs"):
        assert type(job["created"]) is float
        assert job["lease_until"] is None or type(job["lease_until"]) is float
        assert type(job["cancel"]) is bool
        for field in ("budget", "reserved", "payload_version"):
            assert type(job[field]) is int
        assert 0 <= job["reserved"] <= job["budget"]


def refreshed(fixture, pg):
    try:
        with fixture.case.engine.connect() as connection:
            original = source_rows(connection)
            jobs = [
                dict(row)
                for row in connection.exec_driver_sql(
                    "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                    "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                    "ORDER BY j.id"
                ).mappings()
            ]
            assert len(jobs) == connection.exec_driver_sql("SELECT count(*) FROM jobs").scalar_one()
    finally:
        drain(pg)
    before = native_snapshot(fixture.case, pg)
    assert_native_jobs(before)
    return replace(
        fixture,
        before=before,
        original=original,
        source=source_fingerprint(original),
        jobs=jobs,
        encrypted=encrypted_files(fixture),
    )


def assert_job_change(before, after, job_id, changes):
    assert set(before) == set(after) == {"catalog", "tables", "authority", "role"}
    for name in ("catalog", "authority", "role"):
        assert typed(before[name]) == typed(after[name])
    assert set(before["tables"]) == set(after["tables"])
    for name, previous in before["tables"].items():
        if name != "jobs":
            assert typed(previous) == typed(after["tables"][name]), name
    previous, current = rows(before, "jobs"), rows(after, "jobs")
    (selected,) = [row for row in previous if row["id"] == job_id]
    assert changes and all(typed(selected[key]) != typed(value) for key, value in changes.items())
    expected = [{**row, **changes} if row["id"] == job_id else row for row in previous]
    assert before["tables"]["jobs"]["columns"] == after["tables"]["jobs"]["columns"]
    assert typed(sorted(current, key=lambda row: row["id"])) == typed(
        sorted(expected, key=lambda row: row["id"])
    )


def change_eligibility(fixture, pg, case, job_id):
    field, value = CHANGES[case]
    try:
        with fixture.case.engine.begin() as connection:
            result = connection.execute(
                text(f"UPDATE jobs SET {field}=:value WHERE id=:id"),
                {"value": value, "id": job_id},
            )
            assert result.rowcount == 1
    finally:
        drain(pg)
    result = refreshed(fixture, pg)
    assert_job_change(fixture.before, result.before, job_id, {field: value})
    return result


def terminal_precursor(fixture, pg, job_id):
    try:
        with fixture.case.engine.begin() as connection:
            result = connection.execute(
                text("UPDATE jobs SET reserved=0,owner=NULL,lease_until=NULL WHERE id=:id"),
                {"id": job_id},
            )
            assert result.rowcount == 1
    finally:
        drain(pg)
    result = refreshed(fixture, pg)
    assert_job_change(
        fixture.before, result.before, job_id, {"reserved": 0, "owner": None, "lease_until": None}
    )
    (job,) = [row for row in rows(result.before, "jobs") if row["id"] == job_id]
    assert job["status"] in {"succeeded", "failed", "cancelled"}
    assert type(job["payload_version"]) is int and job["payload_version"] == 1
    return result


def admitted_predecessor(pg, root, monkeypatch, record):
    fixture = build_postgres_case(pg)
    engine = None
    try:
        # The setup adapters require checkedout(); the attested operator stays unchanged.
        engine = create_engine(fixture.case.engine.url, poolclass=QueuePool)
        f = SimpleNamespace(engine=engine, config=configuration())
        f.principal, authority_binding = native_principal(fixture)
        record("predecessor_authority_binding", typed(authority_binding))
        with engine.connect() as connection:
            role = connection.exec_driver_sql("SELECT current_user").scalar_one()
            assert role == pg["owner_role"]
            f.name = connection.execute(
                text("SELECT name FROM projects WHERE id=:p"), {"p": fixture.project}
            ).scalar_one()
        record(
            "admission_connection_prerequisite",
            {
                "role": role,
                "pool": type(engine.pool).__name__,
                "admission_engine_id": id(engine),
                "predecessor_engine_id": id(fixture.case.engine),
            },
        )
        f.authority = RequestAuthority(engine)
        f.context = f.authority.named(f.principal, fixture.project, action="record").context
        f.intent = parse_submit(canonical(submission()))
        f.root, objects = root / "admission-journal", root / "admission-objects"
        f.root.mkdir(mode=0o700)
        objects.mkdir(mode=0o700)
        f.policy, f.ready = Policy(f), Ready(f)
        f.storage, f.journal = Storage(f, objects), AdmissionJournal(f.root)
        f.service = AdmissionCoordinator(
            engine,
            f.authority,
            policy=f.policy,
            readiness=f.ready,
            registry=NativeRegistry(f.config, ["fixture-image"]),
            storage=f.storage,
            journal=f.journal,
        )
        compatibility = predecessor_compatibility(f.service, record)
        # Only real predecessor admission uses the existing synthetic readiness adapter.
        with monkeypatch.context() as patch:
            patch.setattr(
                f.service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
            )
            accepted = f.service.submit(
                f.principal, f.context, f.intent, "7" * 64, OriginCorrelation("6" * 32)
            )
        assert len(f.storage.calls) == 3 and f.ready.calls == 1
        for descriptor in f.storage.calls:
            assert (
                hashlib.sha256(f.storage.local.read_verified(descriptor)).hexdigest()
                == descriptor.digest
            )
        assert engine is not fixture.case.engine and engine.pool.checkedout() == 0
        record(
            "admission_engine_return",
            {
                "admission_engine_id": id(engine),
                "predecessor_engine_id": id(fixture.case.engine),
                "checkedout": engine.pool.checkedout(),
            },
        )
        # A pooled idle backend must close before the unchanged all-session drain.
        engine.dispose()
        engine = None
        drain(pg)
        result = refreshed(fixture, pg)
        assert result.source != fixture.source and len(result.jobs) == len(fixture.jobs) + 1
        association = assert_admitted(
            result.before,
            accepted,
            project=result.project,
            principal=f.principal.principal_id,
            config_digest=f.config.digest,
            budget=f.intent.budget_microusd,
        )
        assert type(association["operation"]["accepted_response"]) is str
        for key in ("created_at", "retain_until"):
            value = association["operation"][key]
            assert type(value) is datetime and value.tzinfo is not None
        assert typed(result.before["tables"]["project_memberships"]) == typed(
            fixture.before["tables"]["project_memberships"]
        )
        assert typed(
            [row for row in rows(result.before, "jobs") if row["id"] != accepted["job_id"]]
        ) == typed(rows(fixture.before, "jobs"))
        assert encrypted_files(result) == fixture.encrypted
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
    finally:
        if engine is not None:
            engine.dispose()
            drain(pg)


def assert_typed_initialization(fixture, pg, manifest, receipt, after):
    accounts, _, _ = expected_stage(fixture, [manifest], [receipt], database_role=pg["owner_role"])
    expected = [
        {
            **row,
            "period_start": datetime.fromisoformat(row["period_start"].replace("Z", "+00:00")),
            "period_end": datetime.fromisoformat(row["period_end"].replace("Z", "+00:00")),
        }
        for row in accounts
    ]
    assert typed(sorted(rows(after, "budget_accounts"), key=lambda row: row["id"])) == typed(
        sorted(expected, key=lambda row: row["id"])
    )
    before = fixture.before
    assert typed(after["catalog"]) == typed(installed_profile("postgresql", LEDGER))
    assert typed(after["role"]) == typed(before["role"])
    assert typed(after["authority"]["schema"]) == typed(before["authority"]["schema"])
    for kind in ("relations", "functions"):
        width = 1 if kind == "relations" else 2
        current = {row[:width]: row for row in after["authority"][kind]}
        for row in before["authority"][kind]:
            assert typed(current[row[:width]]) == typed(row)
    for name, previous in before["tables"].items():
        if name not in {"jobs", "alembic_version", "installation_adoptions", "migration_progress"}:
            assert typed(after["tables"][name]) == typed(previous), name
    old_jobs = before["tables"]["jobs"]
    current = after["tables"]["jobs"]
    assert current["columns"] == (
        *old_jobs["columns"],
        "lease_generation",
        "legacy_reserved_microusd",
    )
    projected = {"columns": old_jobs["columns"], "rows": tuple(row[:-2] for row in current["rows"])}
    assert typed(projected) == typed(old_jobs)
    old = before["tables"]["migration_progress"]
    new = after["tables"]["migration_progress"]
    index = new["columns"].index("revision")
    assert typed(
        {
            "columns": new["columns"],
            "rows": tuple(row for row in new["rows"] if row[index] != LEDGER),
        }
    ) == typed(old)
    old = before["tables"]["installation_adoptions"]
    new = after["tables"]["installation_adoptions"]
    index = old["columns"].index("installed_schema_fingerprint")
    expected_rows = tuple(
        tuple(
            digest(installed_profile("postgresql", LEDGER)) if i == index else value
            for i, value in enumerate(row)
        )
        for row in old["rows"]
    )
    assert typed(new) == typed({"columns": old["columns"], "rows": expected_rows})
