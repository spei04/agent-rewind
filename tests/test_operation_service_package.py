"""Exercise the exact committed smoke body; installed proof remains separate."""

import ast
from pathlib import Path


def test_exact_operation_service_smoke_body(tmp_path, capsys):
    source = Path(__file__).parents[1] / "scripts" / "ci_smoke.py"
    node = next(
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "operation_service_smoke"
    )
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    namespace["operation_service_smoke"](tmp_path)
    assert capsys.readouterr().out.strip() == ("operation_service_installed_smoke_verified")
