"""Whole-state paid-transition expectations independent of the successor writers."""

import json
import time
from contextlib import contextmanager
from copy import deepcopy

from ledger_restore_authority import typed
from operation_failure_service_oracle import one
from sqlalchemy import event
from test_failure_persistence_native_oracle import assert_same_state, observe_controls, utc_micros

from agent_rewind.reservation_types import ClaimIntent, ReservationIntent


def claim_intent(case):
    return ClaimIntent(case.job_id, "a" * 32, 0, 60)


def reservation_intent(case, fence, *, amount=7, number=980001):
    organization, project, job = case.account_ids
    return ReservationIntent(
        call_id=f"{number:032x}",
        project_id=case.project_id,
        job_id=case.job_id,
        logical_call_id=f"{number + 10000:032x}",
        request_digest="b" * 64,
        purpose="continuation",
        price_version=case.price_version,
        reserved_microusd=amount,
        lease_generation=fence.generation,
        organization_account_id=organization,
        project_account_id=project,
        job_account_id=job,
    )


def assert_reservation_delta(case, before, after, intent, clock_bounds):
    expected = deepcopy(before)
    calls = [
        row for row in after["tables"]["provider_calls"]["rows"] if row["id"] == intent.call_id
    ]
    assert len(calls) == 1
    created = calls[0]["created_at"]
    assert clock_bounds[0] <= utc_micros(created) <= clock_bounds[1]
    call = {
        "id": intent.call_id,
        "project_id": case.project_id,
        "job_id": case.job_id,
        "logical_call_id": intent.logical_call_id,
        "purpose": "continuation",
        "request_digest": intent.request_digest,
        "price_version": case.price_version,
        "state": "reserved",
        "reserved_microusd": intent.reserved_microusd,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": created,
        "organization_id": case.organization_id,
        "job_resource_kind": "job",
        "lease_generation": intent.lease_generation,
        "organization_account_id": intent.organization_account_id,
        "project_account_id": intent.project_account_id,
        "job_account_id": intent.job_account_id,
    }
    assert typed(calls[0]) == typed(call)
    expected["tables"]["provider_calls"]["rows"].append(call)
    expected["tables"]["resource_scopes"]["rows"].append(
        {
            "resource_kind": "provider_call",
            "resource_id": intent.call_id,
            "project_id": case.project_id,
        }
    )
    for account_id in case.account_ids:
        expected["tables"]["budget_entries"]["rows"].append(
            {
                "call_id": intent.call_id,
                "account_id": account_id,
                "entry_kind": "reserve",
                "amount_microusd": intent.reserved_microusd,
                "evidence_ref": None,
                "created_at": created,
                "project_id": case.project_id,
                "evidence_owner_kind": "provider_call",
                "evidence_role": "budget_evidence",
            }
        )
        account = one(expected, "budget_accounts", id=account_id)
        assert type(account["held_microusd"]) is int
        account["held_microusd"] += intent.reserved_microusd
    job = one(expected, "jobs", id=case.job_id)
    assert type(job["reserved"]) is int
    job["reserved"] += intent.reserved_microusd
    for table in expected["tables"].values():
        table["rows"].sort(key=lambda row: repr(typed(row)))
    assert_same_state(expected, after)


@contextmanager
def observe_paid(case, monkeypatch, record_property, coordinator):
    """Forward-only Work and SQL evidence around one actual coordinator invocation."""
    statements = []
    with monkeypatch.context() as patch:
        controls = observe_controls(patch)

        def statement(_connection, _cursor, sql, _parameters, context, _many):
            statements.append(
                (sql, len(context.compiled.params or {}) if context.compiled is not None else 0)
            )

        event.listen(case.engine, "before_cursor_execute", statement)
        started = time.monotonic()
        try:
            yield statements
        finally:
            elapsed = time.monotonic() - started
            event.remove(case.engine, "before_cursor_execute", statement)
            work = coordinator._work
            assert work is not None
            cleanup = sum(
                after - before
                for target, kind, before, after in controls
                if target is work and kind not in {"begin", "commit"}
            )
            assert work._invocation_started is not None
            assert 0 < cleanup <= 8 and 0 < work.statements - cleanup <= 504
            assert work.statements <= 512 and work.instructions < 20_000_000 and elapsed < 10
            assert work._started is None and work._connection is None and work._raw is None
            assert work._detached and not work._listeners and work._lease is None
            assert case.engine.pool.checkedout() == 0
            assert max((count for _, count in statements), default=0) <= 64
            record_property(
                "f4_complete_paid_work",
                json.dumps(
                    {
                        "total": work.statements,
                        "cleanup": cleanup,
                        "ordinary": work.statements - cleanup,
                        "vm": work.instructions,
                        "elapsed_seconds": elapsed,
                        "acquisition_clock": True,
                        "commit_attempted": coordinator.outcome.commit_attempted,
                        "commit_acknowledged": coordinator.outcome.commit_acknowledged,
                        "rollback_acknowledged": coordinator.outcome.rollback_acknowledged,
                        "cleanup_failed": coordinator.outcome.cleanup_failed,
                        "maximum_compiled_binds": max(
                            (count for _, count in statements), default=0
                        ),
                    },
                    sort_keys=True,
                ),
            )
