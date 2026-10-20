# Error, readiness and telemetry contract

AR-011-A · C04 · Proposed for AR-004-B reconciliation and G0 freeze. This is a
consumer design and synthetic test contract. It changes no runtime handler,
health endpoint, instrumentation or central M1 proposal. Current behavior is
recorded in [BASELINE_INTERFACES.md](BASELINE_INTERFACES.md), especially IF-08.
The [structured contract](../../contracts/proposals/observability.contract.json)
contains fixed public messages, response examples and bounded metric values.

## Stable response and correlation contract

Versioned API errors use exactly `code`, `message`, `request_id` and `retryable`.
Codes are stable machine values; messages are selected from approved templates
and are at most 300 characters. Never interpolate exception text, source paths,
request bodies, validation input values, SQL, provider responses or tokens.
Unexpected exceptions map to a fixed message plus a restricted correlated
error event. A generic ValueError is not automatically a client error: only a
known validated domain condition maps to invalid_request; programming/integrity
failures map to internal_error or a classified dependency failure.

Generate a fresh cryptographically random 128-bit lowercase hexadecimal request
ID at the trusted API boundary, before body-limit/auth/validation handlers. Return
it as `X-Request-ID` on successes and errors, and in each error body. Do not echo
an untrusted caller's request-ID header. A proxy may supply a distinct trusted
trace parent only under explicitly configured trust; it does not replace the
server request ID. Repeated requests have distinct request IDs but preserve the
same logical operation and client-operation identity when using idempotency.

Use `Cache-Control: no-store` on API/error/health responses. Responses emitted
upstream by a proxy before reaching the app may lack this envelope; deployment
checks must identify that boundary rather than asserting application guarantees
for arbitrary gateway failures. Authentication responses retain safe required
headers; cookie mutations use `X-Rewind-CSRF` and Origin checks. This preserves
the existing browser header; central proposal revision m1-review-2 now carries this header; runtime enforcement remains planned.

| Condition | HTTP/code | Client meaning |
| --- | --- | --- |
| Malformed JSON, invalid field/path/adapter | 422 / invalid_request | Correct the request; no raw value is echoed. |
| Body over 9 MiB, or canonical task manifest over 8 MiB | 413 / invalid_request | Distinct fixed size messages; transport and semantic limits are separate. |
| Missing/invalid credentials | 401 / unauthenticated | Authenticate; do not reveal token lookup details. |
| Forbidden action on an already accessible project | 403 / forbidden | Change permissions or action; no automatic retry. |
| Missing or inaccessible resource/project | 404 / not_found | Identical safe response prevents an existence oracle. |
| Foreign, tampered, expired or invalid cursor | 422 / invalid_cursor | Restart authorized pagination; reveal no cursor contents. |
| Identity reused with changed canonical request | 409 / idempotency_conflict | Preserve original identity or explicitly start different work. |
| Exhausted permitted budget | 409 / budget_exhausted | No automatic retry or cap reset. |
| Temporary admission quota | 429 / quota_exceeded | Bounded Retry-After seconds; admission was not performed. |
| Required authority unavailable before admission | 503 / dependency_unavailable | Transient failure, known not admitted; retry under the operation's safe retry rules. |
| Incompatible schema | 503 / schema_incompatible | Operator intervention required; runtime must not migrate automatically. |
| Unexpected internal fault | 500 / internal_error | Use request ID for diagnostics; no blind retry. |
| Admission commit or dispatched provider outcome ambiguous | 503 / outcome_uncertain | Reconcile the same logical operation/call; do not assume failure, refund, or dispatch new work. |

`retryable=true` is limited here to known pre-admission transient dependency/quota
failures. It means a condition may resolve, not that any POST can be repeated
safely. Reads may retry with bounded backoff; versioned mutations must retain
project, canonical body, client-operation ID and idempotency key. Legacy POSTs
have no automatic retry contract. Generic 500 and uncertain outcomes use false.
A 429 response must contain an integer Retry-After from 1–60 seconds. Clients
must also respect their own retry deadline and attempt limit.

