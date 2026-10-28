"""Actual P1/P2 period composition with explicit deterministic clock samples.

Returned boundary times are synthetic; every original native clock query still
runs and consumes its original work. No elapsed-time rollover claim is made.
"""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

from cryptography.fernet import Fernet
from ledger_eligibility_fixture import file_hashes, refreshed
from ledger_provisioning_fixture import digest, invoke
from reservation_qe_fixture import (
    assert_reservation,
    claim,
    coordinator,
    identity,
    intent,
    one,
    rows,
    same,
    snapshot,
)
from sqlalchemy import text
from test_admission_envelope import descriptor

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.sqlite_ownership import owned_begin


def synthetic_settlement(case, value):
    """Retained synthetic state/evidence only, never a settlement API invocation."""
    before = snapshot(case.engine)
    expected = deepcopy(before)
    content = b"synthetic retained P2 period accounting observation"
    root = case.case.path.parent / "period-synthetic-evidence"
    root.mkdir(mode=0o700)
    storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    proof = descriptor(content, object_id=identity(130001), project=case.project_id)
    stored = storage.put_verified(proof, content)
    assert stored.object == proof and storage.read_verified(proof) == content
    one(expected, "provider_calls", id=value.call_id)["state"] = "reconciled"
    additions = [
        {**row, "entry_kind": "settle", "evidence_ref": proof.id}
        for row in rows(before, "budget_entries")
        if row["call_id"] == value.call_id
    ]
    assert len(additions) == 3
    rows(expected, "budget_entries").extend(additions)
    for account_id in (
        value.organization_account_id,
        value.project_account_id,
        value.job_account_id,
    ):
        account = one(expected, "budget_accounts", id=account_id)
        account["held_microusd"] -= value.reserved_microusd
        account["accounted_microusd"] += value.reserved_microusd
    rows(expected, "artifact_objects").append(
        {
            "id": proof.id,
            "project_id": proof.project_id,
            "digest": proof.digest,
            "locator": proof.locator,
            "format_version": proof.format_version,
            "byte_count": proof.byte_count,
            "created_at": proof.created_at.astimezone(UTC).isoformat(),
        }
    )
    rows(expected, "artifact_refs").append(
        {
            "project_id": case.project_id,
            "owner_kind": "provider_call",
            "owner_id": value.call_id,
            "artifact_id": proof.id,
            "role": "budget_evidence",
        }
    )
    with owned_begin(case.engine) as connection:
        record_verified(connection, proof)
        register_ref(
            connection,
            project_id=case.project_id,
            owner_kind="provider_call",
            owner_id=value.call_id,
            role="budget_evidence",
            artifact_id=proof.id,
        )
        for row in additions:
            connection.execute(
                text(
                    "INSERT INTO budget_entries("
                    + ",".join(row)
                    + ") VALUES("
                    + ",".join(":" + key for key in row)
                    + ")"
                ),
                row,
            )
            connection.execute(
                text(
                    "UPDATE budget_accounts SET held_microusd=held_microusd-:amount,"
                    "accounted_microusd=accounted_microusd+:amount WHERE id=:id"
                ),
                {"amount": value.reserved_microusd, "id": row["account_id"]},
            )
        connection.execute(
            text("UPDATE provider_calls SET state='reconciled' WHERE id=:id"), {"id": value.call_id}
        )
    same(expected, snapshot(case.engine))
    return SimpleNamespace(
        storage=storage, descriptor=proof, content=content, root=root, hashes=file_hashes(root)
    )


def build_period_case(tmp_path, monkeypatch, *, stage):
    import reservation_fixture as shared

    from agent_rewind import reservation

    assert stage in {"reserved", "rolled-held", "rolled-accounted"}
    boundary = int(datetime(2030, 1, 1, tzinfo=UTC).timestamp()) * 1_000_000
    original_manifest = shared.initial_manifest

    def initial(fixture):
        result = original_manifest(fixture)
        for account in result["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["period_end"] = "2030-01-01T00:00:00.000000Z"
        return result

    with monkeypatch.context() as setup:
        setup.setattr(shared, "initial_manifest", initial)
        case = shared.build_reservation_case(tmp_path, setup, account_limit=10)
    try:
        original_clock = reservation._clock
        phase = {"now": boundary - 20_000_000}
        samples = []

        def clock(connection):
            native = original_clock(connection)
            assert type(native) is int and native % 1000 == 0
            samples.append((native, phase["now"]))
            return phase["now"]

        monkeypatch.setattr(reservation, "_clock", clock)
        fence = claim(case)
        before = snapshot(case.engine)
        original = intent(case, fence, amount=7, number=130100)
        saved = coordinator(case).reserve(case.principal, case.context, fence, original)
        assert saved.kind == "created"
        assert_reservation(before, snapshot(case.engine), original, case.organization_id)
        manifests = [case.admission.manifest]
        receipts = [case.admission.initialization_receipt]
        evidence = synthetic_settlement(case, original) if stage == "rolled-accounted" else None
        if stage != "reserved":
            fixture = refreshed(case.provisioning)
            first = case.admission.manifest
            accounts = [
                {
                    **account,
                    "id": identity(130200 + number),
                    "period_start": "2030-01-01T00:00:00.000000Z",
                    "period_end": "2100-01-01T00:00:00.000000Z",
                }
                for number, account in enumerate(first["accounts"])
                if account["scope"] in {"organization", "project"}
            ]
            provision = {
                **first,
                "manifest_id": identity(1302010),
                "operation": "provision",
                "source_digest": fixture.source,
                "parent_manifest_digest": digest(first),
                "opening_accounts": None,
                "accounts": accounts,
            }
            before_provision = snapshot(case.engine)
            receipt = invoke(fixture, provision)
            after_provision = snapshot(case.engine)
            assert receipt.sequence == 1 and receipt.account_rows == 2
            assert rows(before_provision, "jobs") == rows(after_provision, "jobs")
            assert rows(before_provision, "provider_calls") == rows(
                after_provision, "provider_calls"
            )
            assert rows(before_provision, "budget_entries") == rows(
                after_provision, "budget_entries"
            )
            for account in rows(before_provision, "budget_accounts"):
                assert one(after_provision, "budget_accounts", id=account["id"]) == account
            case.account_ids = (accounts[0]["id"], accounts[1]["id"], case.account_ids[2])
            for account_id in case.account_ids[:2]:
                selected = one(after_provision, "budget_accounts", id=account_id)
                assert selected["held_microusd"] == selected["accounted_microusd"] == 0
                assert selected["limit_microusd"] == 10
            manifests.append(provision)
            receipts.append(receipt)
            phase["now"] = boundary + 1_000
        return SimpleNamespace(
            case=case,
            fence=fence,
            original=original,
            saved=saved,
            manifests=manifests,
            receipts=receipts,
            evidence=evidence,
            samples=samples,
            phase=phase,
            boundary=boundary,
        )
    except BaseException:
        case.close()
        raise
