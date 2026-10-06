from unittest.mock import Mock, patch

import pytest
from docker.errors import DockerException

from agent_rewind.runner import DockerRunner
from agent_rewind.workspace import File


def make_runner(settings):
    client = Mock()
    client.info.return_value = {"Runtimes": {"runsc": {}}}
    with patch("agent_rewind.runner.docker.from_env", return_value=client):
        return DockerRunner(settings), client


def test_evaluator_start_failure_removes_created_container_and_volumes(settings):
    runner, client = make_runner(settings)
    workspace, grader = Mock(), Mock()
    client.volumes.create.side_effect = [workspace, grader]
    uploader = client.containers.create.return_value
    uploader.start.side_effect = DockerException("startup failed")
    uploader.attrs = {"State": {"Running": False, "Paused": False}}

    with pytest.raises(DockerException, match="startup failed"):
        runner.evaluate("image", {}, {"grade.py": File(b"print(42)")}, "grade", 10, lambda: None)

    uploader.remove.assert_called_once_with(force=True)
    workspace.remove.assert_called_once_with(force=True)
    grader.remove.assert_called_once_with(force=True)


def test_cleanup_attempts_remaining_resources_after_one_failure(settings):
    runner, _ = make_runner(settings)
    container, workspace, grader = Mock(), Mock(), Mock()
    container.reload.side_effect = DockerException("container unavailable")
    workspace.remove.side_effect = DockerException("volume busy")

    with pytest.raises(ExceptionGroup, match="Sandbox cleanup failed") as failure:
        runner._cleanup_resources([container], [workspace, grader])

    assert len(failure.value.exceptions) == 2
    grader.remove.assert_called_once_with(force=True)
