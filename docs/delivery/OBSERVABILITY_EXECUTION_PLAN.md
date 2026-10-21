# AR-011-C execution boundary

Status: planning reconciliation, 2026-10-21. Implementation is Not started.
The [aggregate and package cards](../EXECUTION_BACKLOG.md#ar-011-c) retain the
approved C04 obligations and one aggregate identity. The estimate replaces
2 [2–3] PL days with 4 [4–6], medium-low confidence, across two independently
reviewable PRs. This is engineering effort, not a calendar or additional funding.

Both packages wait for **AR-011-B, AR-005-C and AR-010-B to be Verified**.
P1 inherits every aggregate prerequisite, and P2 additionally requires accepted
merged P1. The generic validator remains unchanged: an independently useful
HTTP foundation is not an exception permitting early implementation. AR-010-B
transitively waits for AR-008-A/B, whose accepted producers persist the durable
origin; AR-012-B is a downstream acceptance consumer, not a reverse dependency.
Neither package nor the aggregate is currently ready or assigned.

| Package | Effort | Acceptance boundary |
| --- | --- | --- |
| P1 | 2 [2–3] PL days | Trusted correlation helpers, exact five-metric collector, actual HTTP/readiness observations and bounded local diagnostic/drop state; freeze observation and resource semantics at the first design checkpoint. |
| P2 | 2 [2–3] PL days | Consume accepted admission origin persistence and worker/ledger fences for actual queue, provider and recovery evidence; close the full correlation/redaction/boundedness matrix. |

The exact vocabulary remains the [frozen observability contract](../../contracts/proposals/observability.contract.json)
and [C04 telemetry specification](ERROR_READINESS_TELEMETRY.md):

| Metric | Existing labels |
| --- | --- |
| http_requests_total | route, method, status_class |
| http_errors_total | route, error_code |
| queue_delay_seconds | job_kind, queue_outcome |
| dependency_ready | component, process_role |
| provider_calls_total | call_purpose, call_outcome |

All values and per-metric label-combination limits remain exactly frozen.
Provider call_outcome is **observed / uncertain / rejected**, not a new
success/failure vocabulary. HTTP observations count attempts, including replays,
rather than committed jobs. budget_exhausted is emitted only when the actual
HTTP boundary classifies that existing error; no budget amount, admission-success
metric or inferred provider charge is introduced.

At the first concrete design checkpoint, freeze the event observation boundaries,
readiness cache and unknown-state semantics, histogram bucket lists, buffer
limits and installation-level series limits. The existing per-metric combination
limits are not a complete installation bound. Choose no arbitrary new numeric
limits in this planning amendment. Fresh, cached and unknown readiness evidence
must have honest semantics without adding labels. Ordinary zero-initialized
counters are allowed; they do not demonstrate a worker or queue integration.

The server-generated request/poll ID is distinct from the write-once trusted
operation/job origin. Consume AR-008-A/B's persisted origin without overwriting
it on replay, deriving it from client headers/body/configuration or reusing
legacy jobs.error. Historical missing origins use only the producer's explicit
migration-marker contract, never a fabricated original request. AR-011-C does
not own admission or ledger schema changes.

Diagnostics use allowlisted restricted fields and bounded local drop state.
Drops must remain observable locally, including sink/buffer failure, without a
new exported drop metric, label vocabulary, network exporter or backend rollout.
Telemetry remains best effort: it cannot acknowledge missing mandatory audit or
ledger receipts, trigger retries/refunds or block ordinary responses indefinitely.
Required audit and ledger persistence keep their owning fail-closed semantics.

Tests must exercise actual accepted HTTP/readiness and synthetic worker/provider
paths, including origin continuity across retries/polls, observed/uncertain/
rejected transitions, recovery, unknown/cached readiness, saturation and local
drops, and failure of both optional diagnostics and mandatory audit/ledger.
Secret canaries, finite label/cardinality checks and bounded work are required.
Mock collector calls or zero worker counters alone cannot close P2 or the
aggregate. No live provider, paid execution, SLO claim, paging rota, production
activation or external gate is authorized by this plan.

The separate admission reconciliation remains auditable at 1d284ba. At the
historical 9a70fdc producer/estimate checkpoint, computed totals were 151 aggregate tasks,
155 planned delivery PRs, 544 acyclic edges, 454 base days, 768.1 summed upper
days and a 168.5-day effort-only path. The alternate 25% allowance is 567.5 days;
these uncertainty views are not additive. M1 is 55.5 days and PL 90 days.
Historical schedules, C21/owner decisions and frozen contract bytes remain intact.

Later reconciliations are recorded in the current [roadmap](../PLAN.md) and
[machine ledger](../../contracts/proposals/execution-backlog.json); the figures
above retain that observability checkpoint rather than override current totals.
