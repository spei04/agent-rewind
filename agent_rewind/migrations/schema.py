"""Frozen unversioned DDL and bounded, dialect-specific schema inspection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

BASELINE = "ar_0001_baseline"
HEAD = "ar_0002_adoption"  # Explicit install/adopt preparation target, retained for compatibility.
OWNERSHIP = "ar_0003_ownership"
ARTIFACTS = "ar_0004_artifacts"
PROJECTION = "ar_0005_run_index"
ADMISSION = "ar_0006_admission"
ADMISSION_TABLES = {"operations", "operation_keys"}
PROJECTION_TABLES = {"run_index"}
ARTIFACT_TABLES = {"artifact_objects", "artifact_refs"}
OWNERSHIP_TABLES = {"organizations", "projects", "project_memberships", "resource_scopes"}
SOURCE_COMMIT = "8f1ae757005c95c50a789e4fa0a10aae9b3c4024"
TABLES = ("api_keys", "audit", "events", "jobs", "records")
COLUMNS = {
    "records": [
        ("id", "VARCHAR(32)", False),
        ("kind", "VARCHAR(20)", False),
        ("created", "FLOAT", False),
        ("data", "JSON", False),
    ],
    "events": [
        ("run_id", "VARCHAR(32)", False),
        ("step", "INTEGER", False),
        ("artifact", "VARCHAR(64)", False),
        ("hash", "VARCHAR(64)", False),
    ],
    "jobs": [
        ("id", "VARCHAR(32)", False),
        ("kind", "VARCHAR(20)", False),
        ("created", "FLOAT", False),
        ("payload", "VARCHAR(64)", False),
        ("status", "VARCHAR(20)", False),
        ("owner", "VARCHAR(64)", True),
        ("lease_until", "FLOAT", True),
        ("cancel", "BOOLEAN", False),
        ("budget", "BIGINT", False),
        ("reserved", "BIGINT", False),
        ("result", "VARCHAR(64)", True),
        ("error", "VARCHAR(300)", True),
        ("actor", "VARCHAR(256)", True),
    ],
    "api_keys": [
        ("id", "VARCHAR(32)", False),
        ("hash", "VARCHAR(64)", True),
        ("role", "VARCHAR(20)", False),
        ("name", "VARCHAR(120)", False),
        ("expires", "FLOAT", False),
        ("revoked", "BOOLEAN", True),
    ],
    "audit": [
        ("id", "VARCHAR(32)", False),
        ("created", "FLOAT", False),
        ("actor", "VARCHAR(256)", False),
        ("action", "VARCHAR(80)", False),
        ("target", "VARCHAR(64)", False),
    ],
}
PRIMARY_KEYS = {name: ["run_id", "step"] if name == "events" else ["id"] for name in TABLES}
SQL_WORD = re.compile(r"[A-Za-z_]+")
METADATA_TABLES = {"alembic_version", "installation_adoptions", "migration_progress"}


class MigrationRefused(RuntimeError):
    """Only a fixed safe code crosses the CLI boundary; never database exception text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def dialect(connection: Connection) -> str:
    name = connection.dialect.name
    if name not in {"sqlite", "postgresql"}:
        raise MigrationRefused("unsupported_database")
    if name == "postgresql":
        version = connection.dialect.server_version_info
        if not version or version[0] != 16:
            raise MigrationRefused("unsupported_postgresql_version")
    return name


def create_baseline(connection: Connection) -> None:
    # These are fixed schema constants, deliberately independent from application metadata.
    for name in TABLES:
        fields = [
            f'"{column}" {kind}' + ("" if nullable else " NOT NULL")
            for column, kind, nullable in COLUMNS[name]
        ]
        fields.append("PRIMARY KEY (" + ",".join(PRIMARY_KEYS[name]) + ")")
        if name == "api_keys":
            fields.append("UNIQUE (hash)")
        connection.exec_driver_sql(f'CREATE TABLE "{name}" (' + ",".join(fields) + ")")


def _sqlite_ddl_tokens(sql: str) -> list[str]:
    """Read only unquoted SQL words; comments/quoted contents cannot hide a clause."""
    tokens = []
    offset = 0
    while offset < len(sql):
        if sql.startswith("--", offset):
            end = sql.find("\n", offset + 2)
            offset = len(sql) if end < 0 else end + 1
        elif sql.startswith("/*", offset):
            end = sql.find("*/", offset + 2)
            if end < 0:
                raise MigrationRefused("schema_incompatible")
            offset = end + 2
        elif sql[offset] in {"'", '"', "`", "["}:
            opening = sql[offset]
            closing = "]" if opening == "[" else opening
            offset += 1
            while offset < len(sql):
                if sql[offset] != closing:
                    offset += 1
                elif closing != "]" and sql.startswith(closing * 2, offset):
                    offset += 2
                else:
                    offset += 1
                    break
            else:
                raise MigrationRefused("schema_incompatible")
        else:
            word = SQL_WORD.match(sql, offset)
            if word:
                tokens.append(word.group().upper())
                offset += len(word.group())
            else:
                offset += 1
    return tokens


