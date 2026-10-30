import traceback

import pytest
from sqlalchemy import select, update

from agent_rewind.database import JobStopped, events, jobs
from agent_rewind.engine import read_events
from agent_rewind.models import Action, Intervention
from agent_rewind.policy import ModelCallFailure
from agent_rewind.sqlite_ownership import owned_begin, owned_connect


def test_result_intervention_changes_future_policy_without_mutating_parent(engine, task):
    original = engine.run(task)
    before = engine.events(original)
    branch = engine.run(
        task,
        original,
        Intervention(step=1, kind="tool_result", result={"exit_code": 0, "output": "repair"}),
        seed=92,
    )
    assert not engine.db.get(original)["success"]
    assert engine.db.get(branch)["success"]
    assert engine.events(original) == before
    assert engine.events(branch)[0]["actual_result"] == before[0]["actual_result"]
    assert engine.events(branch)[0]["observed_result"]["output"] == "repair"


def test_action_intervention_and_shared_prefix(engine, task):
    original = engine.run(task)
    branch = engine.run(
        task,
        original,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    assert engine.db.get(branch)["success"]
    assert engine.events(branch)[0] == engine.events(original)[0]
    assert len(engine.db.event_refs(branch)) == 2


def test_noop_preserves_outcome_and_source_workspace(engine, task):
    original = engine.run(task)
    event = engine.events(original)[0]
    branch = engine.run(
        task, original, Intervention(step=1, kind="tool_result", result=event["observed_result"])
    )
    assert engine.db.get(branch)["final_workspace"] == engine.db.get(original)["final_workspace"]
    assert not engine.db.get(branch)["success"]


def test_redaction_refuses_incomplete_restore(engine, task):
    task = task.model_copy(update={"redact_patterns": ["old instructions"]})
    original = engine.run(task)
    assert not engine.db.get(original)["branchable"]
    assert "old instructions" not in str(engine.events(original))
    with pytest.raises(ValueError, match="redacted"):
        engine.run(task, original, Intervention(step=1, kind="tool_result", result={}))


def test_chain_tampering_is_detected(engine, task):
    original = engine.run(task)
    event = engine.events(original)[0]
    event["actual_result"]["output"] = "forged"
    with owned_begin(engine.db.engine) as connection:
        connection.execute(
            update(events)
            .where(events.c.run_id == original, events.c.step == 1)
            .values(artifact=engine.artifacts.put_json(event))
        )
    with pytest.raises(ValueError, match="chain"):
        read_events(engine.db, engine.artifacts, original)


def test_changed_environment_or_policy_refuses_branch(engine, task):
    original = engine.run(task)
    changed = task.model_copy(update={"instruction": "different objective"})
    with pytest.raises(ValueError, match="identity changed"):
        engine.run(changed, original, Intervention(step=1, kind="tool_result", result={}))


def test_result_edit_preserves_real_tool_side_effect(engine, task):
    original = engine.run(task)
    source_event = engine.events(original)[1]
    branch = engine.run(
        task,
        original,
        Intervention(step=2, kind="tool_result", result={"exit_code": 0, "output": "repair"}),
    )
    assert engine.events(branch)[1]["workspace_after"] == source_event["workspace_after"]
    assert not engine.db.get(branch)["success"]  # Editing feedback cannot undo a write.


def test_branch_of_branch_keeps_previously_replaced_action(engine, task):
    original = engine.run(task)
    child = engine.run(
        task,
        original,
        Intervention(
            step=2,
            kind="action",
            action=Action(tool="write_file", path="source.py", content="correct"),
        ),
    )
    grandchild = engine.run(
        task,
        child,
        Intervention(
            step=2, kind="tool_result", result={"exit_code": 0, "output": "new observation"}
        ),
    )
    assert engine.events(grandchild)[1]["action"]["content"] == "correct"
    assert engine.db.get(grandchild)["success"]


@pytest.mark.parametrize("kind", ["action", "tool_result"])
def test_incomplete_internal_intervention_fails_without_corrupting_parent(engine, task, kind):
    original = engine.run(task)
    before = engine.events(original)
    # Internal callers can bypass model validation; the execution boundary still rejects it.
    intervention = Intervention.model_construct(step=1, kind=kind, action=None, result=None)
    with pytest.raises(ValueError, match="requires"):
        engine.run(task, original, intervention)
    assert engine.events(original) == before


@pytest.mark.parametrize(
    "known,publication",
    [
        pytest.param(False, "success", id="unknown-saved"),
        pytest.param(True, "success", id="known-saved"),
        pytest.param(False, "failure", id="unknown-publication-failure"),
        pytest.param(True, "failure", id="known-publication-failure"),
        pytest.param(False, "lease", id="unknown-expired-owner"),
    ],
)
def test_model_failure_preserves_hold_primary_and_no_effects(
    engine, task, monkeypatch, known, publication
):
    failure = ModelCallFailure(
        "invalid_action" if known else "invalid_usage",
        100,
        usage={"prompt_tokens": 0, "completion_tokens": 0} if known else None,
        reported_micro_usd=0 if known else None,
    )
    runs = []
    add = engine.db.add

    def recorded(kind, data, record_id=None):
        result = add(kind, data, record_id)
        if kind == "run":
            runs.append(result)
        return result

    def propose(*args):
        engine.db.reserve(engine.job_id, engine.owner, 100)
        raise failure

    def forbidden(*args):
        pytest.fail("Rejected model decision must not execute or grade")

    if publication != "success":

        def fail_publication(*args):
            if publication == "lease":
                raise JobStopped("private-publication-payload")
            raise RuntimeError("private-publication-payload")

        monkeypatch.setattr(engine.db, "finish_run", fail_publication)
    monkeypatch.setattr(engine.db, "add", recorded)
    monkeypatch.setattr(engine.policy, "propose", propose)
    monkeypatch.setattr(engine.runner, "execute", forbidden)
    monkeypatch.setattr(engine.runner, "evaluate", forbidden)
    with pytest.raises(ModelCallFailure) as caught:
        engine.run(task)
    assert caught.value is failure
    assert len(runs) == 1 and engine.db.event_refs(runs[0]) == []
    with owned_connect(engine.db.engine) as connection:
        hold = connection.execute(
            select(jobs.c.reserved).where(jobs.c.id == engine.job_id)
        ).scalar_one()
    assert hold == 100
    assert failure.publication_failures == ([] if publication == "success" else ["run"])
    assert "private-publication-payload" not in "".join(traceback.format_exception(failure))
    manifest = engine.db.get(runs[0])
    if publication == "success":
        assert manifest["status"] == "failed" and manifest["branchable"] is False
        assert manifest["model_call_failure"] == failure.evidence()
    else:
        assert manifest["status"] == "running"  # Never claim the failed publication committed.
