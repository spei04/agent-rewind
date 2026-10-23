"""Independent empty-baseline and bounded-query controls without a database."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_restore_authority import AUTHORITY_SQL, typed
from ledger_restore_empty_target import (
    EMPTY_SQL,
    assert_empty_target,
    bounded_rows,
    observe_empty_target,
)

SOURCE = {
    "roles": [
        {"name": "source_app", "rolsuper": False, "rolinherit": False},
        {"name": "source_owner", "rolsuper": False, "rolinherit": True},
    ],
    "memberships": [{"role": "source_group", "member": "source_app", "grantor": "postgres"}],
}
ARGUMENTS = {"database": "target", "owner": "source_owner", "source_authority": SOURCE}


def empty_witness():
    schema = {
        "name": "public",
        "owner": "pg_database_owner",
        "acl": "{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}",
    }
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
    return {
        "authority": {
            "database": [{"name": "target", "owner": "source_owner", "acl": None}],
            "schemas": [schema],
            "relations": [],
            "functions": [],
            "triggers": [],
            "grants": grants,
            **deepcopy(SOURCE),
        },
        "inventory": {
            "namespaces": [{"oid": 2200, **schema}],
            "relations": [],
            "routines": [],
            "types": [],
            "constraints": [],
            "triggers": [],
            "default_acls": [],
            "extensions": [
                {
                    "oid": 13510,
                    "name": "plpgsql",
                    "owner": "postgres",
                    "schema": "pg_catalog",
                    "version": "1.0",
                    "relocatable": False,
                    "configuration": None,
                    "conditions": None,
                }
            ],
        },
    }


def test_explicit_default_baseline_is_accepted_without_mutating_expectations():
    value = empty_witness()
    retained = deepcopy(value)
    assert_empty_target(value, **ARGUMENTS)
    assert value == retained


@pytest.mark.parametrize(
    "family,row",
    [
        ("relations", {"kind": kind, "name": "unexpected"})
        for kind in ("r", "v", "m", "S", "i", "p", "f", "c")
    ]
    + [
        ("routines", {"name": "unexpected"}),
        ("types", {"name": "unexpected"}),
        ("constraints", {"name": "unexpected"}),
        ("triggers", {"name": "unexpected"}),
        ("default_acls", {"acl": "{other=r/owner}"}),
        ("namespaces", {"name": "other", "oid": 2201}),
        ("extensions", {"name": "other", "oid": 20000}),
    ],
)
def test_equal_but_nonempty_before_and_after_can_never_pass(family, row):
    value = empty_witness()
    value["inventory"][family].append(row)
    assert typed(value) == typed(deepcopy(value))
    with pytest.raises(AssertionError):
        assert_empty_target(value, **ARGUMENTS)


@pytest.mark.parametrize(
    "family,field,value",
    [
        ("database", "owner", "other"),
        ("database", "name", "other"),
        ("database", "acl", "{other=C/source_owner}"),
        ("schemas", "owner", "other"),
        ("schemas", "acl", None),
        ("grants", "grantor", "other"),
        ("grants", "grantable", 0),
        ("grants", "privilege", "CREATE"),
        ("roles", "rolsuper", True),
        ("roles", "rolsuper", 0),
        ("memberships", "grantor", "other"),
    ],
)
def test_raw_authority_and_native_type_changes_fail(family, field, value):
    observation = empty_witness()
    observation["authority"][family][0][field] = value
    with pytest.raises(AssertionError):
        assert_empty_target(observation, **ARGUMENTS)


@pytest.mark.parametrize("family", ["relations", "functions", "triggers"])
def test_authority_objects_cannot_hide_behind_an_empty_inventory(family):
    value = empty_witness()
    value["authority"][family] = [{"name": "unexpected"}]
    with pytest.raises(AssertionError):
        assert_empty_target(value, **ARGUMENTS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("oid", True),
        ("oid", 0),
        ("name", "other"),
        ("owner", "source_owner"),
        ("schema", "public"),
        ("version", "2.0"),
        ("relocatable", 0),
        ("configuration", []),
        ("conditions", []),
    ],
)
def test_only_declared_default_extension_identity_is_accepted(field, value):
    observation = empty_witness()
    observation["inventory"]["extensions"][0][field] = value
    with pytest.raises(AssertionError):
        assert_empty_target(observation, **ARGUMENTS)


@pytest.mark.parametrize("family", ["namespaces", "extensions"])
@pytest.mark.parametrize("change", ["missing", "extra-field", "duplicate", "tuple"])
def test_baseline_catalog_shape_is_exact(family, change):
    value = empty_witness()
    rows = value["inventory"][family]
    if change == "missing":
        rows.clear()
    elif change == "extra-field":
        rows[0]["unexpected"] = None
    elif change == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        value["inventory"][family] = tuple(rows)
    with pytest.raises(AssertionError):
        assert_empty_target(value, **ARGUMENTS)


class Connection:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return SimpleNamespace(mappings=lambda: self.rows)


@pytest.mark.parametrize("count", [0, 128, 129])
def test_catalog_overflow_is_detected_by_the_actual_bounded_query(count):
    connection = Connection([{"oid": number} for number in range(count)])
    if count <= 128:
        assert len(bounded_rows(connection, "SELECT oid FROM pg_class ORDER BY oid", {})) == count
    else:
        with pytest.raises(AssertionError, match="row bound"):
            bounded_rows(connection, "SELECT oid FROM pg_class ORDER BY oid", {})
    assert connection.calls == [("SELECT oid FROM pg_class ORDER BY oid LIMIT 129", {})]


def test_actual_capture_uses_fixed_queries_local_limits_fresh_scope_and_final_drain(monkeypatch):
    import ledger_restore_empty_target as module

    events = []
    connection = Connection([])
    connection.exec_driver_sql = lambda sql: events.append(sql)

    class Scope:
        def __enter__(self):
            events.append("begin")
            return connection

        def __exit__(self, *args):
            events.append("closed")

    fixture = SimpleNamespace(case=SimpleNamespace(engine=SimpleNamespace(begin=lambda: Scope())))
    pg = {name + "_role": name for name in ("owner", "app", "group")}
    monkeypatch.setattr(module, "drain", lambda value: events.append(("drain", value)))
    saved = []
    monkeypatch.setattr(module, "save", lambda *args: saved.append(args))
    result = observe_empty_target(fixture, pg, "directory", "before", object())
    assert len(connection.calls) == 16 == len(AUTHORITY_SQL) + len(EMPTY_SQL)
    assert all(query.endswith(" LIMIT 129") for query, _ in connection.calls)
    assert events[:3] == [
        "begin",
        "SET LOCAL statement_timeout='2000ms'",
        "SET LOCAL lock_timeout='1000ms'",
    ]
    assert events[-2:] == ["closed", ("drain", pg)]
    assert saved[0][2] == typed(result)
