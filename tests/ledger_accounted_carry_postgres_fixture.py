"""Fresh native admission and explicit synthetic settlement for accounted carry."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

from cryptography.fernet import Fernet
from ledger_accounted_carry_fixture import (
    CALL,
    SETTLEMENT,
    assert_stores,
    expected_settlement,
    replace_rows,
    settlement_rows,
)
from ledger_eligibility_fixture import file_hashes, rows
from ledger_eligibility_postgres_fixture import admitted_predecessor, refreshed
from ledger_overflow_postgres_fixture import raw_progress
from ledger_provisioning_fixture import expected_stage, identity
from ledger_provisioning_postgres_fixture import native_snapshot
from ledger_restore_authority import typed
from sqlalchemy import BigInteger, DateTime, bindparam, text
from test_admission_envelope import descriptor
from test_run_projection_postgres import drain

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.migrations.schema import LEDGER

MONEY_FIELDS = (
    "limit_microusd",
    "opening_held_microusd",
    "held_microusd",
    "accounted_microusd",
)


def native_time(value):
    assert type(value) is str
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert result.utcoffset() is not None
    return result.astimezone(UTC)


def canonical_time(value):
    assert type(value) is datetime and value.utcoffset() is not None
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def fresh_admitted(pg, root, monkeypatch, record):
    fixture, admission = admitted_predecessor(pg, root, monkeypatch, record, legacy=False)
    try:
        assert fixture.case.legacy is False and fixture.encrypted == {}
        assert admission.original_legacy_jobs == []
        assert admission.original_legacy_ciphertexts == {}
        (job,) = fixture.jobs
        assert type(job["budget"]) is type(job["reserved"]) is int
        assert job["budget"] == 1 and job["reserved"] == 0
        assert job["id"] == admission.accepted["job_id"]
        admission.object_hashes = admission.ciphertexts
        assert admission.object_hashes and admission.journal_hashes
        assert_stores(admission)
        record(
            "admission",
            {
                "association": typed(admission.association),
                "compatibility": admission.compatibility,
                "adapter": admission.adapter_scope,
                "legacy": False,
                "object_hashes": admission.object_hashes,
                "journal_hashes": admission.journal_hashes,
            },
        )
        return fixture, admission
    except BaseException:
        fixture.close()
        raise


def native_additions(fixture, first, evidence, observed, price):
    additions = settlement_rows(fixture, first, evidence, observed, price)
    for name in ("provider_calls", "budget_entries", "artifact_objects"):
        for row in additions[name]:
            row["created_at"] = native_time(row["created_at"])
    return additions


def assert_settlement(before, after, additions, job_id):
    for account in rows(before, "budget_accounts"):
        assert typed([account[field] for field in MONEY_FIELDS]) == typed([1, 0, 0, 0])
        canonical_time(account["period_start"])
        canonical_time(account["period_end"])
    (job,) = rows(before, "jobs")
    assert typed(
        [job["budget"], job["reserved"], job["legacy_reserved_microusd"], job["lease_generation"]]
    ) == typed([1, 0, 0, 0])
    for name in ("provider_calls", "budget_entries", "artifact_objects"):
        for row in additions[name]:
            canonical_time(row["created_at"])
    assert typed(after) == typed(expected_settlement(before, additions, job_id))


def settle_fixture(fixture, pg, admission, first, receipt, root, record):
    """Declared setup SQL and encrypted evidence; no provider or product settlement call."""
    before = native_snapshot(fixture.case, pg)
    progress = raw_progress(fixture, pg)
    root.mkdir(mode=0o700)
    storage = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    evidence = descriptor(SETTLEMENT, object_id=identity(7_000_000), project=fixture.project)
    written = storage.put_verified(evidence, SETTLEMENT)
    assert written.object == evidence and storage.read_verified(evidence) == SETTLEMENT
    additions = native_additions(
        fixture,
        first,
        evidence,
        receipt.initialized_at,
        json.loads(admission.config.canonical_bytes)["price_version"],
    )
    updates = []
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            owner = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert owner == (pg["owner_role"], pg["owner"].url.database)

            def execute(statement, values, expected=1):
                count = connection.execute(statement, values).rowcount
                updates.append(
                    {"sql": str(statement), "parameters": typed(values), "rowcount": count}
                )
                assert type(count) is int and count == expected

            for name in ("provider_calls", "resource_scopes"):
                for row in additions[name]:
                    statement = text(
                        f"INSERT INTO {name} ({','.join(row)}) "
                        f"VALUES ({','.join(':' + key for key in row)})"
                    )
                    if name == "provider_calls":
                        statement = statement.bindparams(
                            bindparam("created_at", type_=DateTime(timezone=True)),
                            bindparam("reserved_microusd", type_=BigInteger),
                        )
                    execute(statement, row)
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
                execute(
                    text(
                        f"INSERT INTO budget_entries ({','.join(row)}) "
                        f"VALUES ({','.join(':' + key for key in row)})"
                    ).bindparams(
                        bindparam("created_at", type_=DateTime(timezone=True)),
                        bindparam("amount_microusd", type_=BigInteger),
                    ),
                    row,
                )
            execute(
                text("UPDATE budget_accounts SET accounted_microusd=:amount").bindparams(
                    bindparam("amount", type_=BigInteger)
                ),
                {"amount": 1},
                expected=3,
            )
            execute(
                text(
                    "UPDATE jobs SET status='running',owner='synthetic-worker',"
                    "lease_until=1900000000,lease_generation=2,reserved=:amount WHERE id=:id"
                ).bindparams(bindparam("amount", type_=BigInteger)),
                {"amount": 1, "id": fixture.jobs[0]["id"]},
            )
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        acknowledged = True
    finally:
        drain(pg)
    result = refreshed(fixture, pg)
    assert_settlement(before, result.before, additions, fixture.jobs[0]["id"])
    assert result.source != fixture.source
    after_progress = raw_progress(result, pg)
    assert typed(after_progress) == typed(progress)
    settlement = SimpleNamespace(
        root=root,
        storage=storage,
        descriptor=evidence,
        hashes=file_hashes(root),
        additions=additions,
    )
    assert settlement.hashes
    assert_stores(admission, settlement)
    record(
        "settlement_setup",
        {
            "synthetic": True,
            "identity": owner,
            "commit_acknowledged": acknowledged,
            "constraints_immediate": True,
            "updates": updates,
            "additions": typed(additions),
            "before": typed(before),
            "after": typed(result.before),
            "raw_progress_before": progress,
            "raw_progress_after": after_progress,
        },
    )
    record("settlement_ciphertexts", settlement.hashes)
    return result, settlement


def progress_row(phase, value):
    cursor, count, source = value
    return {
        "revision": LEDGER,
        "phase": phase,
        "source_digest": source,
        "cursor": deepcopy(cursor),
        "rows_verified": count,
        "status": "complete",
        "updated_at": native_time(cursor["initialized_at"]),
    }


def expected_final(frozen, first, initial, settled, second, written, role):
    """Retain native settled rows; derive opening only from the frozen queued-zero job."""
    assert type(role) is str and role
    assert len(frozen.jobs) == 1
    assert typed(frozen.jobs[0]["reserved"]) == typed(0)
    assert typed([a["limit_microusd"] for a in first["accounts"]]) == typed([1, 1, 1])
    assert typed([a["limit_microusd"] for a in second["accounts"]]) == typed([0, 0])
    assert typed(initial.imported_jobs) == typed(1)
    assert typed(initial.imported_opening_microusd) == typed(0)
    for receipt in (initial, written):
        for name in ("sequence", "account_rows", "imported_jobs", "imported_opening_microusd"):
            assert type(getattr(receipt, name)) is int
    accounts, progress, state = expected_stage(
        frozen, [first, second], [initial, written], database_role=role
    )
    old_ids = {a["id"] for a in first["accounts"]}
    native = [
        {
            **account,
            "period_start": native_time(account["period_start"]),
            "period_end": native_time(account["period_end"]),
            "accounted_microusd": int(account["id"] in old_ids),
        }
        for account in accounts
    ]
    previous = sorted(rows(settled, "budget_accounts"), key=lambda row: row["id"])
    assert typed(previous) == typed(
        sorted([row for row in native if row["id"] in old_ids], key=lambda row: row["id"])
    )
    expected = deepcopy(settled)
    replace_rows(expected, "budget_accounts", native)
    old_progress = rows(settled, "migration_progress")
    phase = "ledger_manifest_" + second["manifest_id"]
    old_ledger = [row for row in old_progress if row["revision"] == LEDGER]
    assert {row["phase"] for row in old_ledger} == set(progress) - {phase}
    assert len(old_ledger) == 2
    for row in old_ledger:
        assert typed(row) == typed(progress_row(row["phase"], progress[row["phase"]]))
    replace_rows(
        expected, "migration_progress", old_progress + [progress_row(phase, progress[phase])]
    )
    return expected, state


def assert_raw_progress(before, after, phase):
    previous = {(row["revision"], row["phase"]): row for row in before}
    current = {(row["revision"], row["phase"]): row for row in after}
    assert len(previous) == len(before) and len(current) == len(after)
    assert set(current) == set(previous) | {(LEDGER, phase)}
    assert (LEDGER, phase) not in previous
    assert all(type(row["raw_cursor"]) is str for row in after)
    for key, row in previous.items():
        assert typed(current[key]) == typed(row)
