# Operation HTTP execution plan

2026-10-21 · Planning amendment for the existing AR-008-B scope, based on published source 5d3ff3096d81f159a457870a1f4fa57590a06cc2. AR-008-B and both packages remain **Not started**. AR-008-A/P3 is Implemented; verification pending. This plan does not accept its pending CI, merge or candidate, implement routes, or enable customer admission.

The design-only [P1 adapter entry checkpoint](OPERATION_ADAPTER_ENTRY.md) proposes concrete APIs, cumulative bounds and the initial unavailable-failure support table. Tracking is aggregate [#93](https://github.com/spei04/agent-rewind/issues/93), P1 [#94](https://github.com/spei04/agent-rewind/issues/94), P2 [#95](https://github.com/spei04/agent-rewind/issues/95); all remain Not started.

## Entry and delivery boundaries

Retain direct prerequisites AR-008-A and AR-011-B and frozen C04. Both packages inherit the aggregate entry gate: accepted AR-008-A, including P3's matching hosted checks, accepted merge and protected-main candidate, plus Verified AR-011-B. P2 additionally requires accepted merged P1. Planning assignment is not runtime assignment. AR-006-B remains the owner of run list/detail/cursors; later AR-010-A/B own generation, ledger and worker dispatch. No reverse worker dependency is added.

| Package | Independently reviewable scope | Base / range | Exit |
| --- | --- | --- | --- |
| AR-008-B/P1 | Bounded Operation read and same-Connection cancellation adapters; producer decision checkpoint | 2 / 2–3 BE days | Reviewed supported-source/cancellation tables, SQLite and actual PostgreSQL evidence, matching hosted checks and accepted merge |
| AR-008-B/P2 | Exactly submit, operation status and cancellation HTTP, using accepted P1 and coordinator | 2 / 2–3 BE days | Full HTTP/contract/race and installed-package matrix, independent review, accepted merge and protected-main candidate |

Total **4 [4–6] BE days, medium-low confidence**, replacing provisional 3 [3–5]. The extra day accounts for the absent status producer and operation-bound cancellation, not another API feature. Reforecast if the concrete producer decision requires work beyond these adapters; do not silently implement worker persistence or weaken refusal to fit the estimate. The full cards are in the [backlog](../EXECUTION_BACKLOG.md#ar-008-b) and [ledger](../../contracts/proposals/execution-backlog.json).

Recomputed portfolio: 151 aggregate tasks, 157 delivery PRs, 52 parents, 544 outer edges, 27 gates and 20 contracts; 457 base days, 772.1 summed upper days, alternative 571.25 days with a 25% allowance, M1 58.5 and BE 90.5. The effort-only critical path is 169.5 days. Relative to the published baseline this is +1 base, +1 upper and +1 PR, with no outer edge/status change. These are engineering estimates, not elapsed-time or spending commitments.

## Frozen responses and actual producer seams

The authority for wire shape remains [m1.openapi.json](../../contracts/proposals/m1.openapi.json) and [C04](M1_CONTRACT_FREEZE.md#errors-limits-and-consumer-compatibility); this amendment changes neither. All declared fields remain required, including nullable values and false booleans.

| Operation | Success | Exact response fields |
| --- | --- | --- |
| POST /api/v1/projects/{project_id}/runs — submitProjectRun | 202 Accepted | operation_id, job_id |
| GET /api/v1/projects/{project_id}/operations/{operation_id} — getProjectOperation | 200 Operation | id, project_id, job_id, client_operation_id, status, cancel_requested, result_run_id, budget_microusd, reserved_microusd, error |
| POST /api/v1/projects/{project_id}/operations/{operation_id}/cancel — cancelProjectOperation | 202 Cancellation | operation_id, cancel_requested, status |

Operation status is queued/running/succeeded/failed/cancelled execution state. It is not evaluator success: a successfully executed job may produce a run with success=false. Cancellation reports cancel_requested=true. Required result_run_id and error nulls remain explicit. Budget is a positive integer microUSD value; reserved is a nonnegative gross cumulative reservation, not a current hold, refund, charge or invoice total. Reject malformed types, including bool-as-integer, rather than coercing them.

Existing seams at the pinned source:

- AdmissionRepository.get_operation is viewer-readable under current named-project authority; it proves operation/config/job association but returns stored identity, not the HTTP Operation view. Submit/replay remains creator-bound. Status/cancel must not accidentally impose creator-only replay semantics.
- The coordinator submit(principal, original_context, intent, key_hash, origin) returns the original Accepted after its own fresh checks. Its SQL-only reconcile remains an internal recovery seam; no new reconcile endpoint is added.
- LegacyViews.jobs demonstrates strict job-owned result reads and original source/ref receipts. Reuse narrowly where behavior is identical; do not load an entire job list or workspace graph to render one operation.
- ScopedActions.cancel owns its own transaction and returns None. A separate operation lookup followed by that method does not bind operation→job during mutation. P1 must provide the narrow same-Connection effect/operation adapter while preserving legacy callers.

P1 chooses concrete adapter names and finite query/byte/work ceilings at its entry design review, reusing existing bounded SQL, authority and transaction helpers. It must not add a generic operation framework or new global engine behavior. Bound selected cells before transfer/JSON decoding, keep invalid candidates as refusal markers, and retain original operation/job/config/scope and all seven descriptor fields through final bounded SQL checks. Reauthorize after I/O; an original snapshot or signed identity is not lasting authority. No partial status response after a failed final check.

## Supported source table and failure-producer decision

| Observed evidence | Required behavior |
| --- | --- |
| Valid authorized operation and associated job, with null result and no required failure evidence | Return current validated status/accounting values, result_run_id:null and error:null |
| Non-null job result digest | Resolve exact job-owned role=result reference, verify bounded bytes with exact {run_id} shape, then prove same-project run lineage and run.job_id==operation.job_id; retain original receipts across all loads |
| Missing, foreign, corrupt, oversized or unknown result evidence | Fixed safe unavailable refusal; never guess by latest run, records.by_job, run_index, raw hash or locator |
| Succeeded job with evaluator success=false | Preserve status:succeeded; do not relabel it failed |
| Actual supported bounded stored Error envelope with matching original correlation | Return Operation HTTP 200, including nested outcome_uncertain; the polling response gets a separate fresh header ID |
| Legacy jobs.error string, malformed/unsupported envelope, or missing required failure evidence | Fixed 503 dependency_unavailable; do not expose raw text, hide corruption as null, or fabricate a trusted envelope |
| Unknown/inaccessible operation or current access revoked | 404 without result/storage disclosure; a visible operation with a denied action yields 403 |

**Unresolved representation decision, mandatory before P1 runtime:** current worker.py writes legacy fixed exception-class text to jobs.error. operations.failure_correlation_id records origin; neither fact proves a stored four-field Error envelope. Freeze the exact bounded producer representation, parsing/validation and allowlisted safe mapping for any supported envelope, with real producer vectors and original-correlation association. Do not parse arbitrary legacy strings into an envelope or treat a poll ID as the historical origin. Until such evidence is supported, that case refuses with fixed 503; its schema declaration is not availability evidence.

Healthy supported rows with null error are implementable now. Failure cases requiring an absent producer remain unavailable, even if their SQL shape is otherwise valid. The finite table must distinguish legitimate null from missing required failure evidence before implementation; no inference from an arbitrary class name, status string or truthiness. Later worker failures and their persistence remain a worker-producer obligation and AR-012-B integration requirement. No new worker prerequisite or worker/schema implementation is included here.

C04's historical missing-correlation migration-marker obligation remains explicit. A GET neither invents nor persists that marker; unsupported historical evidence refuses until its owning migration/producer supplies reviewed evidence. A proposed representation requiring schema or producer changes must be returned as a scoped design finding, not silently added to P1. Original failure IDs remain stable over repeated polling; only the poll header/request error correlation is fresh.

## Cancellation transaction

Resolve scoped visibility without disclosing inaccessible resources, then use one owned transaction and the accepted exclusion order: project → organization → caller membership/key → target scope/job. Lock and revalidate the original operation association within that transaction; an operation row replacement while waiting must not redirect cancellation. Freshly authorize cancel on the associated job immediately before effects, using the same Connection and original trusted principal/project context. Association, role, membership, token expiry/revocation and target changes all remain relevant.

| Locked job state | Effect and response |
| --- | --- |
| queued | Set cancel=true and status=cancelled |
| running | Set cancel=true; retain status=running |
| succeeded, failed or cancelled | Set cancel=true; retain terminal status and outcome |
| Unknown/malformed state or association | Refuse safely; no effect or audit |

Preserve result/error, owner/lease, budget and reserved values. Write the fixed job.cancel audit for the same job under the same transaction; no new audit platform or provider-cancellation/refund claim. Repeated calls remain repeated intent. Return the exact operation_id/cancel_requested/status snapshot only after acknowledged commit and fresh authorized disclosure. A worker may subsequently advance state; the response is an acknowledged snapshot, not a permanent lock.

No storage, provider, readiness or network I/O runs under these locks. Known rollback is not success; ambiguous commit acknowledgment is outcome_uncertain with no automatic mutation retry. Cleanup failures must preserve transaction uncertainty and fixed diagnostics. Existing legacy cancellation behavior remains covered by regression tests; extraction must not silently change it.

## HTTP ordering and error boundary

1. Preserve the existing security/migration guard. The actual migration_only schema returns fixed 503 before customer database/storage/admission/readiness/audit sinks. No synthetic ready profile may leak between app instances or become a production default. The existing transport BodyLimit retains its early received-byte protection; authority-first ordering here governs application parsing and semantic diagnostics, not buffering an unbounded unauthenticated body.
2. Authenticate through actual Auth.principal and resolve named-project visibility, with no dependence on a legacy default. For operation targets establish resource visibility before action denial. Preserve current live key∩membership role and exact cookie CSRF/Origin on both POSTs; GET does not need mutation CSRF. Invalid explicit bearer credentials never fall back to a cookie.
3. Validate transport manually after the appropriate authority checks. Avoid eager FastAPI Body/Path/Header constraints changing 401/404 precedence; use metadata-only declarations for frozen patterns. Preserve duplicate JSON members and headers instead of first converting them to dictionaries.
4. Submit raw bytes to parse_submit, enforcing the 9 MiB received-body bound, including chunked requests, and the independent 8 MiB canonical materialized TaskSpec bound. Only identity content encoding is supported; reject compressed/unsupported transport safely, with no expansion. Preserve exact source text, defaults, duplicate/unknown-key and nonfinite/integer/path validation.
5. Require exactly one Idempotency-Key, 8–128 ASCII characters matching [A-Za-z0-9._:-]+. Do not trim, case-fold or collapse duplicates. Hash exact accepted bytes for the coordinator's scoped key_hash. Pass the server-generated request-boundary OriginCorrelation, never client header/body data.
6. Call the accepted coordinator directly. The old legacy admit helper probes readiness before identity recovery and is not a substitute. Existing committed replay bypasses current new-work policy/config/readiness/journal/storage, while fresh authority and SQL association checks remain mandatory. Required unavailable adapters refuse genuinely new work before readiness probes or external I/O.

Errors keep exactly code/message/request_id/retryable, finite safe messages and fresh generated 32-hex X-Request-ID plus Cache-Control:no-store. Preserve Bearer challenge for 401 and bounded Retry-After for actual 429 outcomes. Compare the complete frozen response/status/header and parameter metadata for these three operations, including null alternatives. Do not change legacy error representation or already accepted list/detail contracts.

| Boundary outcome | HTTP classification |
| --- | --- |
| Missing/invalid identity; hidden resource; visible denied action | Existing fixed 401 / 404 / 403 respectively |
| Invalid request or malformed idempotency transport | Fixed 422 invalid_request after authority |
| Received or canonical task limit exceeded | Fixed 413 invalid_request with the accurate violated bound; do not label the 8 MiB semantic limit as 9 MiB |
| Compared canonical identity conflict | 409 idempotency_conflict |
| Known precommit dependency unavailable; incompatible schema | Existing fixed 503 dependency_unavailable or schema_incompatible |
| Ambiguous outcome | 503 outcome_uncertain, retryable=false; never upload/new-job fallback |
| Supported stored outcome_uncertain inside an Operation | HTTP 200 data with stored origin and fresh polling header |
| Actual later quota/budget producer result | Preserve the frozen declared mapping when the producer exists; no fabricated quota, budget or paid-dispatch success |

Generic ValueError, IntegrityError or raw dependency text is not automatically user input or a safe conflict. Keep unforeseen failures within the existing sanitized 500 boundary. Confirm exact permitted error-code spelling and messages against frozen C04 and current safe-error producers at implementation review, without widening the contract.

## Required evidence and completion

P1 requires bounded SQLite and actual PostgreSQL tests for malformed selected cells, operation/config/job association drift, exact scoped result evidence and all seven descriptor fields, missing/corrupt/foreign bodies, shared cumulative work bounds and final authority. Include succeeded/evaluator-false and raw-error canaries. Supported stored failure fixtures must come from the reviewed producer contract; repeated 200 polls preserve origin and change only the polling header.

Cancellation evidence includes both observed lock orders for membership/key revocation, operation→job replacement while waiting, worker terminal transition, viewer read versus cancel403 and foreign404, no audit on denied/unknown targets, reservation/terminal preservation, repeated intent, rollback, lost acknowledgment and cleanup. Use bounded barriers and actual PostgreSQL locks, not sleeps or SQLite-only concurrency claims.

P2 exercises actual cookie and service-key HTTP requests in two populated projects, absent/other legacy defaults, malformed-path/input precedence, duplicates, exact byte limits and source/default canonical vectors. Cover eight concurrent original-identity submissions, alias/conflict behavior, config/storage-outage replay and unresolved-outcome refusal. Preserve creator-only submit recovery while allowing authorized project viewer status. Test final source/ref/authority changes, migration-only zero sinks, unavailable new-work dependencies before probes, accurate errors/headers and complete generated OpenAPI parity.

Installed wheel/sdist smoke exercises the new service/routes only through isolated synthetic per-app fixtures, preserving the installed-source provenance guard and actual production refusal in another instance. Local helper tests or explicit PostgreSQL skips are not installed or database proof. Matching hosted checks, independent review and accepted merge are required for each package; aggregate completion also needs protected-main/candidate acceptance. Later full M1 worker/ledger/failure-producer behavior remains AR-012-B and its existing producers.

No code, schema, profile, frozen contract, historical schedule, task dependency, worker/customer activation or paid resource changes follow from this planning amendment.
