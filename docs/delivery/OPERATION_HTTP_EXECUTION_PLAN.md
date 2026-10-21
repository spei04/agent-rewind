# Operation HTTP execution plan

2026-10-21 · Planning amendment for the existing AR-008-B scope, originally prepared against source 5d3ff3096d81f159a457870a1f4fa57590a06cc2. P1 is **Verified** at merge 03a8e074 after [accepted delivery](#accepted-p1-delivery--2026-10-21); aggregate AR-008-B and P2 are **In progress**. HTTP implementation, independent PostgreSQL tests and installed-package proof are complete as components. C reviews final composition, B reviews hosted delivery and the lead integrates; A performs read-only successor readiness review. HTTP delivery remains subject to matching hosted checks, accepted merge and protected-main candidate verification. AR-008-A/P3 and aggregate A remain Verified after [accepted PR/main/candidate evidence](ADMISSION_EXECUTION_PLAN.md#accepted-p3-delivery--2026-10-21). Default adapters/customer admission remain unavailable.

The design-only [P1 adapter entry checkpoint](OPERATION_ADAPTER_ENTRY.md) proposes concrete APIs, cumulative bounds and the initial unavailable-failure support table. Tracking is aggregate [#93](https://github.com/spei04/agent-rewind/issues/93), P1 [#94](https://github.com/spei04/agent-rewind/issues/94), P2 [#95](https://github.com/spei04/agent-rewind/issues/95); P1 is Verified/closed; aggregate and P2 are In progress.

## Entry and delivery boundaries

Retain direct prerequisites AR-008-A and AR-011-B and frozen C04. Both packages inherit the aggregate entry gate: accepted AR-008-A, including P3's matching hosted checks, accepted merge and protected-main candidate, plus Verified AR-011-B. P2 additionally requires accepted merged P1. Planning assignment is not runtime assignment. AR-006-B remains the owner of run list/detail/cursors; later AR-010-A/B own generation, ledger and worker dispatch. No reverse worker dependency is added.

| Package | Independently reviewable scope | Base / range | Exit |
| --- | --- | --- | --- |
| AR-008-B/P1 | Bounded Operation read/cancel adapters; factory-born SQLite ownership and producer checkpoint | 4 / 4–7 BE days | Reviewed ownership/source/cancellation tables, all shared-engine caller and SQLite/PostgreSQL proof, matching hosted checks and accepted merge |
| AR-008-B/P2 | Exactly submit, operation status and cancellation HTTP, using accepted P1 and coordinator | 2 / 2–3 BE days | Full HTTP/contract/race and installed-package matrix, independent review, accepted merge and protected-main candidate |

Total **6 [6–10] BE days, medium-low confidence**. The original adapter/HTTP reconciliation replaced provisional 3 [3–5] with 4 [4–6]; the current two additional P1 days account for the measured SQLite callback-ownership gap, generation-bound post-close verdicts and explicit 33-site/14-module caller adaptation. The first ownership draft's 3 [3–5] P1 estimate was superseded after the missing ordinary-caller reporting boundary was identified. Reforecast if the concrete producer decision requires work beyond these adapters; do not silently implement worker persistence or weaken refusal to fit the estimate. The full cards are in the [backlog](../EXECUTION_BACKLOG.md#ar-008-b) and [ledger](../../contracts/proposals/execution-backlog.json).

At the original operation HTTP planning checkpoint: 151 aggregate tasks, 157 delivery PRs, 52 parents, 544 outer edges, 27 gates and 20 contracts; 457 base days, 772.1 summed upper days, alternative 571.25 days with a 25% allowance, M1 58.5 and BE 90.5. The effort-only critical path is 169.5 days. Relative to the published baseline this is +1 base, +1 upper and +1 PR, with no outer edge/status change. These are engineering estimates, not elapsed-time or spending commitments.

The current ownership reforecast retains 151 tasks, 158 delivery PRs, 544 outer
edges, 52 parents, 27 gates and 20 contracts: **461 base / 779.1 upper / 576.25
alternative allowance / 173.5 effort-path days**, with M1 62.5 and BE 94.5.
Parent AR-008 totals 13 days. Earlier checkpoint totals above remain history.
B/lead accepted ownership entry **5bedede** and C independently confirmed the
acquisition map. The complete caller, factory and service implementation is now
accepted at **03a8e074**, including full hosted and candidate proof below.
P2 HTTP entry and implementation have separate review and delivery gates.
Aggregate #93, parent #8 and all later customer/production gates remain open.

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

P1 chooses concrete adapter names and finite query/byte/work ceilings at its entry design review, reusing existing bounded SQL, authority and transaction helpers. The [ownership amendment](OPERATION_ADAPTER_ENTRY.md#sqlite-callback-ownership-amendment--accepted-entry) permits only a factory-born SQLite lifecycle policy and shared progress lease; work-budget listeners remain Connection-local. No generic operation framework or broader engine policy change is included. Bound selected cells before transfer/JSON decoding, keep invalid candidates as refusal markers, and retain original operation/job/config/scope and all seven descriptor fields through final bounded SQL checks. Reauthorize after I/O; an original snapshot or signed identity is not lasting authority. No partial status response after a failed final check.

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

**Initial support decision, frozen by the [GET entry](OPERATION_GET_ENTRY.md):** current worker.py writes legacy fixed exception-class text to jobs.error. No stored Error envelope is supported by the initial adapter. Queued/running/succeeded/cancelled with SQL NULL error may render; failed with NULL or any non-NULL error refuses with fixed 503. operations.failure_correlation_id is origin evidence, not a trusted envelope. AR-010-B retains the later bounded representation, provenance and consumer handoff. Any future supported envelope needs its exact reviewed producer vectors and original-correlation association; never infer one from a legacy string or polling ID.

Healthy supported rows with null error are implementable now. Failure cases requiring an absent producer remain unavailable, even if their SQL shape is otherwise valid. The finite table must distinguish legitimate null from missing required failure evidence before implementation; no inference from an arbitrary class name, status string or truthiness. AR-010-B/P1 owns the complete chosen bounded failure persistence/version/provenance/parser and consumer handoff, including the operator-only historical-marker path; AR-010-B/P2 integrates both normal completion and database-time conditional lease expiry with their distinct fences. AR-012-B verifies that accepted integration rather than implementing the omitted producer. The two sequential 2 [2–3] BE packages total 4 [4–6], medium-low, and inherit AR-010-A/AR-005-C. No new AR-008-B prerequisite or worker/schema implementation is included here; current portfolio rollups are in the roadmap/backlog.

C04's historical missing-correlation migration-marker obligation remains explicit. A GET neither invents nor persists that marker; unsupported historical evidence refuses until AR-010-B/P1 supplies its reviewed operator-only, idempotent marker/provenance evidence without rewriting original rows, audit, ciphertexts or hash history. P1 must freeze encoding/native bounds and any necessary migration owner/revision/catalog/preservation/rollback/restore decision before implementation, reforecasting if broader; this plan does not choose a schema. A proposed representation requiring schema or producer changes must be returned as a scoped design finding, not silently added to P1. Original failure IDs remain stable over repeated polling; only the poll header/request error correlation is fresh.

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

<a id="p1-implementation-assignment--2026-10-21"></a>

## Earlier P1 implementation assignment — 2026-10-21

This historical checkpoint predates accepted factory activation. For the current primitive assignment and database ownership, see [current assignments](../ASSIGNMENTS.md) and the [accepted primitive entry](OPERATION_ADAPTER_ENTRY.md#bounded-primitive-checkpoint--accepted-entry-2026-10-21).

Engineer C retains P1 #94 ownership. B independently reviews cumulative work accounting, optional transaction work and raw receipts before dependent read/cancel services. B/lead accepted ownership entry 5bedede; C independently confirmed its acquisition map. A completed dormant helper d1b7ce20, accepted by B/C source review and 67 lead tests plus an original/corrected pool-substitution probe. C is assigned complete caller integration in the reused secondary checkout with Database factory activation disabled. C completed 40 actual PostgreSQL component cases at e490a27; the existing synthetic instance is stopped with baseline state restored. B/lead accepted the separate detach correction 97ef62c after source review and 18 independent regression passes. The helper, caller integration and factory activation remain separately reviewed checkpoints before dependent services. The initial failure table remains fail-closed: no stored-failure producer is invented. The entry audit found no additional producer prerequisite. Actual PostgreSQL, hosted/package checks, independent source review and accepted delivery are still required. P2 remains Not started; no HTTP/schema/profile/worker/provider/customer activation is included.

## Foundation CI checkpoint — 2026-10-21

2026-10-21 foundation CI and fixture correction: Draft PR #105 run 39596377455 at 97d39edf failed the same four optimized doctor-command fixture cases on both Python versions. Python 3.11 passed 3,326 with 14 skips in 978.18 seconds; Python 3.12 passed 3,337 with three skips in 1,050.02 seconds; each had one existing warning. All 40 operation-component, 33 publication and 26 recovery PostgreSQL cases executed on both versions. Package/security and three gVisor cases passed, but the CI gate failed and the main-only candidate delivery job correctly skipped. B's exact skip identities are source-derived (11 Python-3.12-only SQLite cases plus three Docker cases), consistent with the logged aggregate counts.

A corrected only test_cli_doctor.py at a92db83 after reproducing all four failures. Engine/Connection doubles now follow direct connect and close semantics while the real owned_connect remains exercised; all original artifact, runner and optimization assertions remain. The doctor/CLI/sentinel selection passed 37 cases with no skips, and static checks passed. B and the lead accepted the narrow source; no production guard changed. Full failed-run and correction evidence are privately indexed outside checkouts with owner-only permissions and a 2026-11-20 review date. C continues the separate primitive implementation and actual PostgreSQL proof; A next reviews that frozen checkpoint. Corrected matching hosted checks, complete service composition and accepted P1 delivery remain pending. P1 stays In progress, P2 Not started; estimates, dependencies and activation gates are unchanged.

## Bounded primitive component checkpoint — 2026-10-21

2026-10-21 bounded primitive component accepted: C froze 691ad661 with bounded complete-cohort discovery, a single typed final receipt query, the pure full-job decoder and immutable cancellation association. B independently accepted its SQL/security/native-type and cardinality boundaries. A verified the exact 366-path composition at 1985202 and passed 174 SQLite/component cases in 45.41 seconds, then all 15 original actual PostgreSQL cases in 41.63 seconds. A's test-only cbed928 adds three PostgreSQL controls that passed in 9.80 seconds: same-project reassignment invalidates the snapshot, foreign-project reassignment stays excluded, and actual write denial is followed by clean reads. The original tests and production source remain unchanged. The initial new-test NullPool cleanup-oracle diagnostic is preserved; it was not a production defect. PostgreSQL baseline was restored and the existing instance stopped.

Measured examples reached 255 roots/259 identities and 4,000 scoped/foreign distractors within unchanged limits (101,000/177,000 SQLite VM instructions; 22 final-query binds and 26 PostgreSQL attempts observed before cleanup, including setup/probe; the normal post-cleanup total of 28 is derived from source). These examples do not establish throughput for arbitrary unindexed tables. C built exact-source wheel/sdist; the lead independently matched all 111 runtime members in each archive, hashes, pinned manifests and actual isolated smoke/CLI evidence. Disposable build runtime cleanup recovered 126,238,720 filesystem bytes; both active cloud checkouts remain. Private source-bound evidence is indexed with owner-only permissions and a 2026-11-20 review date.

This accepts the strict GET receipt and association primitives, not OperationService or multi-phase cancellation. The next cancellation entry must share cumulative request work while releasing phase-local mutable evidence; worker progress between phases must not be compared with an earlier GET snapshot. A reviews that entry, B prepares the concrete phase API, C prepares GET composition, and the lead owns integrated CI/delivery. The first failed hosted run remains historical; the doctor correction is included in the composed source. P1 stays In progress and P2 Not started, with unchanged scope, effort, dependencies and external gates.

## GET evidence and cancellation correction — 2026-10-21

2026-10-21 GET source and package evidence accepted: B and the lead reviewed 28d47cc9. C passed 312 combined cases with 19 explicit PostgreSQL skips, then all 19 actual GET PostgreSQL cases with zero skips in 58.36 seconds. Completed OIDC/API-key requests measured 40/48 SQLite and 50/62 PostgreSQL attempts; these are bounded synthetic examples, not arbitrary-scale throughput. The lead verified the source-bound logs and restored/stopped database baseline. Exact wheel, sdist and installed-tree proof matched all 112 runtime members; isolated installed GET/result/refusal scenarios and a separate real migration-only guard passed. The disposable runtime was removed, recovering 126,410,752 filesystem bytes.

The earlier primitive source 5e1766d passed draft PR #105 CI 39601721324: 3,406/3,417 tests, expected 14/3 skips, all 117 targeted PostgreSQL cases on both Python versions, package/security, three gVisor cases and the CI gate. This is component CI; no protected-main or complete service acceptance follows.

Cancellation helper d8975224 remains blocked on one independently reproduced failure-latch defect. Its original 43 SQLite cases passed in the lead's run, but an additional schema-legal oversized-job-metadata test caught a read failure, repaired the metadata and successfully retried the same phase. A owns the narrow correction and its SQLite/PostgreSQL regressions; B reviews it and C checks unchanged GET behavior. The lead owns composition and the written cancellation-service handoff. P1 remains In progress, P2 Not started; task counts, estimates, dependencies, funding and activation gates are unchanged.


### 2026-10-21 — corrected phase ownership and service assignment

The caught-active-read blocker is closed at 9f73448d. B accepted exact source and indexed evidence, C accepted unchanged ordinary GET behavior, and the lead independently passed 55 SQLite cases in 36.06s including the unchanged original failing probe. The author’s final 134 SQLite and 40 actual PostgreSQL coverage is assembled from full runs plus 9/4 affected test-only reruns; the original 11/4 regressions and intermediate diagnostic failures remain preserved.

The lead composed exact GET 28d47cc9, corrected helper 9f73448d and accepted cancellation entry b65d38f7 at 950a4160. B verified 372 unchanged union paths, the exact guide append union and 113-member distribution allowlist. Independent lead GET execution passed 85 SQLite cases in 57.59s; C passed 19 actual PostgreSQL cases without skips in 61.07s. Completed GET traces remain 40/48 SQLite and 50/62 PostgreSQL attempts for OIDC/API-key callers. The exact synthetic database baseline was restored with zero other clients and the server stopped. Installed proof at 28d47cc9 remains distinct from this composition; a final 113-member service package and hosted delivery are still required.

A is assigned cancellation runtime/effect extraction and SQLite tests in the reused primary checkout. C is assigned independent actual PostgreSQL service tests in the reused secondary checkout and coordinates the sole existing database lifecycle. B independently reviews both deliveries; the lead owns composition, evidence and delivery. The [cancellation service entry](OPERATION_CANCEL_ENTRY.md) freezes three phases, original associations, the stable 85-root pre-effect refusal, malformed-ID authority ordering and phase-specific uncertainty mapping. No helper or GET support-table expansion is authorized. P1 remains In progress; P2 Not started. No task status, dependency, estimate, spending or production/data gate changes.

## Service composition and final delivery checkpoint — 2026-10-21

The same-Connection cancellation implementation at 1ce9469f has independent source review and 68 independently executed SQLite passes at 0f031962 (43.63 seconds). Its author selection passed 274 new/existing cases; six strengthened test observations were rerun separately. Completed cancellation traces are 88/106 SQLite and 119/146 PostgreSQL attempts for OIDC/API-key callers, within the unchanged 512-attempt/10-second SQL-active limits.

C's PostgreSQL evidence covers 65 distinct cases across runs: 62 initial passes, one corrected organization contention case and two physical QueuePool recovery cases. The first run's nonexistent-column fixture and a later tuple-initialization typo are preserved as test failures; neither required a runtime change. The two pool cases prove closed old physical connections, zero occupied slots, an idle replacement and a successful subsequent cancellation after confirmed rollback or acknowledged commit. The exact original database/role inventory was restored, with zero other clients and the socket-only server stopped.

Composition f9172462 preserves the exact 377-file union of reviewed runtime, independent PostgreSQL tests and installed smoke. The 71d33737 package proof passes isolated service GET/cancellation, a separate untouched real migration-only guard, CLI and all 113 Git/wheel/sdist/installed runtime member comparisons. The service marker follows the service scenarios and real-guard checks; separate package and CLI evidence records the remaining checks. Final source binding and matching hosted checks remain required; older component CI does not cover this composition.

The core CI job receives a bounded 30-minute scheduling window because the preceding Python 3.12 suite already took 1,106.67 seconds and this composition adds execution coverage. Product, native SQL, test wait and other job deadlines remain unchanged. A owns final installed proof, B reviews final source/CI inventory, C reviews integration evidence, and the lead owns delivery. P1 remains In progress; P2 Not started. No task status, dependency, estimate, spending or production/data gate changes.

## Accepted P1 delivery — 2026-10-21

P1 is **Verified** and [#94](https://github.com/spei04/agent-rewind/issues/94) is closed. [PR #105](https://github.com/spei04/agent-rewind/pull/105) merged reviewed source `1b0d1fe4b9555848c8c5445c9c857df477fd5cf9` as `03a8e074b51dca7c03d69295e0c18ca0f22dc1da` through the normal strict CI gate. Reviewed source and accepted merge share tree `680fef3a103292276d8a6a9a9a04dbdabe5ffbd5`; the first parent is `ec65cb7fa6af8489dd003f6d388784cfc4563ffb`. The PR tested merge `5f916c071fecaa70fb6640aafe60e66a507a09cd` has the expected base/source parents and the same tree.

| Evidence | Python 3.11 | Python 3.12 | Other required checks |
| --- | --- | --- | --- |
| [PR run 39616207090](https://github.com/spei04/agent-rewind/actions/runs/39616207090) | 3,716 passed, 14 expected skips | 3,727 passed, 3 expected skips | Actual PostgreSQL, 3 gVisor cases, package, security and CI gate passed |
| [Protected-main run 39620379652](https://github.com/spei04/agent-rewind/actions/runs/39620379652) | 3,716 passed, 14 expected skips | 3,727 passed, 3 expected skips | Actual PostgreSQL, 3 gVisor cases, package, security, CI gate and delivery passed |

Each core job collected 3,730 tests and reported one existing warning. B independently audited all required logs, flags, exact skip inventories and source identity; the lead verified the indexed evidence. The installed service marker appears once per package/delivery job; full-smoke and CLI results remain separate evidence. The 65 distinct cancellation/legacy PostgreSQL cases are assembled component evidence (62 initial passes, one corrected fixture and two QueuePool controls), separate from the complete hosted matrix and 68 independent SQLite cases. The 113-member local Git/wheel/sdist/installed proof is also separate from hosted archive verification.

The lead independently verified candidate **12355648523**, named `candidate-03a8e074b51dca7c03d69295e0c18ca0f22dc1da-1`: exactly four files, archive **640,524 bytes**, archive SHA-256 `a50b3abba6489541d01fc16edba45d8c6405483397c901d9e166737847c24e70`. Source, parent, tree, pinned manifests, package manifests, SHA256SUMS and API/archive digests agree. Wheel SHA-256 is `06e60d4d6fe16b9a971c8e44954fa162ace70dd157443e30efc6c50ba63d9eb6`; source archive SHA-256 is `80807d362d9eba7fc7b6d76427c952ca1b0f56e36993d05609581bbea0d75ba1`. The private indexed release record `reviewed-delivery-20261021-pr105-03a8e07.json` has SHA-256 `d97078681c5e3f2736679fd04a5fb80e39ba21b72aa308aa5e4cf2e3cf434f1b` and is retained outside disposable checkouts with owner-only permissions.

Failed run **39612054532** remains recorded. Its sole core failure on each Python version was the stale universal 20-minute workflow assertion. The narrow test correction permits 30 minutes only for core, keeps other jobs at 20 and preserves all security assertions; 50 relevant local tests passed before the successful final PR run. Runtime bounds remain unchanged.

Acceptance unlocks only **AR-008-B/P2 #95**, now In progress under the separate HTTP entry review. C owns entry/implementation, A independent tests and later the existing PostgreSQL lifecycle, B security/contract review, and the lead composition/progress/delivery. Aggregate #93 and parent #8 remain open. Totals remain 151 aggregate tasks (29 Verified, 1 In progress, 121 Not started), 158 planned PRs, 544 edges, 52 parents, 27 gates and 20 contracts. Package totals are 8 Verified, 1 In progress and 4 Not started. Estimates and external gates are unchanged; default adapters and customer-ready admission remain unavailable.

## P2 entry accepted — 2026-10-21

A/B/lead accepted [the concrete HTTP entry](OPERATION_HTTP_ENTRY.md) at 9f4f9a34 after the compatibility-description correction. C is assigned runtime and SQLite/ASGI tests; A owns independent actual PostgreSQL HTTP tests after a frozen-runtime handoff and B reviews source/security/contracts. This consumes the accepted P1 predecessor without changing estimates, dependencies or external gates. P2 remains In progress with no accepted merge or delivery evidence.

## P2 validation before hosted delivery — 2026-10-21

The exact three-route runtime is frozen at acd5ebc; C's final 24bf739 adds 80 passing HTTP/ASGI/helper cases and installed smoke. B's independent 41bfed8 contract tests exposed the missing explicit false GET CSRF metadata; the correction passed all five contract cases at composed 1fa397d. C independently accepted A's test-only d6be3ba and its single final 34-case actual PostgreSQL run (zero skips, one existing warning, 124.06 seconds). The lead composed exact bytes at 907946c. This is separate evidence, not a combined 119-case run.

Installed proof at be9f3dd used an isolated Python 3.12.3 runtime outside the checkouts. B independently verified all 114 Git/wheel/sdist/installed members, the exact distribution file sets, all 40 locked dependency identities, both smoke markers and CLI execution. Final composition changes only tests and documentation relative to this package proof. The lead separately passed 91 existing API, identity, contract and backlog cases, plus whole-runtime typing, lint/format/security rules and all three contract/planning validators. Failed fixture/oracle and command checkpoints remain private and clearly superseded.

The synthetic PostgreSQL baseline was restored exactly and the server stopped; the temporary installed runtime was removed after all consumers released it. Two cloud checkouts are reused. P2 and aggregate #93 remain In progress. Matching PR checks, protected-main checks and verified candidate delivery remain required; accepted-merge/review ledger fields stay null. The next ledger implementation, worker/customer readiness, full M1 integration and external production/data/funding gates remain open.


## Hosted failure and test-isolation correction — 2026-10-21

PR #106 run [39631674974](https://github.com/spei04/agent-rewind/actions/runs/39631674974), attempt 1 at a304d52, is not accepted. Python 3.11 reported 3 failed, 3,832 passed and 14 expected skips; Python 3.12 passed 3,846 with 3 expected skips. Each reported one existing warning. Package, security and the separate three-case gVisor check passed; the CI gate failed and delivery was skipped. The immutable private failed-run index SHA-256 is a1eb76406442ce7d5b1a98e2896d9e5f04a4ee96a7a70027aed96ad9072d2570.

The three existing failing checks cover a named-project run detail, the PostgreSQL read-only compatibility guard and a maximum-size listing. The listing recorded 2.749 seconds against its unchanged two-second budget. The fixed errors from the other two checks do not expose their exact cause. Local guarded diagnostics passed once on Python 3.12.3 and 3.11.15; the pinned installer did not supply hosted 3.11.17. These are supporting diagnostics, not an exact hosted reproduction or proof that scheduling caused the failures.

C separately demonstrated that three process-global classifier LRUs in pinned FastAPI 0.142.2 retain completed endpoint closures and applications. Nine closed applications and disposed zero-checkout engines survived full garbage collection; clearing those three caches and collecting released all nine. Reviewed correction a992425 adds only a test helper, module teardown in the three new HTTP modules and three behavioral regressions. It preserves within-test caching, runtime code, deadlines and all prior test bodies. The helper uses global classifier-cache clearing at completed module boundaries; it does not provide per-application eviction.

The weak-reference regression failed before the cleanup and passed afterward. The exact 94-case selection passed on Python 3.11.15 in 66.05 seconds and Python 3.12.3 in 62.53 seconds, with zero skips and one existing warning each. It includes 80 HTTP, five independent contract, three new cleanup, two formerly failing SQLite and four deliberate work-exhaustion/cleanup controls. Ruff, formatting, diff and AST-preservation checks passed. PostgreSQL was not rerun locally for its single fixture import; the corrected hosted matrix must execute it. The private correction index SHA-256 is 04bd29a6dca7aa08ba678c6d025c8fb3e93358970bbdd74fa3176d635ad74948; the preceding diagnostic index is e62e617679d8fb95d5060faafc55d1eaf362cd8d0c7c08aa766ac7314b37ec02.

This fixes demonstrated fixture retention without establishing the original hosted failures' causes or eliminating all timing sensitivity. The private candidate verifier now binds explicit PR/main attempt numbers, exact complete job sets and the retained failed attempt, with independent positive/negative review. A corrected-source matrix, protected-main checks and verified candidate remain required before P2 or aggregate acceptance. No unchanged-source retry was dispatched.
