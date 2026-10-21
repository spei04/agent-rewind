# Existing-route authority — AR-007-C

Planning/design reconciliation, 2026-10-20. Source inspected:
3c60f1a4b5e6d16504b2209dadd4b735d57037ce. Implementation is **Not started**;
this record is not route acceptance or permission to enable customer admission.
The lead and A accepted the concrete design; the exact planning composition
still requires review.

## Entry, ownership and estimate

AR-007-B scoped repositories, AR-011-B safe errors/readiness and AR-009-B's
verified publication reader are Verified. C04 and C05 are required contracts.
The new direct AR-009-B edge records an actual consumed interface. No reverse
dependency on future route or admission producers is introduced.

C owns implementation, A reviews authentication/security/read behavior,
B reviews transactions, and the lead integrates. Use one coherent preparatory
PR with four reviewable commits:

1. Issuer-bound v2 identity/session and fresh default/named-project authority.
2. Existing data-route readers/renderers using scoped verified refs/graphs.
3. Atomic cancel/key actions and the required unavailable work-admission adapter.
4. Exhaustive route, compatibility and real PostgreSQL race/rollback tests.

Estimate: **6 BE engineering days, range 6–10, medium-low confidence**,
replacing the original two-day estimate for the same obligations. Reforecast
at the first immutable identity/reader handoff, about 1.5–2 engineering days:
renderer compatibility and transaction coupling are the main uncertainty.
These commits are review checkpoints, not separate activation gates or a
calendar commitment. Do not mark an incomplete route subset Verified.

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
| POST /api/runs, /api/branches, /api/studies, /api/investigations | Fresh default-project action authority and existing readiness policy; required admission adapter is unavailable in this slice. Refuse before artifact upload, credential creation, job/scope/audit writes or provider access. No raw enqueue fallback. |
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

The required admission adapter has no permissive default. AR-008-A owns
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
unavailable-adapter paths before any persistent write/provider access.
Verify /api/me and logout after membership revocation, exact Origin/CSRF,
DB-unavailable refusal and explicit-role UI behavior. Keep the production
schema-guard negative matrix unchanged.

Independent A/B review, exact-head hosted checks, preserved legacy-compatible
shapes and documented future obligations are required. The lead records
Verified only for this coherent preparatory task. M1/customer activation,
live publication, production readiness and external funding/data gates remain
open.
