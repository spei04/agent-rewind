"""Bounded legacy SQL presentations; no artifact access or projection-read claim."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy import and_, case, select
from sqlalchemy.engine import Connection

from .database import jobs, records
from .scoped_lineage import (
    MAX_EDGES,
    MAX_NODES,
    MAX_RETAINED_BYTES,
    Lineage,
    ResourceNotFound,
    encoded_size,
    identifier,
)
from .scoped_repositories import ProjectContext, _byte_length, _Reads, _scope, scopes

Presentation = TypeVar("Presentation")

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LIST_ROWS = 100


@dataclass
class ReadBudget:
    """Conservative request-wide work, including repeated closure validation."""

    nodes: int = 0
    edges: int = 0
    retained: int = 0

    def row(self, value: dict[str, Any]) -> dict[str, Any]:
        created = value.get("created")
        if (
            not isinstance(created, int | float)
            or isinstance(created, bool)
            or not math.isfinite(created)
        ):
            raise ResourceNotFound()
        size = encoded_size(value)
        if self.nodes + 1 > MAX_NODES or self.retained + size > MAX_RETAINED_BYTES:
            raise ResourceNotFound()
        self.nodes += 1
        self.retained += size
        return value


class LegacyReads(_Reads):
    def __init__(self, connection: Connection, context: ProjectContext, budget: ReadBudget):
        super().__init__(connection, context)
        self.budget = budget

    def record(self, kind: str, resource_id: str) -> dict[str, Any]:
        value = self.budget.row(super().record(kind, resource_id))
        edges = 1  # Every record's owning job.
        if kind == "run":
            edges += int(value.get("parent_id") is not None)
        elif kind == "study":
            edges += 1  # Source run.
            groups = value.get("candidates")
            confirmation = value.get("confirmation")
            if not isinstance(groups, list):
                raise ResourceNotFound()
            for group in [*groups, *([confirmation] if confirmation is not None else [])]:
                if not isinstance(group, dict) or not isinstance(group.get("pairs"), list):
                    raise ResourceNotFound()
                for pair in group["pairs"]:
                    if not isinstance(pair, dict):
                        raise ResourceNotFound()
                    edges += int("control_run" in pair) + int("treatment_run" in pair)
        if self.budget.edges + edges > MAX_EDGES:
            raise ResourceNotFound()
        self.budget.edges += edges
        return value

    def job(self, resource_id: str) -> dict[str, Any]:
        return self.budget.row(super().job(resource_id))

    def by_job(self, job_id: str) -> list[tuple[str, str]]:
        rows = super().by_job(job_id)
        if self.budget.edges + len(rows) > MAX_EDGES:
            raise ResourceNotFound()
        self.budget.edges += len(rows)
        return rows

    def resource(self, kind: str, resource_id: str) -> dict[str, Any]:
        # New Lineage per root preserves its cross-record consistency checks;
        # the outer budget also bounds accumulated work across a whole list.
        return Lineage(self.record, self.job, self.by_job).validate(kind, resource_id)

    def ids(self, kind: str, limit: int) -> list[str]:
        if (
            kind not in {"run", "study", "job"}
            or type(limit) is not int
            or not 1 <= limit <= MAX_LIST_ROWS
        ):
            raise ResourceNotFound()
        source = jobs if kind == "job" else records
        safe = and_(
            _byte_length(self.connection, source.c.id) == 32,
            _byte_length(self.connection, source.c.created) <= 64,
        )
        query = select(
            case((safe, source.c.id), else_=None).label("id"),
            case((safe, source.c.created), else_=None).label("created"),
        ).select_from(source.join(scopes, _scope(kind, source.c.id, self.context)))
        if kind != "job":
            query = query.where(records.c.kind == kind)
        rows = (
            self.connection.execute(
                query.order_by(source.c.created.desc(), source.c.id.desc()).limit(limit)
            )
            .mappings()
            .all()
        )
        result = []
        for row in rows:
            if type(row["created"]) not in {int, float} or not math.isfinite(row["created"]):
                raise ResourceNotFound()
            result.append(identifier(row["id"]))
        return result


def bounded_response(value: Presentation) -> Presentation:
    if encoded_size(value) > MAX_RESPONSE_BYTES:
        raise ResourceNotFound()
    return value


def append_response(items: list[Any], value: Any, used: int) -> int:
    size = encoded_size(value) + 1
    if used + size + 2 > MAX_RESPONSE_BYTES:
        raise ResourceNotFound()
    items.append(value)
    return used + size