Authorization precedes loading scoped resource data. Missing and inaccessible
resources share code/message/status and response shape; timing side channels
need implementation review. A malformed identifier can be rejected structurally
without revealing whether any resource exists. Request validation locations must
be schema-defined field names if exposed in future; dynamic file keys can contain
customer information and are not public error details in this envelope.

## Unknown outcomes are not ordinary failures

A lost database commit acknowledgment can leave admission uncertain even when
no operation ID reached the caller. Do not claim no job exists. After authority
recovers, resolve the original client-operation/key identity or repeat only the
same canonical idempotent admission request under the frozen admission contract.
Never mint a new identity merely because the response was lost. The current M1
proposal has no lookup by client-operation ID, so that recovery must use the
same POST identity until a lookup API is separately approved.

A provider timeout after dispatch is a different uncertainty: the provider may
have executed and charged. Preserve its logical call ID, reservation and unknown
outcome for reconciliation; never automatically release the hold or create a
replacement paid call. A local job can terminate as failed while the provider
outcome remains unknown. Reading that job/operation is a successful HTTP read,
not an HTTP 503 merely because its stored error is outcome_uncertain. Preserve
that distinction in future Operation/receipt schemas; do not add a new operation
status implicitly in this task.

A completed run whose evaluator reports success=false is an ordinary task
failure, not an API error or infrastructure incident. Cancellation remains intent
until execution stops; a 202 cancellation response with status=running is valid.
Missing evidence must never be converted to evaluator failure or a supported
improvement claim. These distinctions apply in UI and SDK consumers.

## Liveness, readiness and safe admission

Introduce `GET /livez` for process responsiveness and `GET /readyz` for admission
readiness. A responsive process returns 200 `{status:live}` regardless of DB or
artifact outage. Readiness returns 200 `{status:ready}` only when all required
checks are fresh and pass; otherwise 503 with the safe Error envelope. An
unsupported schema uses schema_incompatible; unavailable, timed-out, unknown or
draining readiness uses dependency_unavailable. Public probes expose no host,
bucket, schema revision, exception, credential status or per-project data.

The existing `/healthz` performs a DB check. Retain that compatibility behavior
until deployment manifests and operators explicitly switch probes; do not call
it pure liveness or silently change restart behavior. New manifests use /livez
for restart decisions and /readyz for admission routing. Startup/readiness must
not execute DDL or repair schemas.

| Required readiness check | Bounded evidence and failure action |
| --- | --- |
| Database | Connect through the configured pool and perform a read-only lightweight check; unavailable/timeout fails readiness. |
| Schema | Read the declared revision and required compatibility state; unknown or unsupported revision fails closed. |
| Artifacts | Read, decrypt and verify a deployment-owned synthetic sentinel of at most 4 KiB; missing, corrupt or slow sentinel fails readiness. No customer blob is probed. |
| Encryption | Validate configured decrypt capability using the same synthetic sentinel and startup key checks; never return key IDs or values publicly. |

Provision the synthetic sentinel during explicit installation/doctor validation,
with system ownership and no customer project attribution. Do not create a new
object per probe, enumerate customer storage, or run destructive writes. This
readiness signal does not prove current object-write permissions; installation
and ongoing operational checks must verify writes separately. Every actual
request still validates authorization, schema compatibility, storage publication
and budget in its own operation. A cached ready flag grants no permission and
cannot replace transaction invariants.

Use a one-second total probe deadline, one in-flight dependency check per process
and a positive cache no older than five seconds. Expired/unknown checks fail
closed; no background refresh may keep stale success indefinitely. During drain,
readiness fails immediately while liveness stays healthy. The deadline/cache
values are proposed operational defaults to verify in deployment tests, not SLO
measurements or proof that a storage client obeys cancellation.

Do not call a model, start a sandbox, pull an image or dispatch a job during a
probe. Provider health, worker capacity and IdP availability have separate
operational indicators. Queue admission remains bounded by the admission/queue
contract. A remote IdP outage need not disable authenticated API-key traffic or
valid cached-key verification; the relevant authentication path still fails
closed when its required authority cannot be verified.

## Safe diagnostics and bounded telemetry

