# Admission recovery checkpoint

This first AR-008-A/P3 checkpoint supplies pure frozen restoration and an internal
SQL-only winner path. It cannot publish a new job or upload bytes. The default
packaged schema guard still refuses migration-only ar6 before operation/alias
queries. Synthetic tests replace one coordinator instance's compatibility result;
they do not establish a customer-ready profile.

## Internal API

`AdmissionCoordinator(engine, authority)` exposes
`submit(principal, original_context, intent, key_hash, origin)` and
`reconcile(principal, original_context, client_operation_id, key_hash, request_digest)`.
Both return only the original stored `operation_id`/`job_id` pair through
`StoredOperation.accepted_response`. Inputs retain the original project and
creator; a viewer status read never substitutes for current record permission.
New submit without a SQL winner refuses with `dependency_unavailable`;
reconciliation without one, or unable to establish one, is `outcome_uncertain`.
Neither path invokes a registry, policy/readiness adapter, journal or storage.

Both scoped identities are resolved before locks, then repeated under the shared
project → organization → caller membership → caller key scope/key → target
scope/job hierarchy. A legitimate missing key alias is committed atomically.
Matching replay preserves configuration/origin and adds no job.create audit.
After SQL is released, another creator-record/dual-identity check compares the
complete original stored operation before disclosing its pair. No response
linearizability promise follows from READ COMMITTED.

## Frozen restoration and transaction observations

`restore_admission` parses the original bounded configuration through
`NativeConfiguration(bytes, expected_digest=...)`, shares the same envelope and
binding validator as new preparation, and compares the expected envelope digest.
The full original job, origin and seven-field descriptors must still come from
validated original journal state; the envelope digest does not bind them all.
Restoration is neither a policy grant, upload receipt nor committed authority.

`TransactionOutcome` records begin, commit attempt/acknowledgment, rollback
attempt/acknowledgment and cleanup failure separately. Acknowledged rollback
after a commit attempt is never a confirmed precommit rollback. Effective
autocommit, dirty connections and SQLite FK-off modes refuse; transaction waits
are bounded and failed cleanup discards the physical connection. Existing typed
identity/visibility/action denials survive cleanup. Lost acknowledgment or
postcommit disclosure dependency failure remains uncertain. Only explicit
compared SQL identity mismatch produces idempotency_conflict; a generic
IntegrityError/storage conflict cannot supply that proof.

The shared lock extraction preserves existing ScopedActions transaction/audit
behavior; it does not broaden legacy writer guarantees. Later P3 checkpoints
still own dual journal locators/strict reload phases, unavailable policy routing,
verified receipts, bounded metadata readback, atomic new publication, one
confirmed-rollback metadata retry and actual contention/process-death evidence.
HTTP/worker/ledger/generation and customer activation remain separately gated.

## Checkpoint validation boundary

Focused SQLite tests cover existing/absent/conflicting identities, alias rollback
and lost-ACK retry, current authority and postcommit disclosure, real schema
refusal, actual driver modes/rollback/close faults, and preserved ScopedActions.
Package smoke imports the new modules, validates frozen restoration and executes
the real migration-only coordinator refusal. Local helper execution is not an
installed-wheel or PostgreSQL claim; actual hosted tests remain required.
