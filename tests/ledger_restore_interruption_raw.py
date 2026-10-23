"""Raw source-derived schema witnesses that do not require installed provenance."""

import json
from copy import deepcopy

from ledger_restore_authority import assert_same_authority, typed
from ledger_restore_empty_target import AUTHORITY_SQL, EMPTY_SQL
from ledger_restore_postgres_fixture import save
from sqlalchemy import text
from test_run_projection_postgres import drain

TABLES = (
    "alembic_version",
    "api_keys",
    "artifact_objects",
    "artifact_refs",
    "audit",
    "budget_accounts",
    "budget_entries",
    "events",
    "installation_adoptions",
    "jobs",
    "migration_progress",
    "operation_keys",
    "operations",
    "organizations",
    "project_memberships",
    "projects",
    "provider_calls",
    "records",
    "resource_scopes",
    "run_index",
)
RAW_SQL = {
    **EMPTY_SQL,
    "columns": """
SELECT c.oid::bigint AS relation_oid,c.relname AS relation,a.attnum AS position,
 a.attname AS name,format_type(a.atttypid,a.atttypmod) AS type,
 a.attnotnull AS not_null,a.attidentity AS identity,a.attgenerated AS generated,
 pg_get_expr(d.adbin,d.adrelid) AS default_value
FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
ORDER BY c.relname,a.attnum
""",
    "indexes": """
SELECT i.indexrelid::bigint AS index_oid,ic.relname AS name,
 i.indrelid::bigint AS relation_oid,c.relname AS relation,i.indisunique AS is_unique,
 i.indisprimary AS is_primary,i.indisvalid AS valid,pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY c.relname,ic.relname
""",
    "constraint_definitions": """
SELECT k.oid::bigint AS oid,k.conname AS name,k.contype AS kind,
 k.conrelid::bigint AS relation_oid,c.relname AS relation,
 k.confrelid::bigint AS referenced_oid,rc.relname AS referenced_relation,
 k.condeferrable AS deferrable,k.condeferred AS deferred,k.convalidated AS valid,
 pg_get_constraintdef(k.oid) AS definition
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_class rc ON rc.oid=k.confrelid
WHERE n.nspname='public' ORDER BY c.relname,k.conname
""",
}


MAX_SNAPSHOT = 8 * 1024 * 1024


def encoded(value):
    return json.dumps(typed(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class SnapshotBudget:
    """Charge the exact compact typed-JSON snapshot before retaining each row."""

    def __init__(self):
        self.value = {
            "authority": {key: [] for key in AUTHORITY_SQL},
            "inventory": {key: [] for key in RAW_SQL},
            "rows_present": dict.fromkeys(TABLES, False),
        }
        self.bytes = len(encoded(self.value))
        assert self.bytes <= MAX_SNAPSHOT

    def append(self, family, name, row):
        rows = self.value[family][name]
        # All list/dict/type envelopes were charged in the initial empty shape.
        size = self.bytes + len(encoded(row)) + bool(rows)
        assert size <= MAX_SNAPSHOT, "raw snapshot retention bound exceeded"
        rows.append(row)
        self.bytes = size

    def present(self, name, value):
        assert type(value) is bool and self.value["rows_present"][name] is False
        self.bytes += len(encoded(value)) - len(encoded(False))
        self.value["rows_present"][name] = value


def bounded_rows(connection, query, parameters, budget, family, name):
    result = connection.execute(text(query.strip() + " LIMIT 1025"), parameters)
    for index, original in enumerate(result.mappings()):
        assert index < 1024, "raw catalog row bound exceeded"
        row = dict(original)
        assert len(row) <= 64
        for value in row.values():
            assert len(str(value).encode()) <= 65536, "raw catalog cell bound exceeded"
        budget.append(family, name, row)


def observe_schema_only(fixture, pg, directory, name, record_property):
    parameters = {key: pg[key + "_role"] for key in ("owner", "app", "group")}
    budget = SnapshotBudget()
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            for family, queries, binds in (
                ("authority", AUTHORITY_SQL, parameters),
                ("inventory", RAW_SQL, {}),
            ):
                for key, query in queries.items():
                    bounded_rows(connection, query, binds, budget, family, key)
            inventory = budget.value["inventory"]
            tables = tuple(row["name"] for row in inventory["relations"] if row["kind"] == "r")
            assert tables == TABLES, "raw schema table inventory differs"
            for table in TABLES:
                quoted = connection.dialect.identifier_preparer.quote(table)
                rows = connection.exec_driver_sql("SELECT 1 FROM " + quoted + " LIMIT 1").all()
                assert rows in ([], [(1,)])
                budget.present(table, bool(rows))
    finally:
        drain(pg)
    assert len(encoded(budget.value)) == budget.bytes <= MAX_SNAPSHOT
    save(directory, name, typed(budget.value), record_property)
    return budget.value


def structure(value):
    """Verify local OID associations before comparing cross-database identities."""
    result = deepcopy(value)
    for rows in value.values():
        for row in rows:
            for key, item in row.items():
                if key == "oid" or key.endswith("_oid"):
                    assert type(item) is int
                    assert item >= 0 if key in {"referenced_oid", "namespace_oid"} else item > 0
    relations = {row["name"]: row for row in value["relations"]}
    assert len(relations) == len(value["relations"])
    for row in value["columns"]:
        assert row["relation_oid"] == relations[row["relation"]]["oid"]
        assert type(row["position"]) is int and row["position"] > 0
        assert relations[row["relation"]]["kind"] == "r"
    for row in value["indexes"]:
        assert row["relation_oid"] == relations[row["relation"]]["oid"]
        assert row["index_oid"] == relations[row["name"]]["oid"]
        assert relations[row["name"]]["kind"] == "i"
    for row in value["constraint_definitions"]:
        assert row["relation_oid"] == relations[row["relation"]]["oid"]
        if row["referenced_oid"]:
            assert row["referenced_oid"] == relations[row["referenced_relation"]]["oid"]
        else:
            assert row["referenced_relation"] is None
    namespaces = {row["oid"] for row in value["namespaces"]}
    for row in value["default_acls"]:
        assert row["namespace_oid"] == 0 or row["namespace_oid"] in namespaces
    for rows in result.values():
        identifiers = [row["oid"] for row in rows if "oid" in row]
        assert all(type(item) is int and item > 0 for item in identifiers)
        assert len(identifiers) == len(set(identifiers))
        for row in rows:
            for key in tuple(row):
                if key == "oid" or key.endswith("_oid"):
                    del row[key]
    return typed(result)


def assert_schema_only(value, source):
    assert set(value) == set(source) == {"authority", "inventory", "rows_present"}
    assert set(value["rows_present"]) == set(TABLES)
    assert all(value["rows_present"][table] is False for table in TABLES)
    assert set(value["inventory"]) == set(source["inventory"]) == set(RAW_SQL)
    assert_same_authority(source["authority"], value["authority"])
    assert structure(source["inventory"]) == structure(value["inventory"])
    columns = [
        row["name"] for row in value["inventory"]["columns"] if row["relation"] == "api_keys"
    ]
    assert columns == ["id", "hash", "role", "name", "expires", "revoked"]
    assert not any(
        row["relation"] == "api_keys" and row["kind"] == "f"
        for row in value["inventory"]["constraint_definitions"]
    )
