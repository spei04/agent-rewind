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
