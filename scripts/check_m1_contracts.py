"""Check the M1 proposal's structural references and mapped persistence fields.

This deliberately uses only the standard library and does not certify OpenAPI
conformance, executable migrations, authorization, or runtime behavior.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
# Derived values are explicit: no claim that the logical model stores these directly.
PROJECTIONS = {
    "Accepted": {"operation_id": "operations.id", "job_id": "operations.job_id"},
    "RunSummary": {
        "id": "run_index.run_id",
        "project_id": "run_index.project_id",
        "created_at": "run_index.created_at",
        "status": "run_index.status",
        "branchable": "run_index.branchable",
        "parent_id": "run_index.parent_id",
        "event_head": "run_index.event_head",
    },
    "Operation": {
        "id": "operations.id",
        "project_id": "operations.project_id",
        "job_id": "operations.job_id",
        "client_operation_id": "operations.client_operation_id",
        "status": "legacy:jobs.status",
        "cancel_requested": "legacy:jobs.cancel",
        "result_run_id": "derived:authorized decrypted jobs.result run_id",
        "budget_microusd": "legacy:jobs.budget",
        "reserved_microusd": "legacy:jobs.reserved",
        "error": "derived:safe error envelope from jobs.error plus request context",
    },
    "Cancellation": {
        "operation_id": "operations.id",
        "cancel_requested": "legacy:jobs.cancel",
        "status": "legacy:jobs.status",
    },
}


def nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def legacy_tables(source: str) -> dict[str, set[str]]:
    tables = {}
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            tables[node.args[0].value] = {
                col.args[0].value
                for col in node.args[1:]
                if isinstance(col, ast.Call)
                and isinstance(col.func, ast.Name)
                and col.func.id == "Column"
                and col.args
                and isinstance(col.args[0], ast.Constant)
            }
    return tables


def check(api: dict, data: dict, models: str, database: str) -> dict[str, int]:
    def require(ok: bool, message: str) -> None:
        if not ok:
            raise ValueError(message)

    require(api["openapi"] == "3.1.0", "Expected OpenAPI 3.1.0 proposal")
    require(api["x-source-baseline"] == data["baseline"], "Baseline identities disagree")
    refs = 0
    for node in nodes(api):
        if "$ref" in node:
            ref = node["$ref"]
            require(ref.startswith("#/"), f"Unsupported external reference: {ref}")
            target: Any = api
            try:
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            except (KeyError, TypeError) as exc:
                raise ValueError(f"Unresolved reference: {ref}") from exc
            refs += 1
        if "properties" in node:
            require(
                set(node.get("required", [])) <= node["properties"].keys(),
                "Required property is missing its schema",
            )
    operation_ids = set()
    schemes = api["components"]["securitySchemes"]
    for path, item in api["paths"].items():
        for method in METHODS & item.keys():
            operation = item[method]
            identity = operation["operationId"]
            require(identity not in operation_ids, f"Duplicate operation ID: {identity}")
            operation_ids.add(identity)
            parameters = item.get("parameters", []) + operation.get("parameters", [])
            bound = {p["name"] for p in parameters if p.get("in") == "path"}
            require(
                bound == set(re.findall(r"{([^{}]+)}", path)),
                f"Path parameter mismatch: {method} {path}",
            )
            require(
                all(p.get("required") for p in parameters if p.get("in") == "path"),
                f"Optional path parameter: {path}",
            )
            for security in operation.get("security", api.get("security", [])):
                require(set(security) <= schemes.keys(), f"Unknown security scheme: {path}")
    schemas = api["components"]["schemas"]
    model = next(
        n for n in ast.parse(models).body if isinstance(n, ast.ClassDef) and n.name == "TaskSpec"
    )
    source_fields = {
        n.target.id
        for n in model.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    require(
        set(schemas["TaskDefinition"]["properties"]) == source_fields - {"budget_usd", "seed"},
        "TaskDefinition field coverage differs from TaskSpec",
    )
    tables = legacy_tables(database)
    covered = 0
    for schema, mapping in PROJECTIONS.items():
        require(
            set(schemas[schema]["properties"]) == set(mapping),
            f"Unmapped API projection field: {schema}",
        )
        for field, target in mapping.items():
            if target.startswith("derived:"):
                continue
            if target.startswith("legacy:"):
                table, column = target.removeprefix("legacy:").split(".")
                available = tables.get(table, set())
            else:
                table, column = target.split(".")
                available = data["entities"].get(table, {}).get("fields", {})
            require(column in available, f"Missing persistence field: {schema}.{field} -> {target}")
            covered += 1
    return {
        "operations": len(operation_ids),
        "internal_references": refs,
        "entities": len(data["entities"]),
        "legacy_tables": len(tables),
        "mapped_projection_fields": covered,
        "derived_projection_fields": 2,
    }


def load(root: Path = ROOT) -> tuple[dict, dict, str, str]:
    return (
        json.loads((root / "contracts/proposals/m1.openapi.json").read_text()),
        json.loads((root / "contracts/proposals/m1.data-model.json").read_text()),
        (root / "agent_rewind/models.py").read_text(),
        (root / "agent_rewind/database.py").read_text(),
    )


if __name__ == "__main__":
    print(json.dumps(check(*load()), sort_keys=True))
