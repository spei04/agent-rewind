"""Literal preservation, bounded initial batches and rollback of projection progress."""

import json
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from legacy_fixture import assert_preserved_rows, materialize_legacy, read_manifest, sha256
from sqlalchemy import create_engine, text
from test_migrations import mapping_for
from test_ownership import FRESH

from agent_rewind.migrations import projection_service, service
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.migrations.schema import PROJECTION, MigrationRefused
from agent_rewind.projection_evidence import FrozenLegacySource
from agent_rewind.projection_rows import read_index


@pytest.fixture
def legacy(tmp_path):
    path = materialize_legacy(tmp_path / "legacy")
    engine = create_engine(f"sqlite:///{path}")
    service.adopt(engine, mapping_for(engine), "b" * 64, "d" * 64)
    initialize_ownership(engine)
    initialize_artifacts(engine)
    source = FrozenLegacySource(
        path.parent, Fernet(read_manifest()["synthetic_fernet_key"].encode())
    )
    yield path, engine, source
    engine.dispose()


def state(engine):
    with engine.connect() as connection:
        row = dict(
            connection.execute(
                text("SELECT * FROM migration_progress WHERE revision=:revision"),
                {"revision": PROJECTION},
            )
            .mappings()
            .one()
        )
        row["cursor"] = json.loads(row["cursor"])
        return row


def rows(engine):
    with engine.connect() as connection:
        return read_index(connection, limit=10001)


def counters(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT id,run_sequence FROM projects ORDER BY id")).all()


def preserved(path):
    assert_preserved_rows(path)
    for entry in read_manifest()["objects"].values():
        assert (
            sha256((path.parent / "objects" / entry["address"]).read_bytes())
            == entry["ciphertext_sha256"]
        )


def test_literal_history_preserved_after_every_batch_and_exact_resume(legacy):
    path, engine, source = legacy
    initial = initialize_projection(engine)
    assert initial["projection_rows_verified"] == 0
    assert initial["projection_status"] == "running"
    assert state(engine)["cursor"]["evidence_digest"] is None
    preserved(path)
    first = backfill_run_index(engine, source, batch_size=1)
    assert first["projection_rows_verified"] == 1
    first_row = rows(engine)[0]
    assert first_row["run_id"] == "1" * 32 and first_row["published_seq"] == 1
    preserved(path)
    engine.dispose()
    second = backfill_run_index(engine, source, batch_size=1)
    assert second["projection_status"] == "complete"
    assert rows(engine)[0] == first_row
    for index, row in enumerate(rows(engine), 1):
        assert row["status"] == "complete" and row["branchable"]
        assert (
            row["created_at"] == datetime(2023, 11, 14, 22, 13, 20, 125000, tzinfo=UTC).isoformat()
        )
        assert row["event_head"] == read_manifest()["runs"][row["run_id"]]["head"]
        assert row["published_seq"] == index
    frozen = state(engine)
    assert backfill_run_index(engine, source, batch_size=1) == second
    assert state(engine) == frozen
    preserved(path)
    assert runtime_schema_compatibility(engine).code == "migration_only"


def test_schema_only_empty_install_needs_no_artifact_reader(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.sqlite'}")
    try:
        service.install(engine, FRESH["installation_key"])
        initialize_ownership(engine, FRESH)
        initialize_artifacts(engine)
        result = initialize_projection(engine)
        assert result["projection_status"] == "complete"
        assert result["projection_rows_total"] == 0
        before = state(engine)
        assert initialize_projection(engine) == result
        assert (
            backfill_run_index(engine, lambda *_: pytest.fail("empty cohort read bytes")) == result
        )
        assert state(engine) == before
        assert runtime_schema_compatibility(engine).code == "migration_only"
    finally:
        engine.dispose()


def test_progress_failure_rolls_back_projection_counter_and_cursor(legacy, monkeypatch):
    path, engine, source = legacy
    initialize_projection(engine)
    before = state(engine), counters(engine)
    original = projection_service._write_progress

    def fail(connection, next_state, *, insert):
        assert len(read_index(connection, limit=3)) == 1
        assert connection.execute(text("SELECT run_sequence FROM projects")).scalar_one() == 1
        raise RuntimeError("synthetic process boundary")

    monkeypatch.setattr(projection_service, "_write_progress", fail)
    with pytest.raises(RuntimeError, match="synthetic process boundary"):
        backfill_run_index(engine, source, batch_size=1)
    assert rows(engine) == []
    assert (state(engine), counters(engine)) == before
    preserved(path)
    monkeypatch.setattr(projection_service, "_write_progress", original)
    assert backfill_run_index(engine, source, batch_size=1)["projection_rows_verified"] == 1
    assert rows(engine)[0]["published_seq"] == 1


@pytest.mark.parametrize("mutation", ["created", "scope", "late"])
def test_source_drift_never_skips_or_rewrites_frozen_prefix(legacy, mutation):
    path, engine, source = legacy
    initialize_projection(engine)
    backfill_run_index(engine, source, batch_size=1)
    before = rows(engine), state(engine), counters(engine)
    with engine.begin() as connection:
        if mutation == "created":
            connection.execute(
                text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": "2" * 32}
            )
        elif mutation == "scope":
            connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": "2" * 32}
            )
        else:
            connection.execute(
                text(
                    "INSERT INTO records SELECT :id,kind,created-10,data FROM records WHERE id=:old"
                ),
                {"id": "0" * 32, "old": "1" * 32},
            )
            connection.execute(
                text("INSERT INTO resource_scopes SELECT 'run',:id,id FROM projects"),
                {"id": "0" * 32},
            )
    with pytest.raises(MigrationRefused, match="projection_(cohort_changed|source_invalid)"):
        backfill_run_index(engine, lambda *_: pytest.fail("changed cohort reached byte reader"))
    assert (rows(engine), state(engine), counters(engine)) == before


def test_change_during_reader_cannot_commit_stale_proof(legacy):
    _, engine, source = legacy
    initialize_projection(engine)
    before = state(engine), counters(engine)
    changed = False

    def reader(*args):
        nonlocal changed
        assert engine.pool.checkedout() == 0
        if not changed:
            changed = True
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": "2" * 32}
                )
        return source(*args)

    with pytest.raises(MigrationRefused, match="projection_cohort_changed"):
        backfill_run_index(engine, reader)
    assert rows(engine) == [] and (state(engine), counters(engine)) == before


def test_missing_terminal_evidence_never_commits_branchability(legacy):
    path, engine, source = legacy
    initialize_projection(engine)
    manifest = read_manifest()
    run = manifest["runs"]["1" * 32]
    with engine.connect() as connection:
        data = json.loads(
            connection.execute(
                text("SELECT data FROM records WHERE id=:id"), {"id": "1" * 32}
            ).scalar_one()
        )
    assert run["head"] == data["head"]
    (path.parent / "objects" / data["evaluation_ref"]).unlink()
    before = state(engine), counters(engine)
    with pytest.raises(MigrationRefused, match="projection_evidence_missing"):
        backfill_run_index(engine, source)
    assert rows(engine) == [] and (state(engine), counters(engine)) == before
