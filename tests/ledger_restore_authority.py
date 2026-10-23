"""Independent raw authority and typed-row witnesses for same-cluster restoration."""

import hashlib
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

TRIGGER_TABLES = {
    "ar7_accounts_constraint": "budget_accounts",
    "ar7_calls_constraint": "provider_calls",
    "ar7_entries_constraint": "budget_entries",
    "ar7_jobs_constraint": "jobs",
    "ar7_scopes_constraint": "resource_scopes",
}

AUTHORITY_SQL = {
    "database": """
        SELECT datname AS name,pg_get_userbyid(datdba) AS owner,datacl::text AS acl
        FROM pg_database WHERE datname=current_database()
    """,
    "schemas": """
        SELECT nspname AS name,pg_get_userbyid(nspowner) AS owner,nspacl::text AS acl
        FROM pg_namespace WHERE nspname='public' ORDER BY nspname
    """,
    "relations": """
        SELECT c.oid::bigint AS oid,c.relname AS name,c.relkind AS kind,
               pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' ORDER BY c.relname
    """,
    "functions": """
        SELECT p.oid::bigint AS oid,p.proname AS name,
               pg_get_function_identity_arguments(p.oid) AS arguments,
               pg_get_userbyid(p.proowner) AS owner,p.proacl::text AS acl,
               p.prosecdef AS security_definer,p.proconfig AS settings,l.lanname AS language,
               p.prosrc AS body,pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public'
        ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)
    """,
    "triggers": """
        SELECT t.oid::bigint AS oid,t.tgname AS name,
               t.tgrelid::bigint AS relation_oid,t.tgfoid::bigint AS function_oid,
               t.tgconstraint::bigint AS constraint_oid,c.relname AS relation,
               p.proname AS function_name,pn.nspname AS function_schema,
               pg_get_function_identity_arguments(p.oid) AS function_arguments,
               t.tgenabled AS enabled,t.tgdeferrable AS deferrable,
               t.tginitdeferred AS initially_deferred,pg_get_triggerdef(t.oid) AS definition,
               k.conname AS constraint_name,k.conrelid::bigint AS constraint_relation_oid,
               k.condeferrable AS constraint_deferrable,
               k.condeferred AS constraint_initially_deferred
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace
        LEFT JOIN pg_constraint k ON k.oid=t.tgconstraint
        WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY t.tgname
    """,
    "grants": """
        WITH objects AS (
          SELECT 'database'::text AS kind,datname::text AS name,''::text AS arguments,
                 datacl AS acl FROM pg_database WHERE datname=current_database()
          UNION ALL SELECT 'schema',nspname,'',nspacl FROM pg_namespace WHERE nspname='public'
          UNION ALL SELECT 'relation',c.relname,'',c.relacl FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
          UNION ALL SELECT 'function',p.proname,pg_get_function_identity_arguments(p.oid),
                 p.proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                 WHERE n.nspname='public'
        )
        SELECT o.kind,o.name,o.arguments,pg_get_userbyid(x.grantor) AS grantor,
               CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END AS grantee,
               x.privilege_type AS privilege,x.is_grantable AS grantable
        FROM objects o CROSS JOIN LATERAL aclexplode(o.acl) x
        ORDER BY o.kind,o.name,o.arguments,grantor,grantee,privilege,grantable
    """,
    "roles": """
        SELECT rolname AS name,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,
               rolreplication,rolbypassrls FROM pg_roles
        WHERE rolname IN (:owner,:app,:group) ORDER BY rolname
    """,
    "memberships": """
        SELECT r.rolname AS role,m.rolname AS member,g.rolname AS grantor,
               a.admin_option,a.inherit_option,a.set_option
        FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid
        JOIN pg_roles m ON m.oid=a.member JOIN pg_roles g ON g.oid=a.grantor
        WHERE r.rolname IN (:owner,:app,:group) OR m.rolname IN (:owner,:app,:group)
           OR g.rolname IN (:owner,:app,:group)
        ORDER BY r.rolname,m.rolname,g.rolname
    """,
}


