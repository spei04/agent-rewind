"""Offline controls for native cohort provenance and exact captured value types."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_cohort_fixture import CASES, cohort_change
from ledger_cohort_observer import assert_cohort_refusal, observe_cohort
from ledger_cohort_postgres_fixture import (
    assert_native_cohort_change,
    assert_native_cohort_refusal,
    assert_native_preparation,
)
from ledger_eligibility_observer import assert_preparation
from ledger_eligibility_postgres_fixture import native_handle
from test_ledger_eligibility_postgres_controls import preparation_case

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.schema import MigrationRefused


def delegated(case, monkeypatch):
    fixture, _, watch, context, admitted = preparation_case("admitted")
    baseline, manifest, target = cohort_change(fixture, admitted, case)
    recorded = []
    with (
        observe_cohort(
            watch, monkeypatch, lambda *value: recorded.append(value), raw_handle=native_handle
        ) as observed,
        pytest.raises(MigrationRefused) as failure,
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), watch.work)
    (entry,), stages = observed
    assert len(recorded) == 1 and not hasattr(watch.trace, "raws")
    return fixture, admitted, baseline, manifest, target, watch, entry, stages, failure.value


@pytest.mark.parametrize("case", CASES)
def test_native_handle_delegates_original_cohort_guard(monkeypatch, case):
    fixture, admitted, baseline, manifest, target, watch, entry, stages, error = delegated(
        case, monkeypatch
    )
    assert_native_cohort_change(fixture, baseline, manifest, case, target, admitted)
    assert_native_preparation(entry, fixture, manifest, watch)
    assert_native_cohort_refusal(entry, stages, error, watch, case=case, target_job=target)
    assert entry["traceback"]["preparation_frames"][0]["line"] == (
        117 if case == "nonexistent-job" else 149
    )


@pytest.mark.parametrize(
    "fault", ["foreign-handle", "multiple-handles", "foreign-work", "foreign-engine"]
)
def test_native_cohort_callback_rejects_foreign_original_identities(monkeypatch, fault):
    fixture, _, watch, context, admitted = preparation_case("admitted")
    _, manifest, _ = cohort_change(fixture, admitted, "omit-admitted-zero")
    work = watch.work
    if fault == "foreign-handle":
        watch.trace.handles = [object()]
    elif fault == "multiple-handles":
        watch.trace.handles.append(object())
    elif fault == "foreign-work":
        work = SimpleNamespace(_raw=work._raw, _connection=work._connection)
    else:
        work._connection.engine = object()
    with (
        observe_cohort(watch, monkeypatch, lambda *row: None, raw_handle=native_handle),
        pytest.raises((AssertionError, ValueError)),
    ):
        ledger_service._prepare_ledger(context, validate_ledger_manifest(manifest), work)


@pytest.mark.parametrize(
    "fault",
    [
        "manifest-cap",
        "financial-job",
        "rejected-jobs",
        "rejected-job",
        "rejected-assignments",
        "rejected-account",
        "missing-account",
    ],
)
def test_native_cohort_witness_rejects_equal_value_type_substitution(monkeypatch, fault):
    case = "nonexistent-job" if fault == "missing-account" else "omit-admitted-zero"
    fixture, _, _, manifest, target, watch, entry, stages, error = delegated(case, monkeypatch)
    rejected = entry["traceback"]["preparation_frames"][0]
    before = deepcopy(entry)
    if fault == "manifest-cap":
        account = entry["manifest"]["accounts"][0]
        account["limit_microusd"] = float(account["limit_microusd"])
    elif fault == "financial-job":
        job = entry["financial"]["job"][0]
        job["cancel"] = int(job["cancel"])
        rejected["jobs"][job["id"]]["cancel"] = job["cancel"]
    elif fault == "rejected-jobs":
        job = next(iter(rejected["jobs"].values()))
        job["cancel"] = int(job["cancel"])
    elif fault == "rejected-job":
        rejected["job"]["budget"] = float(rejected["job"]["budget"])
    elif fault == "rejected-assignments":
        account = next(iter(rejected["assignments"].values()))
        account["limit_microusd"] = float(account["limit_microusd"])
    else:
        account = rejected["account"]
        account["limit_microusd"] = float(account["limit_microusd"])
    # Equal-value substitutions pass the shared SQLite comparison but not the native witness.
    assert entry == before
    assert_preparation(entry, fixture, manifest, watch)
    assert_cohort_refusal(entry, stages, error, watch, case=case, target_job=target)
    if fault in {"manifest-cap", "financial-job"}:
        with pytest.raises(AssertionError):
            assert_native_preparation(entry, fixture, manifest, watch)
    else:
        with pytest.raises(AssertionError):
            assert_native_cohort_refusal(entry, stages, error, watch, case=case, target_job=target)
