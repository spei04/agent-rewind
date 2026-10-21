# Ledger execution proposal

2026-10-21 · Readiness review against HTTP source `a304d52b52667b882c70e922b73d7070d714efb0`.

**State:** Draft for internal review. AR-010-A remains Not started until AR-008-B has accepted protected-main delivery. This proposal does not change the approved task ledger, estimates, contract interpretation or runtime. The current task remains 3 [3–4.5] BE days until a reviewed amendment is recorded.

## Problem and intended result

New paid work needs one durable integer reservation at organization, project and job levels. A retry must recover the original logical call without granting another dispatch opportunity. Uncertain old obligations must continue to constrain new admission.

The existing `Database.reserve` increments a job counter. It does not implement hierarchical accounts, immutable account periods or generation fencing. The legacy worker uses owner and process/Python time; its job-first lock acquisition cannot be extended by acquiring a project afterward.

Consume the [frozen C04 contract](M1_CONTRACT_FREEZE.md#relational-closure-fences-and-accounting), [logical model](../../contracts/proposals/m1.data-model.json) and [AR-010-A card](../EXECUTION_BACKLOG.md#ar-010-a). The source contract remains authoritative.

## Recommended entry decisions

| Decision | Recommended boundary | Reason / remaining review |
| --- | --- | --- |
| Trusted account provisioning | Explicit internal operator manifest identifying existing organization/project/jobs, account IDs, UTC periods and integer caps | Validate ownership from SQL. Compute opening holds from original data, never caller-supplied amounts. No public provisioning route or account creation during reservation. |
| Job lifetime | One finite, immutable authorized execution window supplied by trusted provisioning | This is a proposed interpretation of C04's fixed job lifetime, not an observed completion interval. Neither a retry, claim, generation nor billing rollover renews it. Missing historical bounds refuse provisioning; do not invent timestamps. |
| Window expiry | Refuse new claims/reservations and later dispatch outside the window; retain all existing obligations and original IDs | Early completion leaves the recorded window unchanged. Reconciliation may occur afterward through its future authorized producer. The later live worker must consume the persisted bounds. |
| Automatic deadline policy | Defer a new automatic admission-policy producer | Existing mutable `max_job_seconds` starts at each worker claim. Reusing it would change its meaning. The exact public SubmitRun and native-v1 configuration have no lifetime field and remain unchanged. |
| Rollover | Keep balances and call account IDs in their original periods; include prior outstanding held exposure in new organization/project admission | A blanket refusal for any old hold is insufficient as complete rollover acceptance. Stable scope exclusion and bounded complete exposure reads must prove the result; overflow or unprovable history refuses. |
| Opening exposure | Copy original `jobs.reserved` exactly once, aggregate once per level, retain the gross compatibility counter | No fabricated provider calls, receipts or invoices; historical fixture exposure remains 245000 microUSD. A cap below exposure refuses rather than silently increasing the cap. |
| Provisioning exclusion | Acquire the appropriate stable organization/project scope before downstream jobs/accounts | Sorted existing account IDs alone cannot serialize simultaneous absent-period inserts. No late shared-to-exclusive lock upgrade. Freeze every explicit and implicit FK/trigger wait. |
| SQL execution support | Exact, revision-specific PostgreSQL trigger/function inventory and literal dialect profiles | C04 requires deferred relational checks. Earlier profiles must continue rejecting extra executable objects. Never allow arbitrary functions/triggers to make a catalog pass. |
| Live activation | Keep migration-only compatibility and reserve-only internal services | AR-010-B owns actual worker/permit/cancellation integration. This proposal enables no provider calls or customer readiness. |

The authorized-window meaning is the main semantic decision to settle before schema code. If job lifetime instead means actual first start through eventual completion, the current fixed non-null account-bounds model needs an explicit amendment; neither recommended provisioning nor an invented infinity resolves that ambiguity.

The operator manifest must have a reviewed exact schema, canonical digest, authority model, size/cardinality bounds and replay/conflict semantics before implementation. Job-account limits must not expand the unchanged job budget. Historical and newly created jobs need explicit producers; absence of one is an unavailable path, not a fallback to mutable settings.

## Proposed two-package delivery

This is a proposed split within AR-010-A. It does not create approved packages or make its successor eligible.

### P1 — Ledger schema, trusted provisioning and opening backfill

- **Objective:** Represent scoped accounts, logical calls and evidence-backed entries without rewriting historical meanings.
- **Scope:** One additive linear revision after ar6; the three frozen ledger tables; job lease-generation and legacy-reservation fields; explicit provisioning manifest and exact opening migration. Update both catalog inspection and migration exclusion coherently for the new 20-table profile. Add only the reviewed PostgreSQL deferred constraints/functions with exact definitions, enabled state, owner/security/search-path/privilege expectations. Preserve literal SQLite and PostgreSQL profiles, restart/restore behavior and migration-only compatibility.
- **Out of scope:** HTTP changes, automatic deadline policy, new public/native-v1 fields, live worker claims/dispatch, settlement/release commands, transfers, invoice ingestion or new incident tables.
- **Prerequisites:** Accepted AR-008-B, settled lifetime/provisioning interpretation, exact schema/interface review and supported-source inventory.
- **Contracts:** C04 account shape, immutable call account triple, original periods, unique entries, same-call/project evidence closure and opening exposure; existing operator migration/backup/restore contracts.
- **Acceptance:** Every old field/row/ciphertext is preserved except explicitly declared additive backfill. Opening exposure is copied once and caps below it refuse. Fresh, resumed and restored states agree. A completed profile accepts only its reviewed relational/executable objects; drift and unsupported states refuse before customer activity.
- **Tests:** Historical 245000 fixture; missing/conflicting manifest identities; cross-project/null-shape/period overlap; simultaneous absent-period provisioning; wrong/extra/disabled triggers/functions; deferred commit rejection; same-call evidence constraints; restricted runtime DDL denial; pre/post-commit interruption and exact restore on actual PostgreSQL.
- **Security/reliability:** No supplied opening balance, generic executable-object allowance or silent cap increase. Preserve old-profile rejection. Failed migration must leave a diagnosable resumable state or confirmed rollback, never a ready profile.
- **Effort/role:** Proposed BE 3 [3–5] days, medium-low confidence; PL/QE/security review. Executable catalog and absent-period serialization are the principal uncertainty.
- **Done:** Independently reviewed exact DDL/profiles, migration and restore proof, matching hosted checks, accepted merge and candidate verification. P2 waits for this evidence.

### P2 — Integer reservations, minimum generation fence and rollover proof

- **Objective:** Make concurrent reserve-only calls conservative, idempotent and compatible with accepted admission/read/cancel behavior.
- **Scope:** Connection-bound claim/fence and existing-account reservation primitives; immutable logical-call identity; call/scope/three-entry publication and three-level balance updates in one transaction; gross job counter; prior-period exposure checks; scoped recovery of an uncertain original call.
- **Out of scope:** Live ChatPolicy replacement, network dispatch, cancellation refunds, invoice reconciliation, transfer production, broad lease/process recovery and automatic account creation.
- **Prerequisites:** Accepted P1 and complete lock/interface review against actual consumers.
- **Proposed internal interfaces:** `claim_generation(connection, scope, owner, lease_policy) -> JobFence`; `require_live_job(connection, scope, expected_fence)`; `reserve(connection, scope, fence, intent, account_ids) -> ReservationRecord`; separate scoped inspection after uncertain acknowledgement. Exact signatures, exceptions, units and bounded SQL behavior must be frozen at entry.
- **Identity contract:** Intent binds logical-call ID, project/job, request digest, purpose, amount, price version and account triple. Exact repeats recover existing state; changed bindings conflict. Neither recovery nor a reservation record is a fresh dispatch permit.
- **Lock/time contract:** Preserve project(s), organization/grants/key, original scope/job and sorted account order. Choose any stronger organization exclusion before downstream acquisition. Refresh database time after waits; compare owner/generation/running state/cancel and persisted execution window. Increment generation only on successful claim. Do not wrap legacy job-first transactions and then acquire a project.
- **Acceptance:** No cap can be exceeded by concurrent work or period rollover; no call is counted twice at one level; old holds and original IDs survive. Reject booleans, floats and out-of-range integers. Preserve `jobs.reserved = legacy opening + gross new reservations`, including after future evidenced release. Unknown commit preserves identity/hold and never creates new work.
- **Tests:** Eight-way shared-cap contention; different projects sharing an organization; nonoverlap and outstanding prior holds at rollover; repeated/conflicting logical calls; signed-64-bit boundaries and 2**53+1; wait-time expiry/cancellation/generation change; rollback at each write stage; lost acknowledgement; physical connection cleanup; unchanged admission, operation GET and cancellation behavior. PostgreSQL must execute the concurrency/deferred-constraint claims.
- **Security/reliability:** No external I/O in SQL, no estimate treated as invoice truth, no ambiguous retry/refund, no implicit settings fallback. Unsupported settlement/transfer paths retain exposure and remain unavailable.
- **Effort/role:** Proposed BE 3 [3–5] days, medium-low confidence; TL/QE review and independent PostgreSQL tests.
- **Done:** Independent source/test review, local and hosted actual-database evidence, installed package proof, accepted merge/candidate and all AR-010-A criteria. Full C04 and M1 acceptance remain separate.

Provisional total: **6 [6–10] engineering days**, replacing the current 3 [3–4.5] only if the amendment is reviewed. These are effort estimates, not a staffing or calendar commitment. No new external dependency or funding gate is proposed.

## Evidence and future producer ownership

| Obligation | Current slice representation | Runtime producer / later owner |
| --- | --- | --- |
| Account/call/entry relational constraints, integer balances, openings and rollover exposure | AR-010-A schema and reserve path | AR-010-A; integrated M1 proof in AR-012-B |
| Worker dispatch transition, cancellation/expiry uncertainty and unchanged holds | Fence interface only | AR-010-B, with broader process/lease drills in AR-017 |
| Authentic receipt, charge and non-charge vocabulary | Evidence-reference closure does not establish financial authenticity | AR-023-A |
| Durable external dispatch/response/unknown evidence | No invented invoice producer | AR-023-B |
| Audited idempotent settlement/release, over-quote handling and breached-account freeze | Store required shapes; successful unsupported reconciliation stays unavailable | AR-023-C consuming AR-023-A/B |
| Historical opening-hold adjustment and actual period/account transfer | Retain exposure and original identity; no fabricated call-owned evidence | Clarify this existing C04 obligation explicitly in AR-023-A and AR-023-C cards/tests before those paths activate |

The final row is a traceability wording gap, not justification for a new account-transfer table, fake provider call or reverse prerequisite. The current `budget_evidence` ownership model is call-owned; imported opening exposure intentionally has no provider call. Authentic representation and a durable producer must be frozen by the later owner.

Over-bound billing must eventually retain the evidence and block further dispatch. AR-023-C already owns over-quote reconciliation and breached accounts. Before any such evidence-ingestion path is enabled, its producer/migration must provide durable block state and repeated-dispatch denial proof. AR-010-A's reserve-only completion must not claim that this later capability exists.

## Assignment and dependency review

- A: read-only source/interface and workload-lifetime review completed; explicit provisioning recommended.
- C: independent schema/lock/rollover and producer-ownership challenge completed.
- B: final HTTP hosted delivery audit; later ledger entry review only after that assignment releases.
- Lead: prepare this proposal, retain the HTTP delivery gates, and reconcile roadmap/backlog/issue changes only after review.

No ledger code, database migration, provider request, new resource or task-status advance is authorized by this draft. The primary checkout is reused for proposal documentation; the secondary remains frozen on the HTTP delivery source. Both remain independently removable and own their existing environments.

Before assigning implementation, verify: accepted AR-008-B delivery; reviewed lifetime/provisioning and manifest contracts; exact package boundaries and effort rollup; complete existing-consumer map; unchanged external gates; synchronized roadmap, task cards, machine ledger and issues. No successor implementation is scheduled before these prerequisites.
