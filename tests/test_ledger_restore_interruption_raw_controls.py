"""Independent schema-only, retention, and archive-stage controls without a database."""

from copy import deepcopy
from types import SimpleNamespace

import ledger_restore_interruption_raw as raw
import pytest
from ledger_restore_interruption_contracts import COLUMNS
from ledger_restore_interruption_oracles import archive_witness
from test_ledger_restore_controls import authority, restored, source_fixture


def witness():
    shape = {key: [] for key in raw.RAW_SQL}
    shape["namespaces"] = [{"oid": 1, "name": "public", "owner": "pg_database_owner", "acl": None}]
    shape["relations"] = [
        {
            "oid": index + 10,
            "name": name,
            "schema": "public",
            "kind": "r",
            "owner": "owner",
            "acl": None,
        }
        for index, name in enumerate(raw.TABLES)
    ]
    for relation in shape["relations"]:
        columns = COLUMNS if relation["name"] == "api_keys" else ("id",)
        shape["columns"].extend(
            {
                "relation_oid": relation["oid"],
                "relation": relation["name"],
                "position": position,
                "name": name,
                "type": "text",
                "not_null": True,
                "identity": "",
                "generated": "",
                "default_value": None,
            }
            for position, name in enumerate(columns, 1)
        )
    shape["relations"].append(
        {
            "oid": 80,
            "name": "api_keys_pkey",
            "schema": "public",
            "kind": "i",
            "owner": "owner",
            "acl": None,
        }
    )
    shape["indexes"] = [
        {
            "index_oid": 80,
            "name": "api_keys_pkey",
            "relation_oid": 11,
            "relation": "api_keys",
            "is_unique": True,
            "is_primary": True,
            "valid": True,
            "definition": "CREATE UNIQUE INDEX api_keys_pkey",
        }
    ]
    shape["constraints"] = [{"oid": 90, "schema": "public", "name": "api_keys_pkey", "kind": "p"}]
    shape["constraint_definitions"] = [
        {
            "oid": 90,
            "name": "api_keys_pkey",
            "kind": "p",
            "relation_oid": 11,
            "relation": "api_keys",
            "referenced_oid": 0,
            "referenced_relation": None,
            "deferrable": False,
            "deferred": False,
            "valid": True,
            "definition": "PRIMARY KEY (id)",
        }
    ]
    return {
        "authority": authority(),
        "inventory": shape,
        "rows_present": dict.fromkeys(raw.TABLES, False),
    }


def restored_witness(source):
    target = deepcopy(source)
    target["authority"] = restored(source["authority"])
    for rows in target["inventory"].values():
        for row in rows:
            for key in row:
                if (key == "oid" or key.endswith("_oid")) and row[key]:
                    row[key] += 1000
    return target


def test_raw_schema_accepts_distinct_oids_with_verified_local_associations():
    source = witness()
    target = restored_witness(source)
    retained = deepcopy(source)
    raw.assert_schema_only(target, source)
    assert source == retained and target["inventory"]["columns"][0]["relation_oid"] != 10


@pytest.mark.parametrize(
    "family,field,bad",
    [
        ("columns", "relation_oid", 999),
        ("columns", "type", "integer"),
        ("columns", "not_null", 1),
        ("columns", "position", 2),
        ("columns", "default_value", "unsafe"),
        ("relations", "owner", "different"),
        ("relations", "acl", "{=r/owner}"),
        ("indexes", "index_oid", 999),
        ("indexes", "is_unique", False),
        ("indexes", "definition", "different"),
        ("constraint_definitions", "relation_oid", 999),
        ("constraint_definitions", "referenced_oid", 999),
        ("constraint_definitions", "deferred", True),
        ("constraint_definitions", "kind", "f"),
    ],
)
def test_raw_schema_rejects_definition_type_acl_and_oid_mutations(family, field, bad):
    source = witness()
    target = restored_witness(source)
    target["inventory"][family][0][field] = bad
    with pytest.raises((AssertionError, KeyError)):
        raw.assert_schema_only(target, source)


@pytest.mark.parametrize(
    "change", ["row", "row-type", "missing-table", "column", "authority", "extra"]
)
def test_zero_row_and_complete_raw_shape_are_required(change):
    source = witness()
    target = restored_witness(source)
    if change == "row":
        target["rows_present"]["api_keys"] = True
    elif change == "row-type":
        target["rows_present"]["api_keys"] = 0
    elif change == "missing-table":
        target["rows_present"].pop("jobs")
    elif change == "column":
        target["inventory"]["columns"].pop(1)
    elif change == "authority":
        target["authority"]["functions"][0]["acl"] = None
    else:
        target["inventory"]["extra"] = []
    with pytest.raises(AssertionError):
        raw.assert_schema_only(target, source)


