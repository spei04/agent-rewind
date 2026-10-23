"""Pure controls; no database, publication or provider execution."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_accounted_carry_fixture import (
    expected_settlement,
    future_carry_manifest,
    initial_carry_manifest,
    replace_rows,
    settlement_rows,
)
from ledger_accounted_carry_observer import (
    assert_carry,
    assert_receipt_reentry,
    expected_final,
    observe_carry,
)
from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import canonical, digest, expected_stage, identity
from test_admission_envelope import descriptor
from test_ledger_eligibility_controls import table

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_reader_financial import _validate_calls
from agent_rewind.migrations.ledger_state import (
    LedgerManifestReceipt,
    LedgerProvisioning,
    LedgerState,
)
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, MigrationRefused

OBSERVED = "2026-10-23T00:00:00.000000Z"


def receipt(manifest, sequence):
    return LedgerProvisioning(
        installation_key=manifest["installation_key"],
        revision=LEDGER,
        manifest_id=manifest["manifest_id"],
        manifest_digest=digest(manifest),
        sequence=sequence,
        operation=manifest["operation"],
        source_digest=manifest["source_digest"],
        account_rows=len(manifest["accounts"]),
        imported_jobs=1 if sequence == 0 else 0,
        imported_opening_microusd=0,
        initialized_at=OBSERVED,
        outcome="complete",
    )


def example():
    frozen = SimpleNamespace(
        case=SimpleNamespace(adoption={"installation_key": "synthetic-installation"}),
        source="a" * 64,
        project="9" * 32,
        organization="8" * 32,
        jobs=[{"id": "2" * 32, "budget": 1, "reserved": 0, "project_id": "9" * 32}],
    )
    first = initial_carry_manifest(frozen)
    initial = receipt(first, 0)
    accounts, progress, state = expected_stage(frozen, [first], [initial])
    job = {
        "id": frozen.jobs[0]["id"],
        "status": "queued",
        "budget": 1,
        "reserved": 0,
        "legacy_reserved_microusd": 0,
        "lease_generation": 0,
        "owner": None,
        "lease_until": None,
    }
    before = {
        "schema": ("synthetic pure shape",),
        "tables": {
            "jobs": table([job]),
            "budget_accounts": table(accounts),
            "migration_progress": table(
                [
                    {
                        "revision": LEDGER,
                        "phase": phase,
                        "source_digest": source,
                        "cursor": canonical(cursor).decode(),
                        "rows_verified": count,
                        "status": "complete",
                        "updated_at": cursor["initialized_at"],
                    }
                    for phase, (cursor, count, source) in progress.items()
                ]
            ),
            "resource_scopes": table(
                [{"resource_kind": "job", "resource_id": job["id"], "project_id": frozen.project}]
            ),
            "operations": table([{"id": identity(99), "job_id": job["id"]}]),
        },
    }
    evidence = descriptor(b"control-only", object_id=identity(7_000_000), project=frozen.project)
    additions = settlement_rows(frozen, first, evidence, OBSERVED, "price-v1")
    for name, values in additions.items():
        if name not in before["tables"]:
            before["tables"][name] = {"columns": tuple(values[0]), "rows": ()}
    settled = expected_settlement(before, additions, job["id"])
    evolved = SimpleNamespace(source="b" * 64, before=settled)
    second = future_carry_manifest(first, evolved.source)
    return frozen, first, initial, before, evolved, second, receipt(second, 1), state


def test_caps_and_frozen_opening_are_separate_from_evolved_reservation():
    frozen, first, initial, before, evolved, second, written, state = example()
    assert [a["limit_microusd"] for a in first["accounts"]] == [1, 1, 1]
    assert [a["limit_microusd"] for a in second["accounts"]] == [0, 0]
    expected, after_state = expected_final(frozen, first, initial, evolved.before, second, written)
    assert rows(expected, "jobs")[0]["reserved"] == 1
    assert rows(expected, "jobs")[0]["legacy_reserved_microusd"] == 0
    assert after_state["opening"] == state["opening"]
    assert after_state["opening"]["job_count"] == 1
    assert after_state["opening"]["organization_opening_microusd"] == 0
    assert expected["tables"]["operations"] == before["tables"]["operations"]


def observed(monkeypatch, *, held=0):
    frozen, first, initial, before, evolved, second, written, state = example()
    work, raw, engine = LedgerWork(), object(), object()
    work._raw, work._connection = raw, SimpleNamespace(engine=engine)
    watch = SimpleNamespace(work=work, engine=engine, trace=SimpleNamespace(raws=[raw], events=[]))
    financial = {
        key: rows(evolved.before, name)
        for key, name in (
            ("account", "budget_accounts"),
            ("job", "jobs"),
            ("scope", "resource_scopes"),
            ("call", "provider_calls"),
            ("entry", "budget_entries"),
            ("ref", "artifact_refs"),
        )
    }
    financial["account"][0]["held_microusd"] = held
    context = SimpleNamespace(
        state=LedgerState.model_validate(state),
        financial=financial,
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=frozen.organization),
            manifests=(),
            opening=None,
            adoption={"installed_schema_fingerprint": "e" * 64},
        ),
    )
    with observe_carry(watch, monkeypatch, lambda *args: None) as (entries, sources):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(second), work)
    identity_values = {"work_id": id(work), "raw_id": id(raw), "engine_id": id(engine)}
    # Source receipts are explicit pure oracle input; no fake SQL/delegate success.
    sources.extend([{**identity_values, "value": evolved.source, "position": 0} for _ in range(2)])
    return entries[0], sources, evolved, first, second, state, watch


def test_actual_original_prepare_excludes_accounted_from_zero_cap(monkeypatch):
    args = observed(monkeypatch)
    assert_carry(*args)


def test_actual_original_prepare_refuses_nonzero_held_at_zero_cap(monkeypatch):
    with pytest.raises(MigrationRefused, match="^ledger_exposure_refused$"):
        observed(monkeypatch, held=1)


@pytest.mark.parametrize(
    "mutation",
    [
        "work",
        "raw",
        "engine",
        "parent",
        "source",
        "held",
        "accounted",
        "original-caller",
        "line",
        "values",
        "boolean",
        "total",
        "missing-sum",
        "source-receipt",
        "source-count",
        "prepared",
        "call",
        "entry",
        "scope",
        "reference",
    ],
)
def test_carry_oracle_rejects_wrong_identity_operands_or_financial_context(monkeypatch, mutation):
    entry, sources, evolved, first, second, state, watch = observed(monkeypatch)
    if mutation in {"work", "raw", "engine"}:
        entry[mutation + "_id"] += 1
    elif mutation in {"parent", "source"}:
        second["parent_manifest_digest" if mutation == "parent" else "source_digest"] = "c" * 64
        entry["manifest"] = deepcopy(second)
    elif mutation in {"held", "accounted"}:
        entry["financial"]["account"][0][mutation + "_microusd"] += 1
    elif mutation == "original-caller":
        entry["sums"][0]["original_caller"] = False
    elif mutation == "line":
        entry["sums"][0]["line"] = 193
    elif mutation == "values":
        entry["sums"][0]["values"] = [1]
    elif mutation == "boolean":
        entry["sums"][0]["values"] = [False]
    elif mutation == "total":
        entry["sums"][0]["total"] = 1
    elif mutation == "missing-sum":
        entry["sums"].pop()
    elif mutation == "source-receipt":
        sources[0]["value"] = "c" * 64
    elif mutation == "source-count":
        sources.pop()
    elif mutation == "prepared":
        entry["prepared"]["exposure"] = {identity(400): 1}
    else:
        entry["financial"][{"reference": "ref"}.get(mutation, mutation)].pop()
    with pytest.raises(AssertionError):
        assert_carry(entry, sources, evolved, first, second, state, watch)


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "missing-settle",
        "missing-ref",
        "wrong-account",
        "wrong-scope",
        "generation",
        "unequal-amount",
    ],
)
def test_original_call_validator_checks_complete_synthetic_settlement(mutation):
    frozen, _, _, _, evolved, _, _, _ = example()
    calls = {r["id"]: r for r in rows(evolved.before, "provider_calls")}
    accounts = {r["id"]: r for r in rows(evolved.before, "budget_accounts")}
    jobs = {r["id"]: r for r in rows(evolved.before, "jobs")}
    scopes = {
        (r["resource_kind"], r["resource_id"]): r["project_id"]
        for r in rows(evolved.before, "resource_scopes")
    }
    entries = rows(evolved.before, "budget_entries")
    refs = {
        (r["project_id"], r["owner_kind"], r["owner_id"], r["artifact_id"], r["role"])
        for r in rows(evolved.before, "artifact_refs")
    }
    call = next(iter(calls.values()))
    if mutation == "missing-settle":
        entries.pop()
    elif mutation == "missing-ref":
        refs.clear()
    elif mutation == "wrong-account":
        call["job_account_id"] = call["project_account_id"]
    elif mutation == "wrong-scope":
        scopes[("provider_call", call["id"])] = "f" * 32
    elif mutation == "generation":
        call["lease_generation"] = 3
    elif mutation == "unequal-amount":
        entries[-1]["amount_microusd"] = 0
    args = (
        calls,
        accounts,
        jobs,
        scopes,
        {frozen.project: {}},
        entries,
        refs,
        frozen.organization,
        LedgerWork(),
    )
    if mutation == "none":
        _validate_calls(*args)
    else:
        with pytest.raises(MigrationRefused):
            _validate_calls(*args)


@pytest.mark.parametrize(
    "mutation",
    ["regenerated-opening", "old-account", "old-progress", "immutable-cap", "legacy-reservation"],
)
def test_final_projection_rejects_rewritten_m0_or_old_balances(mutation):
    frozen, first, initial, _, evolved, second, written, _ = example()
    if mutation == "regenerated-opening":
        frozen.jobs[0]["reserved"] = 1
    elif mutation == "old-account":
        values = rows(evolved.before, "budget_accounts")
        values[0]["held_microusd"] = 1
        replace_rows(evolved.before, "budget_accounts", values)
    elif mutation == "old-progress":
        values = rows(evolved.before, "migration_progress")
        values[0]["updated_at"] = "2001-01-01T00:00:00.000000Z"
        replace_rows(evolved.before, "migration_progress", values)
    elif mutation == "immutable-cap":
        first["accounts"][0]["limit_microusd"] = 0
    else:
        initial = initial.model_copy(update={"imported_opening_microusd": 1})
    with pytest.raises(AssertionError):
        expected_final(frozen, first, initial, evolved.before, second, written)


@pytest.mark.parametrize(
    "field",
    [
        None,
        "initialized_at",
        "manifest_digest",
        "source_digest",
        "account_rows",
        "imported_jobs",
        "imported_opening_microusd",
    ],
)
def test_reentry_compares_complete_immutable_receipt_without_model_class_equality(field):
    _, _, written, _, _, _, _, _ = example()
    value = written.model_dump(mode="json")
    assert value.pop("outcome") == "complete"
    actual = LedgerManifestReceipt.model_validate(value)
    if field is None:
        assert_receipt_reentry(actual, written)
    else:
        original = getattr(actual, field)
        actual = actual.model_copy(
            update={field: original + 1 if type(original) is int else "changed"}
        )
        with pytest.raises(AssertionError):
            assert_receipt_reentry(actual, written)
