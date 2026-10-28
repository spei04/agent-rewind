"""Bounded raw restored-state witnesses; never invoke product catalog validation."""

import json
from copy import deepcopy
from datetime import UTC, datetime

from ledger_restore_authority import assert_same_authority, typed
from ledger_restore_interruption_raw import (
    MAX_SNAPSHOT,
    TABLES,
    encoded,
    observe_schema_only,
    structure,
)
from ledger_restore_postgres_fixture import save
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from test_run_projection_postgres import drain

MAX_ROWS = 1024
MAX_CELL = 65536
CURSOR_TEXT = "__cursor_text"
REVISION = "ar_0007_ledger"
FUNCTION = "ar7_ledger_constraint"
CURSOR_UPDATE = (
    "UPDATE public.migration_progress SET cursor=:cursor "
    "WHERE revision=:revision AND phase=:phase RETURNING revision,phase,cursor::text"
)
ACL_GRANT = "GRANT EXECUTE ON FUNCTION public.ar7_ledger_constraint() TO PUBLIC"


def source_columns(metadata):
    relations = metadata["inventory"]["relations"]
    assert tuple(row["name"] for row in relations if row["kind"] == "r") == TABLES
    columns = {}
    for table in TABLES:
        rows = [row for row in metadata["inventory"]["columns"] if row["relation"] == table]
        assert 1 <= len(rows) <= 32
        assert [row["position"] for row in rows] == list(range(1, len(rows) + 1))
        names = tuple(row["name"] for row in rows)
        assert all(type(name) is str and name and len(name.encode()) <= 63 for name in names)
        assert len(set(names)) == len(names) and CURSOR_TEXT not in names
        columns[table] = names
    return columns


class RawRows:
    """Charge compact typed JSON, including metadata/envelopes, before retention."""

    def __init__(self, metadata, columns):
        assert set(columns) == set(TABLES)
        self.value = {
            "metadata": metadata,
            "tables": {table: {"columns": columns[table], "rows": []} for table in TABLES},
        }
        self.bytes = len(encoded(self.value))
        assert self.bytes <= MAX_SNAPSHOT, "corrupt-state snapshot retention bound"

    def append(self, table, row):
        rows = self.value["tables"][table]["rows"]
        assert len(rows) < MAX_ROWS, "corrupt-state row bound"
        names = (*self.value["tables"][table]["columns"],)
        if table == "migration_progress":
            names += (CURSOR_TEXT,)
        assert tuple(row) == names, "corrupt-state row columns"
        assert all(len(encoded(cell)) <= MAX_CELL for cell in row.values()), "raw cell bound"
        size = self.bytes + len(encoded(row)) + bool(rows)
        assert size <= MAX_SNAPSHOT, "corrupt-state snapshot retention bound"
        rows.append(row)
        self.bytes = size

    def finish(self):
        for table, value in self.value["tables"].items():
            value["rows"].sort(key=encoded)
            assert bool(value["rows"]) is self.value["metadata"]["rows_present"][table]
        assert len(encoded(self.value)) == self.bytes <= MAX_SNAPSHOT
        return self.value


def capture_raw(fixture, pg, directory, name, record_property, *, columns=None):
    # This observer reads raw metadata, including invalid ACLs, without catalog().
    metadata = observe_schema_only(fixture, pg, directory, name + "-schema", record_property)
    observed = source_columns(metadata)
    if columns is None:
        columns = observed  # Only the valid source establishes the inventory.
    assert typed(observed) == typed(columns), "source-defined column inventory differs"
    budget = RawRows(metadata, columns)
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            quote = connection.dialect.identifier_preparer.quote_identifier
            for table in TABLES:
                projection = ",".join(quote(name) for name in columns[table])
                if table == "migration_progress":
                    projection += ",cursor::text AS " + quote(CURSOR_TEXT)
                query = (
                    "SELECT "
                    + projection
                    + " FROM public."
                    + quote(table)
                    + " LIMIT "
                    + str(MAX_ROWS + 1)
                )
                result = connection.exec_driver_sql(query)
                for row in result.mappings():
                    budget.append(table, dict(row))
    finally:
        drain(pg)
    value = budget.finish()
    save(directory, name, typed(value), record_property)
    return value


def assert_restored_raw(source, target):
    assert set(source) == set(target) == {"metadata", "tables"}
    assert_same_authority(source["metadata"]["authority"], target["metadata"]["authority"])
    assert structure(source["metadata"]["inventory"]) == structure(target["metadata"]["inventory"])
    assert typed(source["metadata"]["rows_present"]) == typed(target["metadata"]["rows_present"])
    assert typed(source["tables"]) == typed(target["tables"])


