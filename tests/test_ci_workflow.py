"""Guard the PR trust boundary and required-check wiring in the actual workflow."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_pr_workflow_has_no_privileged_trigger_or_token():
    assert set(WORKFLOW["on"]) == {"push", "pull_request"}
    assert WORKFLOW["on"]["push"] == {"branches": ["main"]}
    assert WORKFLOW["on"]["pull_request"] is None
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    )
    for job_id, job in WORKFLOW["jobs"].items():
        assert job["runs-on"] == "ubuntu-24.04"
        if job_id == "core":
            assert job["timeout-minutes"] == "${{ matrix.timeout }}"
        else:
            assert 0 < job["timeout-minutes"] <= 20
        if job_id == "ci-gate":
            assert job["permissions"] == {"contents": "read", "actions": "read"}
        else:
            assert "permissions" not in job
        assert "continue-on-error" not in job
        for step in job["steps"]:
            assert "continue-on-error" not in step
            if "uses" in step:
                assert re.fullmatch(r"[a-zA-Z0-9_/-]+@[0-9a-f]{40}", step["uses"])
                if step["uses"].startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False
            if "run" in step:
                assert "uv run " not in step["run"].replace("uv run --no-sync ", "")
    assert "secrets." not in (ROOT / ".github/workflows/ci.yml").read_text()


def test_combined_gate_cannot_skip_a_required_job():
    jobs = WORKFLOW["jobs"]
    gate = jobs["ci-gate"]
    assert gate["name"] == "CI gate"
    assert gate["if"] == "${{ always() }}"
    assert set(gate["needs"]) == set(jobs) - {"ci-gate", "delivery"}
    step = gate["steps"][-1]
    assert step["run"] == "python3 -m scripts.ci_gate"
    assert step["env"]["CI_JOB_RESULTS"] == "${{ toJSON(needs) }}"


def test_protected_main_candidate_and_core_receipts_have_separate_exact_uploads():
    jobs = WORKFLOW["jobs"]
    delivery = jobs["delivery"]
    assert delivery["needs"] == ["ci-gate"]
    assert delivery["if"] == (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' "
        "&& github.ref_protected && needs.ci-gate.result == 'success' }}"
    )
    uploads = [
        (name, step)
        for name, job in jobs.items()
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert [name for name, _ in uploads] == ["core", "delivery"]
    receipt_step = uploads[0][1]
    assert receipt_step["if"] == "${{ always() }}"
    receipt = receipt_step["with"]
    assert receipt == {
        "name": "core-receipt-${{ github.run_id }}-${{ github.run_attempt }}-"
        "${{ github.sha }}-py${{ matrix.python }}-${{ matrix.leg }}",
        "path": "${{ runner.temp }}/core-receipt/receipt.json",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 7,
    }
    upload = uploads[1][1]["with"]
    assert upload["retention-days"] == 7
    assert upload["include-hidden-files"] is False
    assert upload["if-no-files-found"] == "error"
    assert set(upload["path"].splitlines()) == {
        "${{ runner.temp }}/rewind-candidate/" + name
        for name in (
            "agent_rewind-0.1.0-py3-none-any.whl",
            "agent_rewind-0.1.0.tar.gz",
            "candidate.json",
            "SHA256SUMS",
        )
    }


def test_dependency_security_scan_is_locked_and_fails_on_findings():
    commands = "\n".join(step.get("run", "") for step in WORKFLOW["jobs"]["security"]["steps"])
    assert "uv export --frozen --all-groups --no-emit-project" in commands
    assert "pip-audit --strict --disable-pip --no-deps --require-hashes" in commands
    assert "ruff check --select S agent_rewind scripts" in commands
    assert "--ignore-vuln" not in commands
    assert "|| true" not in commands


def test_tested_python_versions_and_pinned_external_inputs():
    core = WORKFLOW["jobs"]["core"]
    assert core["strategy"]["matrix"] == {
        "include": [
            {"python": "3.11", "leg": "early", "timeout": 45},
            {"python": "3.11", "leg": "late", "timeout": 45},
            {"python": "3.12", "leg": "all", "timeout": 75},
        ]
    }
    assert core["strategy"]["fail-fast"] is False
    assert core["timeout-minutes"] == "${{ matrix.timeout }}"
    command = next(step["run"] for step in core["steps"] if step.get("name") == "Run core tests")
    assert command.split().count("--maxfail=1") == command.split().count("--durations=50") == 1
    assert core["name"] == "core (${{ matrix.python }}, ${{ matrix.leg }})"
    assert re.fullmatch(
        r"postgres:16-alpine@sha256:[0-9a-f]{64}", core["services"]["postgres"]["image"]
    )
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            if step.get("uses", "").startswith("astral-sh/setup-uv@"):
                assert step["with"]["version"] == "0.13.4"
                assert step["with"]["checksum"] == (
                    "2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f"
                )
                assert step["with"]["enable-cache"] is False


def test_every_frozen_consumer_checks_manifest_lock_consistency_first():
    for job in WORKFLOW["jobs"].values():
        commands = [step.get("run", "") for step in job["steps"]]
        consumers = [i for i, command in enumerate(commands) if "uv sync --frozen" in command]
        for index in consumers:
            assert "uv lock --check --offline" in commands[:index]


def test_package_job_validates_container_installer_and_offline_cli():
    steps = WORKFLOW["jobs"]["package"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "docker build --tag agent-rewind-ci:${{ github.sha }} ." in commands
    assert (
        "docker run --rm --network none agent-rewind-ci:${{ github.sha }} rewind --help" in commands
    )
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY scripts/uv-requirements.txt /tmp/uv-requirements.txt" in dockerfile
    assert (
        "pip install --no-cache-dir --no-deps --only-binary=:all: --require-hashes "
        "-r /tmp/uv-requirements.txt" in dockerfile
    )


def test_container_trust_repair_precedes_network_bootstrap_and_final_check_is_offline():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.index("container_ca.py --repair") < dockerfile.index("pip install")
    commands = "\n".join(step.get("run", "") for step in WORKFLOW["jobs"]["package"]["steps"])
    assert (
        "docker run --rm --network none agent-rewind-ci:${{ github.sha }} "
        "/app/.venv/bin/python -I /opt/agent-rewind/container_ca.py --check"
    ) in commands
