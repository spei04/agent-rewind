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


## Unwired private journal component

`AdmissionJournal.open(JournalIdentity(...))` opens only the two deterministic
full-scope client/key locators in sorted nonblocking lock order, followed by their
two known child attempts. It never enumerates the installation root. Each root
must be pre-provisioned, private, durable and installation-specific as required by
PublicationJournal. Existing journal defaults and callers retain their limits.
The wrapper tightens reads before materialization to 4 KiB per locator, 128 KiB
per child, 64 records per child and 16 KiB per record; combined child history is
bounded to 1,179,648 bytes. Four known journals are locked by one local owner;
this is not a distributed or installation-wide writer limit.

`bind` durably freezes identical full identities, request digest, first origin
and child IDs. A later request origin is ignored in favor of that first origin.
One-sided, colliding, malformed, torn or missing frozen inputs refuse. A reopened
bound pair with no child is conservative refusal, not absence proof. Only a fresh
pair in its creating invocation may first freeze an attempt. Failures poison the
current session; accepted existing files are revalidated and fsynced on reopen.

Child snapshots contain metadata and canonical configuration, never task or
envelope plaintext. Strict policy evidence binds organization/project/principal,
request/task/configuration digests and processor profile plus an opaque version
and bounded structured state (16 KiB total). That trusted adapter evidence must
exclude credentials and arbitrary exception text; its shape is not a grant.
`restore(intent)` requires the matching retried task and shared envelope validator.

Upload phase records compare exact descriptors and retain unknown prior work and
all observed counters. They are diagnostics, not newly manufactured receipts.
A durable commit_pending on reload permanently chooses SQL-only reconciliation,
including if a linked second child exists. In the same invocation only, child 1
requires an observed confirmed precommit TransactionOutcome and exact diagnostic
MetadataCollision pair. The future coordinator must separately prove that pair
through fresh scoped SQL after rollback; neither this type nor a generic storage
error supplies that authority. Both children preserve IDs, origin, config and
policy. No third child or old receipt relabeling is supported.

This component is not connected to AdmissionCoordinator. Authority, dual SQL
routing, policy availability, real put receipts, journal/SQL ordering and final
publication still require their later reviewed composition. File/lock/fault
unit evidence does not establish actual PostgreSQL publication or crash recovery.