Build diagnostics from allowlisted structured fields before any sink: stable
event/code, severity, route category, dependency category, generated request ID,
operation/job ID when authorized, trace ID and bounded numeric duration. Generated
IDs belong in restricted logs or traces, never metric labels. Do not emit raw
URLs, query strings, request headers, body/source, cookies, authorization tokens,
OIDC claims, principal/customer/project IDs, prompts, tool output, provider error
bodies or arbitrary exception messages. Do not hash secret/customer values into
labels; hashing still creates cardinality and correlation risks.

Record a fixed error event and a safe exception category; unknown classes map to
an unclassified category. Do not enable automatic exception capture that exports
locals, SQL parameters, arbitrary filenames or stack traces. Unknown fields are
dropped/rejected before logging rather than passed to a string redactor. Secret
canary tests must cover responses, middleware/access logs, tracing exporters and
metrics at implementation time, including nested exceptions and validation paths.
The synthetic contract checks are not evidence that these runtime sinks are safe.

The structured contract declares exact label sets and finite values per metric.
Raw route paths map to fixed operation categories; unknown routes map to
`unmatched`, and unknown HTTP methods to `OTHER`. No resource ID enters a value.

| Metric | Label dimensions | Maximum combinations per target |
| --- | --- | --- |
| http_requests_total | route, method, status_class | 250 |
| http_errors_total | route, error_code | 120 |
| queue_delay_seconds | job_kind, queue_outcome | 8 |
| dependency_ready | component, process_role | 8 |
| provider_calls_total | call_purpose, call_outcome | 6 |

These are per-metric label-combination bounds, not total backend series limits.
Histogram buckets, count/sum, scrape targets and deployment resource attributes
multiply exported series. Freeze bucket lists and an installation-level series
budget in AR-011-C before rollout. Service/version/region attributes must come
from reviewed deployment configuration, never incoming traffic; each rollout's
new version still consumes series retention. Do not enable automatic unbounded
OpenTelemetry HTTP/provider attributes by default.

Telemetry failure must not create paid retries or block ordinary business
responses indefinitely. Use bounded buffers and explicit drop counters for
best-effort diagnostics. Required transactional audit records and budget receipts
are not best-effort telemetry; their persistence failure follows the owning
admission/security contract and can require failing closed.

## Reconciliation disposition

Revision m1-review-2 in [M1_CONTRACT_FREEZE.md](M1_CONTRACT_FREEZE.md) resolves
these central proposal differences. Review is accepted in [G0_DECISION.md](G0_DECISION.md); runtime remains
unchanged; the list records the agreed implementation contract, not open JSON
drift. AR-005-C is now required before AR-011-B; the system-sentinel bounded read
belongs to AR-011-B and is reused by AR-009-A customer storage work.

1. AR-004-B adds outcome_uncertain to the central Error enum and specifies safe
   HTTP/stored-operation use, receipt linkage and identity-preserving recovery.
   The existing enum cannot represent the required ambiguity distinctly.
2. Add 500 responses and X-Request-ID/no-store headers to versioned operation
   responses, plus exact 413/422 mapping and bounded 429 Retry-After. Ensure
   known pre-admission versus uncertain-after-dispatch failures are explicit.
3. Freeze X-Rewind-CSRF across existing and proposed cookie mutation contracts;
   do not implement a conflicting X-CSRF-Token header accidentally.
4. Retain `/healthz` compatibility while defining /livez and /readyz deployment
   transitions, system sentinel ownership and explicit probe deadlines. Require
   a bounded sentinel read in AR-011-B, reused by the AR-009 storage interface; the existing full-blob
   get must not be called bounded merely because the expected object is small.
5. Define versioned versus legacy error migration. Recommendation: v1 uses the
   four-field envelope; legacy keeps a safe `detail` shape plus request-ID header
   until workbench/SDK compatibility tests approve migration. Never preserve
   unsafe exception interpolation for compatibility.
6. AR-011-B implements handlers/readiness and CT-M1-022/023 runtime fault tests;
   AR-011-C implements correlation and checks exporter cardinality. This task's
   fixtures cannot satisfy those runtime gates or security review on their own.
