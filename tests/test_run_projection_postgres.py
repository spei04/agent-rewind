"""Real PostgreSQL initial projection preservation, interruption and recovery."""

import json
import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
import test_migration_recovery_postgres as recovery_tests
import test_migrations_postgres as migrations
from cryptography.fernet import Fernet
from legacy_fixture import FIXTURE_ROOT, read_manifest, sha256
from postgres_control import wait_for_database_drain
from sqlalchemy import text
from test_artifact_postgres import prepare_postgres
from test_migration_recovery_postgres import _dump, _restore_command, _run

from agent_rewind.migrations import projection_service, service
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection
from agent_rewind.migrations.schema import ARTIFACTS, PROJECTION, MigrationRefused, catalog
from agent_rewind.projection_evidence import FrozenLegacySource
from agent_rewind.projection_rows import read_index

pg = migrations.pg
recovery = recovery_tests.recovery
pytestmark = pytest.mark.skipif(
    not migrations.POSTGRES, reason="Opt-in synthetic PostgreSQL run projection"
)
PROFILE = (
    Path(__file__).parents[1] / "agent_rewind/migrations/profiles/postgresql16_projection.json"
)


@pytest.fixture
def projection_profile():
    assert PROFILE.is_file(), "Projection PostgreSQL catalog requires independent review"


def drain(pg, engine=None):
    wait_for_database_drain(pg["control"], (engine or pg["owner"]).url.database)


def source():
    return FrozenLegacySource(
        FIXTURE_ROOT, Fernet(read_manifest()["synthetic_fernet_key"].encode())
    )


def preserved(engine):
    migrations.assert_original_rows(engine)
    for spec in read_manifest()["objects"].values():
        assert (
            sha256((FIXTURE_ROOT / "objects" / spec["address"]).read_bytes())
            == (spec["ciphertext_sha256"])
        )


def snapshot(engine):
    with engine.connect() as connection:
        progress = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM migration_progress WHERE revision=:revision"),
                {"revision": PROJECTION},
            ).mappings()
        ]
        return (
            read_index(connection, limit=10001),
            progress,
            connection.exec_driver_sql("SELECT id,run_sequence FROM projects ORDER BY id").all(),
        )


def prepare_legacy(pg):
    migrations.load_legacy(pg["owner"])
    mapping = migrations.mapping_for(pg["owner"])
    drain(pg)
    service.adopt(pg["owner"], mapping, "b" * 64, "d" * 64)
    drain(pg)
    initialize_ownership(pg["owner"])
    drain(pg)
    initialize_artifacts(pg["owner"])
    drain(pg)


@pytest.fixture
def observed_reader(pg, monkeypatch):
    original = projection_service.readonly_source

    @contextmanager
    def observed(engine, budget):
        with original(engine, budget) as connection:
            yield connection
        # NullPool client close precedes observed server-side exit. This boundary
        # observes absence before the next exclusive phase; no product retry.
        drain(pg, engine)

    monkeypatch.setattr(projection_service, "readonly_source", observed)


@pytest.fixture
def projected_legacy(pg, projection_profile, observed_reader):
    prepare_legacy(pg)
    initialize_projection(pg["owner"])
    return pg


def test_postgres_projection_preserves_literal_history_and_exact_batch_resume(projected_legacy):
    pg = projected_legacy
    engine = pg["owner"]
    first = backfill_run_index(engine, source(), batch_size=1)
    assert first["projection_rows_verified"] == 1
    assert first["projection_status"] == "running"
    prefix = snapshot(engine)[0]
    assert prefix[0]["run_id"] == "1" * 32 and prefix[0]["published_seq"] == 1
    preserved(engine)
    engine.dispose()
    second = backfill_run_index(engine, source(), batch_size=1)
    assert second["projection_status"] == "complete"
    after = snapshot(engine)
    assert after[0][0] == prefix[0]
    assert [row["published_seq"] for row in after[0]] == [1, 2]
    assert all(row["branchable"] and row["status"] == "complete" for row in after[0])
    assert all(row["created_at"] == "2023-11-14T22:13:20.125000+00:00" for row in after[0])
    assert backfill_run_index(engine, source()) == second
    assert snapshot(engine) == after
    preserved(engine)
    assert runtime_schema_compatibility(engine).code == "migration_only"


