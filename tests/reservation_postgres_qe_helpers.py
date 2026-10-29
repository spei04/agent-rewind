"""Finite native P2 oracles and real period setup; no service or cluster ownership."""

import json
import time
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import Event

import reservation_postgres_fixture as shared
from ledger_eligibility_fixture import rows as native_rows
from ledger_eligibility_postgres_fixture import refreshed
from ledger_provisioning_fixture import digest
from ledger_provisioning_postgres_fixture import invoke
from ledger_restore_authority import typed
from reservation_qe_fixture import assert_claim, identity, one, same

from agent_rewind.reservation_service import ReservationCoordinator
from agent_rewind.reservation_types import ClaimIntent


def record(record_property, name, value):
    record_property(name, json.dumps(typed(value), allow_nan=False))


def state(case):
    """Retain every native catalog/authority/role cell, with strict row dictionaries."""
    result = deepcopy(case.snapshot())
    for name, value in result["tables"].items():
        value["rows"] = native_rows(result, name)
    return result


def report(record_property, label, owner):
    value = {"outcome": asdict(owner.outcome)}
    if owner._work is not None:
        value["work"] = {
            "units": owner._work.statements,
            "seconds": owner._work.seconds,
            "vm": owner._work.instructions,
        }
    record(record_property, label, value)


def bounded(owner):
    assert owner._work is not None
    assert owner._work.statements <= 512 and owner._work.seconds < 10
    assert not owner.outcome.cleanup_failed


def claim(case, record_property, number=140000):
    before = state(case)
    owner = ReservationCoordinator(case.engine, case.authority)
    try:
        fence = owner.claim_generation(
            case.principal, case.context, ClaimIntent(case.job_id, identity(number), 0, 60)
        )
    finally:
        report(record_property, "claim", owner)
    assert owner.outcome.commit_acknowledged
    bounded(owner)
    assert_claim(before, state(case), fence)
    return fence


def native_time(pg):
    with pg["owner"].connect() as connection:
        result = connection.exec_driver_sql("SELECT clock_timestamp()").scalar_one()
    assert isinstance(result, datetime) and result.utcoffset() == timedelta(0)
    return result


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def micros(value):
    origin = datetime(1970, 1, 1, tzinfo=UTC)
    difference = value - origin
    return (difference.days * 86400 + difference.seconds) * 1_000_000 + difference.microseconds


def build_expiring_period_case(pg, tmp_path, monkeypatch, selected, record_property):
    """Real P1 periods; only the later SET CONSTRAINTS phase receives injected latency."""
    initial = shared.initial_manifest
    boundary = []

    def short_opening(fixture):
        manifest = initial(fixture)
        # Admission/predecessor preparation has completed before this callback.
        # The initial pair must match and remain live for actual P1 initialization.
        end = native_time(pg) + timedelta(seconds=10)
        boundary.append(end)
        for account in manifest["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["period_end"] = stamp(end)
        return manifest

    with monkeypatch.context() as patch:
        patch.setattr(shared, "initial_manifest", short_opening)
        case = shared.build_postgres_reservation_case(pg, tmp_path, patch)
    try:
        assert len(boundary) == 1
        fence = claim(case, record_property)
        # Wait on observed native time, never infer expiry from an arbitrary sleep.
        deadline, observations = time.monotonic() + 14, []
        while True:
            now = native_time(pg)
            observations.append(now)
            if now >= boundary[0]:
                break
            assert time.monotonic() < deadline, "initial period did not expire within fixture bound"
            Event().wait(min(0.05, max(0.0, (boundary[0] - now).total_seconds())))
        fixture = refreshed(case.provisioning, pg)
        previous = case.admission.manifest
        before = state(case)
        # Suspension/drain precedes the short deadline; P2 runs only after exact ACL restoration.
        with shared.offline_postgres_ledger(
            case, lambda name, value: record(record_property, name, value)
        ):
            selected_end = native_time(pg) + timedelta(seconds=4)
            accounts = []
            for number, scope in enumerate(("organization", "project"), 140010):
                original = next(row for row in previous["accounts"] if row["scope"] == scope)
                accounts.append(
                    {
                        **original,
                        "id": identity(number),
                        "period_start": stamp(boundary[0]),
                        "period_end": stamp(
                            selected_end if scope == selected else datetime(2100, 1, 1, tzinfo=UTC)
                        ),
                    }
                )
            manifest = {
                **previous,
                "manifest_id": identity(140012),
                "operation": "provision",
                "source_digest": fixture.source,
                "parent_manifest_digest": digest(previous),
                "opening_accounts": None,
                "accounts": accounts,
            }
            receipt = invoke(fixture, pg, manifest)
        assert receipt.account_rows == 2 and receipt.sequence == 1
        after = state(case)
        for table in set(before["tables"]) - {"budget_accounts", "migration_progress"}:
            assert typed(before["tables"][table]) == typed(after["tables"][table]), table
        prior = {row["id"]: row for row in before["tables"]["budget_accounts"]["rows"]}
        current = {row["id"]: row for row in after["tables"]["budget_accounts"]["rows"]}
        assert set(current) == set(prior) | {row["id"] for row in accounts}
        assert all(current[key] == value for key, value in prior.items())
        for row in accounts:
            actual = current[row["id"]]
            assert actual["held_microusd"] == actual["accounted_microusd"] == 0
        result = replace(
            case,
            provisioning=fixture,
            account_ids=(accounts[0]["id"], accounts[1]["id"], case.account_ids[2]),
        )
        observed = native_time(pg)
        assert boundary[0] <= observed < selected_end
        assert one(after, "jobs", id=case.job_id)["lease_until"] * 1_000_000 > micros(observed)
        record(
            record_property,
            "period_setup",
            {
                "initial_end": boundary[0],
                "condition_samples": observations,
                "provision_receipt": receipt.model_dump(mode="json"),
                "selected_accounts": [current[key] for key in result.account_ids],
                "after_provision_time": observed,
                "selected_end": selected_end,
                "qualification": "Actual native time and P1 provisioning; no clock substitution.",
            },
        )
        return result, fence, selected_end, after
    except BaseException:
        case.close()
        raise


def assert_competitor_delta(before, after, table, selectors, changes):
    expected = deepcopy(before)
    one(expected, table, **selectors).update(changes)
    same(expected, after)
