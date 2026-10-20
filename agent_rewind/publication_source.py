"""Scoped SQL capture used by the preparatory publication coordinator."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, select, text
from sqlalchemy.engine import Connection

from .artifact_graph import MAX_DEPTH, MAX_JSON_BYTES
from .artifact_metadata import ArtifactError, digest_value
from .database import events, keys, records
from .models import canonical
from .scoped_repositories import (
    ProjectContext,
    ScopedRepositories,
    _byte_length,
    _Reads,
    _scope,
    members,
    scopes,
)


def _snapshot(
    repositories: ScopedRepositories,
    connection: Connection,
    context: ProjectContext,
    run_id: str,
    *,
    lock: bool = False,
    action: str = "record",
) -> dict[str, Any]:
    """Capture immutable input, using the same scoped policy as ordinary reads.

    A writer must acquire its job/transaction exclusion before a locking capture.
    PostgreSQL share locks keep current grant/source/scope rows stable to commit.
    SQLite requires the caller's writer transaction, not an implicit DDL step.
    """
    repositories._authorize(connection, context, action)
    if lock and connection.dialect.name == "postgresql":
        connection.execute(
            select(members)
            .where(
                members.c.project_id == context.project_id,
                members.c.principal_id == context.principal_id,
            )
            .with_for_update(read=True)
        ).all()
        if context.principal_id.startswith("api-key:"):
            connection.execute(
                select(keys.c.id)
                .select_from(keys.join(scopes, _scope("key", keys.c.id, context)))
                .where(keys.c.id == context.principal_id[8:])
                .with_for_update(read=True)
            ).all()
    reads = _Reads(connection, context)
    lineage: list[dict[str, Any]] = []
    own_events: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    current = run_id
    manifest: dict[str, Any] | None = None
    retained = 0
    while current:
        if current in seen or len(seen) > MAX_DEPTH:
            raise ArtifactError("artifact_graph_invalid")
        seen.add(current)
        if lock and connection.dialect.name == "postgresql":
            connection.execute(
                select(records.c.id)
                .select_from(records.join(scopes, _scope("run", records.c.id, context)))
                .where(records.c.id == current)
                .with_for_update(read=True)
            ).all()
            connection.execute(
                select(scopes)
                .where(
                    scopes.c.project_id == context.project_id,
                    scopes.c.resource_kind == "run",
                    scopes.c.resource_id == current,
                )
                .with_for_update(read=True)
            ).all()
        run = reads.resource("run", current)
        if manifest is None:
            manifest = run
            retained += len(canonical(manifest))
        item = {
            key: run[key]
            for key in (
                "id",
                "parent_id",
                "fork_step",
                "seed",
                "image",
                "policy",
                "task_digest",
                "branchable",
            )
        }
        retained += len(canonical(item))
        if retained > MAX_JSON_BYTES:
            raise ArtifactError("artifact_graph_limit")
        lineage.append(item)
        byte_size = sum(
            (func.coalesce(_byte_length(connection, field), 0) for field in events.c), literal(0)
        )
        # Reject malformed SQLite dynamic cells in SQL before materialization.
        if connection.execute(
            select(events.c.run_id).where(events.c.run_id == current, byte_size > 256).limit(1)
        ).first():
            raise ArtifactError("artifact_graph_invalid")
        query = (
            select(events)
            .where(events.c.run_id == current, byte_size <= 256)
            .order_by(events.c.step)
            .limit(101)
        )
        if lock and connection.dialect.name == "postgresql":
            query = query.with_for_update(read=True)
        rows: list[dict[str, Any]] = []
        for row in connection.execute(query).mappings():
            if len(rows) >= 100:
                raise ArtifactError("artifact_graph_limit")
            if (
                row["run_id"] != current
                or type(row["step"]) is not int
                or not 1 <= row["step"] <= 100
            ):
                raise ArtifactError("artifact_graph_invalid")
            digest_value(row["artifact"])
            digest_value(row["hash"])
            value = dict(row)
            retained += len(canonical(value))
            if retained > MAX_JSON_BYTES:
                raise ArtifactError("artifact_graph_limit")
            rows.append(value)
        own_events[current] = rows
        current = run["parent_id"]
    lineage.reverse()
    history: list[dict[str, Any]] = []
    for item in lineage:
        if item["parent_id"]:
            fork = item["fork_step"]
            if type(fork) is not int or not 1 <= fork <= len(history):
                raise ArtifactError("artifact_graph_invalid")
            history = [row for row in history if row["step"] < fork]
        history.extend(own_events[item["id"]])
    repositories._authorize(connection, context, action)
    return {"manifest": manifest, "lineage": lineage, "events": history}


def snapshot(
    repositories: ScopedRepositories,
    connection: Connection,
    context: ProjectContext,
    run_id: str,
    *,
    lock: bool = False,
    action: str = "record",
) -> dict[str, Any]:
    try:
        return _snapshot(repositories, connection, context, run_id, lock=lock, action=action)
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("artifact_graph_invalid") from None


def lock_ancestor_ref(
    connection: Connection, project: str, owner: str, role: str, artifact: str
) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "SELECT artifact_id FROM artifact_refs WHERE project_id=:project "
                "AND owner_kind='run' AND owner_id=:owner AND role=:role AND "
                "artifact_id=:artifact FOR SHARE"
            ),
            {"project": project, "owner": owner, "role": role, "artifact": artifact},
        ).all()
