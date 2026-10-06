"""Candidate discovery, fixed screening, and independent confirmation."""

import contextlib
import copy
import random
from typing import Any

from .database import BudgetExceeded, JobStopped, identifier
from .engine import Engine
from .models import Action, Intervention, StudyRequest, TaskSpec, digest
from .statistics import paired_evidence


def locate(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank suspicious observations. These scores are hypotheses, not attribution."""
    ranked = []
    seen: dict[str, int] = {}
    for event in events:
        action = event["action"]
        stopped = action["tool"] == "finish"
        signature = digest(action)
        repeated = seen.get(signature, 0)
        seen[signature] = repeated + 1
        failed = event["actual_result"].get("exit_code", 0) != 0
        changed = bool(event["changes"])
        reason = (
            "Agent stopped at this decision"
            if stopped
            else "Repeated action with no new progress"
            if repeated
            else (
                "Tool returned a failure"
                if failed
                else "Workspace changed before failure"
                if changed
                else "Earlier information may have redirected the agent"
            )
        )
        score = (
            4 * int(failed)
            + 3 * int(stopped)
            + 2 * min(repeated, 3)
            + int(changed)
            + 1 / event["step"]
        )
        ranked.append({"step": event["step"], "score": round(score, 3), "reason": reason})
    return sorted(ranked, key=lambda r: (-r["score"], r["step"]))


class Experiments:
    def __init__(self, engine: Engine):
        self.engine = engine

    def discover(self, run_id: str, count: int = 3) -> list[Intervention]:
        engine = self.engine
        run = engine.db.get(run_id, "run")
        if not run["branchable"] or run["status"] != "complete":
            raise ValueError("Discovery requires a complete, branchable run.")
        if run["success"]:
            raise ValueError("Select a failed run to investigate.")
        history = engine.events(run_id)
        proposals = []
        for location in locate(history)[:count]:
            event = history[location["step"] - 1]
            checkpoint = engine.artifacts.json(event["checkpoint"])
            state = copy.deepcopy(checkpoint["state"])
            if "messages" not in state:
                raise ValueError("Automatic proposal generation requires the chat policy adapter.")
            state["messages"].append(
                {
                    "role": "user",
                    "content": "This run failed its independent evaluator. "
                    "Propose one different "
                    "action at this decision, without accessing evaluator files. "
                    "Original action: "
                    + str(event["action"])
                    + ". Diagnostic hypothesis: "
                    + location["reason"],
                }
            )
            engine.guard()
            replacement, _ = engine.policy.propose(state, location["step"], run["seed"] + 777)
            if replacement != Action.model_validate(event["action"]):
                proposals.append(
                    Intervention(
                        step=location["step"],
                        kind="action",
                        action=replacement,
                        label=location["reason"],
                    )
                )
        if not proposals:
            raise ValueError(
                "Discovery produced no distinct intervention. Supply a manual candidate."
            )
        # Include an unchanged observation as a negative control. It is screened
        # but cannot be selected as the intervention for confirmation.
        first = history[proposals[0].step - 1]
        proposals.append(
            Intervention(
                step=first["step"],
                kind="tool_result",
                result=first["observed_result"],
                label="Negative control: unchanged observation",
            )
        )
        return proposals

    def study(self, request: StudyRequest) -> str:
        engine = self.engine
        original = engine.db.get(request.run_id, "run")
        task = TaskSpec.model_validate(engine.artifacts.json(original["task_ref"]))
        history = engine.events(request.run_id)
        for candidate in request.candidates:
            if candidate.step > len(history):
                raise ValueError("Candidate refers to a nonexistent decision.")
        study_id = identifier()
        report: dict[str, Any] = {
            "source_run": request.run_id,
            "job_id": engine.job_id,
            "status": "running",
            "method": "paired-fixed-sample-v1",
            "seed_support": original["policy"].get("seed_supported", False),
            "screening_trials": request.screening_trials,
            "confirmation_trials": request.confirmation_trials,
            "candidates": [],
            "winner": None,
            "confirmation": None,
            "protocol_digest": digest(request.model_dump()),
            "request": request.model_dump(),
            "claim_scope": "This task, checkpoint, policy, environment image, and evaluator only.",
        }
        engine.db.add("study", report, study_id)

        def save() -> None:
            engine.db.finish_run(engine.job_id, engine.owner, study_id, report)

        def trials(
            candidate: Intervention, n: int, phase: int, pairs: list[dict[str, Any]]
        ) -> list[dict[str, Any]]:
            event = history[candidate.step - 1]
            control = Intervention(
                step=candidate.step,
                kind=candidate.kind,
                action=Action.model_validate(event["action"])
                if candidate.kind == "action"
                else None,
                result=event["observed_result"] if candidate.kind == "tool_result" else None,
                label="Unchanged control",
            )
            for index in range(n):
                seed = request.seed + phase + index
                pair: dict[str, Any] = {
                    "seed": seed,
                    "control_success": None,
                    "treatment_success": None,
                }
                pairs.append(pair)
                order = [("control", control), ("treatment", candidate)]
                random.Random(seed).shuffle(order)
                pair["order"] = [name for name, _ in order]
                save()
                try:
                    for arm, intervention in order:
                        run_id = engine.run(task, request.run_id, intervention, seed)
                        run = engine.db.get(run_id, "run")
                        pair[arm + "_run"] = run_id
                        pair[arm + "_success"] = run["success"]
                        save()
                except Exception as exc:
                    pair["error"] = type(exc).__name__
                    # Preserve every planned trial. Missing outcomes cannot support a claim.
                    if isinstance(exc, BudgetExceeded | JobStopped):
                        pairs.extend(
                            {
                                "seed": request.seed + phase + j,
                                "control_success": None,
                                "treatment_success": None,
                                "error": "not_attempted",
                            }
                            for j in range(index + 1, n)
                        )
                        raise StudyInterrupted(pairs, type(exc).__name__) from exc
                save()
            return pairs

        try:
            for candidate in request.candidates:
                event = history[candidate.step - 1]
                unchanged = (
                    candidate.action.model_dump() == event["action"]
                    if candidate.action
                    else candidate.result == event["observed_result"]
                )
                entry: dict[str, Any] = {
                    "intervention": candidate.model_dump(),
                    "pairs": [],
                    "negative_control": unchanged,
                }
                report["candidates"].append(entry)
                try:
                    entry["pairs"] = trials(
                        candidate, request.screening_trials, 1000, entry["pairs"]
                    )
                except StudyInterrupted as exc:
                    entry["pairs"] = exc.pairs
                    raise
                entry["evidence"] = paired_evidence(entry["pairs"])
                save()
            eligible = [
                e
                for e in report["candidates"]
                if not e["negative_control"] and e["evidence"]["missing"] == 0
            ]
            if not eligible:
                raise ValueError("No candidate completed screening.")
            winner = max(
                eligible, key=lambda e: (e["evidence"]["interval"][0], -e["intervention"]["step"])
            )
            report["winner"] = winner["intervention"]
            report["winner_digest"] = digest(winner["intervention"])
            # Commit the chosen candidate before any confirmation call.
            save()
            report["confirmation"] = {"pairs": []}
            try:
                pairs = trials(
                    Intervention.model_validate(winner["intervention"]),
                    request.confirmation_trials,
                    100000,
                    report["confirmation"]["pairs"],
                )
            except StudyInterrupted as exc:
                report["confirmation"]["pairs"] = exc.pairs
                raise
            report["confirmation"] = {"pairs": pairs, "evidence": paired_evidence(pairs)}
            report["status"] = "complete"
        except Exception as exc:
            report["status"] = "incomplete"
            report["error"] = type(exc).__name__
            if report["confirmation"]:
                report["confirmation"]["evidence"] = paired_evidence(
                    report["confirmation"]["pairs"]
                )
                report["confirmation"]["evidence"]["verdict"] = "incomplete study"
            for entry in report["candidates"]:
                entry["evidence"] = paired_evidence(entry["pairs"])
            with contextlib.suppress(JobStopped):
                save()
            raise
        save()
        return study_id


class StudyInterrupted(RuntimeError):
    def __init__(self, pairs: list[dict[str, Any]], reason: str):
        super().__init__(reason)
        self.pairs = pairs
