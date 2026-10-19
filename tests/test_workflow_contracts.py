"""Validate trusted, synthetic workflow contracts; no live execution evidence."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_rewind.models import Action, Intervention, TaskSpec

FIXTURE = Path(__file__).resolve().parents[1] / "contracts/fixtures/workflows.json"
CONTRACT = json.loads(FIXTURE.read_text())
WORKFLOWS = CONTRACT["workflows"]


def evaluate_fixture(workflow, tmp_path, repaired):
    workspace = tmp_path / ("repaired" if repaired else "original")
    workspace.mkdir()
    files = workflow["task"]["files"] | (
        workflow["successful_workspace"] if repaired else {}
    )
    for name, content in files.items():
        destination = workspace / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
    evaluator = tmp_path / "grade.py"
    evaluator.write_text(workflow["task"]["evaluator_files"]["grade.py"])
    return subprocess.run(
        [sys.executable, "-I", str(evaluator)],
        cwd=workspace,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_workflow_contract_fields():
    assert CONTRACT["contract"] == "C01"
    assert CONTRACT["evidence_class"] == "synthetic-contract-examples"
    assert len({flow["id"] for flow in WORKFLOWS}) == len(WORKFLOWS) == 2
    required = {
        "id", "buyer", "operator", "objective", "input", "failure", "intervention",
        "success", "task", "successful_workspace", "expected_checks", "interview_questions",
    }
    for workflow in WORKFLOWS:
        assert required <= workflow.keys()
        assert all(workflow[field] for field in required)
        assert len(workflow["interview_questions"]) >= 3


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda flow: flow["id"])
def test_examples_match_current_models(workflow):
    task = TaskSpec.model_validate(workflow["task"])
    intervention = Intervention.model_validate(workflow["intervention"])
    Action.model_validate(workflow["original_action"])
    assert intervention.step <= task.max_steps
    assert "@sha256:" in task.image
    assert set(workflow["successful_workspace"]) <= task.files.keys()
    assert task.evaluator_command == "python -I /evaluator/grade.py"
    assert {"exit_code", "output", "truncated"} <= workflow["original_result"].keys()


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda flow: flow["id"])
def test_original_fails_and_reference_repair_passes(workflow, tmp_path):
    original = evaluate_fixture(workflow, tmp_path, repaired=False)
    repaired = evaluate_fixture(workflow, tmp_path, repaired=True)
    assert original.returncode == workflow["expected_checks"]["initial_evaluator_exit_code"] == 1
    assert repaired.returncode == workflow["expected_checks"]["successful_evaluator_exit_code"] == 0
    assert repaired.stdout.strip() == "PASS"
    assert not original.stderr and not repaired.stderr


def test_smoke_success_does_not_imply_task_success(tmp_path):
    workflow = next(flow for flow in WORKFLOWS if flow["id"] == "automatic-intervention-evaluation")
    grade = evaluate_fixture(workflow, tmp_path, repaired=False)
    smoke = subprocess.run(
        [sys.executable, "-B", "smoke.py"],
        cwd=tmp_path / "original",
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert smoke.returncode == 0
    assert smoke.stdout == workflow["original_result"]["output"]
    assert grade.returncode == 1
