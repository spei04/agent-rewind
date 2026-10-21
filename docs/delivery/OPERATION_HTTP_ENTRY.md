# Operation HTTP implementation entry

2026-10-21 · AR-008-B/P2 [#95](https://github.com/spei04/agent-rewind/issues/95).
Engineer C owns the HTTP implementation and SQLite/transport tests in the reused
secondary checkout; A independently owns actual PostgreSQL HTTP tests in primary,
B reviews security/contracts, and the lead owns composition and delivery.
This checkpoint authorizes no runtime changes before independent entry review.

P1 is accepted: reviewed source `1b0d1fe4b9555848c8c5445c9c857df477fd5cf9`,
merge `03a8e074b51dca7c03d69295e0c18ca0f22dc1da`, PR/main runs
39616207090/39620379652, and verified candidate 12355648523. The lead's private
record is `reviewed-delivery-20261021-pr105-03a8e07.json`. This entry consumes
that source, [C04](M1_CONTRACT_FREEZE.md#errors-limits-and-consumer-compatibility),
the frozen [OpenAPI](../../contracts/proposals/m1.openapi.json), and the
[HTTP execution plan](OPERATION_HTTP_EXECUTION_PLAN.md). It changes no contract,
estimate, dependency, schema/profile or worker/failure producer. The existing
2 [2–3] BE-day P2 scope remains; no additional implementation prerequisite is found.

## Files and public seams

A focused `agent_rewind/operation_http.py` will own
`register_operation_routes(app: FastAPI, *, auth: Auth, authority: RequestAuthority) -> None`,
three handlers, finite transport helpers and response/OpenAPI metadata.
`api.create_app` constructs and registers per-app dependencies without SQL,
storage reads, readiness calls or publication at construction:

- `app.state.operation_coordinator = AdmissionCoordinator(db.engine, authority)`.
  Keep its unavailable policy and absent registry/readiness/journal/storage defaults.
  Do not derive grants/configuration from Settings, fabricate a policy adapter,
  bridge async readiness, or connect the legacy `app.state.admission`.
- `app.state.operation_service = OperationService(db.engine, authority, artifact_loader=...)`.
  For local storage, use a separate `LocalArtifactStorage(settings.data_dir,
  auth.cipher, plaintext_limit=4096).read_verified` bound method. For unsupported
  storage leave the loader absent: no remote client, ambient credentials or local
  fallback. The service alone selects/authorizes the descriptor and performs its
  one verified load outside SQL; HTTP does not read result artifacts.

Handlers read these per-app state objects at invocation, permitting isolated
test replacements without global readiness/profile flags. Existing constructor,
legacy admission, list/detail and Auth behavior remain intact. Services retain
their own real schema guards, fresh checks and outcome classification.

| Method/path below /api/v1/projects/{project_id} | operationId | Service call | Result |
| --- | --- | --- | --- |
| POST /runs | submitProjectRun | coordinator.submit(principal, context, intent, key_hash, origin) | 202, exactly operation_id/job_id |
| GET /operations/{operation_id} | getProjectOperation | service.read_operation(principal, context, operation_id) | 200, exact ten-field Operation |
| POST /operations/{operation_id}/cancel | cancelProjectOperation | service.cancel_operation(principal, context, operation_id) | 202, exactly operation_id/cancel_requested/status |

All synchronous authority, parsing and service work runs through the existing
threadpool pattern; no SQL/native blocking work runs directly on the ASGI loop.
No new reconcile route or application retry loop is introduced. Response DTOs
must retain required nulls, false values, strict integer accounting and
`cancel_requested:true`; no exclude-none/default/unset serialization.

## Ordering and raw transport

Preserve the current middleware order: outer SafeBoundary generates correlation;
security performs its bounded real compatibility probe; BodyLimit buffers at
most the accepted received-body threshold before routing; route authentication
and application validation follow. A non-ready real schema refuses before route
authentication/customer sinks. Existing security maps status incompatible to
schema_incompatible; migration_only is one such incompatibility reason. An
unavailable probe maps to dependency_unavailable. Do not change this into a synthetic ready default.
BodyLimit's 413 may precede authentication; authority-first below concerns
application diagnostics, not expansion or unbounded unauthenticated buffering.

1. Authenticate with actual `Auth.principal(request)`; store the returned verified
   principal in request state. Preserve explicit-invalid bearer rejection without
   cookie fallback, live key expiry/revocation and cookie CSRF/exact Origin checks
   on both POSTs. These cookie checks precede project lookup as they do today.
   In these three routes, duplicate Authorization is ambiguous identity and gives
   fixed 401 before selection. After successful cookie authentication on a POST,
   duplicate X-Rewind-CSRF or Origin gives fixed 403, before project lookup.
   Do not alter legacy Auth or cookie parsing globally.
2. Submit resolves `authority.named(principal.verified, project_id, "record")`
   before key/media/JSON diagnostics. GET/cancel resolve the same named project
   with `"read"`. Never consult the legacy default. Plain string path arguments
   carry metadata-only patterns; no eager FastAPI Path/Body/Header validation.
   RequestAuthority retains malformed/inaccessible project 404. OperationService
   retains malformed/missing operation 404 and target visibility before cancel
   action 403; do not precheck project `cancel`, call GET to authorize cancel,
   or add an unbudgeted resource lookup.
3. After named authority, inspect raw `request.scope["headers"]` pairs, not a
   collapsed mapping. All three routes accept absent Content-Encoding or exactly
   one case-insensitive `identity` token. Repeated values, lists, unsupported
   codings or malformed tokens give fixed 422 before service effects; never
   decompress. Project visibility therefore precedes these encoding diagnostics,
   while service target visibility occurs afterward. A visible project with an
   unknown operation and bad encoding gets 422; with valid transport it gets 404.
4. GET/cancel have no declared query/body input. Ignore those already bounded
   bytes and query pairs as non-input; do not parse JSON or infer options from
   them. They cannot replace IDs, change cancellation/status or authorize work.
   Content-Type is not interpreted for these unused bodies; encoding and global
   BodyLimit still apply. No new empty-body or unknown-query rejection is added.
5. Submit rejects undeclared query pairs after record authority. It requires
   exactly one Content-Type identifying application/json,
   case-insensitively, with either no parameter or one charset=utf-8 parameter
   (case-insensitive value, optional standard quoted value/OWS). Reject duplicate
   Content-Type, other parameters/charsets, malformed media syntax and missing or
   other media types as fixed 422 after record authority. Accept no other JSON
   media type. Read raw bounded bytes, never `request.json()` or model coercion.
6. Require exactly one raw Idempotency-Key, 8–128 ASCII bytes matching
   `[A-Za-z0-9._:-]+` by full match. Do not trim, fold case, split lists, join
   duplicates or decode a non-ASCII value permissively. Pass SHA-256 hex of the
   exact accepted bytes. A different spelling/case remains a different key.
7. Delegate the original bytes to `admission_request.parse_submit`. Preserve
   strict UTF-8, duplicate members at every level, exact fields, integer grammar,
   finite/path/file/redaction validation and canonical default materialization.
   Received SubmitRun bytes are bounded by 9 MiB; the independent 8 MiB limit
   applies to canonical materialized TaskSpec, not source character count or the
   wrapper. Do not reserialize before parsing or substitute a current registry.
8. Construct `OriginCorrelation(request.scope["state"]["request_id"])` only from
   SafeBoundary's generated state. Neither X-Request-ID nor body data supplies
   origin. Call coordinator.submit directly. Its SQL winner/recovery path runs
   before current policy, registry, readiness, journal and storage; HTTP adds no
   require-available/readiness preflight. A new unavailable request refuses before
   downstream work; existing replay retains original IDs/config/origin and fresh
   authority. Unknown outcome uses the same submit identities without fallback,
   automatic retry, another principal, new upload or job.

The no-body/query and encoding precedence choices above are deliberate bounded
entry decisions. Raw ASGI tests must cover them; client dictionaries alone lose
the duplicate-header evidence.

## Finite errors and generated metadata

Reuse SafeBoundary/Fault and existing safe messages, generated 32-hex
X-Request-ID and Cache-Control:no-store. Preserve the 401 Bearer challenge and
actual 429 Retry-After (existing value 5, within frozen 1–60). Never serialize
exception text, raw headers, paths, file keys, submitted values or traceback.

- Only `AdmissionPreparationError("admission_invalid_input")` maps to 422.
  Its `admission_body_limit` maps to fixed 413 received-body 9 MiB;
  `admission_task_limit` maps to fixed 413 canonical-materialized-task 8 MiB.
  Configuration/binding/internal preparation failures are not malformed HTTP
  input; they remain coordinator responsibility or safe internal errors if
  unexpectedly exposed at this route parser boundary.
- Translate only finite `AdmissionError.code` values from coordinator.submit:
  invalid_request 422, idempotency_conflict 409, dependency_unavailable 503,
  schema_incompatible 503, outcome_uncertain 503/retryable=false. Typed identity,
  visibility and action denials retain existing 401/404/403 handling.
- OperationService already emits Fault/typed authority errors. Preserve them,
  including post-ACK uncertainty and fresh-authority denial. No blanket exception
  conversion, raw IntegrityError-to-conflict, ValueError-to-422 or new retry.
  Unexpected non-SQL programming faults retain the sanitized 500 boundary.
  Uncaught SQLAlchemy errors retain SafeBoundary's existing GET dependency / POST
  uncertainty classification; do not relabel them as conflicts or malformed input.
- Add a narrow finite `task_limit=False` keyword to `errors.error_response`
  for the parser's semantic 413 (fixed message: "Canonical materialized task
  exceeds 8 MiB."). Existing default and `body_limit=True` calls stay unchanged;
  only the semantic-limit branch passes task_limit. The two limit modes are
  exclusive at call sites and retain exactly the four Error fields.

Declare Accepted, Operation, Cancellation and Error-compatible metadata for only
these routes. Document SubmitRun/TaskDefinition as schema metadata, never eager
body validation. A scoped OpenAPI registration helper may add their required
component schemas and requestBody metadata without reading packaged contract
files at runtime or replacing existing paths/components. Compare resolved schema
structure, required fields, additionalProperties, nullable alternatives, integer
bounds, path/header parameters, role/CSRF extensions, operation IDs and complete
response status/header sets against the frozen three operations. Apply the frozen
serviceKey-or-sessionCookie security alternatives explicitly to these operations,
adding only required named security schemes; do not set a new global security
requirement that rewrites legacy/list/detail metadata. Submit alone
declares 409; all three retain declared 413/429/500/503. Do not accidentally
publish FastAPI HTTPValidationError bodies or add response codes/endpoints.
Any metadata normalization must leave accepted list/detail and legacy nodes
unchanged.

Initial GET support remains exactly accepted P1: queued/running/succeeded/cancelled
with SQL NULL error may render; failed+NULL or any non-NULL legacy error returns
503. Null result stays null; non-null result requires the service's bounded
original descriptor/ref/run proof. Cancellation still supports all five states,
preserves accounting/result/error and returns its acknowledged snapshot. Do not
fabricate a stored Error producer or use poll correlation as historical origin.

## Independent test and package checkpoints

C owns `tests/test_operation_http.py`, the new route module, minimal api/error
integration, its one distribution entry, and a narrow installed-smoke addition.
A owns `tests/test_operation_http_postgres.py` after an immutable runtime handoff,
using the one existing synthetic PostgreSQL instance under explicit lifecycle
ownership. Reuse existing ar6 preparation and accepted service/publication
helpers by import; no duplicate shared fixture contracts or mutable cross-checkout
source consumption. Root owns shared progress files.

1. Actual cookies and scoped API keys, two populated projects, absent/other legacy
   defaults, same-project noncreator viewer GET, viewer cancel403, foreign/missing
   target404, revoked/expired identities and current membership/key ceilings.
   Exercise valid/invalid/duplicate authentication, CSRF/Origin and transport
   precedence, with raw ASGI pairs and a separate real migration-only app whose
   route/auth/readiness/storage/coordinator/effect spies remain untouched.
2. Missing/duplicate/boundary/non-ASCII/list-like Idempotency-Key; duplicate JSON
   at nested levels, UTF-8 versus UTF-16/32, invalid numeric/path/source fields,
   raw source whitespace conflict versus parsed-default equivalence. Accepted
   8 MiB TaskSpec, one-byte semantic overflow, exact 9 MiB received boundary and
   chunked overflow with misleading/absent Content-Length; no decompression.
   Error bodies/headers remain exact and private canaries never escape.
3. Real coordinator plus explicitly synthetic per-app policy/config/readiness/
   storage/journal for new-work success. SQL replay with each current dependency
   poisoned, atomic alias binding, changed-body conflicts, first-origin retention
   with fresh HTTP correlation, eight concurrent original-identity requests,
   lost commit ACK/restart/pending SQL-only reconciliation, no duplicate job/ref/
   operation/alias/audit and no HTTP retry. Instance readiness substitutions are
   limited to the exact app db/coordinator/service, never global profile changes.
4. Real GET and cancellation service HTTP effects: nullable result and verified
   encrypted result load outside SQL, unsupported legacy failure503 without
   exposure, source/ref drift and final revocation; queued/running/terminal and
   repeated cancellation, original-association replacement and current
   membership/key/worker lock races. Preserve rollback versus ambiguous/ACK
   outcomes, fresh disclosure, exact effect/audit counts and no provider action.
   Pure malformed/limit cases stay in C's transport suite; A focuses independent
   actual database/race proof rather than duplicating primitive-only cases.
5. Independently compare all three generated OpenAPI operations and preserve
   existing list/detail/legacy metadata, existing auth/route/service regressions
   and safe-error tests. Installed wheel/sdist smoke must use installed imports
   outside source, exercise these three HTTP paths via real services in an
   isolated synthetic app, and retain an untouched second app proving real
   migration-only refusal. Assert absent default new-work adapters before sinks,
   complete artifact/installed member parity and no cross-app override leakage.

Freeze reviewed runtime before A executes against its exact immutable signatures.
No actual PG or installed-package evidence follows from this entry or local
collection/skips. Matching hosted checks, independent review, accepted merge and
protected-main candidate are required before aggregate completion. No list/detail,
worker/ledger, schema/index/profile, customer/provider or paid-resource activation
is included.
