"""Scoped SQL capture used by the preparatory publication coordinator."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, select, text
from sqlalchemy.engine import Connection

from .artifact_graph import MAX_DEPTH, MAX_JSON_BYTES
from .artifact_metadata import ArtifactError, digest_value
from .database import events, jobs, keys, records
from .models import canonical
from .scoped_lineage import Lineage
from .scoped_repositories import (
    ProjectContext,
    ScopedRepositories,
    _byte_length,
    _Reads,
    _scope,
    members,
    organizations,
    projects,
    scopes,
)


def _lock_closure(reads: _Reads, run_id: str) -> None:
    """Lock only the existing bounded validated dependency closure.

    Future graph-source producers needing project and job/run locks must take all
    affected projects in sorted order first, then serialize on owning job/run rows,
    including event insert/reassignment/deletion, ancestry or
    source identity changes and by_job membership. Reassignment locks both owners
    in a consistent order. Existing-row locks alone do not protect phantoms under
    READ COMMITTED. Producers must revalidate under those locks and never mutate a
    complete source graph. Current legacy writers do not establish this contract.
    """

    def dependencies() -> set[tuple[str, str]]:
        lineage = Lineage(reads.record, reads.job, reads.by_job)
        lineage.validate("run", run_id)
        return set(lineage.records) | {("job", job) for job in lineage.jobs}

    before = dependencies()
    for kind, resource_id in sorted(before):
        source = jobs if kind == "job" else records
        row = reads.connection.execute(
            select(source.c.id)
            .select_from(source.join(scopes, _scope(kind, source.c.id, reads.context)))
            .where(source.c.id == resource_id)
            .with_for_update(read=True)
        ).first()
        if row is None:
            raise ArtifactError("publication_source_changed")
    if dependencies() != before:
        raise ArtifactError("publication_source_changed")


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

    A writer must acquire project exclusion before job/run exclusion and before
    this locking capture whenever its operation requires both lock families.
    PostgreSQL share locks keep current grant/source/scope rows stable to commit.
    SQLite requires the caller's writer transaction, not an implicit DDL step.
    """
    repositories._authorize(connection, context, action)
    if lock and connection.dialect.name == "postgresql":
        connection.execute(
            select(members)
            .select_from(
                members.join(projects, members.c.project_id == projects.c.id).join(
                    organizations, organizations.c.id == projects.c.organization_id
                )
            )
            .where(
                organizations.c.id == context.organization_id,
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
    if lock and connection.dialect.name == "postgresql":
        _lock_closure(reads, run_id)
        repositories._authorize(connection, context, action)
    result = capture_rows(reads, run_id, lock=lock)
    repositories._authorize(connection, context, action)
    return result


def capture_rows(
    reads: _Reads, run_id: str, *, lock: bool = False, complete_only: bool = True
) -> dict[str, Any]:
    """Scoped SQL evidence only; caller must establish operator or principal authority."""
    connection = reads.connection
    lineage: list[dict[str, Any]] = []
    own_events: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    current = run_id
    closure = Lineage(reads.record, reads.job, reads.by_job)
    manifest = closure.validate("run", run_id)
    retained = 0
    while current:
        if current in seen or len(seen) > MAX_DEPTH:
            raise ArtifactError("artifact_graph_invalid")
        seen.add(current)
        run = closure.records[("run", current)]
        if (complete_only or current != run_id) and run.get("status") != "complete":
            raise ArtifactError("artifact_graph_invalid")
        if current == run_id:
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
                "status",
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
