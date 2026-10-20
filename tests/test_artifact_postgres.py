"""Real PostgreSQL artifact catalog and composite/concurrent reference acceptance."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import test_migration_recovery_postgres as recovery_tests
import test_migrations_postgres as migration_tests
from postgres_control import wait_for_database_drain
from sqlalchemy.exc import IntegrityError
from test_artifact_metadata import FRESH, OTHER, object_value, owners, reference, resolve
from test_migration_recovery_postgres import _dump, _restore_command, _run
from test_migrations_postgres import POSTGRES, assert_original_rows, load_legacy, mapping_for

from agent_rewind.artifact_metadata import record_verified
from agent_rewind.migrations import service
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.schema import ARTIFACTS, catalog

pg = migration_tests.pg
recovery = recovery_tests.recovery
pytestmark = pytest.mark.skipif(
    not POSTGRES, reason="Opt-in synthetic PostgreSQL artifact metadata"
)
PROFILE = Path(__file__).parents[1] / "agent_rewind/migrations/profiles/postgresql16_artifacts.json"


def _drain(pg):
    wait_for_database_drain(pg["control"], pg["owner"].url.database)


def prepare_postgres(pg):
    # Each exclusive migration follows observed server-side exit of the prior
    # disposable client; this never retries the product's refusal.
    _drain(pg)
    service.install(pg["owner"], FRESH["installation_key"])
    _drain(pg)
    initialize_ownership(pg["owner"], FRESH)
    _drain(pg)
    initialize_artifacts(pg["owner"])


@pytest.fixture
def artifact_profile():
    if not PROFILE.is_file():
        pytest.skip("Hosted catalog capture requires independent literal profile review")


def test_postgres_artifact_profile_requires_independent_freeze(pg):
    _drain(pg)
    with service.migration_transaction(pg["owner"]) as c:
        service._alembic(c, "upgrade", ARTIFACTS)
        shape = catalog(c)
        if not PROFILE.is_file():
            pytest.fail(
                "SYNTHETIC_ARTIFACT_POSTGRES16_CATALOG_REVIEW_REQUIRED="
                + json.dumps(shape, sort_keys=True, separators=(",", ":")),
                pytrace=False,
            )
        assert shape == json.loads(PROFILE.read_text())


def test_postgres_scoped_refs_conflicts_and_migration_only(pg, artifact_profile):
    engine = pg["owner"]
    prepare_postgres(pg)
    assert runtime_schema_compatibility(engine).code == "migration_only"
    with engine.begin() as c:
        owners(c)
        record_verified(c, object_value())
    with pytest.raises(IntegrityError), engine.begin() as c:
        reference(c, object_value(), project_id=OTHER, owner_id="3" * 32)
    with engine.begin() as c:
        assert reference(c, object_value())
        assert not reference(c, object_value())
        assert resolve(c, object_value()) == object_value()
        assert resolve(c, object_value(), project_id=OTHER) is None


def test_postgres_concurrent_metadata_reference_is_idempotent(pg, artifact_profile):
    engine = pg["owner"]
    prepare_postgres(pg)
    with engine.begin() as c:
        owners(c)
    barrier = Barrier(2)
    value = object_value()

    def contender():
        barrier.wait(timeout=5)
        with engine.begin() as c:
            record_verified(c, value)
            return reference(c, value)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(contender) for _ in range(2)]
        assert sorted(f.result(10) for f in results) == [False, True]
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_objects").scalar_one() == 1
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 1


def test_postgres_artifact_catalog_restores_without_admission(recovery, pg, artifact_profile):
    load_legacy(recovery["owner"])
    mapping = mapping_for(recovery["owner"])
    _drain(pg)
    service.adopt(recovery["owner"], mapping, "b" * 64, "d" * 64)
    _drain(pg)
    initialize_ownership(recovery["owner"])
    _drain(pg)
    initialize_artifacts(recovery["owner"])
    archive = _dump(recovery)
    _run(_restore_command(recovery), archive=archive)
    assert_original_rows(recovery["target"])
    with recovery["target"].connect() as connection:
        actual = catalog(connection)
    assert actual == json.loads(PROFILE.read_text())
    assert service.schema_status(recovery["target"])["revision"] == ARTIFACTS
    assert runtime_schema_compatibility(recovery["target"]).code == "migration_only"
