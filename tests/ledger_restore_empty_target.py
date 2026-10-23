"""Bounded catalog witnesses for the pinned default empty restore target."""

from ledger_restore_authority import AUTHORITY_SQL, typed
from ledger_restore_postgres_fixture import save
from sqlalchemy import text
from test_run_projection_postgres import drain

MAX_CATALOG_ROWS = 128
PUBLIC_ACL = "{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}"
NON_SYSTEM = "n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
EMPTY_SQL = {
    "namespaces": """
        SELECT n.oid::bigint AS oid,n.nspname AS name,
               pg_get_userbyid(n.nspowner) AS owner,n.nspacl::text AS acl
        FROM pg_namespace n WHERE """
    + NON_SYSTEM
    + " ORDER BY n.nspname",
    "relations": """
        SELECT n.nspname AS schema,c.relname AS name,c.relkind AS kind,c.oid::bigint AS oid,
               pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE """
    + NON_SYSTEM
    + " ORDER BY n.nspname,c.relname",
    "routines": """
        SELECT n.nspname AS schema,p.proname AS name,p.prokind AS kind,p.oid::bigint AS oid,
               pg_get_function_identity_arguments(p.oid) AS arguments,
               pg_get_userbyid(p.proowner) AS owner,p.proacl::text AS acl
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE """
    + NON_SYSTEM
    + " ORDER BY n.nspname,p.proname,p.oid",
    "types": """
        SELECT n.nspname AS schema,t.typname AS name,t.typtype AS kind,t.oid::bigint AS oid,
               pg_get_userbyid(t.typowner) AS owner,t.typacl::text AS acl
        FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE """
    + NON_SYSTEM
    + " ORDER BY n.nspname,t.typname",
    "constraints": """
        SELECT n.nspname AS schema,c.conname AS name,c.contype AS kind,c.oid::bigint AS oid
        FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE """
    + NON_SYSTEM
    + " ORDER BY n.nspname,c.conname,c.oid",
    "triggers": """
        SELECT n.nspname AS schema,c.relname AS relation,t.tgname AS name,t.oid::bigint AS oid
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND """
    + NON_SYSTEM
    + " ORDER BY n.nspname,c.relname,t.tgname",
    "default_acls": """
        SELECT d.oid::bigint AS oid,pg_get_userbyid(d.defaclrole) AS owner,
               d.defaclnamespace::bigint AS namespace_oid,d.defaclobjtype AS kind,
               d.defaclacl::text AS acl FROM pg_default_acl d ORDER BY d.oid
    """,
    "extensions": """
        SELECT e.oid::bigint AS oid,e.extname AS name,pg_get_userbyid(e.extowner) AS owner,
               n.nspname AS schema,e.extversion AS version,e.extrelocatable AS relocatable,
               e.extconfig AS configuration,e.extcondition AS conditions
        FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace ORDER BY e.extname
    """,
}


def bounded_rows(connection, query, parameters):
    rows = [
        dict(row)
        for row in connection.execute(
            text(query.strip() + " LIMIT " + str(MAX_CATALOG_ROWS + 1)), parameters
        ).mappings()
    ]
    assert len(rows) <= MAX_CATALOG_ROWS, "empty-target catalog row bound exceeded"
    return rows


def observe_empty_target(fixture, pg, directory, name, record_property):
    """Sixteen fixed catalog queries, plus two local limits, on one fresh connection."""
    parameters = {key: pg[key + "_role"] for key in ("owner", "app", "group")}
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            result = {
                "authority": {
                    key: bounded_rows(connection, query, parameters)
                    for key, query in AUTHORITY_SQL.items()
                },
                "inventory": {
                    key: bounded_rows(connection, query, {}) for key, query in EMPTY_SQL.items()
                },
            }
    finally:
        drain(pg)
    save(directory, name, typed(result), record_property)
    return result


def assert_empty_target(value, *, database, owner, source_authority):
    """Two equally nonempty captures cannot satisfy this independent baseline."""
    assert set(value) == {"authority", "inventory"}
    authority, inventory = value["authority"], value["inventory"]
    assert set(authority) == set(AUTHORITY_SQL) and set(inventory) == set(EMPTY_SQL)
    assert typed(authority["database"]) == typed([{"name": database, "owner": owner, "acl": None}])
    schema = {"name": "public", "owner": "pg_database_owner", "acl": PUBLIC_ACL}
    assert typed(authority["schemas"]) == typed([schema])
    for family in ("relations", "functions", "triggers"):
        assert type(authority[family]) is list and authority[family] == []
    grants = [
        {
            "kind": "schema",
            "name": "public",
            "arguments": "",
            "grantor": "pg_database_owner",
            "grantee": grantee,
            "privilege": privilege,
            "grantable": False,
        }
        for grantee, privilege in (
            ("PUBLIC", "USAGE"),
            ("pg_database_owner", "CREATE"),
            ("pg_database_owner", "USAGE"),
        )
    ]
    assert typed(authority["grants"]) == typed(grants)
    for family in ("roles", "memberships"):
        assert typed(authority[family]) == typed(source_authority[family])
    namespaces = inventory["namespaces"]
    assert type(namespaces) is list and len(namespaces) == 1
    namespace = namespaces[0]
    assert set(namespace) == {"oid", *schema}
    assert type(namespace["oid"]) is int and namespace["oid"] > 0
    assert typed({key: namespace[key] for key in schema}) == typed(schema)
    for family in ("relations", "routines", "types", "constraints", "triggers", "default_acls"):
        assert type(inventory[family]) is list and inventory[family] == []
    extensions = inventory["extensions"]
    assert type(extensions) is list and len(extensions) == 1
    extension = extensions[0]
    expected = {
        "name": "plpgsql",
        "owner": "postgres",
        "schema": "pg_catalog",
        "version": "1.0",
        "relocatable": False,
        "configuration": None,
        "conditions": None,
    }
    assert set(extension) == {"oid", *expected}
    assert type(extension["oid"]) is int and extension["oid"] > 0
    assert typed({key: extension[key] for key in expected}) == typed(expected)
