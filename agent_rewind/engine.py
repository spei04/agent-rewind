"""Record and branch at tool boundaries; evaluate in a fresh workspace."""

from __future__ import annotations

import copy
import time
from contextlib import suppress
from typing import Any

from .artifacts import Artifacts
from .database import Database, JobStopped, identifier
from .models import Action, Intervention, TaskSpec, digest
from .policy import Policy
from .runner import Runner
from .workspace import File, summary


class Capture:
    """Literal redaction is bounded and cannot trigger regex denial of service."""

    def __init__(self, patterns: list[str]):
        self.patterns = [p for p in patterns if p]
        self.changed = False

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            for pattern in self.patterns:
                if pattern in value:
                    self.changed = True
                    value = value.replace(pattern, "[REDACTED]")
            return value
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        return value

    def workspace(self, files: dict[str, File]) -> dict[str, File]:
        cleaned = {}
        for path, file in files.items():
            data = file.data
            for pattern in self.patterns:
                if pattern.encode() in data:
                    self.changed = True
                    data = data.replace(pattern.encode(), b"[REDACTED]")
            cleaned[self.clean(path)] = File(data, file.mode, file.kind, file.mtime)
        return cleaned


class Engine:
    def __init__(
        self,
        db: Database,
        artifacts: Artifacts,
        runner: Runner,
        policy: Policy,
        job_id: str,
        owner: str,
        workspace_limit: int = 32 * 1024 * 1024,
    ):
        self.db, self.artifacts, self.runner, self.policy = db, artifacts, runner, policy
        self.job_id, self.owner, self.limit = job_id, owner, workspace_limit
        self.last_guard = 0.0

    def guard(self) -> None:
        if time.monotonic() - self.last_guard > 0.5:
            self.db.heartbeat(self.job_id, self.owner)
            self.last_guard = time.monotonic()

    def events(self, run_id: str, depth: int = 0) -> list[dict[str, Any]]:
        return read_events(self.db, self.artifacts, run_id, depth)

    def run(
        self,
        task: TaskSpec,
        parent_id: str | None = None,
        intervention: Intervention | None = None,
        seed: int | None = None,
    ) -> str:
        self.guard()
        run_id, seed = identifier(), task.seed if seed is None else seed
        files = {path: File(content.encode()) for path, content in task.files.items()}
        state, start, previous = self.policy.initial(task), 1, None
        capture = Capture(task.redact_patterns)
        pinned = self.runner.resolve_image(task.image)
        selected: dict[str, Any] | None = None
        if parent_id:
            if intervention is None:
                raise ValueError("A branch requires an intervention.")
            parent = self.db.get(parent_id, "run")
            if not parent["branchable"] or parent["status"] != "complete":
                raise ValueError("This run is incomplete or has redacted restore state.")
            if parent["task_digest"] != digest(task.model_dump()) or parent["image"] != pinned:
                raise ValueError("Task or environment identity changed.")
            if parent["policy"] != self.policy.identity():
                raise ValueError("Policy identity changed; use the original model configuration.")
            history = self.events(parent_id)
            if intervention.step > len(history):
                raise ValueError("The selected decision does not exist.")
            selected = history[intervention.step - 1]
            checkpoint = self.artifacts.json(selected["checkpoint"])
            if not checkpoint["branchable"]:
                raise ValueError("Checkpoint is not branchable.")
            files = self.artifacts.workspace(checkpoint["workspace"], self.limit)
            state = checkpoint["state"]
            start = intervention.step
            previous = history[start - 2]["hash"] if start > 1 else None
        manifest = {
            "name": task.name,
            "job_id": self.job_id,
            "parent_id": parent_id,
            "fork_step": start if parent_id else None,
            "seed": seed,
            "image": pinned,
            "policy": self.policy.identity(),
            "task_digest": digest(task.model_dump()),
            "task_ref": self.artifacts.put_json(task.model_dump()),
            "status": "running",
            "branchable": True,
            "head": previous,
            "steps": start - 1,
            "intervention": intervention.model_dump() if intervention else None,
        }
        self.db.add("run", manifest, run_id)
        try:
            for step in range(start, task.max_steps + 1):
                self.guard()
                before = dict(files)
                checkpoint = {
                    "schema": 1,
                    "workspace": self.artifacts.put_workspace(capture.workspace(files)),
                    "state": capture.clean(copy.deepcopy(state)),
                    "next_step": step,
                    "image": pinned,
                    "policy": self.policy.identity(),
                    "seed": seed,
                }
                checkpoint["branchable"] = not capture.changed
                checkpoint_ref = self.artifacts.put_json(checkpoint)
                if selected and step == start:
                    proposed = Action.model_validate(selected["proposed"])
                    decision = {"reused_from": parent_id, "step": step}
                else:
                    proposed, decision = self.policy.propose(state, step, seed)
                applied = (
                    Action.model_validate(selected["action"])
                    if selected and step == start
                    else proposed
                )
                if intervention and step == start and intervention.kind == "action":
                    assert intervention.action is not None
                    applied = intervention.action
                if (
                    selected
                    and step == start
                    and intervention
                    and intervention.kind == "tool_result"
                ):
                    # A result edit preserves the original tool's actual filesystem effects.
                    files = self.artifacts.workspace(selected["workspace_after"], self.limit)
                    actual = selected["actual_result"]
                else:
                    files, actual = self.runner.execute(
                        pinned, files, applied, task.command_timeout, self.guard
                    )
                observed = actual
                if intervention and step == start and intervention.kind == "tool_result":
                    assert intervention.result is not None
                    observed = intervention.result
                state = self.policy.observe(state, applied, observed)
                after_ref = self.artifacts.put_workspace(capture.workspace(files))
                event = capture.clean(
                    {
                        "schema": 1,
                        "run_id": run_id,
                        "step": step,
                        "previous": previous,
                        "checkpoint": checkpoint_ref,
                        "proposed": proposed.model_dump(),
                        "action": applied.model_dump(),
                        "actual_result": actual,
                        "observed_result": observed,
                        "decision": decision,
                        "workspace_after": after_ref,
                        "changes": summary(before, files),
                        "intervened": bool(intervention and step == start),
                    }
                )
                event["hash"] = digest(event)
                self.db.save_event(
                    self.job_id,
                    self.owner,
                    run_id,
                    step,
                    self.artifacts.put_json(event),
                    event["hash"],
                )
                previous = event["hash"]
                manifest.update(head=previous, steps=step, branchable=not capture.changed)
                self.db.finish_run(self.job_id, self.owner, run_id, manifest)
                if applied.tool == "finish":
                    break
            # Evaluator files live in a separate read-only mount, unavailable to agent steps.
            evaluation = self.runner.evaluate(
                pinned,
                files,
                {
                    path: File(content.encode(), 0o444)
                    for path, content in task.evaluator_files.items()
                },
                task.evaluator_command,
                task.command_timeout,
                self.guard,
            )
            manifest.update(
                status="complete",
                success=evaluation["exit_code"] == 0,
                evaluation_ref=self.artifacts.put_json(capture.clean(evaluation)),
                final_workspace=self.artifacts.put_workspace(capture.workspace(files)),
                branchable=not capture.changed,
            )
            self.db.finish_run(self.job_id, self.owner, run_id, manifest)
            return run_id
        except Exception:
            manifest.update(
                status="failed",
                branchable=False,
                error="Execution interrupted; inspect job status.",
            )
            # Expired owners cannot write; the job retains its failure status.
            with suppress(JobStopped):
                self.db.finish_run(self.job_id, self.owner, run_id, manifest)
            raise


def read_events(
    db: Database, artifacts: Artifacts, run_id: str, depth: int = 0
) -> list[dict[str, Any]]:
    if depth > 64:
        raise ValueError("Branch ancestry exceeds 64 levels.")
    run = db.get(run_id, "run")
    prefix: list[dict[str, Any]] = []
    if run["parent_id"]:
        prefix = [
            e
            for e in read_events(db, artifacts, run["parent_id"], depth + 1)
            if e["step"] < run["fork_step"]
        ]
    result = prefix + [artifacts.json(row["artifact"]) for row in db.event_refs(run_id)]
    previous = None
    for step, event in enumerate(result, 1):
        if (
            event["step"] != step
            or event["previous"] != previous
            or digest({k: v for k, v in event.items() if k != "hash"}) != event["hash"]
        ):
            raise ValueError("Event chain verification failed.")
        previous = event["hash"]
    # A worker can commit an event just before its manifest update. Reading during
    # execution permits that one-step lag; completed runs must match exactly.
    if run["status"] == "complete" and previous != run["head"]:
        raise ValueError("Run head verification failed.")
    return result
