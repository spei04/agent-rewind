"""Validate the narrow public-corpus planning amendment, never dataset admission."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = "contracts/research/public-corpus-plan.v1.json"
DECISION_PATH = "contracts/research/public-corpus-preparation.v1.json"
PLAN_SHA256 = "124f6c79a3c224537614442b9d22aaa78adbb1f7f2502ea29aa7cbcea823a3be"
DECISION_SHA256 = "8c3b7c95db2da979d8161a442321f103f2eed3b363fbd2fe3c5d9f602ba1f76f"
READY = {"Verified", "Satisfied"}
ACTIVE = READY | {"In progress", "Implemented; verification pending"}
PREPARATION: dict[str, tuple[str, str, list[str], float, list[float], list[float]]] = {
    "PCA1": ("AR-002-C", "RS", ["AR-002-B", "PUBLICPREP0"], 1, [1, 2], [2, 4]),
    "PCA2": ("PUBCAP-A", "BE", ["PCA1", "PUBLICPREP0"], 2, [2, 3], [1, 2]),
}
TEXT_FIELDS = {
    "title",
    "objective",
    "scope",
    "out_of_scope",
    "acceptance",
    "tests",
    "security_reliability",
    "definition_of_done",
}
FIELDS = TEXT_FIELDS | {
    "id",
    "aggregate_id",
    "kind",
    "role",
    "dependencies",
    "contracts",
    "effort_days",
    "effort_range_days",
    "confidence",
    "status",
    "source_commit",
    "accepted_merge_commit",
    "review_evidence",
}
# These hashes pin reviewed boundaries, not live status, acceptance evidence or estimates.
PREPARATION_BOUNDARY_SHA256 = {
    "PCA1": "5658d38c9d6ceb646ac1bc65fac6dfb4a799684e5673c4aee7eced28af30eea5",
    "PCA2": "909417c1a3e2c7e4b306344432453eaf0fe64610a1bd40ea111ca390d93214a8",
}
PROTECTED_BOUNDARY_SHA256 = "ac7c914cc81aedda77c28accf3761cb368d0e3553bf9542968ed731c359d54cd"
ADDED_BOUNDARY_FIELDS = (
    "id",
    "parent",
    "milestone",
    "role",
    "scope",
    "acceptance",
    "tests",
    "security_reliability",
    "out_of_scope",
    "definition_of_done",
    "contracts",
)
ADDED_BOUNDARY_SHA256 = "a5a9998a19b9ce7fde8c574bd223eee879ef2b64b069a7f440eecdda97d07ad2"
PROTECTED_TASK_PREFIXES = ("AR-035-", "AR-036-", "AR-037-", "AR-039-")
PROTECTED_GATES = ("DATA0", "PARTNER0", "G4", "G5")
NATIVE_DEPENDENCIES = {
    "AR-002-C": ["AR-002-B", "PUBLICPREP0", "PCA1"],
    "PUBCAP-A": ["PUBLICDATA0", "G2", "PCA2"],
    "PUBCAP-B": ["PUBCAP-A", "G2", "PUBLICDATA0", "CAPTUREFUNDS0"],
    "PUBCAP-C": ["PUBCAP-A", "AR-026-A", "G2", "PUBLICDATA0", "CAPTUREFUNDS0"],
    "PUBLICPREP0": ["AR-002-B"],
    "PUBLICDATA0": ["AR-002-C"],
    "CAPTUREFUNDS0": ["PAID0", "PUBLICDATA0", "PUBCAP-A"],
    "STUDYFUNDS0": ["AR-026-A", "AR-038-A"],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "Duplicate public planning JSON member")
        result[key] = value
    return result


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    ).hexdigest()


def load_record(path: str) -> dict[str, Any]:
    source = ROOT / path
    require(source.stat().st_size <= 2 * 1024 * 1024, "Public planning record exceeds bound")
    value = json.loads(source.read_text(), object_pairs_hook=unique_object)
    require(isinstance(value, dict), "Public planning record must be an object")
    return dict(value)


def preparation_nodes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index only the two reviewed exceptions, including accepted-source sequencing."""
    result: dict[str, dict[str, Any]] = {}
    for task in data["tasks"]:
        if "preparatory_prs" not in task:
            continue
        rows = task["preparatory_prs"]
        require(
            isinstance(rows, list) and len(rows) == 1 and "delivery_packages" not in task,
            "Invalid preparation allocation",
        )
        for row in rows:
            require(isinstance(row, dict) and set(row) == FIELDS, "Preparation fields differ")
            key = row["id"]
            require(isinstance(key, str) and key in PREPARATION, "Unknown preparation identity")
            require(key not in result, "Duplicate preparation identity")
            aggregate, role, dependencies, base, bounds, residual = PREPARATION[key]
            require(
                row["aggregate_id"] == task["id"] == aggregate
                and row["role"] == task["role"] == role,
                "Preparation aggregate/role differs",
            )
            require(
                row["kind"] == "offline_preparation"
                and row["contracts"] == ["C02"]
                and row["dependencies"] == dependencies,
                "Preparation kind/contracts/dependencies differ",
            )
            require(
                all(isinstance(row[field], str) and row[field].strip() for field in TEXT_FIELDS)
                and row["confidence"] == "medium",
                "Empty preparation boundary or confidence",
            )
            require(
                canonical_sha256({field: row[field] for field in sorted(TEXT_FIELDS)})
                == PREPARATION_BOUNDARY_SHA256[key],
                "Reviewed preparation boundary differs",
            )
            lower_upper = row["effort_range_days"]
            require(
                isinstance(lower_upper, list)
                and len(lower_upper) == 2
                and all(
                    type(v) in (int, float) and math.isfinite(v)
                    for v in [row["effort_days"], *lower_upper]
                )
                and row["effort_days"] == base
                and lower_upper == bounds,
                "Invalid preparation effort/range",
            )
            total = task["effort_range_days"]
            require(
                isinstance(total, list)
                and len(total) == 2
                and all(
                    type(v) in (int, float) and math.isfinite(v)
                    for v in [task["effort_days"], *total]
                )
                and task["effort_days"] == base + residual[0]
                and total == [bounds[i] + residual[i] for i in (0, 1)]
                and 0 < residual[0] <= residual[1],
                "Preparation residual effort/range differs",
            )
            require(
                isinstance(row["status"], str)
                and row["status"]
                in {"Not started", "In progress", "Implemented; verification pending", "Verified"},
                "Invalid preparation status",
            )
            evidence = [
                row[name] for name in ("source_commit", "accepted_merge_commit", "review_evidence")
            ]
            if row["status"] == "Verified":
                require(
                    all(
                        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
                        for value in evidence[:2]
                    )
                    and isinstance(evidence[2], str)
                    and bool(evidence[2].strip()),
                    "Verified preparation lacks accepted source/merge/review evidence",
                )
            else:
                require(
                    all(value is None for value in evidence),
                    "Unverified preparation cannot claim accepted evidence",
                )
            result[key] = row
    require(set(result) == set(PREPARATION), "Missing preparation identity")
    return result


