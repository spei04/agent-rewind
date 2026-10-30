import traceback

import pytest
from sqlalchemy import select

from agent_rewind.database import JobStopped, jobs, records
from agent_rewind.experiments import Experiments, StudyInterrupted, locate
from agent_rewind.models import Intervention, StudyRequest
from agent_rewind.policy import ModelCallFailure
from agent_rewind.sqlite_ownership import owned_connect
from agent_rewind.statistics import paired_evidence


def test_premature_finish_remains_available_for_intervention_discovery():
    ranked = locate(
        [
            {
                "step": 1,
                "action": {"tool": "finish"},
                "actual_result": {"exit_code": 0},
                "changes": {},
            }
        ]
    )
    assert len(ranked) == 1
    assert ranked[0]["step"] == 1


def test_zero_discordance_does_not_produce_zero_width_interval():
    result = paired_evidence([{"control_success": False, "treatment_success": False}] * 30)
    assert result["effect"] == 0
    assert result["interval"][0] < 0 < result["interval"][1]
    assert result["exact_p_value"] == 1


def test_strong_effect_and_missing_trials():
    pairs = [{"control_success": False, "treatment_success": True}] * 30
    result = paired_evidence(pairs)
    assert result["interval"][0] > 0
    assert result["verdict"] == "improvement supported"
    missing = paired_evidence(pairs + [{"control_success": None, "treatment_success": None}])
    assert missing["missing"] == 1
    assert missing["verdict"] == "inconclusive"
    assert missing["missing_outcome_bounds"][0] < 1


def test_screening_and_confirmation_are_disjoint(engine, task):
    original = engine.run(task)
    request = StudyRequest(
        run_id=original,
        candidates=[
            Intervention(
                step=1,
                kind="tool_result",
                result={"exit_code": 0, "output": "repair"},
                label="Correct the stale observation",
            )
        ],
        screening_trials=2,
        confirmation_trials=5,
        seed=11,
        budget_usd=100.0,
    )
    study = engine.db.get(Experiments(engine).study(request), "study")
    assert study["status"] == "complete"
    discovery = {p["seed"] for p in study["candidates"][0]["pairs"]}
    confirmation = {p["seed"] for p in study["confirmation"]["pairs"]}
    assert not discovery & confirmation
    assert study["winner_digest"]
    assert study["confirmation"]["evidence"]["effect"] == 1
    assert all(p["control_run"] != p["treatment_run"] for p in study["confirmation"]["pairs"])


def test_missing_pair_does_not_duplicate_remaining_trials(engine, task):
    original = engine.run(task)
    request = StudyRequest(
        run_id=original,
        candidates=[
            Intervention(step=1, kind="tool_result", result={"exit_code": 0, "output": "repair"})
        ],
        screening_trials=2,
        confirmation_trials=5,
    )
    execute = engine.run
    calls = 0

    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError("temporary test failure")
        return execute(*args, **kwargs)

    engine.run = flaky
    result = engine.db.get(Experiments(engine).study(request))
    assert len(result["confirmation"]["pairs"]) == 5
    assert result["confirmation"]["evidence"]["missing"] == 1
    assert result["confirmation"]["evidence"]["verdict"] == "inconclusive"


