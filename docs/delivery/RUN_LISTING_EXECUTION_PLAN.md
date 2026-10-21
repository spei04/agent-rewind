# Scoped run listing and detail execution plan

This is the AR-006-B implementation boundary for independent review, not runtime
acceptance or a customer-ready release. The [task cards](../EXECUTION_BACKLOG.md#ar-006-b)
and [machine ledger](../../contracts/proposals/execution-backlog.json) retain the
aggregate identity and existing prerequisites: Verified AR-006-A, AR-007-C and
AR-011-B, consuming reviewed C04. Both delivery packages remain **Not started**;
a planning assignment does not start their runtime work.

A authored exact plan `9b97a09`; B independently accepted its contract, dependency
and arithmetic review, and the lead accepted the plan. Tracking: aggregate
[#86](https://github.com/spei04/agent-rewind/issues/86), P1
[#87](https://github.com/spei04/agent-rewind/issues/87), P2
[#88](https://github.com/spei04/agent-rewind/issues/88). Runtime remains unassigned;
planning acceptance does not satisfy either delivery package.

C04, the frozen OpenAPI/logical schema and CT-M1-005/006 remain authoritative.
This plan elaborates their implementation without changing their bytes. Read/cursor
authority also contributes to CT-M1-007/008; it cannot close their later replay or
whole-M1 acceptance obligations. No reverse dependency on AR-008 or AR-010 is
needed for these conservative SQL-only reads. AR-006-C still owns persistent
fenced repair and restricted audit after AR-010-B; AR-012-B verifies integration.

## Two independently reviewable deliveries

| Package | Boundary | Effort | Exit before successor |
| --- | --- | --- | --- |
| AR-006-B/P1 | Dedicated cursor configuration/codec and bounded scoped projection reader; finite suppression, original receipts and native query-work cleanup; no HTTP wiring | TL 2 days, range 2–3 | Independent interface/security review, actual SQLite/PostgreSQL evidence, matching hosted checks and accepted merge |
| AR-006-B/P2 | Exactly the two frozen v1 GET list/detail routes, named-project authority, response/error contracts, route and package integration | TL 2 days, range 2–3 | Full route/read/cursor matrix and accepted delivery evidence; aggregate acceptance remains separate from G1/customer readiness |

The aggregate is **4 TL days, range 4–6, medium-low confidence**. This replaces the
old 2 [2–3] estimate; it is not extra effort added on top of that estimate. P1
inherits all aggregate prerequisites and C04; P2 additionally requires accepted
merged P1. Neither package can use mock producer availability to bypass its inputs.
Review the key, suppression table, receipt comparison and query evidence at the
first P1 design checkpoint before freezing code. A concrete inability to meet the
bounded interface requires a scoped reforecast, not silently dropped acceptance.

Scope excludes submit/status/cancel (AR-008-B), rich legacy run representations,
event/workspace/artifact loading, live worker fences, mutable repair/audit, new
schema/profile authority, customer activation, arbitrary filters, history export
and provider calls. Existing legacy routes and their retained run.read audit stay
unchanged. The new RunSummary is the frozen seven-field representation, not the
legacy rich run response.

## Dedicated signing-key lifecycle and safe errors

Proposed configuration is optional `REWIND_CURSOR_SIGNING_KEY`, held as a secret:
exactly 43 canonical unpadded base64url characters encoding 32 operator-generated
random bytes. Do not derive it from the encryption, bootstrap or session key,
reuse the artifact encryption bytes, generate it on application startup, or
persist it to the database. Validate canonical decoding and unequal encryption
key bytes without logging values. Operators supply the same stable key to all
API processes and restarts. Coordinated replacement invalidates all existing
cursors; there is one current key, with no implicit grace keyring. Restarting
pagination after rotation is safe.

Missing or malformed cursor configuration is a LIST-only dependency failure:
after schema eligibility and fresh identity/project authority, return existing
503 `dependency_unavailable`, retryable true, with the fixed safe error envelope.
A detail request, /api/me, logout and liveness do not depend on this key. Do not
make optional malformed cursor configuration abort construction of unrelated
surfaces. An inaccessible project stays 404 before cursor/configuration details;
an unauthenticated request stays 401. Preserve the actual migration-only guard;
no new ready profile or broad route exception is introduced.

Errors carry exactly code/message/request_id/retryable and the existing generated
request ID/no-store headers. Never log a cursor, key, SQL/body, raw exception or
source payload. Native query-budget exhaustion and inconsistent bounded source
metadata give fixed dependency_unavailable, no partial page or continuation token.
Missing/unmapped/foreign run ownership and lost visibility give the existing
inaccessible 404. A revoked or expired credential still follows authentication
and fresh authority semantics; no cursor is durable authorization.

## Strict cursor and ordering policy

Use a versioned, domain-separated HMAC-SHA256 envelope over canonical payload
bytes: `base64url(payload).base64url(mac)`. Reject more than 2048 ASCII bytes before
decoding, anything other than two canonical unpadded segments, or a non-32-byte
MAC. Compare signatures in constant time before parsing payload JSON. Reject
duplicate/unknown members, nonfinite values, booleans masquerading as integers,
unsupported versions and noncanonical encodings. A cursor is tamper-evident, not
confidential; it contains no task/source body or secret.

Bind the exact payload to version, project ID, full authenticated principal ID
(`oidc:<64hex>` or `api-key:<32hex>`), the fixed empty filter set, page limit,
initial committed project watermark, last `(created_at, id)` and expiry. Use the
full issuer-bound principal, not an OIDC subject alone or cookie role. Watermark
is an integer in 0..2^63-1; last ID is 32 lowercase hex and timestamp is canonical
UTC with microseconds. Freeze the finite payload grammar in P1 tests.

The first request defaults to 50 or accepts an integer 1–200. A continuation with
omitted limit uses its signed limit; an explicit different limit refuses. Repeated
cursor/limit query parameters refuse rather than choosing one. The initial expiry
is server UTC time plus 900 seconds and is carried unchanged across all pages;
continuations do not slide it. Expired/foreign/tampered cursors return 422
invalid_cursor only after project visibility succeeds. Empty filters are not an
extension point for arbitrary caller search.

Capture the first page watermark and candidate page in one SQL statement. Read
only rows in the authorized project with published_seq at or below that immutable
watermark, ordered by `(created_at DESC, run_id DESC)` and strictly below the
previous tuple. Fetch at most limit+1 candidates; the last returned tuple, not a
skipped malformed row, defines continuation. Equal timestamps use the ID tie.
Do not re-round or overwrite accepted projection timestamps: AR-006-A already
rounds the exact legacy binary float ties-to-even and stores UTC.

Commit-ordered project sequence excludes later backfills even when their created
values are old. No snapshot of mutable status is promised; deletions or revocation
can shorten traversal. No duplicate row or silently filtered malformed candidate
may masquerade as a valid empty page. A selected malformed row fails the response.

## Finite conservative suppression checkpoint

The following table is a proposed implementation rule within C04, to review before
runtime code. It applies only after valid bounded projection/source/job metadata,
complete scoped ancestry and final receipt equality. It does not reread blobs or
re-verify capture integrity. Stored publication-time verification remains the
provenance for complete evidence; a read cannot manufacture that verification.

| Stored projection / current source | Current owning-job evidence | Returned status / branchable |
| --- | --- | --- |
| Complete; source remains complete with matching run/project/parent/UTC creation and represented terminal head; both source and projection permit restoration | Job status succeeded, cancellation false, valid scoped identity | complete / true; source success=false is still complete and a succeeded job needs no active lease |
| Same complete evidence, but source or projection is redacted/non-branchable | Any otherwise valid current job | complete / false |
| Same complete evidence and restoration flag, but job is cancelled, failed, nonterminal or otherwise conflicts with normal completion | Job status queued/running/failed/cancelled, or cancellation true, including an apparently active legacy owner/lease | complete / false; never infer compatible live running authority |
| Stored complete but current source is partial/noncomplete or has contradictory represented identity/head | Any | Fixed refusal; do not return the stale completion claim |
| Stored failed | Valid scoped source/job, without contradictory identity | failed / false; evaluator failure alone is not this classification |
| Stored incomplete | Valid scoped source/job, without contradictory identity | incomplete / false; a now-complete source cannot promote unverified stored evidence |
| Stored running | Any legacy job/owner/lease | incomplete / false until a future reviewed compatible generation/fence reader exists |
| Missing projection/source/ancestry, foreign scope or lost visibility | Any | Inaccessible 404 |
| Malformed selected metadata, unsupported shape, contradictory identity, or changed original receipt during this request | Any | Fixed failure, no partial page; fresh retry may recompute after the cause is resolved |

For partial states preserve the last verified projection event_head even if the
current running manifest lags an event; do not scan events, infer terminal objects
or turn a manifest artifact digest into an event-chain hash. A source identity
contradiction is not a reason to silently omit a candidate. The supported current job vocabulary is exactly queued, running, succeeded, failed
and cancelled; any other state refuses. Cancellation and branchable must be exact
booleans, success must be a supported source value, and owner/lease values must
validate without supplying unavailable generation authority. Never use truthiness
of malformed SQLite values. The P1 fixture matrix must enumerate each actual job state and
complete/partial/success/redaction combination under these rules. There is no
per-read repair, restricted repair audit, sequence reassignment or source write.
A read summary says nothing about natural-failure eligibility or grading validity.

## Scoped source receipts and final authority

The current `projection_rows.read_index` is an operator helper with a global
preflight and run-ID order; it is not a customer list implementation. Existing
legacy repository list limits/order are also not the frozen v1 cursor contract.
Create a focused reader that uses project-leading indexed SQL, before-transfer
CASE/type/byte bounds for every selected dynamic cell, and limit+1 candidates.
Retain an invalid-row marker and refuse it; do not remove oversized rows in a
WHERE predicate and pretend traversal was complete.

`run_index` has no owning-job field or frozen whole-source digest. Read the current
bounded run record to find its job and verify complete project/parent ancestry
through the accepted scoped helpers. Compare the represented immutable projection
identity (including parent and exact UTC created value) with supported source
fields. For complete sources compare projection event_head with the nullable manifest
`head` in records.data (Engine updates it from the event-chain hash), not task_ref,
workspace/evaluation locators or artifact digests. Map run ID and created time from
the bounded record identity using the accepted exact UTC conversion, parent/job
from its manifest and project from relational scope. Preserve the partial-head
exception: a partial manifest head may lag the last verified projected head.
Demonstrate this exact mapping with actual Engine/backfill fixtures; do not read
event artifacts to guess it.
This is not a claim to detect every historical source mutation absent a stored
publication digest.

Retain the original normalized projection cells and original bounded raw run/job
content, scopes and by-job membership sets across all loads. Extend or reuse the
existing materialized receipt pattern for a single final SQL statement comparing
those original values together, then reauthorize the same named project/principal
on fresh database state. Do not rebuild the expected identity from the latest
row. Selected owner/scope/source/job/ref changes fail the whole response; no
partial return, silent omission or automatic retry. Reuse the existing 2048-identity,
4 MiB receipt-input and 16 MiB repeated-metadata budgets with shared accounting;
ancestry/node/edge bounds apply to the entire request, not once per result.

Use scoped READ COMMITTED/READ ONLY PostgreSQL access and fresh final observations;
a long repeatable snapshot cannot establish post-load revocation. SQLite must use
supported clean legacy transaction mode with query_only scoped to the owned
connection and no retained read snapshot spanning all phases. Restore local state
or invalidate an unusable connection. This is optimistic SQL consistency, not
linearizability up to socket delivery; no storage or network work occurs inside
read/write locks and no new write transaction is needed for these routes.

## Query-work proof and cleanup

The current `(project_id, created_at DESC, run_id DESC)` index supports the intended
order, but LIMIT alone does not bound work: many late publications excluded by an
older watermark can force scanning. Prefer set-oriented candidate, ancestry and
receipt queries; do not introduce per-item N+1 reads merely because a large call
ceiling would permit them. Keep a finite query count as a secondary defense.

Proposed P1 ceilings are 4096 SQL statements, a cumulative two-second SQL-work
budget and 20 million SQLite VM instructions (callback every 1000). PostgreSQL
statement_timeout is clipped to the remaining budget and at most 2000 ms, with
lock_timeout at most 250 ms and bounded by remaining time. SQLite progress/time
and busy handling must be bounded natively. These are proposed adapter ceilings,
not frozen C04 constants, benchmark results or end-to-end latency promises. P1
must show representative and adversarial fixtures succeed or safely refuse within
their supported limits; revise measured ceilings through review before freezing.

Exhaustion aborts the native statement and fails closed. Remove SQLite callbacks
before cleanup, roll back any owned transaction, restore scoped settings or
invalidate the physical connection, and demonstrate subsequent safe reuse. No
abandoned timeout thread, automatic retry, global engine/guard setting change or
promise to bound arbitrary network stalls. Missing driver/version support refuses
this adapter rather than silently executing without work bounds.

Require actual PostgreSQL plans/execution for deep cursors, many post-watermark
backfills, max-page/ancestry receipts and permission failures; SQLite instruction
budgets are not PostgreSQL performance proof. An indexed plan alone is also not a
runtime bound. No additive index is justified yet. If measured fixtures cannot
meet the interface with existing indexes and safe refusal, stop and propose a
separate bounded additive migration/catalog review and estimate. Do not mutate
historical profiles or smuggle schema work into P2.

## Acceptance evidence and delivery limits

P1 tests include strict cursor grammar/binding/expiry/rotation and omitted limits;
fixed-corpus traversal and exact timestamp ties; reversed publication completion,
rollback and old-timestamp late backfills; complete success=false and redaction;
unfenced/expired/cancelled jobs; malformed/NUL/BLOB/oversized selected metadata;
changes between initial and final receipt statements; missing/foreign parents;
max-page shared ancestry and query-work cleanup. Prove zero artifact/event I/O,
no source/projection writes, SELECT-only privileges and actual PostgreSQL behavior.
No source-derived enum/head assertion may pass merely because a synthetic fixture
invented a field the Engine does not produce.

P2 tests exercise both actual frozen GET operations with named-project authority,
401/404/403/error precedence, key/cursor dependence only on LIST, full response
shapes/headers, fresh principal/membership revocation before return, and immutable
migration-only admission refusal before customer sinks. Keep v1 summaries separate
from existing legacy metadata/rich graph routes; do not activate a profile or
change the retained audit behavior. Installed-package smoke exercises the actual
new modules under synthetic supported fixtures without a product bypass flag.

Each package requires exact-source independent review, matching hosted checks,
accepted merge and the normal protected-main candidate verification. P2 remains
Not started until P1's accepted merge is recorded; AR-006-B remains unverified
until both and the complete CT-M1-005/006 matrix pass. A fixture/design is not
production readiness, paid execution, a new funding decision or G1 acceptance.

The amendment changes only delivery planning: 151 aggregate tasks, 156 planned
PRs, unchanged 544 acyclic outer edges, 456 base days, 771.1 summed upper days and
570 days with the alternative 25% allowance. The recomputed effort-only path
remains 168.5 days; M1 is 57.5 days and TL 75 days. The extra two base/three upper
days replace the prior listing estimate. Historical schedules, C21, owner
decisions and frozen contracts remain unchanged.
