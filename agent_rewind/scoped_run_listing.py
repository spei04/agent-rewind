"""SQL-only scoped run summaries; caller owns schema eligibility and HTTP mapping.

This preparatory reader never loads events/artifacts or repairs projection rows.
It compares original receipts optimistically, then freshly authorizes the same
named project. It does not promise linearizability through response delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, union_all
from sqlalchemy.engine import Connection, Engine

from .config import Settings
from .cursor_config import cursor_codec
from .legacy_reads import MAX_RECEIPT_BYTES, ReadBudget
from .listing_projection import IndexEntry, by_ids, candidates, fail, matching_query, summary
from .listing_session import SQLWork, listing_connection
from .listing_sources import Sources
from .models import canonical
from .request_authority import RequestAuthority
from .request_identity import VerifiedPrincipal
from .run_cursor import CursorPosition, initial_expiry, page_limit
from .scoped_lineage import MAX_NODES, identifier
from .scoped_repositories import ProjectContext


@dataclass(frozen=True)
class RunPage:
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None


class ScopedRunReader:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine, self.settings = engine, settings
        self.authority = RequestAuthority(engine)

    def _context(
        self, connection: Connection, principal: VerifiedPrincipal, project_id: str
    ) -> ProjectContext:
        context = self.authority._context(connection, principal, project_id)
        self.authority.check(connection, principal, context)
        return context

    @staticmethod
    def _receipts(
        connection: Connection,
        context: ProjectContext,
        budget: ReadBudget,
        entries: list[IndexEntry],
    ) -> None:
        projected = canonical([item.receipt() for item in entries])
        expected = set(budget.receipts) | {("projection", item.value.run_id) for item in entries}
        if (
            len(expected) != len(budget.receipts) + len(entries)
            or len(expected) > MAX_NODES
            or budget.receipt_bytes + len(projected) > MAX_RECEIPT_BYTES
        ):
            fail()
        if not entries:
            return
        original, parameters = budget.matching_query(connection, context)
        source = original.subquery("matching_sources")
        projection = matching_query(connection, entries).subquery("matching_projections")
        query = union_all(
            select(source.c.kind, source.c.id),
            select(projection.c.kind, projection.c.id),
        ).limit(len(expected) + 1)
        rows = connection.execute(
            query, {**parameters, "projection_receipts": projected.decode()}
        ).all()
        identities = {(row.kind, row.id) for row in rows}
        if len(rows) != len(identities) or identities != expected:
            fail()

    def _finish(
        self,
        principal: VerifiedPrincipal,
        context: ProjectContext,
        entries: list[IndexEntry],
        sources: Sources,
        work: SQLWork,
    ) -> None:
        with listing_connection(self.engine, work) as connection:
            self._receipts(connection, context, sources.budget, entries)
            self.authority.check(connection, principal, context)

    @staticmethod
    def _summaries(entries: list[IndexEntry], sources: Sources) -> tuple[dict[str, Any], ...]:
        # Lineage has already verified the complete shared scoped SQL closure.
        return tuple(
            summary(
                item,
                sources.records[("run", item.value.run_id)],
                sources.jobs[sources.records[("run", item.value.run_id)]["job_id"]],
            )
            for item in entries
        )

    def list(
        self,
        principal: VerifiedPrincipal,
        project_id: str,
        *,
        now: datetime,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> RunPage:
        self.authority._principal(principal)
        project_id = identifier(project_id)
        work = SQLWork()
        with listing_connection(self.engine, work) as connection:
            context = self._context(connection, principal, project_id)
            # Authority precedes all key/token errors; configuration is LIST-only.
            codec = cursor_codec(self.settings)
            position = (
                None
                if cursor is None
                else codec.decode(cursor, project_id, principal.principal_id, now=now, limit=limit)
            )
            size = page_limit(limit) if position is None else position.limit
            expiry = initial_expiry(now) if position is None else position.expires_at
            watermark, entries = candidates(connection, project_id, size, position)
            sources = Sources(context, ReadBudget(nodes=len(entries)))
            if entries:
                sources.load(connection, [item.value.run_id for item in entries])
                # The lookahead row is also validated; it cannot hide a bad row.
                items = self._summaries(entries, sources)
            else:
                items = ()
        self._finish(principal, context, entries, sources, work)
        next_cursor = None
        if len(entries) > size:
            last = entries[size - 1].value
            next_cursor = codec.encode(
                project_id,
                principal.principal_id,
                CursorPosition(size, watermark, last.created_at, last.run_id, expiry),
                now=now,
            )
        return RunPage(items[:size], next_cursor)

    def detail(self, principal: VerifiedPrincipal, project_id: str, run_id: str) -> dict[str, Any]:
        self.authority._principal(principal)
        project_id, run_id = identifier(project_id), identifier(run_id)
        work = SQLWork()
        with listing_connection(self.engine, work) as connection:
            context = self._context(connection, principal, project_id)
            entries = list(by_ids(connection, project_id, {run_id}).values())
            sources = Sources(context, ReadBudget(nodes=len(entries)))
            sources.load(connection, [run_id])
            items = self._summaries(entries, sources)
        self._finish(principal, context, entries, sources, work)
        return items[0]
