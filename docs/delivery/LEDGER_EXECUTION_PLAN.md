# Ledger execution plan

2026-10-21 · Approved ledger execution plan. The original readiness review used HTTP source `a304d52b52667b882c70e922b73d7070d714efb0`; the current HTTP prerequisite is accepted at protected merge `cefd222230c800eb2e90c49a3b3c411b394d0393`.

**State:** The owner approved [proposal 882fa139](https://github.com/spei04/agent-rewind/blob/882fa139946dd31f401a5518a7b24750cbe88e25/docs/delivery/LEDGER_EXECUTION_PLAN.md), including the finite execution window and two sequential 3 [3–5] BE packages, total 6 [6–10], medium-low. P1 entry 51af77dc and HTTP delivery cefd222 are accepted. The lead assigned AR-010-A/P1 #108 to platform/security; P1, aggregate #107 and parent #10 are **In progress**. F1 dormant foundation is **Merged; checkpoint accepted** at 2e0eeeab; the full P1 package has no accepted product delivery yet. F2 is **In progress** under the [accepted implementation entry](#f2-reader-implementation-entry--2026-10-22), with null checkpoint acceptance. F3 and P2 #109 remain **Not started**; P2 waits for accepted full P1 and its own reservation/fence entry review. Both packages retain null acceptance. No public/native-v1 contract, ready-profile or external gate changes follow.

## Current P1 implementation sequence — 2026-10-22

The lead accepted a scope-preserving delivery refinement: three independently
reviewable implementation PRs inside the existing P1 acceptance package. This
keeps the approved finite window, exact entry, scope, effort and all final
gates. F1/F2/F3 are implementation identities, not new aggregate tasks or
acceptance packages.

| Implementation PR | Boundary | Entry and exit | Current state |
| --- | --- | --- | --- |
| F1 · [PR #111](https://github.com/spei04/agent-rewind/pull/111) | Dormant schema, owned operator and private guard foundation | Accepted HTTP/P1 entry; independent exact-source review, native regression proof and scoped PR/main/candidate acceptance | Merged; checkpoint accepted at 2e0eeeab; [evidence](#accepted-f1-foundation-checkpoint--2026-10-22) |
| F2 | Complete bounded persisted reader | Accepted F1 plus exact query-family/native-plan review; complete provenance/financial/graph proof, maximum-state limits and scoped PR/main/candidate acceptance | In progress; entry accepted, complete implementation/delivery pending |
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
are complemented by the [accepted F1 hosted and candidate evidence](#accepted-f1-foundation-checkpoint--2026-10-22); they alone did not establish delivery.
The full reader remains unaccepted. Exact component query plans and the combined
schedule are reviewed at the F2 entry below; the conditional 215-page graph bound
does not prove complete implementation cost or capacity.
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

- Planning/verification: independently review frozen reader integration and acceptance coverage; preserve null F2/P1 acceptance and dated evidence.
- Platform/security: maintain the complete dormant F2 reader/runtime in secondary, compose reviewed independent tests and resolve integration findings under the exact query and work schedule.
- Independent QE: own only new tests/ledger_reader_fixture.py, tests/test_ledger_reader_independent.py and tests/test_ledger_reader_native.py in primary; validate complete states and native boundaries against immutable runtime handoffs.
- Lead: review/integrate source and independent evidence, coordinate exclusive database ownership, maintain public issue scope, and require scoped F2 delivery then full F3/P1 acceptance before P2.

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
