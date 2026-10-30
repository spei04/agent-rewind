"""Independent synthetic planning mutations; no corpus rows or runtime admission."""

from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from scripts import check_evaluation_design as evaluation
from scripts import check_execution_backlog as execution
from scripts import public_corpus_plan as public


@pytest.fixture
def packet():
    return (
        public.load_record("contracts/proposals/execution-backlog.json"),
        (public.ROOT / "docs/EXECUTION_BACKLOG.md").read_text(),
        (public.ROOT / "docs/PLAN.md").read_text(),
    )


def nodes(data):
    return {
        row["id"]: row
        for row in data["tasks"]
        + data["gates"]
        + [row for task in data["tasks"] for row in task.get("preparatory_prs", [])]
    }


def accept(row):
    row.update(
        status="Verified",
        source_commit="a" * 40,
        accepted_merge_commit="b" * 40,
        review_evidence="Independent synthetic acceptance fixture",
    )


def sync_card(markdown, row):
    heading = f"#### {row['id']} — {row['title']}"
    before, section = markdown.split(heading, 1)
    body, separator, after = section.partition("\n###")
    body = re.sub(
        r"^- \*\*Progress:\*\* .+$", f"- **Progress:** {row['status']}.", body, flags=re.M
    )
    if row["status"] == "Verified":
        evidence = (
            f"Source {row['source_commit']}; accepted merge {row['accepted_merge_commit']}; "
            f"review {row['review_evidence']}."
        )
        body = re.sub(
            r"^- \*\*Delivery evidence:\*\* .+$",
            f"- **Delivery evidence:** {evidence}",
            body,
            flags=re.M,
        )
    return before + heading + body + separator + after


def test_preparation_progress_preserves_native_status_and_aggregate_accounting(packet):
    data, markdown, roadmap = packet
    lookup = nodes(data)
    baseline = execution.validate(*packet)
    for status in ("In progress", "Implemented; verification pending"):
        lookup["PCA1"]["status"] = status
        markdown = sync_card(markdown, lookup["PCA1"])
        assert execution.validate(data, markdown, roadmap) == baseline
    accept(lookup["PCA1"])
    lookup["PCA2"]["status"] = "In progress"
    for key in ("PCA1", "PCA2"):
        markdown = sync_card(markdown, lookup[key])
    assert execution.validate(data, markdown, roadmap) == baseline
    accept(lookup["PCA2"])
    markdown = sync_card(markdown, lookup["PCA2"])
    assert execution.validate(data, markdown, roadmap) == baseline
    assert lookup["AR-002-C"]["status"] == lookup["PUBCAP-A"]["status"] == "Not started"
    assert baseline["base_effort_days"] == 482
    assert baseline["upper_range_days"] == 814.6
    assert baseline["preparatory_pr_count"] == 2
    assert baseline["delivery_pr_count"] == 171
    assert baseline["edge_count"] == 569
    assert {"G4", "G5"} <= set(baseline["effort_only_critical_path"])


