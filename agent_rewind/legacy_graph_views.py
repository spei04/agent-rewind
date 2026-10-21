"""Pure legacy representations from a scoped, verified complete run graph."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .artifact_graph import GraphRef, VerifiedGraph, decode
from .artifact_metadata import ArtifactError
from .experiments import locate
from .legacy_reads import append_response, bounded_response
from .models import Action
from .scoped_lineage import ResourceNotFound
from .workspace import File


class GraphPresentation:
    def __init__(self, graph: VerifiedGraph, workspace_limit: int):
        self.graph, self.workspace_limit = graph, workspace_limit
        self.refs = frozenset(graph.refs)
        self.root = decode(graph.envelope)
        self.manifest = self.root["manifest"]
        self.events: list[dict[str, Any]] = []
        used = 0
        for row in self.root["events"]:
            value = self.object(row["run_id"], "event", row["artifact"])
            # Integrity verification keeps arbitrary policy payloads opaque.
            # Validate the containers used by legacy locate/compare/UI here.
            try:
                Action.model_validate(value["action"])
                if not isinstance(value["actual_result"], dict) or not isinstance(
                    value["observed_result"], dict
                ):
                    raise ValueError()
                if type(value["actual_result"].get("exit_code", 0)) is not int:
                    raise ValueError()
                if not isinstance(value["changes"], list):
                    raise ValueError()
            except (ValidationError, ValueError, TypeError, KeyError):
                raise ArtifactError("artifact_graph_invalid") from None
            used = append_response(self.events, value, used)

    def bytes(self, owner: str, role: str, digest: str) -> bytes:
        if GraphRef(owner, role, digest) not in self.refs:
            raise ResourceNotFound()
        try:
            return self.graph.objects[digest]
        except KeyError:
            raise ArtifactError("artifact_graph_invalid") from None

    def object(self, owner: str, role: str, digest: str) -> dict[str, Any]:
        return decode(self.bytes(owner, role, digest))

    def workspace(self, owner: str, digest: str) -> dict[str, File]:
        value = self.object(owner, "workspace", digest)
        files: dict[str, File] = {}
        total = 0
        for path, item in value["files"].items():
            data = self.bytes(owner, "file_blob", item["blob"])
            total += len(data)
            if total > self.workspace_limit:
                raise ArtifactError("artifact_graph_limit")
            files[path] = File(data, item["mode"], item["kind"], item["mtime"])
        return files

    def run(self) -> dict[str, Any]:
        return bounded_response(
            {
                **self.manifest,
                "events": self.events,
                "locations": locate(self.events),
                "evaluation": self.object(
                    self.root["run_id"], "evaluation", self.manifest["evaluation_ref"]
                ),
            }
        )

    def final_workspace(self) -> dict[str, File]:
        return self.workspace(self.root["run_id"], self.manifest["final_workspace"])

    def files(self, step: int, path: str | None) -> Any:
        if type(step) is not int or not 1 <= step <= len(self.events):
            raise ResourceNotFound()
        event = self.events[step - 1]
        owner = self.root["events"][step - 1]["run_id"]
        checkpoint = self.object(owner, "checkpoint", event["checkpoint"])
        workspace = self.workspace(owner, checkpoint["workspace"])
        if path is None:
            result: list[Any] = []
            used = 0
            for name, value in sorted(workspace.items()):
                used = append_response(
                    result, {"path": name, "bytes": len(value.data), "mode": oct(value.mode)}, used
                )
            return result
        if path not in workspace:
            raise ResourceNotFound()
        data = workspace[path].data
        return bounded_response(
            {
                "path": path,
                "content": data[:100000].decode("utf-8", errors="replace"),
                "truncated": len(data) > 100000,
            }
        )
