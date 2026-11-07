# Engineering assignment log

## Current status — November 7, 2026 UTC

- F1–F3 are delivered. F4 candidate `e02ad6b` remains frozen and unaccepted.
- The approved R3 attempt stopped before product tests. R1's unused future 4 GiB hold was retired and independently read back. Preflight wrote the new R3 allocation, but its admission reader rejected a request missing the original clock fields.
- No retry, paid provider call, hosted CI or production deployment occurred. The written R3 allocation and earlier charges remain retained.
- The [outcome and correction plan](F4_VALIDATION_PLAN.md) records the exact failure, evidence limits and next source work. The consumed R3 approval cannot authorize another attempt.

| Engineer | Assignment | Result |
| --- | --- | --- |
| Runtime | Reconstruct the failed reader boundary and propose a scoped correction. | Confirmed missing clock fields in the nested request; outer 124 was not a timeout. Identified the same omission in the unused root-exit path. |
| Quality | Independently verify retirement, allocation, original outputs and closeout. | Accepted failed-attempt evidence only. Zero product tests; no F4 acceptance. |
| Lead | Execute the one-use procedure, preserve results and update the roadmap. | Preserved original failure output after closeout; recorded the timing and retention limitations. Next source correction is scoped below. |

The next source work repairs the affected payload contracts, preserves failed control outputs through the normal API, and adds integration regressions before another execution proposal. No new execution is scheduled.

[Roadmap](PLAN.md) · [Execution backlog](EXECUTION_BACKLOG.md#ar-010-b) · [Approved preparation package](https://github.com/spei04/agent-rewind/blob/b2bd4765c40fbfc13cac14878404c775fcc36c34/docs/F4_VALIDATION_PLAN.md)

Detailed evidence remains private. Source checks and failed-attempt evidence are not product acceptance, production readiness or research results.
