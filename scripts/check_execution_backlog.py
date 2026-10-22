"""Recompute the execution ledger and its bounded conditional planning checks."""

from __future__ import annotations

import json
import math
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


def planned_delivery_prs(task: dict[str, Any]) -> int:
    """Count implementation PRs without multiplying package effort or DAG nodes."""
    count = 0
    for package in task.get("delivery_packages", [{}]):
        if "implementation_prs" not in package:
            count += 1
            continue
        prs = package["implementation_prs"]
        require(isinstance(prs, list) and 2 <= len(prs) <= 8, "Invalid implementation PR count")
        count += len(prs)
    return count


def check_implementation_prs(package: dict[str, Any], markdown: str) -> None:
    """Check structural references and sequencing, not remote delivery authenticity."""
    if "implementation_prs" not in package:
        return
    prs = package["implementation_prs"]
    require(isinstance(prs, list) and 2 <= len(prs) <= 8, "Invalid implementation PR count")
    text_fields = {
        "title",
        "objective",
        "scope",
        "out_of_scope",
        "interface_contracts",
        "acceptance",
        "tests",
        "security_reliability",
        "definition_of_done",
    }
    required = text_fields | {
        "id",
        "dependencies",
        "contracts",
        "role",
        "status",
        "source_commit",
        "accepted_merge_commit",
        "review_evidence",
        "tracking_pr",
    }
    for pr in prs:
        require(isinstance(pr, dict) and pr.keys() == required, "Invalid implementation PR fields")
        require(
            isinstance(pr["id"], str)
            and all(isinstance(pr[k], str) and pr[k].strip() for k in text_fields),
            "Empty implementation PR boundary",
        )
    parts = indexed(prs, "implementation PR")
    ids = [f"{package['id']}/F{i}" for i in range(1, len(prs) + 1)]
    require(list(parts) == ids, "Implementation PR identities/order differ")
    accepted = "Merged; checkpoint accepted"
    merges: list[str] = []
    tracking: list[str] = []
    for index, pr in enumerate(prs):
        key = pr["id"]
        deps = pr["dependencies"]
        require(
            isinstance(deps, list)
            and all(isinstance(v, str) for v in deps)
            and len(deps) == len(set(deps)),
            f"Invalid implementation PR dependencies: {key}",
        )
        expected_deps = set(package["dependencies"]) | ({ids[index - 1]} if index else set())
        require(set(deps) == expected_deps, f"Implementation PR prerequisites differ: {key}")
        require(
            isinstance(pr["contracts"], list)
            and all(isinstance(v, str) for v in pr["contracts"])
            and len(pr["contracts"]) == len(set(pr["contracts"]))
            and set(pr["contracts"]) == set(package["contracts"]),
            f"Implementation PR dropped inherited contracts: {key}",
        )
        require(pr["role"] == package["role"], f"Implementation PR role differs: {key}")
        require(
            pr["status"]
            in {"Not started", "In progress", "Implemented; verification pending", accepted},
            f"Invalid implementation PR status: {key}",
        )
        url = pr["tracking_pr"]
        require(
            url is None
            or (
                isinstance(url, str)
                and re.fullmatch(r"https://github\.com/spei04/agent-rewind/pull/[1-9][0-9]*", url)
                is not None
            ),
            f"Invalid implementation PR tracking: {key}",
        )
        if url is not None:
            tracking.append(url)
        if pr["status"] == accepted:
            require(
                all(
                    isinstance(pr[k], str) and re.fullmatch(r"[0-9a-f]{40}", pr[k]) is not None
                    for k in ("source_commit", "accepted_merge_commit")
                )
                and isinstance(pr["review_evidence"], str)
                and bool(pr["review_evidence"].strip())
                and url is not None,
                f"Implementation PR lacks source/merge/review evidence: {key}",
            )
            merges.append(pr["accepted_merge_commit"])
        else:
            require(
                all(
                    pr[k] is None
                    for k in ("source_commit", "accepted_merge_commit", "review_evidence")
                ),
                f"Unaccepted implementation PR claims evidence: {key}",
            )
        if pr["status"] != "Not started":
            require(
                package["status"] != "Not started",
                f"Active implementation PR under unstarted package: {key}",
            )
            require(
                not index or prs[index - 1]["status"] == accepted,
                f"Implementation PR starts before accepted predecessor: {key}",
            )
        heading = f"#### {key} — {pr['title']}\n"
        require(markdown.count(heading) == 1, f"Missing implementation PR card: {key}")
        body = markdown.split(heading, 1)[1]
        stop = re.search(r"^#{1,4} ", body, re.M)
        fields = dict(
            re.findall(r"^- \*\*([^*]+):\*\* (.+)$", body[: stop.start()] if stop else body, re.M)
        )
        values = {
            "Objective": pr["objective"],
            "Implementation scope": pr["scope"],
            "Out of scope": pr["out_of_scope"],
            "Required contracts": ", ".join(pr["contracts"]) + ". " + pr["interface_contracts"],
            "Acceptance criteria": pr["acceptance"],
            "Required automated tests": pr["tests"],
            "Security and reliability": pr["security_reliability"],
            "Definition of done": pr["definition_of_done"],
            "Prerequisites": ", ".join(f"[{k}](#{k.lower().replace('/', '-')})" for k in deps),
            "Responsible role": pr["role"],
            "Effort allocation": (
                f"Included in {package['id']}; no additional effort or acceptance package"
            ),
            "Progress": pr["status"],
            "Tracking PR": url or "Not assigned",
            "Checkpoint evidence": (
                f"{pr['source_commit']} / {pr['accepted_merge_commit']}. {pr['review_evidence']}"
                if pr["status"] == accepted
                else "Pending; no accepted source/merge/review"
            ),
        }
        for label, value in values.items():
            require(
                fields.get(label) == value.rstrip(".") + ".",
                f"Implementation PR card differs: {key}/{label}",
            )
    require(len(merges) == len(set(merges)), "Implementation PRs reuse accepted merge")
    require(len(tracking) == len(set(tracking)), "Implementation PRs reuse tracking identity")
    if package["status"] == "Verified":
        require(
            all(pr["status"] == accepted for pr in prs),
            "Package completes before all implementation PRs",
        )
        require(
            package["accepted_merge_commit"] == prs[-1]["accepted_merge_commit"]
            and package["review_evidence"] == prs[-1]["review_evidence"],
            "Package acceptance differs from final implementation PR evidence",
        )