def selected_progress(value, phase):
    rows = value["tables"]["migration_progress"]["rows"]
    selected = [row for row in rows if row["revision"] == REVISION and row["phase"] == phase]
    assert len(selected) == 1, "one original M1 progress row required"
    row = selected[0]
    assert type(row["cursor"]) is dict and type(row[CURSOR_TEXT]) is str
    assert typed(json.loads(row[CURSOR_TEXT])) == typed(row["cursor"])
    assert type(row["cursor"]["sequence"]) is int and row["cursor"]["sequence"] == 1
    assert row["cursor"]["manifest"]["operation"] == "provision"
    assert phase == "ledger_manifest_" + row["cursor"]["manifest"]["manifest_id"]
    return row


def historical_row(value, phase):
    rows = value["tables"]["migration_progress"]["rows"]
    selected = [row for row in rows if row["revision"] == REVISION and row["phase"] == phase]
    assert len(selected) == 1
    result = deepcopy(selected[0])
    text_value = result.pop(CURSOR_TEXT)
    assert type(text_value) is str and typed(json.loads(text_value)) == typed(result["cursor"])
    result["cursor"] = text_value
    observed = result["updated_at"]
    assert type(observed) is datetime and observed.utcoffset() is not None
    # H60 emits six-digit UTC text, then _read restores an aware UTC datetime
    # before validate_progress_row. Only this expected-read copy changes zone.
    result["updated_at"] = observed.astimezone(UTC)
    assert set(result) == {
        "revision",
        "phase",
        "source_digest",
        "cursor",
        "rows_verified",
        "status",
        "updated_at",
    }
    return result


def cursor_payload(value, phase):
    payload = deepcopy(selected_progress(value, phase)["cursor"])
    payload["sequence"] = 0  # Valid JSON and scalar range, invalid provision cursor binding.
    return payload


def assert_cursor_delta(before, after, phase, payload, returned_text):
    expected = deepcopy(before)
    row = selected_progress(expected, phase)
    assert typed(payload) == typed(cursor_payload(before, phase))
    assert type(returned_text) is str and typed(json.loads(returned_text)) == typed(payload)
    row["cursor"], row[CURSOR_TEXT] = deepcopy(payload), returned_text
    expected["tables"]["migration_progress"]["rows"].sort(key=encoded)
    assert typed(after) == typed(expected), "unexpected cursor-corruption delta"


def assert_acl_delta(before, after, owner):
    expected = deepcopy(before)
    authority = expected["metadata"]["authority"]
    functions = authority["functions"]
    assert len(functions) == 1
    function = functions[0]
    assert function["name"] == FUNCTION and function["arguments"] == ""
    assert function["owner"] == owner and type(owner) is str
    assert owner.isascii() and owner.replace("_", "").isalnum()
    original_acl = "{" + owner + "=X/" + owner + "}"
    added_acl = "{" + owner + "=X/" + owner + ",=X/" + owner + "}"
    assert function["acl"] == original_acl
    function["acl"] = added_acl
    routines = expected["metadata"]["inventory"]["routines"]
    assert len(routines) == 1 and routines[0]["name"] == FUNCTION
    assert routines[0]["arguments"] == "" and routines[0]["owner"] == owner
    assert routines[0]["oid"] == function["oid"] and routines[0]["acl"] == original_acl
    routines[0]["acl"] = added_acl
    edge = {
        "kind": "function",
        "name": FUNCTION,
        "arguments": "",
        "grantor": owner,
        "grantee": "PUBLIC",
        "privilege": "EXECUTE",
        "grantable": False,
    }
    grants = authority["grants"]
    assert not any(row["kind"] == "function" and row["grantee"] == "PUBLIC" for row in grants)
    grants.append(edge)
    fields = ("kind", "name", "arguments", "grantor", "grantee", "privilege", "grantable")
    grants.sort(key=lambda row: tuple(row[field] for field in fields))
    assert typed(after) == typed(expected), "unexpected function-ACL corruption delta"


def mutate_target(fixture, pg, before, kind, phase):
    payload = cursor_payload(before, phase) if kind == "cursor" else None
    assert kind in ("cursor", "acl")
    try:
        with fixture.case.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='2000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            identity = tuple(
                connection.exec_driver_sql("SELECT current_user,current_database()").one()
            )
            assert identity == (pg["owner_role"], pg["owner"].url.database)
            if kind == "cursor":
                statement = text(CURSOR_UPDATE).bindparams(bindparam("cursor", type_=JSONB))
                rows = connection.execute(
                    statement, {"cursor": payload, "revision": REVISION, "phase": phase}
                ).all()
                assert len(rows) == 1 and tuple(rows[0][:2]) == (REVISION, phase)
                returned = rows[0][2]
                assert type(returned) is str and typed(json.loads(returned)) == typed(payload)
            else:
                connection.exec_driver_sql(ACL_GRANT)
                returned = None
        # Successful context exit acknowledges this explicit test mutation commit.
        return {
            "kind": kind,
            "phase": phase,
            "identity": identity,
            "committed": True,
            "sql": CURSOR_UPDATE if kind == "cursor" else ACL_GRANT,
            "payload": payload,
            "returned_cursor_text": returned,
            "session_replication_role_changed": False,
        }
    finally:
        drain(pg)
