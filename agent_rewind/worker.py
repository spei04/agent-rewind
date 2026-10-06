import contextlib
import threading
import time
from typing import Any

from .artifacts import Artifacts
from .config import Settings
from .database import Database, JobStopped, identifier
from .engine import Engine
from .experiments import Experiments
from .models import BranchRequest, StudyRequest, TaskSpec
from .policy import ChatPolicy
from .runner import DockerRunner


def work_once(settings: Settings, db: Database, artifacts: Artifacts) -> bool:
    owner = identifier()
    job = db.claim(owner)
    if job is None:
        return False
    done = threading.Event()
    started = time.monotonic()

    def lease() -> None:
        while not done.wait(10):
            try:
                if time.monotonic() - started > settings.max_job_seconds:
                    db.cancel(job["id"], "worker:deadline")
                    return
                db.heartbeat(job["id"], owner)
            except JobStopped:
                return

    heartbeat = threading.Thread(target=lease, daemon=True)
    heartbeat.start()
    result: dict[str, Any] | None = None
    error = None
    try:
        runner = DockerRunner(settings)
        runner.cleanup(max(3600, settings.max_job_seconds + 600))
        policy = ChatPolicy(settings, lambda amount: db.reserve(job["id"], owner, amount))
        engine = Engine(
            db, artifacts, runner, policy, job["id"], owner, settings.workspace_mb * 1024 * 1024
        )
        payload = artifacts.json(job["payload"])
        if job["kind"] == "run":
            result = {"run_id": engine.run(TaskSpec.model_validate(payload))}
        elif job["kind"] == "branch":
            branch = BranchRequest.model_validate(payload)
            parent = db.get(branch.parent_id, "run")
            task = TaskSpec.model_validate(artifacts.json(parent["task_ref"]))
            result = {
                "run_id": engine.run(task, branch.parent_id, branch.intervention, branch.seed)
            }
        elif job["kind"] in {"study", "investigate"}:
            experiment = Experiments(engine)
            if job["kind"] == "investigate":
                payload["candidates"] = [
                    c.model_dump() for c in experiment.discover(payload["run_id"])
                ]
            result = {"study_id": experiment.study(StudyRequest.model_validate(payload))}
        else:
            raise ValueError("Unknown job kind.")
    except Exception as exc:
        # Exception bodies from providers or containers can contain private data.
        error = f"{type(exc).__name__}: job failed; partial runs and studies remain available."
    finally:
        with contextlib.suppress(JobStopped):
            db.complete_job(job["id"], owner, artifacts.put_json(result) if result else None, error)
        done.set()
        heartbeat.join(timeout=2)
    return True


def serve_worker(settings: Settings) -> None:
    db, artifacts = Database(settings), Artifacts(settings)
    while True:
        if not work_once(settings, db, artifacts):
            time.sleep(1)
