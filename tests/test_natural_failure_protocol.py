"""Synthetic protocol checks, not a natural-failure result or power analysis."""

import copy
import hashlib
import json
import re
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


def identity_status(frozen, observed):
    """Bounded design oracle; runtime study admission is a later implementation."""
    contract = CONTRACT["identity_contract"]
    required = set(contract["required_fields"])
    for identity in (frozen, observed):
        if not isinstance(identity, dict) or len(identity) != len(required):
            return "quarantine"
        if set(identity) != required:
            return "quarantine"
        for key, value in identity.items():
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= contract["maximum_value_characters"]
            ):
                return "quarantine"
            if key in contract["digest_fields"]:
                pattern = r"[0-9a-f]{64}"
            elif key in contract["revision_fields"]:
                pattern = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
            else:
                pattern = r"[A-Za-z0-9._:-]{1,128}"
            if re.fullmatch(pattern, value) is None:
                return "quarantine"
    return "compatible" if frozen == observed else "quarantine"


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


def test_complete_identity_contract_covers_declared_frozen_boundary():
    contract = CONTRACT["identity_contract"]
    required = {
        "protocol_revision",
        "protocol_digest",
        "eligibility_digest",
        "corpus_digest",
        "split_manifest_digest",
        "task_digest",
        "source_revision",
        "checkpoint_digest",
        "event_chain_head",
        "model_revision",
        "provider_fingerprint",
        "fingerprint_policy_digest",
        "processor_profile_id",
        "adapter_digest",
        "prompt_digest",
        "configuration_digest",
        "image_digest",
        "tool_policy_digest",
        "evaluator_digest",
        "evaluator_command_digest",
        "budget_policy_digest",
        "candidate_procedure_digest",
    }
    assert set(contract["required_fields"]) == required
    assert len(contract["required_fields"]) == len(required)
    groups = [set(contract[name]) for name in ("digest_fields", "revision_fields", "named_fields")]
    assert set.union(*groups) == required
    assert sum(map(len, groups)) == len(required)
    frozen = CONTRACT["frozen_identity_example"]
    assert identity_status(frozen, copy.deepcopy(frozen)) == "compatible"


@pytest.mark.parametrize("field", CONTRACT["identity_drift_fields"])
def test_frozen_identity_drift_quarantines_comparison(field):
    frozen = CONTRACT["frozen_identity_example"]
    observed = copy.deepcopy(frozen)
    if field in CONTRACT["identity_contract"]["digest_fields"]:
        observed[field] = "f" * 64
    elif field in CONTRACT["identity_contract"]["revision_fields"]:
        observed[field] = "f" * 40
    else:
        observed[field] = "different-synthetic-identity"
    assert identity_status(frozen, observed) == "quarantine"


@pytest.mark.parametrize("field", CONTRACT["identity_contract"]["required_fields"])
@pytest.mark.parametrize("side", ["frozen", "observed"])
def test_missing_required_identity_field_quarantines_comparison(field, side):
    identities = {
        name: copy.deepcopy(CONTRACT["frozen_identity_example"]) for name in ("frozen", "observed")
    }
    del identities[side][field]
    assert identity_status(**identities) == "quarantine"


@pytest.mark.parametrize("side", ["frozen", "observed"])
def test_unexpected_identity_field_quarantines_comparison(side):
    identities = {
        name: copy.deepcopy(CONTRACT["frozen_identity_example"]) for name in ("frozen", "observed")
    }
    identities[side]["unregistered_state"] = "synthetic"
    assert identity_status(**identities) == "quarantine"


@pytest.mark.parametrize("value", [None, 1, "", "not-a-digest", "f" * 129])
def test_invalid_identity_values_are_quarantined_even_when_equal(value):
    frozen = copy.deepcopy(CONTRACT["frozen_identity_example"])
    frozen["evaluator_digest"] = value
    assert identity_status(frozen, copy.deepcopy(frozen)) == "quarantine"


def test_equal_missing_or_extra_identities_are_not_compatible():
    frozen = copy.deepcopy(CONTRACT["frozen_identity_example"])
    del frozen["checkpoint_digest"]
    assert identity_status(frozen, copy.deepcopy(frozen)) == "quarantine"
    frozen["unregistered_state"] = "synthetic"
    assert identity_status(frozen, copy.deepcopy(frozen)) == "quarantine"


def test_split_rejects_missing_evaluator_content_and_permits_generic_sharing():
    tasks = copy.deepcopy(CONTRACT["split_cases"][0]["tasks"])
    assert tasks[0]["image_digest"] == tasks[1]["image_digest"]
    assert tasks[0]["evaluator_command_digest"] == tasks[1]["evaluator_command_digest"]
    assert split_status(tasks) == "valid"
    del tasks[1]["evaluator_digest"]
    with pytest.raises(ValueError, match="Missing leakage"):
        split_status(tasks)


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
