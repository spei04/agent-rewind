"""Explicit artifact schema transition; historical bytes and admission stay unchanged."""

import json

import pytest
from legacy_fixture import assert_preserved_rows, materialize_legacy
from sqlalchemy import create_engine
from test_migrations import mapping_for
from test_ownership import FRESH, row

from agent_rewind.migrations import artifact_service, service
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.schema import (
    ARTIFACTS,
    OWNERSHIP,
    MigrationRefused,
    catalog,
    installed_profile,
)


@pytest.fixture
def prepared(tmp_path):
    path = tmp_path / "metadata.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    service.install(engine, FRESH["installation_key"])
    yield path, engine
    engine.dispose()


def test_explicit_upgrade_requires_completed_ownership(prepared):
    path, engine = prepared
    before = path.read_bytes()
    with pytest.raises(MigrationRefused, match="completed_ownership_required"):
        initialize_artifacts(engine)
    assert path.read_bytes() == before
    initialize_ownership(engine, FRESH)
    previous = row(engine)
    result = service.upgrade(engine, ARTIFACTS)
    assert result["revision"] == ARTIFACTS and result["customer_ready"] is False
    current = row(engine)
    for field in previous:
        if field != "installed_schema_fingerprint":
            assert current[field] == previous[field]
    before = path.read_bytes()
    assert service.upgrade(engine, ARTIFACTS) == result
    assert path.read_bytes() == before
    assert runtime_schema_compatibility(engine).code == "migration_only"
    with engine.connect() as c:
        assert catalog(c) == installed_profile("sqlite", ARTIFACTS)
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_objects").scalar_one() == 0
        assert c.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0


def test_schema_install_rollback_preserves_prior_revision(prepared, monkeypatch):
    path, engine = prepared
    initialize_ownership(engine, FRESH)
    original = artifact_service.verify_installed_profile

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic catalog verification stop")

    monkeypatch.setattr(artifact_service, "verify_installed_profile", interrupted)
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="synthetic"):
        initialize_artifacts(engine)
    assert path.read_bytes() == before
    assert service.schema_status(engine)["revision"] == OWNERSHIP
    monkeypatch.setattr(artifact_service, "verify_installed_profile", original)
    assert initialize_artifacts(engine)["revision"] == ARTIFACTS


def test_legacy_transition_keeps_14_rows_18_ciphertexts_and_245000_hold(tmp_path):
    path = materialize_legacy(tmp_path / "legacy")
    engine = create_engine(f"sqlite:///{path}")
    before = {p.name: p.read_bytes() for p in (path.parent / "objects").iterdir()}
    try:
        service.adopt(engine, mapping_for(engine), "b" * 64, "d" * 64)
        initialize_ownership(engine)
        adoption = row(engine)
        initialize_artifacts(engine)
        assert_preserved_rows(path)
        assert len(before) == 18
        assert {p.name: p.read_bytes() for p in (path.parent / "objects").iterdir()} == before
        with engine.connect() as c:
            assert c.exec_driver_sql("SELECT sum(reserved) FROM jobs").scalar_one() == 245000
            assert c.exec_driver_sql("SELECT count(*) FROM artifact_refs").scalar_one() == 0
        for field in adoption:
            if field != "installed_schema_fingerprint":
                assert row(engine)[field] == adoption[field]
    finally:
        engine.dispose()


def test_partial_ownership_never_gains_object_schema(tmp_path):
    path = materialize_legacy(tmp_path / "legacy")
    engine = create_engine(f"sqlite:///{path}")
    try:
        service.adopt(engine, mapping_for(engine), "b" * 64, "d" * 64)
        initialize_ownership(engine, batch_size=1)
        before = path.read_bytes()
        with pytest.raises(MigrationRefused, match="completed_ownership_required"):
            initialize_artifacts(engine)
        assert path.read_bytes() == before
    finally:
        engine.dispose()


def test_catalog_drift_on_reentry_is_not_repaired(prepared):
    _, engine = prepared
    initialize_ownership(engine, FRESH)
    initialize_artifacts(engine)
    with engine.begin() as c:
        c.exec_driver_sql("CREATE INDEX unexpected_artifact_index ON artifact_objects(digest)")
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        initialize_artifacts(engine)


def test_new_profile_does_not_replace_historical_profiles():
    from pathlib import Path

    root = Path(__file__).parents[1] / "agent_rewind/migrations/profiles"
    assert set(json.loads((root / "sqlite_artifacts.json").read_text())) - set(
        json.loads((root / "sqlite_ownership.json").read_text())
    ) == {"artifact_objects", "artifact_refs"}
