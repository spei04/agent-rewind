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
        next(c for c in data["contracts"] if c["id"] == "C21")["status"] = "Available"
    elif variant == "active":
        tasks["RA-01-A"]["status"] = "Not started"
        tasks["RA-01-B"]["status"] = "In progress"
    elif variant == "schedule":
        data["schedule"][4]["work"] = {"RA-01-B": 0.5}
    elif variant == "capacity":
        data["schedule"][0]["work"] = {"RA-01-A": 1.0}
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
