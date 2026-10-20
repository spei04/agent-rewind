"""Synthetic PostgreSQL 16 backup/restore using the existing pinned CI service.

The source/target and roles are disposable. Object copies are a separate fixture
backup: pg_dump does not back up encrypted objects, encryption keys, or roles.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from legacy_fixture import FIXTURE_ROOT, read_manifest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from test_migrations_postgres import (
    POSTGRES,
    assert_original_rows,
    load_legacy,
    mapping_for,
)
from test_migrations_postgres import pg as pg

from agent_rewind.migrations import service
from agent_rewind.migrations.schema import catalog, installed_profile

pytestmark = pytest.mark.skipif(not POSTGRES, reason="Opt-in synthetic PostgreSQL recovery")
POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
)
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024


def _run(command, *, archive=None):
    result = subprocess.run(command, input=archive, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, "Synthetic PostgreSQL backup/restore command failed"
    return result.stdout


@pytest.fixture
def recovery(request):
    container = os.getenv("REWIND_TEST_POSTGRES_CONTAINER", "")
    assert re.fullmatch(r"[0-9a-f]{64}", container), (
        "PostgreSQL recovery requires the existing pinned service container ID"
    )
    assert shutil.which("docker"), "Docker CLI is required for the configured recovery drill"
    image = _run(["docker", "inspect", "--format", "{{.Config.Image}}", container]).decode().strip()
    assert image == POSTGRES_IMAGE, "Recovery tools must come from the pinned CI service image"
    for tool in ("pg_dump", "pg_restore"):
        version = _run(["docker", "exec", container, tool, "--version"]).decode().strip()
        assert version.startswith(f"{tool} (PostgreSQL) 16."), "Recovery tool version mismatch"
    state = request.getfixturevalue("pg")
    admin = create_engine(state["admin"].url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = "ar_recovery_" + uuid4().hex
    with admin.connect() as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {name} OWNER {state['owner_role']}")
    target = create_engine(state["owner"].url.set(database=name), poolclass=NullPool)
    try:
        with target.begin() as connection:
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        yield {**state, "target": target, "control": admin, "container": container}
    finally:
        target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE {name} WITH (FORCE)")
        admin.dispose()


def _command(recovery, tool, engine, *options, application="ar_recovery"):
    # Credentials are the existing public synthetic test-role password, never a
    # deployment DSN. No shell, new container, image pull, or installed client.
    return [
        "docker",
        "exec",
        "-i",
        "-e",
        "PGPASSWORD=synthetic-test-only",
        "-e",
        f"PGAPPNAME={application}",
        recovery["container"],
        tool,
        "--host=127.0.0.1",
        f"--username={engine.url.username}",
        f"--dbname={engine.url.database}",
        "--no-owner",
        "--no-acl",
        *options,
    ]


def _dump(recovery):
    archive = _run(_command(recovery, "pg_dump", recovery["owner"], "--format=custom"))
    assert archive.startswith(b"PGDMP") and len(archive) <= MAX_ARCHIVE_BYTES
    return archive


def _restore_command(recovery, *options, application="ar_recovery"):
    return _command(
        recovery,
        "pg_restore",
        recovery["target"],
        "--single-transaction",
        "--exit-on-error",
        *options,
        application=application,
    )


def _object_copy(source, destination):
    manifest = read_manifest()
    expected = {obj["address"]: obj for obj in manifest["objects"].values()}
    assert len(expected) == 18 and {p.name for p in source.iterdir()} == set(expected)
    destination.mkdir(mode=0o700)
    cipher = Fernet(manifest["synthetic_fernet_key"].encode())
    for address, spec in expected.items():
        data = (source / address).read_bytes()
        assert hashlib.sha256(data).hexdigest() == spec["ciphertext_sha256"]
        assert hashlib.sha256(cipher.decrypt(data)).hexdigest() == address
        target = destination / address
        target.touch(mode=0o600)
        target.write_bytes(data)
    return destination


def _assert_identity(engine):
    manifest = read_manifest()
    assert sum(map(len, manifest["expected_rows"].values())) == 14
    assert manifest["reservation_total_microusd"] == 245000
    assert_original_rows(engine)  # Literal rows, individual hashes and reservation sum.


def _assert_restored_catalog(engine):
    # Diagnostics contain only this disposable synthetic schema, never row values,
    # connection parameters, or a database-derived replacement for the authority.
    expected = installed_profile("postgresql")
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL search_path TO public, pg_temp")
        actual = catalog(connection)
    differences = []

    def compare(left, right, path):
        if len(differences) >= 12 or left == right:
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
    if actual != expected:
        pytest.fail("Synthetic restored catalog differs: " + json.dumps(differences), pytrace=False)


def _assert_migration_only(engine):
    # This interface arrives with the independently reviewed AR-005-C guard.
    from agent_rewind.migrations.compatibility import runtime_schema_compatibility

    result = runtime_schema_compatibility(engine)
    assert result.status == "incompatible" and result.code == "migration_only"


@pytest.mark.parametrize("prepared", [False, True], ids=["legacy-backup", "prepared-backup"])
def test_postgres_restore_preserves_literal_history_and_objects(recovery, tmp_path, prepared):
    load_legacy(recovery["owner"])
    mapping = mapping_for(recovery["owner"])
    if prepared:
        service.adopt(recovery["owner"], mapping, "b" * 64, "d" * 64)
    _assert_identity(recovery["owner"])
    objects = _object_copy(FIXTURE_ROOT / "objects", tmp_path / "backup-objects")
    archive = _dump(recovery)
    backup_digest = hashlib.sha256(archive).hexdigest()
    _run(_restore_command(recovery), archive=archive)
    assert recovery["target"].url.database != recovery["owner"].url.database
    _assert_identity(recovery["target"])
    restored = _object_copy(objects, tmp_path / "restored-objects")
    assert {p.name: p.read_bytes() for p in restored.iterdir()} == {
        p.name: p.read_bytes() for p in (FIXTURE_ROOT / "objects").iterdir()
    }
    if not prepared:
        assert service.schema_status(recovery["target"])["state"] == "legacy_unversioned"
        from agent_rewind.migrations.compatibility import runtime_schema_compatibility

        assert runtime_schema_compatibility(recovery["target"]).status == "incompatible"
        # Restoring the pre-adoption backup permits the same deliberate migration;
        # it neither releases holds nor activates application access.
        service.adopt(recovery["target"], mapping, backup_digest, "d" * 64)
    _assert_restored_catalog(recovery["target"])
    status = service.schema_status(recovery["target"])
    assert status["state"] == "prepared" and status["customer_ready"] is False
    _assert_migration_only(recovery["target"])
    _assert_identity(recovery["owner"])
    _assert_identity(recovery["target"])


def test_postgres_truncated_archive_refuses_without_partial_restore(recovery):
    load_legacy(recovery["owner"])
    archive = _dump(recovery)
    failed = subprocess.run(
        _restore_command(recovery),
        input=archive[: len(archive) // 2],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert failed.returncode != 0, "Truncated archive unexpectedly restored"
    with recovery["target"].connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).scalar_one()
            == 0
        )
    assert service.schema_status(recovery["target"])["state"] == "empty"
    _assert_identity(recovery["owner"])
    _run(_restore_command(recovery), archive=archive)
    _assert_identity(recovery["target"])


def test_postgres_interrupted_restore_rolls_back_rows_and_retries(recovery):
    load_legacy(recovery["owner"])
    archive = _dump(recovery)
    # Pre-create only schema so a real table lock deterministically pauses COPY.
    # Successful full restores above use one transaction for both schema and data.
    _run(_restore_command(recovery, "--schema-only"), archive=archive)
    application = "ar_recovery_cancel_" + uuid4().hex
    with recovery["target"].begin() as blocker:
        blocker.exec_driver_sql("LOCK TABLE jobs IN ACCESS EXCLUSIVE MODE")
        blocker_pid = blocker.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        process = subprocess.Popen(
            _restore_command(recovery, "--data-only", application=application),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            completed = executor.submit(process.communicate, input=archive, timeout=30)
            try:
                deadline = time.monotonic() + 10
                while True:
                    with recovery["control"].connect() as connection:
                        pid = connection.execute(
                            text(
                                "SELECT pid FROM pg_stat_activity WHERE application_name=:app "
                                "AND datname=:db AND :blocker=ANY(pg_blocking_pids(pid))"
                            ),
                            {
                                "app": application,
                                "db": recovery["target"].url.database,
                                "blocker": blocker_pid,
                            },
                        ).scalar_one_or_none()
                        if pid is not None:
                            assert connection.execute(
                                text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                            ).scalar_one()
                            break
                    assert not completed.done(), "Restore exited before the cancellation barrier"
                    assert time.monotonic() < deadline, (
                        "Restore never reached its table-lock barrier"
                    )
                    Event().wait(0.02)  # Bounded polling of the actual blocking condition.
                completed.result(timeout=15)
                assert process.returncode != 0, "Terminated restore unexpectedly succeeded"
            finally:
                if process.poll() is None:
                    process.kill()
                completed.result(timeout=35)
    with recovery["target"].connect() as connection:
        for table in read_manifest()["expected_rows"]:
            assert connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one() == 0
    _assert_identity(recovery["owner"])
    _run(_restore_command(recovery, "--data-only"), archive=archive)
    _assert_identity(recovery["target"])
    assert service.schema_status(recovery["target"])["state"] == "legacy_unversioned"
