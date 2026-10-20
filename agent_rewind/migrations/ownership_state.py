"""Read-only validation of the ownership revision's durable initialization intent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from .inputs import Grant, _unique_object, empty_source_digest, validate_mapping
from .ownership_inputs import validate_fresh
from .ownership_lineage import MAX_RESOURCES
from .schema import OWNERSHIP, MigrationRefused, canonical, checksum

PHASE = "ownership"
MAX_CURSOR_BYTES = 65536


@dataclass(frozen=True)
class OwnershipState:
    cursor: dict[str, Any]
    source_digest: str
    count: int
    status: str
    organization_id: str
    project_id: str
    project_name: str
    grants: list[Grant]


def timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("invalid timestamp")
    return value


def resolve_intent(
    row: dict[str, Any], intent: dict[str, Any]
) -> tuple[str, str, str, list[Grant]]:
    if row["source_kind"] == "fresh":
        if set(intent) != {"source_kind", "input"} or intent["source_kind"] != "fresh":
            raise ValueError("invalid fresh intent")
        parsed = validate_fresh(intent["input"])
        if parsed.installation_key != row["installation_key"]:
            raise ValueError("installation identity differs")
        return (
            parsed.organization_id,
            parsed.project_id,
            parsed.project_name,
            parsed.principal_grants,
        )
    if intent != {"source_kind": "legacy", "mapping_digest": row["mapping_digest"]}:
        raise ValueError("legacy intent differs")
    mapping = validate_mapping(row["mapping"])
    return mapping.organization_id, mapping.project_id, "Legacy project", mapping.principal_grants


def inspect_ownership_state(connection: Connection, row: dict[str, Any]) -> OwnershipState:
    # SQL-side size check prevents corrupted metadata being materialized before its bound.
    size_query = (
        "SELECT octet_length(cursor::text) FROM migration_progress "
        "WHERE revision=:revision AND phase=:phase"
        if connection.dialect.name == "postgresql"
        else "SELECT length(CAST(cursor AS BLOB)) FROM migration_progress "
        "WHERE revision=:revision AND phase=:phase"
    )
    size = connection.execute(
        text(size_query), {"revision": OWNERSHIP, "phase": PHASE}
    ).scalar_one_or_none()
    if not isinstance(size, int) or size > MAX_CURSOR_BYTES:
        raise MigrationRefused("ownership_progress_invalid")
    entries = (
        connection.execute(
            text(
                "SELECT source_digest,CAST(cursor AS TEXT) AS cursor,"
                "rows_verified,status,updated_at "
                "FROM migration_progress WHERE revision=:revision AND phase=:phase LIMIT 2"
            ),
            {"revision": OWNERSHIP, "phase": PHASE},
        )
        .mappings()
        .all()
    )
    try:
        if len(entries) != 1:
            raise ValueError("missing progress")
        progress = entries[0]
        cursor = json.loads(progress["cursor"], object_pairs_hook=_unique_object)
        if (
            set(cursor)
            != {
                "schema_version",
                "intent",
                "intent_digest",
                "closure_digest",
                "total_resources",
                "last_resource",
                "initialized_at",
            }
            or type(cursor["schema_version"]) is not int
            or cursor["schema_version"] != 1
        ):
            raise ValueError("invalid cursor")
        if len(canonical(cursor)) > MAX_CURSOR_BYTES:
            raise ValueError("oversize cursor")
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in (
                cursor["intent_digest"],
                cursor["closure_digest"],
                progress["source_digest"],
            )
        ):
            raise ValueError("invalid digest")
        if checksum(cursor["intent"]) != cursor["intent_digest"]:
            raise ValueError("changed intent")
        timestamp(cursor["initialized_at"])
        timestamp(progress["updated_at"])
        total, count = cursor["total_resources"], progress["rows_verified"]
        if (
            type(total) is not int
            or not 0 <= total <= MAX_RESOURCES
            or type(count) is not int
            or not 0 <= count <= total
        ):
            raise ValueError("invalid count")
        if count == 0:
            if cursor["last_resource"] is not None:
                raise ValueError("invalid empty cursor")
        elif (
            not isinstance(cursor["last_resource"], list)
            or len(cursor["last_resource"]) != 2
            or cursor["last_resource"][0] not in {"run", "study", "job", "key"}
            or not isinstance(cursor["last_resource"][1], str)
            or not re.fullmatch(r"[0-9a-f]{32}", cursor["last_resource"][1])
        ):
            raise ValueError("invalid last resource")
        if progress["status"] not in {"running", "complete"}:
            raise ValueError("invalid progress state")
        complete = progress["status"] == "complete"
        if complete != (count == total) or complete != (row["state"] == "ownership_complete"):
            raise ValueError("inconsistent completion")
        organization, project, name, grants = resolve_intent(row, cursor["intent"])
        if row["source_kind"] == "fresh" and progress["source_digest"] != empty_source_digest():
            raise ValueError("fresh source provenance differs")
        if row["source_kind"] == "legacy":
            mapping = validate_mapping(row["mapping"])
            if progress["source_digest"] != mapping.source_dataset_digest:
                raise ValueError("source provenance differs")
        if (complete or row["source_kind"] == "legacy") and (
            row["organization_id"] != organization or row["project_id"] != project
        ):
            raise ValueError("targets differ")
        state = OwnershipState(
            cursor,
            progress["source_digest"],
            count,
            progress["status"],
            organization,
            project,
            name,
            grants,
        )
        verify_principals(connection, row, state)
        return state
    except (ValueError, TypeError, KeyError, RecursionError):
        raise MigrationRefused("ownership_progress_invalid") from None


def expected_members(connection: Connection, state: OwnershipState) -> list[tuple[Any, ...]]:
    result: list[tuple[Any, ...]] = []
    at = timestamp(state.cursor["initialized_at"])
    key_ids = [g.principal_id[8:] for g in state.grants if g.principal_id.startswith("api-key:")]
    keys: dict[str, tuple[Any, Any]] = {}
    if key_ids:
        rows = connection.execute(
            text("SELECT id,revoked,expires FROM api_keys WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": key_ids},
        )
        keys = {r.id: (r.revoked, r.expires) for r in rows}
    for grant in state.grants:
        revoked = None
        if grant.principal_id.startswith("api-key:"):
            key = keys.get(grant.principal_id[8:])
            if key is None:
                raise ValueError("missing granted key")
            if key[0] or key[1] <= at.timestamp():
                revoked = at
        result.append(
            (state.project_id, grant.principal_id, grant.role, revoked, grant.legacy_default)
        )
    return sorted(result)


def verify_principals(connection: Connection, row: dict[str, Any], state: OwnershipState) -> None:
    organizations = connection.execute(text("SELECT * FROM organizations LIMIT 2")).mappings().all()
    projects = connection.execute(text("SELECT * FROM projects LIMIT 2")).mappings().all()
    at = timestamp(state.cursor["initialized_at"])
    if (
        len(organizations) != 1
        or organizations[0]["id"] != state.organization_id
        or organizations[0]["installation_key"] != row["installation_key"]
        or timestamp(organizations[0]["created_at"]) != at
        or len(projects) != 1
        or projects[0]["id"] != state.project_id
        or projects[0]["organization_id"] != state.organization_id
        or projects[0]["name"] != state.project_name
        or timestamp(projects[0]["created_at"]) != at
    ):
        raise ValueError("ownership identity differs")
    members = connection.execute(
        text(
            "SELECT project_id,principal_id,role,revoked_at,legacy_default "
            "FROM project_memberships ORDER BY project_id,principal_id LIMIT 257"
        )
    ).all()
    actual = [
        (r[0], r[1], r[2], timestamp(r[3]) if r[3] is not None else None, bool(r[4]))
        for r in members
    ]
    if actual != expected_members(connection, state):
        raise ValueError("membership differs")
