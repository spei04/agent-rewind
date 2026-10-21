# Admission recovery checkpoint

AR-008-A/P3 now composes pure frozen restoration, SQL-only winner recovery and
an internal new-work path requiring explicit policy, readiness, registry, journal
and storage dependencies. The default policy is unavailable; the packaged schema
guard still refuses migration-only ar6 before operation/alias queries. Synthetic
tests replace one coordinator instance's compatibility result and supply a test
policy; they do not establish a deployed policy or customer-ready profile.

## Internal API

`AdmissionCoordinator(engine, authority)` exposes
`submit(principal, original_context, intent, key_hash, origin)` and
`reconcile(principal, original_context, client_operation_id, key_hash, request_digest)`.
Both return only the original stored `operation_id`/`job_id` pair through
`StoredOperation.accepted_response`. Inputs retain the original project and
creator; a viewer status read never substitutes for current record permission.
With default dependencies, new submit without a SQL winner refuses with
`dependency_unavailable`. Reconciliation without one, or unable to establish one,
is `outcome_uncertain`. SQL winner/reconcile paths never invoke registry,
policy/readiness, journal or storage. Optional keyword dependencies are internal
composition only; no route or product activation switch is added.

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
behavior; it does not broaden legacy writer guarantees. The new-work composition
below consumes the separately reviewed journal, metadata and transaction
primitives. Actual publication contention/process-death and matching hosted
PostgreSQL/package evidence remain required before full P3 acceptance.
HTTP/worker/ledger/generation and customer activation remain separately gated.

## Checkpoint validation boundary

Focused SQLite tests cover existing/absent/conflicting identities, alias rollback
and lost-ACK retry, current authority and postcommit disclosure, real schema
refusal, actual driver modes/rollback/close faults, and preserved ScopedActions.
Package smoke imports the new modules, validates frozen restoration and executes
the real migration-only coordinator refusal. Local helper execution is not an
installed-wheel or PostgreSQL claim; actual hosted tests remain required.


## Private journal component

`AdmissionJournal.open(JournalIdentity(...))` opens only the two deterministic
full-scope client/key locators in sorted nonblocking lock order, followed by their
two known child attempts. It never enumerates the installation root. Each root
must be pre-provisioned, private, durable and installation-specific as required by
PublicationJournal. Existing journal defaults and callers retain their limits.
The wrapper tightens reads before materialization to 4 KiB per locator, 128 KiB
per child, 64 records per child and 16 KiB per record. Each child intent plus
its history is bounded to 1,179,648 bytes; the two children together are bounded
to 2,359,296 bytes, plus two locator intents of at most 4,096 bytes each. Four
known journals are locked by one local owner; this is not a distributed or
installation-wide writer limit.

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
requires an observed confirmed precommit TransactionOutcome, successful SQL
release and an exact diagnostic MetadataCollision pair. The coordinator must
separately prove that pair through fresh scoped SQL after rollback; neither this
type nor a generic storage error supplies that authority. Both children preserve IDs, origin, config and
policy. No third child or old receipt relabeling is supported.

The component is now consumed by the internal coordinator. File/lock/fault unit
evidence still does not establish actual PostgreSQL publication or crash recovery.

## Explicit new-work composition checkpoint

The unchanged constructor's optional keyword dependencies are `policy`, `registry`,
`readiness`, `journal` and `storage`. Existing two-argument callers retain SQL-only
winner behavior and default refusal. `AdmissionPolicy.require_available` is a pure
preflight. `permission(principal, context, intent, candidate)` must establish actual
caller/corpus permission for the exact immutable candidate and returns
`ProcessorPermission(configuration_digest, processor_profile)` before registry
resolution. Registry metadata and this value's shape are not grants.
`prepare(..., configuration)` returns the existing bounded policy schema after
exact configuration selection. `recheck(connection, ..., configuration, evidence)`
must perform bounded SQL/pure checks on that Connection under the agreed project
exclusion or immutable version protocol. No deployed policy adapter is supplied.

`AdmissionReadiness.check(principal, context, intent, configuration)` is explicitly
synchronous and outside SQL; only exact `AdmissionReady(ready=True)` succeeds.
Awaitables and malformed values refuse, with no event-loop bridge. The existing
async HTTP readiness object is not this interface. Adapters own their bounded
operations; no background timeout thread or provider discovery is introduced.

New work durably binds both locators, freezes validated configuration/policy/IDs
and descriptors, then checks current authority/policy and readiness before actual
put/verify. Exact resume uses the frozen configuration/evidence and first origin,
never current registry defaults. Every put and journal call occurs after SQL is
released. Returned receipts are checked against all original descriptor fields
and preserved in the journal; interrupted work remains UNKNOWN.

Descriptor discovery and `record_verified` share one bounded candidate query:
prospective ID OR same-project digest/format, LIMIT 2 with all seven SQL cell bounds.
Malformed, foreign or ambiguous candidates refuse. Only an actual metadata-stage
mismatch can produce `PublicationCollision`; generic constraint failure cannot.
After clean acknowledged rollback, both SQL identities are checked again and a
fresh unique exact metadata winner must prove every replacement. One linked child
reverifies all bytes; a second collision refuses without a third attempt.

After durable commit_pending, one owned transaction repeats identity and policy
checks under exclusion, inserts all 16 job columns (queued, reserved=0, null
owner/lease/result/error), then the job scope, three verified metadata/refs,
operation, alias, first origin and one fixed job.create audit. No legacy enqueue,
postinsert config update, budget reservation, sequence allocation or dispatch is
used. A late SQL winner bypasses new-work policy and returns its original pair
without confirming the abandoned journal's different proposed IDs. Commit/close,
journal confirmation and fresh disclosure failures retain the reviewed fixed
phase classifications. Restart after pending always reconciles SQL-only.

Focused tests use actual SQLite and encrypted local storage with a synthetic
SQL policy, stage faults and observed rollback/commit. Separate real PostgreSQL
publication tests, process-death/concurrency proof and hosted package validation
remain pending; this checkpoint does not complete P3 or activate customers.
