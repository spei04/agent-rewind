import ast
import json
from pathlib import Path

import sqlalchemy

ROOT = Path(__file__).resolve().parents[1]


def test_exact_installed_smoke_helper_executes_pure_pipeline(monkeypatch):
    # Execute the actual helper, avoiding the script's installed-environment and
    # database smoke setup. Hosted packaging executes the whole script in its
    # isolated runtime; this local check makes no installed-package claim.
    source = ast.parse((ROOT / "scripts" / "ci_smoke.py").read_text())
    helper = next(
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "admission_foundation_smoke"
    )
    namespace = {"json": json}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "ci_smoke.py", "exec"), namespace)

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure preparation opened a database")

    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    namespace["admission_foundation_smoke"]()


def test_exact_installed_storage_smoke_executes_real_migration_and_sql(tmp_path):
    from test_artifact_metadata import prepare
    from test_ownership import FRESH

    from agent_rewind.artifact_metadata import configure_artifact_engine
    from agent_rewind.migrations.compatibility import runtime_schema_compatibility
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.scoped_lineage import ResourceNotFound

    source = ast.parse((ROOT / "scripts" / "ci_smoke.py").read_text())
    helper = next(
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "admission_storage_smoke"
    )
    namespace = {"Engine": sqlalchemy.engine.Engine, "ResourceNotFound": ResourceNotFound}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "ci_smoke.py", "exec"), namespace)
    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'installed-storage.sqlite'}")
    configure_artifact_engine(engine)
    try:
        prepare(engine)
        initialize_projection(engine)
        namespace["admission_storage_smoke"](engine)
        assert runtime_schema_compatibility(engine).code == "migration_only"
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM operations").scalar_one() == 0
            assert (
                connection.exec_driver_sql(
                    "SELECT project_id FROM project_memberships WHERE principal_id=:principal",
                    {"principal": FRESH["principal_grants"][0]["principal_id"]},
                ).scalar_one()
                == FRESH["project_id"]
            )
    finally:
        engine.dispose()
