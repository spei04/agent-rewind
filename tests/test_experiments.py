from agent_rewind.experiments import Experiments
from agent_rewind.models import Intervention, StudyRequest
from agent_rewind.statistics import paired_evidence


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
