# Ledger execution plan

2026-10-21 · Approved ledger execution plan. The original readiness review used HTTP source `a304d52b52667b882c70e922b73d7070d714efb0`; the current HTTP prerequisite is accepted at protected merge `cefd222230c800eb2e90c49a3b3c411b394d0393`.

**State:** The owner approved [proposal 882fa139](https://github.com/spei04/agent-rewind/blob/882fa139946dd31f401a5518a7b24750cbe88e25/docs/delivery/LEDGER_EXECUTION_PLAN.md), including the finite execution window and two sequential 3 [3–5] BE packages, total 6 [6–10], medium-low. P1 entry 51af77dc and HTTP delivery cefd222 are accepted. The lead assigned AR-010-A/P1 #108 to platform/security; P1, aggregate #107 and parent #10 are **In progress**. P1 has no accepted product delivery yet; P2 #109 remains **Not started**, waiting for accepted P1 and its own reservation/fence entry review. Both packages retain null acceptance. No public/native-v1 contract, ready-profile or external gate changes follow.

## Current P1 implementation sequence — 2026-10-22

The lead accepted a scope-preserving delivery refinement: three independently
reviewable implementation PRs inside the existing P1 acceptance package. This
keeps the approved finite window, exact entry, scope, effort and all final
gates. F1/F2/F3 are implementation identities, not new aggregate tasks or
acceptance packages.

| Implementation PR | Boundary | Entry and exit | Current state |
| --- | --- | --- | --- |
| F1 · [PR #111](https://github.com/spei04/agent-rewind/pull/111) | Dormant schema, owned operator and private guard foundation | Accepted HTTP/P1 entry; independent exact-source review, native regression proof and scoped PR/main/candidate acceptance | In progress; no accepted checkpoint merge |
| F2 | Complete bounded persisted reader | Accepted F1 plus exact query-family/native-plan review; complete provenance/financial/graph proof, maximum-state limits and scoped PR/main/candidate acceptance | Not started; traversal design remains held |
| F3 | Trusted provisioning, original opening, replay and recovery | Accepted F2; complete original P1 matrix including preservation, concurrency, privilege, child interruption and restore, then final protected-main candidate | Not started |

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
do not replace fresh hosted source checks, protected merge or candidate proof.
The full reader remains unaccepted: the corrected conditional graph bound is
215 pages, but exact observed query plans and combined costs are still required.
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

- Planning/verification: hand off the frozen refinement and prepare source-bound hosted inventory and CI evidence; no runtime or database changes.
- Platform/security: independently review the private candidate verifier and bounded native read controls; F2 query design and implementation remain gated.
- Delivery reviewer: author and test the private candidate-verifier correction while preserving exact runtime identity, archive and delivery gates; independent review precedes use.
- Lead: independently review the refinement, compose and publish reviewed sources, keep database/checkouts under explicit ownership, update public issue/PR scope and require full P1 acceptance before P2.

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
