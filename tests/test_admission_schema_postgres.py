"""Actual PG16 admission catalog capture; no automatic literal approval."""

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

import pytest
import test_migrations_postgres as migration_tests
import test_run_projection_postgres as projection_tests
from legacy_fixture import canonical_bytes, read_manifest
from sqlalchemy import text

from agent_rewind.migrations import service
from agent_rewind.migrations.admission_service import initialize_admission
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.inputs import source_digest
from agent_rewind.migrations.projection_service import backfill_run_index
from agent_rewind.migrations.schema import ADMISSION, COLUMNS, catalog, checksum
from agent_rewind.projection_source import QueryBudget, read_cohort

pg = migration_tests.pg
observed_reader = projection_tests.observed_reader
projection_profile = projection_tests.projection_profile
projected_legacy = projection_tests.projected_legacy
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL admission schema"
)
ROOT = Path(__file__).parents[1]
PROFILE = ROOT / "agent_rewind/migrations/profiles/postgresql16_admission.json"
CAPTURE_FILES = (
    "agent_rewind/migrations/admission_schema.py",
    "agent_rewind/migrations/schema.py",
    "agent_rewind/migrations/versions/0006_admission.py",
)


def original_rows(connection):
    # This deliberately reads only the frozen 13 job fields: additive defaults
    # must neither enter historical hashes nor excuse a changed original value.
    manifest = read_manifest()
    for name, expected in manifest["expected_rows"].items():
        columns = ",".join(column[0] for column in COLUMNS[name])
        order = "run_id,step" if name == "events" else "id"
        rows = [
            dict(row)
            for row in connection.execute(
                text(f"SELECT {columns} FROM {name} ORDER BY {order}")
            ).mappings()
        ]
        for row in rows:
            for field in ("cancel", "revoked"):
                if field in row and row[field] is not None:
                    row[field] = int(row[field])
        assert rows == expected
        assert [hashlib.sha256(canonical_bytes(row)).hexdigest() for row in rows] == manifest[
            "row_sha256"
        ][name]
    assert connection.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 245000


def test_postgres_admission_profile_requires_independent_freeze(projected_legacy):
    state = projected_legacy
    engine = state["owner"]
    backfill_run_index(engine, projection_tests.source())
    before = projection_tests.snapshot(engine)
    projection_tests.preserved(engine)  # All 14 rows, 18 ciphertexts and literal heads.
    projection_tests.drain(state)
    with service.migration_transaction(engine) as connection:
        previous = catalog(connection)
        with QueryBudget().observe(connection):
            identity = read_cohort(connection).identity
        original = source_digest(connection)
        service._alembic(connection, "upgrade", ADMISSION)
        shape = catalog(connection)
        assert len(shape) == 17
        assert set(shape) - set(previous) == {"operations", "operation_keys"}
        assert all(shape[name] == previous[name] for name in previous if name != "jobs")
        assert shape["jobs"]["columns"][:13] == previous["jobs"]["columns"]
        assert source_digest(connection) == original
        with QueryBudget().observe(connection):
            assert read_cohort(connection).identity == identity
        original_rows(connection)
        assert (
            connection.exec_driver_sql(
                "SELECT payload_version,execution_config_ref,execution_config_digest FROM jobs"
            ).all()
            == [(1, None, None)] * 3
        )
    assert projection_tests.snapshot(engine) == before
    if not PROFILE.is_file():
        revision = os.getenv("GITHUB_SHA", "")
        record = {
            "schema": 1,
            "source_commit": revision if re.fullmatch("[0-9a-f]{40}", revision) else "local",
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in CAPTURE_FILES
            },
            "predecessor_catalog_sha256": checksum(previous),
            "preserved_cohort": asdict(identity),
            "catalog": shape,
        }
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert len(encoded.encode()) <= 192 * 1024
        # Only fixed synthetic schema/digests enter this intentional failing review
        # aid. No DSN, row body, role name, key, artifact plaintext or automatic freeze.
        pytest.fail(
            "SYNTHETIC_ADMISSION_POSTGRES16_CATALOG_REVIEW_REQUIRED=" + encoded, pytrace=False
        )
    assert shape == json.loads(PROFILE.read_text())


@pytest.fixture
def admission_profile():
    assert PROFILE.is_file(), "Admission PostgreSQL catalog needs independent review"


def test_postgres_admission_initializer_preserves_completed_projection(
    projected_legacy, admission_profile
):
    state = projected_legacy
    engine = state["owner"]
    backfill_run_index(engine, projection_tests.source())
    before = projection_tests.snapshot(engine)
    projection_tests.drain(state)
    result = initialize_admission(engine)
    assert result["revision"] == ADMISSION and result["customer_ready"] is False
    assert projection_tests.snapshot(engine) == before
    with engine.connect() as connection:
        original_rows(connection)
        assert catalog(connection) == json.loads(PROFILE.read_text())
    projection_tests.drain(state)
    assert initialize_admission(engine) == result
    assert runtime_schema_compatibility(engine).code == "migration_only"
