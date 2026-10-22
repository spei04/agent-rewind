"""Observed catalog validation for the dormant ledger reader."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .ledger_catalog_sql import EXPECTED, SQL
from .ledger_check import LedgerCheck
from .schema import (
    ADMISSION,
    LEDGER,
    MigrationRefused,
    _canonicalize_postgresql_enum_checks,
    _sqlite_supported_clauses,
    dialect,
    schema_table_names,
    verify_installed_profile,
)

# The generic PG column query has 21 binds for optional identity/collation
# reflection. The ledger's preceding exact gates exclude those shapes, so this
# observation preserves the shared 16-bind limit without changing old readers.
_POSTGRES_COLUMNS = """SELECT a.attname::text AS name,
       pg_catalog.format_type(a.atttypid,a.atttypmod) AS format_type,
       a.attnotnull AS not_null,
       CASE WHEN a.atthasdef THEN
         (SELECT pg_catalog.pg_get_expr(d.adbin,d.adrelid)
          FROM pg_catalog.pg_attrdef d
          WHERE d.adrelid=a.attrelid AND d.adnum=a.attnum)
       ELSE NULL END AS default_expression,
       a.attgenerated::text AS generated,
       a.attidentity::text AS identity_kind,
       a.attisdropped AS dropped
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
WHERE n.nspname='public' AND c.relkind='r'
  AND c.relname=:table_name AND a.attnum>0
