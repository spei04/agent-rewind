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

    tasks = {task["id"]: task for task in data["tasks"]}
    task = tasks["AR-007-C"]
    # Sequencing fixtures rewind the producer and its packaged consumers,
    # including a ledger assignment that may be active in the live packet.
    rewound = ["AR-007-C", "AR-008-A", "AR-008-B", "AR-006-B", "AR-010-A"]
    for key in rewound:
        current = tasks[key]
        current["status"] = "In progress" if key == "AR-007-C" else "Not started"
        for package in current["delivery_packages"]:
            package.update(status="Not started", accepted_merge_commit=None, review_evidence=None)
            for pr in package.get("implementation_prs", []):
                pr.update(
                    status="Not started",
                    source_commit=None,
                    accepted_merge_commit=None,
                    review_evidence=None,
                )
            markdown = _sync_implementation_cards(markdown, package)
        markdown = _sync_package_cards(markdown, current["delivery_packages"])
        heading = re.search(rf"^#{{3,4}} {re.escape(key)} — .+$", markdown, re.M)
        assert heading is not None
        following = re.search(r"^#{1,4} ", markdown[heading.end() :], re.M)
        end = heading.end() + following.start() if following else len(markdown)
        body, count = re.subn(
            r"(?m)^(- \*\*(?:Progress|Status):\*\* ).*$",
            lambda match, status=current["status"]: match[1]
            + status
            + "; synthetic sequencing fixture.",
            markdown[heading.end() : end],
        )
        assert count == 1
        markdown = markdown[: heading.end()] + body + markdown[end:]

    # Keep parent rollups and their roadmap rows consistent with the copied tasks.
    lines = plan.splitlines()
    for parent_id in {tasks[key]["parent"] for key in rewound}:
        parent = data["parents"][parent_id]
        states = {tasks[key]["status"] for key in parent["children"]}
        parent["status"] = next(iter(states)) if len(states) == 1 else "In progress"
        displayed = "NS" if parent["status"] == "Not started" else parent["status"]
        matches = 0
        for index, line in enumerate(lines):
            cells = line.split("|")
            if len(cells) == 8 and cells[1].strip() == parent_id:
                cells[-2] = f" {displayed} "
                lines[index] = "|".join(cells)
                matches += 1
        assert matches == 1
    plan = "\n".join(lines) + "\n"
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
    ) == sum(CHECK.planned_delivery_prs(task) for task in data["tasks"])
    assert task["status"] == "In progress"


def test_delivery_fixture_rewinds_started_ledger_with_http(packet):
    data, markdown, plan = deepcopy(packet)
    tasks = {task["id"]: task for task in data["tasks"]}
    operation = tasks["AR-008-B"]
    operation["status"] = "Verified"
    for package in operation["delivery_packages"]:
        package.update(
            status="Verified",
            accepted_merge_commit="a" * 40,
            review_evidence="Synthetic completed HTTP prerequisite",
        )
    data["parents"]["AR-008"]["status"] = "Verified"
    ledger = tasks["AR-010-A"]
    ledger["status"] = ledger["delivery_packages"][0]["status"] = "In progress"
    data["parents"]["AR-010"]["status"] = "In progress"

    data, markdown, plan, _, _ = _delivery_packet((data, markdown, plan))
    ledger = next(task for task in data["tasks"] if task["id"] == "AR-010-A")
    assert ledger["status"] == data["parents"]["AR-010"]["status"] == "Not started"
    assert all(
        package["status"] == "Not started"
        and package["accepted_merge_commit"] is None
        and package["review_evidence"] is None
        for package in ledger["delivery_packages"]
    )
    CHECK.check_cards(data, markdown, plan)
    assert (
        CHECK.check_delivery_packages(data, markdown, plan)
        == data["validation"]["delivery_pr_count"]
    )


