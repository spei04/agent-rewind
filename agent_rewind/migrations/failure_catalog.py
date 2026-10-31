"""Complete, bounded observation of the dormant failure-evidence successor.

This observer grants no migration or producer authority. The caller owns the
connection and exclusion scope. A retained ar7 view is returned only after the
complete successor, including executable objects and native authority, matches
the independently captured source-owned profile.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, TupleType, bindparam, inspect, text
from sqlalchemy.engine import Connection

from .ledger_check import LedgerCheck
from .ledger_reader_catalog import _POSTGRES_COLUMNS, _postgres_column, _postgres_constraints
from .schema import (
    LEDGER,
    MigrationRefused,
    _canonicalize_postgresql_enum_checks,
    _sqlite_check_declarations,
    _sqlite_check_supported_ddl,
    _sqlite_ddl_items,
    _sqlite_ddl_tokens,
    _sqlite_require_reflected_checks,
    checksum,
    dialect,
    installed_profile,
)

_TABLE = "job_failure_evidence"
_SUPPORT = "job_failure_operation_binding_uq"
_OWNER = "installation_table_owner"


@dataclass(frozen=True)
class FailureCatalog:
    catalog: dict[str, Any]
    retained_ar7: dict[str, Any]


def _profile(name: str) -> dict[str, Any]:
    filename = {
        "sqlite": "sqlite_failure_evidence.json",
        "postgresql": "postgresql16_failure_evidence.json",
    }[name]
    value = json.loads((Path(__file__).parent / "profiles" / filename).read_text())
    if type(value) is not dict:
        raise MigrationRefused("schema_incompatible")
    return value


def _project_ar7(shape: dict[str, Any], name: str) -> dict[str, Any]:
    """Private projection: its caller must first validate the complete shape."""
    retained = copy.deepcopy(shape)
    del retained[_TABLE]
    executable = retained.pop("$executables")
    retained["operations"]["indexes"] = [
        index for index in retained["operations"]["indexes"] if index["name"] != _SUPPORT
    ]
    if name == "postgresql":
        native = retained["$postgres"]
        for field in ("columns", "constraints"):
            native[field] = [row for row in native[field] if row[0] != _TABLE]
        native["indexes"] = [
            row
            for row in native["indexes"]
            if row[0] != _TABLE
            and not (
                row[0] == "operations"
                and row[1].startswith("CREATE UNIQUE INDEX " + _SUPPORT + " ")
            )
        ]
        native["ledger_executables"] = {
            "function": next(
                f for f in executable["functions"] if f["name"] == "ar7_ledger_constraint"
            ),
            "triggers": [
                t for t in executable["triggers"] if t["function_name"] == "ar7_ledger_constraint"
            ],
        }
    return retained


def _require_equal(actual: object, expected: object) -> None:
    # Canonical checksum preserves type distinctions (including bool vs integer)
    # and uses exactly the same encoding as the retained migration profiles.
    if checksum(actual) != checksum(expected):
        raise MigrationRefused("schema_incompatible")


def _scalar_gate(connection: Connection, sql: str, expected: tuple[Any, ...]) -> None:
    rows = connection.execute(text(sql)).all()
    if len(rows) != 1 or len(rows[0]) != len(expected):
        raise MigrationRefused("schema_incompatible")
    for value, wanted in zip(rows[0], expected, strict=True):
        if type(value) is not type(wanted) or value != wanted:
            raise MigrationRefused("schema_incompatible")


def _tables(connection: Connection, name: str, expected: list[str]) -> list[str]:
    statement = (
        "SELECT CASE WHEN length(CAST(name AS BLOB))<=128 THEN name END "
        "FROM main.sqlite_master WHERE type='table' ORDER BY name LIMIT 22"
        if name == "sqlite"
        else "SELECT c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' "
        "ORDER BY c.relname LIMIT 22"
    )
    rows = connection.exec_driver_sql(statement).all()
    if len(rows) != 21 or any(len(row) != 1 or type(row[0]) is not str for row in rows):
        raise MigrationRefused("schema_incompatible")
    tables = [row[0] for row in rows]
    if tables != expected:
        raise MigrationRefused("schema_incompatible")
    return tables


def _sqlite_gates(connection: Connection, work: LedgerCheck) -> None:
    # Aggregate native sizes before any DDL or reflected payload is transferred.
    gates = [
        (
            """SELECT count(*),sum(name NOT IN ('main','temp'))
             FROM (SELECT name FROM pragma_database_list LIMIT 3)""",
            None,
        ),
        ("""SELECT count(*) FROM (SELECT 1 FROM sqlite_temp_master LIMIT 1)""", (0,)),
        (
            """WITH objects AS MATERIALIZED
             (SELECT type,name,tbl_name,sql FROM main.sqlite_master ORDER BY name LIMIT 70)
             SELECT count(*),sum(type='table'),sum(type='index'),sum(type='trigger'),
               sum(type NOT IN ('table','index','trigger')
                   OR typeof(name)<>'text' OR length(CAST(name AS BLOB))>128
                   OR typeof(tbl_name)<>'text' OR length(CAST(tbl_name AS BLOB))>128),
               coalesce(max(CASE WHEN type='table' THEN
                 typeof(sql)<>'text' OR length(CAST(sql AS BLOB))>65536 END),0),
               coalesce(sum(CASE WHEN type='table' THEN length(CAST(sql AS BLOB)) END),0)<=1310720,
               coalesce(max(CASE WHEN type='trigger' THEN
                 typeof(sql)<>'text' OR length(CAST(sql AS BLOB))>16384 END),0),
               coalesce(sum(CASE WHEN type='trigger' THEN length(CAST(sql AS BLOB)) END),0)<=65536,
               coalesce(max(CASE WHEN type='index' THEN
                 sql IS NOT NULL AND (typeof(sql)<>'text' OR length(CAST(sql AS BLOB))>65536)
                 END),0)
             FROM objects""",
            (69, 21, 45, 3, 0, 0, 1, 0, 1, 0),
        ),
        (
            """WITH candidate AS MATERIALIZED (
               SELECT m.name AS tbl,p.* FROM main.sqlite_master m
               JOIN pragma_table_xinfo(m.name,'main') p
               WHERE m.type='table' ORDER BY m.name,p.cid LIMIT 172)
             SELECT count(*),sum(hidden<>0 OR typeof(name)<>'text'
               OR length(CAST(name AS BLOB))>128 OR typeof(type)<>'text'
               OR length(CAST(type AS BLOB))>65536 OR "notnull" NOT IN (0,1)
               OR typeof(pk)<>'integer' OR pk NOT BETWEEN 0 AND 5
               OR (dflt_value IS NOT NULL AND (typeof(dflt_value)<>'text'
                   OR length(CAST(dflt_value AS BLOB))>65536))),
               sum(length(CAST(name AS BLOB))+length(CAST(type AS BLOB))
                 +coalesce(length(CAST(dflt_value AS BLOB)),0))<=1310720
             FROM candidate""",
            (171, 0, 1),
        ),
        (
            """WITH candidate AS MATERIALIZED (
               SELECT m.name AS tbl,p.* FROM main.sqlite_master m
               JOIN pragma_index_list(m.name,'main') p WHERE m.type='table'
               ORDER BY m.name,p.seq LIMIT 46)
             SELECT count(*),sum(typeof(name)<>'text' OR length(CAST(name AS BLOB))>128
               OR "unique" NOT IN (0,1) OR partial NOT IN (0,1)
               OR origin NOT IN ('c','u','pk')
               OR (origin IN ('u','pk') AND ("unique"<>1 OR partial<>0
                   OR name NOT GLOB 'sqlite_autoindex_*')))
             FROM candidate""",
            (45, 0),
        ),
        (
            """WITH indexes AS MATERIALIZED (
               SELECT m.name AS tbl,p.name FROM main.sqlite_master m
               JOIN pragma_index_list(m.name,'main') p WHERE m.type='table'
               ORDER BY m.name,p.seq LIMIT 46),
             candidate AS MATERIALIZED (
               SELECT i.tbl,p.* FROM indexes i JOIN pragma_index_xinfo(i.name,'main') p
               ORDER BY i.tbl,i.name,p.seqno LIMIT 127)
             SELECT count(*),sum("desc" NOT IN (0,1) OR coll<>'BINARY'
               OR "key" NOT IN (0,1) OR (name IS NOT NULL AND
                   (typeof(name)<>'text' OR length(CAST(name AS BLOB))>128))
               OR ("key"=0 AND (cid<>-1 OR name IS NOT NULL OR "desc"<>0))
               OR ("key"=1 AND (cid<0 OR name IS NULL)))
             FROM candidate""",
            (126, 0),
        ),
        (
            """WITH candidate AS MATERIALIZED (
               SELECT m.name AS tbl,p.* FROM main.sqlite_master m
               JOIN pragma_foreign_key_list(m.name,'main') p WHERE m.type='table'
               ORDER BY m.name,p.id,p.seq LIMIT 59)
             SELECT count(*),sum(typeof("table")<>'text'
               OR length(CAST("table" AS BLOB))>128 OR typeof("from")<>'text'
               OR length(CAST("from" AS BLOB))>128
               OR ("to" IS NOT NULL AND (typeof("to")<>'text'
                   OR length(CAST("to" AS BLOB))>128))
               OR typeof(id)<>'integer' OR id<0 OR typeof(seq)<>'integer' OR seq<0
               OR on_update NOT IN ('NO ACTION','RESTRICT','CASCADE','SET NULL','SET DEFAULT')
               OR on_delete NOT IN ('NO ACTION','RESTRICT','CASCADE','SET NULL','SET DEFAULT')
               OR match<>'NONE')
             FROM candidate""",
            (58, 0),
        ),
    ]
    for sql, expected in gates:
        work.check()
        if expected is None:
            rows = connection.execute(text(sql)).all()
            if len(rows) != 1 or tuple(rows[0]) not in ((1, 0), (2, 0)):
                raise MigrationRefused("schema_incompatible")
        else:
            _scalar_gate(connection, sql, expected)


def _failure_sqlite_policy(sql: str) -> tuple[tuple[str | None, str], ...]:
    tokens = set(_sqlite_ddl_tokens(sql))
    if tokens.intersection(
        {
            "COLLATE",
            "CONFLICT",
            "GENERATED",
            "WITHOUT",
            "STRICT",
            "AUTOINCREMENT",
            "DEFAULT",
            "DEFERRED",
        }
    ):
        raise MigrationRefused("schema_incompatible")
    # SQLite reflection drops FK deferrability. Admit only the native immediate
    # clauses; the complete declaration/profile comparison binds all three FKs.
    words = [
        value.upper() for kind, value, _start, _end in _sqlite_ddl_items(sql) if kind == "word"
    ]
    for index, word in enumerate(words):
        if word == "DEFERRABLE" and (index == 0 or words[index - 1] != "NOT"):
            raise MigrationRefused("schema_incompatible")
    if words.count("DEFERRABLE") != 3:
        raise MigrationRefused("schema_incompatible")
    return _sqlite_check_declarations(sql)


def _sqlite_executables(connection: Connection) -> dict[str, Any]:
    rows = connection.execute(
        text(
            "SELECT name,tbl_name,sql FROM main.sqlite_master "
            "WHERE type='trigger' ORDER BY name LIMIT 4"
        )
    ).all()
    if len(rows) != 3 or any(any(type(value) is not str for value in row) for row in rows):
        raise MigrationRefused("schema_incompatible")
    return {"triggers": [{"name": row[0], "table": row[1], "sql": row[2]} for row in rows]}


# These queries inventory the complete public namespace. Counts and native byte
# aggregates are checked before transferring bodies to Python or reflection.
_PG_INDEXES = """WITH candidate AS MATERIALIZED (
 SELECT t.relname::text AS table_name,x.relname::text AS index_name,
        i.*,x.relam,x.reloptions
 FROM pg_catalog.pg_index i
 JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
 JOIN pg_catalog.pg_class x ON x.oid=i.indexrelid
 WHERE n.nspname='public' ORDER BY t.relname,x.relname LIMIT 46
), observed AS (
 SELECT c.*,
   pg_catalog.pg_get_indexdef(c.indexrelid) AS definition,
   CASE WHEN c.indpred IS NULL THEN NULL
        ELSE pg_catalog.pg_get_expr(c.indpred,c.indrelid) END AS predicate,
   p.column_names,p.sort_options,p.part_count,p.invalid_parts,
   k.constraint_count,k.constraint_kind,
   am.amname
 FROM candidate c
 LEFT JOIN pg_catalog.pg_am am ON am.oid=c.relam
 CROSS JOIN LATERAL (
   SELECT count(*) AS part_count,
     array_agg(a.attname::text ORDER BY u.ord) AS column_names,
     array_agg(u.sort_option ORDER BY u.ord) AS sort_options,
     count(*) FILTER (WHERE a.attnum IS NULL OR a.attisdropped OR u.attnum<=0
       OR op.oid IS NULL OR NOT op.opcdefault OR op.opcmethod<>c.relam
       OR u.sort_option NOT BETWEEN 0 AND 3) AS invalid_parts
   FROM (SELECT * FROM unnest(c.indkey::smallint[],c.indoption::smallint[],
               c.indclass::oid[]) WITH ORDINALITY
               AS z(attnum,sort_option,opclass_oid,ord) LIMIT 6) u
   LEFT JOIN pg_catalog.pg_attribute a
     ON a.attrelid=c.indrelid AND a.attnum=u.attnum
   LEFT JOIN pg_catalog.pg_opclass op ON op.oid=u.opclass_oid
 ) p
 CROSS JOIN LATERAL (
   SELECT count(*) AS constraint_count,min(contype::text) AS constraint_kind
   FROM (SELECT contype FROM pg_catalog.pg_constraint
      WHERE conrelid=c.indrelid AND conindid=c.indexrelid
        AND contype IN ('p','u','x') LIMIT 2) bounded
 ) k
), evaluated AS (
 SELECT *,CASE WHEN indisvalid AND indisready AND NOT indnullsnotdistinct
      AND indnatts BETWEEN 1 AND 5 AND indnkeyatts=indnatts
      AND part_count=indnatts AND invalid_parts=0
      AND indexprs IS NULL AND coalesce(cardinality(reloptions),0)=0
      AND amname='btree' AND constraint_count<=1
      AND (constraint_kind IS NULL OR constraint_kind IN ('p','u'))
      AND (indisprimary=(constraint_kind IS NOT DISTINCT FROM 'p'))
      AND (constraint_kind IS NULL OR indisunique)
    THEN 0 ELSE 1 END AS invalid
 FROM observed
)
"""


def _postgres_gates(connection: Connection, work: LedgerCheck) -> None:
    gates = [
        (
            """SELECT count(*) FROM (SELECT 1 FROM pg_catalog.pg_class
             WHERE relnamespace=pg_my_temp_schema() LIMIT 1) x""",
            (0,),
        ),
        (
            """SELECT count(*) FROM (SELECT 1 FROM pg_catalog.pg_namespace
             WHERE nspname NOT IN ('public','information_schema')
               AND nspname NOT LIKE 'pg_%' LIMIT 1) x""",
            (0,),
        ),
        (
            """SELECT count(*),count(*) FILTER (WHERE relkind='r'),
             count(*) FILTER (WHERE relkind='i'),
             count(*) FILTER (WHERE relkind NOT IN ('r','i') OR relrowsecurity
               OR relforcerowsecurity OR relpersistence<>'p' OR relispartition)
             FROM (SELECT c.* FROM pg_catalog.pg_class c
               JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' ORDER BY c.relname LIMIT 67) x""",
            (66, 21, 45, 0),
        ),
        (
            """WITH candidate AS MATERIALIZED (
             SELECT c.oid,a.*,pg_catalog.format_type(a.atttypid,a.atttypmod) AS formatted,
               pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_body
             FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum>0
             LEFT JOIN pg_catalog.pg_attrdef d
               ON d.adrelid=c.oid AND d.adnum=a.attnum
             WHERE n.nspname='public' AND c.relkind='r'
             ORDER BY c.relname,a.attnum LIMIT 172)
             SELECT count(*),count(*) FILTER (WHERE attisdropped OR attgenerated<>''
               OR attidentity<>'' OR attnum>32 OR octet_length(formatted)>65536
               OR coalesce(octet_length(default_body),0)>65536),
             coalesce(sum(octet_length(formatted)+coalesce(octet_length(default_body),0)),0)
                 <=1310720
             FROM candidate""",
            (171, 0, True),
        ),
        (
            _PG_INDEXES
            + """SELECT count(*),coalesce(sum(invalid),0)::bigint,
             coalesce(max(octet_length(definition)),0)<=65536,
             coalesce(sum(octet_length(definition)+coalesce(octet_length(predicate),0)),0)
               <=1310720 FROM evaluated""",
            (45, 0, True, True),
        ),
        (
            """WITH candidate AS MATERIALIZED (
             SELECT k.*,pg_catalog.pg_get_constraintdef(k.oid,false) AS body,
               pg_catalog.pg_get_constraintdef(k.oid,true) AS pretty
             FROM pg_catalog.pg_constraint k
             JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='public' ORDER BY c.relname,k.conname LIMIT 206)
             SELECT count(*),count(*) FILTER (WHERE contype NOT IN ('p','u','f','c','t')
               OR NOT convalidated
               OR coalesce(cardinality(conkey),0)>CASE WHEN contype='c' THEN 7 ELSE 5 END
               OR coalesce(cardinality(confkey),0)>5
               OR (contype<>'f' AND confkey IS NOT NULL)
               OR (contype='t' AND (conkey IS NOT NULL OR confkey IS NOT NULL
                   OR conindid<>0 OR confrelid<>0 OR NOT condeferrable OR NOT condeferred
                    OR (SELECT count(*) FROM pg_catalog.pg_trigger t
                        WHERE t.tgconstraint=candidate.oid AND NOT t.tgisinternal
                          AND t.tgrelid=candidate.conrelid AND t.tgname=candidate.conname
                          AND t.tgdeferrable=candidate.condeferrable
                          AND t.tginitdeferred=candidate.condeferred)<>1))
               OR octet_length(body)>65536 OR octet_length(pretty)>65536),
               coalesce(sum(octet_length(body)+octet_length(pretty)),0)<=1310720,
               count(*) FILTER (WHERE contype='c'),count(*) FILTER (WHERE contype='f'),
               count(*) FILTER (WHERE contype='p'),count(*) FILTER (WHERE contype='u'),
               count(*) FILTER (WHERE contype='t')
             FROM candidate""",
            (205, 0, True, 129, 34, 21, 16, 5),
        ),
        (
            """SELECT count(*) FROM (
             SELECT 1 FROM pg_catalog.pg_description d
             JOIN pg_catalog.pg_class c ON d.objoid=c.oid
             JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='public' AND d.classoid='pg_catalog.pg_class'::regclass
             UNION ALL
             SELECT 1 FROM pg_catalog.pg_description d
             JOIN pg_catalog.pg_constraint k ON d.objoid=k.oid
             JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
             JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='public' AND d.classoid='pg_catalog.pg_constraint'::regclass
             LIMIT 1) x""",
            (0,),
        ),
    ]
    # PostgreSQL has no stored CREATE TABLE text. Bound the complete native
    # table description (columns/defaults, indexes and constraints) per table
    # and in aggregate before any of those bodies cross the driver boundary.
    gates.append(
        (
            """
        WITH sizes AS (
          SELECT table_name,size FROM (
            SELECT c.relname::text AS table_name,
              octet_length(pg_catalog.format_type(a.atttypid,a.atttypmod))
              +coalesce(octet_length(pg_catalog.pg_get_expr(d.adbin,d.adrelid)),0) AS size
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum>0
            LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='public' AND c.relkind='r'
            ORDER BY c.relname,a.attnum LIMIT 172) columns
          UNION ALL
          SELECT table_name,size FROM (
            SELECT c.relname::text AS table_name,
              octet_length(pg_catalog.pg_get_constraintdef(k.oid,false))
              +octet_length(pg_catalog.pg_get_constraintdef(k.oid,true)) AS size
            FROM pg_catalog.pg_constraint k
            JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public'
            ORDER BY c.relname,k.conname LIMIT 206) constraints
          UNION ALL
          SELECT table_name,size FROM (
            SELECT c.relname::text AS table_name,
              octet_length(pg_catalog.pg_get_indexdef(i.indexrelid))
              +coalesce(octet_length(pg_catalog.pg_get_expr(i.indpred,i.indrelid)),0) AS size
            FROM pg_catalog.pg_index i
            JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public'
            ORDER BY c.relname,i.indexrelid LIMIT 46) indexes
        ), per_table AS (
          SELECT table_name,sum(size) AS size FROM sizes GROUP BY table_name
        )
        SELECT count(*),max(size)<=65536,sum(size)<=1310720 FROM per_table
        """,
            (21, True, True),
        )
    )
    for sql, expected in gates:
        work.check()
        _scalar_gate(connection, sql, expected)