@pytest.mark.parametrize(
    "first", ["Not started", "In progress", "Implemented; verification pending"]
)
@pytest.mark.parametrize("second", ["In progress", "Implemented; verification pending", "Verified"])
def test_pca2_requires_accepted_pca1_source_not_implementation_only(packet, first, second):
    data = packet[0]
    lookup = nodes(data)
    lookup["PCA1"]["status"] = first
    if second == "Verified":
        accept(lookup["PCA2"])
    else:
        lookup["PCA2"]["status"] = second
    with pytest.raises(ValueError, match="precedes prerequisites: PCA2"):
        public.validate_amendment(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", None),
        ("source_commit", "a" * 7),
        ("accepted_merge_commit", None),
        ("accepted_merge_commit", "B" * 40),
        ("review_evidence", None),
        ("review_evidence", " "),
    ],
)
def test_accepted_preparation_requires_complete_structural_evidence(packet, field, value):
    row = nodes(packet[0])["PCA1"]
    accept(row)
    row[field] = value
    with pytest.raises(ValueError, match="accepted source/merge/review evidence"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize(
    "status", ["Not started", "In progress", "Implemented; verification pending"]
)
def test_unaccepted_preparation_cannot_carry_acceptance_claim(packet, status):
    row = nodes(packet[0])["PCA1"]
    accept(row)
    row["status"] = status
    with pytest.raises(ValueError, match="Unverified preparation"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize(
    "variant,message",
    [
        ("unknown_id", "Unknown preparation"),
        ("duplicate_id", "Duplicate preparation"),
        ("unknown_field", "fields differ"),
        ("wrong_parent", "aggregate/role"),
        ("wrong_role", "aggregate/role"),
        ("runtime_kind", "kind/contracts/dependencies"),
        ("new_contract", "kind/contracts/dependencies"),
        ("wrong_predecessor", "kind/contracts/dependencies"),
        ("third_package", "Invalid preparation allocation"),
        ("missing_package", "Missing preparation"),
        ("duplicate_member", "Duplicate public planning"),
        ("broaden_scope", "boundary differs"),
    ],
)
def test_only_two_reviewed_preparation_exceptions_exist(packet, variant, message):
    data = packet[0]
    lookup = nodes(data)
    row = lookup["PCA1"]
    if variant == "unknown_id":
        row["id"] = "PCA3"
    elif variant == "duplicate_id":
        lookup["PCA2"]["id"] = "PCA1"
    elif variant == "unknown_field":
        row["runtime_exemption"] = True
    elif variant == "wrong_parent":
        row["aggregate_id"] = "PUBCAP-A"
    elif variant == "wrong_role":
        row["role"] = "PL"
    elif variant == "runtime_kind":
        row["kind"] = "native"
    elif variant == "new_contract":
        row["contracts"].append("C06")
    elif variant == "wrong_predecessor":
        row["dependencies"] = ["RESEARCHSCOPE0"]
    elif variant == "third_package":
        lookup["AR-002-C"]["preparatory_prs"].append(deepcopy(row))
    elif variant == "missing_package":
        del lookup["AR-002-C"]["preparatory_prs"]
    elif variant == "broaden_scope":
        row["scope"] += " Acquire real rows."
    else:
        with pytest.raises(ValueError, match=message):
            json.loads('{"PCA1": {}, "PCA1": {}}', object_pairs_hook=public.unique_object)
        return
    with pytest.raises(ValueError, match=message):
        public.validate_amendment(data)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 0, -1, 2])
