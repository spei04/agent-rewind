"""Planning gates must reject drift, missing prerequisites and invented availability."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "execution_check", ROOT / "scripts/check_execution_backlog.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Execution checker cannot be loaded")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.fixture
def packet():
    return (
        json.loads((ROOT / "contracts/proposals/execution-backlog.json").read_text()),
        (ROOT / "docs/EXECUTION_BACKLOG.md").read_text(),
        (ROOT / "docs/PLAN.md").read_text(),
    )


def test_current_packet_recomputes_all_metrics_and_design_consumer_ancestry(packet):
    result = CHECK.validate(*packet)
    assert result["effort_only_critical_path"][-1] == "G7"
    assert result["base_effort_days"] == sum(task["effort_days"] for task in packet[0]["tasks"])


@pytest.mark.parametrize(
    "variant,message",
    [
        ("metric", "Stored metric differs"),
        ("unknown", "Unknown dependency"),
        ("cycle", "Dependency cycle"),
        ("producer", "Contract producer missing"),
        ("availability", "Unreviewed contract claims availability"),
        ("active", "precedes prerequisites"),
        ("schedule", "Scheduled before prerequisite acceptance"),
        ("capacity", "Contributor overbooked"),
        ("opening", "Unverified schedule opening condition"),
        ("parent", "Parent effort differs"),
    ],
)
def test_machine_record_refuses_invalid_planning_claims(packet, variant, message):
    data, markdown, plan = packet
    data = deepcopy(data)
    tasks = {task["id"]: task for task in data["tasks"]}
    if variant == "metric":
        data["validation"]["edge_count"] += 1
    elif variant == "unknown":
        tasks["RA-01-A"]["dependencies"].append("missing")
    elif variant == "cycle":
        tasks["RA-01-A"]["dependencies"].append("RA-01-B")
    elif variant == "producer":
        tasks["AR-020-A"]["dependencies"].remove("RA-01-B")
        tasks["AR-020-A"]["dependencies"].remove("RESEARCHSCOPE0")
    elif variant == "availability":
        tasks["RA-01-B"]["status"] = "Not started"
        next(g for g in data["gates"] if g["id"] == "RESEARCHSCOPE0")["status"] = "Not satisfied"
        next(c for c in data["contracts"] if c["id"] == "C21")["status"] = "Available"
    elif variant == "active":
        tasks["RA-01-A"]["status"] = "Not started"
        tasks["RA-01-B"]["status"] = "In progress"
    elif variant == "schedule":
        data["schedule"][0]["work"] = {"AR-009-B": 0.5}
    elif variant == "capacity":
        data["schedule"][0]["work"] = {"AR-007-B": 1.0}
    elif variant == "opening":
        data["first_two_weeks_conditions"]["unreviewed-input"] = 0
    else:
        data["parents"]["RA-01"]["base_effort_days"] += 1
    with pytest.raises(ValueError, match=message):
        CHECK.validate(data, markdown, plan)


@pytest.mark.parametrize("variant", ["dependency", "status", "range", "allocation", "roadmap"])
def test_documentation_drift_is_not_hidden_by_valid_json(packet, variant):
    data, markdown, plan = packet
    if variant == "dependency":
        marker = markdown.index("### RA-01-A")
        markdown = markdown[:marker] + markdown[marker:].replace("[AR-002-B](#ar-002-b), ", "", 1)
    elif variant == "status":
        marker = markdown.index("### RA-01-A")
        status = next(t for t in data["tasks"] if t["id"] == "RA-01-A")["status"]
        markdown = markdown[:marker] + markdown[marker:].replace(
            f"**Progress:** {status}", "**Progress:** Unknown", 1
        )
    elif variant == "range":
        marker = markdown.index("### RA-01-B")
        markdown = markdown[:marker] + markdown[marker:].replace(
            "planning range 2–4", "planning range 2–3", 1
        )
    elif variant == "allocation":
        markdown = markdown.replace("(0.5d)", "(1d)", 1)
    else:
        status = data["parents"]["RA-01"]["status"]
        plan = plan.replace(f"| RS / 4 days | {status} |", "| RS / 4 days | Unknown |")
    with pytest.raises(ValueError):
        CHECK.validate(data, markdown, plan)


@pytest.mark.parametrize("task_id", ["AR-002-B", "RA-01-A"])
def test_active_and_verified_consumers_require_available_input(packet, task_id):
    data, markdown, plan = packet
    data = deepcopy(data)
    next(c for c in data["contracts"] if c["id"] == "C02")["status"] = (
        "Not yet available; review withdrawn"
    )
    # Isolate each consumer so a preceding consumer cannot hide the active-task case.
    for task in data["tasks"]:
        if task["id"] != task_id:
            task["contracts"] = [c for c in task["contracts"] if c != "C02"]
    with pytest.raises(ValueError, match=f"consumes unavailable contract: {task_id}/C02"):
        CHECK.validate(data, markdown, plan)


@pytest.mark.parametrize(
    "payload",
    [
        '{"tasks": [], "tasks": []}',
        '{"tasks": [{"status": "Not started", "status": "Verified"}]}',
        r'{"a": 1, "\u0061": 2}',
    ],
)
def test_cli_refuses_duplicate_json_members_before_validation(tmp_path, monkeypatch, payload):
    source = tmp_path / "contracts/proposals/execution-backlog.json"
    source.parent.mkdir(parents=True)
    source.write_text(payload)
    monkeypatch.setattr(CHECK, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Duplicate JSON member"):
        CHECK.main()


@pytest.mark.parametrize("task_id", ["AR-020-A", "AR-024-A"])
def test_research_producers_cannot_bypass_owner_decision_gate(packet, task_id):
    data, markdown, plan = packet
    data = deepcopy(data)
    task = next(t for t in data["tasks"] if t["id"] == task_id)
    task["dependencies"].remove("RESEARCHSCOPE0")
    with pytest.raises(ValueError, match="Research producer lacks owner decision gate"):
        CHECK.validate(data, markdown, plan)


def _delivery_packet(packet):
    data, markdown, plan = deepcopy(packet)
    import re

    task = next(t for t in data["tasks"] if t["id"] == "AR-007-C")
    # Refusal fixtures must not inherit the live delivery's progress.
    task["status"] = "In progress"
    for package in task["delivery_packages"]:
        package.update(status="Not started", accepted_merge_commit=None, review_evidence=None)
    start = markdown.index("#### AR-007-C —")
    end = markdown.index("\n#### ", start + 5)
    body = re.sub(
        r"(?m)^- \*\*Progress:\*\* .*$",
        "- **Progress:** In progress; synthetic test fixture.",
        markdown[start:end],
    )
    markdown = markdown[:start] + body + markdown[end:]
    markdown = _sync_package_cards(markdown, task["delivery_packages"])
    # Rewinding the producer also rewinds its now-active admission consumer.
    admission = next(t for t in data["tasks"] if t["id"] == "AR-008-A")
    admission["status"] = "Not started"
    for package in admission["delivery_packages"]:
        package.update(status="Not started", accepted_merge_commit=None, review_evidence=None)
    markdown = _sync_package_cards(markdown, admission["delivery_packages"])
    # Operation adapters likewise cannot retain progress without admission.
    operation = next(t for t in data["tasks"] if t["id"] == "AR-008-B")
    operation["status"] = "Not started"
    for package in operation["delivery_packages"]:
        package.update(status="Not started", accepted_merge_commit=None, review_evidence=None)
    markdown = _sync_package_cards(markdown, operation["delivery_packages"])
    # Listing also consumes the rewound authority producer.
    listing = next(t for t in data["tasks"] if t["id"] == "AR-006-B")
    listing["status"] = "Not started"
    for package in listing["delivery_packages"]:
        package.update(status="Not started", accepted_merge_commit=None, review_evidence=None)
    markdown = _sync_package_cards(markdown, listing["delivery_packages"])
    return data, markdown, plan, task, task["delivery_packages"]


def _sync_package_cards(markdown, packages):
    """Keep prose honest while testing a separate invalid machine-record claim."""
    import re

    for package in packages:
        start = markdown.index(f"#### {package['id']} —")
        following = re.search(r"^#{1,4} ", markdown[start + 5 :], re.M)
        end = start + 5 + following.start() if following else len(markdown)
        body = markdown[start:end]
        values = {
            "Prerequisites": ", ".join(
                f"[{key}](#{key.lower().replace('/', '-')})" for key in package["dependencies"]
            )
            + ".",
            "Required contracts": ", ".join(package["contracts"])
            + ". "
            + package["interface_contracts"]
            + ".",
            "Progress": package["status"] + "; test record.",
            "Effort / confidence": (
                f"{package['effort_days']:g} engineering days; planning range "
                f"{package['effort_range_days'][0]:g}–{package['effort_range_days'][1]:g}; "
                f"{package['confidence']} confidence."
            ),
        }
        for label, value in values.items():
            body = re.sub(
                rf"(?m)^- \*\*{re.escape(label)}:\*\* .*$", f"- **{label}:** {value}", body
            )
        markdown = markdown[:start] + body + markdown[end:]
    return markdown


@pytest.mark.parametrize(
    "variant,message",
    [
        ("early_aggregate", "Aggregate completes before"),
        ("early_p2", "before accepted merged prerequisite"),
        ("missing_merge", "lacks accepted merge/review"),
        ("missing_review", "lacks accepted merge/review"),
        ("missing_prerequisite", "dropped inherited prerequisites"),
        ("missing_contract", "dropped inherited contracts"),
        ("base_effort", "effort/range rollup differs"),
        ("upper_effort", "effort/range rollup differs"),
        ("unrelated_prerequisite", "bypasses aggregate prerequisites"),
        ("missing_sequence", "preceding accepted PR"),
        ("active_unstarted", "Active package under unstarted aggregate"),
        ("unverified_merge", "Unverified package claims merge"),
        ("duplicate_package", "Duplicate delivery package identity"),
    ],
)
def test_delivery_packages_refuse_premature_or_incomplete_claims(packet, variant, message):
    data, markdown, plan, task, packages = _delivery_packet(packet)
    p1, p2 = packages
    if variant == "early_aggregate":
        task["status"] = "Verified"
    elif variant == "early_p2":
        task["status"] = p2["status"] = "In progress"
    elif variant in ("missing_merge", "missing_review"):
        task["status"] = "In progress"
        p1["status"] = "Verified"
        if variant == "missing_review":
            p1["accepted_merge_commit"] = "a" * 40
    elif variant == "missing_prerequisite":
        p1["dependencies"].remove("AR-009-B")
    elif variant == "missing_contract":
        p1["contracts"] = ["C05"]
    elif variant == "base_effort":
        p1["effort_days"] = p1["effort_range_days"][0] = 1.5
    elif variant == "upper_effort":
        p2["effort_range_days"][1] = 6
    elif variant == "unrelated_prerequisite":
        p1["dependencies"].append("AR-008-A")
    elif variant == "missing_sequence":
        p2["dependencies"] = []
    elif variant == "active_unstarted":
        task["status"] = "Not started"
        p1["status"] = "In progress"
    elif variant == "unverified_merge":
        p1["accepted_merge_commit"] = "a" * 40
    else:
        p2["id"] = p1["id"]
    markdown = _sync_package_cards(markdown, packages)
    with pytest.raises(ValueError, match=message):
        CHECK.check_delivery_packages(data, markdown, plan)


def test_accepted_merged_foundation_allows_p2_without_completing_aggregate(packet):
    data, markdown, plan, task, packages = _delivery_packet(packet)
    task["status"] = "In progress"
    packages[0].update(
        status="Verified",
        accepted_merge_commit="a" * 40,
        review_evidence="Synthetic test-only accepted source/review/check record",
    )
    packages[1]["status"] = "In progress"
    assert CHECK.check_delivery_packages(
        data, _sync_package_cards(markdown, packages), plan
    ) == sum(len(task.get("delivery_packages", [None])) for task in data["tasks"])
    assert task["status"] == "In progress"


@pytest.mark.parametrize("variant", ["scope", "pr_count", "parent_count", "stored_count"])
def test_delivery_package_prose_and_pr_counts_are_checked(packet, variant):
    data, markdown, plan, task, packages = _delivery_packet(packet)
    if variant == "scope":
        marker = markdown.index("#### AR-007-C/P1")
        markdown = markdown[:marker] + markdown[marker:].replace(
            packages[0]["out_of_scope"] + ".", "No constraints.", 1
        )
    elif variant == "pr_count":
        plan = plan.replace(
            "[AR-007](EXECUTION_BACKLOG.md#ar-007): 4 PRs.",
            "[AR-007](EXECUTION_BACKLOG.md#ar-007): 3 PRs.",
        )
    elif variant == "parent_count":
        markdown = markdown.replace(
            "4 PRs across 3 aggregate tasks", "3 PRs across 3 aggregate tasks"
        )
    else:
        data["validation"]["delivery_pr_count"] = 151
    with pytest.raises(ValueError):
        CHECK.validate(data, markdown, plan)


@pytest.mark.parametrize(
    "variant,message",
    [
        ("early_p3", "before accepted merged prerequisite"),
        ("skip_p2", "preceding accepted PR"),
        ("missing_input", "dropped inherited prerequisites"),
        ("missing_contract", "dropped inherited contracts"),
        ("early_aggregate", "Aggregate completes before"),
        ("effort_drift", "effort/range rollup differs"),
    ],
)
def test_admission_three_stage_delivery_retains_all_gates(packet, variant, message):
    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-008-A")
    p1, p2, p3 = task["delivery_packages"]
    # Construct the pre-acceptance fixture independently of live delivery progress.
    task["status"] = p3["status"] = "In progress"
    p3["accepted_merge_commit"] = p3["review_evidence"] = None
    if variant == "early_p3":
        p2["status"] = "Not started"
        p2["accepted_merge_commit"] = p2["review_evidence"] = None
        task["status"] = p3["status"] = "In progress"
    elif variant == "skip_p2":
        p3["dependencies"] = [p1["id"]]
    elif variant == "missing_input":
        p1["dependencies"].remove("AR-007-C")
    elif variant == "missing_contract":
        p3["contracts"] = []
    elif variant == "early_aggregate":
        task["status"] = "Verified"
    else:
        p3["effort_days"] = p3["effort_range_days"][0] = 2.5
    markdown = _sync_package_cards(markdown, task["delivery_packages"])
    with pytest.raises(ValueError, match=message):
        CHECK.check_delivery_packages(data, markdown, plan)


@pytest.mark.parametrize(
    "variant,message",
    [
        ("early_foundation", "before aggregate prerequisites"),
        ("early_integration", "before aggregate prerequisites"),
        ("missing_worker", "dropped inherited prerequisites"),
        ("missing_contract", "dropped inherited contracts"),
        ("unmerged_foundation", "before accepted merged prerequisite"),
        ("early_aggregate", "Aggregate completes before"),
    ],
)
def test_observability_packages_wait_for_real_worker_producer(packet, variant, message):
    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-011-C")
    p1, p2 = task["delivery_packages"]
    if variant == "early_foundation":
        task["status"] = p1["status"] = "In progress"
    elif variant == "early_integration":
        task["status"] = p2["status"] = "In progress"
        p1.update(
            status="Verified",
            accepted_merge_commit="a" * 40,
            review_evidence="Synthetic accepted foundation cannot waive worker producer",
        )
    elif variant == "missing_worker":
        p1["dependencies"].remove("AR-010-B")
    elif variant == "missing_contract":
        p2["contracts"] = []
    elif variant == "unmerged_foundation":
        task["status"] = p2["status"] = "In progress"
    else:
        task["status"] = "Verified"
    markdown = _sync_package_cards(markdown, task["delivery_packages"])
    with pytest.raises(ValueError, match=message):
        CHECK.check_delivery_packages(data, markdown, plan)


def test_observability_successor_requires_accepted_merge_and_all_aggregate_inputs(packet):
    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-011-C")
    p1, p2 = task["delivery_packages"]
    # Complete only the synthetic prerequisite closure; real delivery states are untouched.
    by_id = {row["id"]: row for row in data["tasks"]}
    pending = list(task["dependencies"])
    completed = set()
    while pending:
        prerequisite_id = pending.pop()
        if prerequisite_id in completed or prerequisite_id not in by_id:
            continue
        completed.add(prerequisite_id)
        prerequisite = by_id[prerequisite_id]
        pending.extend(prerequisite["dependencies"])
        prerequisite["status"] = "Verified"
        packages = prerequisite.get("delivery_packages", [])
        for index, package in enumerate(packages, start=1):
            package.update(
                status="Verified",
                accepted_merge_commit=f"{index:040x}",
                review_evidence="Synthetic accepted prerequisite package",
            )
        markdown = _sync_package_cards(markdown, packages)
    task["status"] = "In progress"
    p1.update(
        status="Verified",
        accepted_merge_commit="b" * 40,
        review_evidence="Synthetic accepted source and merge after worker producer",
    )
    p2["status"] = "In progress"
    assert CHECK.check_delivery_packages(
        data, _sync_package_cards(markdown, task["delivery_packages"]), plan
    ) == sum(len(row.get("delivery_packages", [None])) for row in data["tasks"])
    assert task["status"] != "Verified"
