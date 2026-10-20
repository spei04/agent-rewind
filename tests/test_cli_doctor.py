"""Doctor must perform the artifact round trip even with Python optimization."""

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("optimize", [0, 2])
@pytest.mark.parametrize("healthy", [False, True])
def test_doctor_checks_artifacts_when_optimized(monkeypatch, capsys, optimize, healthy):
    source = Path(__file__).resolve().parents[1] / "agent_rewind" / "cli.py"
    namespace = {"__name__": "agent_rewind.cli", "__package__": "agent_rewind"}
    exec(compile(source.read_text(), str(source), "exec", optimize=optimize), namespace)
    settings = SimpleNamespace(
        sandbox_runtime="runsc", allowed_images="", model_api_key="", model_name=""
    )
    connection = Mock()
    namespace["Settings"] = lambda: settings
    namespace["Database"] = lambda _: SimpleNamespace(
        engine=SimpleNamespace(connect=lambda: nullcontext(connection))
    )
    store = Mock()
    store.put.return_value = "synthetic-health-object"
    store.get.return_value = b"health check" if healthy else b"incorrect payload"
    monkeypatch.setattr("agent_rewind.artifacts.Artifacts", lambda _: store)
    runner = Mock()
    monkeypatch.setattr("agent_rewind.runner.DockerRunner", runner)
    monkeypatch.setattr("sys.argv", ["rewind", "doctor"])
    if healthy:
        namespace["main"]()
        assert json.loads(capsys.readouterr().out)["artifacts"] == "ok"
        runner.assert_called_once_with(settings)
    else:
        with pytest.raises(ValueError, match="Artifact store health check failed"):
            namespace["main"]()
        assert capsys.readouterr().out == ""
        runner.assert_not_called()
    connection.exec_driver_sql.assert_called_once_with("SELECT 1")
    store.put.assert_called_once_with(b"health check")
    store.get.assert_called_once_with("synthetic-health-object")
