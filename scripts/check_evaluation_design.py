"""Bounded design oracles and offline integrity checks, never runtime authorization."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_097_152
STAGES = {
    "baseline_capture",
    "diagnosis",
    "proposal",
    "restore",
    "replay",
    "grading",
    "confirmation",
    "failed_attempt",
    "uncertain_attempt",
    "offline_preparation",
}
SCOPE = {"project_id", "study_id", "method_id", "task_id", "policy_run_id"}
GATE_CHOICES = {
    "internal_design_review",
    "owner_baseline_information_choice",
    "owner_thresholds_for_calibration",
    "owner_followup_scope_choice",
    "owner_nested_protocol_disposition",
}
DECISION_IDENTITY = SCOPE | {"policy_digest", "policy_state_digest", "candidate_digest"}
REQUIRED_C08_IDENTITY = {
    "phase",
    "task_id",
    "repository_family_id",
    "checkpoint_digest",
    "method_id",
    "model_revision",
    "evaluator_digest",
    "candidate_digest",
    "adapter_digest",
    "sample_plan_digest",
    "policy_digest",
    "environment_digest",
    "event_chain_digest",
    "policy_state_digest",
    "decision_id",
    "provider_fingerprint_policy",
    "policy_run_id",
    "price_revision",
    "resource_cap_digest",
    "allowed_observation_manifest_digest",
    "project_id",
    "protocol_digest",
    "study_id",
}
REQUIRED_C08_RECEIPTS = {
    "lease_generation",
    "reserve_transfer",
    "reconciliation_parent_id",
    "source_decision_id",
    "settled_charge",
    "outcome_taxonomy",
    "attempt_id",
    "quote_bound",
    "comparison_allocation_id",
    "reservation_id",
    "held_charge",
    "logical_call_id",
    "observed_receipt_ids",
    "physical_invoice_id",
}
LEAKAGE_KEYS = {
    "repository_family_id",
    "task_family_id",
    "task_specific_evaluator_digest",
    "derived_patch_family_id",
}
ALLOWED_OBSERVATIONS = {
    "registered_task_input",
    "factual_prefix",
    "task_local_discovery_outcomes",
    "task_local_discovery_cost_receipts",
}
FORBIDDEN_OBSERVATIONS = {
    "sealed_confirmation",
    "other_heldout_task_outcomes",
    "hidden_expected_answers_in_answer_blind_stratum",
}
CARD_FIELDS = {
    "id",
    "title",
    "maps_to",
    "objective",
    "scope",
    "out_of_scope",
    "dependencies",
    "contracts",
    "acceptance",
    "automated_tests",
    "security_reliability",
    "effort_days",
    "confidence",
    "responsible_role",
    "review_roles",
    "definition_of_done",
    "pr_boundary",
    "conditions",
    "authorized",
    "effort_kind",
    "effort_overlap",
}
EFFORT_KINDS = {
    "producer_amendment",
    "existing_scope_amendment",
    "net_new_optional_scope",
    "replacement_study_scope",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nonnegative(value: Any) -> bool:
    return type(value) is int and value >= 0


def budget_decision(row: dict[str, Any]) -> str:
    """Hand-checkable single-coordinate admission example, not a ledger."""
    names = ("cap", "settled", "held", "uncertain", "reserve", "required_reserve")
    require(all(nonnegative(row[name]) for name in names), "invalid budget amount")
    require(row["uncertain"] <= row["held"], "uncertainty must remain inside held")
    quote = row["quote"]
    if not nonnegative(quote):
        return "refuse_quote"
    exposure = row["settled"] + row["held"] + row["reserve"]
    if exposure > row["cap"]:
        return "refuse_cap"
    if row["purpose"] == "recovery_only":
        require(
            row["phase"] == "retry" and row["reserve"] == row["required_reserve"] == 0,
            "recovery-only method cannot reserve nonexistent confirmation",
        )
    else:
        require(row["purpose"] == "intervention", "unknown budget purpose")
        require(row["required_reserve"] > 0, "intervention plan needs full reserve quote")
        if row["phase"] == "confirmation":
            return "admit" if quote <= row["reserve"] else "refuse_reserve"
        require(row["phase"] == "discovery", "unknown budget phase")
        if row["reserve"] < row["required_reserve"]:
            return "refuse_reserve"
    return "admit" if exposure + quote <= row["cap"] else "refuse_cap"


def confirmation_transfer(row: dict[str, Any]) -> tuple[int, int, int]:
    require(row["phase"] == "confirmation" and budget_decision(row) == "admit", "transfer refused")
    return row["settled"], row["held"] + row["quote"], row["reserve"] - row["quote"]


def settled_example(held_quote: int, charge: int | None) -> tuple[str, int]:
    """Return disposition and releasable amount; missing evidence releases nothing."""
    require(nonnegative(held_quote), "invalid held quote")
    if charge is None:
        return "held", 0
    require(nonnegative(charge), "invalid final charge")
    if charge > held_quote:
        return "breach_freeze", 0
    return "settled", held_quote - charge


def method_closure(row: dict[str, Any]) -> None:
    require(
        all(nonnegative(row[key]) for key in ("cap", "offline", "shared"))
        and isinstance(row["task_caps"], list)
        and bool(row["task_caps"])
        and all(nonnegative(value) for value in row["task_caps"]),
        "method cap inputs",
    )
    require(
        row["offline"] + row["shared"] + sum(row["task_caps"]) <= row["cap"], "method total cap"
    )


def shared_costs(row: dict[str, Any]) -> None:
    invoices = row["physical_invoices"]
    require(isinstance(invoices, list) and bool(invoices), "physical invoice list")
    require(len({x["id"] for x in invoices}) == len(invoices), "duplicate physical invoice")
    require(all(nonnegative(x["amount"]) for x in invoices), "physical invoice amount")
    require(sum(x["amount"] for x in invoices) == row["physical_total"], "physical total")
    require(
        nonnegative(row["required_attribution"])
        and row["required_attribution"] > 0
        and row["required_attribution"] == row["physical_total"],
        "full-pool attribution must equal physical input total",
    )
    require(
        bool(row["method_charges"])
        and all(
            nonnegative(value) and value == row["required_attribution"]
            for value in row["method_charges"].values()
        ),
        "shared inputs must receive equal full attribution",
    )


def frozen_body(plan: dict[str, Any], expected_digest: str) -> dict[str, Any]:
    """Digest consistency of a separate synthetic plan, never owner authorization."""
    require(set(plan) == {"body", "digest"} and isinstance(plan["body"], dict), "frozen plan shape")
    calculated = hashlib.sha256(
        json.dumps(plan["body"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    require(calculated == plan["digest"] == expected_digest, "frozen plan digest changed")
    return dict(plan["body"])


def phase_check(row: dict[str, Any], plan: dict[str, Any]) -> None:
    frozen = frozen_body(plan, row["sample_plan_digest"])
    require(
        set(frozen) == {"identity", "discovery_attempts", "confirmation_attempts"},
        "attempt plan fields",
    )
    require(row["identity"] == frozen["identity"], "changed frozen decision identity")
    require(
        row["discovery_attempts"] == frozen["discovery_attempts"]
        and row["confirmation_attempts"] == frozen["confirmation_attempts"],
        "attempt phases differ from frozen registration",
    )
    require(row["phase"] == "freeze" and row["optional_stop"] is False, "fixed phase boundary")
    expected, observed = row["expected_identity"], row["identity"]
    require(set(expected) == set(observed) == DECISION_IDENTITY, "complete decision identity")
    require(all(isinstance(value, str) and value for value in expected.values()), "identity value")
    require(expected == observed, "changed decision policy/state identity")
    discovery, confirmation = row["discovery_attempts"], row["confirmation_attempts"]
    require(
        len(set(discovery)) == len(discovery) and len(set(confirmation)) == len(confirmation),
        "duplicate analytical attempt",
    )
    require(bool(confirmation) and not set(discovery) & set(confirmation), "fresh phase attempts")
    for receipt in row["observed"]:
        require(receipt["phase"] == "discovery", "confirmation or foreign phase feedback")
        require(all(receipt[key] == observed[key] for key in SCOPE), "foreign receipt scope")
        require(receipt["attempt_id"] in discovery, "unregistered discovery receipt")


def task_credit(task_ids: list[str]) -> int:
    require(len(task_ids) == len(set(task_ids)), "duplicate task credit")
    return len(task_ids)


def recovery_report(row: dict[str, Any]) -> tuple[None, tuple[float, float]]:
    require(row["method_kind"] == "fresh_retry", "this example is recovery-only")
    names = ("assigned_tasks", "successes", "failures", "missing")
    require(all(nonnegative(row[name]) for name in names), "outcome counts")
    count = row["assigned_tasks"]
    require(count > 0 and sum(row[x] for x in names[1:]) == count, "complete recovery denominator")
    return None, (row["successes"] / count, (row["successes"] + row["missing"]) / count)


def family_check(row: dict[str, Any], plan: dict[str, Any]) -> tuple[float, float]:
    """Fixed allocation arithmetic only; no statistical interval is implemented."""
    frozen = frozen_body(plan, row["family_plan_digest"])
    require(
        set(frozen) == {"methods", "tasks", "reuse_claims", "population_contrasts"},
        "family plan fields",
    )
    for values in frozen.values():
        require(
            isinstance(values, list)
            and len(values) == len(set(values))
            and all(isinstance(value, str) and value for value in values),
            "family plan inventory",
        )
    require(
        bool(frozen["methods"]) and bool(frozen["tasks"]) and bool(frozen["population_contrasts"]),
        "empty planned family",
    )
    require(
        all(nonnegative(value) for key, value in row.items() if key != "family_plan_digest"),
        "family integer inputs",
    )
    require(
        row["planned_confirmation_claims"]
        == len(frozen["methods"]) * len(frozen["tasks"]) + len(frozen["reuse_claims"])
        and row["planned_population_contrasts"] == len(frozen["population_contrasts"]),
        "family count differs from frozen inventory",
    )
    total, confirmation, population = (
        row["family_alpha_micros"],
        row["confirmation_alpha_micros"],
        row["population_alpha_micros"],
    )
    require(
        0 < total < 1_000_000
        and confirmation > 0
        and population > 0
        and confirmation + population == total,
        "family alpha allocation",
    )
    planned, contrasts = row["planned_confirmation_claims"], row["planned_population_contrasts"]
    require(
        planned > 0 and contrasts > 0 and row["selected_confirmation_claims"] <= planned,
        "planned claim counts",
    )
    require(
        row["confirmation_divisor"] == planned and row["population_divisor"] == contrasts,
        "full planned family required",
    )
    return confirmation / 1_000_000 / planned, population / 1_000_000 / contrasts


def comparison_check(row: dict[str, Any]) -> None:
    """Allocation ablation only, not heterogeneous end-to-end methods."""
    require(row["kind"] == "allocation_only_common_pool", "comparison estimand")
    methods = row["methods"]
    require(isinstance(methods, list) and len(methods) >= 2, "comparison methods")
    require(len({method["id"] for method in methods}) == len(methods), "duplicate method")
    fields = {
        "model_revision",
        "information_stratum",
        "allowed_observation_digest",
        "proposal_pool_digest",
        "caps",
    }
    for method in methods:
        require(set(method) == fields | {"id"}, "comparison identity fields")
        require(
            all(isinstance(method[key], str) and method[key] for key in fields - {"caps"}),
            "comparison identity values",
        )
        require(
            set(method["caps"])
            == {"usd_micros", "calls", "tokens", "cpu_seconds", "wall_seconds", "concurrency"}
            and all(nonnegative(x) and x > 0 for x in method["caps"].values()),
            "complete comparison caps",
        )
        require(
            all(method[key] == methods[0][key] for key in fields),
            "asymmetric comparison information/resources",
        )


def consumer_ready(gate: dict[str, Any]) -> bool:
    return (
        set(gate["requires"]) == GATE_CHOICES
        and len(gate["requires"]) == len(GATE_CHOICES)
        and set(gate["decisions"]) == set(gate["requires"])
        and all(gate["decisions"][key] == "approved" for key in gate["requires"])
    )


def validate_followups(data: dict[str, Any], ledger: dict[str, Any], document: str) -> None:
    original = {row["id"]: row for row in ledger["tasks"] + ledger["gates"]}
    require(
        len(original) == len(ledger["tasks"]) + len(ledger["gates"]), "duplicate ledger identity"
    )
    rows = data["followups"]
    cards = {row["id"]: row for row in rows}
    require(
        len(cards) == len(rows) and not set(cards) & set(original), "duplicate follow-up identity"
    )
    gate = data["consumer_gate"]
    if gate["id"] in original:
        require(
            original[gate["id"]]["effort_days"] == 0
            and set(original[gate["id"]]["dependencies"]) == set(gate["dependencies"]),
            "existing owner gate differs",
        )
    graph = {key: set(row["dependencies"]) for key, row in original.items()}
    graph[gate["id"]] = set(gate["dependencies"])
    for consumer in gate["consumers"]:
        require(consumer in graph, "missing original consumer")
        graph[consumer].add(gate["id"])
    for identity, row in cards.items():
        require(set(row) == CARD_FIELDS, "complete follow-up card")
        require(row["authorized"] is False, "follow-up cannot authorize implementation")
        require(row["confidence"] == "low" and row["effort_kind"] in EFFORT_KINDS, "estimate kind")
        days = row["effort_days"]
        require(
            isinstance(days, list)
            and len(days) == 2
            and all(nonnegative(day) for day in days)
            and 0 < days[0] <= days[1],
            "effort range",
        )
        require(row["maps_to"] in original, "unknown integration owner")
        require(
            bool(row["dependencies"]) and len(set(row["dependencies"])) == len(row["dependencies"]),
            "dependency list",
        )
        for key in CARD_FIELDS - {
            "dependencies",
            "contracts",
            "effort_days",
            "review_roles",
            "conditions",
            "authorized",
        }:
            require(isinstance(row[key], str) and bool(row[key].strip()), "empty card field")
        require(
            isinstance(row["contracts"], list)
            and bool(row["contracts"])
            and len(set(row["contracts"])) == len(row["contracts"])
            and isinstance(row["review_roles"], list)
            and bool(row["review_roles"])
            and isinstance(row["conditions"], list),
            "card contracts/reviews/conditions",
        )
        graph[identity] = set(row["dependencies"])
        heading = f"### {identity} — {row['title']}"
        require(document.count(heading) == 1, "card/document identity drift")
        section = document.split(heading, 1)[1].split("\n### ", 1)[0]
        for key in (
            "objective",
            "scope",
            "out_of_scope",
            "acceptance",
            "automated_tests",
            "security_reliability",
            "definition_of_done",
            "effort_overlap",
            "effort_kind",
        ):
            require(row[key] in section, f"card/document drift: {key}")
        require(f"{days[0]}–{days[1]} engineering days" in section, "card/document effort drift")
        dependency_lines = [
            line.removeprefix("- **Dependencies:** ")
            for line in section.splitlines()
            if line.startswith("- **Dependencies:** ")
        ]
        contract_lines = [
            line.removeprefix("- **Contracts:** ")
            for line in section.splitlines()
            if line.startswith("- **Contracts:** ")
        ]
        require(len(dependency_lines) == len(contract_lines) == 1, "card link fields")
        dependency_text, separator, owner = dependency_lines[0].partition(". Integration owner: ")
        dependency_ids = dependency_text.split(", ")
        require(
            bool(separator)
            and owner == f"{row['maps_to']}; original prerequisites remain."
            and len(dependency_ids) == len(set(dependency_ids))
            and set(dependency_ids) == set(row["dependencies"]),
            "card/document dependency drift",
        )
        contract_text, separator, suffix = contract_lines[0].partition("; ")
        contract_ids = contract_text.split(", ")
        require(
            bool(separator)
            and suffix == "producer acceptance is not granted here."
            and len(contract_ids) == len(set(contract_ids))
            and set(contract_ids) == set(row["contracts"]),
            "card/document contract drift",
        )
    ancestors: dict[str, set[str]] = {}

    def visit(identity: str, active: set[str]) -> set[str]:
        require(identity in graph, "unknown prerequisite")
        require(identity not in active, "dependency cycle")
        if identity not in ancestors:
            closure = set(graph[identity])
            for dep in graph[identity]:
                closure |= visit(dep, active | {identity})
            ancestors[identity] = closure
        return ancestors[identity]

    producers = {row["id"]: row["producer"] for row in ledger["contracts"]}
    for identity, row in cards.items():
        closure = visit(identity, set())
        require(gate["id"] in closure, "owner gate missing from follow-up ancestry")
        for contract in row["contracts"]:
            require(contract in producers, "unknown required contract")
            producer = producers[contract]
            if producer and not (
                row["effort_kind"] == "producer_amendment" and producer == row["maps_to"]
            ):
                require(producer in closure, "required contract producer missing")
    for consumer in gate["consumers"]:
        visit(consumer, set())


def validate(data: dict[str, Any], ledger: dict[str, Any], document: str) -> None:
    require(data["schema_version"] == 1 and data["design_id"] == "RA-01-B", "design identity")
    require(data["status"] == "proposed_design", "design status")
    require(
        data["authorization"]
        == {
            "design_only": True,
            "runtime_authorized": False,
            "paid_evaluation_authorized": False,
            "heldout_access_authorized": False,
        },
        "design-only authority",
    )
    gate = data["consumer_gate"]
    require(
        gate["id"] == "RESEARCHSCOPE0"
        and gate["record_kind"] == "synthetic_pending_decision_template"
        and gate["effort_days"] == 0
        and gate["dependencies"] == ["RA-01-B"]
        and set(gate["consumers"]) == {"AR-020-A", "AR-024-A"}
        and set(gate["requires"]) == GATE_CHOICES
        and len(gate["requires"]) == len(GATE_CHOICES),
        "owner gate contract",
    )
    require(
        gate["status"] == "pending"
        and gate["consumer_ready"] is False
        and not consumer_ready(gate)
        and set(gate["decisions"]) == set(gate["requires"])
        and all(value == "pending" for value in gate["decisions"].values()),
        "unresolved owner choices cannot unlock consumers",
    )
    policy = data["policy"]
    require(
        policy["adaptation_scope"] == "within_task_only"
        and policy["cross_task_outcome_transfer"] is False
        and policy["confirmation_feedback"] is False
        and policy["optional_confirmation_stopping"] is False
        and policy["maximum_frozen_candidates_per_method_task"] == 1
        and policy["current_c02_authoritative"] is True
        and policy["nested_holdout_execution_approved"] is False,
        "phase/holdout policy",
    )
    for key, required in (
        ("outer_leakage_keys", LEAKAGE_KEYS),
        ("allowed_discovery_observations", ALLOWED_OBSERVATIONS),
        ("forbidden_observations", FORBIDDEN_OBSERVATIONS),
    ):
        require(
            isinstance(policy[key], list)
            and set(policy[key]) == required
            and len(policy[key]) == len(required),
            "complete narrow information/split contract",
        )
    thresholds = data["thresholds"]
    require(
        thresholds["status"] == "pending_owner_and_external_review"
        and thresholds["paired_harm_reporting"] == "descriptive_with_coupling"
        and thresholds["pilot_numbers"]["power_guarantee"] is False
        and thresholds["feasibility_status"] == "not_demonstrated",
        "statistical choices remain pending",
    )
    accounting = data["accounting"]
    require(accounting["unit"] == "usd_micros", "explicit accounting unit")
    require(set(accounting["required_stages"]) == STAGES, "offline or attempt costs omitted")
    for key in (
        "physical_and_comparison_separate",
        "shared_input_full_charge_per_method",
        "one_shot_primary",
        "amortized_reuse_frozen_before_outcomes",
        "no_cross_task_budget_reallocation",
        "quote_required",
    ):
        require(accounting[key] is True, "cost fairness/closure invariant")
    contract = data["receipt_contract"]
    require(
        contract["producer"] == "AR-020-A" and contract["report_contract_producer"] == "AR-024-A",
        "original C08/C09 producers",
    )
    require(
        set(contract["identity_fields"]) == REQUIRED_C08_IDENTITY
        and len(set(contract["identity_fields"])) == len(contract["identity_fields"])
        and set(contract["receipt_fields"]) == REQUIRED_C08_RECEIPTS
        and len(set(contract["receipt_fields"])) == len(contract["receipt_fields"]),
        "complete required C08 identity/receipt fields",
    )
    for case in data["budget_cases"]:
        require(budget_decision(case) == case["expected"], "budget example decision")
    method_closure(data["method_budget_case"])
    shared_costs(data["shared_case"])
    phase_check(data["phase_case"], data["phase_plan"])
    family_check(data["family_case"], data["family_plan"])
    comparison_check(data["comparison_case"])
    yield_value, bounds = recovery_report(data["recovery_case"])
    require(
        yield_value is data["recovery_case"]["expected_intervention_yield"]
        and list(bounds) == data["recovery_case"]["expected_recovery_bounds"],
        "retry recovery applicability",
    )
    validate_followups(data, ledger, document)


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def bounded_text(path: Path) -> str:
    # Nonblocking open prevents a mistakenly supplied FIFO from hanging CI.
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "input must be a regular file")
        require(info.st_size <= MAX_BYTES, "input too large")
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input too large")
    return raw.decode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(bounded_text(path), object_pairs_hook=unique_pairs)
    require(isinstance(data, dict), "JSON root must be an object")
    return dict(data)


def read_inputs() -> tuple[dict[str, Any], dict[str, Any], str]:
    return (
        load_json(ROOT / "contracts/research/evaluation-design.json"),
        load_json(ROOT / "contracts/proposals/execution-backlog.json"),
        bounded_text(ROOT / "docs/research/TOTAL_BUDGET_PROTOCOL.md"),
    )


APPROVED_MAPPING = {
    "RB-01": "AR-020-A",
    "RB-02": "AR-023-C",
    "RB-03": "AR-021-A",
    "RB-04": "AR-024-A",
    "RB-05": "AR-025-B",
    "RB-06": "AR-025-D",
    "RB-10": "AR-025-C",
    "RB-11A": "AR-024-D",
    "RB-11B": "AR-026-A",
}
APPROVED_LIMITS = {
    "engineering_implementation": True,
    "paid_evaluation": False,
    "heldout_execution": False,
    "optional_adapters": False,
    "reuse_claims": False,
    "customer_data": False,
    "production_resources": False,
    "external_statistical_approval": False,
    "existing_validation_cap_usd": 200,
    "historical_reservations_usd": "36.567974",
    "invoice_spend_reconciled": False,
}
APPROVED_CHOICES = {
    "information": "answer_blind",
    "core_controls": [
        "unchanged_continuation",
        "fresh_retry",
        "random_location",
        "latest_error",
        "frozen_heuristic",
    ],
    "allocation_comparison": ["uniform", "standard_successive_halving"],
    "common_pool": (
        "allocation_ablation_only; full end-to-end methods may use "
        "different fully attributed proposers"
    ),
    "useful_edit_net_lower_bound": 0.10,
    "family_alpha": 0.05,
    "power_target": 0.80,
    "population_interval_width_target": 0.20,
    "paired_discordance": "descriptive_with_coupling",
    "fresh_retry": "full_recovery_cap; intervention_endpoint_not_applicable",
    "current_c02_authoritative": True,
}
C21_COMMIT = "555d28cf21ff91d05fca30aec94a86df2510813c"
C21_RECORD_SHA256 = "07c9dad5dedcee482a229e9fe5c5df61b13f39902cee76fceeb041a3bef34e37"
C21_DOCUMENT_SHA256 = "f7f8cb2fd21baf7c99a8467ad413556e130fc647f0b9479ed6deb8c502431554"
BASELINE_PROJECTION_SHA256 = "303d22fb96cd95e1ddf29733ba40767bdf9e6ffb90f514718e0d6f1e9fe58393"


def validate_activation(
    decision: dict[str, Any], ledger: dict[str, Any], record: bytes, document: bytes
) -> None:
    """Check this reviewed overlay; consistency is not authentication of a person."""
    require(
        decision["schema_version"] == 1
        and decision["record_kind"] == "actual_owner_decision"
        and decision["decision_id"] == "RESEARCHSCOPE0-2026-10-20"
        and decision["status"] == "approved",
        "actual decision identity",
    )
    authority = decision["authority"]
    require(
        authority["owner"] == "spei04"
        and authority["date"] == "2026-10-20"
        and authority["issue"] == "https://github.com/spei04/agent-rewind/issues/51"
        and authority["source"].startswith("Explicit user conversation approval"),
        "actual decision provenance",
    )
    binding = decision["accepted_c21"]
    require(
        binding["commit"] == C21_COMMIT
        and binding["record_sha256"] == C21_RECORD_SHA256
        and binding["document_sha256"] == C21_DOCUMENT_SHA256
        and hashlib.sha256(record).hexdigest() == C21_RECORD_SHA256
        and hashlib.sha256(document).hexdigest() == C21_DOCUMENT_SHA256,
        "immutable accepted C21 binding",
    )
    require(
        decision["selected_scopes"] == list(APPROVED_MAPPING)
        and decision["deferred_scopes"] == ["RB-07", "RB-08", "RB-09", "RB-12A", "RB-12B"],
        "exact approved subset",
    )
    require(decision["limits"] == APPROVED_LIMITS, "approval cannot expand execution/funding")
    require(decision["choices"] == APPROVED_CHOICES, "approved comparison/calibration choices")
    baseline = decision["baseline"]
    projection = baseline["task_projection"]
    frozen_baseline = {
        key: baseline[key]
        for key in (
            "commit",
            "ledger_sha256",
            "task_projection",
            "gate_statuses",
            "gate_projection",
        )
    }
    digest = hashlib.sha256(
        json.dumps(frozen_baseline, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    require(
        baseline["commit"] == C21_COMMIT and digest == BASELINE_PROJECTION_SHA256,
        "pinned original work/dependency projection",
    )
    tasks = {row["id"]: row for row in ledger["tasks"]}
    gates = {row["id"]: row for row in ledger["gates"]}
    require(
        len(tasks) == len(ledger["tasks"])
        and (set(projection) | {"AR-024-D", "AR-025-D"}) <= set(tasks),
        "mapped task identities",
    )
    require(
        decision["issuance_promoted_gates"] == ["RESEARCHSCOPE0"],
        "only recorded owner gate is promoted at issuance",
    )
    require(set(baseline["gate_statuses"]) <= set(gates), "original gate removed")
    for key, current in gates.items():
        if key != "RESEARCHSCOPE0":
            require(
                current.get("decision_record") != "contracts/research/owner-decision.v1.json",
                "only recorded owner gate may cite this decision",
            )
    gate = gates["RESEARCHSCOPE0"]
    require(
        gate["status"] == "Satisfied"
        and gate["decision_record"] == "contracts/research/owner-decision.v1.json"
        and gate["dependencies"] == ["RA-01-B"]
        and gate["effort_days"] == 0,
        "actual gate binding",
    )
    mappings = {row["proposal_id"]: row for row in decision["mappings"]}
    require(
        len(mappings) == len(decision["mappings"]) == len(APPROVED_MAPPING)
        and {key: row["completion_task"] for key, row in mappings.items()} == APPROVED_MAPPING,
        "approved scope completion mapping",
    )
    changes = decision["task_changes"]
    require(
        set(changes) == set(APPROVED_MAPPING.values()) | {"AR-020-B"},
        "complete overlap reconciliation",
    )
    for key, original in projection.items():
        task = tasks[key]
        require(
            set(original["dependencies"]) <= set(task["dependencies"]),
            f"original prerequisite removed: {key}",
        )
        if key in changes:
            prior = changes[key]["before"]
            require(
                prior is not None
                and hashlib.sha256(prior["scope"].encode()).hexdigest() == original["scope_sha256"]
                and prior["dependencies"] == original["dependencies"]
                and prior["effort_days"] == original["effort_days"]
                and prior["effort_range_days"] == original["effort_range_days"]
                and prior["scope"] in task["scope"],
                f"original work lost or invented savings: {key}",
            )
    for key, change in changes.items():
        require(
            all(tasks[key][field] == value for field, value in change["after"].items()),
            f"mapped task differs: {key}",
        )
        require(
            bool(change["retained_original_scope"]),
            "retained work must be explicit",
        )
    for key, mapping in mappings.items():
        require(bool(mapping["retained_work"]), "missing retained-work disposition")
        for target in mapping["implementation_tasks"]:
            require(target in tasks, "unknown mapped implementation task")
        require(
            key in tasks[mapping["completion_task"]]["research_scopes"],
            "completion task does not own approved scope",
        )
    for task in tasks.values():
        require(
            set(task.get("research_scopes", [])) <= set(APPROVED_MAPPING),
            "deferred scope activated",
        )
    require(
        mappings["RB-02"]["implementation_tasks"] == ["AR-020-B", "AR-023-B", "AR-023-C"]
        and "AR-023-C" in tasks["AR-021-A"]["dependencies"]
        and "AR-021-A" in tasks["AR-025-B"]["dependencies"]
        and "AR-025-D" in tasks["AR-025-C"]["dependencies"]
        and tasks["AR-024-C"]["dependencies"] == ["AR-024-B"]
        and tasks["AR-025-D"]["dependencies"]
        == ["RESEARCHSCOPE0", "AR-025-B", "AR-024-C", "AR-025-A"]
        and tasks["AR-024-D"]["dependencies"] == ["RESEARCHSCOPE0", "AR-024-C", "AR-025-D"]
        and "AR-024-D" in tasks["AR-026-A"]["dependencies"],
        "accounting/harness integration boundary bypass",
    )
    graph = {row["id"]: row["dependencies"] for row in ledger["tasks"] + ledger["gates"]}
    try:
        list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise ValueError("activated dependency cycle") from error
    # Issuance is frozen; normal live status/estimate progress is checked separately
    # by check_execution_backlog, not made into a new owner decision.
    issued = {key: dict(row) for key, row in projection.items()}
    for key, change in changes.items():
        issued[key] = {**issued.get(key, {}), **change["after"]}
    issued_nodes = {**issued, **baseline["gate_projection"]}
    issued_graph = {key: row["dependencies"] for key, row in issued_nodes.items()}
    require(
        all(dep in issued_nodes for deps in issued_graph.values() for dep in deps),
        "unknown issuance prerequisite",
    )
    try:
        ordered = list(TopologicalSorter(issued_graph).static_order())
    except CycleError as error:
        raise ValueError("issuance dependency cycle") from error
    durations: dict[str, float] = {}
    for key in ordered:
        durations[key] = issued_nodes[key]["effort_days"] + max(
            (durations[dep] for dep in issued_graph[key]), default=0
        )
    computed = {
        "task_count": len(issued),
        "gate_count": len(baseline["gate_projection"]),
        "edge_count": sum(len(deps) for deps in issued_graph.values()),
        "base_effort_days": sum(t["effort_days"] for t in issued.values()),
        "upper_range_days": round(sum(t["effort_range_days"][1] for t in issued.values()), 4),
        "effort_only_critical_path_days": max(durations.values()),
    }
    require(
        decision["issuance_metrics"] == computed
        and computed
        == {
            "task_count": 150,
            "gate_count": 27,
            "edge_count": 538,
            "base_effort_days": 440,
            "upper_range_days": 744.6,
            "effort_only_critical_path_days": 152.5,
        },
        "reconciled issuance metrics",
    )
    canonical_decision = (json.dumps(decision, indent=2, ensure_ascii=False) + "\n").encode()
    require(
        gate["decision_sha256"] == hashlib.sha256(canonical_decision).hexdigest(),
        "ledger decision digest differs",
    )


def main() -> None:
    try:
        data, ledger, document = read_inputs()
        validate(data, ledger, document)
        decision = load_json(ROOT / "contracts/research/owner-decision.v1.json")
        validate_activation(
            decision,
            ledger,
            bounded_text(ROOT / "contracts/research/evaluation-design.json").encode(),
            document.encode(),
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit(f"Evaluation design invalid: {error}") from None
    print(
        f"Historical examples valid: {len(data['followups'])} proposed scopes; "
        "synthetic template pending. "
        "Actual owner decision valid: 9 mapped engineering scopes; RESEARCHSCOPE0 satisfied; "
        "runtime prerequisites and external execution gates retained."
    )


if __name__ == "__main__":
    main()
