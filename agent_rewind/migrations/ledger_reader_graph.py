"""Observed bounded keyset transport for the unchanged relational graph proof."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .inputs import validate_mapping
from .ledger_check import LedgerCheck
from .ledger_graph_sql import SQL
from .ledger_reader_history import History
from .ownership_lineage import Closure, reduce_relational_closure
from .schema import MigrationRefused, dialect

_STREAMS = {
    "SELECT id,kind FROM jobs ORDER BY id": "jobs",
    "SELECT id,revoked,expires FROM api_keys ORDER BY id": "api_keys",
    "SELECT id,kind,CAST(data AS TEXT) AS data FROM records ORDER BY id": "records",
    "SELECT run_id,step FROM events ORDER BY run_id,step": "events",
}
_FIELDS = {
    "jobs": ("id", "kind", "scope_project_id", "invalid"),
    "api_keys": ("id", "revoked", "expires", "scope_project_id", "invalid"),
    "records": ("id", "kind", "data", "scope_project_id", "invalid"),
    "events": ("run_id", "step", "invalid"),
}


@dataclass(frozen=True)
class Graph:
    closure: Closure
    projects: dict[tuple[str, str], str]


def _query(connection: Connection, name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            text(SQL[("all", dialect(connection), name)]), parameters
        ).mappings()
    ]


@dataclass(frozen=True)
class SourceBounds:
    rows: int
    native_bytes: int
    max_native_bytes: int


def source_bounds(connection: Connection, work: LedgerCheck) -> dict[str, int]:
    return {name: receipt.rows for name, receipt in read_source_bounds(connection, work).items()}


def read_source_bounds(connection: Connection, work: LedgerCheck) -> dict[str, SourceBounds]:
    """Expose the existing complete native receipts without transferring row bodies."""
    total_rows = total_bytes = 0
    receipts = {}
    for table in ("api_keys", "audit", "events", "jobs", "records"):
        work.check()
        rows = _query(
            connection,
            "source_count_" + table,
            {"remaining_rows_plus_one": 1000000 - total_rows + 1},
        )
        if len(rows) != 1 or type(rows[0]["candidate_rows"]) is not int:
            raise MigrationRefused("invalid_source_data")
        count = rows[0]["candidate_rows"]
        if not 0 <= count <= 1000000 - total_rows:
            raise MigrationRefused("source_limit_exceeded")
        rows = _query(connection, "source_stats_" + table, {})
        if len(rows) != 1 or any(type(value) is not int or value < 0 for value in rows[0].values()):
            raise MigrationRefused("invalid_source_data")
        receipt = rows[0]
        if receipt["observed_rows"] != count or receipt["graph_invalid_rows"]:
            raise MigrationRefused("ownership_lineage_invalid")
        total_rows += count
        total_bytes += receipt["original_native_bytes"]
        if total_bytes > 1073741824 or receipt["max_original_native_bytes"] > 16777216:
            raise MigrationRefused("source_limit_exceeded")
        receipts[table] = SourceBounds(
            count, receipt["original_native_bytes"], receipt["max_original_native_bytes"]
        )
    return receipts


def read_graph(
    connection: Connection,
    counts: dict[str, int],
    history: History,
    financial: dict[str, list[dict[str, Any]]],
    work: LedgerCheck,
) -> Graph:
    projects: dict[tuple[str, str], str] = {}
    organization = history.ownership.organization_id

    def stream(sql: str) -> Iterable[Any]:
        table = _STREAMS[sql]
        keys = ("run_id", "step") if table == "events" else ("id",)
        after: tuple[Any, ...] | None = None
        observed = 0
        while True:
            work.check()
            suffix = "first" if after is None else "next"
            parameters: dict[str, Any] = (
                {} if table == "events" else {"installation_org": organization}
            )
            if after is not None:
                parameters.update(
                    ("after_" + key, value) for key, value in zip(keys, after, strict=True)
                )
            gates = _query(connection, "graph_page_gate_" + table + "_" + suffix, parameters)
            if len(gates) != 1:
                raise MigrationRefused("ownership_lineage_invalid")
            gate = gates[0]
            if any(
                type(gate[name]) is not int
                for name in (
                    "candidates",
                    "invalid_candidates",
                    "accepted_rows",
                    "accepted_original_native_bytes",
                )
            ):
                raise MigrationRefused("ownership_lineage_invalid")
            if not 0 <= gate["candidates"] <= 4096 or gate["invalid_candidates"] != 0:
                raise MigrationRefused("ownership_lineage_invalid")
            if gate["candidates"] == 0:
                if (
                    gate["accepted_rows"]
                    or gate["accepted_original_native_bytes"]
                    or observed != counts[table]
                ):
                    raise MigrationRefused("ownership_lineage_invalid")
                break
            if not 1 <= gate["accepted_rows"] <= gate["candidates"] or not (
                0 <= gate["accepted_original_native_bytes"] <= 16777216
            ):
                raise MigrationRefused("source_limit_exceeded")
            endpoint = tuple(gate["end_" + key] for key in keys)
            if endpoint == after or any(value is None for value in endpoint):
                raise MigrationRefused("ownership_lineage_invalid")
            parameters.update(
                ("through_" + key, value) for key, value in zip(keys, endpoint, strict=True)
            )
            batch = _query(connection, "graph_page_body_" + table + "_" + suffix, parameters)
            if (
                len(batch) != gate["accepted_rows"]
                or tuple(batch[-1][key] for key in keys) != endpoint
            ):
                raise MigrationRefused("ownership_lineage_invalid")
            observed += len(batch)
            if observed > counts[table]:
                raise MigrationRefused("ownership_lineage_invalid")
            # Ordering and native bytes are proved by the fixed SQL prefix under exclusion.
            # The derived UTF-8 transport ceiling is not an observed Python-byte receipt.
            for row in batch:
                work.check()
                if set(row) != set(_FIELDS[table]) or row["invalid"] != 0:
                    raise MigrationRefused("ownership_lineage_invalid")
                if table != "events":
                    kind = (
                        row["kind"] if table == "records" else ("job" if table == "jobs" else "key")
                    )
                    identity = (kind, row["id"])
                    if identity in projects:
                        raise MigrationRefused("ownership_lineage_invalid")
                    projects[identity] = row["scope_project_id"]
                yield SimpleNamespace(**row)
            after = endpoint

    closure = reduce_relational_closure(stream, check=work.check, projects=projects)
    financial_scopes = {
        (row["resource_kind"], row["resource_id"]): row["project_id"] for row in financial["scope"]
    }
    for key, project in projects.items():
        work.check()
        if key[0] == "job" and financial_scopes.get(key) != project:
            raise MigrationRefused("ownership_lineage_invalid")
    if history.adoption["source_kind"] == "legacy":
        mapping = validate_mapping(history.adoption["mapping"])
        dispositions = {value.key_id: value.role for value in mapping.key_dispositions}
        if any(key_id not in closure.keys for key_id in dispositions):
            raise MigrationRefused("unknown_key_disposition")
        if any(
            grant.principal_id.startswith("api-key:")
            and dispositions.get(grant.principal_id[8:]) != grant.role
            for grant in mapping.principal_grants
        ):
            raise MigrationRefused("invalid_key_grant")
    for grant in history.ownership.grants:
        work.check()
        if grant.principal_id.startswith("api-key:"):
            key_id = grant.principal_id[8:]
            if (
                key_id not in closure.keys
                or projects.get(("key", key_id)) != history.ownership.project_id
            ):
                raise MigrationRefused("ownership_progress_invalid")
    expected = len(closure.resources) + len(financial["call"])
    rows = _query(connection, "scope_complete_count", {"expected_scopes_plus_one": expected + 1})
    if len(rows) != 1 or rows[0]["scope_candidates"] != expected:
        raise MigrationRefused("ownership_lineage_invalid")
    work.check()
    return Graph(closure, projects)