def graph_nodes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = data["tasks"] + data["gates"] + list(preparation_nodes(data).values())
    nodes = {row["id"]: row for row in rows}
    require(len(nodes) == len(rows), "Duplicate planning node identity")
    return nodes


def protected_boundary(data: dict[str, Any]) -> dict[str, Any]:
    task_fields = (
        "id",
        "parent",
        "dependencies",
        "contracts",
        "scope",
        "acceptance",
        "out_of_scope",
    )
    gate_fields = ("id", "dependencies", "owner", "criteria", "kind", "effort_days")
    return {
        "tasks": [
            {field: row[field] for field in task_fields}
            for row in data["tasks"]
            if row["id"].startswith(PROTECTED_TASK_PREFIXES)
        ],
        "gates": [
            {field: row[field] for field in gate_fields}
            for row in data["gates"]
            if row["id"] in PROTECTED_GATES
        ],
        "C17": [
            {field: row[field] for field in ("id", "producer")}
            for row in data["contracts"]
            if row["id"] == "C17"
        ],
    }


def validate_amendment(
    data: dict[str, Any],
    amendment: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Check live public routing before any historical comparison projection."""
    amendment = load_record(PLAN_PATH) if amendment is None else amendment
    decision = load_record(DECISION_PATH) if decision is None else decision
    require(canonical_sha256(amendment) == PLAN_SHA256, "Pinned public amendment differs")
    require(canonical_sha256(decision) == DECISION_SHA256, "Scoped public owner decision differs")
    require(
        data.get("public_corpus_amendment") == {"record": PLAN_PATH, "sha256": PLAN_SHA256},
        "Public amendment binding differs",
    )
    for path, digest in amendment["preserved_artifact_sha256"].items():
        require(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest,
            f"Preserved historical artifact differs: {path}",
        )
    nodes = graph_nodes(data)
    require(len(nodes) <= 1000, "Planning graph exceeds review bound")
    graph = {key: row["dependencies"] for key, row in nodes.items()}
    for key, deps in graph.items():
        require(
            isinstance(deps, list) and all(isinstance(dep, str) for dep in deps),
            f"Invalid dependency list: {key}",
        )
        require(len(deps) == len(set(deps)), f"Duplicate dependency: {key}")
        require(all(dep in nodes for dep in deps), f"Unknown dependency: {key}")
    try:
        ordered = list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise ValueError("Dependency cycle in public amendment") from error
    for key, change in amendment["task_changes"].items():
        require(
            key in nodes
            and all(nodes[key][field] == value for field, value in change["after"].items()),
            f"Public route differs: {key}",
        )
    for key, dependencies in NATIVE_DEPENDENCIES.items():
        require(
            key in nodes and nodes[key]["dependencies"] == dependencies,
            f"Native/public prerequisites differ: {key}",
        )
    require(
        canonical_sha256(protected_boundary(data)) == PROTECTED_BOUNDARY_SHA256,
        "Customer/partner/pilot boundary differs",
    )
    prep_gate = nodes["PUBLICPREP0"]
    require(
        prep_gate["status"] == "Satisfied"
        and prep_gate["effort_days"] == 0
        and prep_gate.get("decision_record") == DECISION_PATH
        and prep_gate.get("decision_sha256") == DECISION_SHA256,
        "Scoped preparation decision gate differs",
    )
    for key, node in nodes.items():
        if key != "PUBLICPREP0":
            require(
                node.get("decision_record") != DECISION_PATH,
                "Preparation decision cannot authorize another node",
            )
        if key != "RESEARCHSCOPE0":
            require(
                node.get("decision_record") != "contracts/research/owner-decision.v1.json",
                "only recorded owner gate may cite this decision",
            )
    for key in ("PUBLICDATA0", "CAPTUREFUNDS0", "PAID0", "STUDYFUNDS0"):
        require(
            nodes[key]["status"] == "Not satisfied" and nodes[key]["effort_days"] == 0,
            "Preparation decision cannot satisfy native external gates",
        )
    ancestors: dict[str, set[str]] = {}
    for key in ordered:
        ancestors[key] = set(graph[key])
        for dep in graph[key]:
            ancestors[key].update(ancestors[dep])
    contracts = {row["id"]: row for row in data["contracts"]}
    require(contracts["C02"]["producer"] == "AR-002-A", "Original C02 producer differs")
    for key in PREPARATION:
        require("E0" in ancestors[key], f"Missing E0 ancestry: {key}")
        require(
            contracts["C02"]["producer"] in ancestors[key],
            f"Preparation C02 producer missing: {key}",
        )
        if nodes[key]["status"] in ACTIVE:
            require(
                all(nodes[dep]["status"] in READY for dep in graph[key]),
                f"Active or verified node precedes prerequisites: {key}",
            )
            require(
                re.match(r"^(?:Available|Reviewed)(?:$|[ :])", contracts["C02"]["status"])
                is not None,
                "Preparation consumes unavailable C02",
            )
    require(
        contracts["C06"]["producer"] == "AR-014-A"
        and "AR-014-A" in ancestors["G2"]
        and contracts["C06"]["producer"] in ancestors["PUBCAP-A"],
        "Native C06 producer missing from ancestry",
    )
    added_boundaries = {
        key: {field: nodes[key][field] for field in ADDED_BOUNDARY_FIELDS}
        for key in amendment["added_tasks"]
    }
    require(
        canonical_sha256(added_boundaries) == ADDED_BOUNDARY_SHA256,
        "Reviewed public aggregate boundary differs",
    )
    for key, original in amendment["customer_route_preserved"]["records"].items():
        require(
            all(
                nodes[key][field] == original[field]
                for field in (
                    "scope",
                    "acceptance",
                    "tests",
                    "out_of_scope",
                    "security_reliability",
                    "definition_of_done",
                )
            ),
            "Retained public research work differs",
        )
    for key in ("PUBCAP-B", "PUBCAP-C"):
        require(
            all(
                type(v) in (int, float) and math.isfinite(v)
                for v in [nodes[key]["effort_days"], *nodes[key]["effort_range_days"]]
            )
            and nodes[key]["effort_days"] == 1
            and nodes[key]["effort_range_days"] == [1, 2],
            "Capture effort/range differs",
        )
    for key in amendment["added_tasks"]:
        if nodes[key]["status"] in ACTIVE:
            require(
                all(nodes[dep]["status"] in READY for dep in graph[key]),
                f"Active or verified node precedes prerequisites: {key}",
            )
    return {key: nodes[key] for key in PREPARATION}


def legacy_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Restore only three reviewed fields for immutable C21 scope comparison."""
    validate_amendment(data)
    result = deepcopy(data)
    changes = load_record(PLAN_PATH)["task_changes"]
    for task in result["tasks"]:
        if task["id"] in changes:
            for field, value in changes[task["id"]]["before"].items():
                task[field] = deepcopy(value)
    return result


def check_preparation_cards(data: dict[str, Any], markdown: str, plan: str) -> None:
    rows = preparation_nodes(data)
    headings = list(re.finditer(r"^#### (PCA\d+) — (.+)$", markdown, re.M))
    require(
        len(headings) == len(rows) and {h[1] for h in headings} == set(rows),
        "Preparation card identities differ",
    )
    aliases = {
        "objective": "Objective",
        "scope": "Scope",
        "out_of_scope": "Out of scope",
        "acceptance": "Acceptance criteria",
        "tests": "Required automated tests",
        "security_reliability": "Security and reliability",
        "definition_of_done": "Definition of done",
    }
    for heading in headings:
        key, title = heading.groups()
        row = rows[key]
        body = re.split(r"^#{1,4} ", markdown[heading.end() :], maxsplit=1, flags=re.M)[0]
        pairs = re.findall(r"^- \*\*([^*]+):\*\* (.+)$", body, re.M)
        fields = dict(pairs)
        require(len(fields) == len(pairs), f"Duplicate preparation card field: {key}")
        require(
            title == row["title"]
            and all(fields.get(label) == row[field] for field, label in aliases.items()),
            f"Preparation card boundary differs: {key}",
        )
        expected = {
            "Kind": (
                "Offline preparation only; distinct machine dependency node, "
                "included in aggregate effort."
            ),
            "Aggregate": f"{row['aggregate_id']}.",
            "Required contracts": "C02.",
            "Confidence": f"{row['confidence']}.",
            "Responsible role": f"{row['role']}.",
            "Progress": f"{row['status']}.",
            "Effort allocation": (
                f"{row['effort_days']:g} engineering days; planning range "
                f"{row['effort_range_days'][0]:g}–{row['effort_range_days'][1]:g}; "
                f"included in {row['aggregate_id']}."
            ),
        }
        require(
            all(fields.get(label) == value for label, value in expected.items()),
            f"Preparation card allocation/status differs: {key}",
        )
        require(
            re.findall(r"\[([A-Z][A-Z0-9-]*)\]\(#", fields.get("Prerequisites", ""))
            == row["dependencies"],
            f"Preparation card dependencies differ: {key}",
        )
        evidence = "Pending; no accepted source/merge/review."
        if row["status"] == "Verified":
            evidence = (
                f"Source {row['source_commit']}; accepted merge "
                f"{row['accepted_merge_commit']}; review {row['review_evidence']}."
            )
        require(
            fields.get("Delivery evidence") == evidence,
            f"Preparation card delivery evidence differs: {key}",
        )
    for parent in ("AR-002", "PUBCAP"):
        count = sum(
            1 + len(task.get("preparatory_prs", []))
            for task in data["tasks"]
            if task["parent"] == parent
        )
        road = next((line for line in plan.splitlines() if line.startswith(f"| {parent} | M")), "")
        section = re.search(rf"^### {parent} — [^\n]+\n+([^\n]+)", markdown, re.M)
        require(
            f": {count} PRs." in road and section is not None and f"· {count} PRs" in section[1],
            "Preparation parent PR count differs",
        )
