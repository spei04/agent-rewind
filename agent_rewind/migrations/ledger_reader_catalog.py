"""Observed catalog validation for the dormant ledger reader."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Integer, String, TupleType, bindparam, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector, ObjectKind, ObjectScope

from .ledger_catalog_sql import EXPECTED, SQL
from .ledger_check import LedgerCheck
from .schema import (
    ADMISSION,
    LEDGER,
    MigrationRefused,
    _canonicalize_postgresql_enum_checks,
    _sqlite_check_supported_ddl,
    _sqlite_require_reflected_checks,
    dialect,
    installed_profile,
    schema_table_names,
    verify_installed_profile,
)

# The generic PG column query has 21 binds for optional identity/collation
# reflection. The ledger's preceding exact gates exclude those shapes, so this
# observation preserves the shared 16-bind limit without changing old readers.
_POSTGRES_COLUMNS = """SELECT c.relname::text AS table_name, a.attnum AS ordinal,
       a.attname::text AS name,
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
  AND a.attnum>0
ORDER BY c.relname,a.attnum
LIMIT :row_limit
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


def _postgres_columns(
    connection: Connection, selected: list[str], revision_key: str, work: LedgerCheck
) -> dict[str, list[list[Any]]]:
    revision = {"ar6": ADMISSION, "ar7": LEDGER}[revision_key]
    expected = sorted(
        table for table in installed_profile("postgresql", revision) if not table.startswith("$")
    )
    if selected != expected:
        raise MigrationRefused("schema_incompatible")
    count = EXPECTED[(revision_key, "postgresql", "catalog_column_count")]["candidate_rows"]
    if type(count) is not int:
        raise MigrationRefused("schema_incompatible")
    rows = connection.execute(text(_POSTGRES_COLUMNS), {"row_limit": count + 1}).mappings().all()
    if len(rows) != count:
        raise MigrationRefused("schema_incompatible")
    ordinals = {table: 0 for table in selected}
    names: set[tuple[str, str]] = set()
    columns: list[tuple[str, list[Any]]] = []
    previous = ("", 0)
    for row in rows:
        work.check()
        table_name, ordinal = row.get("table_name"), row.get("ordinal")
        if (
            type(table_name) is not str
            or table_name not in ordinals
            or type(ordinal) is not int
            or ordinal != ordinals[table_name] + 1
            or not 1 <= ordinal <= 32
            or (table_name, ordinal) <= previous
        ):
            raise MigrationRefused("schema_incompatible")
        # Keep the complete original scalar parser; no unsupported native
        # column is filtered out or repaired by batching.
        column = _postgres_column(
            {key: value for key, value in row.items() if key not in {"table_name", "ordinal"}}
        )
        identity = (table_name, column[0])
        if identity in names:
            raise MigrationRefused("schema_incompatible")
        names.add(identity)
        ordinals[table_name] = ordinal
        previous = table_name, ordinal
        columns.append((table_name, column))
    if any(value == 0 for value in ordinals.values()):
        raise MigrationRefused("schema_incompatible")
    # Group only after complete ownership, order, multiplicity and type checks.
    return {table: [column for owner, column in columns if owner == table] for table in selected}


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


def _sqlite_table_options(
    connection: Connection,
    tables: list[str],
    revision: str,
    work: LedgerCheck,
    *,
    admission: bool = False,
    ledger: bool = False,
) -> tuple[list[str], dict[str, tuple[tuple[str | None, str], ...]]]:
    # Use only the revision-owned literals, after proving the fresh table set.
    selected = sorted(installed_profile("sqlite", revision))
    if len(tables) != len(selected) or set(tables) != set(selected):
        raise MigrationRefused("schema_incompatible")
    # Names are typed compiler literals; only the N+1 limit is a native bind.
    # The LEFT JOIN and CASE expose missing or oversized DDL as refusal values.
    statement = text(
        "SELECT p.name,p.wr,p.strict,"
        "CASE WHEN typeof(m.sql)='text' AND length(CAST(m.sql AS BLOB))<=65536 "
        "THEN m.sql END AS ddl "
        "FROM pragma_table_list AS p LEFT JOIN main.sqlite_master AS m "
        "ON m.type='table' AND m.name=p.name "
        "WHERE p.schema='main' AND p.name IN :table_names "
        "ORDER BY p.name LIMIT :row_limit"
    ).bindparams(
        bindparam("table_names", type_=String(), expanding=True, literal_execute=True),
        bindparam("row_limit", type_=Integer()),
    )
    result = connection.execute(
        statement, {"table_names": selected, "row_limit": len(selected) + 1}
    )
    declarations = {}
    primary: BaseException | None = None
    try:
        for table in selected:
            row = result.fetchone()
            work.check()
            if (
                row is None
                or len(row) != 4
                or type(row[0]) is not str
                or row[0] != table
                or type(row[1]) is not int
                or type(row[2]) is not int
                or row[1:3] != (0, 0)
                or type(row[3]) is not str
                or len(row[3].encode("utf-8")) > 65536
            ):
                raise MigrationRefused("schema_incompatible")
            declarations[table] = _sqlite_check_supported_ddl(
                table, row[3], admission=admission, ledger=ledger
            )
            # Retain only the native declaration slices, not complete DDL rows.
            del row
        if result.fetchone() is not None:
            raise MigrationRefused("schema_incompatible")
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            result.close()
        except BaseException:
            if primary is None:
                raise
    return selected, declarations


