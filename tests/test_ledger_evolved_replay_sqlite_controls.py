"""Small pure SQLite representation checks; the two service cases are separate."""

import json
import sys
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
import test_ledger_evolved_replay_sqlite as sqlite_case
from ledger_accounted_carry_fixture import replace_rows
from ledger_eligibility_fixture import rows
from ledger_evolved_replay_fixture import (
    SQLITE_CLOCK_SQL,
    assert_evolution,
    assert_expiry_clock,
    cohort,
    equal,
)
from test_ledger_evolved_replay_controls import clock_witness, witness


def sqlite_witness():
    """Convert the existing independent literal observations, not expected output."""
    w = witness()
    for name in ("before", "reserved", "settled"):
        native = getattr(w, name)
        state = {
            "schema": (("table", "literal", "literal", "literal schema"),),
            "tables": deepcopy(native["tables"]),
        }
        for table in state["tables"]:
            values = rows(state, table)
            for value in values:
                for key, cell in value.items():
                    if type(cell) is datetime:
                        value[key] = (
                            cell.isoformat()
                            if table == "artifact_objects"
                            else cell.isoformat(timespec="microseconds").replace("+00:00", "Z")
                        )
                    elif type(cell) is bool:
                        value[key] = int(cell)
                    elif type(cell) is dict:
                        value[key] = json.dumps(cell, sort_keys=True, separators=(",", ":"))
            replace_rows(state, table, values)
        setattr(w, name, state)
    return w


@pytest.mark.parametrize("phase", ["reserved", "settled"])
def test_sqlite_literal_evolution_and_cohort(phase):
    w = sqlite_witness()
    saved = deepcopy(w.before)
    extra = (
        {}
        if phase == "reserved"
        else {"evidence": w.evidence, "legacy_job": w.legacy, "membership": w.membership}
    )
    assert_evolution(w.before, getattr(w, phase), w.ids, backend="sqlite", **extra)
    equal(
        cohort(
            w.before,
            w.first,
            w.one,
            w.ids["job"],
            w.ids["price"],
            w.ids["observed"],
            backend="sqlite",
        ),
        w.ids,
    )
    equal(w.before, saved)


@pytest.mark.parametrize("damage", ["native-time", "opening", "progress"])
def test_sqlite_evolution_rejects_changed_native_state(damage):
    w = sqlite_witness()
    if damage == "native-time":
        values = rows(w.reserved, "provider_calls")
        values[0]["created_at"] = datetime.fromisoformat(
            values[0]["created_at"].replace("Z", "+00:00")
        )
        replace_rows(w.reserved, "provider_calls", values)
    elif damage == "opening":
        values = rows(w.reserved, "budget_accounts")
        values[0]["opening_held_microusd"] += 1
        replace_rows(w.reserved, "budget_accounts", values)
    else:
        values = rows(w.reserved, "migration_progress")
        values[0]["cursor"] += " "
        replace_rows(w.reserved, "migration_progress", values)
    with pytest.raises(AssertionError):
        assert_evolution(w.before, w.reserved, w.ids, backend="sqlite")


def test_sqlite_financial_projection_keeps_raw_snapshot_and_exact_scope():
    w = sqlite_witness()
    original = deepcopy(w.reserved)
    values = rows(w.reserved, "resource_scopes")
    replace_rows(
        w.reserved,
        "resource_scopes",
        values
        + [{"resource_kind": "run", "resource_id": "not-a-job", "project_id": w.ids["project"]}],
    )
    saved = deepcopy(w.reserved)
    financial = sqlite_case.sqlite_financial(w.reserved)
    assert financial["scope"] == values
    assert financial["call"][0]["created_at"] == w.ids["observed"]
    equal(w.reserved, saved)
    equal(original["tables"]["provider_calls"], w.reserved["tables"]["provider_calls"])


def sqlite_clock():
    schedule, first, receipt, samples = clock_witness()
    for sample in samples:
        for key in ("role", "database_name", "drained"):
            sample.pop(key)
        sample.update(sql=SQLITE_CLOCK_SQL, query_only=1)
    return schedule, first, receipt, samples


def test_sqlite_clock_gate_requires_actual_elapsed_expiry():
    schedule, first, receipt, samples = sqlite_clock()
    assert_expiry_clock(schedule, first, receipt, samples, 1011, 1020, 1161.4, backend="sqlite")


@pytest.mark.parametrize("damage", ["write-capable", "unclosed", "premature"])
def test_sqlite_clock_gate_rejects_invalid_sample(damage):
    schedule, first, receipt, samples = sqlite_clock()
    if damage == "write-capable":
        samples[-1]["query_only"] = 0
    elif damage == "unclosed":
        samples[-1]["connection_closed"] = False
    else:
        samples[-1]["database"] = receipt["initialized_at"]
    with pytest.raises(AssertionError):
        assert_expiry_clock(schedule, first, receipt, samples, 1011, 1020, 1161.4, backend="sqlite")


@pytest.mark.parametrize("external", [None, "1000"])
def test_ordinary_entry_or_external_child_anchor_is_not_reset(monkeypatch, external):
    monkeypatch.setattr(sqlite_case.time, "monotonic", lambda: 1005.0)
    if external is None:
        monkeypatch.delenv("AR_R1_CHILD_STARTED_MONOTONIC", raising=False)
    else:
        monkeypatch.setenv("AR_R1_CHILD_STARTED_MONOTONIC", external)
    schedule, _ = sqlite_case.begin(lambda *_: None, "test")
    equal(
        schedule,
        {
            "entered": 1005.0,
            "started": 1005.0 if external is None else 1000.0,
            "deadline": 1365.0 if external is None else 1360.0,
        },
    )


@pytest.mark.parametrize("has_original", [False, True])
def test_cleanup_failure_retains_original_or_propagates_cleanup(has_original):
    original = RuntimeError("original service failure")
    cleanup = ValueError("cleanup failure")

    def close():
        raise cleanup

    fixture = SimpleNamespace(close=close)
    expected = original if has_original else cleanup
    records = []
    with pytest.raises(type(expected)) as caught:
        try:
            if has_original:
                raise original
        finally:
            sqlite_case.finish(
                fixture,
                {},
                lambda name, value: records.append((name, value)),
                None,
                sys.exception(),
            )
    assert caught.value is expected
    assert records[0][1]["cleanup_error"] == "ValueError"
    if has_original:
        assert original.__notes__ == ["Local fixture cleanup also failed: ValueError"]
    else:
        assert records[0][1]["original_error"] is None
