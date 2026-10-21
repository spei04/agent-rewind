import difflib
from typing import Any

from .artifacts import Artifacts
from .database import Database
from .engine import read_events
from .legacy_reads import append_response, bounded_response
from .workspace import File


def compare(
    db: Database, artifacts: Artifacts, left: str, right: str, limit: int
) -> dict[str, Any]:
    left_run, right_run = db.get(left, "run"), db.get(right, "run")
    a, b = read_events(db, artifacts, left), read_events(db, artifacts, right)
    before = (
        artifacts.workspace(left_run["final_workspace"], limit)
        if left_run.get("final_workspace")
        else None
    )
    after = (
        artifacts.workspace(right_run["final_workspace"], limit)
        if right_run.get("final_workspace")
        else None
    )
    return compare_presentations(left_run, right_run, a, b, before, after)


def compare_presentations(
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
    before: dict[str, File] | None,
    after: dict[str, File] | None,
) -> dict[str, Any]:
    """Pure bounded presentation of already authorized and verified inputs."""
    used = 0
    decisions: list[Any] = []
    for index in range(max(len(a), len(b))):
        first = a[index] if index < len(a) else None
        second = b[index] if index < len(b) else None
        if (
            first is None
            or second is None
            or any(first[k] != second[k] for k in ("action", "observed_result", "workspace_after"))
        ):
            used = append_response(
                decisions,
                {
                    "step": index + 1,
                    "left_action": first["action"] if first else None,
                    "right_action": second["action"] if second else None,
                    "observation_changed": first is None
                    or second is None
                    or first["observed_result"] != second["observed_result"],
                },
                used,
            )
    diffs: list[Any] = []
    if before is not None and after is not None:
        for path in sorted(before.keys() | after.keys()):
            if before.get(path) == after.get(path):
                continue
            a_file, b_file = before.get(path), after.get(path)
            text = "".join(
                difflib.unified_diff(
                    a_file.data[:100000].decode(errors="replace").splitlines(keepends=True)
                    if a_file
                    else [],
                    b_file.data[:100000].decode(errors="replace").splitlines(keepends=True)
                    if b_file
                    else [],
                    fromfile=f"source/{path}",
                    tofile=f"branch/{path}",
                )
            )
            used = append_response(
                diffs,
                {
                    "path": path,
                    "diff": text[:12000],
                    "mode_before": a_file.mode if a_file else None,
                    "mode_after": b_file.mode if b_file else None,
                },
                used,
            )
    return bounded_response(
        {
            "left": left_run["id"],
            "right": right_run["id"],
            "left_success": left_run.get("success"),
            "right_success": right_run.get("success"),
            "decisions": decisions,
            "files": diffs,
        }
    )
