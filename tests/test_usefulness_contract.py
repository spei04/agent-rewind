"""Test-only arithmetic oracle for the proposed measurement contract."""

import copy
import json
import math
import statistics
from pathlib import Path

import pytest

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts/fixtures/usefulness.json").read_text()
)
TARGETS = CONTRACT["targets"]


def require_unique(rows, key):
    identifiers = [row[key] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate measurement identity")


def capture_summary(case):
    rows = case["attempts"]
    require_unique(rows, "attempt_id")
    eligible = [row for row in rows if row["eligible_at_registration"]]
    restored = sum(row["outcome"] == "captured_and_restored" for row in eligible)
    rate = restored / len(eligible) if eligible else None
    return {
        "eligible_count": len(eligible),
        "unsupported_count": len(rows) - len(eligible),
        "restored_count": restored,
        "capture_rate": rate,
        "target_state": (
            "insufficient"
            if rate is None
            else "met"
            if rate >= TARGETS["capture_rate"]
            else "not_met"
        ),
    }


def timing_summary(case):
    pairs = case["pairs"]
    require_unique(pairs, "case_id")
    reviewed = []
    for pair in pairs:
        for arm in (pair["baseline"], pair["rewind"]):
            duration = arm["active_minutes"]
            if duration is not None and (duration < 0 or not math.isfinite(duration)):
                raise ValueError("Invalid duration")
        if all(
            pair[arm]["state"] == "reviewed" and pair[arm]["active_minutes"] is not None
            for arm in ("baseline", "rewind")
        ):
            reviewed.append(pair)
    baseline = (
        statistics.median(row["baseline"]["active_minutes"] for row in reviewed) if reviewed else 0
    )
    rewind = (
        statistics.median(row["rewind"]["active_minutes"] for row in reviewed) if reviewed else 0
    )
    reduction = 1 - rewind / baseline if baseline else None
    if len(pairs) < TARGETS["minimum_timing_cases"]:
        state = "insufficient"
    elif len(reviewed) != len(pairs) or reduction is None:
        state = "inconclusive"
    else:
        state = "met" if reduction >= TARGETS["timing_reduction"] else "not_met"
    return {
        "case_count": len(pairs),
        "attempt_count": len(pairs) * 2,
        "reviewed_pair_count": len(reviewed),
        "descriptive_reduction": reduction,
        "target_state": state,
    }


def pilot_summary(case):
    organizations = {"partner-a", "partner-b"}
    rows = case["weekly_use"]
    keys = [(row["organization_id"], row["week"]) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate organization/week")
    required = {(organization, week) for organization in organizations for week in range(1, 5)}
    if not set(keys) <= required:
        raise ValueError("Unregistered organization/week")
    used = {(row["organization_id"], row["week"]) for row in rows if row["reviewed_reports"] > 0}
    adopted = {
        row["organization_id"]
        for row in case["adoptions"]
        if row["owner_reviewed"]
        and row["source_report_id"]
        and row["accepted_revision"]
        and row["change_kind"] in {"regression", "policy_fix"}
    }
    return "met" if used == required and adopted >= organizations else "not_met"


@pytest.mark.parametrize("case", CONTRACT["capture_cases"], ids=lambda case: case["id"])
def test_capture_includes_failed_and_abandoned_attempts(case):
    assert capture_summary(case) == case["expected"]


@pytest.mark.parametrize("case", CONTRACT["timing_cases"], ids=lambda case: case["id"])
def test_timing_complete_incomplete_and_insufficient_cohorts(case):
    actual = timing_summary(case)
    expected = case["expected"]
    assert actual == expected


@pytest.mark.parametrize("case", CONTRACT["pilot_cases"], ids=lambda case: case["id"])
def test_two_partners_need_every_week_and_actual_adoption(case):
    assert pilot_summary(case) == case["expected"]


@pytest.mark.parametrize(
    "family,key,summarizer",
    [
        ("capture_cases", "attempts", capture_summary),
        ("timing_cases", "pairs", timing_summary),
        ("pilot_cases", "weekly_use", pilot_summary),
    ],
)
def test_duplicate_identities_are_rejected(family, key, summarizer):
    case = copy.deepcopy(CONTRACT[family][0])
    case[key].append(copy.deepcopy(case[key][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        summarizer(case)


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan")])
def test_invalid_timing_cannot_improve_result(duration):
    case = copy.deepcopy(CONTRACT["timing_cases"][0])
    case["pairs"][0]["rewind"]["active_minutes"] = duration
    with pytest.raises(ValueError, match="Invalid duration"):
        timing_summary(case)


def test_missing_duration_and_zero_baseline_are_inconclusive():
    case = copy.deepcopy(CONTRACT["timing_cases"][0])
    case["pairs"][0]["rewind"]["active_minutes"] = None
    assert timing_summary(case)["target_state"] == "inconclusive"
    for pair in case["pairs"]:
        pair["baseline"]["active_minutes"] = 0
        pair["rewind"]["active_minutes"] = 0
    assert timing_summary(case)["target_state"] == "inconclusive"
    assert timing_summary(case)["descriptive_reduction"] is None


def test_no_effect_or_uncertainty_does_not_remove_useful_work():
    case = CONTRACT["timing_cases"][0]
    assert {pair["rewind"]["report_outcome"] for pair in case["pairs"]} == {
        "positive",
        "no_effect",
        "uncertain",
        "harmful",
    }
    assert timing_summary(case)["reviewed_pair_count"] == 20
    pilot = CONTRACT["pilot_cases"][0]
    assert all("positive" not in row["outcomes"] for row in pilot["weekly_use"])
    assert pilot_summary(pilot) == "met"
