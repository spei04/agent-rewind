"""Fresh real admission and declared synthetic settlement; no seeded ledger history."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from cryptography.fernet import Fernet
from ledger_eligibility_fixture import (
    admission_engine,
    assert_admitted,
    file_hashes,
    predecessor_compatibility,
    refreshed,
    rows,
)
from ledger_provisioning_fixture import (
    build_case,
    identity,
    initial_manifest,
    next_manifest,
    snapshot,
)
from sqlalchemy import text
from test_admission_configuration import configuration
from test_admission_envelope import descriptor
from test_admission_request import submission
from test_admission_submit import Policy, Ready, Storage
from test_ownership import FRESH

from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_coordinator import AdmissionCoordinator
from agent_rewind.admission_envelope import OriginCorrelation
from agent_rewind.admission_journal import AdmissionJournal
from agent_rewind.admission_request import parse_submit
from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.compatibility import CompatibilityResult
from agent_rewind.models import canonical
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal

CALL = identity(3_000_000)
SETTLEMENT = b"synthetic accounted-only carry settlement; one economic microusd"


def initial_carry_manifest(fixture):
    result = initial_manifest(fixture)
    assert len(result["accounts"]) == 3 and len(fixture.jobs) == 1
    assert fixture.jobs[0]["budget"] == 1 and fixture.jobs[0]["reserved"] == 0
    for account in result["accounts"]:
        account["limit_microusd"] = 1
    return result


def future_carry_manifest(first, source):
    result = next_manifest(first)
    result["source_digest"] = source
    for account in result["accounts"]:
        account["limit_microusd"] = 0
    return result


def fresh_admitted(path, monkeypatch, record):
    """Real coordinator/publication with the existing explicit fixture policy adapter."""
    fixture = build_case(path, legacy=False)
    engine = None
    try:
        engine = admission_engine(fixture)
        f = SimpleNamespace(engine=engine, config=configuration())
        (grant,) = FRESH["principal_grants"]
        (member,) = rows(fixture.before, "project_memberships")
        assert member == {
            **grant,
            "project_id": fixture.project,
            "legacy_default": 1,
            "revoked_at": None,
        }
        assert fixture.organization == FRESH["organization_id"]
        assert fixture.project == FRESH["project_id"]
        f.principal = VerifiedPrincipal(grant["principal_id"])
        record("fresh_admission_authority", {"grant": grant, "membership": member})
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            f.name = connection.execute(
                text("SELECT name FROM projects WHERE id=:p"), {"p": fixture.project}
            ).scalar_one()
            record(
                "admission_fk",
                {"enabled": 1, "raw_id": id(connection.connection.driver_connection)},
            )
        f.authority = RequestAuthority(engine)
        f.context = f.authority.named(f.principal, fixture.project, action="record").context
        f.intent = parse_submit(canonical(submission()))
        f.root = path.parent / "admission-journal"
        objects = path.parent / "admission-objects"
        f.root.mkdir(mode=0o700)
        objects.mkdir(mode=0o700)
        f.policy, f.ready = Policy(f), Ready(f)
        f.storage, f.journal = Storage(f, objects), AdmissionJournal(f.root)
        service = AdmissionCoordinator(
            engine,
            f.authority,
            policy=f.policy,
            readiness=f.ready,
            registry=NativeRegistry(f.config, ["fixture-image"]),
            storage=f.storage,
            journal=f.journal,
        )
        compatibility = predecessor_compatibility(service, record)
        with monkeypatch.context() as patch:
            patch.setattr(
                service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
            )
            accepted = service.submit(
                f.principal, f.context, f.intent, "7" * 64, OriginCorrelation("6" * 32)
            )
        assert len(f.storage.calls) == 3 and f.ready.calls == 1
        result = refreshed(fixture)
        assert len(result.jobs) == 1 and result.source != fixture.source
        assert (
            result.before["tables"]["project_memberships"]
            == fixture.before["tables"]["project_memberships"]
        )
        association = assert_admitted(
            result.before,
            accepted,
            project=result.project,
            principal=f.principal.principal_id,
            config_digest=f.config.digest,
            budget=1,
        )
        bundle = SimpleNamespace(
            accepted=accepted,
            association=association,
            config=f.config,
            storage=f.storage.local,
            descriptors=tuple(f.storage.calls),
            objects=objects,
            journal=f.root,
            object_hashes=file_hashes(objects),
            journal_hashes=file_hashes(f.root),
        )
        assert bundle.object_hashes and bundle.journal_hashes
        assert_stores(bundle)
        record(
            "admission",
            {
                "association": association,
                "compatibility": asdict(compatibility),
                "object_hashes": bundle.object_hashes,
                "journal_hashes": bundle.journal_hashes,
                "adapter": "Synthetic policy/readiness/schema; "
                "real coordinator and encrypted publication",
            },
        )
        return result, bundle
    except BaseException:
        fixture.close()
        raise
    finally:
        if engine is not None:
            try:
                record("admission_pool_return", {"checkedout": engine.pool.checkedout()})
                assert engine.pool.checkedout() == 0
            finally:
                engine.dispose()


def assert_stores(admission, settlement=None):
    assert file_hashes(admission.objects) == admission.object_hashes
    assert file_hashes(admission.journal) == admission.journal_hashes
    for value in admission.descriptors:
        content = admission.storage.read_verified(value)
        assert len(content) == value.byte_count
        assert hashlib.sha256(content).hexdigest() == value.digest
    if settlement is not None:
        assert file_hashes(settlement.root) == settlement.hashes
        assert settlement.storage.read_verified(settlement.descriptor) == SETTLEMENT
        assert hashlib.sha256(SETTLEMENT).hexdigest() == settlement.descriptor.digest


def replace_rows(state, table, values):
    columns = state["tables"][table]["columns"]
    assert all(set(row) == set(columns) for row in values)
    state["tables"][table]["rows"] = tuple(
        sorted((tuple(row[column] for column in columns) for row in values), key=repr)
    )


def settlement_rows(fixture, first, evidence, observed, price):
    triple = [account["id"] for account in first["accounts"]]
    assert [account["scope"] for account in first["accounts"]] == ["organization", "project", "job"]
    job = fixture.jobs[0]["id"]
    call = {
        "id": CALL,
        "project_id": fixture.project,
        "job_id": job,
        "logical_call_id": identity(6_000_000),
        "purpose": "continuation",
        "request_digest": "a" * 64,
        "price_version": price,
        "state": "reconciled",
        "reserved_microusd": 1,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": observed,
        "organization_id": fixture.organization,
        "job_resource_kind": "job",
        "lease_generation": 1,
        "organization_account_id": triple[0],
        "project_account_id": triple[1],
        "job_account_id": triple[2],
    }
    entries = [
        {
            "call_id": CALL,
            "account_id": account,
            "entry_kind": kind,
            "amount_microusd": 1,
            "created_at": observed,
            "project_id": fixture.project,
            "evidence_ref": evidence.id if kind == "settle" else None,
            "evidence_owner_kind": "provider_call",
            "evidence_role": "budget_evidence",
        }
        for kind in ("reserve", "settle")
        for account in triple
    ]
    return {
        "provider_calls": [call],
        "budget_entries": entries,
        "resource_scopes": [
            {"resource_kind": "provider_call", "resource_id": CALL, "project_id": fixture.project}
        ],
        "artifact_objects": [{**asdict(evidence), "created_at": evidence.created_at.isoformat()}],
        "artifact_refs": [
            {
                "project_id": fixture.project,
                "owner_kind": "provider_call",
                "owner_id": CALL,
                "role": "budget_evidence",
                "artifact_id": evidence.id,
            }
        ],
    }


def expected_settlement(before, additions, job_id):
    expected = deepcopy(before)
    for table, values in additions.items():
        replace_rows(expected, table, rows(before, table) + values)
    jobs = rows(before, "jobs")
    assert len(jobs) == 1 and jobs[0]["id"] == job_id
    assert jobs[0]["legacy_reserved_microusd"] == jobs[0]["reserved"] == 0
    replace_rows(
        expected,
        "jobs",
        [
            {
                **jobs[0],
                "status": "running",
                "owner": "synthetic-worker",
                "lease_until": 1900000000.0,
                "lease_generation": 2,
                "reserved": 1,
            }
        ],
    )
    accounts = rows(before, "budget_accounts")
    assert len(accounts) == 3
    assert all(
        (
            a["limit_microusd"],
            a["opening_held_microusd"],
            a["held_microusd"],
            a["accounted_microusd"],
        )
        == (1, 0, 0, 0)
        for a in accounts
    )
    replace_rows(expected, "budget_accounts", [{**a, "accounted_microusd": 1} for a in accounts])
    return expected


def settle_fixture(fixture, admission, first, receipt, record):
    """Explicit fixture SQL, not execution of a production reservation/settlement."""
    before = snapshot(fixture.case.path)
    root = fixture.case.path.parent / "settlement-objects"
    root.mkdir(mode=0o700)
    storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    evidence = descriptor(SETTLEMENT, object_id=identity(7_000_000), project=fixture.project)
    written = storage.put_verified(evidence, SETTLEMENT)
    assert written.object == evidence and storage.read_verified(evidence) == SETTLEMENT
    additions = settlement_rows(
        fixture,
        first,
        evidence,
        receipt.initialized_at,
        json.loads(admission.config.canonical_bytes)["price_version"],
    )
    engine = admission_engine(fixture)
    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            for table in ("provider_calls", "resource_scopes"):
                for row in additions[table]:
                    connection.execute(
                        text(
                            f"INSERT INTO {table} ({','.join(row)}) "
                            f"VALUES ({','.join(':' + key for key in row)})"
                        ),
                        row,
                    )
            record_verified(connection, evidence)
            register_ref(
                connection,
                project_id=fixture.project,
                owner_kind="provider_call",
                owner_id=CALL,
                role="budget_evidence",
                artifact_id=evidence.id,
            )
            for row in additions["budget_entries"]:
                connection.execute(
                    text(
                        f"INSERT INTO budget_entries ({','.join(row)}) "
                        f"VALUES ({','.join(':' + key for key in row)})"
                    ),
                    row,
                )
            assert (
                connection.exec_driver_sql(
                    "UPDATE budget_accounts SET accounted_microusd=1"
                ).rowcount
                == 3
            )
            assert (
                connection.exec_driver_sql(
                    "UPDATE jobs SET status='running',owner='synthetic-worker',"
                    "lease_until=1900000000,lease_generation=2,reserved=1 WHERE id=?",
                    (fixture.jobs[0]["id"],),
                ).rowcount
                == 1
            )
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert engine.pool.checkedout() == 0
        record(
            "settlement_setup",
            {
                "synthetic": True,
                "additions": additions,
                "fk_enabled": 1,
                "fk_violations": [],
                "checkedout": 0,
                "expected": expected_settlement(before, additions, fixture.jobs[0]["id"]),
            },
        )
    finally:
        engine.dispose()
    result = refreshed(fixture)
    assert result.before == expected_settlement(before, additions, fixture.jobs[0]["id"])
    assert result.source != fixture.source
    settlement = SimpleNamespace(
        root=root,
        storage=storage,
        descriptor=evidence,
        hashes=file_hashes(root),
        additions=additions,
    )
    assert settlement.hashes
    assert_stores(admission, settlement)
    record("settlement_ciphertexts", settlement.hashes)
    return result, settlement
