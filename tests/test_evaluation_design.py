"""Static design checks and synthetic arithmetic, never study execution/approval."""

import copy
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluation_design_check", ROOT / "scripts/check_evaluation_design.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Evaluation-design checker cannot be loaded")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.fixture
def inputs():
    return copy.deepcopy(CHECK.read_inputs())


def test_record_and_document_match_and_consumer_remains_closed(inputs):
    data, ledger, document = inputs
    CHECK.validate(data, ledger, document)
    assert CHECK.ROOT == ROOT
    assert not CHECK.consumer_ready(data["consumer_gate"])
    assert len(data["followups"]) == 14
    assert all(not card["authorized"] for card in data["followups"])


@pytest.mark.parametrize("index", range(9))
def test_declared_budget_decisions(inputs, index):
    case = inputs[0]["budget_cases"][index]
    assert CHECK.budget_decision(case) == case["expected"]


def test_confirmation_transfer_preserves_exposure_then_settlement_releases_only_unused(inputs):
    row = inputs[0]["budget_cases"][3]
    before = row["settled"] + row["held"] + row["reserve"]
    assert CHECK.confirmation_transfer(row) == (20, 40, 0)
    assert sum(CHECK.confirmation_transfer(row)) == before == 60
    assert CHECK.settled_example(25, None) == ("held", 0)
    assert CHECK.settled_example(25, 18) == ("settled", 7)
    assert CHECK.settled_example(25, 26) == ("breach_freeze", 0)


@pytest.mark.parametrize(
    "field", ["cap", "settled", "held", "uncertain", "reserve", "required_reserve"]
)
@pytest.mark.parametrize("value", [-1, True])
def test_invalid_amount_cannot_admit(inputs, field, value):
    row = inputs[0]["budget_cases"][0]
    row[field] = value
    with pytest.raises(ValueError, match="budget amount"):
        CHECK.budget_decision(row)


def test_uncertain_charge_cannot_be_removed_from_held_exposure(inputs):
    row = inputs[0]["budget_cases"][6]
    row["held"] = 0
    with pytest.raises(ValueError, match="uncertainty must remain"):
        CHECK.budget_decision(row)


@pytest.mark.parametrize("quote", [None, -1, True, "1"])
def test_unknown_or_invalid_quote_cannot_admit(inputs, quote):
    row = inputs[0]["budget_cases"][0]
    row["quote"] = quote
    assert CHECK.budget_decision(row) == "refuse_quote"


def test_recovery_only_does_not_lose_cap_to_nonexistent_confirmation(inputs):
    row = inputs[0]["budget_cases"][7]
    assert row["quote"] == 65
    assert CHECK.budget_decision(row) == "admit"
    row["reserve"] = row["required_reserve"] = 1
    with pytest.raises(ValueError, match="nonexistent confirmation"):
        CHECK.budget_decision(row)


def test_method_global_closure_includes_offline_and_shared_costs(inputs):
    row = inputs[0]["method_budget_case"]
    CHECK.method_closure(row)
    row["offline"] += 1
    with pytest.raises(ValueError, match="method total cap"):
        CHECK.method_closure(row)


def test_offline_preparation_cannot_be_omitted(inputs):
    data, ledger, document = inputs
    data["accounting"]["required_stages"].remove("offline_preparation")
    with pytest.raises(ValueError, match="offline or attempt costs"):
        CHECK.validate(data, ledger, document)


def test_shared_attribution_does_not_duplicate_physical_invoices(inputs):
    row = inputs[0]["shared_case"]
    CHECK.shared_costs(row)
    assert row["physical_total"] == 30
    assert sum(row["method_charges"].values()) == 60
    row["physical_invoices"].append(copy.deepcopy(row["physical_invoices"][0]))
    with pytest.raises(ValueError, match="duplicate physical invoice"):
        CHECK.shared_costs(row)


@pytest.mark.parametrize("value", [0, 15, 29])
def test_shared_input_cannot_be_free_or_split_between_methods(inputs, value):
    row = inputs[0]["shared_case"]
    row["method_charges"]["uniform"] = value
    with pytest.raises(ValueError, match="equal full attribution"):
        CHECK.shared_costs(row)


@pytest.mark.parametrize("scope", sorted(CHECK.SCOPE))
def test_discovery_receipt_cannot_cross_method_or_other_identity_scope(inputs, scope):
    row = inputs[0]["phase_case"]
    row["observed"][0][scope] = "foreign"
    with pytest.raises(ValueError, match="foreign receipt scope"):
        CHECK.phase_check(row)


@pytest.mark.parametrize("field", ["policy_digest", "policy_state_digest"])
def test_changed_policy_or_state_is_not_same_decision(inputs, field):
    row = inputs[0]["phase_case"]
    row["identity"][field] = "f" * 64
    with pytest.raises(ValueError, match="changed decision"):
        CHECK.phase_check(row)


