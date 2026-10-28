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
