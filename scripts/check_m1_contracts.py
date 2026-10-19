"""Validate the pending M1 proposal, traceability and frozen synthetic fixtures.

The default suite uses only the standard library; --openapi-model adds installed
FastAPI structural validation. Neither mode executes planned runtime behaviors.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import sys
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


def nodes(value: Any, location: str = "$"):
    if isinstance(value, dict):
        yield value, location
        for key, child in value.items():
            label = (
                key
                if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_$-]{1,80}", key)
                else "<member>"
            )
            yield from nodes(child, (location + "." + label)[-240:])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nodes(child, f"{location}[{index}]")


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


def _check_inventory(api: dict, data: dict, models: str, database: str) -> dict[str, int]:
    def require(ok: bool, message: str) -> None:
        if not ok:
            raise ValueError(message)

    require(api["openapi"] == "3.1.0", "Expected OpenAPI 3.1.0 proposal")
    require(api["x-source-baseline"] == data["baseline"], "Baseline identities disagree")
    refs = 0
    for node, location in nodes(api):
        if "$ref" in node:
            ref = node["$ref"]
            require(
                ref.startswith("#/"),
                f"Unsupported external reference at {location}; use a local #/ target",
            )
            target: Any = api
            try:
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"Unresolved reference at {location}; declare its local target"
                ) from exc
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
        read_json(root / "contracts/proposals/m1.openapi.json"),
        read_json(root / "contracts/proposals/m1.data-model.json"),
        read_bounded(root / "agent_rewind/models.py").decode(),
        read_bounded(root / "agent_rewind/database.py").decode(),
    )


MAX_FILE_BYTES = 1024 * 1024
MAX_NODES = 50000
MAX_DEPTH = 64
DIGEST = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
FIXTURE_NAMES = {
    "known",
    "unknown_schema",
    "partial_schema",
    "corrupt_ciphertext",
    "corrupt_address",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(MAX_FILE_BYTES + 1)
    require(len(content) <= MAX_FILE_BYTES, "Input exceeds the 1 MiB contract file limit")
    return content


def unique_members(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in values:
        require(key not in result, "Duplicate JSON member; remove the ambiguous declaration")
        result[key] = value
    return result


def bounded_tree(value: Any) -> None:
    pending, count = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        require(count <= MAX_NODES and depth <= MAX_DEPTH, "Contract tree exceeds node/depth limit")
        if isinstance(node, dict):
            pending.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            pending.extend((child, depth + 1) for child in node)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(read_bounded(path), object_pairs_hook=unique_members)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise ValueError("Invalid JSON document; check encoding, syntax and nesting") from None
    require(isinstance(value, dict), "Contract document must be a JSON object")
    bounded_tree(value)
    return value


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def check(api: dict, data: dict, models: str, database: str) -> dict[str, int]:
    """Preserve the original inventory API while bounding malformed inputs."""
    bounded_tree(api)
    bounded_tree(data)
    try:
        return _check_inventory(api, data, models, database)
    except (KeyError, TypeError, AttributeError, StopIteration, SyntaxError):
        raise ValueError(
            "Invalid inventory shape; check API components, entity fields and source AST"
        ) from None


def check_planned_acceptance(
    api: dict, data: dict, acceptance: dict, links: dict, fixture: dict
) -> int:
    require(acceptance.get("contract_version") == 1, "Unsupported acceptance contract version")
    require(
        acceptance.get("status") == "planned-not-executed",
        "Behavior cases must remain planned-not-executed",
    )
    require(
        links.get("contract_id") == "C04" and links.get("schema_version") == 1,
        "Unsupported C04 links contract",
    )
    require(
        links.get("acceptance_status") == "planned-not-executed",
        "Links cannot claim executed behavior",
    )
    require(set(acceptance["exit_gates"]) == {"G0", "G1"}, "Acceptance must retain G0 and G1 gates")
    cases = {}
    for case in acceptance["cases"]:
        identity = case["id"]
        require(
            isinstance(identity, str) and re.fullmatch(r"CT-M1-[0-9]{3}", identity) is not None,
            "Invalid acceptance case ID",
        )
        require(identity not in cases, f"Duplicate acceptance case ID: {identity}")
        require(
            all(
                isinstance(case.get(key), str) and case[key].strip()
                for key in ("issue", "layer", "given", "when", "then")
            ),
            f"Incomplete acceptance case: {identity}",
        )
        require(
            re.fullmatch(r"AR-00[5-9]|AR-01[0-2]", case["issue"]) is not None,
            f"Invalid M1 owner for {identity}",
        )
        cases[identity] = case
    operations = {
        operation["operationId"]
        for item in api["paths"].values()
        for method, operation in item.items()
        if method in METHODS
    }
    seen, mapped_operations, mapped_entities = set(), set(), set()
    for link in links["links"]:
        identity = link["case_id"]
        require(identity in cases, "Contract link references an unknown acceptance case ID")
        require(identity not in seen, f"Duplicate contract mapping: {identity}")
        seen.add(identity)
        require(link["issue"] == cases[identity]["issue"], f"Acceptance owner mismatch: {identity}")
        fields = ("operations", "entities", "fields", "schemas", "legacy_fixtures")
        for field in fields:
            values = link[field]
            require(
                isinstance(values, list) and all(isinstance(value, str) for value in values),
                f"Invalid {field} list for {identity}",
            )
            require(len(values) == len(set(values)), f"Duplicate {field} mapping for {identity}")
        require(any(link[field] for field in fields), f"Empty contract mapping: {identity}")
        require(set(link["operations"]) <= operations, f"Unknown operation mapping for {identity}")
        require(
            set(link["entities"]) <= data["entities"].keys(),
            f"Unknown entity mapping for {identity}",
        )
        require(
            set(link["schemas"]) <= api["components"]["schemas"].keys(),
            f"Unknown schema mapping for {identity}",
        )
        require(
            set(link["legacy_fixtures"]) <= fixture["variants"].keys(),
            f"Unknown fixture mapping for {identity}",
        )
        for field in link["fields"]:
            parts = field.split(".")
            require(
                len(parts) == 2 and parts[0] in link["entities"],
                f"Field mapping lacks its entity for {identity}",
            )
            require(
                parts[1] in data["entities"][parts[0]]["fields"],
                f"Missing logical field mapping for {identity}",
            )
        mapped_operations.update(link["operations"])
        mapped_entities.update(link["entities"])
    require(
        seen == cases.keys(),
        "Missing contract mapping for acceptance case(s): "
        + ", ".join(sorted(cases.keys() - seen)),
    )
    require(mapped_operations == operations, "API operation lacks an acceptance mapping")
    require(
        mapped_entities == data["entities"].keys(), "Logical entity lacks an acceptance mapping"
    )
    require(
        len(cases) == 24,
        "M1 baseline requires 24 planned cases; review any scope change explicitly",
    )
    return len(cases)


def fixture_schema(connection: sqlite3.Connection) -> dict:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    require(all(NAME.fullmatch(table) for table in tables), "Invalid fixture SQL table identifier")
    return {
        table: {
            "columns": [list(row) for row in connection.execute(f'PRAGMA table_info("{table}")')],
            "unique_indexes": sorted(
                [
                    [
                        column[2]
                        for column in connection.execute(
                            'PRAGMA index_info("' + row[1].replace('"', '""') + '")'
                        )
                    ]
                    for row in connection.execute(f'PRAGMA index_list("{table}")')
                    if row[2]
                ]
            ),
        }
        for table in tables
    }


def fixture_connection(sql: str) -> sqlite3.Connection:
    """Evaluate only bounded synthetic SQL in memory, with external I/O denied."""
    connection = sqlite3.connect(":memory:")
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_FILE_BYTES)
    connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_FILE_BYTES)
    connection.execute("PRAGMA max_page_count=128")
    denied = {
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_VTABLE,
        sqlite3.SQLITE_DROP_VTABLE,
    }

    def authorize(action, arg1, arg2, database, trigger):
        if action in denied or (
            action == sqlite3.SQLITE_FUNCTION and arg2 not in {"printf", "substr", "length"}
        ):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ticks = 0

    def progress():
        nonlocal ticks
        ticks += 1
        return int(ticks > 1000)

    connection.set_authorizer(authorize)
    connection.set_progress_handler(progress, 100)
    try:
        connection.executescript(sql)
    except sqlite3.Error:
        connection.close()
        raise ValueError(
            "Frozen SQL is invalid, exceeds bounds or requests forbidden I/O"
        ) from None
    connection.set_authorizer(None)
    return connection


def check_fixture(root: Path, fixture: dict, baseline: str) -> dict[str, int]:
    require(
        fixture.get("fixture_version") == 1 and fixture.get("synthetic_only") is True,
        "Legacy fixture must remain explicitly synthetic version 1",
    )
    require(
        fixture["source_commit"] == baseline,
        "Frozen fixture baseline differs from M1 source baseline",
    )
    require(set(fixture["variants"]) == FIXTURE_NAMES, "Missing or unknown frozen fixture variant")
    sql = read_bounded(root / "baseline.sql")
    require(
        sha256(sql) == fixture["baseline_sql_sha256"],
        "Frozen SQL checksum mismatch; restore the reviewed fixture",
    )
    objects = fixture["objects"]
    require(0 < len(objects) <= 100, "Legacy object count outside fixture bounds")
    addresses = set()
    for obj in objects.values():
        address = obj["address"]
        require(
            isinstance(address, str) and DIGEST.fullmatch(address) is not None,
            "Invalid frozen object address",
        )
        require(address not in addresses, "Duplicate frozen object address")
        addresses.add(address)
        require(
            DIGEST.fullmatch(obj["ciphertext_sha256"]) is not None,
            "Invalid frozen ciphertext checksum",
        )
        require(
            sha256(read_bounded(root / "objects" / address)) == obj["ciphertext_sha256"],
            "Frozen object ciphertext checksum mismatch",
        )
    require(
        {path.name for path in (root / "objects").iterdir()} == addresses,
        "Frozen object inventory differs from manifest",
    )
    classifications = set()
    for name, variant in fixture["variants"].items():
        classification = variant["classification"]
        require(classification not in classifications, "Duplicate fixture classification")
        classifications.add(classification)
        connection = fixture_connection(sql.decode() + variant["sql"])
        try:
            shape = fixture_schema(connection)
            require(sorted(shape) == variant["tables"], f"Frozen table inventory mismatch: {name}")
            require(
                sha256(canonical(shape)) == variant["schema_sha256"],
                f"Frozen schema fingerprint mismatch: {name}",
            )
            if name == "known":
                require(shape == fixture["schema"], "Frozen baseline schema structure mismatch")
                require(
                    set(shape) == fixture["expected_rows"].keys() == fixture["row_sha256"].keys(),
                    "Frozen row/table coverage mismatch",
                )
                for table, expected in fixture["expected_rows"].items():
                    require(len(expected) <= 1000, "Frozen row count exceeds bounds")
                    connection.row_factory = sqlite3.Row
                    order = "run_id, step" if table == "events" else "id"
                    actual = [
                        dict(row)
                        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}')
                    ]
                    if table == "records":
                        for row in actual:
                            row["data"] = json.loads(row["data"])
                    require(actual == expected, f"Frozen original row values changed: {table}")
                    require(
                        [sha256(canonical(row)) for row in actual] == fixture["row_sha256"][table],
                        f"Frozen row checksum mismatch: {table}",
                    )
        finally:
            connection.close()
        override = variant["object_override"]
        if override:
            require(
                override["address"] in addresses, "Corruption variant references unknown object"
            )
            file = override["file"]
            require(
                isinstance(file, str)
                and re.fullmatch(r"[a-z0-9-]+\.(bin|token)", file) is not None,
                "Unsafe corruption fixture path",
            )
            require(
                sha256(read_bounded(root / "variants" / file)) == override["ciphertext_sha256"],
                "Corruption fixture checksum mismatch",
            )
    baseline_schema = fixture["variants"]["known"]["schema_sha256"]
    for name, variant in fixture["variants"].items():
        changed_schema = name in {"unknown_schema", "partial_schema"}
        require(
            (variant["schema_sha256"] != baseline_schema) == changed_schema,
            "Fixture schema classifications no longer distinguish malformed history",
        )
        require(
            bool(variant["object_override"]) == name.startswith("corrupt_"),
            "Fixture corruption classification lacks the correct object override",
        )
    rows = fixture["expected_rows"]
    require(
        sum(job["reserved"] for job in rows["jobs"]) == fixture["reservation_total_microusd"],
        "Frozen reservation total mismatch",
    )
    runs = {row["id"]: row for row in rows["records"] if row["kind"] == "run"}
    require(set(runs) == fixture["runs"].keys(), "Frozen run identity coverage mismatch")
    for run_id, expected in fixture["runs"].items():
        run = runs[run_id]
        require(
            run["created"] == expected["created"]
            and run["data"]["head"] == expected["head"]
            and run["data"]["steps"] == expected["steps"],
            "Frozen run timestamp/head/step identity mismatch",
        )
        require(
            len(expected["expanded_event_hashes"]) == expected["steps"]
            and expected["expanded_event_hashes"][-1] == expected["head"],
            "Frozen expanded event head/count mismatch",
        )
    for event in rows["events"]:
        require(event["artifact"] in addresses, "Frozen event references missing artifact")
        require(
            event["hash"]
            == fixture["runs"][event["run_id"]]["expanded_event_hashes"][event["step"] - 1],
            "Frozen event hash disagrees with expanded history",
        )
    return {
        "frozen_objects": len(objects),
        "fixture_variants": len(fixture["variants"]),
        "frozen_rows": sum(len(values) for values in rows.values()),
    }


def check_pending_proposal(api: dict, data: dict, links: dict) -> None:
    """Stage-specific gate; not a permanent rule for approved contracts.

    A freeze revision must replace this gate with reviewed scope/approval-evidence
    validation. Structural inventory and planned-behavior checks are independent.
    """
    require(
        api.get("x-approval-status") == "pending",
        "Pending-proposal gate: OpenAPI approval metadata changed; review the freeze disposition",
    )
    require(
        data.get("approval_status") == "pending",
        "Pending-proposal gate: data approval metadata changed; review the freeze disposition",
    )
    require(
        links.get("approval_status") == "pending",
        "Pending-proposal gate: link approval metadata changed; review the freeze disposition",
    )


def check_proposal_suite(root: Path = ROOT, *, openapi_model: bool = False) -> dict:
    """Current proposal-only gate; passing does not approve or implement M1."""
    api, data, models, database = load(root)
    result = check(api, data, models, database)
    fixture_root = root / "tests/fixtures/legacy_v0"
    fixture = read_json(fixture_root / "manifest.json")
    links = read_json(root / "contracts/fixtures/m1-contract-links.json")
    check_pending_proposal(api, data, links)
    try:
        result["planned_acceptance_cases"] = check_planned_acceptance(
            api,
            data,
            read_json(root / "contracts/proposals/m1.acceptance.json"),
            links,
            fixture,
        )
        result.update(check_fixture(fixture_root, fixture, data["baseline"]))
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError(
            "Invalid contract/fixture shape; check required mapping and manifest members"
        ) from None
    if openapi_model:
        from fastapi.openapi.models import OpenAPI
        from pydantic import ValidationError

        try:
            OpenAPI.model_validate(api)
        except ValidationError:
            raise ValueError("Installed FastAPI rejected the proposed OpenAPI structure") from None
    return result | {
        "approval_status": "pending",
        "behavior_status": "planned-not-executed",
        "openapi_model_checked": openapi_model,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--openapi-model",
        action="store_true",
        help="Also validate with installed FastAPI; requires the project environment",
    )
    arguments = parser.parse_args()
    try:
        result = check_proposal_suite(openapi_model=arguments.openapi_model)
    except (ValueError, OSError, ImportError) as error:
        # Raw parser/model exception bodies and filesystem paths are never printed.
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "Required local input or installed dependency is unavailable"
        )
        print("Contract validation failed: " + message, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
