import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_postgres", ROOT / "scripts" / "ci_postgres.py")
assert spec is not None and spec.loader is not None
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
CONTAINER = "a" * 64
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_RUN_ID": "123",
    "GITHUB_RUN_ATTEMPT": "2",
    "REWIND_CI_POSTGRES_CONTAINER": CONTAINER,
    # These arbitrary external targets must never be read by this setup.
    "REWIND_TEST_POSTGRES": "postgresql://private-server/production",
    "REWIND_TEST_POSTGRES_URL": "postgresql://private-server/production",
}


def identity(image=setup.IMAGE, label="123-2", running=True):
    return "\n".join(json.dumps(value) for value in (image, label, running))


def runner(monkeypatch, replies):
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        answer = replies.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return subprocess.CompletedProcess(arguments, 0, answer, "")

    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(setup.time, "sleep", lambda seconds: None)
    return calls


def test_only_verified_service_is_configured_and_effective_state_observed(monkeypatch):
    calls = runner(
        monkeypatch,
        [
            identity(),
            "ALTER SYSTEM",
            "t",
            "on|default|f|0",
            "off|configuration file|f|1",
            "off|configuration file|f|0",
        ],
    )
    setup.configure(ENV)
    sql = [arguments[-1] for arguments, _ in calls[1:]]
    assert sql == [
        "ALTER SYSTEM SET autovacuum = off",
        "SELECT pg_catalog.pg_reload_conf()",
        setup.OBSERVE,
        setup.OBSERVE,
        setup.OBSERVE,
    ]
    for arguments, options in calls:
        assert options["check"] is True
        assert 0 < options["timeout"] <= setup.COMMAND_SECONDS
        assert "shell" not in options
        assert "private-server" not in " ".join(arguments)
        if arguments[1] == "exec":
            assert arguments[2] == CONTAINER
            assert arguments[3:6] == ["psql", "-X", "-w"]
            assert arguments[arguments.index("-h") + 1] == "/var/run/postgresql"
            assert arguments[arguments.index("-d") + 1] == "postgres"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_RUN_ID", ""),
        ("GITHUB_RUN_ID", "../123"),
        ("GITHUB_RUN_ATTEMPT", "0"),
        ("REWIND_CI_POSTGRES_CONTAINER", "postgres"),
        ("REWIND_CI_POSTGRES_CONTAINER", "--help"),
        ("REWIND_CI_POSTGRES_CONTAINER", "a" * 63),
    ],
)
def test_missing_ci_identity_never_invokes_docker(monkeypatch, field, value):
    calls = runner(monkeypatch, [])
    with pytest.raises(setup.SetupRefused, match="identity_required"):
        setup.configure({**ENV, field: value})
    assert calls == []


@pytest.mark.parametrize(
    "response",
    [
        identity(image="postgres:16-alpine"),
        identity(label="123-1"),
        identity(label=None),
        identity(running=False),
        identity(running=1),
        "not-json",
        identity() + "\nnull",
        "x" * 4097,
    ],
)
def test_wrong_service_never_reaches_sql(monkeypatch, response):
    calls = runner(monkeypatch, [response])
    with pytest.raises(setup.SetupRefused):
        setup.configure(ENV)
    assert len(calls) == 1
    assert calls[0][0][1] == "inspect"


@pytest.mark.parametrize("stage", range(4))
def test_command_failure_has_fixed_diagnostic_and_no_retry(monkeypatch, stage):
    replies = [identity(), "ALTER SYSTEM", "t", "off|configuration file|f|0"]
    replies[stage] = subprocess.CalledProcessError(
        1, ["private-canary"], output="private-canary", stderr="private-canary"
    )
    calls = runner(monkeypatch, replies)
    with pytest.raises(setup.SetupRefused, match="ci_postgres_command_failed") as caught:
        setup.configure(ENV)
    assert str(caught.value) == "ci_postgres_command_failed"
    assert len(calls) == stage + 1


@pytest.mark.parametrize(
    "failure", [OSError("private-canary"), subprocess.TimeoutExpired("secret", 5)]
)
def test_spawn_and_command_timeout_do_not_expose_details(monkeypatch, failure):
    calls = runner(monkeypatch, [failure])
    with pytest.raises(setup.SetupRefused, match="ci_postgres_command_failed"):
        setup.configure(ENV)
    assert len(calls) == 1


@pytest.mark.parametrize("response", ["f", "", "private-canary"])
def test_reload_must_acknowledge_success(monkeypatch, response):
    calls = runner(monkeypatch, [identity(), "ALTER SYSTEM", response])
    with pytest.raises(setup.SetupRefused, match="ci_postgres_reload_failed"):
        setup.configure(ENV)
    assert len(calls) == 3


@pytest.mark.parametrize("response", ["", "off|configuration file|f|0\nprivate", "private-canary"])
def test_malformed_observation_refuses(monkeypatch, response):
    runner(monkeypatch, [identity(), "ALTER SYSTEM", "t", response])
    with pytest.raises(setup.SetupRefused, match="ci_postgres_observation_invalid"):
        setup.configure(ENV)


@pytest.mark.parametrize(
    "observation",
    [
        "on|default|f|0",
        "off|configuration file|f|1",
        "off|command line|f|0",
        "off|configuration file|t|0",
    ],
)
def test_unverified_or_busy_service_hits_total_deadline_without_reconfiguration(
    monkeypatch, observation
):
    calls = runner(monkeypatch, [identity(), "ALTER SYSTEM", "t", observation])
    # Start, inspect, ALTER, reload, observation, then check after observation.
    clock = iter([0, 0, 1, 2, 3, setup.MAX_SECONDS])
    monkeypatch.setattr(setup.time, "monotonic", lambda: next(clock))
    with pytest.raises(setup.SetupRefused, match="ci_postgres_setup_timeout"):
        setup.configure(ENV)
    assert len(calls) == 4


def test_main_reports_fixed_failure_only(monkeypatch, capsys):
    monkeypatch.setattr(setup, "configure", Mock(side_effect=setup.SetupRefused("safe_fixed_code")))
    assert setup.main() == 1
    assert capsys.readouterr().out == "safe_fixed_code\n"


def test_workflow_binds_setup_to_disposable_service_before_every_test():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    core = workflow["jobs"]["core"]
    service = core["services"]["postgres"]
    assert service["image"] == setup.IMAGE
    assert (
        "--label io.agent-rewind.ci-run=\u0024{{ github.run_id }}-\u0024{{ github.run_attempt }}"
        in service["options"]
    )
    steps = core["steps"]
    position, step = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("run") == "python3 scripts/ci_postgres.py"
    )
    assert step["env"] == {"REWIND_CI_POSTGRES_CONTAINER": "\u0024{{ job.services.postgres.id }}"}
    assert step["timeout-minutes"] == 1
    assert all(
        position < index for index, step in enumerate(steps) if "pytest" in step.get("run", "")
    )