@pytest.mark.parametrize(
    "variant,message",
    [
        ("scope", "Delivery package card differs: AR-007-C/P1/out_of_scope"),
        ("pr_count", "Roadmap delivery PR count differs"),
        ("parent_count", "Backlog parent delivery PR count differs"),
        ("stored_count", "Stored metric differs: delivery_pr_count"),
    ],
)
def test_delivery_package_prose_and_pr_counts_are_checked(packet, variant, message):
    data, markdown, plan = deepcopy(packet)
    # These full-validator cases start valid, without a synthetic producer rewind.
    assert (
        CHECK.validate(data, markdown, plan)["delivery_pr_count"]
        == data["validation"]["delivery_pr_count"]
    )
    task = next(task for task in data["tasks"] if task["id"] == "AR-007-C")
    packages = task["delivery_packages"]
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
        marker = markdown.index("### AR-007 —")
        markdown = markdown[:marker] + markdown[marker:].replace(
            "4 PRs across 3 aggregate tasks", "3 PRs across 3 aggregate tasks", 1
        )
    else:
        data["validation"]["delivery_pr_count"] -= 1
    with pytest.raises(ValueError, match=message):
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
            for number, pr in enumerate(package.get("implementation_prs", []), 1):
                _accept_implementation_pr(pr, number)
            if package.get("implementation_prs"):
                final = package["implementation_prs"][-1]
                package["accepted_merge_commit"] = final["accepted_merge_commit"]
                package["review_evidence"] = final["review_evidence"]
                markdown = _sync_implementation_cards(markdown, package)
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
    ) == sum(CHECK.planned_delivery_prs(row) for row in data["tasks"])
    assert task["status"] != "Verified"


def test_implementation_pr_refinement_counts_prs_without_completing_package(packet):
    data, markdown, plan = packet
    result = CHECK.validate(data, markdown, plan)
    assert result["delivery_pr_count"] == 161
    task = next(t for t in data["tasks"] if t["id"] == "AR-010-A")
    p1, p2 = task["delivery_packages"]
    assert len(p1["implementation_prs"]) == 3
    assert p1["status"] == "In progress"
    assert p1["accepted_merge_commit"] is p1["review_evidence"] is None
    assert p2["status"] == "Not started"
    assert result["task_count"] == 151
    assert result["edge_count"] == 544
    assert result["base_effort_days"] == 464


def _sync_implementation_cards(markdown, package):
    import re

    for pr in package.get("implementation_prs", []):
        start = markdown.index(f"#### {pr['id']} —")
        following = re.search(r"^#{1,4} ", markdown[start + 5 :], re.M)
        end = start + 5 + following.start() if following else len(markdown)
        values = {
            "Progress": pr["status"],
            "Checkpoint evidence": (
                f"{pr['source_commit']} / {pr['accepted_merge_commit']}. {pr['review_evidence']}"
                if pr["status"] == "Merged; checkpoint accepted"
                else "Pending; no accepted source/merge/review"
            ),
            "Tracking PR": pr["tracking_pr"] or "Not assigned",
        }
        body = markdown[start:end]
        for label, value in values.items():
            body, count = re.subn(
                rf"(?m)^- \*\*{re.escape(label)}:\*\* .*$",
                lambda match, label=label, value=value: f"- **{label}:** {value.rstrip('.')}.",
                body,
            )
            assert count == 1
        markdown = markdown[:start] + body + markdown[end:]
    return markdown


def _accept_implementation_pr(pr, number):
    pr.update(
        status="Merged; checkpoint accepted",
        source_commit=f"{100 + number:040x}",
        accepted_merge_commit=f"{200 + number:040x}",
        review_evidence=f"Synthetic checkpoint {number}: reviewed source, PR/main and candidate",
        tracking_pr=f"https://github.com/spei04/agent-rewind/pull/{9000 + number}",
    )


@pytest.mark.parametrize("completed", [1, 2, 3])
def test_implementation_pr_acceptance_does_not_complete_parent_package(packet, completed):
    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-010-A")
    p1, p2 = task["delivery_packages"]
    for number, pr in enumerate(p1["implementation_prs"][:completed], 1):
        _accept_implementation_pr(pr, number)
    for pr in p1["implementation_prs"][completed:]:
        pr.update(
            status="Not started",
            source_commit=None,
            accepted_merge_commit=None,
            review_evidence=None,
            tracking_pr=None,
        )
    if completed < 3:
        p1["implementation_prs"][completed]["status"] = "In progress"
    markdown = _sync_implementation_cards(markdown, p1)
    assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 161
    assert p1["status"] == task["status"] == "In progress"
    assert p1["accepted_merge_commit"] is p1["review_evidence"] is None
    assert p2["status"] == "Not started"


