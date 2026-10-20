"""Real PostgreSQL ownership profile, exclusion, crash/retry and restore evidence."""

import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
import test_migration_recovery_postgres as recovery_tests
import test_migrations_postgres as migration_tests
from sqlalchemy import text
from test_migration_recovery_postgres import _dump, _restore_command, _run
from test_migrations_postgres import POSTGRES, assert_original_rows, load_legacy, mapping_for
from test_ownership import FRESH

from agent_rewind.migrations import ownership_service, service
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.schema import HEAD, OWNERSHIP, MigrationRefused, catalog

pg = migration_tests.pg
recovery = recovery_tests.recovery

pytestmark = pytest.mark.skipif(not POSTGRES, reason="Opt-in synthetic PostgreSQL ownership")
PROFILE = Path(__file__).parents[1] / "agent_rewind/migrations/profiles/postgresql16_ownership.json"


@pytest.fixture
def ownership_profile():
    if not PROFILE.is_file():
        pytest.skip("Hosted catalog capture requires independent literal profile freezing")


def prepare(pg):
    load_legacy(pg["owner"])
    service.adopt(pg["owner"], mapping_for(pg["owner"]), "b" * 64, "d" * 64)


def test_postgres_ownership_profile_requires_independent_freeze(pg):
    with service.migration_transaction(pg["owner"]) as connection:
        service._alembic(connection, "upgrade", OWNERSHIP)
        shape = catalog(connection)
        if not PROFILE.is_file():
            pytest.fail(
                "SYNTHETIC_OWNERSHIP_POSTGRES16_CATALOG_REVIEW_REQUIRED="
                + json.dumps(shape, sort_keys=True, separators=(",", ":")),
                pytrace=False,
            )
        assert shape == json.loads(PROFILE.read_text())


def test_postgres_fresh_transition_and_nonowner_read_only_refusal(pg, ownership_profile):
    service.install(pg["owner"], FRESH["installation_key"])
    first = initialize_ownership(pg["owner"], FRESH)
    assert first["state"] == "ownership_complete" and first["customer_ready"] is False
    assert initialize_ownership(pg["owner"], FRESH) == first
    with pg["owner"].begin() as connection:
        metadata = connection.execute(text("SELECT * FROM installation_adoptions")).mappings().one()
        assert metadata["backup_evidence_digest"] is metadata["drain_evidence_digest"] is None
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    result = runtime_schema_compatibility(pg["app"])
    assert result.status == "incompatible" and result.code == "migration_only"
    with pytest.raises(MigrationRefused, match="migration_owner_required"):
        initialize_ownership(pg["app"], FRESH)
    assert service.schema_status(pg["owner"])["state"] == "ownership_complete"


def test_postgres_batches_preserve_history_and_idle_application_blocks_resume(
    pg, ownership_profile
):
    prepare(pg)
    first = initialize_ownership(pg["owner"], batch_size=2)
    assert first["ownership_rows_verified"] == 2
    with pg["app"].connect() as application:
        application.exec_driver_sql("SELECT 1")
        with pytest.raises(MigrationRefused, match="writers_not_drained"):
            initialize_ownership(pg["owner"], batch_size=2)
    with pg["owner"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT rows_verified FROM migration_progress WHERE phase='ownership'"
            ).scalar_one()
            == 2
        )
    result = initialize_ownership(pg["owner"])
    assert result["ownership_rows_verified"] == 7
    assert result["state"] == "ownership_complete"
    assert_original_rows(pg["owner"])


def test_postgres_competing_migrators_do_not_advance_same_cursor(
    pg, ownership_profile, monkeypatch
):
    prepare(pg)
    initialize_ownership(pg["owner"], batch_size=1)
    entered, release = Event(), Event()
    original = ownership_service._write_progress

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(5), "Concurrent refusal did not finish"
        return original(*args, **kwargs)

    monkeypatch.setattr(ownership_service, "_write_progress", held)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(initialize_ownership, pg["owner"], batch_size=1)
        assert entered.wait(5)
        try:
            with pytest.raises(MigrationRefused, match="migration_busy"):
                initialize_ownership(pg["owner"], batch_size=1, timeout_seconds=1)
        finally:
            release.set()
        assert first.result(5)["ownership_rows_verified"] == 2
    assert_original_rows(pg["owner"])


@pytest.mark.parametrize("after_commit", [False, True])
def test_postgres_actual_process_death_before_or_after_batch_commit(
    pg, ownership_profile, after_commit
):
    prepare(pg)
    child = """
import os, signal
from sqlalchemy import create_engine
from agent_rewind.migrations import ownership_service
engine = create_engine(os.environ["SYNTHETIC_OWNERSHIP_DSN"])
if os.environ["AFTER_COMMIT"] == "0":
    def interrupted(*args, **kwargs):
        os.kill(os.getpid(), signal.SIGKILL)
    ownership_service._write_progress = interrupted
ownership_service.initialize_ownership(engine, batch_size=2)
os.kill(os.getpid(), signal.SIGKILL)
"""
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        timeout=30,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "SYNTHETIC_OWNERSHIP_DSN": pg["owner"].url.render_as_string(hide_password=False),
            "AFTER_COMMIT": str(int(after_commit)),
        },
    )
    assert result.returncode == -signal.SIGKILL, "Child did not reach intended transaction boundary"
    status = service.schema_status(pg["owner"])
    assert status["revision"] == (OWNERSHIP if after_commit else HEAD)
    if after_commit:
        with pg["owner"].connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT rows_verified FROM migration_progress WHERE phase='ownership'"
                ).scalar_one()
                == 2
            )
    assert_original_rows(pg["owner"])
    assert initialize_ownership(pg["owner"])["state"] == "ownership_complete"
    assert_original_rows(pg["owner"])


def test_postgres_ownership_checkpoint_dump_restore_resumes_without_activation(
    recovery, ownership_profile
):
    prepare(recovery)
    initialize_ownership(recovery["owner"], batch_size=2)
    archive = _dump(recovery)
    _run(_restore_command(recovery), archive=archive)
    assert_original_rows(recovery["target"])
    expected = json.loads(PROFILE.read_text())
    with recovery["target"].connect() as connection:
        actual = catalog(connection)
    differences = []

    def compare(left, right, path):
        if left == right or len(differences) >= 12:
            return
        if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
            for key in sorted(left):
                compare(left[key], right[key], f"{path}/{key}")
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for index, (before, after) in enumerate(zip(left, right, strict=True)):
                compare(before, after, f"{path}/{index}")
        else:
            differences.append(
                {"path": path, "expected": repr(left)[:700], "restored": repr(right)[:700]}
            )

    compare(expected, actual, "")
    assert actual == expected, "Synthetic ownership restored catalog differs: " + json.dumps(
        differences
    )
    assert service.schema_status(recovery["target"])["state"] == "prepared"
    assert runtime_schema_compatibility(recovery["target"]).status == "incompatible"
    assert initialize_ownership(recovery["target"])["state"] == "ownership_complete"
    assert_original_rows(recovery["target"])
    assert runtime_schema_compatibility(recovery["target"]).code == "migration_only"
