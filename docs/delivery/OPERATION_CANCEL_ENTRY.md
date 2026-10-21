# Cancellation Operation service entry

2026-10-21 · AR-008-B/P1 [#94](https://github.com/spei04/agent-rewind/issues/94).

This is the next separately reviewable service slice. Runtime implementation
requires acceptance of the corrected cancellation receipt helper and this
entry, followed by an explicit lead assignment. A recorded plan or a helper's
passing tests is not whole-service acceptance. P1 remains In progress and P2
remains Not started.

The [adapter entry](OPERATION_ADAPTER_ENTRY.md),
[HTTP execution plan](OPERATION_HTTP_EXECUTION_PLAN.md), and accepted
[GET entry](OPERATION_GET_ENTRY.md) remain authoritative. GET source
`28d47cc9ad1d704ebe00a2c1b339f034c53162e6` is the service baseline.
Helper `d89752241049b6b19941f821fed98bec1f9eb9e2` has a reproduced
caught-active-read failure-latch defect and is not an acceptable implementation
dependency. Record the accepted correction and composed source in the
assignment log before runtime work.

## Scope and interfaces

Extend the existing OperationService with:

```python
def cancel_operation(
    self,
    principal: VerifiedPrincipal,
    context: ProjectContext,
    operation_id: str,
) -> CancellationView: ...
```

CancellationView has exactly three required fields: operation_id (the original
validated operation identity), cancel_requested (true), and status (queued,
running, succeeded, failed or cancelled). Capture the response from the locked
mutation: queued becomes cancelled; the other four statuses are preserved.
Return that captured intent response after disclosure checks and cleanup,
even if a worker subsequently advances the stored status. Keep the accepted
bounded canonical response check. Do not apply GET's failure-evidence support
table: a natively valid failed job with bounded legacy error text is cancellable
without parsing or exposing that text.

Allowed runtime changes are focused cancellation methods/helpers in
operation_service.py and a private same-Connection effect/audit extraction in
scoped_actions.py. Add dedicated SQLite and actual PostgreSQL tests and a narrow
implementation-guide update. Preserve the public
ScopedActions.cancel(principal, context, job_id) -> None API, transaction
ownership and behavior, including its existing callers and tests.

The private effect helper receives the already validated current job status,
original job ID, principal and pre-generated audit ID. It owns no transaction,
authority lookup, resource closure, status reread or retry. On the caller's
Connection, issue one jobs UPDATE (cancel=true; status=cancelled only when
queued) and one fixed job.cancel audit insert for the current actor. Return
the captured status or focused value needed by the service. Generate the audit
identity before locks. Preserve result, error, owner, lease, budget and reserved
amounts. Repeated intents may repeat the existing audit semantics; they never
refund, reserve, dispatch or claim worker completion.

No route, schema, packaged readiness profile, dependency, worker, provider,
artifact loader, storage access, reservation, refund or general mutation
framework belongs in this slice.

## Shared ownership and normal request sequence

Use exactly one OperationWork and one CancellationReceipts owner for a valid
identifier. Every SQL scope shares the original named-project context and
remaining counters. All authority calls omit resource arguments: this service
supplies its own complete budgeted original-resource proof.

Principal validation, owned SQLite provenance and real runtime compatibility
inspection follow GET's reviewed ordering. Compatibility completes before
OperationWork attaches. Real migration-only/incompatible state fails closed;
future-profile fixtures are instance-local and cannot change packaged guards.

Each of the three normal phases encloses acquisition through complete cleanup;
the mutation phase remains active through commit acknowledgement and release.
A phase failure aborts the owner. Never catch a bounded read/decode/retention
failure inside a phase and retry it, start another phase on a failed owner,
replace the owner, reset work, refresh an original receipt or reuse a sealed
book. Keep phase-local mutable receipts in focused function scopes and release
them between phases. Retain only original identity/association and the captured
response outside those scopes.

1. **Preflight, read-only.** Check fresh original-project read authority.
   Read the original operation14 and its actual scoped job16. Establish
   independent primary visibility, then check current cancel permission.
   An accessible viewer gets 403 for an existing visible target; a missing or
   foreign target remains 404. Read the job-owned admission_config descriptor
   and validate configuration, original creator and operation/job association.
   Associate the phase and read the complete scoped by-job root cohort.
   Perform the one final phase verification, followed by a fresh cancel
   authority check as the last protected SQL. Complete read cleanup.

2. **Locked mutation.** Use admission_transaction with the same work and a
   single outcome record. Call lock_authority without resource arguments:
   project UPDATE, organization SHARE, membership SHARE, and key scope/key
   SHARE where applicable. Then lock the original job's scope SHARE and job
   UPDATE using lock_resource. Lock the scoped operation SHARE by the original
   operation ID plus original project only. Never join or lock through a
   substituted current operation.job_id.

   Freshly read operation/job/configuration/cohort into this phase's book;
   match the original immutable association and perform one final phase
   verification. Check fresh cancel authority on this same Connection,
   without resource arguments, after the locks and relational verification.
   Run the pure disclosure-feasibility check below immediately before the
   effect. Execute the one effect and audit, and capture the bounded response.
   Do not compare the old full job16 after this intentional write, replace
   originals with its result or reread status through a separate connection.
   Remain inside the phase through commit acknowledgement and cleanup.

3. **Disclosure, read-only.** Create the next fresh phase on the same owner
   and work. Check fresh project read authority and independent original
   primary visibility; read the current operation/job/configuration/cohort,
   validate the original immutable association and perform one final phase
   verification. Check current cancel authority as the last protected SQL.
   Valid worker status, lease, reserved amount, job result and root-cohort
   advancement between phases are allowed when the new bounded phase remains
   valid and fits the shared budget. Return the previously captured response
   only after confirmed cleanup and work.finish.

All cancellation phases ignore result artifact references and perform zero
loader calls. Full current job16 is still checked within each phase; ignoring
artifact refs is not permission to omit job.result from that phase's native
row receipt. Configuration selection filters role=admission_config before its
bounded cardinality limit.

Use the GET primary-visibility semantics: observe presence of the original
operation in the original project and the original job with its original
project/job scope. Do not require the current operation.job_id to equal the
original job in that presence query. Reassociation is a secondary receipt
mismatch, never an invented missing-resource 404 or authority to cancel the
replacement job.

## Disclosure feasibility before effect

Under mutation locks, after verifying the current cohort and immediately
before effect/audit, compare remaining cumulative source visits and edges with
one fresh job plus every current root and two edges per root for disclosure.
This is a pure feasibility check, not a charge, reservation, refund, guarantee
against future growth, or permission to widen caps.

A stable 85-root case has consumed 172 visits after two phases and has 84 left,
but needs 86: refuse before effect, audit or commit and complete known rollback
and cleanup. A stable 84-root case has consumed 170 and has 86 left, needing 85,
so it fits. The helper's existing three-phase budget behavior is unchanged.

Later cohort growth, native budget exhaustion, authority change or cleanup
failure can still prevent disclosure after an acknowledged effect. Preserve
the finite uncertainty/typed-denial behavior; never retry the mutation.
Required evidence includes both stable 85 roots with zero effects/audits/
commits and a previously feasible late-growth case with one committed effect
and outcome_uncertain.

## Malformed identifier precedence

Keep the strict CancellationReceipts constructor unchanged. After principal,
engine ownership and real compatibility checks, privately capture only the
pure operation-identifier validation failure. Do not catch arbitrary
constructor, context or programming failures as malformed identifiers.

Only for a malformed identifier, enter one operation_connection with the same
OperationWork and original named-project context. Check project read authority
without resource arguments, finish cleanup, then raise ResourceNotFound
from None. Do not check cancel permission here: an accessible viewer's
malformed or missing target is 404. Invalid identity, revoked/foreign project,
schema, SQL and cleanup failures retain their earlier precedence.

This exceptional path performs zero operation/job/cohort/ref reads, row locks,
storage, audit or effects. Valid identifiers construct the strict receipt owner
before acquisition and follow the three normal phases. No sentinel identity,
deferred mutable owner or broader constructor API is needed.

## Failure and authority ordering

Classify a secondary failure only after the failed SQL scope/transaction has
completed cleanup. Preserve independently captured original IDs outside the
failed receipt owner. Do not query an aborted PostgreSQL transaction or create
a new owner, Work or replacement association merely to classify the failure.

When the original job ID is known, use at most one fresh same-work scope:
project read authority, independent original primary visibility, then current
cancel authority. With no established original job ID, recheck project read
authority only; never invent a target or re-read a replacement association.
Only after that check emit the original fixed dependency/uncertainty
classification. Typed identity, visibility and action denials retain their
precedence, including after commit; their presence does not assert rollback.
A typed denial from the original operation is preserved directly.

| Boundary | Result |
| --- | --- |
| Real migration-only/incompatible guard | schema_incompatible; zero customer sinks |
| Known precommit failure, confirmed rollback and clean release | dependency_unavailable |
| Commit attempted/lost acknowledgement, or attempted rollback without acknowledgement | Existing admission outcome_uncertain mapping; never retry effect |
| Ordinary cleanup failure before commit with acknowledged rollback | Existing dependency_unavailable mapping; cleanup failure alone does not imply an uncertain mutation |
| Cleanup failure after a possible or acknowledged effect | Existing outcome_uncertain mapping; never retry effect |
| Acknowledged effect followed by dependency, association or late-growth disclosure failure | outcome_uncertain |
| Fresh typed identity/project/action denial | Preserve IdentityInvalid, ResourceNotFound or ActionForbidden |
| Fresh classification cannot run within remaining SQL budget | Preserve dependency before effect or uncertainty after possible effect; do not fabricate visibility |
| Unrelated programming error outside the mutation transaction | Preserve existing internal-error boundary |
| Failure inside admission_transaction | Preserve its reviewed finite outcome mapping and mandatory cleanup |
| BaseException/interruption | Preserve identity after mandatory cleanup, with no retry or successful response |

The post-failure authority check cannot revive a failed owner. Explicitly test
the missing-configuration/invalid-cohort branch and the post-acknowledgement
branch with concurrent revocation. This ordering is separate from the
malformed-ID branch, which needs only project read authority before 404.

## Limits and actual PostgreSQL proof

Keep 512 charged attempts, 10 SQL-active seconds, 20,000,000 SQLite VM
instructions, cumulative 256 visits/512 edges, 4 MiB retained receipts,
259 identities and the existing bounded final-query shape. Authority, locks,
native setters, commit, rollback and cleanup all consume the same work.
Compatibility has its separate reviewed finite inspection budget.

The earlier source-only estimate of approximately 31 OIDC/39 API-key body
statements and 116/140 PostgreSQL attempts predates this entry's explicit
early plus final preflight cancel checks. It is not executed capacity evidence.
Recount the implemented path and record complete traces only after cleanup.
Pool wait and storage latency do not become an end-to-end 10-second promise.

Use the existing synthetic PostgreSQL instance after explicit exclusive
lifecycle handoff. Prove SELECT plus narrow UPDATE(kind) on operations suffices
for its SHARE lock while association-column updates are denied. Grant only
the intended job cancel/status updates plus documented row-lock requirements,
and audit INSERT; no broad operation UPDATE or schema privileges. Separate
actual app-role permission refusals from native read-only transaction controls.

Exercise ordinary administrative update/delete contention on existing project,
membership, key, job and operation rows through commit, as well as association
drift and worker advancement. Row locks do not freeze wall-clock expiry or
arbitrary future administrative inserts. Preserve the existing project-first
writer convention and its documented legacy-worker limits; do not claim more.

Restore the exact initial database/role inventory, prove zero other clients,
stop the socket-only instance and record final process/socket state before
releasing its lifecycle. No second instance, installation or paid resource.

## Reviewable acceptance checkpoint

The implementation PR must include:

- Exact three-field response and all five native statuses; queued transition,
  repeated audit, noncreator operator, unchanged budgets/leases/results/errors
  and zero storage/provider/worker/reservation/refund effects.
- Viewer/foreign/missing/revoked/expired-key/role-ceiling cases and original
  named context even if the legacy default changes. Malformed-ID precedence
  and zero downstream reads/effects, including SQL/cleanup failures.
- Fresh three-phase receipts, original operation/job/config association,
  zero-to-many result-ref changes ignored for cancellation, valid worker
  advancement between phases and within-phase native-row drift refusal.
- Stable 84-root success, stable 85-root pre-effect refusal, late post-commit
  cohort overflow, substantial distractors and complete charged-work traces.
- Known rollback, effect/audit failures, commit-acknowledgement loss and cleanup
  faults; at-most-one effect and no mutation retry. Fresh authority/visibility
  precedence after secondary failures, including post-commit revocation.
- Actual PostgreSQL narrow-grant, lock contention, reassociation, concurrent
  revocation/worker and usable-pool evidence, with synthetic fixture setup
  separated from request effects.
- Unchanged GET/legacy cancellation/helper regression behavior, relevant lint,
  format/type checks, contract/backlog/evaluation validators, and independent
  source plus execution review on the exact composed source.

A local service component does not satisfy P1 by itself. Exact installed
package proof, full source-bound hosted checks and final component composition
remain required. Production activation, live provider/KMS/IdP, partner data,
research superiority and P2 HTTP work remain outside this assignment.
