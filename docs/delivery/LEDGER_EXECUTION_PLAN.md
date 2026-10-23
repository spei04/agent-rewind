# Ledger execution plan

2026-10-21 · Approved ledger execution plan. The original readiness review used HTTP source `a304d52b52667b882c70e922b73d7070d714efb0`; the current HTTP prerequisite is accepted at protected merge `cefd222230c800eb2e90c49a3b3c411b394d0393`.

**State:** The owner approved [proposal 882fa139](https://github.com/spei04/agent-rewind/blob/882fa139946dd31f401a5518a7b24750cbe88e25/docs/delivery/LEDGER_EXECUTION_PLAN.md), including the finite execution window and two sequential 3 [3–5] BE packages, total 6 [6–10], medium-low. P1 entry 51af77dc and HTTP delivery cefd222 are accepted. The lead assigned AR-010-A/P1 #108 to platform/security; P1, aggregate #107 and parent #10 are **In progress**. F1 dormant foundation is **Merged; checkpoint accepted** at 2e0eeeab; the full P1 package has no accepted product delivery yet. F2 is **Merged; checkpoint accepted** at e8cba52; [accepted evidence](#accepted-f2-reader-and-f3-handoff--2026-10-22) binds source ac3b0a31, exact PR/main attempts and verified candidate 12431486551. The lead explicitly started F3 on 2026-10-22 with the shared-check kernel first; F3 is **In progress** with null checkpoint acceptance. P2 #109 remains **Not started**; P2 waits for accepted full P1 and its own reservation/fence entry review. Both packages retain null acceptance. No public/native-v1 contract, ready-profile or external gate changes follow.

## Current P1 implementation sequence — 2026-10-22

The lead accepted a scope-preserving delivery refinement: three independently
reviewable implementation PRs inside the existing P1 acceptance package. This
keeps the approved finite window, exact entry, scope, effort and all final
gates. F1/F2/F3 are implementation identities, not new aggregate tasks or
acceptance packages.

| Implementation PR | Boundary | Entry and exit | Current state |
| --- | --- | --- | --- |
| F1 · [PR #111](https://github.com/spei04/agent-rewind/pull/111) | Dormant schema, owned operator and private guard foundation | Accepted HTTP/P1 entry; independent exact-source review, native regression proof and scoped PR/main/candidate acceptance | Merged; checkpoint accepted at 2e0eeeab; [evidence](#accepted-f1-foundation-checkpoint--2026-10-22) |
| F2 · [PR #114](https://github.com/spei04/agent-rewind/pull/114) | Complete bounded persisted reader | Accepted F1 plus exact query-family/native-plan review; complete provenance/financial/graph proof, maximum-state limits and scoped PR/main/candidate acceptance | Merged; checkpoint accepted at e8cba52; [evidence](#accepted-f2-reader-and-f3-handoff--2026-10-22) |
| F3 | Trusted provisioning, original opening, replay and recovery | Accepted F2; complete original P1 matrix including preservation, concurrency, privilege, child interruption and restore, then final protected-main candidate | In progress; explicit 2026-10-22 handoff, kernel first; checkpoint acceptance remains null |

[Assignable PR cards](../EXECUTION_BACKLOG.md#ar-010-a)
record exact inherited contracts, prerequisites, scope, tests and exit criteria.
Each PR inherits all P1 inputs; successors wait for accepted predecessor
checkpoints. F1/F2 merges cannot populate P1 accepted-merge/review fields, close
issue #108 or start P2. All three component records and the complete final P1
gate must pass before P1 acceptance is bound to the final F3 merge and review
record. P2 still requires its own entry; AR-010-B still waits for the whole
AR-010-A aggregate. No customer ar7 profile or public operator activation follows
from the foundation or reader.

The optional implementation_prs records validate structural source/merge/review
references and matching cards. A 40-character hash in JSON is not proof of a
real merge or passing remote checks. Independent review still verifies actual
source, PR/main attempts and protected candidate artifacts. Component records
use **Merged; checkpoint accepted** separately from package **Verified**.

Current PR forecast is **161**, including four for AR-010-A and six for parent
AR-010. There remain 151 tasks and 15 acceptance packages, with 544 outer edges.
P1/P2 each retain 3 [3–5] BE days, aggregate 6 [6–10]; base 464, upper 784.6,
alternative allowance 580, effort path 176.5, M1 65.5 and BE 97.5 are unchanged
estimate baselines, not new staffing or calendar promises. Component PRs do not
duplicate effort. Earlier dated 159/four-PR records below remain history.

Original hosted attempt [39724247038/1](https://github.com/spei04/agent-rewind/actions/runs/39724247038)
tested source d2c04f24 through merge a4eaf800. Python 3.11 passed 4431 tests with
32 skips and one existing warning in 1667.43 seconds; Python 3.12 passed 4442
with 21 skips and the same warning in 1730.67 seconds. Actual PostgreSQL,
package/final-container trust checks and three gVisor cases passed. Static
security failed on two source constructs; dependency audit was skipped and
the required CI gate failed. Main-only delivery was skipped. This is retained
failed-attempt evidence, not successful foundation delivery. The Python 3.12
job took 1780 of 1800 seconds. Reviewed correction c3e9fd0 raises only the core
job limit from 30 to 45 minutes and its existing test bound. All 87 CI workflow
and delivery checks pass on each interpreter; application deadlines and every
required check remain unchanged.

Correction 91f0742 and private guard ff65892 have independent internal source
acceptance. The guard selection passed 281 checks on Python 3.12.3 (26.70s)
and Python 3.11.17 (23.96s), with no skips or warnings. Database state was
restored and the server stopped before checkout handoff. These local results
are complemented by the [accepted F1 hosted and candidate evidence](#accepted-f1-foundation-checkpoint--2026-10-22); they alone did not establish delivery.
The complete internal reader is accepted by the F2 record below. Exact component
query plans and the combined schedule remain bound to that evidence; the
conditional 215-page graph bound alone does not prove implementation cost or capacity.
No partial LedgerState, hidden server-cursor FETCH or second work budget is
authorized. The dated checkpoints below retain their original state of knowledge.

## Security correction and guard handoff — 2026-10-22

Draft [PR #111](https://github.com/spei04/agent-rewind/pull/111) publishes the
reviewed schema/operator checkpoint at d2c04f24. Original attempt
[39724247038/1](https://github.com/spei04/agent-rewind/actions/runs/39724247038)
passed isolation and package checks but failed static security rules before
dependency audit; both core jobs remain pending at this checkpoint.

Reviewed correction 91f0742 renames a numeric parser argument and selects
between two complete literal SQL queries. Independent semantic probes confirm
unchanged lexical behavior and emitted SQL. No rule suppression, dependency,
test or workflow change. Full security rules, lint, formatting and types pass;
291 regressions pass with 42 expected skips and one existing warning.
Private peer review digest:
042897d8772d20b37ca9047457d286613b6776b724a193767ad699764c3967e9.

The next assigned internal checkpoint is the private transaction-body guard.
Platform/security reuses secondary from 91f0742; lead retains primary for
progress/publication, delivery prepares independent controls and planning owns
hosted evidence. The guard issues only after actual exclusion, verifies the
same native transaction and owned connection, then revokes before commit or
cleanup. Added PostgreSQL identity reads consume ordinary work within the
unchanged 2048 total. SQLite continuity remains a cooperative caller guarantee.

The complete reader remains under design review. Its new traversal must use
observed fixed-page reads because native server-cursor fetches bypass the
existing statement observer. Financial byte bounds, whole-reader query cost and
catalog text bounds need evidence before implementation acceptance. No partial
LedgerState success path is authorized. No new provider call or paid resource.
P1 remains In progress/null acceptance; P2 remains Not started.

## Operator native and lifecycle checkpoint — 2026-10-22

The lead and independent reviewers accept source
80023cbc057dabcef13e8ce760baed757fcfd56b for the bounded factory, work accounting,
transaction outcomes and lifecycle. Runtime remains the reviewed df55c1f;
the final lifecycle delta changes tests only. Private lead acceptance digest:
4e52e10bfd7693607bdaa90f98bb19050f33171d39445c8248f9a9f5b39aef3d.

Independent verification passed 100 SQLite/factory/lifecycle cases on Python
3.11.17 (3.29 seconds) and 3.12.3 (3.86 seconds), without skips or warnings.
The 21 new cases cover partial acquisition, callback/listener installation and
removal, both eight-control cleanup branches, observer failure/exhaustion and
later-generation callback survival. Native actions and fresh SQL reads are
observed separately from implementation accounting. Initial 13/8 and 20/1 test
attempts were fixture/expectation failures; their evidence remains retained.

Separate independent PostgreSQL evidence passed 131 cases together on Python
3.11 (79 SQLite/factory, 18 independent PostgreSQL and 34 prior PostgreSQL).
Python 3.12 passed an earlier 47-case selection, then all 18 expanded independent
cases. This is not one combined 52-case run. Logical BEGIN acknowledgment is
distinguished from native IDLE/INTRANS; lost commit acknowledgment remains
uncertain, and fresh connections verify actual effects.

Separate authored checks passed 41 SQLite cases per interpreter and 31 PostgreSQL
module cases per interpreter: 23 socket-backed cases, six pre-connect refusals and
two deliberately failed numeric/TLS controls. These are not 31 successful connections
or proof of successful TLS. Prior regressions passed 206 on Python 3.12 and 204 with
two intentional Python-3.12-API skips on 3.11. Authored wheel/source-archive proof
matched 124 runtime files; runtime bytes remain unchanged. Overlapping selections
are not a new full-suite result.

The exact three-database/fifteen-role baseline was restored and PostgreSQL stopped.
Lead owns primary for publication; secondary is free after independent verification.
Both cloud checkouts and their independent environments remain for reuse. No provider
call or new paid resource.

Next is review of a bounded non-owning reader under operator exclusion. Historical
ownership/creator provenance and current request authority remain distinct;
unresolved wider membership policy cannot be bypassed or called a complete audit.
Compatibility activation is separate. Actual provisioning, 245000 opening/backfill,
replay, concurrency, maximum-state inspection, child-death/owner-preserving recovery,
hosted checks, protected merge and candidate proof are still required. P1 remains
In progress/null acceptance; P2 stays Not started.

## Operator SQLite verification checkpoint — 2026-10-22

Corrected runtime df55c1fc3a574f66a2ad96ef924cc1e1710c022d is composed with
independent tests at 3716811ec2990398c6e09deec11118691b336c7b. The exact committed
source passes 79 independent SQLite and nonconnecting factory cases in 2.47
seconds: 14 transaction, 37 work-boundary and 28 factory checks. Separate authored
checks pass 41 cases. These results are not a combined full-suite or P1 result.

The expanded independent transaction run preserved four genuine failures: an inaccurate
BEGIN-attempt flag, artificial uncertainty despite acknowledged rollback,
replacement of the first interruption, and incorrect mapping of a native lock
timeout. Corrective source f4395ce also addresses the reviewed PostgreSQL adapter
context, pre-construction plugin rejection, server-major gate and final
check-before-release ordering. Subsequent native deadline controls showed BEGIN,
SELECT and COMMIT executing after their timeout setter exhausted the deadline;
reservation-delay controls exposed stale caps and a setter running after expiry.
Follow-up df55c1f reserves the whole bundle before obtaining caps, checks between
setters and before the target, and refreshes the second PostgreSQL lock cap.
Failed runs and native traces remain retained.

Independent native SQLite effects and fresh connection reads support the outcome
checks. The real ordinary-unit boundary is 2028 plus 12 prepaid startup/eight
cleanup units; prepaid allowance is not an observed SQL count. Nonconnecting
PostgreSQL factory controls do not establish native PostgreSQL behavior. The
full startup/cleanup matrix, both-interpreter proof, prior ownership/admission
regressions and full operator acceptance remain pending.

Platform/security owns native PostgreSQL and isolated Python 3.11.17 validation
in the existing secondary; the 3.12 environment is unchanged. PostgreSQL testing
uses the existing socket-only server after a verified 3-database/15-role baseline
with zero other clients. Independent QE prepares PostgreSQL verification while
the lead updates progress in the released primary; database use waits for
restoration, stop and explicit handoff. Delivery independently reviews source
and evidence. No new checkout, provider call, paid resource or partner data.

P1 remains In progress with null accepted-merge and runtime-acceptance fields.
Provisioning, the actual 245000 opening/backfill, replay, concurrency, recovery,
maximum-state inspection and hosted delivery remain required. P2 stays Not
started. Dependencies, estimates, staffing and external approval gates are unchanged.

## Operator slice assigned — 2026-10-22

The lead and independent reviewer accepted V3 of the operator design, digest
74bafbf8d60f9352b1d9f9fb854f476fe2692f1837c0ddb95ff90f129043765f,
for implementation. It conserves 12 prepaid startup units, eight prepaid cleanup
units and at most 2028 ordinary units within the existing 2048 ceiling. These
allowances are not claimed as observed SQL counts. One deadline, strict command
engine ownership and single-endpoint connection policy remain mandatory.
Commit attempt, acknowledgment and cleanup facts are separate; uncertain outcomes
cannot become completion. Actual native traces must validate the proposed bounds.

Platform/security owns the work/transaction/factory code in the reused secondary.
Independent QE owns separate startup/accounting/outcome/cleanup tests in the reused
primary after handoff. The author has the next exclusive PostgreSQL slot only
after verifying the restored, stopped baseline; QE waits for explicit release.
Delivery reviews the implementation and its evidence. The lead integrates reviewed
checkpoints. No provisioning/CLI activation is included in this first code slice.

Planning PR #110 is accepted at protected merge b304da1 with PR/main attempts
39691736070/39694886231 and independently verified candidate 12391249020.
The source wheel/archive match all 114 runtime members of that planning merge;
this does not prove the separately developed ledger implementation. All seven
main jobs passed; Python 3.11 recorded 3894 passes/14 documented skips and Python
3.12 recorded 3905 passes/3 documented skips. Prior failed evidence remains retained.

P1 and its aggregate remain In progress with null delivery acceptance. The full
opening/provisioning, replay, concurrency, recovery and capacity gates remain
required. P2 remains Not started. No budget, dependency, staffing or external
approval boundary changed.

## First schema checkpoint — 2026-10-21

Independent review accepted source `b2e19beaf8ca195c74a69871817ef96004f73444`.
Pure manifest/history verification previously passed 190 independent cases.
The actual schema run passed all 65 independent PostgreSQL cases; together with
the authored schema module, it recorded 107 passes and 18 explicit dialect
skips. The four scope-change/reversal bypasses found during review now refuse
at COMMIT, while no-op and unrelated-scope controls still pass. The original
failed evidence remains retained.

The corrected PostgreSQL capture changes only the constraint function body and
digest. Old literal profiles remain unchanged; all 209 prior migration
regressions pass. The local wheel and source archive match all 121 runtime
files. Native metadata tests prove refusal at 103,233 aggregate bytes while
every individual object stays below its limit; this is a rejection test, not
a capacity or performance result. PostgreSQL returned to its verified
three-database/fifteen-role baseline and was stopped after each exclusive slot.

The lead composed accepted planning merge `b304da1` with this checkpoint without
changing its source tree. Operator design review then found that cold database
startup bypasses ordinary SQL listeners and a callback-release retry was absent
from the proposed cleanup count. Platform/security revises those two bounds;
delivery reviews the source-based accounting and planning prepares fault tests.
No operator implementation is assigned until that internal review passes.

The full operator, 245000 opening/backfill, replay, concurrency, recovery,
maximum-state inspection and hosted delivery gates remain required. P1 stays
In progress, P2 stays Not started, and both delivery acceptance records stay null.

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

Approved planning total: **6 [6–10] engineering days**, replacing 3 [3–4.5] within the same aggregate. These are effort estimates, not staffing or calendar commitments. No new outer dependency or funding gate is added. The machine ledger computes 151 tasks, 161 delivery PRs, 544 outer edges, 464 base / 784.6 upper / 580 alternative allowance and 176.5 effort-path days; M1 is 65.5, BE 97.5 and parent AR-010 10 days/six PRs. The three implementation PRs refine P1 delivery without changing either approved package. Earlier proposal/estimate history remains auditable.

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

- Planning/verification: finalize accepted F2 progress, release primary and independently review F3 integration/evidence.
- Platform/security: implement the guarded writer/service, finalization and recovery in primary after progress release and reviewed kernel composition. Existing writer/compatibility native evidence remains component-only.
- Independent QE: implement the minimal shared-check kernel in secondary, then the compatibility adapter and independent native/recovery controls; retain the unchanged two-second deadline and verify old profiles under the new coherent snapshot.
- Lead: own policy, source integration and delivery; coordinate checkout/database ownership and require complete F3/P1 acceptance before P2.

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

## Accepted F1 foundation checkpoint — 2026-10-22

[PR #111](https://github.com/spei04/agent-rewind/pull/111) merged normally with
reviewed source `c6f32cdd2633d5022d4ebdbc78589920a7f3d9dc` at protected-main
merge `2e0eeeab45eb97c925454a7c9e23f2ddfcc47249`. The merge has the reviewed
source tree and unchanged required protection. Independent delivery review
accepted both exact attempts and the candidate archive.

| Evidence | Python 3.11 | Python 3.12 |
| --- | --- | --- |
| [PR run 39729061054/1](https://github.com/spei04/agent-rewind/actions/runs/39729061054) | 4561 passed, 32 skipped, 1 existing warning; 1817.93s | 4572 passed, 21 skipped, 1 existing warning; 1305.61s |
| [Protected-main run 39733331352/1](https://github.com/spei04/agent-rewind/actions/runs/39733331352) | 4561 passed, 32 skipped, 1 existing warning; 1093.68s | 4572 passed, 21 skipped, 1 existing warning; 1201.11s |

Durations are pytest durations. Skip totals match the source-bound interpreter
and dialect forecast; the existing warning is the Starlette/httpx deprecation.
Both attempts used the pinned PostgreSQL 16.15 service and actual database
opt-ins. Three actual gVisor cases, package/installed-service/HTTP smoke, locked
dependency audit, static security and the required CI gate passed. The exact
source Docker build and separate offline installed-image checks passed,
including the four-store CA identity proof. Protected-main delivery passed.

The reviewed verifier accepted artifact **12407151544**, **726324 bytes**,
archive SHA256
`746fd89d18ad35604ee92b6043352d0d6589bb4c9151cbc62ff7ed94af4d2479`.
It verified the exact candidate members and **124 runtime files** against the
reviewed Git source, wheel and source distribution. The durable release record
`reviewed-delivery-20261021-pr111-2e0eeea.json` has SHA256
`b28fd23a35b3b3e8cc02418912cf215898f44baf57bf73ef60489dcb03dbf1e8`.
Original failed run 39724247038 and all earlier failed attempts remain separate
retained evidence; no successful run replaces their outcome.

This accepts only AR-010-A/P1/F1. P1, AR-010-A and parent AR-010 remain
**In progress**; P1 accepted-merge/review fields remain null. F2/F3 remain
**Not started**, with no component source/merge/review acceptance. F1 satisfies
F2's predecessor gate, while exact query-family/native-plan and combined cost
review still precedes reader implementation. A2 native feasibility (15 cases
on each database dialect) and B2 native feasibility (43 on each) are partial proofs,
not complete reader or capacity acceptance. P2 remains Not started/null,
behind complete P1 and its own entry. No customer, production or spending gate
changes, new task, effort, dependency or PR allocation follows.

The lead updated and read back issues #10/#107/#108 on 2026-10-22 with this
F1 evidence; all remain open/In progress. Issue #109 was separately read back
open/Not started and was unchanged.


## F2 reader implementation entry — 2026-10-22

The lead accepted the complete dormant reader entry after independent exact
query/schedule review. Private entry identity:
9f9b34a48a1b9abeef52e49d623ef3cda7bcccec86beb7e17e70a614946bee2e.
F2 is **In progress**, with source/merge/review acceptance null. P1 remains
In progress/null; F3 and P2 remain Not started. This starts implementation,
not a product, maximum-capacity or customer-readiness claim. The canonical
entry is agent_rewind.migrations.ledger_inspection.inspect_ledger_state(Connection).

Catalog component evidence is separate: SQLite passed **36 cases**, observing
288/351 ar6/ar7 targets and one additional target in the injected fallback.
PostgreSQL passed **54 cases** after correcting the unquoted reserved alias
in the constraint gate, observing 119/141 targets on fresh/warm/restored paths.
The original alias-failure evidence remains retained. The conservative SQLite
420/564-target fallback allowance is source-derived, not measured worst-case
capacity. A2/B2/C2 partial evidence is reused; complete installed provenance,
financial/graph closure and actual operator-budget proof remain required.

New support conditions apply only to this dormant reader: four previously
unbounded historical SQLite timestamp cells have a native 64 KiB ceiling each
(262144 bytes together), preserving the original aware-time grammar; all
progress keys must be native TEXT within schema-derived 128/256-byte ceilings,
without an ASCII-only restriction or fetching unrelated bodies. SQLite fetched
partial-index SQL is bounded at 64 KiB; reflection-omitted physical indexes and
duplicate extra foreign keys refuse. Scoped main-table options follow
no-ATTACH/empty-temp checks. PostgreSQL rejects non-NULL comments, including
empty comments, only at the exact fetched joins. Existing wrappers and the
frozen P1 schema entry remain unchanged.

Implementation uses one issued Connection/LedgerWork, entry/final body guards
and observed fixed-page queries. SQL, setters, xids and fallback targets are
charged; pure loops check the deadline without consuming an extra work unit. Keep 2048 total units (12 bootstrap, 2028
ordinary, 8 cleanup), 120 seconds and 16 binds. The complete schedule pays
duplicate discovery/H00 and catalog prefixes until traced reuse exists.
The entry estimate used P=0 ordinary totals of SQLite ar6/ar7 676/816 nominal,
940/1242 conservative fallback, and PostgreSQL 535/628. The complete-reader
trace and source review below correct SQLite by two units; PostgreSQL is
unchanged. Each accepted graph page adds 4/6 units respectively. These
constructions do not prove executed capacity, and jointly incompatible maxima
cannot be combined.

Keep native storage, decoded UTF8 receipts and canonical bytes separate.
The original H10 1114625-byte and fixed nonledger 1443887-byte bounds are
unchanged and independently checked. PostgreSQL UTC wire text becomes an
aware datetime only after exact 27-byte format, receipt and round-trip checks,
before the unchanged H30/H60 validators; SQLite historical text remains raw.
Retain each existing JSON decoder. All ten financial gates and the shared
2 MiB native/canonical limits precede financial or graph-job bodies. Complete
history, source, scope, account, opening and chain closure must precede the
seven-field immutable LedgerState. No recursive old wrapper, current source
digest traversal, hidden server cursor or new budget is permitted.

Platform/security implements runtime in secondary after this documentation
handoff. Independent QE owns three new reader test modules in primary;
planning reviews integration and the lead owns delivery. Complete ar6/ar7
positives, original 245000 exposure, joint bounds and no-write/native faults
belong to this slice. Exact F2 PR/main/package/security/candidate acceptance
still precedes F3. Progress PR #112 merged at f39d2db with all seven main jobs
passing; its candidate verification was still running at this entry checkpoint.
No final artifact acceptance is inferred from those job results.


## F2 source and test handoffs — 2026-10-22

Runtime source **90ce9513bbafc74fa7f5e93246d08ddae913b7b7** freezes the
complete non-owning reader, nine bounded query/consumer modules, shared pure
historical reducers and the explicit 133-file distribution policy. The first
complete SQLite selection passes **20 tests** across fresh/legacy ar6 and
empty/organization/legacy-opening ar7. Fresh existing-caller regressions pass
**166 tests**; whole-repository format/lint, source security and type checks
pass. These are local checkpoints, not final F2 acceptance.

Independent QE source **fd4c9dc7fedd0ed6fc401c88cebcdd24100c9570** adds
evolving reserved/settled/released states, financial closure failures, transport
witness controls, a future-period regression and prepared LATIN1 coverage.
Its fixture-only selection passes 15 checks. The first composed independent
reader run records **69 passes, two failures and 11 PostgreSQL cases
deselected**. The two failures are retained: an invalid test role fails the
existing schema before inspection; a changed v2 job budget fails its immutable
admission association before the intended exposure check. QE owns the narrow
fixture/oracle corrections. All complete-state, evolving-state, future-period,
H10 receipt and SQLite no-write/guard tests in that run pass.

The complete trace observes P=0 ordinary work **678/818** on SQLite ar6/ar7.
The outer early-temp witness is additional to the component's early witness
and original catalog witness: one extra target costs two ordinary units.
Preserve the ordering and correct the source-derived conservative fallback
bases to **942/1244**. PostgreSQL remains **535/628**; graph pages add **4/6**
units. The total remains **2048 = 12 bootstrap + 2028 ordinary + 8 cleanup**,
with 120 seconds and 16 binds. No allowance is increased and no positive
maximum-capacity claim follows.

Independent source review, corrected complete test results, native PostgreSQL,
combined-bound evidence and exact PR/main/package/candidate delivery remain
required. F2/P1 acceptance stays null; F3 and P2 stay Not started.

## Accepted progress delivery after F1 — 2026-10-22

The earlier pending candidate for [PR #112](https://github.com/spei04/agent-rewind/pull/112)
is now independently accepted: reviewed source
**08bf372743a03c3a21140caee7b830561bed0ef1**, protected-main merge
**f39d2db892595b45aa4f234454c4d83d2e06ee63**. Exact PR/main runs
[39737515333/1](https://github.com/spei04/agent-rewind/actions/runs/39737515333)
and [39742506695/1](https://github.com/spei04/agent-rewind/actions/runs/39742506695)
pass. Main Python 3.11 records **4561 passed / 32 skipped** and Python 3.12
**4572 passed / 21 skipped**, each with one existing warning; the other
required native, isolation, security and delivery jobs pass.

Candidate **12411685094** is 726290 bytes, SHA256
`d74a7392759e727922c8712176eb9b1cd68a7a98ec43a64d9b990505d9d1bb74`.
The unchanged reviewed verifier confirms all 124 runtime files against the
source, wheel and source distribution. The first verifier invocation's
transient log-download failure remains retained; the successful invocation and
durable release record are separate. This delivery updates F1 progress only;
it contains no F2 runtime and cannot accept F2 or P1.


## F2 reviewed source and offline verification — 2026-10-22

Independent source review found missing cooperative deadline checks in pure
study/graph traversal and the separate financial descriptor-validation pass.
Correction **0ce4c3edc3525197adb354582a96425eaefbd985** adds those checks
without another work budget or changing SQL. Genuine failing regressions on
the prior source and passing corrected results remain recorded. Historical
callers retain their existing behavior when no check callback is supplied.

The real integration fixture contains 4097 valid jobs and scopes. Both Python
versions traverse 4096+1 job pages and all four terminal empty streams, using
524534 native financial bytes, 864631 canonical bytes and 686 total ordinary
units. A separate control spends the remaining work through 677 real SELECT
queries and refuses at 2028 ordinary units before returning any state. Final
reentrancy, changed connection options and expiry controls run after real graph
validation. This establishes representative paging and refusal behavior, not
maximum joint capacity or detection of hidden raw SQLite transaction changes.

Final offline composition **0638961b3f732b769a16358edea13d27d5bb0c91**
passes **267 tests on Python 3.12** and **265 on Python 3.11**, with two
intentional Python-3.12-only autocommit skips, 25 PostgreSQL cases deselected
and one existing warning per run. Repository formatting, lint, source security,
types, frozen offline build and package policy pass. All **133 runtime files**
match Git, disk, wheel and source archive. Collection contains 4715 cases on
each interpreter; two existing wall-clock-derived IDs differ between collections.
These results are a selected offline suite, not full hosted CI.

Independent SQLite evidence is separately staged: 78 passes at 11c12bc,
followed by two cleanup-order cases at 28f5685; the six new authored integration
cases also pass independently. Earlier fixture, oracle and style failures remain
retained. The initial pooled-connection test incorrectly required immediate raw
closure; the corrected test proves restored timeout, no transaction or checked-out
lease, unchanged rows before disposal and closure after explicit disposal.

The first complete-reader native attempt stops in its first write-witness case.
The native counter detects exactly three intended job updates, but the deliberate
ordinary rollback exception is mapped to the existing database-failure category.
Post-context assertions, the zero-row control and the reader phases do not execute.
The exact three-database/fifteen-role baseline is restored and the server stopped.
Reviewed test-only **5e92242937bf96024bf15479ee7589b8d220eaa5** changes only
that sentinel to a distinct interruption, preserving all assertions and avoiding
an error expectation that could mask earlier failures. The corrected matrix
contains 2 write-witness, 17 independent and 6 authored PostgreSQL cases.

Native traces, complete PostgreSQL outcomes, LATIN1 and exact UTF8 receipts,
then exact protected PR/main/package/candidate evidence remain required.
Independent native reports measure inspect-only work separately from charged
observation queries; the authored property records total ordinary work.
F2/P1 acceptance stays null. F3 and P2 stay Not started.


## F2 PostgreSQL bind repair and complete native checkpoint — 2026-10-22

The corrected write-witness controls both pass, followed by five fixture
histories. The first complete reader then exposes a product compatibility
failure: pinned SQLAlchemy PostgreSQL column reflection compiles **21 binds**,
so the existing **16-bind** guard refuses before its target native cursor call.
That compilation count is separate from observed native execution. The failed
attempt and exact restored/stopped release remain retained.

Reviewed repair **2bf335288d85133e4f4962218d0a2b47e086914b** replaces only
the new reader's PostgreSQL column observation with fixed literal SQL and one
bound table name. It returns at most 33 rows, refuses zero or more than 32, and
preserves observed names, native types, nullability and defaults through the
existing scalar and exact-profile gates. Unsupported generated, identity,
dropped, commented and type states still refuse. SQLite and historical caller
paths are unchanged. No query, time, bind or payload allowance is increased.

The repair's selected offline suite passes **124 tests on each interpreter**,
with 29 PostgreSQL cases deselected and no warnings. Formatting, lint, security,
types, frozen offline build and distribution checks pass; all **133 runtime
members** match source, wheel and source archive. This supplements the earlier
267/265 regression checkpoint; it is not a repeated full-suite claim.

A separate native observer records actual cursor calls, raw identity, parameter
counts and outcome without recording parameter values or changing arguments.
Its first native run returns the exact fresh-ar6 state, then the observer refuses
six pinned immutable parameter-map containers that it cannot yet count. The
remaining post-witness assertions and later cases were not reached. Test-only
**09cc3ba0d65e25408c7cc4d27c3d15834ba54411** recognizes that exact pinned
class, preserves unknown-container refusal and adds 16-bind acceptance and
17-bind refusal controls. Fourteen focused observer/CTE checks pass.

The corrected PostgreSQL 16.15 run at 09cc3ba passes all **29 selected cases**
on Python 3.12: 2 write controls (8.96s), 17 independent cases (66.08s), 6
integration cases (26.70s) and 4 catalog-drift controls (13.11s). There are no
selected skips or warnings. Complete fresh/legacy ar6 and three ar7 histories,
evolving reservations, LATIN1/UTF8 receipts, real paging, exhaustion, final
publication guards and default/type/comment/dropped-column drift are covered.
Every observed call in the nine shared complete/evolved-state positives uses
at most 10 parameters; that observation does not extend the observer's scope
to other test modules. The LATIN1 case observes 4 native bytes and 5 decoded
UTF8 bytes for its payload, not physical wire capture.

All phases restore the exact three-database/fifteen-role/zero-client baseline.
The final release proves PostgreSQL stopped with no PID, socket or socket lock.
Source bytes are unchanged across execution. The same 29-case Python 3.11 run,
final independent evidence audit and exact protected PR/main/package/candidate
checks remain pending at this checkpoint. Maximum joint capacity, F2 delivery,
full P1, provisioning and production readiness are not accepted by these local
results. F2/P1 acceptance stays null; F3/P2 remain Not started.


## F2 integrated byte-boundary review — 2026-10-22

The original 29-case PostgreSQL matrix also passes on Python 3.11 at
**93ef7d516e67048744834031f8028589829984a5**: 2 write controls (9.64s),
17 independent cases (68.07s), 6 integration cases (26.04s) and 4 catalog
drift controls (13.11s), with no selected skips or warnings. The exact baseline
is restored and PostgreSQL stopped. Source-equivalence review preserves the
separate Python 3.12 evidence at 09cc3ba.

Final acceptance review identified an additional requirement: the complete
PostgreSQL reader needed shared 2 MiB native and canonical boundary evidence.
Earlier component-bound checks and a representative 4097-job reader state
did not establish that integrated property. Five cases cover native CAP and
CAP + 1, canonical escaping expansion, and canonical CAP and CAP + 1. Native
overflow must refuse before financial body transfer. Canonical CAP must
return the exact complete immutable state; canonical overflow must refuse.

The first attempt failed during fixture construction because one payload
exceeded PostgreSQL's existing VARCHAR(64) limit. Test-only **c683cfd** replaces
that invalid fixture with individually valid zero-reserved v1 jobs and exact
scopes, retaining the original **245000 microUSD** opening. A complete
single-row control precedes scaled calibration. Actual ten-family receipts
and independent whole-array serialization establish the final byte sizes;
each payload remains at most 64 characters and total candidates stay below
the existing row limit. No schema, reader or allowance changes.

Twenty-five focused offline checks pass on each interpreter. In SQLite,
canonical CAP is exactly **2097152** bytes with **1189447** native bytes and
**12191** candidate rows; native CAP and CAP + 1 are separately observed.
The next PostgreSQL attempt at c683cfd reaches the expected native-CAP
reader refusal and passes its same-connection/zero-write checks, then fails
when the test accesses the exception context manager incorrectly. Later
postconditions and four cases do not execute. Test-only **8da2938** captures
the entered context and still requires identity with the original reader
exception; seven focused installed-pytest probes validate refusal and
non-refusal paths. Both failed native attempts are retained with restored,
stopped releases.

[PR #113](https://github.com/spei04/agent-rewind/pull/113) tracks F2.
Its original source 93ef7d5 passes hosted attempt **39763710972/1**:
Python 3.11 **4729 passed / 32 skipped** and Python 3.12 **4740 passed /
21 skipped**, one existing warning each; package, security, isolation and
CI gate pass. That result does not cover the subsequent boundary correction.
The corrected five-case PostgreSQL run at **8da2938121d0cd6cddb826d0c8f1add51e836ea5**
passes on Python 3.12 in **79.78s**, with no selected skips or warnings.
Native CAP is **2097152** bytes; native CAP + 1 is **2097153** and transfers
no financial bodies. The canonical-CAP positive returns the exact complete
state at **2097152** canonical bytes, **1199873** native bytes and **12051**
candidate rows. Canonical CAP + 1 and escaping expansion refuse while native
bytes remain below the cap. Every observed native call uses at most 10 binds;
maximum inspect-only work is 618 units and maximum total ordinary work is
667, including the separate counter observations and transaction setup.
Same-connection, no-write, rollback/commit, cleanup and unchanged-snapshot
postconditions pass. The exact database baseline is restored and the server
stopped.

The matching five-case Python 3.11 run, refreshed source inventory, replacement
PR checks and protected-main candidate remain required. These are separate
limit-enforcement proofs, not a promise that every combination of maximum
dimensions fits. F2/P1 acceptance remains null; F3/P2 remain Not started.

## F2 protected-main delivery remains unaccepted — 2026-10-22

The five additional PostgreSQL boundary cases also pass on Python 3.11 at
432bcbc in **81.63s**, without selected skips or warnings; the separate Python
3.12 run passed in **79.78s**. Final collection contains **4768 unique cases**
and the package retains **133 runtime members**. These complement the earlier
29-case native matrix, not a universal combined maximum-state capacity claim.

Exact source **432bcbc04dd83b3c1330e2a8042802929e2a2425** passed PR #113
attempt **39768849981/1**: Python 3.11 **4736 passed / 32 skipped / 1 warning**
in **2004.63s**, Python 3.12 **4747 passed / 21 skipped / 1 warning** in
**2088.87s**. Package, security, isolation and the PR gate passed. Normal
protected merge **08234c3796cf0ebeaa59ea1c0d1a2c325857551a** preserves that tree.

Protected-main attempt **39773689705/1** failed: Python 3.11 recorded **1 failed /
4735 passed / 32 skipped / 1 warning** in **1746.66s**; Python 3.12 passed
**4747 / 21 skipped / 1 warning** in **2072.88s**. The failure is the
nul-suffix variant of the malformed-order listing test, during its subsequent
valid continuation: observed SQL work was **2.0331571339997936 seconds**
against the existing two-second limit. Its malformed-value refusal, restored
value and released-connection checks had already passed. This does not
establish a reader implementation defect or a harmless infrastructure cause.
Package, security and isolation passed; the main gate failed, candidate
delivery was skipped and the run has no artifacts. Both complete job outcomes
and the original failed trace are retained.

The next delivery combines a separately reviewed test-only clock correction
with this progress update. Actual-query deadline and connection-reuse controls
remain required; no production timeout, work allowance or reader changes follow
from the test repair. F2 accepted-source/merge/review fields and full P1
acceptance remain null until fresh protected delivery and candidate verification.

F3 preparation remains separate from implementation: writer statement,
compatibility projection and recovery-rehearsal designs have scoped review;
writer feasibility passed **20 SQLite / 23 PostgreSQL** asserted component case groups with
restored/stopped release **1161b848**. This is not complete provisioning,
commit/replay, owner/ACL-preserving financial recovery or two-second compatibility
adapter proof. Compatibility controller cleanup corrections remain pending.
F3/P2 stay Not started; all approved scope, effort, dependencies and external
gates remain unchanged.

## Accepted F2 reader and F3 handoff — 2026-10-22

The complete internal persisted reader is accepted at source
**ac3b0a31edb1ff06393b12943eabd31e0ae232b5** and protected merge
**e8cba52f2979b9b8d2f2047de6856f82ba8e0502**. The final test-only correction
047a0f08 isolates eight malformed-order cases and adds actual-query continuation
controls below and at the unchanged two-second deadline, including connection
reuse. Its local selection passed 59 cases on Python 3.12 and **57 with two
predeclared Python-3.12-only skips** on Python 3.11. A reporting wrapper wrongly
expected zero skips after successful pytest; its failure and separate metadata
validation are retained, with no pytest rerun or product-test assertion change.

| Exact attempt | Python 3.11 | Python 3.12 | Remaining required jobs |
| --- | --- | --- | --- |
| PR #114 · 39780954252/1 | 4738 passed, 32 skipped, 1 warning; 1593.10s | 4749 passed, 21 skipped, 1 warning; 2022.52s | Package/container, security, three gVisor cases and gate passed; main-only delivery correctly skipped |
| Protected main · 39786131008/1 | 4738 passed, 32 skipped, 1 warning; 1999.91s | 4749 passed, 21 skipped, 1 warning; 1945.83s | All seven jobs passed, including candidate rebuild/upload |

Both cores exercised actual PostgreSQL. The one existing Starlette warning per
core and exact expected skip inventories remain recorded. Fresh collection binds
4770 unique cases. The original 29-case native matrix and five added complete
financial-boundary cases retain their separate source/interpreter identities;
this is bounded limit/refusal proof, not a claim that every joint maximum fits.

Candidate **12431486551** is **853440 bytes**, archive SHA256
**9dff927ab83464b63066126f121f2efa5f74942b419dfa078ac578372515c56f**.
The unchanged reviewed verifier accepted its manifest and **133 exact runtime
members**, independently rechecked against Git. Durable release record
reviewed-delivery-20261021-pr114-e8cba52.json has SHA256
**3f74e257d52532dc7c72a6bfeaf2594760816309435d8f31cba72ceba824338d**.
The first invocation stopped on SSH exit 255 before completing its source/merge
check (record d9f0d44b); the separate second invocation passed unchanged
(record b5aa94a7). Original PR #113 delivery and failed main 39773689705/1
remain separate history; no failed result is retroactively accepted.

The lead explicitly authorizes F3 implementation, kernel first, in the existing
build/test scope. Entry record 0e930256 binds this handoff. QE owns the shared-check
kernel then compatibility adapter in secondary; platform/security owns the
guarded writer/service, finalization and recovery in primary after progress
release and reviewed kernel composition. Planning reviews integration and the
lead owns policy, source integration and delivery. The lead updated and read back
#10/#107/#108 with accepted F2 and the F3 start; all remain open/In progress
with full P1 acceptance null. #109 remains Not started and was not changed.

Writer feasibility **20 SQLite / 23 PostgreSQL** asserted component groups and
compatibility projection **27 cases on each dialect** have scoped peer acceptance
after the reviewed cleanup corrections and restored/stopped database releases.
They do not establish the full adapter's two-second coherent lifecycle, complete
command capacity, real initialization-derived positive states, replay/uncertainty
handling or owner/ACL-preserving financial recovery. All original P1 gates remain.
F3 is In progress with null checkpoint acceptance; P1, AR-010-A and parent #10
remain In progress/null acceptance. P2 remains Not started. No ready profile,
customer activation, spending authority, effort or dependency change follows.


## F3 component integration checkpoint — 2026-10-22

The following components have source review and bounded local evidence. None is
full F3, P1, production or maximum-capacity acceptance.

| Component | Reviewed source and evidence | Remaining integration proof |
| --- | --- | --- |
| Counted original-source fingerprint | a50b11fb; all 40 statements match the frozen packet; 33 Python 3.12 SQLite cases pass | Python 3.11 and PostgreSQL consumer execution; both actual writer traversals and complete caller prerequisites |
| Private complete context | 36eee0e9; original full inspector pipeline preserved; 86 Python 3.12 cases pass with 11 existing JUnit invocation warnings | Actual service use and finalizer ordering; native integration |
| Coherent compatibility lifecycle | 63e069f7 resolves independently found native-autocommit rollback leak; original and corrected controls retained | PostgreSQL repeatable-read setup, native setters and cleanup; whole two-second lifecycle |
| Immutable compatibility adapter | b7f7ea4; eight exact projection statements; 180 Python 3.12 passes and 177 Python 3.11 passes/three explicit version skips, one existing warning each | Actual service-created ar7 states, PostgreSQL consumer execution and whole-history/account capacity |
| Pure intent preparation and writer SQL | 090d22c; independent review, 18 direct tests and 16 exact SQL/type records | Actual provenance/project receipts, service-created rows, native execution and whole-command bounds |

Compatibility success remains incompatible/migration_only, with no ready state
or operator rights. Its seeded histories validate immutable provenance, actual
accounts and original opening; they deliberately do not prove current balances,
calls, entries or graph health. Deadline tests use actual serialization followed
by controlled clock advancement, not elapsed wall-clock capacity evidence.

The lead integrates policy and progress in released secondary. Platform/security
owns service/native-test work in primary; planning reviews service/integration
evidence; QE prepares native/recovery controls without an active database hold. Full actual
initialization, provisioning, exact older replay, uncertainty, commit/cleanup,
owner/ACL restore and final protected PR/main/candidate gates remain required.
F3/P1 acceptance stays null; P2 remains Not started. No new spending, deployment
or partner-data authorization follows.


At composed source **8708b8f**, the combined selection passes **251 cases on
Python 3.12** and **248 with three explicit version skips on Python 3.11**,
one existing warning each. The unchanged backlog validator and 94 backlog tests,
full lint/format/security and type checking across 125 source files pass. Offline
wheel/sdist checks confirm all **141 runtime members** equal Git. A separate
corrected build uses the existing CI no-gitignore option after the first local
wrapper's extra-file refusal; both attempts remain recorded. No installed-package,
hosted-delivery, native PostgreSQL or full-capacity result is claimed.

Writer source **6bc02da** has independent API/replay and lead finalizer review.
Its separate 189-case selection includes 20 service controls: 15 actual SQLite
cases and five pre-checkout refusals. The legacy invocation records 1646 ordinary
work units under unchanged limits; 1910 SQLite trace callbacks include trigger
repetitions and are not an independent execute-attempt count. Full native,
recovery and protected delivery gates remain open. F3/P1 acceptance stays null;
P2 remains Not started.


## F3 native validation checkpoint — 2026-10-22

At **001e0bd**, **33 PostgreSQL compatibility cases pass** on Python 3.12 in
86.15 seconds: 22 new controls and 11 existing regressions, with one existing
warning. They cover complete seeded histories, deliberately corrupt immutable
projections, coherent metadata snapshots, deadline boundaries, rollback faults
and three actual service-created histories. Independent evidence reconciles
7,617 ordered driver receipts across 24 wrapper observations. The 30 new
projection calls use at most 16 binds; unchanged old-profile reflection remains
separately reported. Controlled-clock cases prove check placement, not maximum
elapsed capacity.

Service validation is assembled from **four passes at a6456ca** and **five
passes at 00e568a**. The first attempt stopped on a missing newline in a trace
assertion; the next reached four complete passes before the owner fixture
correctly triggered the earlier live-writer guard. The final fixture temporarily
disables only its original owner's LOGIN flag, restores it in a finally block,
and reaches the intended ownership refusal. All five unresolved cases then pass
in 26.94 seconds, including three post-write rollbacks and the actual deferred
constraint refusal. Neither failure was erased or relabeled as a passing run.
No runtime guard changed.

All native runs restored the same database/role baseline, reaped their test
processes and stopped PostgreSQL. Composition preserves all **141 runtime files**
from 8708b8f. These results are scoped Python 3.12 evidence; full matching
two-interpreter hosted delivery remains required.

Next work uses the two existing checkouts: independent actual S2 provisioning
adds both organization and project accounts, while QE measures complete adapter
capacity under the unchanged two-second limit. The existing later-provision
fixture adds only an organization account and does not close the S2 gate.
Concurrency, uncertainty, process death, owner/ACL restore, remaining boundaries
and protected PR/main/candidate acceptance stay open. F3/P1 remains In progress
with null acceptance; P2 remains Not started. No task, estimate, dependency,
spending or deployment gate changes.


## F3 provisioning and capacity checkpoint — 2026-10-22

Composition **5f575667** advances F3. The earlier a4007b0 checkpoint preserved
all runtime files; this checkpoint changes exactly **ledger_state.py** and
**ledger_inputs.py** in the runtime. Sorted adjacent-period checks replace
repeated scans while preserving immediate overlap refusal and deadline checks.
The parser trims only the four legal outer JSON whitespace characters after
unchanged raw-byte and BOM checks. SQL, transaction lifecycle, limits and the
migration-only profile remain unchanged.

| Evidence | Result | Scope |
| --- | --- | --- |
| SQLite provisioning at 5e73c863 | Eight passes on each Python version | Actual initialization, new organization and project periods, original columns/ciphertexts, older replay and cap refusal |
| Runtime capacity fixes at 16dfc7c3 | 337 focused passes on each interpreter | Independent writer-eligible seeded histories; complete already-connected SQLite compatibility inspection |
| Native provisioning | Two passes at 015ac758; six continuation passes at 42ec316a in 51.22 seconds | Actual S0→S1→S2, empty initialization, four cap refusals and two actual-service write-observer negatives |
| Native capacity preparation | Four SQLite regressions pass at 5a73c621; four native nodes collect on each interpreter at e4600298 | PostgreSQL execution, reviewed controller and exclusive grant remain pending |

The first capacity fixtures were reader-valid but had queued-v1 jobs that the
writer could not initialize. Those failed runs remain reader-capacity findings.
After eligibility was corrected, the 4,096-account fixture still timed out.
The period-search correction resolved that measured bottleneck; the parser
correction improved the separate trailing-padding fixture. At 16dfc7c3, the complete
SQLite inspection took **1.27 / 1.19 seconds** for 4,096 accounts and
**0.93 / 0.80 seconds** for a separate 16 MiB trailing-padding history on Python
3.12 / 3.11. One byte over refuses before history-body transfer. The two-second
limit is unchanged. These results cover the recorded shapes and host, not joint
maxima, arbitrary whitespace layouts or production sizing. Earlier failures of
a linear-scan-specific test remain recorded; its replacement checks expiry
during the actual bounded lookup and prevents subsequent insertion/projection.

The first native provisioning attempt failed after initialization because its
oracle expected canonical JSON text despite the writer's existing JSONB cast.
The corrected independent decoder compares canonical values, rejects duplicate
keys and nonfinite numbers, preserves boolean/number distinctions, and records
raw progress before assertions. Exact non-JSON fields and aware timestamps stay
unchanged; eight pure oracle controls pass. The next attempt passed the complete
provisioning/replay and empty-initialization cases, then stopped because the
no-write observer lacked two existing read-only project queries. The test-only
correction adds their exact digests and four hidden-update negative mutations.
Only the six unresolved cases ran afterward. Report **two prior passes plus six
continuation passes**, never a single eight-pass run. Both failures are retained.

The actual-service negative controls detect same-value and zero-row writes.
Cap refusals preserve the original 245000 exposure and native state. Independent
review verified typed progress values, exact non-JSON preservation and ordered
native receipts. Every native attempt restored the original database/role
baseline, verified unchanged source inputs and stopped PostgreSQL. Earlier
evidence remains separate: 33 compatibility passes and four service passes plus
five continuation passes.

Prepared native capacity cases cover the whole PostgreSQL runtime wrapper,
including checkout and cleanup. Earlier SQLite measurements start from an
already-connected entry; timings are not a controlled cross-database comparison.
Native fixtures retain exact JSON bytes and strict values, native non-JSON
cells, ciphertexts and owner/ACL/catalog state. Review removed a premature
preservation-report field; the remaining report follows actual comparisons.
Collection and SQLite regression results do not establish native capacity.

Next gates are native capacity, remaining writer boundaries, fresh inspection
after uncertain outcomes, concurrent operators, actual process death,
owner/ACL-preserving restore and matching two-interpreter protected
PR/main/candidate delivery. F3/P1/AR-010-A remain **In progress** with null
acceptance; P2 remains **Not started**. Task counts, estimates, dependencies and
funding/deployment/data gates are unchanged. This checkpoint made no provider
calls and created no paid resources.


## F3 recovery and native capacity checkpoint — 2026-10-23

This checkpoint composes recovery source 7eccb241 and the test-only
capacity correction ee2dc3e2. All runtime files and the lockfile remain equal
to 232130d. Earlier period/parser optimizations retain their separately bound
evidence; no new performance correction or full capacity acceptance follows.

### Actual SQLite recovery

The final 23-case Python 3.12 selection passes in **70.69 seconds**. It covers
original M0/M1 receipt recovery after actual S2, genuine absence at the exact
parent, changed intent, advanced parent, partial identity collisions and corrupt
current state. Initialization and provisioning each exercise failures before
physical COMMIT, loss after physical COMMIT acknowledgement, acknowledged
COMMIT followed by close failure, failures before/after native ROLLBACK, and
preservation of the first BaseException through a later cleanup interruption.
A failed writer returns no successful receipt. Every explicit recovery uses a
distinct engine and raw connection; no hidden writer retry is permitted.

The 35 observed commands include 23 fresh inspections with zero DDL/DML.
Before harness disposal, 10 cleanup-fault paths have physically closed and
quarantined their handles; 25 healthy paths have clean idle pool returns.
Actual C-level acknowledgements, transaction outcomes, original receipts and
independent SQL state are checked separately. Caller cleanup is labeled as its
own trace phase. Clean SQLite QueuePool return does not require physical closure.

The first run passed the same 23 cases in 70.25 seconds but checked final handle
closure after test-owned disposal. Review retained its state/outcome evidence
and corrected that attribution gap in the helper only. The final run rechecks
the shared observer; these are **23 cases rerun**, not 46 distinct passing cases.
All 463 source inputs remained unchanged during each run. Lint, formatting and
type checks pass. Native recovery and final matching Python 3.11 delivery are
still required. SQL snapshots on refusals do not claim a separate ciphertext
rehash.

### Native capacity result

| Attempt / source | Result | Evidence boundary |
| --- | --- | --- |
| Initial observer at 232130d | One failure; three unrun | The test confused 372 fetch observations with five SQL body executions. The wrapper returned migration_only in 1.38219s, but later strict preservation checks were not reached. |
| Corrected observer at ee2dc3e2 | Control passed in 1.40977s | One history body, five projection executions, 372 fetch observations transferring 319 accounts and 48 jobs; exact native rows, JSON values/bytes, owner/ACL/catalog and ciphertext preservation pass. |
| Same corrected attempt | 4,096-account positive failed at 2.01115s | The real whole wrapper returned schema_unavailable after the unchanged two-second deadline. The 16 MiB and one-byte-over cases were not run. |

The correction matches ordered exact SQL executions to parameter receipts,
separates them from fetch observations, retains row bounds and exhaustion
counts, and rejects missing/duplicated/reordered evidence in 12 offline controls
against the original trace. No SQL, product limit, parser, transaction behavior
or runtime file changed.

The failed maximum records ordered native SQL and rollback/close returns, with
no COMMIT. Its tuple-write delta and final strict preservation assertions were
not reached and are not claimed. Traces have no per-event timings; the failure
does not isolate product parsing, database time or observation overhead.
Diagnosis must precede an optimization or a separately reviewed diagnostic run.
A passing control and earlier already-connected SQLite timings do not close
this whole PostgreSQL capacity gate.

Both native attempts restored the exact database/role baseline, reaped their
children, verified unchanged source inputs and stopped PostgreSQL. The original
failed attempt remains immutable evidence. Two existing cloud checkouts are
retained for active recovery and capacity work; no provider calls or paid
resources were added.

F3/P1/AR-010-A remain **In progress** with null acceptance; P2 remains **Not
started**. Native recovery, capacity, process interruption, competing operators,
owner/ACL-preserving restore, remaining service boundaries and matching
two-interpreter protected delivery remain required. No task, estimate,
dependency, funding, deployment or customer-data gate changes.


## F3 native recovery and capacity diagnosis — 2026-10-23

### Native recovery component

At 7738aec6, **25 actual PostgreSQL cases pass on Python 3.12 in 207.34s**.
The bounded controller finishes in 213.42s. The selection includes 23 recovery
scenarios and two actual-write observer controls, rather than 25 zero-write
positives. All 37 command observations establish physical raw-connection
closure and claim release before harness disposal. Twenty-three fresh
inspections perform zero DDL/DML; the two negative controls detect same-value
and zero-row UPDATE attempts. Ordered SQL/parameter receipts, physical
COMMIT/ROLLBACK returns, logical acknowledgements, the first interruption
object and original persisted receipts are checked independently.

Fresh inspections use separate owned engines/connections, validate complete
current state and do not retry the writer. Explicitly malformed fixtures are
not writer-produced state; their temporary trigger bypass is restored on the
same physical session after COMMIT. The close-acknowledgment fault cases inject a logical close
error after actual physical closure; this is not proof of recovery from a
sustained native close failure. Refusal snapshots do not claim a separate
ciphertext rehash. RC2 process death/concurrency and RC3 restore remain separate.

Independent review verifies 465 unchanged source inputs, 28,822 ordered SQL
receipts and the exact stopped database/role baseline. The accepted native
proof is at 7738aec6; SQLite's 23-case corrected run remains separate at
7eccb241. Final matching Python 3.11/3.12 delivery is still required.

### Exact optimization and unsuccessful native capacity continuation

At 54844ac, a compiled character-range check replaces the repeated Unicode
category loop in strict JSON string validation. Every Unicode code point
matches the prior rejection predicate on Python 3.11 and 3.12. All **312
focused tests pass on each interpreter**, including actual-validator key/value,
escaped JSON, scalar-type and depth controls; lint, formatting and runtime
type checks pass. No validation pass, input/work limit or deadline changes.

| Native attempt / source | Result | Evidence boundary |
| --- | --- | --- |
| Initial observer, 232130d | One failure; three unrun | Fetch receipts were mistaken for SQL executions; final preservation was not reached. Retained separately. |
| Corrected observer, ee2dc3e2 | Control passes at 1.40977s; account maximum times out at 2.01115s; two cursor cases unrun | The failed maximum has no final tuple-write delta or strict-preservation result. |
| Exact predicate optimization, 54844ac | Control passes at 1.63709s; account maximum times out at 2.00466s; two cursor cases unrun | Control completes strict preservation. The maximum transfers all 4,096 account and 48 job rows plus five projection exhaustion receipts, but returns schema_unavailable under the unchanged two-second deadline. |

The last attempt's failed maximum still has a null tuple-write delta and
unreached final strict-preservation assertions. Transferred rows, rollback/close
returns and eventual baseline restoration do not replace those assertions.
Isolated parser timings improved, but they do not prove native capacity or
attribute the residual time to product parsing, database work, CPU contention
or observation overhead. The existing process-wide profiling observer is a
specific diagnostic concern, not an established cause. Further native timing
requires a separately reviewed proposal; no automatic retry is authorized.

The new recovery and capacity runs both reap their children, restore the
exact baseline, verify unchanged run inputs and stop PostgreSQL. Failed
attempts remain immutable evidence. Composition f09c727 contains the reviewed
native recovery tests and optimization; its runtime and uv.lock match
54844ac, while the native recovery execution remains bound to 7738aec6.

### Remaining delivery work

The provisioning engineer next owns RC2 process interruption and competing
operators after the integrated-base handoff. The capacity engineer owns
bounded diagnosis of the unresolved native timeout. RC3 owner/ACL-preserving
restore follows when a checkout is free; remaining actual-writer boundaries
and matching protected PR/main/candidate checks remain required. The same two
cloud checkouts are reused. No provider calls, paid resources, customer data
or deployment were added.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Task counts, estimates, contract
and dependency records, funding and production gates are unchanged.

## F3 SQLite process-death checkpoint — 2026-10-23

Source 80704bd adds four test-only files; runtime and uv.lock remain unchanged
from the reviewed ce82a2c composition. **Four actual SQLite process-death cases
pass on Python 3.12 in 20.58s**. The bounded runner exits successfully in
22.36s. Eight final-source IPC controls pass separately in 0.10s.

Initialize and provision each run in a fresh process, stopped immediately
before physical COMMIT or after its actual return but before the service
publishes a response or cleans up. The parent validates a nonce/PID-bound
socket message, sends SIGKILL and verifies exit -9, reaping and channel EOF.
A fresh physical connection then completes BEGIN EXCLUSIVE and ROLLBACK,
proving the killed process no longer holds the SQLite lock. No journal file
is removed by the harness; SQLite performs any required native recovery.

Both pre-COMMIT cases reproduce the exact predecessor state. Both post-ACK
cases preserve the complete expected committed state and original receipt.
All four fresh inspections perform zero application DDL/DML and preserve
original source projections and all 18 protected ciphertexts per case.
Application zero-DML inspection does not imply that native hot-journal
recovery performs no file writes.

Independent review verifies 470 unchanged source inputs and all 138 retained
evidence files. Observed frame payloads are 2,424,817–2,762,051 bytes under the
4 MiB cap; child lifecycles are 2.38–2.64s under the 35s work plus 10s cleanup
bound. The first source review caught a cursor-close/connection-close
conflation before execution. The two earlier source snapshots are unexecuted
preparations, not failed crash-test attempts. Only the corrected source was
used for the four-case run.

This accepts the SQLite part of RC2a only. PostgreSQL process death,
competing operators and RC3 owner/ACL-preserving restore remain open. Native
RC1's 25 passes remain bound to 7738aec6. The latest uninstrumented native
capacity attempt at 54844ac remains one pass, one timeout and two unrun
cases. A private timing diagnostic preserves all observers and the
two-second deadline; its completeness checks are being reviewed before
any execution. Diagnostic timings cannot be adjusted by subtracting guessed
observer overhead.

The provisioning engineer next owns the PostgreSQL counterparts, then
competing operators as a separate slice. The capacity engineer owns timing
diagnosis; the independent reviewer checks each frozen source and result.
Remaining actual-service eligibility, arithmetic, identity, evolved replay,
fault, capacity and authority boundaries retain their original criteria.
Pure helper tests and seeded reader fixtures do not satisfy writer gates.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Matching protected PR/main/candidate
checks are still required. The two existing cloud checkouts are reused; no
new paid resources, provider calls, customer data or deployment were added.
Task counts, estimates, dependencies and external gates are unchanged.

## F3 PostgreSQL process-death checkpoint — 2026-10-23

Source 291ff467 adds three test-only files. Integration ddb8f278 combines
those files with the accepted observer change; the native execution remains
bound to 291ff467 and production code and uv.lock are unchanged. **Four actual PostgreSQL
process-death cases pass on Python 3.12 in 44.57s** in one execution. They
cover initialize and provision immediately before physical COMMIT and after
its actual return, before the service publishes a response or cleans up.
The earlier four-case SQLite result at 80704bd and 25-case native RC1 result
at 7738aec6 remain separate evidence.

Each case binds the child PID and nonce to the actual backend identity,
database, role and transaction phase. Before COMMIT, the backend holds the
required exclusion locks; after COMMIT returns, it is idle with those locks
released. SIGKILL, exit -9, reaping and channel EOF precede natural backend
and lock disappearance. Administrative cleanup does not supply the recovery
success condition. Fresh inspection then verifies the exact predecessor or
expected committed state, original receipt, protected ciphertexts and zero
application DDL/DML.

The bounded controller also passed a process-only timeout control: it
discovered a previously unclaimed adopted worker, killed and reaped it
through owned pidfds, left an unrelated process alive and restored the prior
subreaper setting. The earlier preparation and focused control correction
are not extra native attempts. All source inputs remained unchanged; the
database baseline was restored and the server stopped without cleanup errors.

Capacity remains open. The completed additive diagnostic at 54844ac retained
the original failure while passing its coverage checks; its nested timings
are not a causal decomposition or an adjusted capacity result. Independently
reviewed test-only source 1a0ab2c skips unused cell scanning when the transfer
observer has no targets, after unchanged row/EOF accounting. All 33 focused
controls pass on each interpreter, including existing text/bytes substitutions.

The subsequent ordinary four-case attempt has **one pass, one timeout and
two unrun cases**. Its control completes in 0.783569s with strict preservation.
The 4,096-account case times out at 2.005614s after fetching all account/job
rows and EOFs; its tuple delta is null and final strict preservation is
unreached. This does not establish maximum capacity. No observer, deadline
or assertion was removed, and no retry was performed.

The provisioning engineer next owns competing-operator recovery. The capacity
engineer now owns one scoped optimization: precompute fixed projection field
metadata once per read, retaining every per-row validation and deadline check. Owner/ACL-preserving restore and the remaining actual-writer
eligibility, arithmetic, identity, evolved replay, fault, bound and authority
gates remain open. Pure helper tests and seeded reader fixtures do not satisfy
writer gates.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Final protected PR/main/candidate
checks are still required. The two existing cloud checkouts are reused. No
new paid resources, provider calls, customer data or deployment were added;
task counts, estimates, dependencies and external gates are unchanged.

## F3 seeded reader capacity checkpoint — 2026-10-23

Source eb2cbc4 hoists fixed projection field metadata once per read, while
retaining every row validation, query and deadline check. All 281 focused
controls pass on each supported Python version. Of these, 249 exercise the
actual projection reader; the same 249 also pass against the exact parent
implementation. Whole-project lint, formatting, type and contract checks
pass. This is the only production change in this capacity continuation.

One ordinary PostgreSQL attempt on Python 3.12 passes all four cases with the
original two-second deadline, observers and preservation assertions:

| Case | Whole wrapper elapsed | Result |
| --- | --- | --- |
| 319-account control | 0.828335s | migration_only; full preservation passes. |
| 4,096-account maximum | 1.976373s | migration_only; full preservation passes. |
| 16 MiB cursor | 1.092626s | migration_only; full preservation passes. |
| Cursor one byte over | 0.517268s | schema_incompatible; no history or projection body fetches; full preservation passes. |

All four record empty tuple-write deltas, exact protected state and ciphertext
preservation, transaction rollback and physical connection closure. The source
inputs remain unchanged; the controller reaps its children, restores the exact
database/role baseline and stops PostgreSQL without cleanup errors. Independent
review binds the result to this source and controller. Earlier failed attempts
remain retained and are not converted into passing evidence.

The maximum passes with only about **24ms of headroom**. This is one execution,
not a repeatability, throughput or general performance result. The cursor
positive uses trailing padding; it does not cover every legal whitespace
distribution. These are seeded reader fixtures, not service-created maximum
history, simultaneous maximum dimensions or actual writer capacity. Matching
Python 3.11/3.12 protected PR/main/candidate delivery is still required.

The provisioning engineer owns RC2b1 identical competing commands in primary.
The capacity engineer moves to RC3 owner/ACL-preserving restore preparation
after handing secondary to the lead for integration. The independent reviewer
continues source and evidence review. Remaining actual-service eligibility,
arithmetic, identity, evolved replay, fault, bound and authority gates retain
their criteria; this component does not close F3 or P1.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Both existing cloud checkouts are
reused. No provider calls, paid resources, customer data or deployment were
added; task counts, estimates, dependencies and external gates are unchanged.

## F3 SQLite competing-command checkpoint — 2026-10-23

Source f4ba97c9 adds four test-only files. The first fail-fast execution passes
both actual SQLite cases—initialize and provision—in 28.18s on Python 3.12.
The bounded controller completes in 31.121s. The separate corrected protocol
selection passes 22 controls; it is not another execution of the real cases.

Each case proves the manifest and requested account identities are absent,
then holds the first real command after final validation and before physical
COMMIT. A second process submits the identical command. Its native SQLITE_BUSY
maps to migration_busy, it performs no application DDL/DML, and it cleans up
only its own connection and process.

Before releasing the winner, the harness verifies that its recorded held
state is unchanged and that a separate BEGIN EXCLUSIVE still receives
SQLITE_BUSY. The winner then commits exactly once. A third fresh process
replays the original request, returns the exact original receipt and performs
zero application DDL/DML. Exact resulting state, original source projections
and protected ciphertexts are preserved.

Independent review verifies the nonce/PID/intent-bound exchange, physical
transaction observations, source inputs, child reaping and empty cleanup
errors. Review first caught an expired-cleanup path that could omit KILL.
The corrected helper still signals its owned child after expiration, uses
only a zero-time wait, and retains an unreaped/closed=false state if it cannot
confirm cleanup. Its control labels the later harness reap separately. The
original preparation remains retained; neither preparation was a failed
real-case execution.

This accepts only SQLite identical-command recovery. PostgreSQL counterparts
and the separate identity-collision cases remain open, along with restore,
remaining actual-writer boundaries and protected delivery. Capacity's earlier
four-case PostgreSQL pass remains bound to eb2cbc4, with about 24ms maximum
headroom in one execution; no repeatability claim is added.

The provisioning engineer next owns PostgreSQL identical-command cases.
The restore engineer owns the two same-cluster S0/S2 restore positives and
their offline controls. The lead and independent reviewer retain composition,
evidence and delivery responsibilities. Both existing checkouts are reused.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Task counts, estimates, dependencies,
funding, customer-data and production gates are unchanged.

## F3 PostgreSQL competing-command checkpoint — 2026-10-23

Source 351c1c66 adds the native identical-command counterpart to the accepted
SQLite component. The first native attempt failed the initialize test before
the loser ran; provision was unrun. Its held-winner trace contains a successful
same-connection `SET CONSTRAINTS ALL IMMEDIATE\n` after final classification.
The observer expected the string without its trailing newline. Correction
4bc9a1dc strips only outer whitespace, preserving the exact statement content,
raw connection, uniqueness and ordering requirements. The runtime is unchanged.

The exact runtime statement reproduces the assertion failure offline before
the correction. Fifteen focused controls then pass: three accepted whitespace
forms, seven different-statement refusals and five duplicate, missing,
wrong-connection or ordering refusals. The earlier 47 SQLite/native protocol
controls remain separate evidence. Reinterpreting the retained held witness
does not turn the failed native attempt into a pass.

The corrected native attempt passes both initialize and provision in **30.36s**
on Python 3.12. The controller completes in 33.963s. Each scenario has three
fresh command processes and 12 completed messages; observed group durations
are 8.825s and 8.475s within the shared 60s work plus 15s cleanup limit.
Maximum payloads are 2,877,052 and 3,226,423 bytes, below 4 MiB; frame sizes
include four additional bytes. All six command processes exit normally and
are reaped with channel EOF.

For each actual absent intent, the winner holds exclusion after final proof
and native constraint validation, before physical COMMIT. The second command
attests the actual false `pg_try_advisory_xact_lock` fetch on its owned raw
connection and backend, then returns `migration_busy` and closes only its own
resources. Independent observations prove that the loser's exact backend and
locks disappear naturally while the winner's identity and exclusion remain.
The winner then commits once. A fresh explicit replay returns the original
receipt without application DDL/DML; exact state, predecessor data, owners,
ACLs and protected ciphertexts are preserved.

Independent review reconciles the six final command observations, 8,446 trace
events and 4,175 ordered SQL receipts. It accepts both case outcomes and the
restored/stopped database release separately from source/controller review.
The accepted private result index is 1b7d8f9e, peer index 1e46b276 and stopped
release cf49d163. The earlier zero-pass result b1814a91 and release 239bfbbb
remain unchanged. Native evidence binds exact source 4bc9a1dc; subsequent
documentation composition is not another native execution.

The composition preserves published progress 079a80ec and both test commits.
Its focused offline selection collects and passes 62 SQLite/native protocol
and observer controls in 2.50s; 94 backlog consistency tests also pass.
Full configured Ruff and formatting checks pass. One JUnit
record_property/xunit2 compatibility warning remains recorded. Runtime and
lockfile bytes match the published progress base; no actual native case is
rerun for documentation integration.

Before native execution, controller review also caught cleanup that could
skip owned-process signals after deadline expiration and timer setup that
could extend an aggregate deadline. The corrected runner signals only proved
pidfds, attempts nonblocking reaping after exhaustion and retains unresolved
ownership instead of claiming release. Two real process controls and four
clock controls pass; their earlier preparation records remain retained.
Neither preparation correction changes a service deadline or counts as a
failed native test. The final two-case controller retains 240s child, 450s
work, 275s normal cleanup and 850s outer limits.

The next separate contention slice is RC2b2: distinct well-formed intents with
different manifest IDs that collide on account/period identity. It must prove
actual busy refusal while the first command holds exclusion, then a fresh
conflict with the second intent explicitly bound to the current committed
parent. Include distinct projects sharing an organization; stale-parent
refusal alone is not identity-conflict evidence. This is a proposal, not an
implemented or accepted slice.

Restore remains separate. Its original S0 failure/S2 unrun are retained.
Factory correction dfe7b95b is independently accepted with 100 offline controls
per interpreter, including nine new controls. The corrected native attempt
reports S0 passed and S2 failed at a cross-model receipt comparison; component
success is false. Its result and reported stopped release 101868ca await
independent/root acceptance. A narrow S2-only observer correction is next;
no further native retry or whole restore acceptance is implied.

Remaining writer/privilege/deadline boundaries and final two-interpreter,
packaging, hosted and protected-candidate delivery also remain open.
Capacity's four seeded-reader passes at eb2cbc4 retain only about 24ms maximum
headroom in one run, with no repeatability or broader performance claim.

F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null
acceptance; P2/#109 remains **Not started**. Counts, estimates, dependency
edges, budget and customer-data/production gates are unchanged.

## F3 owner/ACL-preserving restore positives — 2026-10-23

RC3a's two same-cluster positive cases are independently accepted, with separate
executed source identities. The restore branch now composes published progress
4933da5c through ordinary merge d0f59733; this composition is not a new native run.

| Native attempt | Executed source | Retained outcome | Private result index / stopped release |
| --- | --- | --- | --- |
| First two-case attempt | fc3842fc | S0 failed; S2 unrun | c346b9b6 / 8b3c9de2 |
| Corrected runtime-engine attempt | dfe7b95b | S0 passed; S2 failed | e627a71d / 101868ca |
| S2-only receipt-contract continuation | 83c594a2 | S2 passed; S0 not rerun | bf7946fe / 174c1328 |

The first failure was a test factory mismatch: runtime inspection received an
operator engine requiring a migration claim. The normal bounded runtime factory
correction preserves that guard and the strict incompatible/migration_only
verdict; 100 focused controls pass per interpreter. The next failure compared
an inspection receipt directly with the provisioning result that adds outcome.
The S2-only correction requires the exact two model types, complete outcome,
all 11 declared receipt fields with strict value types, and no extra/missing
fields; 117 focused controls pass per interpreter. Both full receipt values
are retained before comparison. Neither failed native attempt was relabeled.

S0's accepted case restores the actual ar6 predecessor, then performs real M0
initialization. S2 restores actual M0/M1 state and replays both original commands
with their original receipts/timestamps and zero-write observations. Distinct
fresh inspections recover every receipt field without writer work. S2's final
attempt reconciles six ordered observations, 11,196 native events and 5,507 SQL
receipts. The full native test's S0 path and its runtime/fixture inputs remain
unchanged by the S2-only correction; S0 evidence remains at dfe7b95b, not the later source.

Each accepted case uses actual custom pg_dump and transactional pg_restore with
owners/ACLs retained. Source-derived rows, raw progress, owner/ACL grant identities,
function/trigger associations, all 18 ciphertext objects and source preservation
pass. All ten application-role DML/schema/function probes return native 42501
and roll back without state changes. Runtime compatibility stays migration_only.
S2's restored, replayed and final target snapshots are identical. The controller
reaps its owned children, restores the exact database/role/membership baseline
and stops PostgreSQL with no cleanup errors.

Independent S0 review is 73ec628a; S2/positive-component review is 07716611.
Lead acceptance 4a696c36 follows fresh stopped verification of release 174c1328.
These private hash identities refer to retained owner-only evidence, not public
artifact downloads. The scope is existing synthetic roles in one cluster with
default database ACLs; arbitrary column/default privileges, global-role
recreation and cross-cluster disaster recovery are not established.

Next restore work is the approved RC3b1 single truncated-archive negative:
actual native failure with no partial user objects and unchanged source.
Interrupted data-only restore and explicit provenance/ACL corruption remain
separate later slices. Distinct-intent collisions and the remaining actual-writer
eligibility, arithmetic, identity, evolved replay, fault, bound and authority
gates remain open. Final matching two-interpreter, packaging, hosted and
protected-candidate delivery remains required.

The earlier four-case seeded-reader capacity result remains bound to eb2cbc4:
1.976373s for the maximum-account case, about 24ms headroom in one run, with no
repeatability or broader performance claim. F3/P1/#108, aggregate #107 and parent
#10 remain **In progress** with null acceptance; P2/#109 remains **Not started**.
Task counts, estimates, dependency edges, budget and external gates are unchanged.
The two existing cloud checkouts are reused; no provider calls, paid resources,
customer data or deployment were added.
