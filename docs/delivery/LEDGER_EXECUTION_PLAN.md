# Ledger execution plan

2026-10-21 · Approved ledger execution plan. The original readiness review used HTTP source `a304d52b52667b882c70e922b73d7070d714efb0`; the current HTTP prerequisite is accepted at protected merge `cefd222230c800eb2e90c49a3b3c411b394d0393`.

**State:** The owner approved [proposal 882fa139](https://github.com/spei04/agent-rewind/blob/882fa139946dd31f401a5518a7b24750cbe88e25/docs/delivery/LEDGER_EXECUTION_PLAN.md), including the finite execution window and two sequential 3 [3–5] BE packages, total 6 [6–10], medium-low. P1 entry 51af77dc and HTTP delivery cefd222 are accepted. The lead assigned AR-010-A/P1 #108 to platform/security; P1, aggregate #107 and parent #10 are **In progress**. P1 has no accepted product delivery yet; P2 #109 remains **Not started**, waiting for accepted P1 and its own reservation/fence entry review. Both packages retain null acceptance. No public/native-v1 contract, ready-profile or external gate changes follow.

## Problem and intended result

New paid work needs one durable integer reservation at organization, project and job levels. A retry must recover the original logical call without granting another dispatch opportunity. Uncertain old obligations must continue to constrain new admission.

The existing `Database.reserve` increments a job counter. It does not implement hierarchical accounts, immutable account periods or generation fencing. The legacy worker uses owner and process/Python time; its job-first lock acquisition cannot be extended by acquiring a project afterward.

Consume the [frozen C04 contract](M1_CONTRACT_FREEZE.md#relational-closure-fences-and-accounting), [logical model](../../contracts/proposals/m1.data-model.json) and [AR-010-A card](../EXECUTION_BACKLOG.md#ar-010-a). The source contract remains authoritative.

## Approved planning decisions and exact-entry obligations

| Decision | Approved boundary | Reason / remaining review |
| --- | --- | --- |
| Trusted account provisioning | Explicit internal operator manifest identifying existing organization/project/jobs, account IDs, UTC periods and integer caps | Validate ownership from SQL. Compute opening holds from original data, never caller-supplied amounts. No public provisioning route or account creation during reservation. |
| Job lifetime | One finite, immutable authorized execution window supplied by trusted provisioning | This is the owner-approved interpretation of C04's fixed job lifetime, not an observed completion interval. Neither a retry, claim, generation nor billing rollover renews it. Missing historical bounds refuse provisioning; do not invent timestamps. |
| Window expiry | Refuse new claims/reservations and later dispatch outside the window; retain all existing obligations and original IDs | Early completion leaves the recorded window unchanged. Reconciliation may occur afterward through its future authorized producer. The later live worker must consume the persisted bounds. |
| Automatic deadline policy | Defer a new automatic admission-policy producer | Existing mutable `max_job_seconds` starts at each worker claim. Reusing it would change its meaning. The exact public SubmitRun and native-v1 configuration have no lifetime field and remain unchanged. |
| Rollover | Keep balances and call account IDs in their original periods; include prior outstanding held exposure in new organization/project admission | A blanket refusal for any old hold is insufficient as complete rollover acceptance. Stable scope exclusion and bounded complete exposure reads must prove the result; overflow or unprovable history refuses. |
| Opening exposure | Copy original `jobs.reserved` exactly once, aggregate once per level, retain the gross compatibility counter | No fabricated provider calls, receipts or invoices; historical fixture exposure remains 245000 microUSD. A cap below exposure refuses rather than silently increasing the cap. |
| Provisioning exclusion | Acquire the appropriate stable organization/project scope before downstream jobs/accounts | Sorted existing account IDs alone cannot serialize simultaneous absent-period inserts. No late shared-to-exclusive lock upgrade. Freeze every explicit and implicit FK/trigger wait. |
| SQL execution support | Exact, revision-specific PostgreSQL trigger/function inventory and literal dialect profiles | C04 requires deferred relational checks. Earlier profiles must continue rejecting extra executable objects. Never allow arbitrary functions/triggers to make a catalog pass. |
| Live activation | Keep migration-only compatibility and reserve-only internal services | AR-010-B owns actual worker/permit/cancellation integration. This plan enables no provider calls or customer readiness. |

The owner settled the authorized-window meaning on 2026-10-21; no repeated semantic approval is required. It is not actual first start through eventual completion. Changing to that different lifetime model would require an explicit contract amendment; it is outside this plan. P1 trusted bounds, authority, storage and transition policy was independently accepted at 51af77dc; exact implementation/catalog/recovery evidence is still required. P2 retains its own later reservation/fence entry review.

The operator manifest must have a reviewed exact schema, canonical digest, authority model, size/cardinality bounds and replay/conflict semantics before implementation. Entry review also freezes schema and function-body/security/search-path/privilege/profile policy and the preservation/restore matrix. Implementation then produces exact DDL and literal dialect catalog captures; independent comparison against the reviewed policy is a delivery-acceptance gate, not a requirement to have implemented captures before code. Job-account limits must not expand the unchanged job budget. Historical and newly created jobs need explicit producers; absence of one is an unavailable path, not a fallback to mutable settings.

## Approved two-package delivery

The two approved packages retain AR-010-A and its sole outer prerequisite AR-008-B, now Verified. P1 is In progress under the explicit runtime handoff; P2 is Not started and waits for accepted merged P1 and its own exact entry. Both acceptance records remain null. AR-010-B consumes the whole accepted aggregate, not early schema availability.

### P1 — Ledger schema, trusted provisioning and opening backfill

- **Objective:** Represent scoped accounts, logical calls and evidence-backed entries without rewriting historical meanings.
- **Scope:** One additive linear revision after ar6; the three frozen ledger tables; job lease-generation and legacy-reservation fields; explicit provisioning manifest and exact opening migration. Update both catalog inspection and migration exclusion coherently for the new 20-table profile. Add only the reviewed PostgreSQL deferred constraints/functions with exact definitions, enabled state, owner/security/search-path/privilege expectations. Preserve literal SQLite and PostgreSQL profiles, restart/restore behavior and migration-only compatibility.
- **Out of scope:** HTTP changes, automatic deadline policy, new public/native-v1 fields, live worker claims/dispatch, settlement/release commands, transfers, invoice ingestion or new incident tables.
- **Prerequisites:** Accepted AR-008-B protected-main delivery, the approved lifetime interpretation, exact schema/provisioning/interface review and supported-source inventory.
- **Contracts:** C04 account shape, immutable call account triple, original periods, unique entries, same-call/project evidence closure and opening exposure; existing operator migration/backup/restore contracts.
- **Acceptance:** Every old field/row/ciphertext is preserved except explicitly declared additive backfill. Opening exposure is copied once and caps below it refuse. Fresh, resumed and restored states agree. A completed profile accepts only its reviewed relational/executable objects; drift and unsupported states refuse before customer activity.
- **Tests:** Historical 245000 fixture; missing/conflicting manifest identities; cross-project/null-shape/period overlap; simultaneous absent-period provisioning; wrong/extra/disabled triggers/functions; deferred commit rejection; same-call evidence constraints; restricted runtime DDL denial; pre/post-commit interruption and exact restore on actual PostgreSQL.
- **Security/reliability:** No supplied opening balance, generic executable-object allowance or silent cap increase. Preserve old-profile rejection. Failed migration must leave a diagnosable resumable state or confirmed rollback, never a ready profile.
- **Effort/role:** BE 3 [3–5] days, medium-low confidence; PL/QE/security review. Executable catalog and absent-period serialization are the principal uncertainty.
- **Done:** Independently reviewed entry policy followed by implementation-generated exact DDL/literal profile captures compared against that policy, migration and restore proof, matching hosted checks, accepted merge and candidate verification. P2 waits for this evidence.

### P2 — Integer reservations, minimum generation fence and rollover proof

- **Objective:** Make concurrent reserve-only calls conservative, idempotent and compatible with accepted admission/read/cancel behavior.
- **Scope:** Connection-bound claim/fence and existing-account reservation primitives; immutable logical-call identity; call/scope/three-entry publication and three-level balance updates in one transaction; gross job counter; prior-period exposure checks; scoped recovery of an uncertain original call.
- **Out of scope:** Live ChatPolicy replacement, network dispatch, cancellation refunds, invoice reconciliation, transfer production, broad lease/process recovery and automatic account creation.
- **Prerequisites:** Accepted AR-008-B and accepted merged P1 plus complete lock/interface review against actual consumers.
- **Proposed internal interfaces:** `claim_generation(connection, scope, owner, lease_policy) -> JobFence`; `require_live_job(connection, scope, expected_fence)`; `reserve(connection, scope, fence, intent, account_ids) -> ReservationRecord`; separate scoped inspection after uncertain acknowledgement. Exact signatures, exceptions, units and bounded SQL behavior must be frozen at entry.
- **Identity contract:** Intent binds logical-call ID, project/job, request digest, purpose, amount, price version and account triple. Exact repeats recover existing state; changed bindings conflict. Neither recovery nor a reservation record is a fresh dispatch permit.
- **Lock/time contract:** Preserve project(s), organization/grants/key, original scope/job and sorted account order. Choose any stronger organization exclusion before downstream acquisition. Refresh database time after waits; compare owner/generation/running state/cancel and persisted execution window. Increment generation only on successful claim. Do not wrap legacy job-first transactions and then acquire a project.
- **Acceptance:** No cap can be exceeded by concurrent work or period rollover; no call is counted twice at one level; old holds and original IDs survive. Reject booleans, floats and out-of-range integers. Preserve `jobs.reserved = legacy opening + gross new reservations`, including after future evidenced release. Unknown commit preserves identity/hold and never creates new work.
- **Tests:** Eight-way shared-cap contention; different projects sharing an organization; nonoverlap and outstanding prior holds at rollover; repeated/conflicting logical calls; signed-64-bit boundaries and 2**53+1; wait-time expiry/cancellation/generation change; rollback at each write stage; lost acknowledgement; physical connection cleanup; unchanged admission, operation GET and cancellation behavior. PostgreSQL must execute the concurrency/deferred-constraint claims.
- **Security/reliability:** No external I/O in SQL, no estimate treated as invoice truth, no ambiguous retry/refund, no implicit settings fallback. Unsupported settlement/transfer paths retain exposure and remain unavailable.
- **Effort/role:** BE 3 [3–5] days, medium-low confidence; TL/QE review and independent PostgreSQL tests.
- **Done:** Independent source/test review, local and hosted actual-database evidence, installed package proof, accepted merge/candidate and all AR-010-A criteria. Full C04 and M1 acceptance remain separate.

Approved planning total: **6 [6–10] engineering days**, replacing 3 [3–4.5] within the same aggregate. These are effort estimates, not staffing or calendar commitments. No new outer dependency or funding gate is added. The machine ledger computes 151 tasks, 159 delivery PRs, 544 outer edges, 464 base / 784.6 upper / 580 alternative allowance and 176.5 effort-path days; M1 is 65.5, BE 97.5 and parent AR-010 10 days/four PRs. Earlier proposal/estimate history remains auditable.

## Evidence and future producer ownership

| Obligation | Current slice representation | Runtime producer / later owner |
| --- | --- | --- |
| Account/call/entry relational constraints, integer balances, openings and rollover exposure | AR-010-A schema and reserve path | AR-010-A; integrated M1 proof in AR-012-B |
| Worker dispatch transition, cancellation/expiry uncertainty and unchanged holds | Fence interface only | AR-010-B, with broader process/lease drills in AR-017 |
| Authentic receipt, charge and non-charge vocabulary | Evidence-reference closure does not establish financial authenticity | AR-023-A |
| Durable external dispatch/response/unknown evidence | No invented invoice producer | AR-023-B |
| Audited idempotent settlement/release, over-quote handling and breached-account freeze | Store required shapes; successful unsupported reconciliation stays unavailable | AR-023-C consuming AR-023-A/B |
| Historical opening-hold adjustment and actual period/account transfer | Retain exposure and original identity; no fabricated call-owned evidence | Existing AR-023-A and AR-023-C cards/tests now explicitly own this evidence contract and later audited command; representation remains an entry decision before those paths activate |

The final row closes the card traceability gap; it does not authorize a new account-transfer table, fake provider call or reverse prerequisite. The current `budget_evidence` ownership model is call-owned; imported opening exposure intentionally has no provider call. Authentic representation and a durable producer must be frozen by the later owner.

Over-bound billing must eventually retain the evidence and block further dispatch. AR-023-C already owns over-quote reconciliation and breached accounts. Before any such evidence-ingestion path is enabled, its producer/migration must provide durable block state and repeated-dispatch denial proof. AR-010-A's reserve-only completion must not claim that this later capability exists.

## Assignment and dependency review

- Planning/verification: finish independently reviewed progress reconciliation, then author the separately owned fixture/adversarial/limits/provisioning/constraint/catalog/recovery tests after runtime interfaces are stable and the lead releases ownership.
- Platform/security: own P1 runtime in the existing secondary checkout, work/ledger-schema, from accepted planning 9f6ea6e; first produce immutable bounded manifest/progress parsing plus explicit ar7 DDL and literal SQLite/PostgreSQL catalog evidence. Retain the sole coordinated PostgreSQL slot until baseline restoration and process release are proved.
- Delivery reviewer: independently review ledger source, integration and actual delivery evidence; accepted HTTP audit remains predecessor evidence.
- Lead: integrate reviewed runtime/tests, coordinate checkout and PostgreSQL ownership, maintain issue read-back and require the full P1 acceptance matrix before P2 handoff.

The historical first-fortnight schedules and opening conditions remain unchanged. Accepted HTTP and exact P1 entry satisfy the implementation prerequisites; the lead has issued the P1 handoff. No new calendar allocation or staffed-time conversion follows from the effort totals.

Implementation entry is satisfied by accepted HTTP and independently accepted P1 policy at 51af77dc. Product delivery still requires exact manifest/bounds/replay behavior, DDL/catalog, deferred constraints/privileges, lock-order, maximum-state and outcome/recovery evidence against that policy. Worker dispatch remains AR-010-B; authentic settlement/opening/transfer producers remain AR-023-A/C. No provider request, paid resource, customer data or ready profile is authorized by this handoff.

## Accepted P1 entry policy — 2026-10-21

A and the lead accepted the [exact schema/provisioning entry](LEDGER_SCHEMA_ENTRY.md) at source 51af77dc2bf3527e496f0123c6bee17882f56b4a. B and the lead independently accepted the 24-case PostgreSQL 16.15 privilege feasibility evidence bound to original design source f3af95ef. It proves only the tested two-table/one-trigger invoker seam. Installed triggers executed for the no-EXECUTE control; table/column privileges and invoker SELECT are the supported DML controls. No runtime revocation claim relies on function EXECUTE. The exact database/role baseline was restored and the instance stopped.

Return values, cursor/native types and fixed refusals are explicit. Non-owning inspection returns a persisted receipt without claiming commit/cleanup, while initialize_ledger returns complete only after its own acknowledged/replayed result and confirmed cleanup. Initial and later-provision uncertainty have separate bounded absence proofs, and each call requires its own same-project scope at commit. All actual product constraints/catalogs/max-state bounds/outcome/restore evidence remain implementation gates. P1/P2 and aggregate remain Not started/null acceptance pending accepted HTTP delivery; no new approval, spending or customer-data authority is inferred.

## Earlier predecessor security gate — 2026-10-21

The corrected HTTP PR matrix passed at a439, but [GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62) requires updating the pinned uv build tool and verifying its official checksum/provenance. Ledger implementation still waits for reviewed patched HTTP delivery, matching protected-main checks and candidate acceptance. This does not reopen the approved finite-window decision or the accepted P1 entry policy.

## Accepted HTTP prerequisite — 2026-10-21

HTTP P2 is Verified at cefd222 after exact PR/main attempts 39683408934/39686498691 and verified candidate 12387716715; see [accepted evidence](OPERATION_HTTP_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). The earlier security gate and failed attempts above remain history. P1 entry 51af77dc needs no repeated approval. This ordered checkpoint leaves ledger packages Not started/null acceptance pending the explicit assignment; actual constraints, privileges, maximum bounds and recovery remain product evidence to build.

## Explicit P1 runtime handoff — 2026-10-21

The lead assigned platform/security to AR-010-A/P1 #108 in the existing secondary checkout, work/ledger-schema, from published planning 9f6ea6e after accepted HTTP delivery. Aggregate #107 and parent #10 are In progress; #109 remains Not started. The lead read back those issue states on 2026-10-21. P1/P2 accepted merge and review evidence remain null.

Planning/verification owns independent test modules after accepted progress reconciliation and stable runtime interfaces; runtime and test file ownership are separate. First checkpoint is immutable manifest/progress parsing and explicit ar7 DDL/literal catalogs, followed by the complete provisioning, historical opening, privilege, constraint, bounds and recovery proof. Parser-only or synthetic privilege feasibility evidence cannot complete P1. Existing profiles and earlier acceptance records remain unchanged; P2 and worker work retain their original gates.
