"""Preservation oracles are frozen literals, not outputs of the current engine."""

import json
import sqlite3

import pytest
from cryptography.fernet import Fernet, InvalidToken
from legacy_fixture import (
    FIXTURE_ROOT,
    assert_preserved_rows,
    canonical_bytes,
    materialize_legacy,
    read_manifest,
    schema_shape,
    sha256,
)
from pydantic import SecretStr

from agent_rewind.artifacts import Artifacts
from agent_rewind.database import Database
from agent_rewind.engine import read_events
from agent_rewind.models import BranchRequest, TaskSpec


def test_frozen_sql_and_encrypted_objects_have_independent_checksums():
    manifest = read_manifest()
    assert manifest["synthetic_only"] is True
    assert sha256((FIXTURE_ROOT / "baseline.sql").read_bytes()) == manifest["baseline_sql_sha256"]
    cipher = Fernet(manifest["synthetic_fernet_key"].encode())
    expected_addresses = {entry["address"] for entry in manifest["objects"].values()}
    assert {path.name for path in (FIXTURE_ROOT / "objects").iterdir()} == expected_addresses
    for entry in manifest["objects"].values():
        token = (FIXTURE_ROOT / "objects" / entry["address"]).read_bytes()
        assert sha256(token) == entry["ciphertext_sha256"]
        plaintext = cipher.decrypt(token)
        assert len(plaintext) == entry["plaintext_bytes"]
        assert sha256(plaintext) == entry["address"]
        if entry["format"] == "json":
            assert canonical_bytes(json.loads(plaintext)) == plaintext


def test_known_baseline_preserves_all_rows_timestamps_and_reservations(tmp_path):
    database = materialize_legacy(tmp_path / "known")
    assert_preserved_rows(database)
    manifest = read_manifest()
    with sqlite3.connect(database) as connection:
        assert schema_shape(connection) == manifest["schema"]
        assert connection.execute("SELECT SUM(reserved) FROM jobs").fetchone()[0] == 245000
        assert manifest["reservation_total_microusd"] == 245000
        assert connection.execute("SELECT COUNT(DISTINCT created) FROM records").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM api_keys WHERE expires < 1700000000"
            ).fetchone()[0]
            == 2
        )
    assert database.stat().st_mode & 0o077 == 0
    assert all(
        path.stat().st_mode & 0o077 == 0 for path in database.parent.joinpath("objects").iterdir()
    )


@pytest.mark.parametrize("variant", read_manifest()["variants"])
def test_variants_have_explicit_schema_and_corruption_identity(tmp_path, variant):
    manifest = read_manifest()
    database = materialize_legacy(tmp_path / variant, variant)
    spec = manifest["variants"][variant]
    with sqlite3.connect(database) as connection:
        shape = schema_shape(connection)
    assert sorted(shape) == spec["tables"]
    assert sha256(canonical_bytes(shape)) == spec["schema_sha256"]
    baseline_hash = manifest["variants"]["known"]["schema_sha256"]
    assert (spec["schema_sha256"] != baseline_hash) == (
        variant in {"unknown_schema", "partial_schema"}
    )
    if spec["object_override"]:
        override = spec["object_override"]
        assert (
            sha256((database.parent / "objects" / override["address"]).read_bytes())
            == override["ciphertext_sha256"]
        )
    classifications = [value["classification"] for value in manifest["variants"].values()]
    assert len(classifications) == len(set(classifications))


def test_parent_branch_chain_and_workspace_preserve_frozen_identity(tmp_path, settings):
    database_path = materialize_legacy(tmp_path / "history")
    manifest = read_manifest()
    settings.storage = "local"
    settings.data_dir = database_path.parent
    settings.database_url = f"sqlite:///{database_path}"
    settings.encryption_key = SecretStr(manifest["synthetic_fernet_key"])
    db, artifacts = Database(settings), Artifacts(settings)
    try:
        for run_id, expected in manifest["runs"].items():
            run = db.get(run_id, "run")
            assert run["created"] == expected["created"]
            assert run["head"] == expected["head"]
            history = read_events(db, artifacts, run_id)
            assert len(history) == expected["steps"]
            assert [event["hash"] for event in history] == expected["expanded_event_hashes"]
            previous = None
            for event in history:
                assert event["previous"] == previous
                body = {key: value for key, value in event.items() if key != "hash"}
                assert sha256(canonical_bytes(body)) == event["hash"]
                previous = event["hash"]
                checkpoint = artifacts.json(event["checkpoint"])
                assert checkpoint["next_step"] == event["step"]
                workspace = artifacts.workspace(checkpoint["workspace"], 1024)
                assert workspace["empty"].kind == "directory"
                assert workspace["empty"].mode == 0o755
                assert workspace["empty"].mtime == 1699999999
            assert previous == expected["head"]
            task = artifacts.json(run["task_ref"])
            TaskSpec.model_validate(task)
            assert sha256(canonical_bytes(task)) == run["task_digest"]
            assert artifacts.json(run["evaluation_ref"])["exit_code"] == (
                0 if run["success"] else 1
            )
        for job in db.list_jobs():
            payload = artifacts.json(job["payload"])
            (BranchRequest if job["kind"] == "branch" else TaskSpec).model_validate(payload)
            if job["result"]:
                assert artifacts.json(job["result"])["run_id"] in manifest["runs"]
        assert_preserved_rows(database_path)
    finally:
        db.engine.dispose()


@pytest.mark.parametrize(
    "variant,error,match",
    [
        ("corrupt_ciphertext", InvalidToken, None),
        ("corrupt_address", ValueError, "Artifact integrity check failed"),
    ],
)
def test_corruption_is_rejected_without_changing_known_good_fixture(
    tmp_path, settings, variant, error, match
):
    manifest = read_manifest()
    known = materialize_legacy(tmp_path / "known")
    broken = materialize_legacy(tmp_path / variant, variant)
    address = manifest["variants"][variant]["object_override"]["address"]
    original = (known.parent / "objects" / address).read_bytes()
    settings.storage = "local"
    settings.data_dir = broken.parent
    settings.encryption_key = SecretStr(manifest["synthetic_fernet_key"])
    with pytest.raises(error, match=match):
        Artifacts(settings).get(address)
    assert (known.parent / "objects" / address).read_bytes() == original
    assert (FIXTURE_ROOT / "objects" / address).read_bytes() == original
    settings.data_dir = known.parent
    assert json.loads(Artifacts(settings).get(address))["step"] == 1
    assert_preserved_rows(known)
    assert_preserved_rows(broken)


@pytest.mark.parametrize(
    "sql,table",
    [
        ("UPDATE records SET created = created + 1", "records"),
        (
            "UPDATE records SET id = 'changed' WHERE id = '11111111111111111111111111111111'",
            "records",
        ),
        ("UPDATE events SET hash = 'changed' WHERE step = 1", "events"),
        ("UPDATE jobs SET reserved = reserved + 1", "jobs"),
    ],
)
def test_preservation_oracle_detects_identity_timestamp_hash_and_budget_edits(tmp_path, sql, table):
    database = materialize_legacy(tmp_path / "modified")
    with sqlite3.connect(database) as connection:
        connection.execute(sql)
    with pytest.raises(AssertionError, match=f"Historical {table} values changed"):
        assert_preserved_rows(database)


def test_materialization_refuses_existing_destination(tmp_path):
    database = materialize_legacy(tmp_path / "known")
    original = database.read_bytes()
    with pytest.raises(FileExistsError):
        materialize_legacy(database.parent, "corrupt_ciphertext")
    assert database.read_bytes() == original
