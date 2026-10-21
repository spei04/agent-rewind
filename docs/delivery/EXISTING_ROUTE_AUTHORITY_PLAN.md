# Existing-route authority — AR-007-C

Planning/design reconciliation, 2026-10-20. Original inspected source: 3c60f1a4b5e6d16504b2209dadd4b735d57037ce. P1 is **Verified** in [PR #78](https://github.com/spei04/agent-rewind/pull/78), accepted merge 51a2b1fefc40fc871426a47e3f3865fcbeef5bec, after independent A/B review, matching PR/main checks and candidate verification. P2 is **In progress** after that gate; aggregate AR-007-C remains In progress. This does not accept route behavior or enable customer admission.

## Entry, ownership and estimate

AR-007-B scoped repositories, AR-011-B safe errors/readiness and AR-009-B's
verified publication reader are Verified. C04 and C05 are required contracts.
The new direct AR-009-B edge records an actual consumed interface. No reverse
dependency on future route or admission producers is introduced.

For P2, C owns route/auth/read/UI integration and B owns atomic scoped mutations.
A independently reviews identity/read/security and B's mutation implementation;
B independently reviews C's transaction consumption; C checks action-interface
integration, and the lead integrates. [Issue #75](https://github.com/spei04/agent-rewind/issues/75)
tracks aggregate AR-007-C. The user requested smaller PRs; use two independently
reviewable delivery packages with their own cards in the execution backlog:

| Package | Delivery boundary | Effort and prerequisite |
| --- | --- | --- |
| AR-007-C/P1 | Strict v2 codec/identity helpers, fresh project authority/typed denial, shared journal-free verified reader with unique root and final compound recheck; existing RunPublisher.read delegates to it. Auth/session issuance, routes, UI, mutations and admission stay unchanged. | 2 days, range 2–3; inherits Verified AR-007-B/011-B/009-B and C04/C05. |
| AR-007-C/P2 | Wire Auth/v2 issuance, all existing routes/renderers/UI, atomic cancel/key actions, unavailable admission and the full route/PostgreSQL matrix. | 4 days, range 4–7; starts only after independently accepted, merged P1. |

Aggregate estimate remains **6 BE engineering days, range 6–10,
medium-low confidence**. Each package needs exact-source review, matching
checks and accepted merged-source evidence. P1 can be accepted independently
without changing existing HTTP behavior; aggregate AR-007-C stays unverified
until P2 and the complete current-route/transaction matrix pass. Both remain
migration-only, with no customer/live-path activation. Reforecast after the
first immutable identity/reader handoff at about 1.5–2 engineering days;
this is not a calendar commitment or a second charge for the same work.

No new route, schema/profile activation, session infrastructure, IdP deployment,
historical artifact adoption, paid call, data access or research scope is added.
The three contributor slots are shared with review; historical daily schedules
are retained as history, not an active six-person schedule.

## Trusted identity and project decisions

Apply the exact issuer-bound principal and v2 session grammar in
[C04](M1_CONTRACT_FREEZE.md#identity-legacy-routing-and-key-authority).
Validate issuer, audience, signature, nonce and expiry before identity
construction. Reject old session versions and require login again; cookie
role snapshots cannot authorize access and the shared artifact key is not
rotated for logout. Bootstrap is not a customer API credential.

Context-free legacy data routes resolve only the explicit active
legacy_default membership. Missing, revoked or ambiguous defaults, foreign
IDs and inaccessible resources yield the same safe 404. A known accessible
project with insufficient action rights yields 403; unauthenticated requests
yield 401. Preserve fixed safe errors and request correlation. Do not map all
repository ResourceNotFound errors to 403 or trust a role/project in the body,
query or a new legacy header. The named-project resolver is a reusable
server-path dependency for later routes, exercised now by focused tests.

Service-key authority is the intersection of current token role, expiry,
revocation, immutable scope and current membership. A retained legacy
administrator token has at most the reviewed operator ceiling. It never gains
key administration. A human with current maintainer membership may issue only
viewer/operator keys. New key + immutable scope + matching membership with an
explicit legacy_default=true for that already-authorized project + restricted
audit commit atomically; no implicit "only membership" selection. Raw token
material is returned once after success and never appears in audit/errors.
Unknown/foreign revocation returns 404.

Fresh authority is required before protected I/O and again before returning
protected results or committing mutations. Use typed internal decisions so
role denial and inaccessible scope remain distinguishable without exposing
foreign resource existence.

## Exhaustive route disposition

This inventory is the existing surface at the source commit. Every added or
changed route must receive an explicit disposition before this PR is accepted.

| Existing route | Required boundary |
| --- | --- |
| GET /api/runs, /api/runs/{run_id}, /api/runs/{run_id}/files/{step} | Fresh default-project authority, scoped repository/lineage and accepted published graph/ref reader; verify owner/role/digest and reauthorize before return. |
| GET /api/compare | Authorize both roots and all nested refs in the same project. Replace raw compare/artifact reads with a bounded verified adapter. |
| GET /api/studies, /api/studies/{study_id}, /api/jobs | Scope list/detail and nested run/result references before body access; use verified refs or safely refuse unsupported/unpublished evidence. No historical raw-hash fallback after a preliminary scope check. |
| POST /api/runs, /api/branches, /api/studies, /api/investigations | Fresh default-project action authority, then refuse the unavailable required admission adapter before readiness probes or storage. When a future adapter is available, existing readiness policy still applies before admission. Refuse before artifact upload, credential creation, job/scope/audit writes or provider access. No raw enqueue fallback. |
| POST /api/jobs/{job_id}/cancel | Scoped fresh action check and job state/intent/audit in one transaction; preserve terminal outcomes and use the common project-before-job hierarchy. No artifact-readiness dependency. |
| POST /api/keys; DELETE /api/keys/{key_id} | Human-maintainer authority and key/scope/membership/audit atomicity with fresh transaction-bound reauthorization; no service-key escalation. |
| GET /api/schema | Existing default-project-scoped schema access; no broad /api/schema or prefix exemption from the schema guard. |
| GET /api/me | Exact identity-only exception: authenticated v2 identity and own CSRF token, optional fresh effective default role or null for missing/revoked/ambiguous membership. No project/resource IDs, resource counts or union of memberships. DB failure is safe 503, not a fallback to cookie role. |
| GET /auth/login, GET /auth/callback | Explicit identity-establishment boundary: existing OIDC validation, state/nonce and safe redirect behavior. No project-data authority or new IdP provisioning. |
| POST /auth/logout | Authenticated v2 identity, CSRF and exact Origin; logout remains possible after project revocation and is independent of project membership/artifact readiness. |
| GET /; mounted /static/*; GET/HEAD /livez, /healthz, /readyz | Preserve their reviewed exact static/liveness/connectivity/readiness behavior and bounded probes; no customer-resource access. |

The identity-only /api/me exception is to project authorization, not a new
customer-ready schema profile or broad middleware exemption. Existing
migration-only schema guards still deny customer paths. Legacy endpoint tests
may use explicit test-only fixtures; guard-denial tests must use the real guard.
The UI enables privileged actions only for an explicit current operator or
maintainer role, never merely "not viewer" or a truthy stale value.

The current implementation still calls raw record/artifact helpers in run,
files, compare and job rendering and unscoped enqueue/cancel/key mutations.
An initial scope check does not make those consumers safe. Replace those
paths or refuse unsupported evidence. Preserve supported response shapes;
do not silently advertise complete history for data lacking scoped refs.

## Mutation and admission contracts

Authorization, project scope, relevant current row state, mutation and
restricted audit must share a transaction. Lock affected projects in stable
order before owning jobs/runs, consistent with C04 and AR-009-B/006-A.
Recheck membership/key revocation at the documented effect boundary; prove
actual concurrent mutation behavior with PostgreSQL rather than only mocks.
No storage/network call may run while retaining the transaction.

The required admission adapter has no permissive default. Check its availability after fresh authorization and before any readiness probe, storage call or enqueue; prove zero calls at those boundaries while it is unavailable. AR-008-A owns
canonical identity, original-operation recovery, scoped atomic publication and
frozen execution configuration; AR-008-B owns route integration; AR-010-B owns
generation/config/cancel validation before paid dispatch. Those prerequisites
must be accepted before actual work creation is enabled. Existing version-1
legacy body shapes do not excuse missing new-job scoped configuration.
Historical jobs are not implicitly redispatchable.

## Deferred consumer and acceptance matrix

All original acceptance requirements remain. This task cannot test an absent
producer by inventing a new endpoint or treating an injected refusal as replay.

| Consumer / case | Ownership and status at this checkpoint |
| --- | --- |
| CT-M1-007 | Planned overall. AR-007-C owns the exhaustive existing-route/default/named-policy subset; AR-006-B and AR-008-A/B add actual v1 routes; AR-012-B verifies the integrated case. |
| CT-M1-008 | Planned. Actual accepted-request identity recovery after revocation requires AR-008-A/B. AR-006-B must also deny revoked result/cursor disclosure; AR-012-B requires the real durable-replay evidence. |
| CT-M1-009 | Planned overall. AR-007-C owns existing-route nested artifact/scope denial. AR-008-A/B own new scoped immutable job config; AR-010-B validates it before dispatch; AR-012-B verifies the full case. |
| AR-006-B | New v1 list/detail/cursor consumers use the shared named-project authority and current-job suppression. No listing endpoint is added here. |
| AR-008-A/B | Admission, operation/retry/status and cancellation consume the authority and frozen-config contracts; retain CT-M1-010/012/013/014 tests. |
| AR-027-B | Future timeline/files/branch/compare API integration owns its bounded reads and retry authorization tests. |
| AR-029-B, AR-032-B | Future report/evidence/lifecycle exports use the same authority and fresh reauthorization; remain producer-owned. |
| AR-012-B | Full 24-case integration gate, including actual durable replay and generation/config checks; no fixture-only or partial-route substitution. |

Only after its exact implementation and tests pass may AR-007-C record partial
evidence for CT-M1-007/009. Their overall acceptance and CT-M1-008 remain planned
until the listed producers and integration gate pass. No original acceptance
case, OpenAPI version or historical contract approval is rewritten by this plan.

## Required evidence and exit gate

Record the exact route inventory, supported renderer compatibility and safe
unsupported cases. Tests must cover two issuers sharing a subject, old cookies,
expired/revoked keys, missing/ambiguous defaults, inaccessible versus
insufficient-role responses, named/cross-project contexts and same-digest
objects owned by different projects. Verify safe errors with secret canaries.

Use real PostgreSQL for revocation before protected return, role/key mutation
races, transaction rollback after each key/cancel stage and terminal cancel
preservation. Test unauthorized requests before expensive probes and all
unavailable-adapter paths before readiness probes, storage, enqueue or any
persistent write/provider access.
Verify /api/me and logout after membership revocation, exact Origin/CSRF,
DB-unavailable refusal and explicit-role UI behavior. Keep the production
schema-guard negative matrix unchanged.

Independent A/B review, exact-head hosted checks, preserved legacy-compatible
shapes and documented future obligations are required. The lead records
Verified for the aggregate only after accepted merged P1 and P2 and the complete current-route matrix. M1/customer activation,
live publication, production readiness and external funding/data gates remain
open.

Current assignment: C owns [P2 #77](https://github.com/spei04/agent-rewind/issues/77) Auth/v2 integration, existing routes/verified renderers/UI and their tests; B owns scoped atomic cancel/key actions and dedicated unit/PostgreSQL tests; A independently reviews identity/security/read and mutation boundaries; lead integrates and maintains planning records. [P1 #76](https://github.com/spei04/agent-rewind/issues/76) is Verified at accepted merge 51a2b1f. P2 requires the complete current-route matrix, independent exact-source review and accepted merged evidence.

2026-10-20 P1 hosted correction: final run [39526088575](https://github.com/spei04/agent-rewind/actions/runs/39526088575) at e7442b5 failed one PostgreSQL fixture before the maximum-reference reader query: repeated project parameters inferred conflicting text/varchar types. Python 3.11 passed 1778 with seven skips; Python 3.12 passed 1782 with three skips; each had one failure and one existing warning. The other 45 new PostgreSQL cases, package/security and three gVisor tests passed. B delivered fixture-only dbfbae0, preserving all 16,000 rows and assertions; A accepted the exact fixture correction and the lead owns matching hosted verification. P1 remains Implemented; verification pending, P2 Not started and aggregate #75 In progress. B/C completed read-only P2 interface and test preparation; the accepted 4 [4–7] engineering-day estimate and prerequisite gate remain. No new checkout, model call, paid resource or partner data was used.

2026-10-20 P1 query correction: C delivered 8222644, integrated as 8be6316, after a bounded SQLite probe found repeated JSON rowset scans. A/B accepted materialized, exact-object-ID matching with the original single-statement snapshot, complete descriptor/ownership checks and input/result bounds retained. A independently verified 16,000 matching refs within about 4.21 million VM instructions under a 20-million ceiling, plus foreign/substituted/missing refusals; 61 reader/publication tests passed. Unsupported SQLite versions refuse before storage. Lead integration passed 314 focused tests with 53 explicit local PostgreSQL skips, lint/format/security rules, strict types and all planning/contract validators. PostgreSQL fixture correction dbfbae0 remains included. These results do not establish PostgreSQL performance: final matching hosted execution, package checks and accepted merge remain required. P1 is Implemented; verification pending; P2 remains Not started and aggregate #75 In progress. No new checkout, dependency installation, paid call or partner data was used.

2026-10-20 P1 accepted delivery: PR #78 source 923647d85ac8acc68f5334c2edcad40c6638d59a accepted by A for identity/read security and B for authority/SQL semantics; merge 51a2b1fefc40fc871426a47e3f3865fcbeef5bec has the identical reviewed tree. PR run 39528447469 and protected-main run 39529350057 passed 1789 tests on Python 3.11 and 1793 on Python 3.12, including all 46 new PostgreSQL cases; package/security and three gVisor tests passed. Candidate 12314568373 archive, exact four-file set, source/pinned manifests and package/SHA256SUMS hashes independently verified. Private release record is indexed outside disposable checkouts. P1 is Verified; P2 #77 is In progress after this prerequisite, with the full current-route/transaction matrix still required before aggregate #75 can close. Customer, production, research-execution and spending gates are unchanged.
