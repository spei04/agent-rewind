"""Bounded relational ancestry only; encrypted artifact closure is a later gate."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .inputs import _unique_object
from .schema import MigrationRefused, canonical, checksum

MAX_RESOURCES = 100000
MAX_EDGES = 200000
MAX_RETAINED_BYTES = 32 * 1024 * 1024
MAX_PARENT_DEPTH = 64
ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Closure:
    resources: tuple[tuple[str, str], ...]
    digest: str
    keys: dict[str, tuple[bool, float]]


def _id(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise MigrationRefused("ownership_lineage_invalid")
    return value


def relational_closure(connection: Connection) -> Closure:
    """Keep only capped identifiers/edges, never accumulated source JSON bodies."""

    def rows(sql: str) -> Any:
        return connection.execute(
            text(sql).execution_options(stream_results=True, yield_per=1, max_row_buffer=1)
        )

    return reduce_relational_closure(rows)


def reduce_relational_closure(
    rows: Callable[[str], Iterable[Any]],
    *,
    check: Callable[[], None] | None = None,
    projects: dict[tuple[str, str], str] | None = None,
) -> Closure:
    """Shared relational proof; supplied rows own transport and optional scope checks."""
    resources: list[tuple[str, str]] = []
    edges: list[tuple[str, ...]] = []
    retained_bytes = 0
    parents: dict[str, str | None] = {}
    run_jobs: dict[str, str] = {}
    jobs: dict[str, str] = {}
    studies: dict[str, tuple[str, str]] = {}
    trial_claims: dict[str, tuple[str, str, str]] = {}
    keys: dict[str, tuple[bool, float]] = {}

    def retain(value: tuple[str, ...], *, resource: bool = False) -> None:
        nonlocal retained_bytes
        if check is not None:
            check()
        retained_bytes += len(canonical(value))
        if resource and projects is not None:
            project = projects.get((value[0], value[1]))
            if project is None:
                raise MigrationRefused("ownership_lineage_invalid")
            retained_bytes += len(canonical((value[0], value[1], project)))
        if retained_bytes > MAX_RETAINED_BYTES:
            raise MigrationRefused("ownership_closure_limit")
        if resource:
            if len(resources) >= MAX_RESOURCES:
                raise MigrationRefused("ownership_closure_limit")
            resources.append((value[0], value[1]))
        else:
            if len(edges) >= MAX_EDGES:
                raise MigrationRefused("ownership_closure_limit")
            edges.append(value)

    for row in rows("SELECT id,kind FROM jobs ORDER BY id"):
        identifier = _id(row.id)
        if row.kind not in {"run", "branch", "study", "investigate"}:
            raise MigrationRefused("ownership_lineage_invalid")
        retain(("job", identifier), resource=True)
        jobs[identifier] = row.kind
    for row in rows("SELECT id,revoked,expires FROM api_keys ORDER BY id"):
        identifier = _id(row.id)
        if row.revoked not in (None, False, True, 0, 1):
            raise MigrationRefused("ownership_lineage_invalid")
        if not isinstance(row.expires, int | float) or not math.isfinite(row.expires):
            raise MigrationRefused("ownership_lineage_invalid")
        retain(("key", identifier), resource=True)
        keys[identifier] = (row.revoked in (True, 1), float(row.expires))
    for row in rows("SELECT id,kind,CAST(data AS TEXT) AS data FROM records ORDER BY id"):
        identifier = _id(row.id)
        try:
            data = json.loads(row.data, object_pairs_hook=_unique_object)
        except (ValueError, TypeError, RecursionError):
            raise MigrationRefused("ownership_lineage_invalid") from None
        if not isinstance(data, dict) or row.kind not in {"run", "study"}:
            raise MigrationRefused("ownership_lineage_invalid")
        retain((row.kind, identifier), resource=True)
        job_id = _id(data.get("job_id"))
        if job_id not in jobs:
            raise MigrationRefused("ownership_lineage_invalid")
        retain((row.kind, identifier, "job", job_id))
        if row.kind == "run":
            if "parent_id" not in data:
                raise MigrationRefused("ownership_lineage_invalid")
            parent = None if data["parent_id"] is None else _id(data["parent_id"])
            if parent:
                retain(("run", identifier, "parent", parent))
            parents[identifier], run_jobs[identifier] = parent, job_id
            if (jobs[job_id] == "run" and parent is not None) or (
                jobs[job_id] != "run" and parent is None
            ):
                raise MigrationRefused("ownership_lineage_invalid")
        else:
            source = _id(data.get("source_run"))
            request = data.get("request")
            if (
                not isinstance(request, dict)
                or request.get("run_id") != source
                or jobs[job_id] not in {"study", "investigate"}
            ):
                raise MigrationRefused("ownership_lineage_invalid")
            retain(("study", identifier, "source", source))
            studies[identifier] = (source, job_id)
            candidates = data.get("candidates")
            confirmation = data.get("confirmation")
            if not isinstance(candidates, list) or (
                confirmation is not None and not isinstance(confirmation, dict)
            ):
                raise MigrationRefused("ownership_lineage_invalid")
            groups = candidates + ([confirmation] if confirmation is not None else [])
            for group_index, group in enumerate(groups):
                if not isinstance(group, dict) or not isinstance(group.get("pairs"), list):
                    raise MigrationRefused("ownership_lineage_invalid")
                for pair_index, pair in enumerate(group["pairs"]):
                    if not isinstance(pair, dict):
                        raise MigrationRefused("ownership_lineage_invalid")
                    for arm in ("control", "treatment"):
                        field = arm + "_run"
                        if field not in pair:
                            continue
                        trial = _id(pair[field])
                        if trial in trial_claims:
                            raise MigrationRefused("ownership_ambiguous_trial")
                        retain(("study", identifier, str(group_index), str(pair_index), arm, trial))
                        trial_claims[trial] = (identifier, source, job_id)
        del data
    # Iterative, memoized walks also bound a late long chain which joins a known suffix.
    depths: dict[str, int] = {}
    for run in parents:
        if check is not None:
            check()
        trail: list[str] = []
        seen: set[str] = set()
        current: str | None = run
        while current is not None and current not in depths:
            if current not in parents or current in seen:
                raise MigrationRefused("ownership_lineage_invalid")
            if len(trail) > MAX_PARENT_DEPTH:
                raise MigrationRefused("ownership_ancestry_limit")
            trail.append(current)
            seen.add(current)
            current = parents[current]
        depth = -1 if current is None else depths[current]
        for member in reversed(trail):
            depth += 1
            if depth > MAX_PARENT_DEPTH:
                raise MigrationRefused("ownership_ancestry_limit")
            depths[member] = depth
    study_jobs = [job for source, job in studies.values()]
    if len(set(study_jobs)) != len(study_jobs):
        raise MigrationRefused("ownership_ambiguous_trial")
    for source, job in studies.values():
        if source not in parents or run_jobs[source] == job:
            raise MigrationRefused("ownership_lineage_invalid")
    for trial, (_study, source, job) in trial_claims.items():
        if trial not in parents or parents[trial] != source or run_jobs[trial] != job:
            raise MigrationRefused("ownership_lineage_invalid")
    study_sources = {job: source for source, job in studies.values()}
    for run, job in run_jobs.items():
        if jobs[job] in {"study", "investigate"} and (
            job not in study_sources or parents[run] != study_sources[job]
        ):
            # engine.run persists a child before it returns the arm ID. Failure
            # can leave it unclaimed by a pair, but the unique study job and
            # source parent still establish SQL ownership, not outcome evidence.
            raise MigrationRefused("ownership_ambiguous_trial")
    for row in rows("SELECT run_id,step FROM events ORDER BY run_id,step"):
        if row.run_id not in parents or type(row.step) is not int or row.step < 1:
            raise MigrationRefused("ownership_lineage_invalid")
        retain(("event", _id(row.run_id), str(row.step)))
    if projects is not None:
        for edge in edges:
            if check is not None:
                check()
            if edge[0] == "event":
                continue
            if len(edge) == 4:
                target_kind = "job" if edge[2] == "job" else "run"
                target_id = edge[3]
            else:
                target_kind, target_id = "run", edge[5]
            if projects[(edge[0], edge[1])] != projects.get((target_kind, target_id)):
                raise MigrationRefused("ownership_lineage_invalid")
    ordered = tuple(sorted(resources))
    return Closure(ordered, checksum({"resources": ordered, "edges": sorted(edges)}), keys)