@pytest.mark.parametrize(
    "phase,arm,known",
    [
        pytest.param("screening", 1, False, id="screen-first-unknown"),
        pytest.param("screening", 2, False, id="screen-second-unknown"),
        pytest.param("confirmation", 1, False, id="confirm-first-unknown"),
        pytest.param("confirmation", 2, False, id="confirm-second-unknown"),
        pytest.param("screening", 1, True, id="screen-first-known"),
        pytest.param("confirmation", 2, True, id="confirm-second-known"),
    ],
)
def test_terminal_model_failure_stops_the_entire_study(
    engine, task, monkeypatch, phase, arm, known
):
    original = engine.run(task)
    request = StudyRequest(
        run_id=original,
        candidates=[
            Intervention(step=1, kind="tool_result", result={"exit_code": 0, "output": "repair"}),
            Intervention(step=1, kind="tool_result", result={"exit_code": 1, "output": "other"}),
        ],
        screening_trials=2,
        confirmation_trials=5,
    )
    failure = ModelCallFailure(
        "invalid_action" if known else "invalid_usage",
        101,
        usage={"prompt_tokens": 1, "completion_tokens": 1} if known else None,
        reported_micro_usd=10 if known else None,
    )
    execute = engine.run
    calls = []
    trigger = arm if phase == "screening" else 8 + arm

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == trigger:
            engine.db.reserve(engine.job_id, engine.owner, 101)
            raise failure
        return execute(*args, **kwargs)

    monkeypatch.setattr(engine, "run", run)
    with pytest.raises(StudyInterrupted) as caught:
        Experiments(engine).study(request)
    assert caught.value.__cause__ is failure
    assert len(calls) == trigger
    with owned_connect(engine.db.engine) as connection:
        rows = (
            connection.execute(select(records.c.data).where(records.c.kind == "study"))
            .scalars()
            .all()
        )
        hold = connection.execute(
            select(jobs.c.reserved).where(jobs.c.id == engine.job_id)
        ).scalar_one()
    assert len(rows) == 1 and hold == 101
    study = rows[0]
    assert study["status"] == "incomplete"
    assert study["request"] == request.model_dump()
    assert study["model_call_failure"] == failure.evidence()
    if phase == "screening":
        assert len(study["candidates"]) == 1
        assert study["winner"] is None and study["confirmation"] is None
        pairs = study["candidates"][0]["pairs"]
        assert len(pairs) == 2
    else:
        assert len(study["candidates"]) == 2 and study["winner_digest"]
        assert all(len(c["pairs"]) == 2 for c in study["candidates"])
        pairs = study["confirmation"]["pairs"]
        assert len(pairs) == 5
        assert study["confirmation"]["evidence"]["verdict"] == "incomplete study"
    assert pairs[0]["model_call_failure"] == failure.evidence()
    assert (
        sum(pairs[0][key] is not None for key in ("control_success", "treatment_success"))
        == arm - 1
    )
    assert all(
        p["error"] == "not_attempted" and p["control_success"] is p["treatment_success"] is None
        for p in pairs[1:]
    )


@pytest.mark.parametrize("publication", ["failure", "lease"])
def test_incomplete_study_publication_cannot_mask_terminal_cause(
    engine, task, monkeypatch, publication
):
    original = engine.run(task)
    request = StudyRequest(
        run_id=original,
        candidates=[Intervention(step=1, kind="tool_result", result={"output": "repair"})],
        screening_trials=2,
        confirmation_trials=5,
    )
    failure = ModelCallFailure("invalid_usage", 100)
    calls = []
    finish = engine.db.finish_run

    def failed_run(*args, **kwargs):
        calls.append("run")
        engine.db.reserve(engine.job_id, engine.owner, 100)
        raise failure

    def failed_save(job, owner, record, data):
        if data["status"] == "incomplete":
            if publication == "lease":
                raise JobStopped("private-study-publication")
            raise RuntimeError("private-study-publication")
        return finish(job, owner, record, data)

    monkeypatch.setattr(engine, "run", failed_run)
    monkeypatch.setattr(engine.db, "finish_run", failed_save)
    with pytest.raises(StudyInterrupted) as caught:
        Experiments(engine).study(request)
    assert calls == ["run"] and caught.value.__cause__ is failure
    assert failure.publication_failures == ["study"]
    assert len(caught.value.pairs) == 2
    assert "private-study-publication" not in "".join(traceback.format_exception(caught.value))


def test_discovery_stops_after_one_terminal_paid_proposal(engine, task, monkeypatch):
    original = engine.run(task)
    events = engine.events(original)
    checkpoint = engine.artifacts.json
    failure = ModelCallFailure(
        "invalid_action",
        100,
        usage={"prompt_tokens": 0, "completion_tokens": 0},
        reported_micro_usd=0,
    )
    calls = []

    def with_messages(reference):
        value = checkpoint(reference)
        if "state" in value:
            value["state"]["messages"] = []
        return value

    def propose(*args):
        calls.append("dispatch")
        engine.db.reserve(engine.job_id, engine.owner, 100)
        raise failure

    monkeypatch.setattr(engine.artifacts, "json", with_messages)
    monkeypatch.setattr(engine.policy, "propose", propose)
    with pytest.raises(ModelCallFailure) as caught:
        Experiments(engine).discover(original, count=3)
    assert caught.value is failure and calls == ["dispatch"]
    assert engine.events(original) == events
    with owned_connect(engine.db.engine) as connection:
        hold = connection.execute(
            select(jobs.c.reserved).where(jobs.c.id == engine.job_id)
        ).scalar_one()
    assert hold == 100
