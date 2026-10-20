"""Pure initial projection rules; these values are not publication authority."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any

from .artifact_graph import VerifiedCapture
from .artifact_metadata import ArtifactError, identifier
from .models import digest

MAX_RUNS = 10000
MAX_COHORT_BYTES = 32 * 1024 * 1024
MAX_CAPTURE_BYTES = 1024 * 1024 * 1024
MAX_CAPTURE_QUERIES = 250000


def utc_created(value: Any) -> datetime:
    """Round the exact stored binary value, with no intermediate float product."""
    if type(value) not in {float, int} or (type(value) is float and not math.isfinite(value)):
        raise ArtifactError("projection_timestamp_invalid")
    try:
        micros = round(Fraction(value) * 1000000)
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros)
    except (OverflowError, ValueError):
        raise ArtifactError("projection_timestamp_invalid") from None


@dataclass(frozen=True)
class RunProjection:
    run_id: str
    project_id: str
    created_at: datetime
    status: str
    branchable: bool
    parent_id: str | None
    event_head: str | None
    projection_reason: str | None


def classify_capture(
    project_id: str, capture: dict[str, Any], verified: VerifiedCapture
) -> RunProjection:
    """Classify verified initial history, never a current generation-fenced job.

    Callers must perform fresh scope/source/evidence validation and transaction
    fencing separately. Mutating an existing projection is not this operation.
    """
    if verified.source_digest != digest(capture):
        raise ArtifactError("projection_source_changed")
    manifest = capture["manifest"]
    identifier(project_id)
    identifier(manifest["id"])
    parent = manifest["parent_id"]
    if parent is not None:
        identifier(parent)
    status = verified.status
    reason = None
    if status == "running":
        # A legacy owner/lease is not proof of the unavailable compatible fence.
        status, reason = "incomplete", "unfenced_execution"
    return RunProjection(
        manifest["id"],
        project_id,
        utc_created(manifest["created"]),
        status,
        verified.branchable,
        parent,
        verified.event_head,
        reason,
    )
