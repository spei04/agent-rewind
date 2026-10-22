"""Bounded inventory for the single reviewed ar7 executable surface."""

import hashlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .schema import MigrationRefused

_OWNER = "installation_table_owner"


def ledger_executables(connection: Connection) -> dict[str, Any]:
    """Bind function ownership to installed tables before replacing the role name."""
    # Refuse count/definition/ACL size before transferring executable metadata.
    bounds = connection.execute(
        text("""
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
                 AND p.proname='ar7_ledger_constraint'
                 AND l.lanname='plpgsql' AND cardinality(p.proacl)<=1
                 AND octet_length(p.prosrc)<=16384
                 AND octet_length(coalesce(p.proconfig::text,''))<=4096)
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public')
    """)
    ).one()
    if tuple(bounds) != (1, 5, 0, True):
        raise MigrationRefused("schema_incompatible")
    sizes = connection.execute(
        text("""
        SELECT
          (SELECT max(octet_length(pg_get_functiondef(p.oid)))
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public'),
          (SELECT max(octet_length(pg_get_triggerdef(t.oid)))
           FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal),
          (SELECT coalesce(sum(octet_length(pg_get_functiondef(p.oid))
                          + octet_length(row_to_json(p)::text)),0)
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public')
          + (SELECT coalesce(sum(octet_length(pg_get_triggerdef(t.oid))
                               + octet_length(row_to_json(t)::text)),0)
             FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
             JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='public' AND NOT t.tgisinternal)
    """)
    ).one()
    if sizes[0] > 16384 or sizes[1] > 4096 or sizes[2] > 65536:
        raise MigrationRefused("schema_incompatible")
    ownership = connection.execute(
        text("""
        SELECT p.proowner = a.relowner
          AND NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r' AND c.relowner<>a.relowner)
          AND (SELECT count(*) FROM aclexplode(p.proacl))=1
          AND NOT EXISTS (
            SELECT 1 FROM aclexplode(p.proacl) x
            WHERE x.grantee<>a.relowner OR x.grantor<>a.relowner
              OR x.privilege_type<>'EXECUTE' OR x.is_grantable)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_class a ON a.relname='installation_adoptions'
        JOIN pg_namespace an ON an.oid=a.relnamespace AND an.nspname='public'
        WHERE n.nspname='public'
    """)
    ).all()
    if ownership != [(True,)]:
        raise MigrationRefused("schema_incompatible")
    function = dict(
        connection.execute(
            text("""
        SELECT p.proname AS name, l.lanname AS language, p.prokind AS kind,
          p.provolatile AS volatility, p.proparallel AS parallel, p.prosecdef AS security_definer,
          p.proisstrict AS strict, p.proleakproof AS leakproof, p.proretset AS returns_set,
          p.procost AS cost, p.prorows AS rows, p.proconfig AS settings,
          p.prosupport::regproc::text AS support, p.probin AS binary,
          pg_get_function_identity_arguments(p.oid) AS arguments,
          pg_get_function_result(p.oid) AS result, pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public'
    """)
        )
        .mappings()
        .one()
    )
    function["owner"] = _OWNER
    function["acl"] = [[_OWNER, _OWNER, "EXECUTE", False]]
    function["definition_sha256"] = hashlib.sha256(
        function["definition"].encode("utf-8")
    ).hexdigest()
    triggers = [
        dict(row)
        for row in connection.execute(
            text("""
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
        """)
        ).mappings()
    ]
    return {"function": function, "triggers": triggers}