def _postgres_authority(connection: Connection) -> None:
    # Only the existing installation owner may own the new relation. Nonowner
    # relation rights are SELECT-only and must already have predecessor access;
    # no PUBLIC, column grants, grant options, or custom broad defaults hide in
    # the canonical owner token.
    _scalar_gate(
        connection,
        """
        WITH owner AS (
          SELECT c.relowner FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='installation_adoptions' AND c.relkind='r'
        ), target AS (
          SELECT c.* FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname='job_failure_evidence' AND c.relkind='r'
        )
        SELECT (SELECT count(*) FROM owner)=1 AND (SELECT count(*) FROM target)=1
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace,owner o
            WHERE n.nspname='public' AND c.relkind='r' AND c.relowner<>o.relowner)
          AND NOT EXISTS (
            SELECT 1 FROM target t,owner o,
              LATERAL aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) x
            WHERE x.grantor<>o.relowner OR x.is_grantable OR x.grantee=0
              OR (x.grantee<>o.relowner AND
                 (x.privilege_type<>'SELECT'
                  OR NOT has_table_privilege(x.grantee,'public.jobs','SELECT'))))
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute a,target t
            WHERE a.attrelid=t.oid AND a.attacl IS NOT NULL)
          AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_default_acl d,owner o,
              LATERAL aclexplode(d.defaclacl) x
            WHERE d.defaclrole=o.relowner
              AND (d.defaclnamespace=0 OR d.defaclnamespace='public'::regnamespace)
              AND (x.grantee<>o.relowner OR x.grantor<>o.relowner OR x.is_grantable))
    """,
        (True,),
    )

    # Direct ACLs are not effective authority: a NOINHERIT login can still SET
    # ROLE through a membership chain. Anchor the exception to the observed
    # installation owner, including when the current observer is a reader.
    # As in installation exclusion, superusers are trusted control-plane actors,
    # never application identities. Existing predecessor grants stay unchanged.
    _scalar_gate(
        connection,
        """
        SELECT NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_roles actor
          JOIN pg_catalog.pg_roles effective
            ON actor.oid=effective.oid OR pg_has_role(actor.oid,effective.oid,'MEMBER')
          CROSS JOIN (
            SELECT c.relowner FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname='installation_adoptions'
              AND c.relkind='r'
          ) owner
          WHERE actor.rolcanlogin AND NOT actor.rolsuper AND actor.oid<>owner.relowner
            AND (effective.oid=owner.relowner
              OR has_schema_privilege(effective.oid,'public','CREATE')
              OR has_table_privilege(effective.oid,'public.job_failure_evidence',
                                     'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))
          LIMIT 1
        )
    """,
        (True,),
    )