ORDER BY a.attnum
LIMIT 33
"""
_POSTGRES_COLUMN_TYPES = {
    "bigint": "BIGINT",
    "boolean": "BOOLEAN",
    "double precision": "DOUBLE PRECISION",
    "integer": "INTEGER",
    "json": "JSON",
    "text": "TEXT",
    "timestamp with time zone": "TIMESTAMP WITH TIME ZONE",
}


def _postgres_column(row: Mapping[Any, Any]) -> list[Any]:
    fields = {
        "name",
        "format_type",
        "not_null",
        "default_expression",
        "generated",
        "identity_kind",
        "dropped",
    }
    if (
        set(row) != fields
        or any(
            type(row[key]) is not str
            for key in ("name", "format_type", "generated", "identity_kind")
        )
        or type(row["not_null"]) is not bool
        or type(row["dropped"]) is not bool
        or row["dropped"]
        or row["generated"] != ""
        or row["identity_kind"] != ""
        or (row["default_expression"] is not None and type(row["default_expression"]) is not str)
    ):
        raise MigrationRefused("schema_incompatible")
    observed_type = row["format_type"]
    normalized_type = _POSTGRES_COLUMN_TYPES.get(observed_type)
    if normalized_type is None:
        bounded_text = re.fullmatch(
            r"(character varying|character)\(([1-9][0-9]*)\)", observed_type
        )
        if bounded_text is None:
            raise MigrationRefused("schema_incompatible")
        prefix = "VARCHAR" if bounded_text[1] == "character varying" else "CHAR"
        normalized_type = prefix + "(" + bounded_text[2] + ")"
    return [
        row["name"],
        normalized_type,
        not row["not_null"],
        row["default_expression"],
        None,
        None,
    ]


def _postgres_columns(connection: Connection, table: str, work: LedgerCheck) -> list[list[Any]]:
    rows = connection.execute(text(_POSTGRES_COLUMNS), {"table_name": table}).mappings().all()
    if not 1 <= len(rows) <= 32:
        raise MigrationRefused("schema_incompatible")
    result = []
    for row in rows:
        work.check()
        result.append(_postgres_column(row))
    return result


def _gate(connection: Connection, revision: str, name: str) -> None:
    identity = (revision, dialect(connection), name)
    rows = connection.execute(text(SQL[identity])).mappings().all()
    if len(rows) != 1:
        raise MigrationRefused("schema_incompatible")
    for key, expected in EXPECTED[identity].items():
        actual = rows[0].get(key.removesuffix("_max").removesuffix("_in"))
        if key.endswith("_max"):
            valid = type(actual) is int and isinstance(expected, int) and 0 <= actual <= expected
        elif key.endswith("_in"):
            valid = type(actual) is int and isinstance(expected, tuple) and actual in expected
        else:
            valid = type(actual) is int and actual == expected
        if not valid:
            raise MigrationRefused("schema_incompatible")


def _selected_indexes(
    connection: Connection, revision: str, work: LedgerCheck
) -> dict[str, list[dict[str, Any]]]:
    identity = (revision, "postgresql", "selected_index_body")
    rows = connection.execute(text(SQL[identity])).mappings().all()
    if len(rows) != EXPECTED[identity]["index_count"]:
        raise MigrationRefused("schema_incompatible")
    fields = {
        "table_name",
        "index_name",
        "indisunique",
        "indisprimary",
        "indisvalid",
        "indisready",
        "definition",
        "predicate",
        "column_names",
        "sort_options",
        "constraint_kind",
        "invalid",
    }
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        work.check()
        if set(row) != fields or row["invalid"] != 0:
            raise MigrationRefused("schema_incompatible")
        if row["indisprimary"] or row["constraint_kind"] is not None:
            continue
        index: dict[str, Any] = {
            "name": row["index_name"],
            "column_names": row["column_names"],
            "unique": row["indisunique"],
            "dialect_options": {"postgresql_include": []},
        }
        if row["predicate"] is not None:
            index["dialect_options"]["postgresql_where"] = row["predicate"]
        sorting = {}
        for column, flag in zip(row["column_names"], row["sort_options"], strict=True):
            modifiers = []
            if flag & 1:
                modifiers.append("desc")
                if not flag & 2:
                    modifiers.append("nulls_last")
            elif flag & 2:
                modifiers.append("nulls_first")
            if modifiers:
                sorting[column] = tuple(modifiers)
        if sorting:
            index["column_sorting"] = sorting
        result.setdefault(row["table_name"], []).append(index)
    return result


def inspect_catalog(connection: Connection, revision: str, work: LedgerCheck) -> dict[str, Any]:
    """Bound reflected payloads first, then compare actual complete observations."""
    key = {ADMISSION: "ar6", LEDGER: "ar7"}.get(revision)
    if key is None:
        raise MigrationRefused("schema_incompatible")
    name = dialect(connection)
    gates = (
        (
            "sqlite_database_gate",
            "sqlite_master_count",
            "sqlite_master_gate",
            "sqlite_column_gate",
            "sqlite_index_gate",
            "sqlite_index_parts_gate",
            "sqlite_foreign_key_gate",
        )
        if name == "sqlite"
        else (
            "catalog_relation_gate",
            "catalog_column_count",
            "catalog_column_gate",
            "selected_index_count",
            "selected_index_gate",
            "catalog_constraint_count",
            "catalog_constraint_gate",
        )
    )
    for gate in gates:
        work.check()
        _gate(connection, key, gate)
    indexes: dict[str, list[dict[str, Any]]] = {}
    if name == "sqlite":
        if connection.exec_driver_sql("SELECT 1 FROM sqlite_temp_master LIMIT 1").first():
            raise MigrationRefused("schema_incompatible")
    else:
        indexes = _selected_indexes(connection, key, work)
    shape = _observe_catalog(connection, indexes, key, work)
    verify_installed_profile(shape, name, revision)
    work.check()
    return shape


def _observe_catalog(
    connection: Connection,
    indexes_by_table: dict[str, list[dict[str, Any]]],
    revision_key: str,
    work: LedgerCheck,
) -> dict[str, Any]:
    """Read bounded structure and the exact revision-owned executable inventory."""
    name = dialect(connection)
    inspector = inspect(connection)
    schema = "public" if name == "postgresql" else None
    tables, revision = schema_table_names(connection)
    ledger = revision == LEDGER
    executable_profile = None
    if name == "sqlite":
        _sqlite_supported_clauses(
            connection, tables, admission=revision == ADMISSION, ledger=ledger
        )
        extras = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1"
        ).first()
        if extras or connection.exec_driver_sql("SELECT 1 FROM sqlite_temp_master LIMIT 1").first():
            raise MigrationRefused("schema_incompatible")
    else:
        if connection.execute(
            text("SELECT 1 FROM pg_class WHERE relnamespace=pg_my_temp_schema() LIMIT 1")
        ).first():
            raise MigrationRefused("schema_incompatible")
        if connection.execute(
            text(
                "SELECT 1 FROM pg_namespace WHERE "
                "nspname NOT IN ('public','information_schema') "
                "AND nspname NOT LIKE 'pg_%' LIMIT 1"
            )
        ).first():
            raise MigrationRefused("unsupported_database_schema")
        extras = connection.execute(
            text("""
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND
              (c.relkind NOT IN ('r','i') OR c.relrowsecurity OR c.relforcerowsecurity
               OR c.relpersistence <> 'p' OR c.relispartition) LIMIT 1
        """)
        ).first()
        if ledger:
            from .ledger_catalog import ledger_executables

            executable_profile = ledger_executables(connection)
        executable = (
            None
            if ledger
            else connection.execute(
                text("""
            SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal
            UNION ALL
            SELECT 1 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
            UNION ALL
            SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public'
            LIMIT 1
        """)
            ).first()
        )
        if extras or executable:
            raise MigrationRefused("schema_incompatible")
    result: dict[str, Any] = {}
    for table in sorted(tables):
        work.check()
        if name == "postgresql":
            column_shape = _postgres_columns(connection, table, work)
        else:
            columns = inspector.get_columns(table, schema=schema)
            if len(columns) > 32:
                raise MigrationRefused("schema_incompatible")
            column_shape = [
                [
                    c["name"],
                    str(c["type"].compile(dialect=connection.dialect)).upper(),
                    c["nullable"],
                    c.get("default"),
                    c.get("computed"),
                    c.get("identity"),
                ]
                for c in columns
            ]
        indexes = (
            indexes_by_table.get(table, [])
            if name == "postgresql"
            else inspector.get_indexes(table, schema=schema)
        )
        for reflected_index in indexes:
            if "dialect_options" in reflected_index:
                reflected_index["dialect_options"] = {
                    key: str(value) if key.endswith("_where") else value
                    for key, value in reflected_index["dialect_options"].items()
                }
        uniques = sorted(
            [c["column_names"] for c in inspector.get_unique_constraints(table, schema=schema)]
        )
        if name == "sqlite":
            # SQLAlchemy's SQLite SQL parser misses inline UNIQUE declarations in the
            # frozen fixture. SQLite's own index catalog is the structural authority.
            quoted = connection.dialect.identifier_preparer.quote_identifier(table)
            uniques = []
            for index in connection.exec_driver_sql(f"PRAGMA index_list({quoted})"):
                index_name = connection.dialect.identifier_preparer.quote_identifier(index[1])
                parts = list(connection.exec_driver_sql(f"PRAGMA index_xinfo({index_name})"))
                allowed_partial = (
                    table == "project_memberships"
                    and index[1] == "membership_active_legacy_default"
                )
                projection_index = (
                    table == "run_index" and index[1] == "run_index_project_created_run"
                )
                exact_projection_order = (
                    index[2] == 0
                    and index[3] == "c"
                    and index[4] == 0
                    and [[part[2], part[3], part[4]] for part in parts if part[5]]
                    == [
                        ["project_id", 0, "BINARY"],
                        ["created_at", 1, "BINARY"],
                        ["run_id", 1, "BINARY"],
                    ]
                    and all(part[4] == "BINARY" for part in parts)
                )
                # SQLite reflection omits sort direction. Admit exactly this
                # named key order; an all-ASC replacement must also refuse.
                if (
                    (projection_index and not exact_projection_order)
                    or (index[4] and not allowed_partial)
                    or (
                        not projection_index
                        and any(part[3] or part[4] != "BINARY" for part in parts)
                    )
                ):
                    raise MigrationRefused("schema_incompatible")
                if index[3] == "u":
                    uniques.append([part[2] for part in parts if part[5]])
            uniques.sort()
            options = connection.execute(
                text(SQL[(revision_key, "sqlite", "sqlite_selected_table_options")]),
                {"table_name": table},
            ).all()
            if len(options) != 1 or tuple(options[0]) != (0, 0):
                raise MigrationRefused("schema_incompatible")
        result[table] = {
            "columns": column_shape,
            "pk": inspector.get_pk_constraint(table, schema=schema)["constrained_columns"],
            "uniques": uniques,
            "foreign_keys": inspector.get_foreign_keys(table, schema=schema),
            "checks": inspector.get_check_constraints(table, schema=schema),
            # Reflection values retain their SQLAlchemy types; the persisted
            # catalog uses JSON arrays without dropping sort/null-order modifiers.
            "indexes": [
                {
                    **index,
                    **(
                        {
                            "column_sorting": {
                                key: list(value) for key, value in index["column_sorting"].items()
                            }
                        }
                        if "column_sorting" in index
                        else {}
                    ),
                }
                for index in indexes
                if not index.get("duplicates_constraint")
            ],
        }
    if name == "postgresql":
        # Include physical index expressions, predicates, opclasses, sort options and typmods.
        # A stored installed fingerprint also detects drift in the additive metadata tables.
        result["$postgres"] = {
            "indexes": [
                list(r)
                for r in connection.execute(
                    text("""
                SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready
                FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' ORDER BY c.relname, pg_get_indexdef(i.indexrelid)
            """)
                )
            ],
            "columns": [
                list(r)
                for r in connection.execute(
                    text("""
                SELECT c.relname,a.attname,a.atttypmod,a.attgenerated,a.attidentity,
                  a.attnum,a.attisdropped,
                  CASE WHEN a.attcollation=0 THEN NULL ELSE cn.nspname||'.'||co.collname END
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                LEFT JOIN pg_collation co ON co.oid=a.attcollation
                LEFT JOIN pg_namespace cn ON cn.oid=co.collnamespace
                WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0
                ORDER BY c.relname,a.attnum
            """)
                )
            ],
            "constraints": [
                list(r)
                for r in connection.execute(
                    text("""
                SELECT c.relname,k.contype,k.condeferrable,k.condeferred,k.convalidated,
                  pg_get_constraintdef(k.oid)
                FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' ORDER BY c.relname,pg_get_constraintdef(k.oid)
            """)
                )
            ],
        }
        _canonicalize_postgresql_enum_checks(result)
        if executable_profile is not None:
            result["$postgres"]["ledger_executables"] = executable_profile
    return result