def test_postgres_projection_progress_failure_rolls_back_all_three_outputs(
    projected_legacy, monkeypatch
):
    pg = projected_legacy
    before = snapshot(pg["owner"])
    original = projection_service._write_progress

    def stop(connection, state, *, insert):
        assert len(read_index(connection, limit=2)) == 1
        assert connection.exec_driver_sql("SELECT run_sequence FROM projects").scalar_one() == 1
        original(connection, state, insert=insert)
        raise RuntimeError("synthetic projection commit interruption")

    monkeypatch.setattr(projection_service, "_write_progress", stop)
    with pytest.raises(RuntimeError, match="synthetic projection commit interruption"):
        backfill_run_index(pg["owner"], source(), batch_size=1)
    assert snapshot(pg["owner"]) == before
    preserved(pg["owner"])
    monkeypatch.setattr(projection_service, "_write_progress", original)
    assert backfill_run_index(pg["owner"], source(), batch_size=1)["projection_rows_verified"] == 1


@pytest.mark.parametrize("after_commit", [False, True], ids=["before-commit", "after-commit"])
def test_postgres_projection_actual_process_death_resumes_exactly(projected_legacy, after_commit):
    pg = projected_legacy
    before = snapshot(pg["owner"])
    drain(pg)
    child = """
import os,signal
from pathlib import Path
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from agent_rewind.migrations import projection_service
from agent_rewind.projection_evidence import FrozenLegacySource
engine=create_engine(os.environ["SYNTHETIC_PROJECTION_DSN"])
reader=FrozenLegacySource(Path(os.environ["SYNTHETIC_OBJECT_ROOT"]),Fernet(os.environ["SYNTHETIC_OBJECT_KEY"].encode()))
if os.environ["AFTER_COMMIT"]=="0":
    original=projection_service._write_progress
    def interrupted(*args,**kwargs):
        original(*args,**kwargs)
        os.kill(os.getpid(),signal.SIGKILL)
    projection_service._write_progress=interrupted
projection_service.backfill_run_index(engine,reader,batch_size=1)
os.kill(os.getpid(),signal.SIGKILL)
"""
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        timeout=30,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "SYNTHETIC_PROJECTION_DSN": pg["owner"].url.render_as_string(hide_password=False),
            "SYNTHETIC_OBJECT_ROOT": str(FIXTURE_ROOT),
            "SYNTHETIC_OBJECT_KEY": read_manifest()["synthetic_fernet_key"],
            "AFTER_COMMIT": str(int(after_commit)),
        },
    )
    assert result.returncode == -signal.SIGKILL, "Child missed intended synthetic boundary"
    drain(pg)
    current = snapshot(pg["owner"])
    if after_commit:
        assert len(current[0]) == 1 and current[1][0]["rows_verified"] == 1
        assert current[2][0][1] == 1
    else:
        assert current == before
    preserved(pg["owner"])
    assert backfill_run_index(pg["owner"], source())["projection_status"] == "complete"
    assert [r["published_seq"] for r in snapshot(pg["owner"])[0]] == [1, 2]
    preserved(pg["owner"])


@pytest.mark.parametrize("change", ["created", "scope", "late"])
def test_postgres_projection_cohort_drift_keeps_committed_prefix(projected_legacy, change):
    pg = projected_legacy
    backfill_run_index(pg["owner"], source(), batch_size=1)
    before = snapshot(pg["owner"])
    with pg["owner"].begin() as connection:
        if change == "created":
            connection.execute(
                text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": "2" * 32}
            )
        elif change == "scope":
            connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": "2" * 32}
            )
        else:
            connection.execute(
                text(
                    "INSERT INTO records SELECT :new,kind,created-10,data "
                    "FROM records WHERE id=:old"
                ),
                {"new": "0" * 32, "old": "1" * 32},
            )
            connection.execute(
                text("INSERT INTO resource_scopes SELECT 'run',:id,id FROM projects"),
                {"id": "0" * 32},
            )
    with pytest.raises(MigrationRefused, match="projection_(source_invalid|cohort_changed)"):
        backfill_run_index(pg["owner"], lambda *_: pytest.fail("drift reached byte reader"))
    assert snapshot(pg["owner"]) == before


@pytest.mark.parametrize("operation", ["initialize", "backfill"])
def test_postgres_projection_autocommit_is_rejected_before_mutation(projected_legacy, operation):
    pg = projected_legacy
    before = snapshot(pg["owner"])
    drain(pg)
    engine = pg["owner"].execution_options(isolation_level="AUTOCOMMIT")
    with pytest.raises(MigrationRefused, match="transaction"):
        if operation == "initialize":
            initialize_projection(engine)
        else:
            backfill_run_index(engine, source())
    assert snapshot(pg["owner"]) == before


