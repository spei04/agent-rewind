"""Independent native capture only; no revision, readiness, or producer authority."""

import hashlib
import json
from pathlib import Path

import pytest
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import complete_ar6
from ledger_service_fixture import service_postgres_state
from sqlalchemy import inspect, text
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope
from test_ledger_service import intent, invoke

from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.schema import (
    LEDGER,
    _canonicalize_postgresql_enum_checks,
    _sqlite_check_declarations,
    _sqlite_require_reflected_checks,
    catalog,
    installed_profile,
)

pg = migration_tests.pg
TABLE = "job_failure_evidence"
SUPPORT = "job_failure_operation_binding_uq"
OWNER = "installation_table_owner"
EXPECTED_COLUMNS = [
    ["schema_version", "INTEGER", False],
    ["kind", "VARCHAR(17)", False],
    ["project_id", "VARCHAR(32)", False],
    ["job_resource_kind", "VARCHAR(3)", False],
    ["job_id", "VARCHAR(32)", False],
    ["operation_id", "VARCHAR(32)", True],
    ["lease_generation", "BIGINT", False],
    ["job_status", "VARCHAR(9)", False],
    ["cause", "VARCHAR(18)", True],
    ["phase", "VARCHAR(15)", True],
    ["origin_kind", "VARCHAR(16)", False],
    ["correlation_id", "VARCHAR(32)", False],
    ["association_sha256", "VARCHAR(64)", False],
    ["source_sha256", "VARCHAR(64)", False],
    ["created_at_micros", "BIGINT", False],
]
QUERIES = {
    "pg_indexes": """
                SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready
                FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' ORDER BY c.relname, pg_get_indexdef(i.indexrelid)
            """,
    "pg_columns": """
                SELECT c.relname,a.attname,a.atttypmod,a.attgenerated,a.attidentity,
                  a.attnum,a.attisdropped,
                  CASE WHEN a.attcollation=0 THEN NULL ELSE cn.nspname||'.'||co.collname END
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                LEFT JOIN pg_collation co ON co.oid=a.attcollation
                LEFT JOIN pg_namespace cn ON cn.oid=co.collnamespace
                WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0
                ORDER BY c.relname,a.attnum
            """,
    "pg_constraints": """
                SELECT c.relname,k.contype,k.condeferrable,k.condeferred,k.convalidated,
                  pg_get_constraintdef(k.oid)
                FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' ORDER BY c.relname,pg_get_constraintdef(k.oid)
            """,
    "functions": """
        SELECT p.proname AS name, l.lanname AS language, p.prokind AS kind,
          p.provolatile AS volatility, p.proparallel AS parallel, p.prosecdef AS security_definer,
          p.proisstrict AS strict, p.proleakproof AS leakproof, p.proretset AS returns_set,
          p.procost AS cost, p.prorows AS rows, p.proconfig AS settings,
          p.prosupport::regproc::text AS support, p.probin AS binary,
          pg_get_function_identity_arguments(p.oid) AS arguments,
          pg_get_function_result(p.oid) AS result, pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public'
    """,
    "triggers": """
            SELECT t.tgname AS name, c.relname AS relation, t.tgtype AS type,
              t.tgenabled AS enabled, t.tgdeferrable AS deferrable,
              t.tginitdeferred AS initially_deferred, t.tgnargs AS argument_count,
              encode(t.tgargs,'hex') AS arguments, t.tgattr::text AS columns,
              t.tgqual::text AS condition, t.tgoldtable AS old_table, t.tgnewtable AS new_table,
              p.proname AS function_name, pn.nspname AS function_schema,
              (t.tgconstraint<>0) AS constraint_trigger, pg_get_triggerdef(t.oid) AS definition
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY t.tgname
        """,
}


def native_rows(connection, sql, limit=4096):
    result = connection.exec_driver_sql(sql)
    rows = result.fetchmany(limit + 1)
    assert len(rows) <= limit
    return [list(row) for row in rows]


def native_mappings(connection, sql, limit):
    result = connection.execute(text(sql)).mappings()
    rows = result.fetchmany(limit + 1)
    assert len(rows) <= limit
    return [dict(row) for row in rows]


