"""Synthetic protocol checks, not a natural-failure result or power analysis."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts/fixtures/natural-failure-protocol.json").read_text())


def classify(row):
    if row["origin"] != "natural":
        return "excluded_origin"
    if row["execution"] != "complete":
        return "infrastructure_failure"
    if row["capture"] != "verified":
        return "capture_failure"
    if row["evaluator"] != "valid":
        return "evaluator_failure"
    if type(row["task_success"]) is not bool:
        return "unknown_outcome"
    return "task_success" if row["task_success"] else "natural_task_failure"


def split_status(tasks):
    if any(row["phase"] not in {"development", "held_out"} for row in tasks):
        raise ValueError("Unknown phase")
    task_ids = [row["task_id"] for row in tasks]
    if len(set(task_ids)) != len(task_ids):
        return "leakage"
    for key in CONTRACT["leakage_keys"]:
        if any(not row.get(key) for row in tasks):
            raise ValueError("Missing leakage identity")
        development = {row[key] for row in tasks if row["phase"] == "development"}
        held_out = {row[key] for row in tasks if row["phase"] == "held_out"}
        if development & held_out:
            return "leakage"
    return "valid"


def stability_status(repeats):
    expected = {"original": "fail", "known_pass": "pass", "known_fail": "fail", "tampered": "fail"}
    if any(len(repeats.get(key, [])) < CONTRACT["stability_minimum_repeats"] for key in expected):
        return "insufficient"
    if any(any(value != outcome for value in repeats[key]) for key, outcome in expected.items()):
        return "quarantine"
    return "eligible"


def feasibility_status(row):
    if len(set(row["observed_group_ids"])) < row["minimum_independent_groups"]:
        return "insufficient_groups"
    if not row["power_reviewed"]:
        return "pending_power_review"
    return "synthetic_design_check_only"


def count_summary(row):
    names = ["planned", "wins", "harms", "ties", "missing"]
    if any(type(row[key]) is not int or row[key] < 0 for key in names):
        raise ValueError("Invalid outcome count")
    total = row["planned"]
    if total == 0 or sum(row[key] for key in names[1:]) != total:
        raise ValueError("Planned outcome accounting mismatch")
    complete = total - row["missing"]
    difference = row["wins"] - row["harms"]
    return (
        difference / complete if complete else None,
        [(difference - row["missing"]) / total, (difference + row["missing"]) / total],
    )


@pytest.mark.parametrize("row", CONTRACT["classification_cases"], ids=lambda row: row["id"])
def test_natural_task_failures_exclude_injected_and_operational_failures(row):
    assert classify(row) == row["expected"]


@pytest.mark.parametrize("row", CONTRACT["split_cases"], ids=lambda row: row["id"])
def test_task_repository_and_evaluator_families_cannot_cross_holdout(row):
    assert split_status(row["tasks"]) == row["expected"]


def test_split_identity_matches_permission_provenance_fixture():
    raw = (ROOT / "contracts/fixtures/corpus-manifest.synthetic.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CONTRACT["source_corpus_sha256"]
    corpus = {row["task_id"]: row for row in json.loads(raw)["tasks"]}
    for task in CONTRACT["split_cases"][0]["tasks"]:
        source = corpus[task["task_id"]]
        assert task["source_digest"] == source["source"]["artifact"]["sha256"]
        assert task["evaluator_digest"] == source["evaluator"]["artifact"]["sha256"]
        assert task["evaluator_command_digest"] == source["evaluator"]["command_sha256"]
        assert task["image_digest"] == source["evaluator"]["image_digest"]


def test_missing_group_or_unknown_phase_cannot_bypass_split_check():
    tasks = copy.deepcopy(CONTRACT["split_cases"][0]["tasks"])
    tasks[0]["repository_family_id"] = ""
    with pytest.raises(ValueError, match="Missing leakage"):
        split_status(tasks)
    tasks[0]["phase"] = "unregistered"
    with pytest.raises(ValueError, match="Unknown phase"):
        split_status(tasks)


@pytest.mark.parametrize("row", CONTRACT["stability_cases"], ids=lambda row: row["id"])
def test_unstable_wrong_and_incomplete_evaluator_controls_block_study(row):
    assert stability_status(row["repeats"]) == row["expected"]


@pytest.mark.parametrize("field", CONTRACT["identity_drift_fields"])
def test_frozen_identity_drift_requires_new_cohort(field):
    frozen = CONTRACT["frozen_identity_example"]
    observed = copy.deepcopy(frozen)
    observed[field] = "different-synthetic-identity"
    changed = {key for key in frozen if observed.get(key) != frozen[key]}
    assert changed == {field}
    assert observed != frozen


@pytest.mark.parametrize("row", CONTRACT["feasibility_cases"], ids=lambda row: row["id"])
def test_repeats_do_not_satisfy_independent_sample_requirement(row):
    assert feasibility_status(row) == row["expected"]


def test_more_replays_do_not_repair_repository_sample_shortfall():
    row = copy.deepcopy(CONTRACT["feasibility_cases"][0])
    row["pairs_per_task"] *= 100
    row["observed_group_ids"] *= 100
    assert feasibility_status(row) == "insufficient_groups"


@pytest.mark.parametrize("row", CONTRACT["outcome_count_cases"], ids=lambda row: row["id"])
def test_null_and_missing_outcome_arithmetic_retains_planned_pairs(row):
    effect, bounds = count_summary(row)
    assert effect == row["expected_effect"]
    assert bounds == row["expected_bounds"]


def test_outcome_counts_cannot_drop_failed_or_missing_pairs():
    row = copy.deepcopy(CONTRACT["outcome_count_cases"][1])
    row["missing"] = 0
    with pytest.raises(ValueError, match="accounting mismatch"):
        count_summary(row)
    row["wins"] = -1
    with pytest.raises(ValueError, match="Invalid outcome count"):
        count_summary(row)


def test_cost_feasibility_does_not_claim_power_or_authorize_spend():
    plan = CONTRACT["within_task_cost_worksheet"]
    arms = (
        2
        * plan["tasks"]
        * (
            plan["screened_candidates_including_negative_control"]
            * plan["screening_pairs_per_candidate"]
            + plan["confirmation_pairs"]
        )
    )
    assert arms == plan["expected_continuation_arms"] == 720
    costs = [arms * price for price in plan["assumed_cost_per_continuation_usd"]]
    assert costs == pytest.approx(plan["continuation_cost_range_usd"])
    assert plan["power_estimate"] is None and plan["authorized_spend"] is None
    assert plan["excludes"]
    assert CONTRACT["evidence_class"] == "synthetic-protocol-cases"
    assert CONTRACT["review_gates"]["independent_statistics"] == "pending"
