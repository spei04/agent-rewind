"""Execute the installed-package helper body against explicit synthetic migrations."""

import ast
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from test_ownership import FRESH

from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.migrations.service import install
from agent_rewind.scoped_repositories import ResourceNotFound


def test_actual_package_helper_round_trip_and_scoped_empty_reader(tmp_path):
    script = Path(__file__).parents[1] / "scripts/ci_smoke.py"
    node = next(
        n
        for n in ast.parse(script.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "run_listing_smoke"
    )
    namespace = {"Engine": Engine, "ResourceNotFound": ResourceNotFound}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(script), "exec"), namespace)
    engine = create_engine(f"sqlite:///{tmp_path / 'package.sqlite'}")
    try:
        install(engine, FRESH["installation_key"])
        initialize_ownership(engine, FRESH)
        initialize_artifacts(engine)
        initialize_projection(engine)
        namespace["run_listing_smoke"](engine)
    finally:
        engine.dispose()