def native_snapshot(connection, expected_tables):
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        gate = native_rows(
            connection,
            """
            SELECT count(*),max(length(CAST(sql AS BLOB))),
                   coalesce(sum(length(CAST(sql AS BLOB))),0)
            FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """,
            1,
        )[0]
        assert gate[0] == expected_tables and gate[1] <= 65536 and gate[2] <= 1310720
        names = native_rows(
            connection,
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 22
        """,
            22,
        )
        assert len(names) == expected_tables
        object_gate = native_rows(
            connection,
            """
            SELECT count(*),max(length(CAST(coalesce(sql,'') AS BLOB))),
                   coalesce(sum(length(CAST(coalesce(sql,'') AS BLOB))),0)
            FROM sqlite_master
        """,
            1,
        )[0]
        assert object_gate[0] <= 128 and object_gate[1] <= 65536
        # This is a separate raw capture ceiling, not a larger table-DDL allowance.
        assert object_gate[2] <= 1310720 + 65536
        objects = native_rows(
            connection, "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name", 128
        )
        raw = {"table_gate": gate, "object_gate": object_gate, "objects": objects}
        raw["table_list"] = native_rows(connection, "PRAGMA table_list", 32)
        raw["foreign_keys_enabled"] = native_rows(connection, "PRAGMA foreign_keys", 1)
        assert raw["foreign_keys_enabled"] == [[1]]
        tables = {}
        for (name,) in names:
            quoted = connection.dialect.identifier_preparer.quote_identifier(name)
            indexes = native_rows(connection, f"PRAGMA index_list({quoted})", 16)
            parts = {}
            for row in indexes:
                key = connection.dialect.identifier_preparer.quote_identifier(row[1])
                parts[row[1]] = native_rows(connection, f"PRAGMA index_xinfo({key})", 33)
            tables[name] = {
                "columns": native_rows(connection, f"PRAGMA table_xinfo({quoted})", 32),
                "foreign_keys": native_rows(connection, f"PRAGMA foreign_key_list({quoted})", 64),
                "indexes": indexes,
                "index_parts": parts,
            }
        raw["tables"] = tables
        raw["counts"] = {
            "tables": len(tables),
            "columns": sum(len(t["columns"]) for t in tables.values()),
            "indexes": sum(len(t["indexes"]) for t in tables.values()),
            "index_parts": sum(
                len(rows) for t in tables.values() for rows in t["index_parts"].values()
            ),
            "foreign_key_parts": sum(len(t["foreign_keys"]) for t in tables.values()),
            "master_objects": len(objects),
            "triggers": sum(r[0] == "trigger" for r in objects),
        }
        return raw
    names = native_rows(
        connection,
        """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname LIMIT 22
    """,
        22,
    )
    assert len(names) == expected_tables
    counts = native_rows(
        connection,
        """
        SELECT
          (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public'),
          (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public'),
          (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal),
          (SELECT count(*) FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
           JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public')
    """,
        1,
    )[0]
    assert counts[0] <= 128 and counts[1] <= 2 and counts[2] <= 7 and counts[3] == 0
    executable_sizes = native_rows(
        connection,
        """
        SELECT
          (SELECT max(octet_length(pg_get_functiondef(p.oid)))
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'),
          (SELECT max(octet_length(pg_get_triggerdef(t.oid)))
           FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal),
          (SELECT coalesce(sum(octet_length(pg_get_functiondef(p.oid))
                       +octet_length(row_to_json(p)::text)),0)
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')
          +(SELECT coalesce(sum(octet_length(pg_get_triggerdef(t.oid))
                       +octet_length(row_to_json(t)::text)),0)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal)
    """,
        1,
    )[0]
    assert executable_sizes[0] <= 16384 and executable_sizes[1] <= 4096
    assert executable_sizes[2] <= 65536
    raw = {"table_names": names, "object_counts": counts, "executable_sizes": executable_sizes}
    for name in ["pg_columns", "pg_indexes", "pg_constraints"]:
        raw[name] = native_rows(connection, QUERIES[name], 1024)
    raw["functions"] = native_mappings(connection, QUERIES["functions"], 2)
    raw["triggers"] = native_mappings(connection, QUERIES["triggers"], 7)
    raw["table_owners_acl"] = native_rows(
        connection,
        """
        SELECT c.relname,pg_get_userbyid(c.relowner),c.relacl::text
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname
    """,
        22,
    )
    raw["function_acl"] = native_rows(
        connection,
        """
        SELECT p.proname,pg_get_userbyid(p.proowner),pg_get_userbyid(a.grantor),
               CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
               a.privilege_type,a.is_grantable
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        LEFT JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a ON true
        WHERE n.nspname='public' ORDER BY p.proname,a.grantee,a.privilege_type
    """,
        16,
    )
    raw["default_acl"] = native_rows(
        connection,
        """
        SELECT pg_get_userbyid(d.defaclrole),n.nspname,d.defaclobjtype,d.defaclacl::text
        FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
        ORDER BY d.defaclrole,d.defaclnamespace,d.defaclobjtype
    """,
        32,
    )
    raw["column_native"] = native_rows(
        connection,
        """
        SELECT c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
               a.attgenerated,a.attidentity,a.attisdropped,
               pg_get_expr(d.adbin,d.adrelid)
        FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0
        ORDER BY c.relname,a.attnum
    """,
        704,
    )
    raw["counts"] = {
        "tables": len(names),
        "relations": counts[0],
        "columns": len(raw["pg_columns"]),
        "indexes": len(raw["pg_indexes"]),
        "constraints": len(raw["pg_constraints"]),
        "functions": len(raw["functions"]),
        "triggers": len(raw["triggers"]),
        "rules": counts[3],
    }
    return raw


def full_shape(connection, raw):
    observer = inspect(connection)
    sqlite = connection.dialect.name == "sqlite"
    schema = None if sqlite else "public"
    names = sorted(raw["tables"]) if sqlite else [r[0] for r in raw["table_names"]]
    postgres = {}
    if not sqlite and names:
        # Reflect this observation's exact ordinary tables; never reuse a prior snapshot.
        options = {
            "schema": schema,
            "filter_names": names,
            "kind": ObjectKind.TABLE,
            "scope": ObjectScope.DEFAULT,
        }
        postgres = {
            "columns": observer.get_multi_columns(**options),
            "indexes": observer.get_multi_indexes(**options),
            "uniques": observer.get_multi_unique_constraints(**options),
            "pk": observer.get_multi_pk_constraint(**options),
            "foreign_keys": observer.get_multi_foreign_keys(**options),
            "checks": observer.get_multi_check_constraints(**options),
        }
        expected = {(schema, name) for name in names}
        assert len(expected) == len(names)
        assert all(set(rows) == expected for rows in postgres.values())
    result = {}
    for name in names:
        columns = (
            observer.get_columns(name, schema=schema)
            if sqlite
            else postgres["columns"][schema, name]
        )
        assert len(columns) <= 32
        indexes = (
            observer.get_indexes(name, schema=schema)
            if sqlite
            else postgres["indexes"][schema, name]
        )
        for index in indexes:
            if "dialect_options" in index:
                index["dialect_options"] = {
                    k: str(v) if k.endswith("_where") else v
                    for k, v in index["dialect_options"].items()
                }
            if "column_sorting" in index:
                index["column_sorting"] = {k: list(v) for k, v in index["column_sorting"].items()}
        if sqlite:
            table = raw["tables"][name]
            uniques = sorted(
                [
                    [r[2] for r in table["index_parts"][idx[1]] if r[5]]
                    for idx in table["indexes"]
                    if idx[3] == "u"
                ]
            )
        else:
            uniques = sorted(c["column_names"] for c in postgres["uniques"][schema, name])
        result[name] = {
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
            "pk": (
                observer.get_pk_constraint(name, schema=schema)
                if sqlite
                else postgres["pk"][schema, name]
            )["constrained_columns"],
            "uniques": uniques,
            "foreign_keys": (
                observer.get_foreign_keys(name, schema=schema)
                if sqlite
                else postgres["foreign_keys"][schema, name]
            ),
            "checks": (
                observer.get_check_constraints(name, schema=schema)
                if sqlite
                else postgres["checks"][schema, name]
            ),
            "indexes": [i for i in indexes if not i.get("duplicates_constraint")],
        }
        if sqlite:
            ddl = next(r[3] for r in raw["objects"] if r[0] == "table" and r[1] == name)
            _sqlite_require_reflected_checks(
                _sqlite_check_declarations(ddl), result[name]["checks"]
            )
            assert [(r[1], r[2].upper(), not bool(r[3]), r[4]) for r in table["columns"]] == [
                tuple(c[:4]) for c in result[name]["columns"]
            ]
        else:
            observed = [r for r in raw["column_native"] if r[0] == name]

            def native_type(value):
                return (
                    value.upper()
                    .replace("CHARACTER VARYING(", "VARCHAR(")
                    .replace("CHARACTER(", "CHAR(")
                )

            assert [
                [r[2], native_type(r[3]), not r[4], r[8], None, None] for r in observed
            ] == result[name]["columns"]
            assert all(r[5:8] == ["", "", False] for r in observed)
    if sqlite:
        result["$executables"] = {
            "triggers": [
                {"name": r[1], "table": r[2], "sql": r[3]}
                for r in raw["objects"]
                if r[0] == "trigger"
            ]
        }
    else:
        result["$postgres"] = {k: raw["pg_" + k] for k in ["columns", "indexes", "constraints"]}
        _canonicalize_postgresql_enum_checks(result)
        owners = {row[1] for row in raw["table_owners_acl"]}
        assert len(owners) == 1
        owner = owners.pop()
        functions = []
        for function in sorted(raw["functions"], key=lambda r: r["name"]):
            acl = [r for r in raw["function_acl"] if r[0] == function["name"]]
            assert acl == [[function["name"], owner, owner, owner, "EXECUTE", False]]
            functions.append(
                function
                | {
                    "owner": OWNER,
                    "acl": [[OWNER, OWNER, "EXECUTE", False]],
                    "definition_sha256": hashlib.sha256(
                        function["definition"].encode()
                    ).hexdigest(),
                }
            )
        result["$executables"] = {
            "functions": functions,
            "triggers": raw["triggers"],
            "rules": [],
        }
    return result


def project_ar7(shape):
    retained = json.loads(json.dumps(shape))
    del retained[TABLE]
    indexes = retained["operations"]["indexes"]
    assert len([x for x in indexes if x["name"] == SUPPORT]) == 1
    retained["operations"]["indexes"] = [x for x in indexes if x["name"] != SUPPORT]
    executable = retained.pop("$executables")
    if "$postgres" in retained:
        native = retained["$postgres"]
        native["columns"] = [r for r in native["columns"] if r[0] != TABLE]
        native["constraints"] = [r for r in native["constraints"] if r[0] != TABLE]
        native["indexes"] = [
            r
            for r in native["indexes"]
            if r[0] != TABLE and not r[1].startswith("CREATE UNIQUE INDEX " + SUPPORT + " ")
        ]
        old = [f for f in executable["functions"] if f["name"] == "ar7_ledger_constraint"]
        assert len(old) == 1
        native["ledger_executables"] = {
            "function": old[0],
            "triggers": [t for t in executable["triggers"] if t["relation"] != TABLE],
        }
    return retained


def observe_capture(connection, directory):
    before_profile = catalog(connection)
    assert before_profile == installed_profile(connection.dialect.name, LEDGER)
    old_names = sorted(k for k in before_profile if not k.startswith("$"))
    quote = connection.dialect.identifier_preparer.quote_identifier
    before_rows = {
        n: connection.exec_driver_sql("SELECT * FROM " + quote(n)).all() for n in old_names
    }
    raw_before = native_snapshot(connection, 20)
    create_failure_schema(connection)
    raw_after = native_snapshot(connection, 21)
    full = full_shape(connection, raw_after)
    assert full == json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "agent_rewind/migrations/profiles"
            / (
                "sqlite_failure_evidence.json"
                if connection.dialect.name == "sqlite"
                else "postgresql16_failure_evidence.json"
            )
        ).read_text()
    )
    assert [c[:3] for c in full[TABLE]["columns"]] == EXPECTED_COLUMNS
    assert len(full[TABLE]["checks"]) == 16
    assert full[TABLE]["pk"] == ["job_id"] and len(full[TABLE]["foreign_keys"]) == 3
    assert all(c[3:] == [None, None, None] for c in full[TABLE]["columns"])
    projection = project_ar7(full)
    assert projection == before_profile
    assert before_rows == {
        n: connection.exec_driver_sql("SELECT * FROM " + quote(n)).all() for n in old_names
    }
    assert (
        connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == LEDGER
    )
    assert connection.exec_driver_sql("SELECT count(*) FROM " + TABLE).scalar_one() == 0
    directory.mkdir()
    for name, value in [
        ("raw.before.json", raw_before),
        ("raw.after.json", raw_after),
        ("profile.full.json", full),
        ("profile.retained-ar7.json", projection),
        ("profile.predecessor.json", before_profile),
    ]:
        (directory / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


@pytest.mark.parametrize("history", ["fresh", "legacy"])
def test_sqlite_native_capture(tmp_path, history):
    case = complete_ar6(tmp_path / "source.sqlite", legacy=history == "legacy")
    try:
        invoke(case, intent(case, empty=history == "fresh"))
        with case.engine.begin() as connection:
            observe_capture(connection, tmp_path / "capture")
    finally:
        case.dispose()


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL capture")
@pytest.mark.parametrize("history", ["empty", "legacy"])
def test_postgres_native_capture(pg, tmp_path, history):
    state = service_postgres_state(pg, history=history)
    try:
        with state.case.engine.begin() as connection:
            observe_capture(connection, tmp_path / "capture")
    finally:
        state.case.dispose()