def _postgres_executables(connection: Connection) -> dict[str, Any]:
    _scalar_gate(
        connection,
        """
        SELECT
          (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public'),
          (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal),
          (SELECT count(*) FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
           JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
          (SELECT bool_and(p.prokind='f' AND p.pronargs=0
                  AND p.prorettype='pg_catalog.trigger'::regtype
                  AND l.lanname='plpgsql' AND coalesce(cardinality(p.proacl),0)<=1
                  AND octet_length(p.prosrc)<=16384
                  AND octet_length(coalesce(p.proconfig::text,''))<=4096)
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public')
    """,
        (2, 7, 0, True),
    )
    _scalar_gate(
        connection,
        """
        SELECT
          (SELECT max(octet_length(pg_get_functiondef(p.oid)))<=16384
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public'),
          (SELECT max(octet_length(pg_get_triggerdef(t.oid)))<=4096
           FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal),
          (SELECT coalesce(sum(octet_length(pg_get_functiondef(p.oid))
                           +octet_length(row_to_json(p)::text)),0)
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public')
          +(SELECT coalesce(sum(octet_length(pg_get_triggerdef(t.oid))
                               +octet_length(row_to_json(t)::text)),0)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal)<=65536
    """,
        (True, True, True),
    )
    ownership = connection.execute(
        text("""
        SELECT p.proowner=a.relowner
          AND (SELECT count(*) FROM aclexplode(coalesce(p.proacl,
                   acldefault('f',p.proowner))))=1
          AND NOT EXISTS (
            SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
            WHERE x.grantee<>a.relowner OR x.grantor<>a.relowner
              OR x.privilege_type<>'EXECUTE' OR x.is_grantable)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_class a ON a.relname='installation_adoptions'
        JOIN pg_namespace an ON an.oid=a.relnamespace AND an.nspname='public'
        WHERE n.nspname='public' ORDER BY p.proname LIMIT 3
    """)
    ).all()
    if ownership != [(True,), (True,)]:
        raise MigrationRefused("schema_incompatible")
    functions = [
        dict(row)
        for row in connection.execute(
            text("""
            SELECT p.proname AS name,l.lanname AS language,p.prokind AS kind,
              p.provolatile AS volatility,p.proparallel AS parallel,p.prosecdef AS security_definer,
              p.proisstrict AS strict,p.proleakproof AS leakproof,p.proretset AS returns_set,
              p.procost AS cost,p.prorows AS rows,p.proconfig AS settings,
              p.prosupport::regproc::text AS support,p.probin AS binary,
              pg_get_function_identity_arguments(p.oid) AS arguments,
              pg_get_function_result(p.oid) AS result,pg_get_functiondef(p.oid) AS definition
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_language l ON l.oid=p.prolang
            WHERE n.nspname='public' ORDER BY p.proname LIMIT 3
        """)
        ).mappings()
    ]
    if len(functions) != 2:
        raise MigrationRefused("schema_incompatible")
    for function in functions:
        function["owner"] = _OWNER
        function["acl"] = [[_OWNER, _OWNER, "EXECUTE", False]]
        function["definition_sha256"] = hashlib.sha256(
            function["definition"].encode("utf-8")
        ).hexdigest()
    triggers = [
        dict(row)
        for row in connection.execute(
            text("""
        SELECT t.tgname AS name,c.relname AS relation,t.tgtype AS type,
          t.tgenabled AS enabled,t.tgdeferrable AS deferrable,
          t.tginitdeferred AS initially_deferred,t.tgnargs AS argument_count,
          encode(t.tgargs,'hex') AS arguments,t.tgattr::text AS columns,
          t.tgqual::text AS condition,t.tgoldtable AS old_table,t.tgnewtable AS new_table,
          p.proname AS function_name,pn.nspname AS function_schema,
          (t.tgconstraint<>0) AS constraint_trigger,pg_get_triggerdef(t.oid) AS definition
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY t.tgname LIMIT 8
    """)
        ).mappings()
    ]
    if len(triggers) != 7:
        raise MigrationRefused("schema_incompatible")
    return {"functions": functions, "triggers": triggers, "rules": []}