def test_final_implementation_evidence_allows_explicit_p1_acceptance_and_p2_start(packet):
    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-010-A")
    p1, p2 = task["delivery_packages"]
    for number, pr in enumerate(p1["implementation_prs"], 1):
        _accept_implementation_pr(pr, number)
    final = p1["implementation_prs"][-1]
    p1.update(
        status="Verified",
        accepted_merge_commit=final["accepted_merge_commit"],
        review_evidence=final["review_evidence"],
    )
    p2["status"] = "In progress"
    markdown = _sync_package_cards(_sync_implementation_cards(markdown, p1), [p1, p2])
    assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 161
    assert task["status"] == "In progress"


@pytest.mark.parametrize(
    "variant,message",
    [
        ("empty", "Invalid implementation PR count"),
        ("one", "Invalid implementation PR count"),
        ("over_bound", "Invalid implementation PR count"),
        ("null_list", "Invalid implementation PR count"),
        ("duplicate", "Duplicate implementation PR identity"),
        ("order", "Implementation PR identities/order differ"),
        ("empty_scope", "Empty implementation PR boundary"),
        ("extra_effort", "Invalid implementation PR fields"),
        ("missing_input", "Implementation PR prerequisites differ"),
        ("extra_input", "Implementation PR prerequisites differ"),
        ("skip_predecessor", "Implementation PR prerequisites differ"),
        ("contract", "Implementation PR dropped inherited contracts"),
        ("role", "Implementation PR role differs"),
        ("status", "Invalid implementation PR status"),
        ("tracking", "Invalid implementation PR tracking"),
        ("unaccepted_evidence", "Unaccepted implementation PR claims evidence"),
        ("early_f2", "Implementation PR starts before accepted predecessor"),
        ("inactive_package", "Active implementation PR under unstarted package"),
        ("missing_source", "Implementation PR lacks source/merge/review evidence"),
        ("missing_merge", "Implementation PR lacks source/merge/review evidence"),
        ("missing_review", "Implementation PR lacks source/merge/review evidence"),
        ("missing_tracking", "Implementation PR lacks source/merge/review evidence"),
        ("premature_package", "Package completes before all implementation PRs"),
        ("early_p2", "Delivery package starts before accepted merged prerequisite"),
        ("wrong_final_merge", "Package acceptance differs from final implementation PR evidence"),
        ("wrong_final_review", "Package acceptance differs from final implementation PR evidence"),
        ("reused_merge", "Implementation PRs reuse accepted merge"),
        ("reused_tracking", "Implementation PRs reuse tracking identity"),
    ],
)
def test_implementation_pr_invalid_claims_reach_the_intended_gate(packet, variant, message):
    data, markdown, plan = deepcopy(packet)
    assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 161
    task = next(t for t in data["tasks"] if t["id"] == "AR-010-A")
    p1, p2 = task["delivery_packages"]
    prs = p1["implementation_prs"]
    if variant in ("unaccepted_evidence", "early_f2"):
        prs[0].update(
            status="In progress",
            source_commit=None,
            accepted_merge_commit=None,
            review_evidence=None,
        )
        for successor in prs[1:]:
            successor.update(
                status="Not started",
                source_commit=None,
                accepted_merge_commit=None,
                review_evidence=None,
                tracking_pr=None,
            )
        markdown = _sync_implementation_cards(markdown, p1)
        assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 161
    if variant in ("empty", "one", "over_bound", "null_list"):
        p1["implementation_prs"] = {
            "empty": [],
            "one": prs[:1],
            "over_bound": prs * 3,
            "null_list": None,
        }[variant]
    elif variant == "duplicate":
        prs[1]["id"] = prs[0]["id"]
    elif variant == "order":
        prs[1]["id"] = p1["id"] + "/F4"
    elif variant == "empty_scope":
        prs[0]["scope"] = " "
    elif variant == "extra_effort":
        prs[0]["effort_days"] = 3
    elif variant == "missing_input":
        prs[0]["dependencies"] = []
    elif variant == "extra_input":
        prs[0]["dependencies"].append("AR-005-C")
    elif variant == "skip_predecessor":
        prs[2]["dependencies"][-1] = prs[0]["id"]
    elif variant == "contract":
        prs[0]["contracts"] = []
    elif variant == "role":
        prs[0]["role"] = "QE"
    elif variant == "status":
        prs[0]["status"] = "Verified"
    elif variant == "tracking":
        prs[0]["tracking_pr"] = "https://example.invalid/pull/111"
    elif variant == "unaccepted_evidence":
        prs[0]["source_commit"] = "a" * 40
    elif variant == "early_f2":
        prs[1]["status"] = "In progress"
    elif variant == "inactive_package":
        p1["status"] = "Not started"
    elif variant.startswith("missing_"):
        _accept_implementation_pr(prs[0], 1)
        field = {
            "missing_source": "source_commit",
            "missing_merge": "accepted_merge_commit",
            "missing_review": "review_evidence",
            "missing_tracking": "tracking_pr",
        }[variant]
        prs[0][field] = None
    else:
        completed = 1 if variant in ("premature_package", "early_p2") else 3
        for number, pr in enumerate(prs[:completed], 1):
            _accept_implementation_pr(pr, number)
        if variant == "early_p2":
            p2["status"] = "In progress"
        elif variant in ("premature_package", "wrong_final_merge", "wrong_final_review"):
            p1.update(
                status="Verified",
                accepted_merge_commit=prs[-1]["accepted_merge_commit"] or "a" * 40,
                review_evidence=prs[-1]["review_evidence"] or "Synthetic premature package claim",
            )
            if variant == "wrong_final_merge":
                p1["accepted_merge_commit"] = prs[0]["accepted_merge_commit"]
            elif variant == "wrong_final_review":
                p1["review_evidence"] = prs[0]["review_evidence"]
        elif variant == "reused_merge":
            prs[1]["accepted_merge_commit"] = prs[0]["accepted_merge_commit"]
        else:
            prs[1]["tracking_pr"] = prs[0]["tracking_pr"]
        markdown = _sync_implementation_cards(markdown, p1)
        markdown = _sync_package_cards(markdown, [p1, p2])
    with pytest.raises(ValueError, match=message):
        CHECK.check_delivery_packages(data, markdown, plan)


