"""Bounded complete-run graph format, separate from legacy schema-1 artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, NoReturn

from .artifact_metadata import ArtifactError, digest_value, identifier
from .models import TaskSpec, canonical, digest, valid_path

MAX_OBJECTS = 16000
MAX_EDGES = 32000
MAX_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_WORKSPACE_ENTRIES = 10000
MAX_DEPTH = 64


def fail() -> NoReturn:
    raise ArtifactError("artifact_graph_invalid")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            fail()
        result[key] = value
    return result


def decode(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_JSON_BYTES:
        raise ArtifactError("artifact_graph_limit")
    try:
        value = json.loads(data, object_pairs_hook=_pairs)
        canonical(value)  # Reject nonfinite values, including overflowing JSON numbers.
        if not isinstance(value, dict):
            fail()
        return value
    except (UnicodeError, TypeError, ValueError, RecursionError):
        raise ArtifactError("artifact_graph_invalid") from None


def exact(value: dict[str, Any], names: str) -> None:
    if set(value) != set(names.split()):
        fail()


@dataclass(frozen=True, order=True)
class GraphRef:
    owner_id: str
    role: str
    digest: str

    def __post_init__(self) -> None:
        identifier(self.owner_id)
        digest_value(self.digest)
        if self.role not in {
            "task",
            "event",
            "checkpoint",
            "workspace",
            "file_blob",
            "evaluation",
            "result",
        }:
            fail()


@dataclass(frozen=True)
class VerifiedGraph:
    envelope: bytes
    refs: tuple[GraphRef, ...]
    objects: Mapping[str, bytes]

    @property
    def root_digest(self) -> str:
        return hashlib.sha256(self.envelope).hexdigest()


@dataclass(frozen=True)
class VerifiedCapture:
    source_digest: str
    status: str
    branchable: bool
    event_head: str | None
    evidence_digest: str


class _Graph:
    def __init__(self, fetch: Callable[[GraphRef, int], bytes]):
        self.fetch = fetch
        self.refs: set[GraphRef] = set()
        self.objects: dict[str, bytes] = {}
        self.total = 0
        self.edges = 0
        self.workspaces: set[GraphRef] = set()

    def load(self, owner: str, role: str, key: Any, *, limit: int = MAX_BYTES) -> bytes:
        ref = GraphRef(owner, role, key)
        self.edges += 1
        if self.edges > MAX_EDGES:
            raise ArtifactError("artifact_graph_limit")
        if ref in self.refs:
            return self.objects[ref.digest]
        if len(self.refs) >= MAX_OBJECTS:
            raise ArtifactError("artifact_graph_limit")
        # The scoped loader is called for each owner/role even when bytes repeat.
        # Deduplication must not turn another owner's cache hit into authority.
        remaining = len(self.objects[key]) if key in self.objects else MAX_BYTES - self.total
        data = self.fetch(ref, min(limit, remaining))
        if not isinstance(data, bytes) or len(data) > min(limit, remaining):
            raise ArtifactError("artifact_graph_limit")
        if hashlib.sha256(data).hexdigest() != key:
            raise ArtifactError("artifact_integrity_failed")
        if key not in self.objects:
            if len(data) + self.total > MAX_BYTES:
                raise ArtifactError("artifact_graph_limit")
            self.total += len(data)
            self.objects[key] = data
        self.refs.add(ref)
        return data

    def json(self, owner: str, role: str, key: Any) -> dict[str, Any]:
        return decode(self.load(owner, role, key, limit=MAX_JSON_BYTES))

    def workspace(self, owner: str, key: Any) -> None:
        content = self.load(owner, "workspace", key, limit=MAX_JSON_BYTES)
        ref = GraphRef(owner, "workspace", key)
        if ref in self.workspaces:
            return
        value = decode(content)
        exact(value, "schema files")
        if (
            type(value["schema"]) is not int
            or value["schema"] != 1
            or not isinstance(value["files"], dict)
        ):
            fail()
        if len(value["files"]) > MAX_WORKSPACE_ENTRIES:
            raise ArtifactError("artifact_graph_limit")
        total = 0
        for path, entry in value["files"].items():
            try:
                valid_path(path)
            except (TypeError, ValueError):
                fail()
            if not isinstance(entry, dict):
                fail()
            exact(entry, "blob mode kind mtime")
            if (
                type(entry["mode"]) is not int
                or not 0 <= entry["mode"] <= 0o777
                or entry["kind"] not in {"file", "directory"}
                or type(entry["mtime"]) is not int
            ):
                fail()
            content = self.load(owner, "file_blob", entry["blob"])
            total += len(content)  # Repeated blobs still occupy each logical path.
            if total > MAX_BYTES:
                raise ArtifactError("artifact_graph_limit")
            if entry["kind"] == "directory" and content:
                fail()
        self.workspaces.add(ref)

    def checkpoint(self, owner: str, key: Any, step: int, run: dict[str, Any]) -> dict[str, Any]:
        value = self.json(owner, "checkpoint", key)
        exact(value, "schema workspace state next_step image policy seed branchable")
        if (
            type(value["schema"]) is not int
            or value["schema"] != 1
            or type(value["next_step"]) is not int
            or value["next_step"] != step
            or not isinstance(value["state"], dict)
            or type(value["branchable"]) is not bool
            or any(value[field] != run[field] for field in ("image", "policy", "seed"))
        ):
            fail()
        self.workspace(owner, value["workspace"])
        return value


def verify_run_graph(envelope: bytes, fetch: Callable[[GraphRef, int], bytes]) -> VerifiedGraph:
    """Derive all edges from declared fields. Opaque tool/state dictionaries are leaves.

    This format supports complete runs only. It does not synthesize completion,
    authorize a source, or publish SQL metadata. Callers supply scoped loaders.
    """
    try:
        return _verify(envelope, fetch)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ArtifactError):
            raise
        raise ArtifactError("artifact_graph_invalid") from None


def _verify(envelope: bytes, fetch: Callable[[GraphRef, int], bytes]) -> VerifiedGraph:
    root = decode(envelope)
    exact(
        root,
        "publication_schema publication_id project_id run_id job_id "
        "worker_id generation manifest lineage events",
    )
    if type(root["publication_schema"]) is not int or root["publication_schema"] != 1:
        fail()
    for name in ("publication_id", "project_id", "run_id", "job_id"):
        identifier(root[name])
    if (
        not isinstance(root["worker_id"], str)
        or not 1 <= len(root["worker_id"]) <= 128
        or type(root["generation"]) is not int
        or root["generation"] < 1
    ):
        fail()
    if not isinstance(root["manifest"], dict) or any(
        root["manifest"].get(field) != root[root_field]
        for field, root_field in (("id", "run_id"), ("job_id", "job_id"))
    ):
        fail()
    graph, _ = _verify_capture(
        {field: root[field] for field in ("manifest", "lineage", "events")},
        fetch,
        complete_only=True,
    )
    if graph.total + len(envelope) > MAX_BYTES or len(graph.refs) >= MAX_OBJECTS:
        raise ArtifactError("artifact_graph_limit")
    root_digest = hashlib.sha256(envelope).hexdigest()
    graph.objects[root_digest] = envelope
    graph.refs.add(GraphRef(root["run_id"], "result", root_digest))
    return VerifiedGraph(envelope, tuple(sorted(graph.refs)), graph.objects)


def verify_run_capture(
    capture: dict[str, Any], fetch: Callable[[GraphRef, int], bytes]
) -> VerifiedCapture:
    """Verify bounded operator evidence without inventing a publication or fence.

    Source/owner authorization belongs to the caller. Plaintext is discarded at
    return; only the verified identities and conservative restore eligibility remain.
    """
    try:
        source_size = len(canonical(capture))
        if source_size > MAX_JSON_BYTES:
            raise ArtifactError("artifact_graph_limit")
        graph, head = _verify_capture(capture, fetch, complete_only=False)
        if graph.total + source_size > MAX_BYTES:
            raise ArtifactError("artifact_graph_limit")
        manifest = capture["manifest"]
        return VerifiedCapture(
            digest(capture),
            manifest["status"],
            manifest["status"] == "complete" and manifest["branchable"],
            head,
            digest({"capture": capture, "refs": [asdict(ref) for ref in sorted(graph.refs)]}),
        )
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("artifact_graph_invalid") from None


def _verify_capture(
    capture: dict[str, Any], fetch: Callable[[GraphRef, int], bytes], *, complete_only: bool
) -> tuple[_Graph, str | None]:
    exact(capture, "manifest lineage events")
    manifest = capture["manifest"]
    if not isinstance(manifest, dict):
        fail()
    identifier(manifest["id"])
    identifier(manifest["job_id"])
    status = manifest.get("status")
    if status not in {"complete", "failed", "incomplete", "running"}:
        fail()
    complete = status == "complete"
    if complete_only and not complete:
        fail()
    lineage = capture["lineage"]
    if not isinstance(lineage, list) or not 1 <= len(lineage) <= MAX_DEPTH + 1:
        fail()
    runs: dict[str, dict[str, Any]] = {}
    for position, run in enumerate(lineage):
        if not isinstance(run, dict):
            fail()
        exact(run, "id parent_id fork_step seed image policy task_digest branchable status")
        identifier(run["id"])
        if run["id"] in runs or type(run["branchable"]) is not bool:
            fail()
        if run["status"] != (status if position == len(lineage) - 1 else "complete"):
            fail()
        if runs:
            previous = lineage[len(runs) - 1]
            if (
                run["parent_id"] != previous["id"]
                or not previous["branchable"]
                or type(run["fork_step"]) is not int
                or not 1 <= run["fork_step"] <= 100
            ):
                fail()
        elif run["parent_id"] is not None or run["fork_step"] is not None:
            fail()
        runs[run["id"]] = run
    if lineage[-1]["id"] != manifest["id"]:
        fail()
    base = set(
        [
            "id",
            "created",
            "name",
            "job_id",
            "parent_id",
            "fork_step",
            "seed",
            "image",
            "policy",
            "task_digest",
            "task_ref",
            "status",
            "branchable",
            "head",
            "steps",
            "intervention",
        ]
    )
    terminal = {"success", "evaluation_ref", "final_workspace"}
    expected = base | (terminal if complete else set())
    if not complete:
        if "error" in manifest:
            expected.add("error")
        if terminal & set(manifest):
            expected |= terminal
    if set(manifest) != expected:
        fail()
    has_terminal = terminal <= set(manifest)
    if (
        (has_terminal and type(manifest["success"]) is not bool)
        or type(manifest["branchable"]) is not bool
        or type(manifest["steps"]) is not int
        or not (1 if complete else 0) <= manifest["steps"] <= 100
        or any(
            manifest[k] != lineage[-1][k]
            for k in ("id", "parent_id", "fork_step", "seed", "image", "policy", "branchable")
        )
    ):
        fail()
    if any(
        any(run[field] != manifest[field] for field in ("image", "policy", "task_digest"))
        for run in lineage
    ):
        fail()
    graph = _Graph(fetch)
    task = graph.json(manifest["id"], "task", manifest["task_ref"])
    validated_task = TaskSpec.model_validate(task)
    if manifest["steps"] > validated_task.max_steps:
        fail()
    if digest(task) != manifest["task_digest"]:
        fail()
    rows = capture["events"]
    if not isinstance(rows, list) or len(rows) > 100:
        fail()
    permitted = {manifest["steps"]} if complete else {manifest["steps"], manifest["steps"] + 1}
    if len(rows) not in permitted or len(rows) > validated_task.max_steps:
        fail()
    previous_hash = None
    previous_workspace = None
    for step, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            fail()
        exact(row, "run_id step artifact hash")
        owner = lineage[0]["id"]
        for run in lineage[1:]:
            if step >= run["fork_step"]:
                owner = run["id"]
        if row["run_id"] != owner or type(row["step"]) is not int or row["step"] != step:
            fail()
        event = graph.json(owner, "event", row["artifact"])
        exact(
            event,
            "schema run_id step previous checkpoint proposed action "
            "actual_result observed_result decision workspace_after changes "
            "intervened hash",
        )
        if (
            type(event["schema"]) is not int
            or event["schema"] != 1
            or event["run_id"] != owner
            or type(event["step"]) is not int
            or event["step"] != step
            or event["previous"] != previous_hash
            or event["hash"] != row["hash"]
            or digest({k: v for k, v in event.items() if k != "hash"}) != row["hash"]
        ):
            fail()
        checkpoint = graph.checkpoint(owner, event["checkpoint"], step, runs[owner])
        if (previous_workspace is not None and checkpoint["workspace"] != previous_workspace) or (
            complete and manifest["branchable"] and not checkpoint["branchable"]
        ):
            fail()
        graph.workspace(owner, event["workspace_after"])
        previous_hash = row["hash"]
        previous_workspace = event["workspace_after"]
    recorded_head = rows[manifest["steps"] - 1]["hash"] if manifest["steps"] else None
    if recorded_head != manifest["head"]:
        fail()
    if has_terminal:
        if previous_workspace != manifest["final_workspace"]:
            fail()
        graph.workspace(manifest["id"], manifest["final_workspace"])
        evaluation = graph.json(manifest["id"], "evaluation", manifest["evaluation_ref"])
        if (
            type(evaluation.get("exit_code")) is not int
            or (evaluation["exit_code"] == 0) != manifest["success"]
        ):
            fail()
    return graph, previous_hash
