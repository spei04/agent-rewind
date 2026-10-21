"""Existing-route reads: bounded scoped SQL lists and verified graph presentations.

Lists report stored metadata, not verified execution completion or artifact
availability. Only complete published run graphs support detail/files/compare.
No raw legacy object fallback, journal, publication writer or admission exists.
"""

from __future__ import annotations

from typing import Any

from .artifact_graph import GraphRef, decode
from .artifact_metadata import ArtifactError
from .compare import compare_presentations
from .legacy_graph_views import GraphPresentation
from .legacy_reads import LegacyReads, ReadBudget, append_response, bounded_response
from .published_reader import PublishedRunReader, RunRead, _identity
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_repositories import ProjectContext, ScopedRepositories

MAX_RESULT_BYTES = 1024


class LegacyViews:
    def __init__(self, reader: PublishedRunReader, workspace_limit: int):
        self.reader, self.workspace_limit = reader, workspace_limit

    def _fresh(self, context: ProjectContext) -> None:
        with self.reader._connection() as connection:
            self.reader.repositories._authorize(connection, context, "read")

    def _snapshot(
        self,
        context: ProjectContext,
        kind: str,
        budget: ReadBudget,
        *,
        ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self.reader._connection() as connection:
            self.reader.repositories._authorize(connection, context, "read")
            reads = LegacyReads(connection, context, budget)
            selected = reads.ids(kind, limit) if ids is None else ids
            result: list[Any] = []
            used = 0
            for resource_id in selected:
                used = append_response(result, reads.resource(kind, resource_id), used)
            self.reader.repositories._authorize(connection, context, "read")
            return result

    def _metadata(
        self,
        context: ProjectContext,
        kind: str,
        *,
        resource_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        budget = ReadBudget()
        rows = self._snapshot(
            context,
            kind,
            budget,
            ids=None if resource_id is None else [identifier(resource_id)],
            limit=limit,
        )
        # Keep the original bounded cohort. Never switch defaults or substitute
        # latest rows for the expectations used by a compound response.
        current = self._snapshot(context, kind, budget, ids=[row["id"] for row in rows])
        if rows != current:
            raise ResourceNotFound()
        self._fresh(context)
        return rows

    def runs(self, context: ProjectContext, limit: int = 100) -> list[dict[str, Any]]:
        return self._metadata(context, "run", limit=limit)

    def studies(self, context: ProjectContext, limit: int = 100) -> list[dict[str, Any]]:
        return self._metadata(context, "study", limit=limit)

    def study(self, context: ProjectContext, study_id: str) -> dict[str, Any]:
        return self._metadata(context, "study", resource_id=study_id)[0]

    def run(self, context: ProjectContext, run_id: str) -> dict[str, Any]:
        graph = self.reader.read_current(context, run_id)
        result = GraphPresentation(graph, self.workspace_limit).run()
        self._fresh(context)
        return result

    def files(
        self, context: ProjectContext, run_id: str, step: int, path: str | None = None
    ) -> Any:
        graph = self.reader.read_current(context, run_id)
        result = GraphPresentation(graph, self.workspace_limit).files(step, path)
        self._fresh(context)
        return result

    def compare(self, context: ProjectContext, left: str, right: str) -> dict[str, Any]:
        graphs = self.reader.read_many(context, (RunRead(left), RunRead(right)))
        first, second = (GraphPresentation(graph, self.workspace_limit) for graph in graphs)
        result = compare_presentations(
            first.manifest,
            second.manifest,
            first.events,
            second.events,
            first.final_workspace(),
            second.final_workspace(),
        )
        self._fresh(context)
        return result

    def jobs(self, context: ProjectContext, limit: int = 100) -> list[dict[str, Any]]:
        budget = ReadBudget()
        rows = self._snapshot(context, "job", budget, limit=limit)
        expected: dict[GraphRef, tuple[Any, ...]] = {}
        # All requested result refs must be scoped and bounded before any I/O.
        with self.reader._connection() as connection:
            self.reader.repositories._authorize(connection, context, "read")
            reads = LegacyReads(connection, context, budget)
            for row in rows:
                if row["result"] is None:
                    continue
                ref = GraphRef(row["id"], "result", row["result"])
                value = self.reader.repositories._resolve(
                    reads, "job", row["id"], "result", row["result"]
                )
                if value.byte_count > MAX_RESULT_BYTES:
                    raise ArtifactError("artifact_graph_limit")
                expected[ref] = _identity(value)
        result: list[Any] = []
        targets: list[tuple[str, str, str]] = []
        used = 0
        for row in rows:
            presented = dict(row)
            if row["result"] is not None:
                ref = GraphRef(row["id"], "result", row["result"])

                def load(value: Any, receipt: tuple[Any, ...] = expected[ref]) -> bytes:
                    if _identity(value) != receipt or value.byte_count > MAX_RESULT_BYTES:
                        raise ArtifactError("publication_reference_changed")
                    loader = self.reader.repositories.artifact_loader
                    if loader is None:
                        raise ArtifactError("publication_loader_unavailable")
                    return loader(value)

                scoped = ScopedRepositories(
                    self.reader.engine,
                    artifact_resolver=self.reader.repositories.artifact_resolver,
                    artifact_loader=load,
                )
                data = scoped.read_artifact(context, "job", row["id"], "result", row["result"])
                result_body = decode(data)
                kind = "run" if row["kind"] in {"run", "branch"} else "study"
                key = kind + "_id"
                if set(result_body) != {key}:
                    raise ArtifactError("artifact_graph_invalid")
                target = identifier(result_body[key])
                targets.append((kind, target, row["id"]))
                presented["result"] = result_body
            used = append_response(result, presented, used)
        # No storage after this phase. Compare the original SQL rows and all
        # original descriptor receipts; latest SQL never becomes the expectation.
        if self._snapshot(context, "job", budget, ids=[row["id"] for row in rows]) != rows:
            raise ResourceNotFound()
        with self.reader._connection() as connection:
            self.reader.repositories._authorize(connection, context, "read")
            reads = LegacyReads(connection, context, budget)
            for kind, target, job_id in targets:
                if reads.resource(kind, target).get("job_id") != job_id:
                    raise ResourceNotFound()
            if expected:
                self.reader._final_refs(connection, context, expected, owner_kind="job")
            self.reader.repositories._authorize(connection, context, "read")
        return bounded_response(result)