def typed(value):
    """Retain native types rather than relying on Python bool/int equality."""
    kind = type(value).__module__ + "." + type(value).__qualname__
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        result = [[key, typed(item)] for key, item in sorted(value.items())]
    elif isinstance(value, list | tuple):
        result = [typed(item) for item in value]
    elif isinstance(value, bytes):
        result = value.hex()
    elif isinstance(value, date | datetime):
        result = value.isoformat()
    elif isinstance(value, str | int | float | bool | Decimal) or value is None:
        result = str(value)
    else:
        raise TypeError("unsupported restore witness scalar")
    return {"type": kind, "value": result}


def observe_authority(connection, pg):
    parameters = {name: pg[name + "_role"] for name in ("owner", "app", "group")}
    result = {
        name: [dict(row) for row in connection.execute(text(query), parameters).mappings()]
        for name, query in AUTHORITY_SQL.items()
    }
    assert len(result["database"]) == 1
    for function in result["functions"]:
        function["body_sha256"] = hashlib.sha256(function["body"].encode()).hexdigest()
    return result


def unique(rows, fields):
    values = {tuple(row[field] for field in fields): row for row in rows}
    assert len(values) == len(rows), "duplicate authority identity"
    return values


def authority_identity(value):
    """Prove raw associations first; only database-local OIDs differ across copies."""
    result = deepcopy(value)
    assert len(result["database"]) == 1
    database = result["database"][0].pop("name")
    relations = unique(result["relations"], ("name",))
    functions = unique(result["functions"], ("name", "arguments"))
    unique(result["triggers"], ("name",))
    unique(result["grants"], ("kind", "name", "arguments", "grantor", "grantee", "privilege"))
    for kind in ("relations", "functions", "triggers"):
        identifiers = [row["oid"] for row in result[kind]]
        assert all(type(oid) is int and oid > 0 for oid in identifiers)
        assert len(identifiers) == len(set(identifiers))
    for trigger in result["triggers"]:
        relation = relations[(trigger["relation"],)]
        function = functions[(trigger["function_name"], trigger["function_arguments"])]
        assert trigger["function_schema"] == "public"
        assert trigger["relation_oid"] == relation["oid"]
        assert trigger["function_oid"] == function["oid"]
        assert type(trigger["constraint_oid"]) is int and trigger["constraint_oid"] > 0
        assert trigger["constraint_relation_oid"] == relation["oid"]
        assert trigger["constraint_name"] == trigger["name"]
        assert trigger["constraint_deferrable"] is trigger["deferrable"]
        assert trigger["constraint_initially_deferred"] is trigger["initially_deferred"]
    for kind in ("relations", "functions", "triggers"):
        for row in result[kind]:
            for key in list(row):
                if key == "oid" or key.endswith("_oid"):
                    del row[key]
    for grant in result["grants"]:
        if grant["kind"] == "database":
            assert grant["name"] == database
            grant["name"] = "<observed database>"
    return typed(result)


def assert_same_authority(source, target):
    assert source["database"][0]["name"] != target["database"][0]["name"]
    assert authority_identity(source) == authority_identity(target)


def assert_ledger_authority(value, owner, expected_function):
    tables = [row for row in value["relations"] if row["kind"] == "r"]
    assert tables and all(row["owner"] == owner for row in tables)
    adoption = unique(tables, ("name",))[("installation_adoptions",)]
    assert adoption["owner"] == owner
    assert len(value["functions"]) == 1
    function = value["functions"][0]
    assert function["name"] == "ar7_ledger_constraint" and function["arguments"] == ""
    assert function["owner"] == owner
    assert function["security_definer"] is False and function["language"] == "plpgsql"
    assert function["settings"] == expected_function["settings"]
    assert function["definition"] == expected_function["definition"]
    assert function["body"] and function["body"] in function["definition"]
    assert function["body_sha256"] == hashlib.sha256(function["body"].encode()).hexdigest()
    grants = [grant for grant in value["grants"] if grant["kind"] == "function"]
    assert grants == [
        {
            "kind": "function",
            "name": "ar7_ledger_constraint",
            "arguments": "",
            "grantor": owner,
            "grantee": owner,
            "privilege": "EXECUTE",
            "grantable": False,
        }
    ]
    triggers = unique(value["triggers"], ("name",))
    assert set(triggers) == {(name,) for name in TRIGGER_TABLES}
    for name, table in TRIGGER_TABLES.items():
        trigger = triggers[(name,)]
        assert trigger["relation"] == table
        assert trigger["enabled"] == "O"
        assert trigger["deferrable"] is True and trigger["initially_deferred"] is True
    authority_identity(value)
