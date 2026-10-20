"""Malformed capture graphs must not gain completion or restore eligibility."""

import json
from copy import deepcopy

import pytest
from publication_fixture import make_capture

from agent_rewind.artifact_graph import verify_run_graph
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.models import canonical, digest


@pytest.fixture
def graph(settings, task):
    capture = make_capture(settings)
    run = capture.run(task)
    intent = capture.intent(run)
    root = json.loads(intent.envelope)
    blobs = {
        obj.digest: capture.artifacts.get(obj.digest)
        for obj in intent.objects
        if obj.digest != intent.root_digest
    }
    yield root, blobs
    capture.db.engine.dispose()


def verify(root, blobs):
    return verify_run_graph(canonical(root), lambda ref, limit: blobs[ref.digest])


def rewrite_events(root, blobs, modify):
    previous = None
    for index, row in enumerate(root["events"]):
        event = json.loads(blobs[row["artifact"]])
        event["previous"] = previous
        modify(index, event)
        event["hash"] = digest({k: v for k, v in event.items() if k != "hash"})
        row["hash"] = event["hash"]
        row["artifact"] = digest(event)
        blobs[row["artifact"]] = canonical(event)
        previous = event["hash"]
    root["manifest"]["head"] = previous


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "jobroot",
        "incomplete",
        "head",
        "step",
        "owner",
        "chainhash-as-artifact",
        "finalworkspace",
        "cycle",
        "tasksteps",
    ],
)
def test_declared_graph_contract_refuses(graph, mutation):
    root, blobs = graph
    if mutation == "unknown":
        root["publication_schema"] = 2
    elif mutation == "jobroot":
        root["job_payload"] = "e" * 64
    elif mutation == "incomplete":
        root["manifest"]["status"] = "failed"
    elif mutation == "head":
        root["manifest"]["head"] = "e" * 64
    elif mutation == "step":
        root["events"][0]["step"] = 2
    elif mutation == "owner":
        root["events"][0]["run_id"] = "e" * 32
    elif mutation == "chainhash-as-artifact":
        root["events"][0]["artifact"] = root["events"][0]["hash"]
    elif mutation == "finalworkspace":
        checkpoint = json.loads(
            blobs[json.loads(blobs[root["events"][0]["artifact"]])["checkpoint"]]
        )
        root["manifest"]["final_workspace"] = checkpoint["workspace"]
    elif mutation == "cycle":
        root["lineage"].append(deepcopy(root["lineage"][0]))
    else:
        task = json.loads(blobs[root["manifest"]["task_ref"]])
        task["max_steps"] = 1
        key = digest(task)
        blobs[key] = canonical(task)
        root["manifest"]["task_ref"] = key
        root["manifest"]["task_digest"] = key
    with pytest.raises(ArtifactError):
        verify(root, blobs)


def test_checkpoint_restore_claim_and_continuity_refuse(graph):
    root, blobs = graph

    def edit(index, event):
        if index == 1:
            checkpoint = json.loads(blobs[event["checkpoint"]])
            checkpoint["branchable"] = False
            key = digest(checkpoint)
            blobs[key] = canonical(checkpoint)
            event["checkpoint"] = key

    rewrite_events(root, blobs, edit)
    with pytest.raises(ArtifactError, match="graph_invalid"):
        verify(root, blobs)


def test_discontinuous_workspace_refuses_even_with_valid_event_chain(graph):
    root, blobs = graph
    first = json.loads(blobs[root["events"][0]["artifact"]])
    workspace = json.loads(blobs[first["checkpoint"]])["workspace"]

    def edit(index, event):
        if index == 1:
            checkpoint = json.loads(blobs[event["checkpoint"]])
            checkpoint["workspace"] = workspace
            key = digest(checkpoint)
            blobs[key] = canonical(checkpoint)
            event["checkpoint"] = key

    rewrite_events(root, blobs, edit)
    with pytest.raises(ArtifactError, match="graph_invalid"):
        verify(root, blobs)


def test_opaque_decision_digest_is_not_a_reference(graph):
    root, blobs = graph

    def edit(index, event):
        event["decision"] = {"opaque": "d" * 64}

    rewrite_events(root, blobs, edit)
    assert verify(root, blobs).root_digest == digest(root)


@pytest.mark.parametrize(
    "payload", [b'{"schema":1,"schema":1,"files":{}}', b'{"schema":1,"files":{},"number":1e999}']
)
def test_duplicate_members_and_overflow_refuse(graph, payload):
    import hashlib

    root, blobs = graph
    key = hashlib.sha256(payload).hexdigest()
    blobs[key] = payload

    def edit(index, event):
        event["workspace_after"] = key

    rewrite_events(root, blobs, edit)
    root["manifest"]["final_workspace"] = key
    with pytest.raises(ArtifactError):
        verify(root, blobs)


@pytest.mark.parametrize(
    "name,value",
    [("MAX_OBJECTS", 2), ("MAX_EDGES", 2), ("MAX_BYTES", 1024), ("MAX_WORKSPACE_ENTRIES", 1)],
)
def test_graph_work_caps_fail_closed(graph, monkeypatch, name, value):
    import agent_rewind.artifact_graph as module

    root, blobs = graph
    monkeypatch.setattr(module, name, value)
    with pytest.raises(ArtifactError, match="graph_limit"):
        verify(root, blobs)


def test_reused_workspaces_traverse_once_under_edge_bound(graph, monkeypatch):
    import agent_rewind.artifact_graph as module

    root, blobs = graph
    # Three checkpoints and after-snapshots share the captured workspace. The
    # bound covers its actual graph, not repeated traversal of identical files.
    monkeypatch.setattr(module, "MAX_EDGES", 30)
    assert verify(root, blobs).root_digest == digest(root)