def _sqlite_supported_clauses(
    connection: Connection, tables: list[str], *, admission: bool = False
) -> None:
    # Unindexed COLLATE and conflict policies are invisible to SQLite reflection.
    # This is a conservative supported-DDL exclusion, not a replacement SQL parser.
    forbidden = {
        "COLLATE",
        "CONFLICT",
        "CHECK",
        "REFERENCES",
        "GENERATED",
        "AS",
        "WITHOUT",
        "STRICT",
        "AUTOINCREMENT",
        "DEFAULT",
        "DEFERRABLE",
        "DEFERRED",
    }
    for table in set(tables) & (
        set(TABLES)
        | METADATA_TABLES
        | OWNERSHIP_TABLES
        | ARTIFACT_TABLES
        | PROJECTION_TABLES
        | ADMISSION_TABLES
    ):
        size: int | None = connection.execute(
            text(
                "SELECT length(CAST(sql AS BLOB)) FROM sqlite_master "
                "WHERE type='table' AND name=:name"
            ),
            {"name": table},
        ).scalar_one()
        if size is None or size > 65536:
            raise MigrationRefused("schema_incompatible")
        sql: str = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table}
        ).scalar_one()
        if not isinstance(sql, str):
            raise MigrationRefused("schema_incompatible")
        restricted = forbidden if table in TABLES else forbidden - {"CHECK", "AS"}
        if table in OWNERSHIP_TABLES | ARTIFACT_TABLES | PROJECTION_TABLES | ADMISSION_TABLES:
            restricted -= {"REFERENCES", "DEFAULT"}
        if admission and table == "jobs":
            # Only the verified ar6 successor may extend this historical table.
            # Full literal-profile equality still checks every clause and column.
            restricted -= {"CHECK", "DEFAULT", "AS"}
        if restricted.intersection(_sqlite_ddl_tokens(sql)):
            raise MigrationRefused("schema_incompatible")


# PostgreSQL 16 pg_dump/pg_restore round trips these frozen enum checks
# from a whole-array text cast to per-element text casts. These are the exact
# observed expressions from synthetic runs 39349792047 (adoption) and
# 39353816614 (ownership), not generic SQL rewriting.
# Keep the original catalog/fingerprint authoritative; all other forms refuse.
_POSTGRES_ENUM_ROUNDTRIPS = (
    (
        "installation_adoptions",
        "installation_adoptions_source_kind_check",
        (
            "source_kind::text = ANY (ARRAY['fresh'::character varying, "
            "'legacy'::character varying]::text[])"
        ),
        (
            "source_kind::text = ANY (ARRAY['fresh'::character varying::text, "
            "'legacy'::character varying::text])"
        ),
        (
            "CHECK (((source_kind)::text = ANY ((ARRAY['fresh'::character varying, "
            "'legacy'::character varying])::text[])))"
        ),
        (
            "CHECK (((source_kind)::text = ANY (ARRAY[('fresh'::character varying)::text,"
            " ('legacy'::character varying)::text])))"
        ),
    ),
    (
        "installation_adoptions",
        "installation_adoptions_state_check",
        (
            "state::text = ANY (ARRAY['prepared'::character varying, "
            "'ownership_complete'::character varying]::text[])"
        ),
        (
            "state::text = ANY (ARRAY['prepared'::character varying::text, "
            "'ownership_complete'::character varying::text])"
        ),
        (
            "CHECK (((state)::text = ANY ((ARRAY['prepared'::character varying, "
            "'ownership_complete'::character varying])::text[])))"
        ),
        (
            "CHECK (((state)::text = ANY (ARRAY[('prepared'::character varying)::text, "
            "('ownership_complete'::character varying)::text])))"
        ),
    ),
    (
        "migration_progress",
        "migration_progress_status_check",
        (
            "status::text = ANY (ARRAY['pending'::character varying, 'running'::character"
            " varying, 'complete'::character varying, 'blocked'::character "
            "varying]::text[])"
        ),
        (
            "status::text = ANY (ARRAY['pending'::character varying::text, "
            "'running'::character varying::text, 'complete'::character varying::text, "
            "'blocked'::character varying::text])"
        ),
        (
            "CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, "
            "'running'::character varying, 'complete'::character varying, "
            "'blocked'::character varying])::text[])))"
        ),
        (
            "CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, "
            "('running'::character varying)::text, ('complete'::character varying)::text,"
            " ('blocked'::character varying)::text])))"
        ),
    ),
    (
        "project_memberships",
        "project_memberships_role_check",
        (
            "role::text = ANY (ARRAY['viewer'::character varying, "
            "'operator'::character varying, 'maintainer'::character varying]::text[])"
        ),
        (
            "role::text = ANY (ARRAY['viewer'::character varying::text, "
            "'operator'::character varying::text, 'maintainer'::character varying::text])"
        ),
        (
            "CHECK (((role)::text = ANY ((ARRAY['viewer'::character varying, "
            "'operator'::character varying, 'maintainer'::character varying])::text[])))"
        ),
        (
            "CHECK (((role)::text = ANY (ARRAY[('viewer'::character varying)::text, "
            "('operator'::character varying)::text, ('maintainer'::character varying)::text])))"
        ),
    ),
    (
        "resource_scopes",
        "resource_scopes_resource_kind_check",
        (
            "resource_kind::text = ANY (ARRAY['run'::character varying, "
            "'study'::character varying, 'job'::character varying, "
            "'key'::character varying, 'provider_call'::character varying]::text[])"
        ),
        (
            "resource_kind::text = ANY (ARRAY['run'::character varying::text, "
            "'study'::character varying::text, 'job'::character varying::text, "
            "'key'::character varying::text, 'provider_call'::character varying::text])"
        ),
        (
            "CHECK (((resource_kind)::text = ANY ((ARRAY['run'::character varying, "
            "'study'::character varying, 'job'::character varying, 'key'::character varying, "
            "'provider_call'::character varying])::text[])))"
        ),
        (
            "CHECK (((resource_kind)::text = ANY (ARRAY[('run'::character varying)::text, "
            "('study'::character varying)::text, ('job'::character varying)::text, "
            "('key'::character varying)::text, ('provider_call'::character varying)::text])))"
        ),
    ),
)


