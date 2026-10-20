"""Bounded SQL lineage checks using exclusively scoped record loaders."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

MAX_NODES = 2048
MAX_EDGES = 4096
MAX_PARENT_DEPTH = 64
MAX_RETAINED_BYTES = 16 * 1024 * 1024


class ResourceNotFound(LookupError):
    """One fixed denial for absent, inaccessible and invalid resource identities."""

    def __init__(self) -> None:
        super().__init__("Resource not found.")


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ResourceNotFound()
    return value


def encoded_size(value: Any) -> int:
    """Measure finite JSON metadata or refuse invalid retained legacy values."""
    try:
        return len(json.dumps(value, separators=(",", ":"), allow_nan=False).encode())
    except (TypeError, ValueError, RecursionError):
        raise ResourceNotFound() from None


class Lineage:
    """No decrypt/load callbacks; metadata is capped and discarded per operation."""

    def __init__(
        self,
        record: Callable[[str, str], dict[str, Any]],
        job: Callable[[str], dict[str, Any]],
        by_job: Callable[[str], list[tuple[str, str]]],
    ):
        self.record, self.job, self.by_job = record, job, by_job
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}

    def validate(self, kind: str, resource_id: str) -> dict[str, Any]:
        pending = [(kind, identifier(resource_id))]
        parents: dict[str, str | None] = {}
        run_jobs: dict[str, str] = {}
        studies: dict[str, tuple[str, str]] = {}
        claims: dict[str, tuple[str, str]] = {}
        edges = 0
        retained_bytes = 0
        expanded_jobs: set[str] = set()

        def add(target_kind: str, target_id: Any) -> None:
            nonlocal edges
            edges += 1
            if edges > MAX_EDGES:
                raise ResourceNotFound()
            pending.append((target_kind, identifier(target_id)))

        while pending:
            current_kind, current_id = pending.pop()
            key = (current_kind, current_id)
            if key in self.records or (current_kind == "job" and current_id in expanded_jobs):
                continue
            if len(self.records) + len(expanded_jobs) >= MAX_NODES:
                raise ResourceNotFound()
            if current_kind == "job":
                job = self.job(current_id)
                retained_bytes += encoded_size(job)
                if retained_bytes > MAX_RETAINED_BYTES:
                    raise ResourceNotFound()
                self.jobs[current_id] = job
                if job["kind"] not in {"run", "branch", "study", "investigate"}:
                    raise ResourceNotFound()
                expanded_jobs.add(current_id)
                for record_kind, record_id in self.by_job(current_id):
                    add(record_kind, record_id)
                continue
            if current_kind not in {"run", "study"}:
                raise ResourceNotFound()
            data = self.record(current_kind, current_id)
            retained_bytes += encoded_size(data)
            if retained_bytes > MAX_RETAINED_BYTES:
                raise ResourceNotFound()
            self.records[key] = data
            job_id = identifier(data.get("job_id"))
            add("job", job_id)
            if current_kind == "run":
                if "parent_id" not in data:
                    raise ResourceNotFound()
                parent = data["parent_id"]
                parents[current_id] = None if parent is None else identifier(parent)
                run_jobs[current_id] = job_id
                if parent is not None:
                    add("run", parent)
            else:
                source = identifier(data.get("source_run"))
                request = data.get("request")
                if not isinstance(request, dict) or request.get("run_id") != source:
                    raise ResourceNotFound()
                studies[current_id] = (source, job_id)
                add("run", source)
                candidates, confirmation = data.get("candidates"), data.get("confirmation")
                if not isinstance(candidates, list) or (
                    confirmation is not None and not isinstance(confirmation, dict)
                ):
                    raise ResourceNotFound()
                groups = candidates + ([confirmation] if confirmation is not None else [])
                for group in groups:
                    if not isinstance(group, dict) or not isinstance(group.get("pairs"), list):
                        raise ResourceNotFound()
                    for pair in group["pairs"]:
                        if not isinstance(pair, dict):
                            raise ResourceNotFound()
                        for arm in ("control_run", "treatment_run"):
                            if arm not in pair:
                                continue
                            trial = identifier(pair[arm])
                            if trial in claims:
                                raise ResourceNotFound()
                            claims[trial] = (source, job_id)
                            add("run", trial)
        by_study_job: dict[str, str] = {}
        for source, job_id in studies.values():
            if (
                self.jobs[job_id]["kind"] not in {"study", "investigate"}
                or job_id in by_study_job
                or run_jobs[source] == job_id
            ):
                raise ResourceNotFound()
            by_study_job[job_id] = source
        for run_id, job_id in run_jobs.items():
            job_kind = self.jobs[job_id]["kind"]
            if (job_kind == "run") != (parents[run_id] is None):
                raise ResourceNotFound()
            if job_kind in {"study", "investigate"} and (
                job_id not in by_study_job or parents[run_id] != by_study_job[job_id]
            ):
                raise ResourceNotFound()
        for trial, (source, job_id) in claims.items():
            if parents[trial] != source or run_jobs[trial] != job_id:
                raise ResourceNotFound()
        for run_id in parents:
            seen: set[str] = set()
            current: str | None = run_id
            depth = 0
            while current is not None:
                if current in seen or depth > MAX_PARENT_DEPTH:
                    raise ResourceNotFound()
                seen.add(current)
                current = parents[current]
                depth += 1
        return self.jobs[resource_id] if kind == "job" else self.records[(kind, resource_id)]