@pytest.mark.parametrize("field", sorted(CHECK.DECISION_IDENTITY))
def test_decision_requires_all_identity_fields(inputs, field):
    row = inputs[0]["phase_case"]
    del row["identity"][field]
    with pytest.raises(ValueError, match="complete decision identity"):
        CHECK.phase_check(row)


@pytest.mark.parametrize("field", ["policy_digest", "policy_state_digest"])
def test_c08_cannot_drop_policy_or_state_contract(inputs, field):
    data, ledger, document = inputs
    data["receipt_contract"]["identity_fields"].remove(field)
    with pytest.raises(ValueError, match="policy/state receipt identity"):
        CHECK.validate(data, ledger, document)


def test_discovery_attempt_cannot_be_reused_for_confirmation(inputs):
    row = inputs[0]["phase_case"]
    row["confirmation_attempts"].append(row["discovery_attempts"][0])
    with pytest.raises(ValueError, match="fresh phase attempts"):
        CHECK.phase_check(row)


def test_confirmation_outcome_cannot_feed_candidate_selection(inputs):
    row = inputs[0]["phase_case"]
    row["observed"][0]["phase"] = "confirmation"
    with pytest.raises(ValueError, match="confirmation or foreign phase"):
        CHECK.phase_check(row)


def test_optional_confirmation_stopping_refuses(inputs):
    row = inputs[0]["phase_case"]
    row["optional_stop"] = True
    with pytest.raises(ValueError, match="fixed phase boundary"):
        CHECK.phase_check(row)


def test_planned_family_does_not_shrink_to_selected_winners(inputs):
    row = inputs[0]["family_case"]
    confirmation, population = CHECK.family_check(row)
    assert confirmation == pytest.approx(0.025 / 42)
    assert population == pytest.approx(0.025 / 3)
    row["confirmation_divisor"] = 7
    with pytest.raises(ValueError, match="full planned family"):
        CHECK.family_check(row)


@pytest.mark.parametrize("field", ["population_divisor", "population_alpha_micros"])
def test_population_contrasts_cannot_escape_family_allocation(inputs, field):
    row = inputs[0]["family_case"]
    row[field] += 1
    with pytest.raises(ValueError, match="family"):
        CHECK.family_check(row)


@pytest.mark.parametrize(
    "field",
    ["model_revision", "information_stratum", "allowed_observation_digest", "proposal_pool_digest"],
)
def test_comparison_rejects_asymmetric_information_or_model(inputs, field):
    row = inputs[0]["comparison_case"]
    row["methods"][1][field] = "different"
    with pytest.raises(ValueError, match="asymmetric comparison"):
        CHECK.comparison_check(row)


@pytest.mark.parametrize(
    "resource", ["usd_micros", "calls", "tokens", "cpu_seconds", "wall_seconds", "concurrency"]
)
def test_comparison_rejects_asymmetric_resource_caps(inputs, resource):
    row = inputs[0]["comparison_case"]
    row["methods"][1]["caps"][resource] += 1
    with pytest.raises(ValueError, match="asymmetric comparison"):
        CHECK.comparison_check(row)


def test_distinct_task_credit_cannot_count_multiple_repairs():
    assert CHECK.task_credit(["task-1", "task-2"]) == 2
    with pytest.raises(ValueError, match="duplicate task credit"):
        CHECK.task_credit(["task-1", "task-1"])


def test_fresh_retry_has_recovery_credit_without_intervention_endpoint(inputs):
    row = inputs[0]["recovery_case"]
    assert CHECK.recovery_report(row) == (None, (0.6, 0.8))
    row.update(successes=0, failures=0, missing=5)
    assert CHECK.recovery_report(row) == (None, (0, 1))
    row["assigned_tasks"] = 4
    with pytest.raises(ValueError, match="complete recovery denominator"):
        CHECK.recovery_report(row)


def test_synthetic_complete_approval_boolean_never_changes_design_authorization(inputs):
    data, ledger, document = inputs
    gate = data["consumer_gate"]
    gate["decisions"] = dict.fromkeys(gate["requires"], "approved")
    assert CHECK.consumer_ready(gate)  # Synthetic predicate only, not an approval record.
    with pytest.raises(ValueError, match="unresolved owner choices"):
        CHECK.validate(data, ledger, document)


def test_cannot_delete_an_owner_choice_to_make_gate_complete(inputs):
    gate = inputs[0]["consumer_gate"]
    key = "owner_followup_scope_choice"
    gate["requires"].remove(key)
    del gate["decisions"][key]
    gate["decisions"] = dict.fromkeys(gate["requires"], "approved")
    assert not CHECK.consumer_ready(gate)


@pytest.mark.parametrize(
    "flag", ["runtime_authorized", "paid_evaluation_authorized", "heldout_access_authorized"]
)
def test_design_does_not_grant_new_authority(inputs, flag):
    data, ledger, document = inputs
    data["authorization"][flag] = True
    with pytest.raises(ValueError, match="design-only authority"):
        CHECK.validate(data, ledger, document)


