"""Recompute the execution ledger and its bounded conditional planning checks."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = r"(?:AR-\d{3}|RA-\d{2})-[A-Z]"
READY = {"Verified", "Satisfied"}
REQUIRED = {
    "id",
    "parent",
    "milestone",
    "priority",
    "title",
    "objective",
    "role",
    "effort_days",
    "effort_range_days",
    "confidence",
    "dependencies",
    "contracts",
    "scope",
    "acceptance",
    "tests",
    "security_reliability",
    "out_of_scope",
    "status",
    "definition_of_done",
    "review_roles",
    "pull_request_boundary",
    "contracts_status",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON member")
        result[key] = value
    return result


def contract_available(contract: dict[str, Any]) -> bool:
    return re.match(r"^(?:Available|Reviewed)(?:$|[ :])", contract["status"]) is not None


def indexed(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result = {row["id"]: row for row in rows}
    require(len(result) == len(rows), f"Duplicate {label} identity")
    return result


def check_cards(data: dict[str, Any], markdown: str, plan: str) -> None:
    headings = list(re.finditer(rf"^#{{3,4}} ({TASK_ID}) — (.+)$", markdown, re.M))
    cards: dict[str, tuple[str, dict[str, str]]] = {}
    for heading in headings:
        identifier, title = heading.groups()
        require(identifier not in cards, f"Duplicate card {identifier}")
        remainder = markdown[heading.end() :]
        stop = re.search(r"^#{1,4} ", remainder, re.M)
        body = remainder[: stop.start()] if stop else remainder
        fields = dict(re.findall(r"^- \*\*([^*]+):\*\* (.+)$", body, re.M))
        cards[identifier] = (title, fields)
    require(set(cards) == {t["id"] for t in data["tasks"]}, "Task/card identities differ")
    for task in data["tasks"]:
        identifier = task["id"]
        title, fields = cards[identifier]
        require(title == task["title"], f"Card title differs: {identifier}")
        aliases = {
            "scope": ("Implementation scope / PR boundary", "Implementation scope"),
            "dependencies": ("Prerequisites", "Prerequisites and dependencies"),
            "tests": ("Required automated tests", "Required automated checks"),
            "role": ("Responsible role", "Responsible role / review"),
            "status": ("Progress", "Status"),
        }
        selected = {
            key: next((fields[n] for n in names if n in fields), "")
            for key, names in aliases.items()
        }
        required = (
            "Objective",
            "Out of scope",
            "Required contracts",
            "Acceptance criteria",
            "Security and reliability",
            "Effort / confidence",
            "Definition of done",
        )
        require(
            all(fields.get(name) for name in required) and all(selected.values()),
            f"Missing card fields: {identifier}",
        )
        dependencies = re.findall(r"\[([A-Z][A-Z0-9-]*)\]\(#", selected["dependencies"])
        require(
            set(dependencies) == set(task["dependencies"]),
            f"Card dependencies differ: {identifier}",
        )
        require(
            set(re.findall(r"\bC\d{2}\b", fields["Required contracts"])) == set(task["contracts"]),
            f"Card contracts differ: {identifier}",
        )
        require(selected["status"].startswith(task["status"]), f"Card status differs: {identifier}")
        require(selected["role"].startswith(task["role"]), f"Card role differs: {identifier}")
        effort = re.match(r"([\d.]+) engineering days?", fields["Effort / confidence"])
        require(
            effort is not None and float(effort[1]) == task["effort_days"],
            f"Card effort differs: {identifier}",
        )
        bounds = re.search(r"planning range ([\d.]+)–([\d.]+)", fields["Effort / confidence"])
        require(
            bounds is not None
            and [float(bounds[1]), float(bounds[2])] == task["effort_range_days"],
            f"Card effort range differs: {identifier}",
        )
        require(
            task["confidence"] in fields["Effort / confidence"],
            f"Card confidence differs: {identifier}",
        )
    parents = {}
    for line in plan.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) == 8 and re.fullmatch(r"AR-\d{3}|RA-\d{2}", parts[1]):
            require(parts[1] not in parents, f"Duplicate roadmap parent {parts[1]}")
            parents[parts[1]] = parts[-2]
    require(set(parents) == set(data["parents"]), "Roadmap parent identities differ")
    for identifier, parent in data["parents"].items():
        require(
            parents[identifier].replace("NS", "Not started") == parent["status"],
            f"Roadmap parent status differs: {identifier}",
        )


def validate(data: dict[str, Any], markdown: str, plan: str) -> dict[str, Any]:
    tasks = indexed(data["tasks"], "task")
    gates = indexed(data["gates"], "gate")
    require(not (tasks.keys() & gates.keys()), "Task/gate identity overlap")
    nodes = {**tasks, **gates}
    contracts = indexed(data["contracts"], "contract")
    require(len(nodes) <= 1000, "Planning graph exceeds review bound")
    for task in tasks.values():
        require(task.keys() >= REQUIRED, f"Missing task fields: {task['id']}")
        lower, upper = task["effort_range_days"]
        require(0 < lower <= task["effort_days"] <= upper, f"Invalid effort: {task['id']}")
        require(task["parent"] in data["parents"], f"Unknown parent: {task['id']}")
    graph = {key: row["dependencies"] for key, row in nodes.items()}
    for key, deps in graph.items():
        require(len(deps) == len(set(deps)), f"Duplicate dependency: {key}")
        require(all(dep in nodes for dep in deps), f"Unknown dependency: {key}")
    try:
        ordered = list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise ValueError("Dependency cycle") from error
    ancestors: dict[str, set[str]] = {}
    paths: dict[str, tuple[float, list[str]]] = {}
    for key in ordered:
        ancestors[key] = set(graph[key])
        for dep in graph[key]:
            ancestors[key].update(ancestors[dep])
        previous: tuple[float, list[str]] = max(
            (paths[dep] for dep in graph[key]), key=lambda item: item[0], default=(0, [])
        )
        paths[key] = (previous[0] + nodes[key]["effort_days"], previous[1] + [key])
        if nodes[key]["status"] in READY | {"In progress"}:
            require(
                all(nodes[dep]["status"] in READY for dep in graph[key]),
                f"Active or verified node precedes prerequisites: {key}",
            )
    for contract in contracts.values():
        producer = contract["producer"]
        require(producer is None or producer in tasks, "Unknown contract producer")
        if producer is not None and contract_available(contract):
            require(
                tasks[producer]["status"] == "Verified", "Unreviewed contract claims availability"
            )
    for key, task in tasks.items():
        require("E0" in ancestors[key], f"Missing E0 ancestry: {key}")
        for contract_id in task["contracts"]:
            require(contract_id in contracts, f"Unknown contract: {key}")
            producer = contracts[contract_id]["producer"]
            require(
                producer is None or producer == key or producer in ancestors[key],
                f"Contract producer missing from ancestry: {key}/{contract_id}",
            )
            if task["status"] in READY | {"In progress"} and producer != key:
                require(
                    contract_available(contracts[contract_id]),
                    f"Active or verified task consumes unavailable contract: {key}/{contract_id}",
                )
            if producer is None:
                require(
                    contract_id == "C04"
                    and contracts[contract_id]["status"].startswith("Reviewed"),
                    f"Unowned contract is not an accepted freeze: {contract_id}",
                )
    children = []
    for key, parent in data["parents"].items():
        group = [tasks[identifier] for identifier in parent["children"]]
        children.extend(parent["children"])
        require(all(t["parent"] == key for t in group), f"Child parent differs: {key}")
        require(
            sum(t["effort_days"] for t in group) == parent["base_effort_days"],
            f"Parent effort differs: {key}",
        )
        status = (
            "Verified"
            if all(t["status"] == "Verified" for t in group)
            else "Not started"
            if all(t["status"] == "Not started" for t in group)
            else "In progress"
        )
        require(parent["status"] == status, f"Parent status differs: {key}")
    require(
        len(children) == len(tasks) and set(children) == set(tasks), "Parent membership differs"
    )
    roles: defaultdict[str, float] = defaultdict(float)
    milestones: defaultdict[str, float] = defaultdict(float)
    for task in tasks.values():
        roles[task["role"]] += task["effort_days"]
        milestones[task["milestone"]] += task["effort_days"]
    longest = max((paths[key] for key in nodes), key=lambda item: (item[0], len(item[1])))
    computed = {
        "task_count": len(tasks),
        "parent_count": len(data["parents"]),
        "gate_count": len(gates),
        "contract_count": len(contracts),
        "edge_count": sum(len(v) for v in graph.values()),
        "base_effort_days": sum(t["effort_days"] for t in tasks.values()),
        "upper_range_days": round(sum(t["effort_range_days"][1] for t in tasks.values()), 4),
        "role_effort_days": dict(roles),
        "milestone_effort_days": dict(milestones),
        "effort_only_critical_path_days": longest[0],
        "effort_only_critical_path": longest[1],
    }
    for key, value in computed.items():
        require(data["validation"][key] == value, f"Stored metric differs: {key}")
    conditions = data["first_two_weeks_conditions"]
    require(
        all(
            key in nodes and nodes[key]["status"] in READY and day == 0
            for key, day in conditions.items()
        ),
        "Unverified schedule opening condition",
    )
    context = data["schedule_context"]
    allocated: defaultdict[str, float] = defaultdict(float)
    finished = dict(conditions)
    require([row["day"] for row in data["schedule"]] == list(range(1, 11)), "Expected ten days")
    for row in data["schedule"]:
        contributors: defaultdict[str, float] = defaultdict(float)
        for key, effort in row["work"].items():
            require(key in tasks and effort > 0, "Invalid scheduled work")
            require(
                all(dep in finished and finished[dep] < row["day"] for dep in graph[key]),
                f"Scheduled before prerequisite acceptance: {key}/day{row['day']}",
            )
            contributor = context["task_contributors"][key]
            contributors[contributor] += effort
            allocated[key] += effort
            require(allocated[key] <= tasks[key]["effort_days"], f"Overallocated task: {key}")
            if allocated[key] == tasks[key]["effort_days"]:
                finished[key] = max(
                    row["day"], context["review_acceptance_days"].get(key, row["day"])
                )
        require(
            len(contributors) <= context["concurrent_contributor_slots"], "Too many contributors"
        )
        require(
            all(
                effort <= context["max_delivery_days_per_contributor_per_day"]
                for effort in contributors.values()
            ),
            "Contributor overbooked",
        )
        matches = [
            line for line in markdown.splitlines() if line.startswith(f"| RA Day {row['day']} |")
        ]
        require(len(matches) == 1, "Conditional schedule row missing or duplicate")
        documented = {
            key: float(effort)
            for key, effort in re.findall(rf"\[({TASK_ID})\]\(#[^)]+\) \(([\d.]+)d\)", matches[0])
        }
        require(documented == row["work"], "Documented schedule allocation differs")
    require(
        all(value == tasks[key]["effort_days"] for key, value in allocated.items()),
        "Scheduled task has incomplete base allocation",
    )
    require(
        context["concurrent_contributor_slots"]
        == data["execution_capacity"]["concurrent_contributor_slots"],
        "Schedule capacity differs",
    )
    for key in context["unscheduled_approved_queue"]:
        require(
            key in tasks
            and tasks[key]["status"] == "Not started"
            and all(nodes[dep]["status"] in READY for dep in graph[key]),
            f"Unscheduled queue incorrectly claims ready prerequisites: {key}",
        )
    for amendment in data["research_amendments"]:
        require(all(key in tasks for key in amendment["task_ids"]), "Amendment task is not active")
        require(
            all("RA-01-B" in ancestors[key] for key in amendment["affected_tasks"]),
            "Research consumer lacks accepted design dependency",
        )
    for key in (
        "dag_acyclic",
        "contract_producers_available_before_consumers",
        "schedule_no_predecessor_violations_conditional_on_stated_approvals",
    ):
        require(data["validation"][key] is True, f"Stored audit flag differs: {key}")
    check_cards(data, markdown, plan)
    return computed


def main() -> None:
    source = ROOT / "contracts/proposals/execution-backlog.json"
    require(source.stat().st_size <= 2 * 1024 * 1024, "Ledger exceeds review bound")
    result = validate(
        json.loads(source.read_text(), object_pairs_hook=unique_object),
        (ROOT / "docs/EXECUTION_BACKLOG.md").read_text(),
        (ROOT / "docs/PLAN.md").read_text(),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
