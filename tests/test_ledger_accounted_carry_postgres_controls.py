"""Offline native carry adapters and independent malformed-evidence controls."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from ledger_accounted_carry_fixture import expected_settlement, replace_rows
from ledger_accounted_carry_observer import observe_carry
from ledger_accounted_carry_postgres_fixture import (
    assert_raw_progress,
    assert_settlement,
    expected_final,
    native_additions,
    native_time,
    progress_row,
)
from ledger_accounted_carry_postgres_observer import assert_native_carry, financial_projection
from ledger_eligibility_fixture import rows
from ledger_eligibility_postgres_fixture import native_handle
from ledger_provisioning_fixture import canonical, expected_stage, identity
from ledger_restore_authority import typed
from test_admission_envelope import descriptor
from test_ledger_accounted_carry_controls import OBSERVED, example
from test_ledger_eligibility_controls import table

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_state import LedgerState
from agent_rewind.migrations.ledger_work import LedgerWork

ROLE = "synthetic_native_owner"


def native_example():
    frozen, first, initial, before, _, second, written, _ = example()
    before = deepcopy(before)
    before.update(catalog={"synthetic": True}, authority={"owner": ROLE}, role=ROLE)
    accounts, progress, state = expected_stage(frozen, [first], [initial], database_role=ROLE)
    for account in accounts:
        for field in ("period_start", "period_end"):
            account[field] = native_time(account[field])
    replace_rows(before, "budget_accounts", accounts)
    replace_rows(
        before,
        "migration_progress",
        [progress_row(phase, value) for phase, value in progress.items()],
    )
    before["tables"]["operations"] = table(
        [
            {
                "id": identity(99),
                "job_id": frozen.jobs[0]["id"],
                "created_at": native_time(OBSERVED),
                "retain_until": native_time(OBSERVED),
            }
        ]
    )
    before["tables"]["projects"] = table(
        [{"id": frozen.project, "organization_id": frozen.organization, "run_sequence": 0}]
    )
    before["tables"]["organizations"] = table(
        [{"id": frozen.organization, "installation_key": first["installation_key"], "name": "test"}]
    )
    evidence = descriptor(b"control-only", object_id=identity(7_000_000), project=frozen.project)
    additions = native_additions(frozen, first, evidence, OBSERVED, "price-v1")
    settled = expected_settlement(before, additions, frozen.jobs[0]["id"])
    evolved = SimpleNamespace(before=settled, source=second["source_digest"])
    return frozen, first, initial, before, additions, evolved, second, written, state


def observed(monkeypatch, *, handles=1):
    frozen, first, _, _, _, evolved, second, _, state = native_example()
    work, raw, engine = LedgerWork(), object(), object()
    work._raw, work._connection = raw, SimpleNamespace(engine=engine)
    trace = SimpleNamespace(
        handles=[raw] if handles == 1 else [object()] * (1 if handles == -1 else handles), events=[]
    )
    watch = SimpleNamespace(work=work, engine=engine, trace=trace)
    _, financial = financial_projection(evolved.before)
    context = SimpleNamespace(
        state=LedgerState.model_validate(state),
        financial=deepcopy(financial),
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=frozen.organization),
            manifests=(),
            opening=None,
            adoption={"installed_schema_fingerprint": "e" * 64},
        ),
    )
    with observe_carry(watch, monkeypatch, lambda *args: None, raw_handle=native_handle) as (
        entries,
        sources,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(second), work)
    identity_values = {"work_id": id(work), "raw_id": id(raw), "engine_id": id(engine)}
    # Explicit synthetic receipts test accounting; they do not claim real source reads.
    sources.extend([{**identity_values, "value": evolved.source, "position": 0} for _ in range(2)])
    return entries[0], sources, evolved, first, second, state, watch


def test_native_setup_and_final_projection_keep_original_opening():
    frozen, first, initial, before, additions, evolved, second, written, _ = native_example()
    assert_settlement(before, evolved.before, additions, frozen.jobs[0]["id"])
    final, state = expected_final(frozen, first, initial, evolved.before, second, written, ROLE)
    assert len(rows(final, "budget_accounts")) == 5
    assert len(rows(final, "migration_progress")) == 3
    assert state["opening"]["organization_opening_microusd"] == 0
    assert rows(final, "jobs")[0]["reserved"] == 1
    assert typed(final["tables"]["provider_calls"]) == typed(
        evolved.before["tables"]["provider_calls"]
    )
    assert all(type(row["period_start"]) is datetime for row in rows(final, "budget_accounts"))
    assert all(type(row["cursor"]) is dict for row in rows(final, "migration_progress"))


def test_native_handle_adapter_observes_original_held_only_reduction(monkeypatch):
    assert_native_carry(*observed(monkeypatch))


@pytest.mark.parametrize("handles,error", [(0, ValueError), (2, ValueError), (-1, AssertionError)])
def test_native_handle_adapter_rejects_missing_multiple_or_wrong_handles(
    monkeypatch, handles, error
):
    with pytest.raises(error):
        observed(monkeypatch, handles=handles)


@pytest.mark.parametrize(
    "mutation",
    [
        "job-bool",
        "account-float",
        "entry-bool",
        "operation-time",
        "object-time",
        "state-float",
        "manifest-float",
        "prepared-float",
        "sum-line-float",
        "source-position-bool",
        "identity-float",
    ],
)
def test_native_carry_rejects_independent_receipt_corruption(monkeypatch, mutation):
    entry, sources, evolved, first, second, state, watch = observed(monkeypatch)
    entry, sources = deepcopy(entry), deepcopy(sources)
    if mutation == "job-bool":
        entry["financial"]["job"][0]["reserved"] = True
    elif mutation == "account-float":
        entry["financial"]["account"][0]["accounted_microusd"] = 1.0
    elif mutation == "entry-bool":
        entry["financial"]["entry"][0]["amount_microusd"] = True
    elif mutation in {"operation-time", "object-time"}:
        entry["financial"][mutation.split("-")[0]][0]["created_at"] = native_time(OBSERVED)
    elif mutation == "state-float":
        entry["state"]["account_count"] = 3.0
    elif mutation == "manifest-float":
        entry["manifest"]["accounts"][0]["limit_microusd"] = 0.0
    elif mutation == "prepared-float":
        entry["prepared"]["organization_opening"] = 0.0
    elif mutation == "sum-line-float":
        entry["sums"][0]["line"] = 136.0
    elif mutation == "source-position-bool":
        sources[0]["position"] = False
    else:
        entry["work_id"] = float(entry["work_id"])
    with pytest.raises(AssertionError):
        assert_native_carry(entry, sources, evolved, first, second, state, watch)


@pytest.mark.parametrize("domain", ["account", "call", "entry", "object", "operation"])
def test_native_projection_rejects_string_or_naive_timestamp(domain):
    _, _, _, _, _, evolved, _, _, _ = native_example()
    name = {
        "account": "budget_accounts",
        "call": "provider_calls",
        "entry": "budget_entries",
        "object": "artifact_objects",
        "operation": "operations",
    }[domain]
    changed = deepcopy(evolved.before)
    values = rows(changed, name)
    field = "period_start" if domain == "account" else "created_at"
    values[0][field] = OBSERVED if domain != "call" else datetime(2026, 10, 23)
    replace_rows(changed, name, values)
    with pytest.raises(AssertionError):
        financial_projection(changed)


@pytest.mark.parametrize(
    "mutation", ["account-bool", "job-float", "catalog", "authority", "object", "call", "entry"]
)
def test_native_settlement_rejects_collateral_or_type_changes(mutation):
    frozen, _, _, before, additions, evolved, _, _, _ = native_example()
    after = deepcopy(evolved.before)
    if mutation in {"catalog", "authority"}:
        after[mutation]["unexpected"] = True
    else:
        name, field, value = {
            "account-bool": ("budget_accounts", "accounted_microusd", True),
            "job-float": ("jobs", "reserved", 1.0),
            "object": ("artifact_objects", "byte_count", 1),
            "call": ("provider_calls", "lease_generation", 2),
            "entry": ("budget_entries", "amount_microusd", 0),
        }[mutation]
        values = rows(after, name)
        values[0][field] = value
        replace_rows(after, name, values)
    with pytest.raises(AssertionError):
        assert_settlement(before, after, additions, frozen.jobs[0]["id"])


@pytest.mark.parametrize(
    "mutation",
    [
        "account-bool",
        "cursor-string",
        "progress-count-float",
        "progress-role",
        "progress-time",
        "manifest-cap-bool",
        "receipt-count-float",
        "frozen-reserved-bool",
    ],
)
def test_native_final_rejects_rewritten_history_and_type_aliases(mutation):
    frozen, first, initial, _, _, evolved, second, written, _ = native_example()
    if mutation == "manifest-cap-bool":
        first["accounts"][0]["limit_microusd"] = True
    elif mutation == "receipt-count-float":
        written = written.model_copy(update={"account_rows": 2.0})
    elif mutation == "frozen-reserved-bool":
        frozen.jobs[0]["reserved"] = False
    elif mutation == "account-bool":
        values = rows(evolved.before, "budget_accounts")
        values[0]["accounted_microusd"] = True
        replace_rows(evolved.before, "budget_accounts", values)
    else:
        values = deepcopy(rows(evolved.before, "migration_progress"))
        selected = next(row for row in values if row["phase"].startswith("ledger_manifest_"))
        if mutation == "cursor-string":
            selected["cursor"] = canonical(selected["cursor"]).decode()
        elif mutation == "progress-count-float":
            selected["rows_verified"] = 3.0
        elif mutation == "progress-role":
            selected["cursor"]["database_role"] = "another_owner"
        else:
            selected["updated_at"] = OBSERVED
        replace_rows(evolved.before, "migration_progress", values)
    with pytest.raises(AssertionError):
        expected_final(frozen, first, initial, evolved.before, second, written, ROLE)


@pytest.mark.parametrize("mutation", [None, "old-text", "duplicate", "new-nontext"])
def test_raw_progress_preserves_exact_old_jsonb_text(mutation):
    old = [{"revision": "ar_0007_ledger", "phase": "ledger_opening", "raw_cursor": '{"old": 0}'}]
    new = deepcopy(old) + [
        {"revision": "ar_0007_ledger", "phase": "new_manifest", "raw_cursor": '{"new": 0}'}
    ]
    if mutation == "old-text":
        new[0]["raw_cursor"] = '{"old": false}'
    elif mutation == "duplicate":
        new.append(deepcopy(new[0]))
    elif mutation == "new-nontext":
        new[-1]["raw_cursor"] = {}
    if mutation is None:
        assert_raw_progress(old, new, "new_manifest")
    else:
        with pytest.raises(AssertionError):
            assert_raw_progress(old, new, "new_manifest")
