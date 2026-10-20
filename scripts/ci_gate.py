"""Fail closed on every required CI job, including omitted or skipped jobs."""

import json
import os

REQUIRED_JOBS = frozenset({"core", "isolation", "security", "package"})


def check_results(results: object) -> None:
    if not isinstance(results, dict) or set(results) != REQUIRED_JOBS:
        raise ValueError("CI gate received an unexpected required-job set")
    for name, result in results.items():
        if not isinstance(result, dict) or result.get("result") != "success":
            raise ValueError(f"Required job did not succeed: {name}")


if __name__ == "__main__":
    check_results(json.loads(os.environ["CI_JOB_RESULTS"]))
    print("Every required CI job succeeded.")