@pytest.mark.parametrize("variant", ["scope", "progress", "evidence", "tracking", "missing_card"])
def test_implementation_pr_card_drift_is_rejected(packet, variant):
    import re

    data, markdown, plan = deepcopy(packet)
    assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 161
    p1 = next(t for t in data["tasks"] if t["id"] == "AR-010-A")["delivery_packages"][0]
    pr = p1["implementation_prs"][0]
    start = markdown.index(f"#### {pr['id']} —")
    end = markdown.index("#### AR-010-A/P1/F2")
    body = markdown[start:end]
    if variant == "missing_card":
        body = ""
    else:
        if variant in ("progress", "evidence"):
            label = "Progress" if variant == "progress" else "Checkpoint evidence"
            match = re.search(rf"(?m)^- \*\*{label}:\*\* .+$", body)
            assert match is not None
            old, new = match[0], f"- **{label}:** Synthetic inconsistent field."
        else:
            old, new = {
                "scope": (pr["scope"], "Scope omitted"),
                "tracking": (pr["tracking_pr"], "https://github.com/spei04/agent-rewind/pull/9999"),
            }[variant]
        assert old in body
        body = body.replace(old, new, 1)
    markdown = markdown[:start] + body + markdown[end:]
    with pytest.raises(
        ValueError, match="(?:Missing implementation PR card|Implementation PR card differs)"
    ):
        CHECK.check_delivery_packages(data, markdown, plan)


def test_legacy_packages_keep_one_pr_each_without_refinement(packet):
    import re

    data, markdown, plan = deepcopy(packet)
    task = next(t for t in data["tasks"] if t["id"] == "AR-010-A")
    p1 = task["delivery_packages"][0]
    del p1["implementation_prs"]
    start = markdown.index("#### AR-010-A/P1/F1")
    end = markdown.index("#### AR-010-A/P2")
    markdown = markdown[:start] + markdown[end:]
    markdown = markdown.replace(
        "151 aggregate tasks and 161 planned delivery PRs",
        "151 aggregate tasks and 159 planned delivery PRs",
        1,
    )
    markdown = re.sub(r"(### AR-010 —[^\n]+\n\nM1 / P0 · )6 PRs", r"\g<1>4 PRs", markdown)
    plan = plan.replace(
        "[AR-010](EXECUTION_BACKLOG.md#ar-010): 6 PRs.",
        "[AR-010](EXECUTION_BACKLOG.md#ar-010): 4 PRs.",
        1,
    )
    data["validation"]["delivery_pr_count"] = 159
    assert CHECK.validate(data, markdown, plan)["delivery_pr_count"] == 159
