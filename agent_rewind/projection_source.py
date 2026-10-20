"""Bounded operator-only SQL cohort capture, separate from artifact reads and writes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, func, literal, select, text
from sqlalchemy.engine import Connection, Engine

from .artifact_metadata import ArtifactError, identifier
from .database import events, jobs, records
from .migrations.inputs import source_digest
from .migrations.ownership_lineage import relational_closure
from .migrations.service import _secure_engine
from .models import canonical, digest
from .publication_source import capture_rows
from .run_projection import MAX_CAPTURE_QUERIES, MAX_COHORT_BYTES, MAX_RUNS
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import _byte_length, _Reads

MAX_PROJECTS = 128
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_EVENT_BYTES = 256


@dataclass(frozen=True)
class _OperatorScope:
    project_id: str


@dataclass
class QueryBudget:
    used: int = 0

    @contextmanager
    def observe(self, connection: Connection) -> Iterator[None]:
        def before(*args: Any) -> None:
            self.used += 1
            if self.used > MAX_CAPTURE_QUERIES:
                raise ArtifactError("projection_query_limit")

        event.listen(connection, "before_cursor_execute", before)
        try:
            yield
        finally:
            event.remove(connection, "before_cursor_execute", before)


@contextmanager
def readonly_source(engine: Engine, budget: QueryBudget) -> Iterator[Connection]:
    """One consistent SQL snapshot; it is closed before any operator byte reader."""
    _secure_engine(engine)
    with engine.connect() as connection:
        previous: int | None = None
        try:
            if connection.dialect.name == "sqlite":
                previous = connection.exec_driver_sql("PRAGMA query_only").scalar_one()
                connection.exec_driver_sql("BEGIN")
                connection.exec_driver_sql("PRAGMA query_only=ON")
            else:
                if (
                    getattr(connection.connection.driver_connection, "autocommit", None)
                    is not False
                ):
                    raise ArtifactError("projection_transaction_required")
                connection.begin()
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.exec_driver_sql("SET LOCAL search_path TO public, pg_temp")
            with budget.observe(connection):
                yield connection
        finally:
            connection.rollback()
            if previous is not None:
                connection.exec_driver_sql(f"PRAGMA query_only={int(previous)}")
                connection.rollback()


@dataclass(frozen=True)
class CohortIdentity:
    source_digest: str
    scope_digest: str
    order_digest: str
    cohort_digest: str
    total_runs: int


@dataclass(frozen=True)
class SQLCohort:
    identity: CohortIdentity
    order: tuple[str, ...]
    captures: dict[str, tuple[str, dict[str, Any]]]
    retained_bytes: int
    project_ids: tuple[str, ...]


def _ordered(parents: dict[str, str | None]) -> tuple[str, ...]:
    ordered: list[str] = []
    complete: set[str] = set()
    for first in sorted(parents):
        path: list[str] = []
        current: str | None = first
        while current is not None and current not in complete:
            if current not in parents or current in path or len(path) > 64:
                raise ArtifactError("projection_source_invalid")
            path.append(current)
            current = parents[current]
        for current in reversed(path):
            complete.add(current)
            ordered.append(current)
    return tuple(ordered)


def read_cohort(connection: Connection, *, byte_limit: int = MAX_COHORT_BYTES) -> SQLCohort:
    """Capture a capped offline cohort; no reader, authorization claim or SQL writes.

    Actual scoped lineage is checked before any artifact can be requested. Original
    table contents and scopes are separate immutable identities. The caller owns a
    consistent read snapshot or the exclusive migration transaction.
    """
    try:
        return _read_cohort(connection, byte_limit=byte_limit)
    except ArtifactError:
        raise
    except (ResourceNotFound, KeyError, TypeError, ValueError, RecursionError):
        raise ArtifactError("projection_source_invalid") from None


def _read_cohort(connection: Connection, *, byte_limit: int) -> SQLCohort:
    retained = 0

    def retain(value: Any) -> None:
        nonlocal retained
        size = len(canonical(value))
        if retained + size > byte_limit:
            raise ArtifactError("projection_cohort_limit")
        retained += size

    # Tighter projection limits apply before the broader legacy source hasher or
    # relational parser fetches any body. This includes SQLite dynamic cells.
    for source, limit in (
        (records, MAX_RECORD_BYTES),
        (jobs, MAX_RECORD_BYTES),
        (events, MAX_EVENT_BYTES),
    ):
        size = sum(
            (func.coalesce(_byte_length(connection, field), 0) for field in source.c), literal(0)
        )
        if connection.execute(
            select(literal(1)).select_from(source).where(size > limit).limit(1)
        ).first():
            raise ArtifactError("projection_source_limit")
    original = source_digest(connection)
    closure = relational_closure(connection)
    # The existing closure has its own resource/edge/retained-byte bounds. Reject
    # SQLite dynamic fields in SQL before fetching additive scope identity cells.
    if connection.execute(
        text(
            "SELECT 1 FROM resource_scopes WHERE length(resource_kind)>20 "
            "OR length(resource_id)>32 OR length(project_id)>32 LIMIT 1"
        )
    ).first():
        raise ArtifactError("projection_source_invalid")
    if connection.execute(
        text(
            "SELECT 1 FROM projects p LEFT JOIN organizations o ON o.id=p.organization_id "
            "WHERE length(p.id)>32 OR length(p.organization_id)>32 OR o.id IS NULL LIMIT 1"
        )
    ).first():
        raise ArtifactError("projection_source_invalid")
    projects = connection.execute(
        text("SELECT id,organization_id FROM projects ORDER BY id LIMIT 129")
    ).all()
    if not projects or len(projects) > MAX_PROJECTS:
        raise ArtifactError("projection_cohort_limit")
    project_ids: set[str] = set()
    project_rows: list[list[str]] = []
    for project_id, organization_id in projects:
        if not isinstance(project_id, str) or not isinstance(organization_id, str):
            raise ArtifactError("projection_source_invalid")
        identifier(project_id)
        identifier(organization_id)
        project_identity = [project_id, organization_id]
        retain(project_identity)
        project_rows.append(project_identity)
        project_ids.add(project_id)
    scoped: dict[tuple[str, str], str] = {}
    scope_rows = []
    rows = connection.execute(
        text(
            "SELECT resource_kind,resource_id,project_id FROM resource_scopes "
            "ORDER BY resource_kind,resource_id LIMIT :bound"
        ).execution_options(stream_results=True, yield_per=1, max_row_buffer=1),
        {"bound": len(closure.resources) + 1},
    )
    for index, row in enumerate(rows):
        if index >= len(closure.resources) or tuple(row[:2]) != closure.resources[index]:
            raise ArtifactError("projection_source_invalid")
        kind, resource_id, project_id = tuple(row)
        if (
            not isinstance(kind, str)
            or not isinstance(resource_id, str)
            or not isinstance(project_id, str)
        ):
            raise ArtifactError("projection_source_invalid")
        if project_id not in project_ids:
            raise ArtifactError("projection_source_invalid")
        retain(list(row))
        scoped[(kind, resource_id)] = project_id
        scope_rows.append(list(row))
    if len(scoped) != len(closure.resources):
        raise ArtifactError("projection_source_invalid")
    scope_identity = digest({"projects": project_rows, "resources": scope_rows})
    runs = [resource_id for kind, resource_id in closure.resources if kind == "run"]
    if len(runs) > MAX_RUNS:
        raise ArtifactError("projection_cohort_limit")
    del closure, scope_rows, project_rows
    captures: dict[str, tuple[str, dict[str, Any]]] = {}
    parents: dict[str, str | None] = {}
    for run_id in runs:
        project = scoped[("run", run_id)]
        value = capture_rows(
            _Reads(connection, _OperatorScope(project)), run_id, complete_only=False
        )
        parent = value["manifest"]["parent_id"]
        if parent is not None and scoped.get(("run", parent)) != project:
            raise ArtifactError("projection_source_invalid")
        retain([run_id, project, value])
        captures[run_id] = (project, value)
        parents[run_id] = parent
    order = _ordered(parents)
    order_identity = digest(order)
    cohort_identity = digest(
        {
            "source": original,
            "scope": scope_identity,
            "order": order_identity,
            "captures": [digest(captures[run]) for run in order],
        }
    )
    return SQLCohort(
        CohortIdentity(original, scope_identity, order_identity, cohort_identity, len(order)),
        order,
        captures,
        retained,
        tuple(sorted(project_ids)),
    )