def _canonicalize_postgresql_enum_checks(shape: dict[str, Any]) -> None:
    for (
        table,
        name,
        original,
        restored,
        native_original,
        native_restored,
    ) in _POSTGRES_ENUM_ROUNDTRIPS:
        for check in shape.get(table, {}).get("checks", []):
            if check["name"] == name and check["sqltext"] == restored:
                check["sqltext"] = original
        for constraint in shape["$postgres"]["constraints"]:
            if constraint[0] == table and constraint[1] == "c" and constraint[5] == native_restored:
                constraint[5] = native_original


def catalog(connection: Connection) -> dict[str, Any]:
    """Read structure only. Fixed public/main profile; reject non-table executable objects."""
    name = dialect(connection)
    inspector = inspect(connection)
    schema = "public" if name == "postgresql" else None
    tables = inspector.get_table_names(schema=schema)
    if len(tables) > 17:
        raise MigrationRefused("schema_incompatible")
    if name == "sqlite":
        admission = False
        if set(tables) >= ADMISSION_TABLES and "alembic_version" in tables:
            revisions = connection.exec_driver_sql(
                "SELECT CASE WHEN length(CAST(version_num AS BLOB))<=32 "
                "THEN version_num END FROM alembic_version LIMIT 2"
            ).all()
            admission = revisions == [(ADMISSION,)]
        _sqlite_supported_clauses(connection, tables, admission=admission)
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
        executable = connection.execute(
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
        if extras or executable:
            raise MigrationRefused("schema_incompatible")
    result: dict[str, Any] = {}
    for table in sorted(tables):
        columns = inspector.get_columns(table, schema=schema)
        if len(columns) > 32:
            raise MigrationRefused("schema_incompatible")
        indexes = inspector.get_indexes(table, schema=schema)
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
            options = connection.exec_driver_sql("PRAGMA table_list").all()
            if any(r[1] == table and (r[4] or r[5]) for r in options):
                raise MigrationRefused("schema_incompatible")
        result[table] = {
            "columns": [
                [
                    c["name"],
                    str(c["type"].compile(dialect=connection.dialect)).upper(),
                    c["nullable"],
                    c.get("default"),
                    c.get("computed"),
                    c.get("identity"),
                ]
                for c in columns
            ],
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
    return result


def verify_baseline(
    shape: dict[str, Any],
    name: str,
    *,
    versioned: bool = False,
    ownership: bool = False,
    artifacts: bool = False,
    projection: bool = False,
    admission: bool = False,
) -> None:
    actual = set(shape) - {"$postgres"}
    expected = set(TABLES) | (METADATA_TABLES if versioned else set())
    if ownership or artifacts or projection or admission:
        expected |= OWNERSHIP_TABLES
    if artifacts or projection or admission:
        expected |= ARTIFACT_TABLES
    if projection or admission:
        expected |= PROJECTION_TABLES
    if admission:
        expected |= ADMISSION_TABLES
    if actual != expected:
        raise MigrationRefused("schema_incompatible")
    for table in TABLES:
        if admission and table == "jobs":
            if shape[table] != installed_profile(name, ADMISSION)[table]:
                raise MigrationRefused("schema_incompatible")
            continue
        cols = [
            [
                column,
                "DOUBLE PRECISION" if name == "postgresql" and kind == "FLOAT" else kind,
                nullable,
                None,
                None,
                None,
            ]
            for column, kind, nullable in COLUMNS[table]
        ]
        s = shape[table]
        if (
            s["columns"] != cols
            or s["pk"] != PRIMARY_KEYS[table]
            or s["uniques"] != ([["hash"]] if table == "api_keys" else [])
            or s["foreign_keys"]
            or s["checks"]
            or s["indexes"]
        ):
            raise MigrationRefused("schema_incompatible")
    if name == "postgresql":
        expected_indexes = []
        for table in TABLES:
            columns = ", ".join(PRIMARY_KEYS[table])
            expected_indexes.append(
                [
                    table,
                    f"CREATE UNIQUE INDEX {table}_pkey ON public.{table} USING btree ({columns})",
                    True,
                    True,
                ]
            )
        expected_indexes.append(
            [
                "api_keys",
                "CREATE UNIQUE INDEX api_keys_hash_key ON public.api_keys USING btree (hash)",
                True,
                True,
            ]
        )
        baseline_indexes = [r for r in shape["$postgres"]["indexes"] if r[0] in TABLES]
        if sorted(baseline_indexes) != sorted(expected_indexes):
            raise MigrationRefused("schema_incompatible")

        expected_columns = []
        for table in TABLES:
            for position, (column, kind, _) in enumerate(COLUMNS[table], 1):
                length = int(kind[8:-1]) + 4 if kind.startswith("VARCHAR(") else -1
                collation = "pg_catalog.default" if kind.startswith("VARCHAR(") else None
                expected_columns.append([table, column, length, "", "", position, False, collation])
        if admission:
            expected_columns.extend(
                r
                for r in installed_profile(name, ADMISSION)["$postgres"]["columns"]
                if r[0] == "jobs" and r[1] not in {c[0] for c in COLUMNS["jobs"]}
            )
            expected_columns.sort(key=lambda r: (r[0], r[5]))
        actual_columns = [r for r in shape["$postgres"]["columns"] if r[0] in TABLES]
        if actual_columns != expected_columns:
            raise MigrationRefused("schema_incompatible")
        expected_constraints = []
        for table in TABLES:
            expected_constraints.append(
                [
                    table,
                    "p",
                    False,
                    False,
                    True,
                    "PRIMARY KEY (" + ", ".join(PRIMARY_KEYS[table]) + ")",
                ]
            )
        expected_constraints.append(["api_keys", "u", False, False, True, "UNIQUE (hash)"])
        if admission:
            expected_constraints.extend(
                r
                for r in installed_profile(name, ADMISSION)["$postgres"]["constraints"]
                if r[0] == "jobs" and r[1] == "c"
            )
        actual_constraints = [r for r in shape["$postgres"]["constraints"] if r[0] in TABLES]
        if sorted(actual_constraints) != sorted(expected_constraints):
            raise MigrationRefused("schema_incompatible")


def installed_profile(name: str, revision: str = HEAD) -> dict[str, Any]:
    """The checked-in literal profile is authority, never a value stored in the target DB."""
    if revision not in {HEAD, OWNERSHIP, ARTIFACTS, PROJECTION, ADMISSION}:
        raise MigrationRefused("unsupported_target_revision")
    profile_name = "postgresql16" if name == "postgresql" else "sqlite"
    if revision == OWNERSHIP:
        profile_name += "_ownership"
    elif revision == ARTIFACTS:
        profile_name += "_artifacts"
    elif revision == PROJECTION:
        profile_name += "_projection"
    elif revision == ADMISSION:
        profile_name += "_admission"
    profile_path = Path(__file__).parent / "profiles" / (profile_name + ".json")
    if not profile_path.is_file():
        raise MigrationRefused("schema_profile_unavailable")
    result = json.loads(profile_path.read_text())
    if not isinstance(result, dict):
        raise MigrationRefused("schema_profile_invalid")
    return result


def source_profile_checksum(name: str, origin: str) -> str:
    profile = installed_profile(name)
    source = {table: profile[table] for table in TABLES} if origin == "legacy" else {}
    if name == "postgresql":
        source["$postgres"] = {
            key: [row for row in rows if row[0] in TABLES] if origin == "legacy" else []
            for key, rows in profile["$postgres"].items()
        }
    return checksum(source)


def verify_installed_profile(shape: dict[str, Any], name: str, revision: str = HEAD) -> None:
    if shape != installed_profile(name, revision):
        raise MigrationRefused("schema_incompatible")
