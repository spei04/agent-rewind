"""Bounded legacy SQL presentations; no artifact access or projection-read claim."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy import Float, Text, and_, case, cast, select, text, union_all
from sqlalchemy.engine import Connection

from .database import jobs, records
from .models import canonical
from .scoped_artifacts import ArtifactObject
from .scoped_lineage import (
    MAX_EDGES,
    MAX_NODES,
    MAX_RETAINED_BYTES,
    Lineage,
    ResourceNotFound,
    encoded_size,
    identifier,
)
from .scoped_repositories import (
    ProjectContext,
    ScopedRepositories,
    _bounded_row,
    _byte_length,
    _Reads,
    _scope,
    scopes,
)

Presentation = TypeVar("Presentation")

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LIST_ROWS = 100
MAX_RECEIPT_BYTES = 4 * 1024 * 1024


@dataclass
class ReadBudget:
    """Conservative request-wide work, including repeated closure validation."""

    nodes: int = 0
    edges: int = 0
    retained: int = 0
    receipts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    receipt_bytes: int = 2
    discoveries: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)

    def remember(self, kind: str, row: dict[str, Any]) -> None:
        key = (kind, identifier(row["id"]))
        prefix = "j_" if kind == "job" else "r_"
        value = {"kind": kind, "id": key[1], **{prefix + k: v for k, v in row.items() if k != "id"}}
        size = encoded_size(value) + 1
        if key in self.receipts:
            if self.receipts[key] != value:
                raise ResourceNotFound()
            return
        if len(self.receipts) >= MAX_NODES or self.receipt_bytes + size > MAX_RECEIPT_BYTES:
            raise ResourceNotFound()
        self.receipt_bytes += size
        self.receipts[key] = value

    def final(self, connection: Connection, context: ProjectContext) -> None:
        """Compare the original entire relational closure in one SELECT."""
        if not self.receipts:
            return
        query, parameters = self.matching_query(connection, context)
        rows = connection.execute(query, parameters).all()
        current = {(row.kind, row.id) for row in rows}
        if len(rows) != len(current) or current != self.receipts.keys():
            raise ResourceNotFound()

    def matching_query(
        self, connection: Connection, context: ProjectContext
    ) -> tuple[Any, dict[str, str]]:
        """Compose original source receipts with another bounded receipt domain.

        Input <=4 MiB/2048 identities; only bounded input IDs are returned.
        Caller compares exact identity/cardinality and freshly reauthorizes.
        """
        if len(self.receipts) > MAX_NODES or self.receipt_bytes > MAX_RECEIPT_BYTES:
            raise ResourceNotFound()
        expected = list(self.receipts.values())
        encoded = canonical(expected)
        if len(encoded) > MAX_RECEIPT_BYTES:
            raise ResourceNotFound()
        fields: dict[str, Any] = {
            "kind": Text(),
            "id": Text(),
            "r_created": Float(),
            "r_body": Text(),
        }
        for column in jobs.c:
            if column.name != "id":
                fields["j_" + column.name] = column.type
        dialect = connection.dialect.name
        if dialect == "sqlite":
            # JSON-derived identities otherwise have no TEXT affinity, causing
            # repeated scans instead of indexed joins to the frozen VARCHAR keys.
            source = text("""SELECT
                CAST(json_extract(value,'$.kind') AS TEXT) AS kind,
                CAST(json_extract(value,'$.id') AS TEXT) AS id,
                json_extract(value,'$.r_created') AS r_created,
                json_extract(value,'$.r_body') AS r_body,
                json_extract(value,'$.j_kind') AS j_kind,
                json_extract(value,'$.j_created') AS j_created,
                json_extract(value,'$.j_payload') AS j_payload,
                json_extract(value,'$.j_status') AS j_status,
                json_extract(value,'$.j_owner') AS j_owner,
                json_extract(value,'$.j_lease_until') AS j_lease_until,
                json_extract(value,'$.j_cancel') AS j_cancel,
                json_extract(value,'$.j_budget') AS j_budget,
                json_extract(value,'$.j_reserved') AS j_reserved,
                json_extract(value,'$.j_result') AS j_result,
                json_extract(value,'$.j_error') AS j_error,
                json_extract(value,'$.j_actor') AS j_actor
                FROM json_each(:receipts)""")
        elif dialect == "postgresql":
            source = text("""SELECT * FROM jsonb_to_recordset(CAST(:receipts AS jsonb)) AS w(
                kind TEXT,id TEXT,r_created DOUBLE PRECISION,r_body TEXT,
                j_kind TEXT,j_created DOUBLE PRECISION,j_payload TEXT,j_status TEXT,
                j_owner TEXT,j_lease_until DOUBLE PRECISION,j_cancel BOOLEAN,
                j_budget BIGINT,j_reserved BIGINT,j_result TEXT,j_error TEXT,j_actor TEXT)""")
        else:
            raise ResourceNotFound()
        wanted = source.columns(**fields).cte("source_receipts").prefix_with("MATERIALIZED")
        record_query = (
            select(wanted.c.kind, wanted.c.id)
            .select_from(
                wanted.join(
                    records, and_(records.c.id == wanted.c.id, records.c.kind == wanted.c.kind)
                ).join(
                    scopes,
                    and_(
                        scopes.c.resource_kind == wanted.c.kind,
                        scopes.c.resource_id == wanted.c.id,
                        scopes.c.project_id == context.project_id,
                    ),
                )
            )
            .where(
                wanted.c.kind.in_(("run", "study")),
                _bounded_row(connection, records),
                records.c.created.is_not_distinct_from(wanted.c.r_created),
                cast(records.c.data, Text).is_not_distinct_from(wanted.c.r_body),
            )
        )
        # Materialize one set of unexpected by-job members for the requested
        # jobs. Correlated EXISTS queries rescanned both records and the expected
        # rowset for every job; even small mixed closures became quadratic/cubic.
        # This anti-join discovers only this project's rows, and its DISTINCT
        # job IDs are a subset of the bounded expected job IDs.
        requested_jobs = select(wanted.c.id).where(wanted.c.kind == "job")
        known = wanted.alias("known_sources")
        unexpected_jobs = (
            select(records.c.data["job_id"].as_string().label("job_id"))
            .select_from(
                records.join(
                    scopes,
                    and_(
                        scopes.c.project_id == context.project_id,
                        scopes.c.resource_kind == records.c.kind,
                        scopes.c.resource_id == records.c.id,
                    ),
                ).outerjoin(
                    known,
                    and_(known.c.id == records.c.id, known.c.kind == records.c.kind),
                )
            )
            .where(
                records.c.data["job_id"].as_string().in_(requested_jobs),
                known.c.id.is_(None),
            )
            .distinct()
            .cte("unexpected_jobs")
            .prefix_with("MATERIALIZED")
        )
        # Bind scope directly to the expected ID as well as the job PK. The
        # indirect scope->job->expected join can scan every expected job per scope.
        job_query = (
            select(wanted.c.kind, wanted.c.id)
            .select_from(
                wanted.join(jobs, jobs.c.id == wanted.c.id)
                .join(scopes, _scope("job", wanted.c.id, context))
                .outerjoin(unexpected_jobs, unexpected_jobs.c.job_id == wanted.c.id)
            )
            .where(
                wanted.c.kind == "job",
                _bounded_row(connection, jobs),
                unexpected_jobs.c.job_id.is_(None),
                *(
                    column.is_not_distinct_from(wanted.c["j_" + column.name])
                    for column in jobs.c
                    if column.name != "id"
                ),
            )
        )
        query = union_all(record_query, job_query).limit(len(expected) + 1)
        return query, {"receipts": encoded.decode()}

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

    def remember(self, kind: str, row: dict[str, Any]) -> None:
        self.budget.remember(kind, row)

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
        original = self.budget.discoveries.setdefault(job_id, tuple(rows))
        if original != tuple(rows):
            raise ResourceNotFound()
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


class BudgetRepositories(ScopedRepositories):
    """Reuse the exact pre/post artifact check with one cumulative read budget."""

    budget: ReadBudget

    def resolve_artifact(
        self, context: ProjectContext, owner_kind: str, owner_id: str, role: str, digest: str
    ) -> ArtifactObject:
        with self._session(context, "read") as reads:
            return self._resolve(
                LegacyReads(reads.connection, context, self.budget),
                owner_kind,
                owner_id,
                role,
                digest,
            )