def check_delivery_packages(data: dict[str, Any], markdown: str, plan: str) -> int:
    """Check optional sequential PR boundaries without changing aggregate DAG identity."""
    tasks = indexed(data["tasks"], "task")
    nodes = {**tasks, **indexed(data["gates"], "gate")}
    count = 0
    for task in tasks.values():
        packages = task.get("delivery_packages")
        if packages is None:
            count += 1
            continue
        require(isinstance(packages, list) and 2 <= len(packages) <= 8, "Invalid PR package count")
        count += planned_delivery_prs(task)
        parts = indexed(packages, "delivery package")
        expected_ids = [f"{task['id']}/P{i}" for i in range(1, len(packages) + 1)]
        require(list(parts) == expected_ids, "Delivery package identities/order differ")
        external: set[str] = set()
        contracts: set[str] = set()
        for index, package in enumerate(packages):
            key = package["id"]
            required = {
                "title",
                "objective",
                "role",
                "scope",
                "out_of_scope",
                "acceptance",
                "tests",
                "security_reliability",
                "definition_of_done",
                "confidence",
                "effort_days",
                "effort_range_days",
                "dependencies",
                "contracts",
                "interface_contracts",
                "status",
                "accepted_merge_commit",
                "review_evidence",
            }
            require(package.keys() >= required, f"Missing delivery package fields: {key}")
            require(
                all(
                    isinstance(package[name], str) and package[name].strip()
                    for name in (
                        "title",
                        "objective",
                        "scope",
                        "out_of_scope",
                        "acceptance",
                        "tests",
                        "security_reliability",
                        "definition_of_done",
                        "interface_contracts",
                    )
                ),
                f"Empty delivery package boundary: {key}",
            )
            lower, upper = package["effort_range_days"]
            require(
                all(
                    type(v) in (int, float) and math.isfinite(v)
                    for v in (lower, package["effort_days"], upper)
                )
                and 0 < lower <= package["effort_days"] <= upper,
                f"Invalid delivery package effort: {key}",
            )
            require(package["role"] == task["role"], "Delivery package role differs")
            require(
                package["status"]
                in {"Not started", "In progress", "Implemented; verification pending", "Verified"},
                f"Invalid delivery package status: {key}",
            )
            deps = package["dependencies"]
            require(len(deps) == len(set(deps)), "Duplicate delivery package dependency")
            internal = set(deps) & parts.keys()
            require(
                internal == ({expected_ids[index - 1]} if index else set()),
                f"Delivery package must depend on its preceding accepted PR: {key}",
            )
            external.update(set(deps) - parts.keys())
            if index == 0:
                require(
                    set(deps) >= set(task["dependencies"]),
                    "Delivery packages dropped inherited prerequisites",
                )
            require(
                set(deps) - parts.keys() <= set(task["dependencies"]),
                f"Delivery package bypasses aggregate prerequisites: {key}",
            )
            require(
                set(package["contracts"]) == set(task["contracts"]),
                f"Delivery package dropped inherited contracts: {key}",
            )
            contracts.update(package["contracts"])
            merge = package["accepted_merge_commit"]
            evidence = package["review_evidence"]
            if package["status"] == "Verified":
                require(
                    isinstance(merge, str)
                    and re.fullmatch(r"[0-9a-f]{40}", merge) is not None
                    and isinstance(evidence, str)
                    and bool(evidence.strip()),
                    f"Delivery package lacks accepted merge/review evidence: {key}",
                )
            else:
                require(
                    merge is None and evidence is None, f"Unverified package claims merge: {key}"
                )
            if package["status"] != "Not started":
                require(task["status"] != "Not started", "Active package under unstarted aggregate")
                require(
                    all(
                        parts[dep]["status"] == "Verified"
                        and isinstance(parts[dep]["accepted_merge_commit"], str)
                        for dep in internal
                    ),
                    f"Delivery package starts before accepted merged prerequisite: {key}",
                )
                require(
                    all(nodes[dep]["status"] in READY for dep in task["dependencies"]),
                    f"Delivery package starts before aggregate prerequisites: {key}",
                )
            check_implementation_prs(package, markdown)
            heading = f"#### {key} — {package['title']}"
            require(markdown.count(heading + "\n") == 1, f"Missing delivery package card: {key}")
            body = markdown.split(heading + "\n", 1)[1]
            stop = re.search(r"^#{1,4} ", body, re.M)
            fields = dict(
                re.findall(
                    r"^- \*\*([^*]+):\*\* (.+)$",
                    body[: stop.start()] if stop else body,
                    re.M,
                )
            )
            for label, field in {
                "Objective": "objective",
                "Implementation scope": "scope",
                "Out of scope": "out_of_scope",
                "Acceptance criteria": "acceptance",
                "Required automated tests": "tests",
                "Security and reliability": "security_reliability",
                "Definition of done": "definition_of_done",
            }.items():
                require(
                    fields.get(label) == package[field].rstrip(".") + ".",
                    f"Delivery package card differs: {key}/{field}",
                )
            documented_deps = re.findall(
                r"\[([A-Z][A-Z0-9/-]*)\]\(#", fields.get("Prerequisites", "")
            )
            require(
                set(documented_deps) == set(deps),
                f"Delivery package card dependencies differ: {key}",
            )
            require(
                fields.get("Required contracts")
                == ", ".join(package["contracts"]) + ". " + package["interface_contracts"] + ".",
                f"Delivery package card contracts differ: {key}",
            )
            require(
                fields.get("Effort / confidence")
                == f"{package['effort_days']:g} engineering days; "
                f"planning range {lower:g}–{upper:g}; {package['confidence']} confidence.",
                f"Delivery package card effort differs: {key}",
            )
            require(
                fields.get("Progress", "").startswith(package["status"])
                and fields.get("Responsible role", "").startswith(package["role"]),
                f"Delivery package card status/role differs: {key}",
            )
        require(
            external == set(task["dependencies"]),
            "Delivery packages dropped inherited prerequisites",
        )
        require(
            contracts == set(task["contracts"]), "Delivery packages dropped inherited contracts"
        )
        require(
            sum(p["effort_days"] for p in packages) == task["effort_days"]
            and [sum(p["effort_range_days"][i] for p in packages) for i in (0, 1)]
            == task["effort_range_days"],
            "Delivery package effort/range rollup differs",
        )
        if task["status"] == "Verified":
            require(
                all(p["status"] == "Verified" for p in packages),
                "Aggregate completes before all delivery packages",
            )
        parent = task["parent"]
        parent_prs = sum(
            planned_delivery_prs(tasks[k]) for k in data["parents"][parent]["children"]
        )
        row = next((line for line in plan.splitlines() if line.startswith(f"| {parent} | M")), "")
        require(f": {parent_prs} PRs." in row, "Roadmap delivery PR count differs")
        parent_section = re.search(rf"^### {re.escape(parent)} — [^\n]+\n+([^\n]+)", markdown, re.M)
        require(
            parent_section is not None and f"· {parent_prs} PRs" in parent_section[1],
            "Backlog parent delivery PR count differs",
        )
    require(
        f"{len(tasks)} aggregate tasks and {count} planned delivery PRs" in markdown,
        "Backlog delivery PR count differs",
    )
    return count


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
    for key in ("AR-020-A", "AR-024-A"):
        require(
            "RESEARCHSCOPE0" in graph[key],
            f"Research producer lacks owner decision gate: {key}",
        )
    require(
        graph.get("RESEARCHSCOPE0") == ["RA-01-B"],
        "Research decision gate lacks accepted design prerequisite",
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
        "delivery_pr_count": check_delivery_packages(data, markdown, plan),
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
            line
            for line in markdown.splitlines()
            if line.startswith(f"| {context.get('row_label', 'RA Day')} {row['day']} |")
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