def test_retention_budget_charges_exact_typed_json_before_retaining(monkeypatch):
    budget = raw.SnapshotBudget()
    assert budget.bytes == len(raw.encoded(budget.value))
    first = {"name": "\u2603", "acl": None, "native": True}
    required = budget.bytes + len(raw.encoded(first))
    monkeypatch.setattr(raw, "MAX_SNAPSHOT", required)
    budget.append("authority", "roles", first)
    assert budget.bytes == len(raw.encoded(budget.value)) == required
    with pytest.raises(AssertionError, match="retention"):
        budget.append("authority", "roles", {"small": ""})
    assert budget.value["authority"]["roles"] == [first]
    budget.present("api_keys", True)
    assert budget.bytes == len(raw.encoded(budget.value))


@pytest.mark.parametrize("fault", ["rows", "fields", "cell", "budget"])
def test_each_query_checks_rows_before_retention(monkeypatch, fault):
    budget = raw.SnapshotBudget()
    rows = [{"name": "x"}] * 1025
    if fault == "fields":
        rows = [{str(index): None for index in range(65)}]
    elif fault == "cell":
        rows = [{"name": "x" * 65537}]
    elif fault == "budget":
        monkeypatch.setattr(raw, "MAX_SNAPSHOT", budget.bytes)
    consumed, queries = [], []

    def mappings():
        for row in rows:
            consumed.append(row)
            yield row

    def execute(query, params):
        queries.append((str(query), params))
        return SimpleNamespace(mappings=mappings)

    connection = SimpleNamespace(execute=execute)
    with pytest.raises(AssertionError):
        raw.bounded_rows(connection, "SELECT fixed", {}, budget, "authority", "roles")
    assert queries == [("SELECT fixed LIMIT 1025", {})]
    assert len(budget.value["authority"]["roles"]) == (1024 if fault == "rows" else 0)
    assert len(consumed) == (1025 if fault == "rows" else 1)


def test_actual_raw_observer_uses_only_fixed_queries_and_bounded_emptiness_probes(monkeypatch):
    source = witness()
    queries, drains = [], []

    class Connection:
        dialect = SimpleNamespace(identifier_preparer=SimpleNamespace(quote=lambda value: value))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            sql = str(query)
            queries.append(sql)
            for family, statements in (
                ("authority", raw.AUTHORITY_SQL),
                ("inventory", raw.RAW_SQL),
            ):
                for name, statement in statements.items():
                    if sql == statement.strip() + " LIMIT 1025":
                        return SimpleNamespace(
                            mappings=lambda family=family, name=name: source[family][name]
                        )
            raise AssertionError("unapproved raw SQL")

        def exec_driver_sql(self, sql):
            queries.append(sql)
            assert sql in {
                "SET LOCAL statement_timeout='2000ms'",
                "SET LOCAL lock_timeout='1000ms'",
                *("SELECT 1 FROM " + name + " LIMIT 1" for name in raw.TABLES),
            }
            return SimpleNamespace(all=lambda: [])

    from dataclasses import replace

    fixture = source_fixture()
    fixture = replace(fixture, case=replace(fixture.case, engine=SimpleNamespace(begin=Connection)))
    monkeypatch.setattr(raw, "drain", lambda pg: drains.append(pg))
    monkeypatch.setattr(raw, "save", lambda *args: None)
    pg = dict(owner_role="owner", app_role="app", group_role="group")
    result = raw.observe_schema_only(fixture, pg, None, "raw", lambda *a: None)
    assert result == source and drains == [pg]
    assert len(queries) == 2 + len(raw.AUTHORITY_SQL) + len(raw.RAW_SQL) + 20
    assert len(raw.AUTHORITY_SQL) + len(raw.RAW_SQL) <= 24


def test_archive_requires_exact_source_bound_copy_order_and_shape(tmp_path):
    source = witness()
    statements = []
    for table in raw.TABLES:
        columns = [
            row["name"] for row in source["inventory"]["columns"] if row["relation"] == table
        ]
        statements.append(
            ("COPY public." + table + " (" + ", ".join(columns) + ") FROM stdin;\n").encode()
        )
    archive = tmp_path / "archive"
    valid = b"PGDMP" + b"\0".join(statements)
    archive.write_bytes(valid)
    result = archive_witness(archive, source)
    assert result["copy_literals"][1].startswith("COPY public.api_keys ")
    variants = [
        valid.replace(b"PGDMP", b"WRONG", 1),
        b"PGDMP" + b"\0".join(statements[1:]),
        b"PGDMP" + b"\0".join([statements[1], statements[0], *statements[2:]]),
        valid + statements[-1],
        valid.replace(b"id, hash", b"hash, id"),
        valid + b"x" * (2 * 1024 * 1024),
    ]
    for invalid in variants:
        archive.write_bytes(invalid)
        with pytest.raises(AssertionError):
            archive_witness(archive, source)
