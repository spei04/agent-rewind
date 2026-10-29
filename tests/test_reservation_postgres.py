"""One complete native P2 path; no provider or live adapter activation."""

import json
from dataclasses import asdict
from datetime import datetime

import pytest
import test_migrations_postgres as migrations
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import assert_job_change
from ledger_restore_authority import typed
from reservation_postgres_fixture import (
    build_postgres_reservation_case,
    with_postgres_service_key,
)
from sqlalchemy import event

from agent_rewind import reservation_rows
from agent_rewind.migrations import ledger_compatibility
from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ClaimIntent, CreatedReservation, ReservationIntent

pg = migrations.pg
__all__ = ["pg"]
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL reservation components"
)


def _complete_claim_and_reserve(pg, tmp_path, monkeypatch, record_property, *, service_key=False):
    def record(name, value):
        record_property(name, json.dumps(typed(value), allow_nan=False))

    case = build_postgres_reservation_case(
        pg, tmp_path, monkeypatch, record=lambda name, value: record("setup_" + name, value)
    )
    if service_key:
        case = with_postgres_service_key(case)
    record("principal_kind", "synthetic-service-key" if service_key else "original-owner")
    queries = []
    stages = []
    mode = ["setup"]
    catalog_parameters = []
    catalog_checks = []
    in_catalog = [False]

    def observe(_connection, _cursor, statement, parameters, *_args):
        queries.append((mode[0], statement))
        if in_catalog[0]:
            catalog_parameters.append(len(parameters))
            assert len(parameters) <= 16

    def staged(name, original):
        def observed(connection, *args):
            work = args[-1]
            start = work.statements
            try:
                return original(connection, *args)
            finally:
                stages.append((mode[0], name, start, work.statements))

        return observed

    def report(owner, label):
        work = owner._work
        record(label + "_outcome", asdict(owner.outcome))
        if work is not None:
            record(
                label + "_work",
                {
                    "units": work.statements,
                    "seconds": work.seconds,
                    "vm_instructions": work.instructions,
                    "sql": [sql for phase, sql in queries if phase == label],
                    "stages": [stage for stage in stages if stage[0] == label],
                },
            )

    event.listen(case.engine, "before_cursor_execute", observe)
    try:
        record("setup", case.setup_events)
        before = case.snapshot()
        record("before", before)
        original_catalog = ledger_compatibility.inspect_catalog

        def compare_catalog(connection, revision, work):
            start = len(catalog_parameters)
            in_catalog[0] = True
            try:
                actual = original_catalog(connection, revision, work)
            finally:
                in_catalog[0] = False
            # The retained observer uses independent schema.catalog, including
            # every physical/executable field, not the optimized reader.
            assert typed(actual) == typed(before["catalog"])
            observed = catalog_parameters[start:]
            catalog_checks.append((mode[0], len(observed), max(observed)))
            record("catalog_equivalence", catalog_checks)
            return actual

        monkeypatch.setattr(ledger_compatibility, "inspect_catalog", compare_catalog)
        for name in (
            "validated_ar7_history",
            "read_financial_projection",
            "read_source_bounds",
        ):
            monkeypatch.setattr(
                reservation_rows, name, staged(name, getattr(reservation_rows, name))
            )
        claim = ReservationCoordinator(case.engine, case.authority)
        mode[0] = "claim"
        try:
            fence = claim.claim_generation(
                case.principal, case.context, ClaimIntent(case.job_id, "a" * 32, 0, 60)
            )
        finally:
            report(claim, "claim")
        assert claim.outcome.commit_acknowledged and not claim.outcome.cleanup_failed
        assert claim._work.statements <= 512 and claim._work.seconds < 10
        mode[0] = "observation"
        claimed = case.snapshot()
        job = next(row for row in rows(claimed, "jobs") if row["id"] == case.job_id)
        assert_job_change(
            before,
            claimed,
            case.job_id,
            {
                "owner": fence.owner_uuid,
                "status": "running",
                "lease_generation": fence.generation,
                "lease_until": job["lease_until"],
            },
        )
        assert fence.generation == 1 and type(job["lease_until"]) is float
        record("claimed", claimed)
        intent = ReservationIntent(
            call_id="b" * 32,
            project_id=case.project_id,
            job_id=case.job_id,
            logical_call_id="c" * 32,
            request_digest="d" * 64,
            purpose="continuation",
            price_version=case.price_version,
            reserved_microusd=12345,
            lease_generation=fence.generation,
            organization_account_id=case.account_ids[0],
            project_account_id=case.account_ids[1],
            job_account_id=case.account_ids[2],
        )
        owner = ReservationCoordinator(case.engine, case.authority)
        mode[0] = "reserve"
        try:
            result = owner.reserve(case.principal, case.context, fence, intent)
        except BaseException as error:
            # Preserve the original failed attempt and traceback. Observe the
            # whole database while it still exists, after coordinator cleanup.
            record(
                "reserve_original_failure",
                {
                    "type": type(error).__module__ + "." + type(error).__qualname__,
                    "code": getattr(error, "code", None),
                    "reason": getattr(error, "reason", None),
                },
            )
            mode[0] = "observation"
            try:
                failed_after = case.snapshot()
                record("reserve_failed_after", failed_after)
                record("reserve_failure_whole_state_equal", typed(failed_after) == typed(claimed))
            except BaseException as diagnostic_error:
                # A snapshot failure cannot replace the original exception.
                record(
                    "reserve_failure_snapshot_error",
                    type(diagnostic_error).__module__ + "." + type(diagnostic_error).__qualname__,
                )
            raise
        finally:
            report(owner, "reserve")
        assert isinstance(result, CreatedReservation) and result.record.identity == intent
        assert owner.outcome.commit_acknowledged and not owner.outcome.cleanup_failed
        assert owner._work.statements <= 512 and owner._work.seconds < 10
        mode[0] = "observation"
        after = case.snapshot()
        record("after", after)
        for key in ("catalog", "authority", "role"):
            assert typed(after[key]) == typed(claimed[key])
        changed = {"jobs", "provider_calls", "resource_scopes", "budget_accounts", "budget_entries"}
        for name in set(after["tables"]) - changed:
            assert typed(after["tables"][name]) == typed(claimed["tables"][name]), name
        (call,) = rows(after, "provider_calls")
        assert call["id"] == intent.call_id and call["job_id"] == case.job_id
        assert call["reserved_microusd"] == 12345 and call["state"] == "reserved"
        assert type(call["created_at"]) is datetime and call["created_at"].tzinfo is not None
        entries = rows(after, "budget_entries")
        assert len(entries) == 3 and {row["account_id"] for row in entries} == set(case.account_ids)
        assert all(
            row["call_id"] == intent.call_id
            and row["entry_kind"] == "reserve"
            and row["amount_microusd"] == 12345
            and row["evidence_ref"] is None
            and row["created_at"] == call["created_at"]
            for row in entries
        )
        assert (
            next(row for row in rows(after, "jobs") if row["id"] == case.job_id)["reserved"]
            == 12345
        )
        assert all(
            row["held_microusd"] == 12345 and row["accounted_microusd"] == 0
            for row in rows(after, "budget_accounts")
        )
        assert [row[0] for row in catalog_checks] == ["claim", "reserve"]
        assert case.engine.pool.checkedout() == 0
    finally:
        event.remove(case.engine, "before_cursor_execute", observe)
        case.close()


