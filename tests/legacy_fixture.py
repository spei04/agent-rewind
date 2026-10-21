"""Test-only materialization of immutable, synthetic pre-migration history."""

import hashlib
import json
import sqlite3
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy_v0"


def read_manifest():
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text())


def canonical_bytes(value):
    # Deliberately independent from application serialization and migration code.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def materialize_legacy(destination, variant="known"):
    """Copy a frozen fixture into a new test directory; never mutate the source."""
    manifest = read_manifest()
    spec = manifest["variants"][variant]
    sql = (FIXTURE_ROOT / "baseline.sql").read_bytes()
    if sha256(sql) != manifest["baseline_sql_sha256"]:
        raise ValueError("Frozen legacy SQL checksum changed.")
    destination.mkdir(mode=0o700)
    database = destination / "metadata.sqlite"
    database.touch(mode=0o600)
    with sqlite3.connect(database) as connection:
        connection.executescript(sql.decode() + spec["sql"])
    object_root = destination / "objects"
    object_root.mkdir(mode=0o700)
    for source in (FIXTURE_ROOT / "objects").iterdir():
        target = object_root / source.name
        target.touch(mode=0o600)
        target.write_bytes(source.read_bytes())
    override = spec["object_override"]
    if override:
        data = (FIXTURE_ROOT / "variants" / override["file"]).read_bytes()
        if sha256(data) != override["ciphertext_sha256"]:
            raise ValueError("Frozen corruption fixture checksum changed.")
        (object_root / override["address"]).write_bytes(data)
    return database


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def schema_shape(connection):
    """Include column order, nullability, PK order and unique index columns."""
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    return {
        table: {
            "columns": [
                list(row) for row in connection.execute(f"PRAGMA table_info({_quoted(table)})")
            ],
            "unique_indexes": sorted(
                [
                    column[2]
                    for column in connection.execute(f"PRAGMA index_info({_quoted(row[1])})")
                ]
                for row in connection.execute(f"PRAGMA index_list({_quoted(table)})")
                if row[2]
            ),
        }
        for table in tables
    }


def assert_preserved_rows(database):
    """Compare original rows with literal expectations, allowing additive tables."""
    manifest = read_manifest()
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        for table, expected in manifest["expected_rows"].items():
            order = "run_id, step" if table == "events" else "id"
            actual = [
                dict(row)
                for row in connection.execute(f"SELECT * FROM {_quoted(table)} ORDER BY {order}")
            ]
            if table == "jobs" and actual and "payload_version" in actual[0]:
                # The only accepted additive job fields; never discard arbitrary
                # unknown columns or weaken the independent historical oracle.
                extra = {"payload_version", "execution_config_ref", "execution_config_digest"}
                for row in actual:
                    assert set(row) == set(expected[0]) | extra
                    assert (
                        row["payload_version"],
                        row["execution_config_ref"],
                        row["execution_config_digest"],
                    ) == (1, None, None)
                    for field in extra:
                        del row[field]
            if table == "records":
                for row in actual:
                    row["data"] = json.loads(row["data"])
            assert actual == expected, f"Historical {table} values changed."
            assert [sha256(canonical_bytes(row)) for row in actual] == manifest["row_sha256"][
                table
            ], f"Historical {table} checksums changed."
