"""Actual capture verification and independent timestamp/projection oracles."""

import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest
import test_artifact_graph as graph_cases

from agent_rewind.artifact_graph import verify_run_capture
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.run_projection import classify_capture, utc_created

graph = graph_cases.graph
PROJECT = "a" * 32


def source(root):
    return {key: deepcopy(root[key]) for key in ("manifest", "lineage", "events")}


def verify(capture, blobs):
    return verify_run_capture(capture, lambda ref, limit: blobs[ref.digest])


def test_verified_task_failure_is_complete(graph):
    root, blobs = graph
    capture = source(root)
    assert capture["manifest"]["success"] is False
    verified = verify(capture, blobs)
    projection = classify_capture(PROJECT, capture, verified)
    assert projection.status == "complete" and projection.branchable
    assert projection.event_head == capture["events"][-1]["hash"]
    assert projection.event_head != capture["events"][-1]["artifact"]


@pytest.mark.parametrize("status", ["failed", "incomplete", "running"])
@pytest.mark.parametrize("lag", [0, 1])
def test_partial_capture_uses_verified_event_head_without_completion(graph, status, lag):
    root, blobs = graph
    capture = source(root)
    manifest = capture["manifest"]
    manifest["status"] = capture["lineage"][-1]["status"] = status
    for key in ("success", "evaluation_ref", "final_workspace"):
        del manifest[key]
    manifest["steps"] -= lag
    manifest["head"] = capture["events"][manifest["steps"] - 1]["hash"]
    verified = verify(capture, blobs)
    projection = classify_capture(PROJECT, capture, verified)
    assert projection.status == ("incomplete" if status == "running" else status)
    assert not projection.branchable
    assert projection.event_head == capture["events"][-1]["hash"]
    assert projection.projection_reason == ("unfenced_execution" if status == "running" else None)


@pytest.mark.parametrize("status", ["failed", "running"])
def test_empty_partial_capture_has_no_invented_event(graph, status):
    root, blobs = graph
    capture = source(root)
    capture["events"] = []
    manifest = capture["manifest"]
    manifest.update(status=status, steps=0, head=None)
    if status == "failed":
        manifest["error"] = "fixed synthetic failure"
    capture["lineage"][-1]["status"] = status
    for key in ("success", "evaluation_ref", "final_workspace"):
        del manifest[key]
    projection = classify_capture(PROJECT, capture, verify(capture, blobs))
    assert projection.status == ("failed" if status == "failed" else "incomplete")
    assert projection.event_head is None
    assert not projection.branchable


def test_capture_evidence_cannot_be_reused_for_changed_source(graph):
    root, blobs = graph
    capture = source(root)
    verified = verify(capture, blobs)
    capture["manifest"]["created"] += 1
    with pytest.raises(ArtifactError, match="projection_source_changed"):
        classify_capture(PROJECT, capture, verified)


@pytest.mark.parametrize(
    "value,micros", [(1 / 128, 7812), (3 / 128, 23438), (-1 / 128, -7812), (-3 / 128, -23438)]
)
def test_true_binary_half_microsecond_ties_are_even(value, micros):
    assert utc_created(value) == datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros)


@pytest.mark.parametrize("direction", [-math.inf, math.inf])
def test_modern_epoch_near_tie_uses_independent_rational_oracle(direction):
    value = math.nextafter(1700000000 + 1 / 128, direction)
    numerator, denominator = value.as_integer_ratio()
    exact = Fraction(numerator * 1000000, denominator)
    quotient, remainder = divmod(exact.numerator, exact.denominator)
    micros = quotient + int(
        2 * remainder > exact.denominator or (2 * remainder == exact.denominator and quotient % 2)
    )
    assert utc_created(value) == datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), "1", b"1", True, 1e100, -1e100, 10**400]
)
def test_invalid_original_timestamp_refuses_without_coercion(value):
    with pytest.raises(ArtifactError, match="projection_timestamp_invalid"):
        utc_created(value)


def test_failed_terminal_write_does_not_turn_verified_evaluation_into_completion(graph):
    root, blobs = graph
    capture = source(root)
    capture["manifest"].update(status="failed", branchable=False, error="fixed synthetic failure")
    capture["lineage"][-1].update(status="failed", branchable=False)
    projection = classify_capture(PROJECT, capture, verify(capture, blobs))
    assert projection.status == "failed" and not projection.branchable


def test_projection_capture_metadata_is_bounded_before_reader(graph, monkeypatch):
    import agent_rewind.artifact_graph as module

    root, _ = graph
    capture = source(root)
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 10)
    with pytest.raises(ArtifactError, match="artifact_graph_limit"):
        verify_run_capture(capture, lambda *_: pytest.fail("oversized metadata reached reader"))