def _sqlite_native_indexes(
    connection: Connection, selected: list[str], revision_key: str, work: LedgerCheck
) -> tuple[dict[str, list[tuple[Any, ...]]], dict[tuple[str, str], list[tuple[Any, ...]]]]:
    """Observe the same native index rows once, within the preceding exact gates."""
    index_count = EXPECTED[(revision_key, "sqlite", "sqlite_index_gate")]["candidate_rows"]
    part_count = EXPECTED[(revision_key, "sqlite", "sqlite_index_parts_gate")]["candidate_rows"]
    if type(index_count) is not int or type(part_count) is not int:
        raise MigrationRefused("schema_incompatible")
    # A one-column expanding tuple retains the VALUES CTE. SQLAlchemy's
    # String literal compiler handles names; only integer limits are wire binds.
    names = bindparam(
        "table_names", type_=TupleType(String()), expanding=True, literal_execute=True
    )
    index_limit = bindparam("index_limit", type_=Integer())
    parameters = {"table_names": [(name,) for name in selected], "index_limit": index_count + 1}
    tables = "WITH tables(table_name) AS :table_names"
    indexes_sql = (
        'SELECT t.table_name,p.seq,p.name,p."unique",p.origin,p.partial '
        "FROM tables t JOIN pragma_index_list(t.table_name,'main') p "
        "ORDER BY t.table_name,p.seq LIMIT :index_limit"
    )
    indexes = connection.execute(
        text(tables + " " + indexes_sql).bindparams(names, index_limit), parameters
    ).all()
    parts = connection.execute(
        text(
            tables + ", indexes AS MATERIALIZED (" + indexes_sql + ") "
            'SELECT i.table_name,i.name,p.seqno,p.cid,p.name,p."desc",p.coll,p."key" '
            "FROM indexes i JOIN pragma_index_xinfo(i.name,'main') p "
            "ORDER BY i.table_name,i.name,p.seqno LIMIT :part_limit"
        ).bindparams(names, index_limit, bindparam("part_limit", type_=Integer())),
        {**parameters, "part_limit": part_count + 1},
    ).all()
    if (
        len(indexes) != index_count
        or len(parts) != part_count
        or any(
            len(row) != 6
            or type(row[0]) is not str
            or row[0] not in selected
            or type(row[1]) is not int
            or type(row[2]) is not str
            or type(row[3]) is not int
            or row[3] not in (0, 1)
            or type(row[4]) is not str
            or row[4] not in ("c", "u", "pk")
            or type(row[5]) is not int
            or row[5] not in (0, 1)
            for row in indexes
        )
        or any(
            len(row) != 8
            or type(row[0]) is not str
            or type(row[1]) is not str
            or type(row[2]) is not int
            or type(row[3]) is not int
            or (row[4] is not None and type(row[4]) is not str)
            or type(row[5]) is not int
            or row[5] not in (0, 1)
            or type(row[6]) is not str
            or row[6] != "BINARY"
            or type(row[7]) is not int
            or row[7] not in (0, 1)
            or (row[4] is None and (row[3], row[5], row[7]) != (-1, 0, 0))
            for row in parts
        )
    ):
        raise MigrationRefused("schema_incompatible")
    keys = {(row[0], row[2]) for row in indexes}
    if (
        len(keys) != index_count
        or len({row[2] for row in indexes}) != index_count
        or {(row[0], row[1]) for row in parts} != keys
    ):
        raise MigrationRefused("schema_incompatible")
    # Prove multiplicity and complete native ordinals before grouping any rows.
    for table in selected:
        work.check()
        ordinals = [row[1] for row in indexes if row[0] == table]
        if ordinals != list(range(len(ordinals))):
            raise MigrationRefused("schema_incompatible")
    for table, index in sorted(keys):
        work.check()
        ordinals = [row[2] for row in parts if row[0] == table and row[1] == index]
        if not ordinals or ordinals != list(range(len(ordinals))):
            raise MigrationRefused("schema_incompatible")
    return (
        {table: [tuple(row[1:]) for row in indexes if row[0] == table] for table in selected},
        {
            (table, index): [tuple(row[2:]) for row in parts if row[0] == table and row[1] == index]
            for table, index in sorted(keys)
        },
    )


