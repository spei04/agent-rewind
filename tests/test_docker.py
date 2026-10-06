import os

import pytest

from agent_rewind.models import Action
from agent_rewind.runner import DockerRunner
from agent_rewind.workspace import File

pytestmark = pytest.mark.skipif(
    os.environ.get("REWIND_TEST_DOCKER") != "1", reason="Opt-in Docker integration"
)


@pytest.fixture
def runner(settings):
    settings.sandbox_runtime = os.environ.get("REWIND_TEST_RUNTIME", "runc")
    settings.allow_insecure_runtime = settings.sandbox_runtime == "runc"
    settings.allowed_images = "python:3.12-slim"
    instance = DockerRunner(settings)
    yield instance
    instance.client.close()


def test_actual_code_execution_and_round_trip(runner):
    image = runner.resolve_image("python:3.12-slim")
    files, result = runner.execute(
        image,
        {"app.py": File(b"print(6 * 7)\n")},
        Action(tool="shell", command="python app.py && echo restored > note.txt"),
        15,
        lambda: None,
    )
    assert result["exit_code"] == 0 and "42" in result["output"]
    assert files["note.txt"].data == b"restored\n"
    _, next_result = runner.execute(
        image, files, Action(tool="shell", command="cat note.txt"), 15, lambda: None
    )
    assert next_result["output"].strip() == "restored"


def test_evaluator_is_read_only_and_not_available_to_agent(runner):
    image = runner.resolve_image("python:3.12-slim")
    _, result = runner.execute(
        image, {}, Action(tool="shell", command="test ! -e /evaluator/grade.py"), 15, lambda: None
    )
    assert result["exit_code"] == 0
    result = runner.evaluate(
        image,
        {},
        {"grade.py": File(b"print(42)\n", 0o444)},
        "python /evaluator/grade.py && ! echo hacked > /evaluator/grade.py",
        15,
        lambda: None,
    )
    assert result["exit_code"] == 0 and "42" in result["output"]


def test_timeout_and_escape_rejection(runner):
    image = runner.resolve_image("python:3.12-slim")
    with pytest.raises(TimeoutError):
        runner.execute(image, {}, Action(tool="shell", command="sleep 60"), 1, lambda: None)
    with pytest.raises(ValueError, match="links"):
        runner.execute(
            image, {}, Action(tool="shell", command="ln -s /etc/passwd stolen"), 10, lambda: None
        )
    _, result = runner.execute(
        image,
        {},
        Action(tool="shell", command="test ! -e /var/run/docker.sock && ! touch /root/escape"),
        10,
        lambda: None,
    )
    assert result["exit_code"] == 0
