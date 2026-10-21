"""Set-oriented scoped source closure with original bounded receipts."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text, and_, case, cast, func, select, text
from sqlalchemy.engine import Connection

from .database import jobs, records
from .legacy_reads import ReadBudget
from .listing_projection import fail
from .models import canonical
from .scoped_lineage import MAX_EDGES, MAX_NODES, Lineage, ResourceNotFound, identifier
from .scoped_repositories import (
    ProjectContext,
    _bounded_row,
    _byte_length,
    _invalid_constant,
    _json_row,
    _object,
    scopes,
)


def wanted(connection: Connection, keys: set[tuple[str, str]]) -> tuple[Any, dict[str, str]]:
    if not keys or len(keys) > MAX_NODES:
        fail()
    payload = canonical([{"kind": k, "id": v} for k, v in sorted(keys)])
    raw = (
        "SELECT CAST(json_extract(value,'$.kind') AS TEXT) AS kind,"
        "CAST(json_extract(value,'$.id') AS TEXT) AS id FROM json_each(:listing_keys)"
        if connection.dialect.name == "sqlite"
        else (
            "SELECT * FROM jsonb_to_recordset(CAST(:listing_keys AS jsonb)) AS k(kind TEXT,id TEXT)"
        )
    )
    return (
        text(raw).columns(kind=Text(), id=Text()).cte("listing_keys").prefix_with("MATERIALIZED"),
        {"listing_keys": payload.decode()},
    )


class Sources:
    """Batched SQL prefetch, followed by the existing lineage verifier on memory."""

    def __init__(self, context: ProjectContext, budget: ReadBudget):
        self.context, self.budget = context, budget
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.members: dict[str, list[tuple[str, str]]] = {}

    def _records(self, connection: Connection, keys: set[tuple[str, str]]) -> None:
        expected, parameters = wanted(connection, keys)
        safe = _bounded_row(connection, records)
        query = (
            select(
                expected.c.kind,
                expected.c.id,
                case((safe, records.c.created), else_=None).label("created"),
                case((safe, cast(records.c.data, Text)), else_=None).label("body"),
            )
            .select_from(
                expected.join(
                    records, and_(records.c.kind == expected.c.kind, records.c.id == expected.c.id)
                ).join(
                    scopes,
                    and_(
                        scopes.c.resource_kind == expected.c.kind,
                        scopes.c.resource_id == expected.c.id,
                        scopes.c.project_id == self.context.project_id,
                    ),
                )
            )
            .limit(len(keys) + 1)
        )
        seen = set()
        for row in connection.execute(query, parameters).mappings():
            key = (row["kind"], identifier(row["id"]))
            if key in seen or row["body"] is None or row["created"] is None:
                fail()
            seen.add(key)
            try:
                data = json.loads(
                    row["body"], object_pairs_hook=_object, parse_constant=_invalid_constant
                )
                if type(data) is not dict:
                    fail()
                value = self.budget.row(
                    _json_row({**data, "id": row["id"], "created": row["created"]})
                )
            except (ValueError, TypeError, RecursionError, ResourceNotFound):
                fail()
            try:
                self.budget.remember(
                    row["kind"], {"id": row["id"], "created": row["created"], "body": row["body"]}
                )
            except ResourceNotFound:
                fail()
            self.records[key] = value
        if seen != keys:
            raise ResourceNotFound()

    def _jobs(self, connection: Connection, ids: set[str]) -> None:
        keys = {("job", item) for item in ids}
        expected, parameters = wanted(connection, keys)
        safe = _bounded_row(connection, jobs)
        if connection.dialect.name == "sqlite":
            safe = and_(safe, func.typeof(jobs.c.cancel) == "integer", jobs.c.cancel.in_((0, 1)))
        query = (
            select(*(case((safe, c), else_=None).label(c.name) for c in jobs.c))
            .select_from(
                expected.join(jobs, jobs.c.id == expected.c.id).join(
                    scopes,
                    and_(
                        scopes.c.resource_kind == "job",
                        scopes.c.resource_id == expected.c.id,
                        scopes.c.project_id == self.context.project_id,
                    ),
                )
            )
            .limit(len(ids) + 1)
        )
        seen = set()
        for row in connection.execute(query, parameters).mappings():
            if row["id"] is None:
                fail()
            job_id = identifier(row["id"])
            if job_id in seen:
                fail()
            seen.add(job_id)
            try:
                value = self.budget.row(_json_row(dict(row)))
                self.budget.remember("job", dict(row))
            except ResourceNotFound:
                fail()
            self.jobs[job_id] = value
        if seen != ids:
            raise ResourceNotFound()
        # Discover all same-project by-job members once for this whole frontier.
        selected_job = records.c.data["job_id"].as_string()
        query = (
            select(
                case(
                    (_byte_length(connection, records.c.kind) <= 20, records.c.kind), else_=None
                ).label("kind"),
                case(
                    (_byte_length(connection, records.c.id) == 32, records.c.id), else_=None
                ).label("id"),
                expected.c.id.label("job_id"),
            )
            .select_from(
                expected.join(records, selected_job == expected.c.id).join(
                    scopes,
                    and_(
                        scopes.c.resource_kind == records.c.kind,
                        scopes.c.resource_id == records.c.id,
                        scopes.c.project_id == self.context.project_id,
                    ),
                )
            )
            .order_by(expected.c.id, records.c.kind, records.c.id)
            .limit(MAX_NODES + 1)
        )
        members: dict[str, list[tuple[str, str]]] = {item: [] for item in ids}
        for count, member in enumerate(connection.execute(query, parameters)):
            if count >= MAX_NODES or member.kind not in {"run", "study"}:
                fail()
            members[member.job_id].append((member.kind, identifier(member.id)))
        for job_id, values in members.items():
            self.budget.discoveries[job_id] = tuple(values)
            self.members[job_id] = values

    @staticmethod
    def _links(kind: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        links = [("job", identifier(data.get("job_id")))]
        if kind == "run":
            if "parent_id" not in data:
                fail()
            if data["parent_id"] is not None:
                links.append(("run", identifier(data["parent_id"])))
        elif kind == "study":
            links.append(("run", identifier(data.get("source_run"))))
            candidates, confirmation = data.get("candidates"), data.get("confirmation")
            if type(candidates) is not list or (
                confirmation is not None and type(confirmation) is not dict
            ):
                fail()
            for group in [*candidates, *([confirmation] if confirmation is not None else [])]:
                if type(group) is not dict or type(group.get("pairs")) is not list:
                    fail()
                for pair in group["pairs"]:
                    if type(pair) is not dict:
                        fail()
                    for key in ("control_run", "treatment_run"):
                        if key in pair:
                            links.append(("run", identifier(pair[key])))
        else:
            fail()
        return links

    def load(self, connection: Connection, run_ids: list[str]) -> None:
        pending = {("run", identifier(item)) for item in run_ids}
        edges = 0
        while pending:
            if len(pending) + self.budget.nodes > MAX_NODES:
                fail()
            record_keys = {(k, i) for k, i in pending if k != "job"}
            job_ids = {i for k, i in pending if k == "job"}
            if record_keys:
                self._records(connection, record_keys)
            if job_ids:
                self._jobs(connection, job_ids)
            following: set[tuple[str, str]] = set()
            for key in record_keys:
                try:
                    links = self._links(key[0], self.records[key])
                except ResourceNotFound:
                    fail()
                edges += len(links)
                following.update(links)
            for job_id in job_ids:
                edges += len(self.members[job_id])
                following.update(self.members[job_id])
            if edges > MAX_EDGES:
                fail()
            pending = {
                (k, i)
                for k, i in following
                if (i not in self.jobs if k == "job" else (k, i) not in self.records)
            }
        try:
            Lineage(
                lambda k, i: self.records[(k, i)],
                lambda i: self.jobs[i],
                lambda i: self.members[i],
            ).validate_many([("run", item) for item in run_ids])
        except ResourceNotFound:
            fail()
