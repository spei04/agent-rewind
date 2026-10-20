"""Read-only bounded validation of initial run-projection progress, not byte availability."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..artifact_metadata import digest_value, identifier
from ..models import canonical, digest
from ..projection_source import MAX_PROJECTS
from ..run_projection import MAX_RUNS
from .inputs import _unique_object
from .ownership_state import MAX_CURSOR_BYTES, timestamp
from .schema import PROJECTION, MigrationRefused

PHASE = "run_index"


@dataclass(frozen=True)
class ProjectionState:
    cursor: dict[str, Any]
    source_digest: str
    count: int
    status: str


def inspect_projection_state(connection: Connection, row: dict[str, Any]) -> ProjectionState:
    try:
        if row["state"] != "ownership_complete" or row["_revision"] != PROJECTION:
            raise ValueError
        size_sql = (
            "SELECT octet_length(CAST(cursor AS TEXT)) FROM migration_progress "
            "WHERE revision=:revision AND phase=:phase"
            if connection.dialect.name == "postgresql"
            else "SELECT length(CAST(cursor AS BLOB)) FROM migration_progress "
            "WHERE revision=:revision AND phase=:phase"
        )
        parameters = {"revision": PROJECTION, "phase": PHASE}
        size: Any = connection.execute(text(size_sql), parameters).scalar_one_or_none()
        if type(size) is not int or not 0 < size <= MAX_CURSOR_BYTES:
            raise ValueError
        entries = (
            connection.execute(
                text(
                    "SELECT source_digest,CAST(cursor AS TEXT) AS cursor,"
                    "rows_verified,status,updated_at "
                    "FROM migration_progress WHERE revision=:revision AND phase=:phase LIMIT 2"
                ),
                parameters,
            )
            .mappings()
            .all()
        )
        if len(entries) != 1:
            raise ValueError
        entry = entries[0]
        cursor = json.loads(entry["cursor"], object_pairs_hook=_unique_object)
        if (
            set(cursor)
            != {
                "schema_version",
                "initialized_at",
                "cohort_digest",
                "scope_digest",
                "order_digest",
                "total_runs",
                "last_run_id",
                "evidence_digest",
                "projects",
            }
            or type(cursor["schema_version"]) is not int
            or cursor["schema_version"] != 1
        ):
            raise ValueError
        if len(canonical(cursor)) > MAX_CURSOR_BYTES:
            raise ValueError
        for value in (
            entry["source_digest"],
            cursor["cohort_digest"],
            cursor["scope_digest"],
            cursor["order_digest"],
        ):
            digest_value(value)
        timestamp(cursor["initialized_at"])
        timestamp(entry["updated_at"])
        total, count = cursor["total_runs"], entry["rows_verified"]
        if (
            type(total) is not int
            or not 0 <= total <= MAX_RUNS
            or type(count) is not int
            or not 0 <= count <= total
        ):
            raise ValueError
        if count == 0:
            if cursor["last_run_id"] is not None:
                raise ValueError
        else:
            identifier(cursor["last_run_id"])
        if cursor["evidence_digest"] is None:
            if count != 0 or total == 0:
                raise ValueError
        else:
            digest_value(cursor["evidence_digest"])
            if count == 0 and (total != 0 or cursor["evidence_digest"] != digest([])):
                raise ValueError
        projects = cursor["projects"]
        if not isinstance(projects, list) or not 1 <= len(projects) <= MAX_PROJECTS:
            raise ValueError
        for project in projects:
            identifier(project)
        if projects != sorted(set(projects)):
            raise ValueError
        if entry["status"] not in {"running", "complete"} or (entry["status"] == "complete") != (
            count == total
        ):
            raise ValueError
        return ProjectionState(cursor, entry["source_digest"], count, entry["status"])
    except (ValueError, KeyError, TypeError, RecursionError):
        raise MigrationRefused("projection_progress_invalid") from None
