"""Exact state and failure boundaries for SQLite-only synthetic history batching."""

import json
import shutil
import sqlite3
from contextlib import closing
from copy import deepcopy
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import ledger_capacity_fixture as capacity
import pytest
from ledger_fixture import canonical_bytes, digest, identifier
from ledger_provisioning_fixture import snapshot
from ledger_reader_fixture import ReaderFixture, append_provision, complete_ar6, seed_ar7
from sqlalchemy import create_engine

from agent_rewind.artifact_metadata import configure_artifact_engine
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.schema import LEDGER

STATE_FIELDS = (
    "original_rows",
    "adoption",
    "previous_progress",
    "expected",
    "manifest",
    "cursor",
    "opening",
)


@pytest.fixture
def seeded(tmp_path):
    case = complete_ar6(tmp_path / "reference.sqlite", legacy=True)
    try:
        seed_ar7(case)
        yield case
    finally:
        case.dispose()


def batches(case, count):
    template = case.manifest["accounts"][0]
    origin = datetime(2030, 1, 1, tzinfo=UTC)
    offset = 0
    result = []
    for size in range(1, count + 1):
        rows = []
        for _ in range(size):
            start = origin + timedelta(days=offset)
            rows.append(
                {
                    **template,
                    "id": identifier(70_000_000 + offset),
                    "period_start": start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "period_end": (start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                }
            )
            offset += 1
        result.append(rows)
    return result


def connection_settings(engine):
    with engine.connect() as connection:
        return tuple(
            connection.exec_driver_sql("PRAGMA " + name).scalar_one()
            for name in ("foreign_keys", "query_only", "busy_timeout")
        )


def clone_case(case, path):
    """A per-test native backup, never a cached migration/readiness result."""
    assert case.engine.pool.checkedout() == 0
    path.parent.mkdir()
    with (
        closing(sqlite3.connect(f"file:{case.path}?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(path)) as target,
    ):
        source.backup(target)
    shutil.copytree(case.path.parent / "objects", path.parent / "objects")
    engine = create_engine(case.engine.url.set(database=str(path)))
    try:
        configure_artifact_engine(engine)
        values = {
            field.name: deepcopy(getattr(case, field.name))
            for field in fields(case)
            if field.name not in {"path", "engine"}
        }
        clone = ReaderFixture(path=path, engine=engine, **values)
        assert connection_settings(engine) == connection_settings(case.engine)
        assert type(engine.pool) is type(case.engine.pool)
        assert snapshot(path) == snapshot(case.path)
        assert capacity.object_hashes(clone) == capacity.object_hashes(case)
        for name in STATE_FIELDS:
            assert getattr(clone, name) == getattr(case, name)
            assert getattr(clone, name) is not getattr(case, name)
        return clone
    except BaseException:
        engine.dispose()
        raise


def assert_small_chain(case, count):
    """Check native bytes and joins independently of the shared receipt builder."""
    state = snapshot(case.path)
    account_table = state["tables"]["budget_accounts"]
    accounts = {
        row["id"]: row
        for values in account_table["rows"]
        for row in [dict(zip(account_table["columns"], values, strict=True))]
    }
    progress = state["tables"]["migration_progress"]
    cursors = []
    for values in progress["rows"]:
        row = dict(zip(progress["columns"], values, strict=True))
        if row["revision"] == LEDGER and row["phase"] != "ledger_opening":
            value = json.loads(row["cursor"])
            assert row["cursor"].encode() == canonical_bytes(value)
            assert row["source_digest"] == value["manifest"]["source_digest"]
            assert row["rows_verified"] == value["account_count"]
            assert row["status"] == "complete"
            cursors.append(value)
    cursors.sort(key=lambda value: value["sequence"])
    assert [value["sequence"] for value in cursors] == list(range(count + 1))
    previous = None
    seen = set()
    for value in cursors:
        raw = value["manifest"]
        assert value["parent_manifest_digest"] == raw["parent_manifest_digest"] == previous
        assert value["manifest_digest"] == digest(raw)
        assert value["database_role"] is None
        assert value["account_count"] == len(raw["accounts"])
        projection = []
        for account in raw["accounts"]:
            assert account["id"] not in seen
            seen.add(account["id"])
            actual = accounts[account["id"]]
            assert {key: actual[key] for key in account} == account
            assert actual["held_microusd"] == actual["opening_held_microusd"]
            assert actual["accounted_microusd"] == 0
            projection.append({**account, "opening_held_microusd": actual["opening_held_microusd"]})
        assert value["account_projection_digest"] == digest(projection)
        previous = value["manifest_digest"]
    assert seen == set(accounts)
    assert case.expected["head"]["manifest_digest"] == previous
    assert case.expected["manifest_count"] == count + 1
    assert case.expected["account_count"] == len(accounts)


@pytest.mark.parametrize("count", [1, 3])
def test_sqlite_capacity_batch_matches_committed_reference(seeded, tmp_path, monkeypatch, count):
    clone = clone_case(seeded, tmp_path / "candidate" / "state.sqlite")
    try:
        rows = batches(seeded, count)
        original = deepcopy({name: getattr(seeded, name) for name in STATE_FIELDS})
        ciphertext = capacity.object_hashes(seeded)
        settings = connection_settings(seeded.engine)
        with seeded.engine.connect() as connection:
            before = source_digest(connection)
        for accounts in rows:
            append_provision(seeded, accounts)
        observed = []
        real_digest = capacity.source_digest

        def observe_digest(connection):
            raw = connection.connection.driver_connection
            value = real_digest(connection)
            observed.append((id(raw), raw.in_transaction, value))
            return value

        monkeypatch.setattr(capacity, "source_digest", observe_digest)
        capacity._append_sqlite_capacity(clone, deepcopy(rows))
        assert len(observed) == 2
        assert observed[0] == observed[1] and observed[0][1:] == (True, before)
        assert snapshot(clone.path) == snapshot(seeded.path)
        for name in STATE_FIELDS:
            assert getattr(clone, name) == getattr(seeded, name)
        for name in ("original_rows", "adoption", "previous_progress", "opening"):
            assert getattr(clone, name) == original[name]
        assert capacity.object_hashes(clone) == capacity.object_hashes(seeded) == ciphertext
        assert connection_settings(clone.engine) == connection_settings(seeded.engine) == settings
        assert seeded.engine.pool.checkedout() == clone.engine.pool.checkedout() == 0
        with seeded.engine.connect() as connection:
            assert source_digest(connection) == before
        assert_small_chain(seeded, count)
        assert_small_chain(clone, count)
    finally:
        clone.dispose()


@pytest.mark.parametrize("failure", ["insert", "source-change", "commit-before"])
def test_sqlite_capacity_batch_rolls_back_without_publishing(seeded, monkeypatch, failure):
    before = snapshot(seeded.path)
    originals = {name: getattr(seeded, name) for name in STATE_FIELDS}
    values = deepcopy(originals)
    settings = connection_settings(seeded.engine)
    error = RuntimeError("fixture sentinel")
    real_insert = capacity._insert_provision
    real_digest = capacity.source_digest
    writes = []
    reads = []

    def observe_digest(connection):
        value = real_digest(connection)
        reads.append((connection.connection.driver_connection.in_transaction, value))
        return value

    def insert(connection, raw, cursor):
        real_insert(connection, raw, cursor)
        writes.append(cursor["sequence"])
        if len(writes) == 2:
            if failure == "insert":
                raise error
            if failure == "source-change":
                result = connection.exec_driver_sql(
                    "UPDATE jobs SET budget=budget+1 "
                    "WHERE id=(SELECT id FROM jobs ORDER BY id LIMIT 1)"
                )
                assert result.rowcount == 1

    def commit(raw):
        assert raw.in_transaction
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(capacity, "_insert_provision", insert)
        patch.setattr(capacity, "source_digest", observe_digest)
        if failure == "commit-before":
            patch.setattr(seeded.engine.dialect, "do_commit", commit)
        with pytest.raises(
            AssertionError if failure == "source-change" else RuntimeError
        ) as caught:
            capacity._append_sqlite_capacity(seeded, batches(seeded, 3))
        if failure != "source-change":
            assert caught.value is error
    assert writes == ([1, 2] if failure == "insert" else [1, 2, 3])
    assert all(active for active, _ in reads)
    assert len(reads) == (1 if failure == "insert" else 2)
    if failure == "source-change":
        assert reads[0][1] != reads[1][1]
    elif failure == "commit-before":
        assert reads[0] == reads[1]
    assert snapshot(seeded.path) == before
    for name, original in originals.items():
        assert getattr(seeded, name) is original
        assert getattr(seeded, name) == values[name]
    assert connection_settings(seeded.engine) == settings
    assert seeded.engine.pool.checkedout() == 0


def test_sqlite_capacity_batch_refuses_native_trigger_before_seed(seeded, monkeypatch):
    with seeded.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER capacity_source_change AFTER INSERT ON budget_accounts "
            "BEGIN UPDATE jobs SET budget=budget+1; END"
        )
    before = snapshot(seeded.path)
    originals = {name: getattr(seeded, name) for name in STATE_FIELDS}
    calls = []
    real_digest = capacity.source_digest

    def observe_digest(connection):
        calls.append(True)
        return real_digest(connection)

    monkeypatch.setattr(capacity, "source_digest", observe_digest)
    with pytest.raises(AssertionError):
        capacity._append_sqlite_capacity(seeded, batches(seeded, 3))
    assert calls == []
    assert snapshot(seeded.path) == before
    assert all(getattr(seeded, name) is value for name, value in originals.items())
    assert seeded.engine.pool.checkedout() == 0