def test_preparation_effort_is_finite_reviewed_allocation(packet, value):
    nodes(packet[0])["PCA1"]["effort_days"] = value
    with pytest.raises(ValueError, match="preparation effort/range"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize(
    "variant", ["zero_residual", "upper_overlap", "lower_overlap", "double_count"]
)
def test_preparation_is_included_with_positive_exact_residual(packet, variant):
    row = nodes(packet[0])["AR-002-C"]
    if variant == "zero_residual":
        row["effort_days"] = 1
    elif variant == "upper_overlap":
        row["effort_range_days"][1] = 7
    elif variant == "lower_overlap":
        row["effort_range_days"][0] = 2
    else:
        row["effort_days"] += 1
    with pytest.raises(ValueError, match="residual effort/range"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize(
    "metric",
    [
        "task_count",
        "edge_count",
        "preparatory_pr_count",
        "base_effort_days",
        "upper_range_days",
    ],
)
def test_live_metrics_cannot_double_count_or_hide_preparation(packet, metric):
    packet[0]["validation"][metric] += 1
    with pytest.raises(ValueError, match=f"Stored metric differs: {metric}"):
        execution.validate(*packet)


@pytest.mark.parametrize(
    "field",
    [
        "Objective",
        "Scope",
        "Security and reliability",
        "Confidence",
        "Definition of done",
        "Prerequisites",
        "Effort allocation",
        "Delivery evidence",
    ],
)
def test_preparation_cards_match_reviewed_machine_boundary(packet, field):
    data, markdown, plan = packet
    start = markdown.index("#### PCA1")
    prefix, tail = markdown[:start], markdown[start:]
    tail = re.sub(
        rf"^- \*\*{re.escape(field)}:\*\* .+$",
        f"- **{field}:** Mismatch.",
        tail,
        count=1,
        flags=re.M,
    )
    with pytest.raises(ValueError, match="Preparation card"):
        public.check_preparation_cards(data, prefix + tail, plan)


@pytest.mark.parametrize("status", ["In progress", "Implemented; verification pending", "Verified"])
def test_preparation_acceptance_never_opens_native_adapter(packet, status):
    data = packet[0]
    lookup = nodes(data)
    accept(lookup["PCA1"])
    accept(lookup["PCA2"])
    lookup["PUBCAP-A"]["status"] = status
    with pytest.raises(ValueError, match="precedes prerequisites: PUBCAP-A"):
        public.validate_amendment(data)


@pytest.mark.parametrize(
    "variant,message",
    [
        ("native_gate_removed", "Native/public prerequisites"),
        ("development_cycle", "Dependency cycle"),
        ("phases_swapped", "Native/public prerequisites"),
        ("original_protocol_edge", "Public route differs"),
        ("study_g3_removed", "Public route differs"),
        ("unknown_node", "Unknown dependency"),
        ("c06_substitution", "Native C06"),
    ],
)
def test_native_and_public_route_prerequisites_cannot_be_bypassed(packet, variant, message):
    data = packet[0]
    lookup = nodes(data)
    if variant == "native_gate_removed":
        lookup["PUBCAP-A"]["dependencies"].remove("G2")
    elif variant == "development_cycle":
        lookup["PUBCAP-B"]["dependencies"].append("G3")
    elif variant == "phases_swapped":
        lookup["PUBCAP-C"]["dependencies"].remove("AR-026-A")
    elif variant == "original_protocol_edge":
        lookup["AR-026-A"]["dependencies"].remove("AR-024-D")
    elif variant == "study_g3_removed":
        lookup["AR-038-B"]["dependencies"].remove("G3")
    elif variant == "unknown_node":
        lookup["AR-001-A"]["dependencies"].append("UNKNOWN0")
    else:
        next(c for c in data["contracts"] if c["id"] == "C06")["producer"] = "AR-002-A"
    with pytest.raises(ValueError, match=message):
        public.validate_amendment(data)


@pytest.mark.parametrize("gate", ["PUBLICDATA0", "CAPTUREFUNDS0", "PAID0", "STUDYFUNDS0"])
def test_preparation_decision_cannot_satisfy_execution_or_spending_gates(packet, gate):
    nodes(packet[0])[gate]["status"] = "Satisfied"
    with pytest.raises(ValueError, match="cannot satisfy native external gates"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize("variant", ["old_decision", "digest", "borrowed_decision"])
def test_scoped_owner_gate_is_bound_to_new_record(packet, variant):
    lookup = nodes(packet[0])
    if variant == "old_decision":
        lookup["PUBLICPREP0"]["decision_record"] = "contracts/research/owner-decision.v1.json"
    elif variant == "digest":
        lookup["PUBLICPREP0"]["decision_sha256"] = "0" * 64
    else:
        lookup["DATA0"]["decision_record"] = public.DECISION_PATH
    with pytest.raises(ValueError, match="decision"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize("variant", ["cap", "cash", "capture", "heldout", "history"])
def test_owner_scope_and_preserved_history_are_immutable(packet, variant):
    decision = public.load_record(public.DECISION_PATH)
    if variant == "cap":
        decision["limits"]["existing_cap_usd"] += 1
    elif variant == "cash":
        decision["limits"]["available_funds_known"] = True
    elif variant == "capture":
        decision["authorized"].append("Dataset acquisition and native capture")
    elif variant == "heldout":
        decision["not_authorized"].remove("Held-out access")
    else:
        decision["preserved_artifact_sha256"]["agent_rewind/corpus.py"] = "0" * 64
    with pytest.raises(ValueError, match="Scoped public owner decision"):
        public.validate_amendment(packet[0], decision=decision)


@pytest.mark.parametrize("variant", ["extra_task", "baseline", "customer_record", "partition"])
def test_versioned_amendment_cannot_expand_its_three_task_projection(packet, variant):
    amendment = public.load_record(public.PLAN_PATH)
    if variant == "extra_task":
        amendment["task_changes"]["AR-021-A"] = deepcopy(amendment["task_changes"]["AR-026-A"])
    elif variant == "baseline":
        amendment["baseline_ledger_sha256"] = "0" * 64
    elif variant == "customer_record":
        amendment["customer_route_preserved"]["records"]["AR-038-A"]["scope"] = "Erased"
    else:
        amendment["estimate_allocation"]["included_preparation"] = [0, 0]
    with pytest.raises(ValueError, match="Pinned public amendment"):
        public.validate_amendment(packet[0], amendment=amendment)


@pytest.mark.parametrize("key", ["DATA0", "PARTNER0", "G4", "G5", "AR-035-A", "AR-039-A"])
def test_global_customer_and_pilot_dependencies_remain(packet, key):
    nodes(packet[0])[key]["dependencies"].pop()
    with pytest.raises(ValueError, match="Customer/partner/pilot boundary"):
        public.validate_amendment(packet[0])


def test_historical_comparison_restores_only_authorized_fields_without_mutation(packet):
    data = packet[0]
    original = deepcopy(data)
    projected = public.legacy_comparison(data)
    changes = public.load_record(public.PLAN_PATH)["task_changes"]
    live, prior = nodes(data), nodes(projected)
    differences = {
        (key, field) for key in live for field in live[key] if live[key][field] != prior[key][field]
    }
    assert differences == {
        ("AR-026-A", "dependencies"),
        ("AR-038-A", "dependencies"),
        ("AR-038-A", "contracts"),
        ("AR-038-B", "dependencies"),
        ("AR-038-B", "contracts"),
    }
    for key, change in changes.items():
        for field, value in change["before"].items():
            assert prior[key][field] == value
    assert data == original


def test_legacy_projection_does_not_hide_unrelated_original_work_loss(packet):
    data = packet[0]
    nodes(data)["AR-020-B"]["scope"] = "Erased original budget migration"
    with pytest.raises(ValueError, match="original work lost"):
        evaluation.validate_activation(
            public.load_record("contracts/research/owner-decision.v1.json"),
            data,
            (public.ROOT / "contracts/research/evaluation-design.json").read_bytes(),
            (public.ROOT / "docs/research/TOTAL_BUDGET_PROTOCOL.md").read_bytes(),
        )


def test_byte_drift_in_historical_artifact_is_rejected_without_writing_repo(packet, monkeypatch):
    original = public.Path.read_bytes

    def changed(path):
        content = original(path)
        return content + b"\n" if path.name == "corpus.py" else content

    monkeypatch.setattr(public.Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="Preserved historical artifact differs"):
        public.validate_amendment(packet[0])


@pytest.mark.parametrize(
    "key,field",
    [
        ("AR-002-C", "scope"),
        ("PUBCAP-A", "contracts"),
        ("PUBCAP-B", "security_reliability"),
        ("PUBCAP-C", "out_of_scope"),
        ("AR-038-A", "scope"),
        ("AR-038-B", "acceptance"),
    ],
)
def test_aggregate_reconciliation_does_not_erase_retained_work(packet, key, field):
    row = nodes(packet[0])[key]
    row[field] = [] if field == "contracts" else "Erased"
    with pytest.raises(ValueError, match="boundary differs|Retained public research"):
        public.validate_amendment(packet[0])


def test_c02_still_has_its_original_producer(packet):
    next(c for c in packet[0]["contracts"] if c["id"] == "C02")["producer"] = "AR-002-B"
    with pytest.raises(ValueError, match="Original C02 producer"):
        public.validate_amendment(packet[0])