def _postgres_constraints(
    inspector: Inspector, selected: list[str], work: LedgerCheck
) -> dict[str, dict[str, Any]]:
    """Reuse the same fresh parsers without repeating each table's queries."""
    result: dict[str, dict[str, Any]] = {"pk": {}, "uniques": {}, "foreign_keys": {}, "checks": {}}

    def retain(kind: str, rows: Mapping[Any, Any], names: list[str]) -> None:
        work.check()
        if set(rows) != {("public", table) for table in names} or any(
            type(value) is not (dict if kind == "pk" else list) for value in rows.values()
        ):
            raise MigrationRefused("schema_incompatible")
        for (_, table), value in rows.items():
            result[kind][table] = value

    # The pinned PostgreSQL dialect expands both names and OIDs. Ten names
    # retain the operator reader's 16-bind ceiling (15 for OIDs, 13 for keys).
    # This Inspector belongs only to this observation; no prior approval is reused.
    for start in range(0, len(selected), 10):
        batch = selected[start : start + 10]
        retain(
            "pk",
            inspector.get_multi_pk_constraint(
                schema="public",
                filter_names=batch,
                scope=ObjectScope.DEFAULT,
                kind=ObjectKind.TABLE,
            ),
            batch,
        )
        retain(
            "uniques",
            inspector.get_multi_unique_constraints(
                schema="public",
                filter_names=batch,
                scope=ObjectScope.DEFAULT,
                kind=ObjectKind.TABLE,
            ),
            batch,
        )
    # The preceding native gates and exact table set already bound all public
    # tables. Omitting the name filter preserves eight fixed binds for these
    # two parsers; the complete returned public keyset must still match.
    retain(
        "foreign_keys",
        inspector.get_multi_foreign_keys(
            schema="public", scope=ObjectScope.DEFAULT, kind=ObjectKind.TABLE
        ),
        selected,
    )
    retain(
        "checks",
        inspector.get_multi_check_constraints(
            schema="public", scope=ObjectScope.DEFAULT, kind=ObjectKind.TABLE
        ),
        selected,
    )
    return result


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
        extras = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1"
        ).first()
        if extras or connection.exec_driver_sql("SELECT 1 FROM sqlite_temp_master LIMIT 1").first():
            raise MigrationRefused("schema_incompatible")
        selected, sqlite_checks = _sqlite_table_options(
            connection,
            tables,
            {"ar6": ADMISSION, "ar7": LEDGER}[revision_key],
            work,
            admission=revision == ADMISSION,
            ledger=ledger,
        )
        native_by_table, parts_by_index = _sqlite_native_indexes(
            connection, selected, revision_key, work
        )
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
        selected = sorted(
            table
            for table in installed_profile(name, {"ar6": ADMISSION, "ar7": LEDGER}[revision_key])
            if not table.startswith("$")
        )
        if tables != selected:
            raise MigrationRefused("schema_incompatible")
        constraints = _postgres_constraints(inspector, selected, work)
        columns_by_table = _postgres_columns(connection, selected, revision_key, work)
    result: dict[str, Any] = {}
    for table in sorted(tables):
        work.check()
        if name == "postgresql":
            column_shape = columns_by_table[table]
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
        indexes = indexes_by_table.get(table, []) if name == "postgresql" else []
        # SQLite uniqueness is observed below from its native index catalog;
        # generic reflection would only repeat reads whose result is discarded.
        uniques = (
            sorted([c["column_names"] for c in constraints["uniques"][table]])
            if name == "postgresql"
            else []
        )
        if name == "sqlite":
            # SQLAlchemy's SQLite SQL parser misses inline UNIQUE declarations in the
            # frozen fixture. SQLite's own index catalog is the structural authority.
            uniques = []
            native_indexes = native_by_table[table]
            for index in native_indexes:
                parts = parts_by_index[(table, index[1])]
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
            # Generic reflection excludes autoindexes, and otherwise repeats
            # index_list plus has_table reads to return the same empty list.
            if any(not index[1].startswith("sqlite_autoindex") for index in native_indexes):
                indexes = [dict(index) for index in inspector.get_indexes(table, schema=schema)]
        for reflected_index in indexes:
            if "dialect_options" in reflected_index:
                reflected_index["dialect_options"] = {
                    key: str(value) if key.endswith("_where") else value
                    for key, value in reflected_index["dialect_options"].items()
                }
        # SQLite's PK reflection uses these same fresh column ordinals; its
        # additional DDL read supplies only the unused constraint name.
        if name == "postgresql":
            primary_key = constraints["pk"][table]["constrained_columns"]
        else:
            primary_columns: list[tuple[int, str]] = []
            for column in columns:
                ordinal = column.get("primary_key", 0)
                if type(ordinal) is not int:
                    raise MigrationRefused("schema_incompatible")
                if ordinal > 0:
                    primary_columns.append((ordinal, column["name"]))
            primary_key = [
                column for _, column in sorted(primary_columns, key=lambda pair: pair[0])
            ]
        result[table] = {
            "columns": column_shape,
            "pk": primary_key,
            "uniques": uniques,
            "foreign_keys": (
                constraints["foreign_keys"][table]
                if name == "postgresql"
                else inspector.get_foreign_keys(table, schema=schema)
            ),
            "checks": (
                constraints["checks"][table]
                if name == "postgresql"
                else inspector.get_check_constraints(table, schema=schema)
            ),
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
        if name == "sqlite" and table in sqlite_checks:
            _sqlite_require_reflected_checks(sqlite_checks[table], result[table]["checks"])
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