def test_postgres_projection_runtime_role_cannot_initialize_or_backfill(projected_legacy):
    pg = projected_legacy
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    before = snapshot(pg["owner"])
    drain(pg)
    with pytest.raises(MigrationRefused, match="migration_owner_required"):
        initialize_projection(pg["app"])
    with pytest.raises(MigrationRefused, match="migration_owner_required"):
        backfill_run_index(pg["app"], source())
    assert snapshot(pg["owner"]) == before
    guarded = runtime_schema_compatibility(pg["app"])
    assert (guarded.status, guarded.code) == ("incompatible", "backfill_incomplete")
    # Only the authorized operator can finish the frozen cohort. Completion still
    # leaves this release inspection-only for the same SELECT-only runtime role.
    assert backfill_run_index(pg["owner"], source())["projection_status"] == "complete"
    guarded = runtime_schema_compatibility(pg["app"])
    assert (guarded.status, guarded.code) == ("incompatible", "migration_only")
    preserved(pg["owner"])


def test_postgres_projection_checkpoint_restores_and_resumes(
    recovery, projection_profile, observed_reader
):
    prepare_legacy(recovery)
    initialize_projection(recovery["owner"])
    backfill_run_index(recovery["owner"], source(), batch_size=1)
    before = snapshot(recovery["owner"])
    archive = _dump(recovery)
    _run(_restore_command(recovery), archive=archive)
    assert snapshot(recovery["target"]) == before
    preserved(recovery["target"])
    with recovery["target"].connect() as connection:
        actual = catalog(connection)
    assert actual == json.loads(PROFILE.read_text())
    assert service.schema_status(recovery["target"])["revision"] == PROJECTION
    guarded = runtime_schema_compatibility(recovery["target"])
    assert (guarded.status, guarded.code) == ("incompatible", "backfill_incomplete")
    assert backfill_run_index(recovery["target"], source())["projection_status"] == "complete"
    guarded = runtime_schema_compatibility(recovery["target"])
    assert (guarded.status, guarded.code) == ("incompatible", "migration_only")
    preserved(recovery["target"])


def test_postgres_empty_projection_needs_no_artifact_read(pg, projection_profile, observed_reader):
    prepare_postgres(pg)
    drain(pg)
    result = initialize_projection(pg["owner"])
    assert result["projection_rows_total"] == 0
    assert result["projection_status"] == "complete"
    before = snapshot(pg["owner"])
    assert (
        backfill_run_index(
            pg["owner"], lambda *_: pytest.fail("empty cohort requested artifact bytes")
        )
        == result
    )
    assert snapshot(pg["owner"]) == before
    assert runtime_schema_compatibility(pg["owner"]).code == "migration_only"


def test_postgres_initializer_rollback_preserves_prior_revision(
    pg, projection_profile, monkeypatch
):
    prepare_legacy(pg)
    original = projection_service._write_progress

    def stop(connection, state, *, insert):
        original(connection, state, insert=insert)
        raise RuntimeError("synthetic initializer interruption")

    monkeypatch.setattr(projection_service, "_write_progress", stop)
    with pytest.raises(RuntimeError, match="synthetic initializer interruption"):
        initialize_projection(pg["owner"])
    with pg["owner"].connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == ARTIFACTS
        )
        assert (
            connection.exec_driver_sql("SELECT to_regclass('public.run_index')").scalar_one()
            is None
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM migration_progress WHERE revision=:revision"),
                {"revision": PROJECTION},
            ).scalar_one()
            == 0
        )
    preserved(pg["owner"])
    monkeypatch.setattr(projection_service, "_write_progress", original)
    drain(pg)
    assert initialize_projection(pg["owner"])["projection_rows_verified"] == 0


def test_postgres_source_change_during_byte_read_refuses_stale_proof(projected_legacy):
    pg = projected_legacy
    before = snapshot(pg["owner"])
    frozen = source()
    changed = False

    def reader(*args):
        nonlocal changed
        if not changed:
            changed = True
            with pg["owner"].begin() as connection:
                connection.execute(
                    text("UPDATE records SET created=created+1 WHERE id=:id"),
                    {"id": "2" * 32},
                )
            drain(pg)
        return frozen(*args)

    with pytest.raises(MigrationRefused, match="projection_cohort_changed"):
        backfill_run_index(pg["owner"], reader)
    assert snapshot(pg["owner"]) == before