def test_checker_accepts_defensive_gate_already_integrated_without_recounting_baseline(inputs):
    data, ledger, document = inputs
    if not any(row["id"] == "RESEARCHSCOPE0" for row in ledger["gates"]):
        ledger["gates"].append(
            {"id": "RESEARCHSCOPE0", "effort_days": 0, "dependencies": ["RA-01-B"]}
        )
    for row in ledger["tasks"]:
        if row["id"] in {"AR-020-A", "AR-024-A"} and "RESEARCHSCOPE0" not in row["dependencies"]:
            row["dependencies"].append("RESEARCHSCOPE0")
    CHECK.validate(data, ledger, document)


def test_owner_gate_cannot_depend_on_calibration_that_consumes_it(inputs):
    data, ledger, document = inputs
    data["consumer_gate"]["dependencies"].append("AR-024-C")
    with pytest.raises(ValueError, match="owner gate contract"):
        CHECK.validate(data, ledger, document)


@pytest.mark.parametrize(
    "field",
    [
        "objective",
        "out_of_scope",
        "acceptance",
        "automated_tests",
        "security_reliability",
        "definition_of_done",
        "effort_overlap",
    ],
)
def test_followup_card_cannot_omit_assignable_scope(inputs, field):
    data, ledger, document = inputs
    del data["followups"][0][field]
    with pytest.raises(ValueError, match="complete follow-up card"):
        CHECK.validate(data, ledger, document)


def test_followup_doc_parity_catches_changed_scope(inputs):
    data, ledger, document = inputs
    data["followups"][0]["scope"] = "Silently expanded implementation."
    with pytest.raises(ValueError, match="card/document drift"):
        CHECK.validate(data, ledger, document)


def test_proposed_followup_is_not_implementation_approval(inputs):
    data, ledger, document = inputs
    data["followups"][0]["authorized"] = True
    with pytest.raises(ValueError, match="cannot authorize"):
        CHECK.validate(data, ledger, document)


def test_unknown_dependency_refuses_even_if_document_matches(inputs):
    data, ledger, document = inputs
    card = data["followups"][0]
    card["dependencies"].append("MISSING-999")
    heading = f"### {card['id']} — {card['title']}"
    document = document.replace(heading, heading + "\nMISSING-999")
    with pytest.raises(ValueError, match="unknown prerequisite"):
        CHECK.validate(data, ledger, document)


def test_dependency_cycle_refuses_even_if_document_matches(inputs):
    data, ledger, document = inputs
    card = data["followups"][0]
    card["dependencies"].append("RB-01")
    heading = f"### {card['id']} — {card['title']}"
    document = document.replace(heading, heading + "\nRB-01")
    with pytest.raises(ValueError, match="dependency cycle"):
        CHECK.validate(data, ledger, document)


def test_missing_contract_producer_ancestry_refuses(inputs):
    data, ledger, document = inputs
    card = next(row for row in data["followups"] if row["id"] == "RB-07")
    card["contracts"].append("C08")
    with pytest.raises(ValueError, match="required contract producer missing"):
        CHECK.validate(data, ledger, document)


def test_duplicate_card_identity_refuses(inputs):
    data, ledger, document = inputs
    data["followups"].append(copy.deepcopy(data["followups"][0]))
    with pytest.raises(ValueError, match="duplicate follow-up identity"):
        CHECK.validate(data, ledger, document)


@pytest.mark.parametrize(
    "raw",
    [
        '{"x":1,"x":2}',
        '{"outer":{"x":1,"x":2}}',
        r'{"x":1,"\u0078":2}',
        r'{"outer":{"x":1,"\u0078":2}}',
    ],
)
def test_duplicate_json_fields_refuse_even_if_nested_or_escaped(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw)
    with pytest.raises(ValueError, match="duplicate JSON field"):
        CHECK.load_json(path)


def test_bounded_input_refuses_oversize_and_fifo_without_wait(tmp_path):
    path = tmp_path / "large.json"
    with path.open("wb") as stream:
        stream.truncate(CHECK.MAX_BYTES + 1)
    with pytest.raises(ValueError, match="input too large"):
        CHECK.load_json(path)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        CHECK.load_json(fifo)


@pytest.mark.parametrize(
    "raw,reason",
    [
        ('{"authorization":{},"authorization":{}}', "duplicate JSON field"),
        ("[]", "JSON root must be an object"),
    ],
)
def test_cli_fails_cleanly_for_malformed_input(tmp_path, raw, reason):
    path = tmp_path / "contracts/research/evaluation-design.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    checker_path = ROOT / "scripts/check_evaluation_design.py"
    code = (
        "import importlib.util; from pathlib import Path; "
        f"s=importlib.util.spec_from_file_location('check', {str(checker_path)!r}); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        f"m.ROOT=Path({str(tmp_path)!r}); m.main()"
    )
    process = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        check=False,
    )
    assert process.returncode != 0
    assert f"Evaluation design invalid: {reason}" in process.stderr
    assert "Traceback" not in process.stderr
    assert "valid;" not in process.stdout
