"""Static local Compose safety plus explicit metadata CLI behavior, without Docker."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_setup_defaults_to_readonly_inspection_without_artifact_secrets():
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    setup = services["migrate"]
    assert setup["command"] == ["rewind", "migrate", "status"]
    assert "env_file" not in setup
    assert "volumes" not in setup
    assert set(setup["environment"]) == {"REWIND_DATABASE_URL"}
    assert setup["profiles"] == ["setup"]


def test_compose_stays_development_only_and_does_not_expose_database_or_docker():
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    assert services["api"]["environment"]["REWIND_MODE"] == "development"
    assert services["api"]["environment"]["REWIND_MODEL_API_KEY"] == ""
    assert services["api"]["ports"] == ["127.0.0.1:8080:8080"]
    assert "ports" not in services["database"]
    assert all("docker.sock" not in volume for volume in services["api"]["volumes"])
