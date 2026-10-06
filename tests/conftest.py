import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from agent_rewind.artifacts import Artifacts
from agent_rewind.config import Settings
from agent_rewind.database import Database
from agent_rewind.models import Action, TaskSpec
from agent_rewind.workspace import File


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'metadata.sqlite'}",
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        bootstrap_key=SecretStr("test-admin-key-" + "a" * 32),
    )


@pytest.fixture
def storage(settings):
    db = Database(settings)
    db.migrate()
    yield db, Artifacts(settings)
    db.engine.dispose()


@pytest.fixture
def task():
    return TaskSpec(
        name="test fixture",
        instruction="Repair the function",
        image="fixture-image",
        files={"source.py": "broken", "README.md": "old instructions"},
        evaluator_files={"grade.py": "grader"},
        evaluator_command="grade",
        max_steps=3,
    )


class FixturePolicy:
    """Test-only policy. No result from this class is a model benchmark."""

    def identity(self):
        return {"adapter": "test-fixture-v1", "seed_supported": True}

    def initial(self, task):
        return {"repair": False}

    def propose(self, state, step, seed):
        if step == 1:
            action = Action(tool="read_file", path="README.md")
        elif step == 2:
            action = Action(
                tool="write_file",
                path="source.py",
                content="correct" if state["repair"] else "broken",
            )
        else:
            action = Action(tool="finish")
        return action, {"fixture": True}

    def observe(self, state, action, result):
        return {"repair": state["repair"] or result.get("output") == "repair"}


class FixtureRunner:
    def resolve_image(self, image):
        return image

    def execute(self, image, files, action, timeout, guard):
        guard()
        output = ""
        if action.tool == "write_file":
            files = {**files, action.path: File(action.content.encode())}
        elif action.tool == "read_file":
            output = files[action.path].data.decode()
        return files, {"exit_code": 0, "output": output}

    def evaluate(self, image, files, evaluator, command, timeout, guard):
        return {"exit_code": 0 if files["source.py"].data == b"correct" else 1, "output": "graded"}


@pytest.fixture
def engine(storage):
    from agent_rewind.engine import Engine

    db, artifacts = storage
    job = db.enqueue("run", artifacts.put_json({}), 100, "test")
    db.claim("test-worker")
    return Engine(db, artifacts, FixtureRunner(), FixturePolicy(), job, "test-worker")
