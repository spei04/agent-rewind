import pytest
from sqlalchemy import update

from agent_rewind.database import events
from agent_rewind.engine import read_events
from agent_rewind.models import Action, Intervention


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
    with engine.db.engine.begin() as connection:
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