def test_postgres_complete_claim_and_reserve_keep_native_work_bounds(
    pg, tmp_path, monkeypatch, record_property
):
    _complete_claim_and_reserve(pg, tmp_path, monkeypatch, record_property)


def test_postgres_service_key_claim_and_reserve_keep_native_work_bounds(
    pg, tmp_path, monkeypatch, record_property
):
    _complete_claim_and_reserve(pg, tmp_path, monkeypatch, record_property, service_key=True)


def test_postgres_second_project_has_real_admission_and_accounts(
    pg, tmp_path, monkeypatch, record_property
):
    from ledger_provisioning_fixture import identity
    from ledger_provisioning_postgres_fixture import inspect
    from reservation_postgres_fixture import (
        offline_postgres_ledger,
        with_postgres_second_project,
    )

    def record(name, value):
        record_property(name, json.dumps(typed(value), allow_nan=False))

    first = build_postgres_reservation_case(
        pg, tmp_path, monkeypatch, account_limit=10, record=record
    )
    try:
        before = first.snapshot()
        second = with_postgres_second_project(first, tmp_path, monkeypatch, record)
        after = second.snapshot()
        record("before", before)
        record("after", after)
        assert first.engine is second.engine and first.case is second.case
        assert first.project_id != second.project_id and first.job_id != second.job_id
        assert first.organization_id == second.organization_id
        assert first.account_ids[0] == second.account_ids[0]
        assert first.principal is second.principal
        assert second.admission.compatibility["code"] == "migration_only"
        assert first.admission.objects != second.admission.objects
        assert first.admission.journal != second.admission.journal
        assert first.admission.ciphertexts and second.admission.ciphertexts
        original_accounts = {row["id"]: row for row in rows(before, "budget_accounts")}
        current_accounts = {row["id"]: row for row in rows(after, "budget_accounts")}
        assert set(current_accounts) == set(original_accounts) | {identity(9001), identity(9002)}
        assert all(
            typed(current_accounts[key]) == typed(value) for key, value in original_accounts.items()
        )
        assert current_accounts[identity(9001)]["limit_microusd"] == 10
        assert (
            current_accounts[identity(9002)]["limit_microusd"]
            == first.admission.association["job"]["budget"]
        )
        for account_id in (identity(9001), identity(9002)):
            account = current_accounts[account_id]
            assert account["project_id"] == second.project_id
            assert all(
                account[name] == 0
                for name in ("held_microusd", "opening_held_microusd", "accounted_microusd")
            )
        old_jobs = {row["id"]: row for row in rows(before, "jobs")}
        new_jobs = {row["id"]: row for row in rows(after, "jobs")}
        assert all(typed(new_jobs[key]) == typed(value) for key, value in old_jobs.items())
        assert set(new_jobs) == set(old_jobs) | {second.job_id}
        assert new_jobs[second.job_id]["payload_version"] == 2
        assert new_jobs[second.job_id]["status"] == "queued"
        assert new_jobs[second.job_id]["reserved"] == 0
        assert len(rows(after, "organizations")) == 1
        assert len(rows(after, "projects")) == 2
        assert typed(before["catalog"]) == typed(after["catalog"])
        assert typed(before["authority"]) == typed(after["authority"])
        with offline_postgres_ledger(second, record):
            observed = inspect(second.provisioning, pg)
        record("inspection", observed.model_dump(mode="json"))
        assert observed.account_count == 5 and observed.manifest_count == 2
        failure_before = second.snapshot()
        original_error = RuntimeError("synthetic offline operator body failure")
        with pytest.raises(RuntimeError) as caught, offline_postgres_ledger(second, record):
            raise original_error
        assert caught.value is original_error
        failure_after = second.snapshot()
        assert typed(failure_after) == typed(failure_before)
        record(
            "offline_body_failure",
            {
                "original_exception_identity": caught.value is original_error,
                "before": failure_before,
                "after": failure_after,
            },
        )
        assert first.engine.pool.checkedout() == 0
    finally:
        first.close()
