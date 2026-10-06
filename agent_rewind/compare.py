import difflib
from typing import Any

from .artifacts import Artifacts
from .database import Database
from .engine import read_events


def compare(
    db: Database, artifacts: Artifacts, left: str, right: str, limit: int
) -> dict[str, Any]:
    left_run, right_run = db.get(left, "run"), db.get(right, "run")
    a, b = read_events(db, artifacts, left), read_events(db, artifacts, right)
    decisions = []
    for index in range(max(len(a), len(b))):
        first = a[index] if index < len(a) else None
        second = b[index] if index < len(b) else None
        if (
            first is None
            or second is None
            or any(first[k] != second[k] for k in ("action", "observed_result", "workspace_after"))
        ):
            decisions.append(
                {
                    "step": index + 1,
                    "left_action": first["action"] if first else None,
                    "right_action": second["action"] if second else None,
                    "observation_changed": first is None
                    or second is None
                    or first["observed_result"] != second["observed_result"],
                }
            )
    diffs = []
    if left_run.get("final_workspace") and right_run.get("final_workspace"):
        before = artifacts.workspace(left_run["final_workspace"], limit)
        after = artifacts.workspace(right_run["final_workspace"], limit)
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
            diffs.append(
                {
                    "path": path,
                    "diff": text[:12000],
                    "mode_before": a_file.mode if a_file else None,
                    "mode_after": b_file.mode if b_file else None,
                }
            )
    return {
        "left": left,
        "right": right,
        "left_success": left_run.get("success"),
        "right_success": right_run.get("success"),
        "decisions": decisions,
        "files": diffs,
    }