def _postgres_columns(
    connection: Connection, selected: list[str], work: LedgerCheck
) -> dict[str, list[list[Any]]]:
    count = 171
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


def _postgres_indexes(connection: Connection, work: LedgerCheck) -> dict[str, list[dict[str, Any]]]:
    rows = (
        connection.execute(
            text(
                _PG_INDEXES
                + """
        SELECT table_name,index_name,indisunique,indisprimary,indisvalid,indisready,
          definition,predicate,column_names,sort_options,constraint_kind,invalid
        FROM evaluated ORDER BY table_name,index_name LIMIT 46
    """
            )
        )
        .mappings()
        .all()
    )
    if len(rows) != 45:
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


def _sqlite_table_options(
    connection: Connection, selected: list[str], work: LedgerCheck
) -> tuple[list[str], dict[str, tuple[tuple[str | None, str], ...]]]:
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
            declarations[table] = (
                _failure_sqlite_policy(row[3])
                if table == _TABLE
                else _sqlite_check_supported_ddl(table, row[3], ledger=True)
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
    connection: Connection, selected: list[str], work: LedgerCheck
) -> tuple[dict[str, list[tuple[Any, ...]]], dict[tuple[str, str], list[tuple[Any, ...]]]]:
    """Observe the same native index rows once, within the preceding exact gates."""
    index_count, part_count = 45, 126
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


