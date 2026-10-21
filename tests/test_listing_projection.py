"""Finite suppression uses actual legacy manifest/job fields and exact timestamps."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from agent_rewind.errors import Fault
from agent_rewind.listing_projection import IndexEntry, entry, summary
from agent_rewind.run_projection import RunProjection

CREATED = 1700000000.125
VALUE = IndexEntry(
    RunProjection(
        "1" * 32,
        "2" * 32,
        datetime.fromtimestamp(CREATED, UTC),
        "complete",
        True,
        None,
        "e" * 64,
        None,
    ),
    1,
)


def source():
    return {
        "id": "1" * 32,
        "created": CREATED,
        "job_id": "3" * 32,
        "parent_id": None,
        "status": "complete",
        "branchable": True,
        "head": "e" * 64,
        "success": False,
    }


def job():
    return {
        "id": "3" * 32,
        "status": "succeeded",
        "cancel": False,
        "owner": None,
        "lease_until": None,
    }


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "failed", "cancelled"])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("restorable", [False, True])
@pytest.mark.parametrize("success", [False, True])
def test_complete_execution_truth_table(status, cancel, restorable, success):
    result = summary(
        VALUE,
        {**source(), "branchable": restorable, "success": success},
        {**job(), "status": status, "cancel": cancel},
    )
    assert result["status"] == "complete"
    assert result["branchable"] is (status == "succeeded" and not cancel and restorable)
    assert set(result) == {
        "id",
        "project_id",
        "created_at",
        "status",
        "branchable",
        "parent_id",
        "event_head",
    }
    assert "success" not in result


@pytest.mark.parametrize("stored", ["running", "failed", "incomplete"])
@pytest.mark.parametrize("current", ["running", "failed", "complete"])
def test_partial_never_promotes_or_claims_live_authority(stored, current):
    value = replace(VALUE, value=replace(VALUE.value, status=stored, branchable=False))
    result = summary(
        value,
        {**source(), "status": current, "head": None},
        {**job(), "status": "running", "owner": "worker", "lease_until": 2e9},
    )
    assert result["status"] == ("incomplete" if stored == "running" else stored)
    assert result["branchable"] is False
    assert result["event_head"] == "e" * 64  # Preserve verified partial head, despite manifest lag.


def test_projection_redaction_is_not_reenabled_by_source():
    value = replace(VALUE, value=replace(VALUE.value, branchable=False))
    assert summary(value, source(), job())["branchable"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "4" * 32),
        ("created", CREATED + 1),
        ("parent_id", "4" * 32),
        ("job_id", "4" * 32),
        ("head", "f" * 64),
        ("status", "failed"),
        ("status", "running"),
        ("branchable", 1),
        ("success", 0),
        ("success", None),
    ],
)
def test_source_contradiction_or_shape_refuses(field, value):
    with pytest.raises(Fault, match="dependency_unavailable"):
        summary(VALUE, {**source(), field: value}, job())


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "unknown"),
        ("cancel", 0),
        ("owner", b"worker"),
        ("owner", "x" * 65),
        ("owner", "x\0"),
        ("lease_until", float("inf")),
        ("lease_until", True),
        ("lease_until", -1),
    ],
)
def test_malformed_current_job_refuses(field, value):
    with pytest.raises(Fault, match="dependency_unavailable"):
        summary(VALUE, source(), {**job(), field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("branchable", "false"),
        ("branchable", 1.0),
        ("branchable", 2),
        ("published_seq", True),
        ("published_seq", 0),
        ("published_seq", 2**63),
        ("event_head", "e" * 64 + "\0"),
        ("run_id", "1" * 32 + "\0"),
        ("created_at", "2023-11-14T23:13:20.125000+01:00"),
    ],
)
def test_selected_projection_has_strict_native_types(field, value):
    row = VALUE.receipt()
    row[field] = value
    with pytest.raises(Fault, match="dependency_unavailable"):
        entry(row, "2" * 32)
