"""Counted original-source hashing inside the caller's excluded ledger transaction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .inputs import MAX_ROW_BYTES, MAX_SOURCE_BYTES, _unique_object
from .ledger_graph_sql import SQL as SOURCE_PREFLIGHT_SQL
from .ledger_source_sql import SQL
from .ledger_work import LedgerWork
from .schema import COLUMNS, PRIMARY_KEYS, TABLES, MigrationRefused, canonical, dialect

_MAX_ROWS = 1_000_000
_PAGE_ROWS = 4096
_GATE_FIELDS = {
    "candidate_count",
    "invalid_rows",
    "max_row_bytes",
    "selected_count",
    "selected_bytes",
}
_STATS_FIELDS = {
    "observed_rows",
    "graph_invalid_rows",
    "original_native_bytes",
    "max_original_native_bytes",
}
_METADATA = {"source_ordinal", "native_row_bytes", "invalid_row"}


def _query(connection: Connection, name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    kind = dialect(connection)
    statement = (
        SOURCE_PREFLIGHT_SQL[("all", kind, name)]
        if name.startswith(("source_count_", "source_stats_"))
        else SQL[(kind, name)]
    )
    # No streaming option: every page is an ordinary observed execute.
    with connection.execute(text(statement), parameters) as result:
        return [dict(row) for row in result.mappings()]


def _integers(rows: list[dict[str, Any]], fields: set[str]) -> dict[str, int]:
    if (
        len(rows) != 1
        or set(rows[0]) != fields
        or any(type(value) is not int or value < 0 for value in rows[0].values())
    ):
        raise MigrationRefused("invalid_source_data")
    return rows[0]


def _preflight(connection: Connection, work: LedgerWork) -> dict[str, tuple[int, int]]:
    receipts = {}
    total_rows = total_native = 0
    for table in TABLES:
        work.check()
        count = _integers(
            _query(
                connection,
                "source_count_" + table,
                {"remaining_rows_plus_one": _MAX_ROWS - total_rows + 1},
            ),
            {"candidate_rows"},
        )["candidate_rows"]
        if count > _MAX_ROWS - total_rows:
            raise MigrationRefused("source_limit_exceeded")
        stats = _integers(_query(connection, "source_stats_" + table, {}), _STATS_FIELDS)
        if stats["observed_rows"] != count:
            raise MigrationRefused("invalid_source_data")
        if stats["graph_invalid_rows"]:
            raise MigrationRefused("ownership_lineage_invalid")
        native, maximum = stats["original_native_bytes"], stats["max_original_native_bytes"]
        if maximum > MAX_ROW_BYTES or total_native + native > MAX_SOURCE_BYTES:
            raise MigrationRefused("source_limit_exceeded")
        if native > count * maximum or maximum > native:
            raise MigrationRefused("invalid_source_data")
        receipts[table] = (count, native)
        total_rows += count
        total_native += native
    return receipts


def _gate(rows: list[dict[str, Any]]) -> dict[str, int]:
    gate = _integers(rows, _GATE_FIELDS)
    candidates, selected = gate["candidate_count"], gate["selected_count"]
    if gate["max_row_bytes"] > MAX_ROW_BYTES or gate["selected_bytes"] > MAX_ROW_BYTES:
        raise MigrationRefused("source_limit_exceeded")
    if (
        candidates > _PAGE_ROWS
        or selected > candidates
        or gate["invalid_rows"]
        or (candidates == 0 and any(gate.values()))
        or (candidates > 0 and selected == 0)
        or gate["selected_bytes"] > selected * gate["max_row_bytes"]
    ):
        raise MigrationRefused("invalid_source_data")
    return gate


def _digest_page(
    rows: list[dict[str, Any]],
    table: str,
    gate: dict[str, int],
    remaining_canonical: int,
    digest: Any,
    work: LedgerWork,
) -> tuple[tuple[Any, ...], int]:
    if len(rows) != gate["selected_count"]:
        raise MigrationRefused("invalid_source_data")
    fields = [column[0] for column in COLUMNS[table]]
    expected = set(fields) | _METADATA
    native = canonical_bytes = 0
    for ordinal, row in enumerate(rows, 1):
        work.check()
        if (
            set(row) != expected
            or type(row["source_ordinal"]) is not int
            or row["source_ordinal"] != ordinal
            or type(row["invalid_row"]) is not int
            or row["invalid_row"] != 0
            or type(row["native_row_bytes"]) is not int
            or not 0 <= row["native_row_bytes"] <= MAX_ROW_BYTES
            or any(row[key] is None for key in PRIMARY_KEYS[table])
        ):
            raise MigrationRefused("invalid_source_data")
        native += row["native_row_bytes"]
        values = [row[field] for field in fields]
        try:
            if table == "records" and isinstance(values[3], str):
                values[3] = json.loads(values[3], object_pairs_hook=_unique_object)
            values = [int(value) if isinstance(value, bool) else value for value in values]
            encoded = canonical(values)
        except (ValueError, TypeError, RecursionError):
            raise MigrationRefused("invalid_source_data") from None
        canonical_bytes += len(encoded)
        if len(encoded) > MAX_ROW_BYTES or canonical_bytes > remaining_canonical:
            raise MigrationRefused("source_limit_exceeded")
        digest.update(encoded)
        digest.update(b"\n")
        work.check()
    if native != gate["selected_bytes"]:
        raise MigrationRefused("invalid_source_data")
    # SQL ordinals/native collation establish order. Rebind the actual last key;
    # do not sort, compare, coerce or impose a new width limit on audit keys.
    return tuple(rows[-1][key] for key in PRIMARY_KEYS[table]), canonical_bytes


def _digest_table(
    connection: Connection,
    table: str,
    expected: tuple[int, int],
    remaining_canonical: int,
    digest: Any,
    work: LedgerWork,
) -> int:
    digest.update(canonical([table, [column[0] for column in COLUMNS[table]]]))
    digest.update(b"\n")
    after: tuple[Any, ...] | None = None
    observed_rows = observed_native = canonical_bytes = 0
    while True:
        work.check()
        stage = "first" if after is None else "next"
        parameters = (
            {}
            if after is None
            else {"last_run": after[0], "last_step": after[1]}
            if table == "events"
            else {"last_key": after[0]}
        )
        gate = _gate(_query(connection, "source_gate_" + table + "_" + stage, parameters))
        if gate["candidate_count"] == 0:
            break
        rows = _query(
            connection,
            "source_body_" + table + "_" + stage,
            {**parameters, "selected_count": gate["selected_count"]},
        )
        after, size = _digest_page(
            rows, table, gate, remaining_canonical - canonical_bytes, digest, work
        )
        observed_rows += len(rows)
        observed_native += gate["selected_bytes"]
        canonical_bytes += size
        # Retain only the last native key, not a previous body while fetching the next.
        del rows
        if observed_rows > expected[0] or observed_native > expected[1]:
            raise MigrationRefused("invalid_source_data")
        if (
            gate["candidate_count"] < _PAGE_ROWS
            and gate["selected_count"] == gate["candidate_count"]
        ):
            break
    if (observed_rows, observed_native) != expected:
        raise MigrationRefused("invalid_source_data")
    return canonical_bytes


def source_digest(connection: Connection, work: LedgerWork) -> str:
    """Hash the original five tables using the caller's existing work and exclusion.

    The service must first prove the exact catalog, complete graph and current
    financial native gates, including all ten domains before a jobs body. Repeat
    those prerequisites after any write that invalidates them. This helper owns
    no transaction, guard, lease or budget and cannot establish those prerequisites.
    """
    if work._connection is not connection or not work._attached or work._detached:
        raise MigrationRefused("transactional_connection_required")
    work.check()
    receipts = _preflight(connection, work)
    digest = hashlib.sha256()
    canonical_bytes = 0
    for table in TABLES:
        canonical_bytes += _digest_table(
            connection, table, receipts[table], MAX_SOURCE_BYTES - canonical_bytes, digest, work
        )
    work.check()
    return digest.hexdigest()