def _observe(
    connection: Connection, tables: list[str], name: str, work: LedgerCheck
) -> dict[str, Any]:
    inspector = inspect(connection)
    schema = "public" if name == "postgresql" else None
    indexes_by_table: dict[str, list[dict[str, Any]]] = {}
    if name == "sqlite":
        selected, sqlite_checks = _sqlite_table_options(connection, tables, work)
        native_by_table, parts_by_index = _sqlite_native_indexes(connection, selected, work)
        executable_profile = _sqlite_executables(connection)
    else:
        indexes_by_table = _postgres_indexes(connection, work)
        constraints = _postgres_constraints(inspector, tables, work)
        columns_by_table = _postgres_columns(connection, tables, work)
        executable_profile = _postgres_executables(connection)
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
                WHERE n.nspname='public' ORDER BY c.relname, pg_get_indexdef(i.indexrelid) LIMIT 46
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
                ORDER BY c.relname,a.attnum LIMIT 172
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
                WHERE n.nspname='public' ORDER BY c.relname,pg_get_constraintdef(k.oid) LIMIT 206
            """)
                )
            ],
        }
        _canonicalize_postgresql_enum_checks(result)
    result["$executables"] = executable_profile
    return result


def inspect_failure_catalog(connection: Connection, work: LedgerCheck) -> FailureCatalog:
    """Return complete successor and retained ar7 only after exact validation.

    This is observation only: it never rewrites history, revisions, grants,
    readiness or data, and it never commits or rolls back the caller's work.
    """
    name = dialect(connection)
    expected = _profile(name)
    selected = sorted(key for key in expected if not key.startswith("$"))
    if len(selected) != 21 or _TABLE not in selected:
        raise MigrationRefused("schema_incompatible")
    # Validate the source-owned successor's retained contract too. This is not
    # a shortcut around observing the actual complete successor below.
    predecessor = installed_profile(name, LEDGER)
    _require_equal(_project_ar7(expected, name), predecessor)
    work.check()
    if name == "sqlite":
        _sqlite_gates(connection, work)
    else:
        _postgres_gates(connection, work)
        _postgres_authority(connection)
    tables = _tables(connection, name, selected)
    observed = _observe(connection, tables, name, work)
    _require_equal(observed, expected)
    retained = _project_ar7(observed, name)
    _require_equal(retained, predecessor)
    work.check()
    return FailureCatalog(copy.deepcopy(observed), retained)
