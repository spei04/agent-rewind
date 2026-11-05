# Engineering assignment log

## Current status — November 5, 2026

- F3 is delivered. F4 candidate `e02ad6b` remains frozen; collection evidence retains its timing qualification.
- Replacement 2 passed preflight, then stopped on an admission-reader schema error. Zero tests ran. Failure evidence, process cleanup and closeout were independently verified; the candidate is not accepted.
- The reader correction and remaining evidence contracts passed source review. [The continuation proposal](F4_VALIDATION_PLAN.md) requires an explicit scratch reassignment and a reviewed successor entry; no further execution is authorized.

| Engineer | Assignment | Status |
| --- | --- | --- |
| Runtime | Correct the admission reader against retained originals; map remaining evidence contracts. | Source correction and contract audit independently accepted. |
| Package | Preserve the frozen package, allocation and closeout contracts. | Package stage not started. |
| Quality | Review actual failure and closeout; independently review the reader correction. | Failure, closeout and source correction independently reviewed. |
| Capacity | Calculate continuation deltas without reservation credits. | Narrow scratch-reassignment proposal prepared; no hold changed. |
| Lead | Retain originals, update progress and prepare the next stopped entry. | Attempt closed; successor entry remains unready and unauthorized. |

[Roadmap](PLAN.md) · [Execution backlog](EXECUTION_BACKLOG.md#ar-010-b) · [Earlier validation status](https://github.com/spei04/agent-rewind/blob/1dfcdb7b37fa7f076684aa620759c634654883a3/docs/ASSIGNMENTS.md) · [History through F3](https://github.com/spei04/agent-rewind/blob/439fca552bf8bee05d223a6e7c174e55a1d70d00/docs/ASSIGNMENTS.md)

This is the canonical current summary. Detailed evidence remains private. Source review does not establish a runtime, production-readiness or research pass.
