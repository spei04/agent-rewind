"""Offline controls for exact money setup, original refusal and result oracles."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_eligibility_fixture import rows
from ledger_money_fixture import (
    EXACT_AMOUNT,
    assert_cap_manifest,
    assert_exact_money,
    assert_setup_delta,
    below_job_cap,
    money_manifest,
)
from ledger_money_observer import assert_job_cap_refusal, observe_money
from ledger_provisioning_fixture import canonical, digest, expected_stage, identity
from test_ledger_eligibility_controls import example, replace_cell, table

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerProvisioning
from agent_rewind.migrations.schema import LEDGER, MigrationRefused


def legacy_example():
    prior, _, _, _, _ = example()
    template = rows(prior.before, "jobs")[0]
    jobs = [
        {**template, "id": identity(10 + i), "budget": budget, "reserved": reserved}
        for i, (budget, reserved) in enumerate(
            [(10000000, 125000), (10000000, 85000), (5000000, 35000)]
        )
    ]
    scopes = [
        {"resource_kind": "job", "resource_id": row["id"], "project_id": prior.project}
        for row in jobs
    ]
    before = {
        "schema": ("unchanged-schema",),
        "tables": {
            "jobs": table(jobs),
            "resource_scopes": table(scopes),
            "unrelated": table([{"id": "protected", "value": "unchanged"}]),
        },
    }
    fixture = SimpleNamespace(
        case=prior.case,
        before=before,
        project=prior.project,
        organization=prior.organization,
        source="f" * 64,
        jobs=[
            {key: row[key] for key in ("id", "budget", "reserved")} | {"project_id": prior.project}
            for row in jobs
        ],
    )
    return fixture


def apply_exact(fixture):
    before = deepcopy(fixture.before)
    target = fixture.jobs[0]["id"]
    for i, row in enumerate(fixture.jobs):
        amount = EXACT_AMOUNT if i == 0 else 0
        replace_cell(fixture.before, "jobs", i, "reserved", amount)
        row["reserved"] = amount
        if i == 0:
            replace_cell(fixture.before, "jobs", i, "budget", EXACT_AMOUNT)
            row["budget"] = EXACT_AMOUNT
    assert_setup_delta(before, fixture.before, target)
    return before, target


def context_for(fixture):
    raw, engine = object(), object()
    work = SimpleNamespace(_raw=raw, _connection=SimpleNamespace(engine=engine), check=lambda: None)
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(raws=[raw], events=[]),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
        markers=[
            (name, id(raw), 0)
            for name in [
                "rollback.before_native",
                "rollback.native_ack",
                "connection.close.before",
                "connection.close.return",
                "command.exit",
            ]
        ],
    )
    context = SimpleNamespace(
        state=SimpleNamespace(
            manifest_count=0,
            account_count=0,
            model_dump=lambda **kwargs: {
                "status": "absent",
                "head": None,
                "revision": "ar_0006_admission",
            },
        ),
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=fixture.organization),
            manifests=(),
            opening=None,
            adoption={"installed_schema_fingerprint": "e" * 64},
        ),
        financial={
            "job": rows(fixture.before, "jobs"),
            "scope": rows(fixture.before, "resource_scopes"),
            "account": [],
        },
    )
    return watch, context


def refused(monkeypatch, *, earlier=False):
    fixture = legacy_example()
    baseline, manifest, target = below_job_cap(fixture)
    if earlier:
        manifest["accounts"][2]["limit_microusd"] = fixture.jobs[0]["budget"] + 1
    watch, context = context_for(fixture)
    captured = []
    with (
        observe_money(watch, monkeypatch, lambda *args: captured.append(args)) as observed,
        pytest.raises(MigrationRefused) as error,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,), stages = observed
    assert len(captured) == 1 and captured[0][0] == "money_preparation"
    return fixture, baseline, manifest, target, watch, entry, stages, error.value


def successful(monkeypatch):
    fixture = legacy_example()
    apply_exact(fixture)
    manifest = money_manifest(fixture)
    watch, context = context_for(fixture)
    with observe_money(watch, monkeypatch, lambda *args: None) as (records, stages):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,) = records
    assert stages == ["prepare.enter", "prepare.return"]
    receipt = LedgerProvisioning(
        installation_key=manifest["installation_key"],
        revision=LEDGER,
        manifest_id=manifest["manifest_id"],
        manifest_digest=digest(manifest),
        sequence=0,
        operation="initialize",
        source_digest=manifest["source_digest"],
        account_rows=5,
        imported_jobs=3,
        imported_opening_microusd=EXACT_AMOUNT,
        initialized_at="2026-01-01T00:00:00.000000Z",
        outcome="complete",
    )
    accounts, progress, state = expected_stage(fixture, [manifest], [receipt])
    after = {
        "tables": {
            "budget_accounts": table(accounts),
            "migration_progress": table(
                [
                    {"revision": LEDGER, "phase": phase, "cursor": canonical(cursor).decode()}
                    for phase, (cursor, _, _) in progress.items()
                ]
            ),
        }
    }
    return fixture, manifest, entry["prepared"], receipt, after, state


def test_exact_four_cell_setup_preserves_other_budgets_and_complete_state():
    fixture = legacy_example()
    before, target = apply_exact(fixture)
    assert_setup_delta(before, fixture.before, target)
    assert [row["budget"] for row in fixture.jobs] == [EXACT_AMOUNT, 10000000, 5000000]
    assert [row["reserved"] for row in fixture.jobs] == [EXACT_AMOUNT, 0, 0]
    assert sum(row["reserved"] for row in fixture.jobs) == EXACT_AMOUNT


@pytest.mark.parametrize(
    "change",
    [
        "other-budget",
        "other-job-field",
        "unrelated",
        "schema",
        "rounded-target",
        "float-zero",
        "missing-zero",
        "missing-job",
    ],
)
def test_setup_oracle_rejects_rounding_and_collateral_state(change):
    fixture = legacy_example()
    before, target = apply_exact(fixture)
    after = fixture.before
    if change == "other-budget":
        replace_cell(after, "jobs", 1, "budget", 1)
    elif change == "other-job-field":
        replace_cell(after, "jobs", 1, "status", "cancelled")
    elif change == "unrelated":
        replace_cell(after, "unrelated", 0, "value", "changed")
    elif change == "schema":
        after["schema"] = ("changed",)
    elif change == "rounded-target":
        replace_cell(after, "jobs", 0, "reserved", 9007199254740992)
    elif change == "float-zero":
        replace_cell(after, "jobs", 1, "reserved", 0.0)
    elif change == "missing-zero":
        replace_cell(after, "jobs", 2, "reserved", 35000)
    else:
        after["tables"]["jobs"]["rows"].pop()
    with pytest.raises(AssertionError):
        assert_setup_delta(before, after, target)


def test_original_job_cap_branch_preserves_original_exception_and_exact_operands(monkeypatch):
    fixture, baseline, manifest, target, watch, entry, stages, error = refused(monkeypatch)
    assert_cap_manifest(fixture, baseline, manifest, target)
    assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)
    assert entry["traceback"]["preparation_frames"][0]["line"] == 177
    assert entry["amount_frames"][0]["amount"] == 125000


def test_same_code_earlier_budget_limit_refusal_does_not_receive_job_cap_credit(monkeypatch):
    fixture, _, manifest, target, watch, entry, stages, error = refused(monkeypatch, earlier=True)
    assert error.code == "ledger_exposure_refused"
    assert entry["traceback"]["preparation_frames"][0]["line"] == 119
    with pytest.raises(AssertionError):
        assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)


@pytest.mark.parametrize(
    "change",
    [
        "amount",
        "float-amount",
        "wrong-job",
        "scope",
        "assignments",
        "exception",
        "site",
        "source",
        "raw",
        "rollback",
        "commit",
        "cleanup-order",
    ],
)
def test_job_cap_oracle_rejects_substitute_failure_identity_or_cleanup(change, monkeypatch):
    fixture, _, manifest, target, watch, entry, stages, error = refused(monkeypatch)
    frame = entry["traceback"]["preparation_frames"][0]
    if change == "amount":
        entry["amount_frames"][0]["amount"] -= 1
    elif change == "float-amount":
        entry["amount_frames"][0]["amount"] = 125000.0
    elif change == "wrong-job":
        frame["job_id"] = identity(99)
    elif change == "scope":
        entry["amount_frames"][0]["scopes"][target] = identity(99)
    elif change == "assignments":
        frame["assignments"].pop(target)
    elif change == "exception":
        error = MigrationRefused("ledger_exposure_refused")
    elif change == "site":
        frame["line"] = 119
    elif change == "source":
        entry["manifest"]["source_digest"] = "0" * 64
    elif change == "raw":
        entry["raw_id"] += 1
    elif change == "rollback":
        watch.outcome.confirmed_precommit_rollback = False
    elif change == "commit":
        watch.outcome.commit_attempted = True
    else:
        watch.markers.reverse()
    with pytest.raises(AssertionError):
        assert_job_cap_refusal(fixture, manifest, target, entry, stages, error, watch)


@pytest.mark.parametrize("change", ["cap", "cohort", "organization", "fingerprint"])
def test_negative_manifest_keeps_all_original_caps_and_membership(change):
    fixture = legacy_example()
    baseline, manifest, target = below_job_cap(fixture)
    if change == "cap":
        manifest["accounts"][0]["limit_microusd"] += 1
    elif change == "cohort":
        manifest["accounts"].pop()
    elif change == "organization":
        manifest["accounts"][0]["organization_id"] = identity(99)
    else:
        manifest["source_digest"] = "0" * 64
    with pytest.raises(AssertionError):
        assert_cap_manifest(fixture, baseline, manifest, target)


def test_original_pure_prepare_and_independent_result_retain_exact_integer(monkeypatch):
    args = successful(monkeypatch)
    assert_exact_money(*args)
    fixture, manifest, prepared, receipt, _, _ = args
    assert receipt.imported_opening_microusd == sum(row["reserved"] for row in fixture.jobs)
    assert receipt.imported_opening_microusd == EXACT_AMOUNT
    assert prepared["organization_opening"] == EXACT_AMOUNT
    assert [row["limit_microusd"] for row in manifest["accounts"][:2]] == [EXACT_AMOUNT] * 2


@pytest.mark.parametrize(
    "change",
    [
        "prepared",
        "receipt",
        "account-rounded",
        "account-float-zero",
        "double-counted",
        "opening",
        "manifest-cursor",
        "inspection",
        "source-float",
    ],
)
def test_exact_integer_oracle_rejects_rounding_and_duplicate_exposure(change, monkeypatch):
    fixture, manifest, prepared, receipt, after, state = successful(monkeypatch)
    if change == "prepared":
        prepared["organization_opening"] = 9007199254740992
    elif change == "receipt":
        receipt = receipt.model_copy(update={"imported_opening_microusd": 9007199254740992})
    elif change == "account-rounded":
        replace_cell(after, "budget_accounts", 0, "held_microusd", 9007199254740992)
    elif change == "account-float-zero":
        replace_cell(after, "budget_accounts", 0, "accounted_microusd", 0.0)
    elif change == "double-counted":
        receipt = receipt.model_copy(update={"imported_opening_microusd": EXACT_AMOUNT * 3})
    elif change in {"opening", "manifest-cursor"}:
        progress = rows(after, "migration_progress")
        index = next(
            i
            for i, row in enumerate(progress)
            if (row["phase"] == "ledger_opening") == (change == "opening")
        )
        import json

        cursor = json.loads(progress[index]["cursor"])
        key = (
            "organization_opening_microusd" if change == "opening" else "imported_opening_microusd"
        )
        cursor[key] = 9007199254740992
        replace_cell(after, "migration_progress", index, "cursor", canonical(cursor).decode())
    elif change == "inspection":
        state["head"]["imported_opening_microusd"] = 9007199254740992
    else:
        fixture.jobs[0]["budget"] = 9007199254740992.0
    with pytest.raises(AssertionError):
        assert_exact_money(fixture, manifest, prepared, receipt, after, state)


def test_observer_preserves_first_baseexception_without_inventing_amount_frame(monkeypatch):
    fixture = legacy_example()
    watch, context = context_for(fixture)
    original = KeyboardInterrupt("money-control")
    calls = []

    def interrupt(*args):
        calls.append(args)
        raise original

    monkeypatch.setattr(ledger_service, "_prepare_ledger", interrupt)
    with (
        observe_money(watch, monkeypatch, lambda *args: None) as (records, stages),
        pytest.raises(KeyboardInterrupt) as failure,
    ):
        ledger_service._prepare_ledger(
            context, validate_ledger_manifest(money_manifest(fixture)), watch.work
        )
    assert failure.value is original and len(calls) == 1
    assert records[0]["error"]["identity"] == id(original)
    assert records[0]["amount_frames"] == []
    assert stages == ["prepare.enter", "prepare.refused"]
