# Admission coordinator entry checkpoint

Planning only, pinned to reviewed storage source `a7caf0f478fb91805a1b194023ef9de1fa9d0307`.
This records the bounded resolution of four AR-008-A/P3 entry findings; it implements nothing.
P3 remains **Not started** until accepted merged P2 and explicit assignment.
The [execution plan](ADMISSION_EXECUTION_PLAN.md), C04 and CT-M1-008/010/011/012
remain authoritative. Estimates, dependencies, schemas, routes, profiles and
spending/data authority are unchanged. Independent B design review is required.

## Service and authority boundary

The service has these two internal entry points; they add no HTTP endpoint:

```text
submit(principal, original_context, intent, key_hash, origin) -> Accepted
reconcile(principal, original_context,
          client_operation_id, key_hash, request_digest) -> Accepted
```

`principal` is an authenticated VerifiedPrincipal; original_context is the
already-resolved ProjectContext, never a newly inferred default. Intent is the
immutable P1 CanonicalIntent. The key is the validated idempotency-key hash, never the raw key.
OriginCorrelation comes from the trusted server boundary. Accepted is exactly
the existing operation_id/job_id pair, with no journal ID, locator or new field.

Fresh schema/identity/project/action checks precede scoped reads. Resolve **both**
client and key identities using the caller's same Connection before readiness,
policy, registry, journal or storage. Viewer status reads remain separate:
submit/reconcile require the creator's current record authority. A service-key
change is a different principal, not recovery. Preserve named/default context
semantics and inaccessible 404 before accessible-action 403.

A matching SQL operation always wins over journal availability. Under the
project/grant/caller/target exclusion below, repeat both lookups, verify its
stored job/config associations, and atomically bind a legitimate missing alias.
Return the original IDs/config/origin after acknowledged commit and fresh
disclosure authority. Do not consult today's registry/policy, probe readiness,
read objects, or add another job.create audit for replay. Conflicting identities
produce idempotency_conflict, never a chosen first winner.

## Same-submit restart routing

The frozen API has no lookup by client-operation ID. A retry of the same POST
must itself enter recovery; exposing only a separate internal reconcile method
does not satisfy this requirement.

Use the existing installation-private PublicationJournal root, outside the
object tree. Define two deterministic locators and two possible child attempts:

```text
S = {organization_id, project_id, principal_id, kind: "run"}
C = {schema: 1, purpose: "admission-client", scope: S, client_operation_id}
K = {schema: 1, purpose: "admission-key", scope: S, key_hash}
locator(x) = sha256(canonical(x)).hexdigest()[:32]   # x is C or K
attempt_id(i) = sha256(canonical(
    {schema: 1, purpose: "admission-attempt", client: C, attempt: i}
)).hexdigest()[:32]                                # i is only 0 or 1
```

All fields are server-validated. The private root belongs to one installation,
not unrelated databases. Retain and compare the full identities and digests:
a truncated-name collision, unexpected child, malformed record or changed
binding refuses. Neither journal possession nor these hashes proves commit.

After initial SQL absence, acquire both existing nonblocking locator locks in
sorted locator-ID order, then repeat both SQL lookups. Both locator intents
must durably bind the same full C/K identities, request_digest, first trusted
origin and two derived child IDs before preparation/upload is permitted. A
retry's new request correlation never replaces or conflicts with first origin. On a
fresh pair, freeze both small records; an interrupted write or only one retained
binding fails closed. A complete existing pair must agree. Inspect only these
two locators and their two known children; never scan the installation journal.
Acquire a child lock only after both locator locks; no journal acquisition or
I/O occurs inside SQL.

A client-only locator would miss an unresolved key reused with another client
ID. A key-only locator would miss a new key for an unresolved client. If either
locator reveals another binding or pending attempt without an exact authorized
SQL winner, return outcome_uncertain with no upload, alias or new SQL write;
journal mismatch alone is not proof of a committed idempotency conflict.
A legitimate new alias is bound through the SQL-winner replay path. Only the
exact original C/K binding resumes a precommit attempt; a new key cannot select
new history merely because it has an empty locator.

A complete, validated journal with no durable commit_pending permits bounded
exact-attempt continuation after fresh authority and both SQL lookups. Reparse
the retried bounded task and verify its original task/request digests; rebuild
the envelope only from those bytes plus the frozen configuration, origin and
IDs. The child intent retains the exact canonical configuration snapshot
(<=64 KiB, private 0600 handling), so changed registry defaults or an unavailable
registry cannot silently substitute configuration. Validate the snapshot digest
and reconstructed envelope against the original descriptors before reverify.
Missing or mismatched frozen input refuses; never resolve current defaults.
Upload-start without a verified outcome remains unknown backend work, never a
free or confirmed write. Reverification uses the same immutable descriptor and
storage's existing put/verify behavior and records additional actual work.
A truncated, unavailable or failed journal read supplies no absence proof.

Persist commit_pending successfully **before opening publication SQL**.
Once it exists, a restarted submit becomes SQL-only reconcile: matching SQL
can recover; absence or database unavailability returns outcome_uncertain and
does not upload, prepare, assign another ID or change configuration. A known
identity conflict remains idempotency_conflict. A busy journal permits a bounded
SQL-only winner check; no unbounded wait or automatic preparation loop.
Reconcile itself never depends on a journal, readiness, registry or storage,
and never falls through to submit when no matching SQL identity exists.

## Immutable attempts and storage evidence

Use PublicationJournal.open/freeze/append and its existing private modes,
nonblocking locks, fsync, bounded records and fixed record kinds. No new journal
framework, record-kind vocabulary, deletion policy or GC is introduced.

Each child intent links full C/K, both locator digests, attempt index and predecessor,
and freezes proposed operation/job IDs, original origin, request/task/config/
envelope digests, canonical configuration, policy evidence and all seven fields
of each of the three descriptors. Task source/envelope plaintext, credentials
and arbitrary exception text are excluded. Configuration remains at most
64 KiB; policy evidence is at most 16 KiB canonical structured metadata; each
coordinator child intent is at most 128 KiB, below the existing journal's 8 MiB
limit. Individual records retain its 16 KiB bound. These are implementation
bounds requiring maximum-size fixtures, not changes to the accepted 8 MiB task.

Before uploading, choose existing same-project/digest/format metadata by bounded
SQL or create prospective descriptors. Verify exact ID, project, digest, locator,
format, byte_count and created_at; a digest is not an object ID or receipt.
Close SQL before all task/config/envelope put_verified calls. Persist upload
start before each call and verified/unknown work afterward. Keep actual read/
write counters separately from logical writes and preserve prior uncertainty.
Corrupt existing objects refuse; no clobber or foreign-project cache lookup.

One shared-metadata collision may trigger attempt 1 only in the same invocation
after publication rollback is positively acknowledged. First resolve both SQL
identities again: a committed operation takes the replay path. Otherwise read
the winning descriptors, retain the same canonical request/config/origin and
proposed job/operation IDs, freeze the linked child, and reverify outside SQL.
Never edit attempt 0, relabel its receipts, or treat a different descriptor as
already verified. The child records the confirmed predecessor rollback as
diagnostic provenance, not commit authority. A restart with commit_pending
still reconciles conservatively; it does not infer rollback from SQL absence.
A second collision refuses with dependency_unavailable after confirmed rollback;
it creates no third attempt. Unknown rollback/commit acknowledgment never permits
this path. Existing orphan objects remain retained and identifiable.

## Policy, lock order and commit

The required trusted policy adapter has a bounded preparation method and
`recheck(connection, principal, original_context, intent, configuration, evidence)`.
Preparation establishes actual caller/corpus permission; its evidence binds
the principal/project, request/task/config identities, policy version/state and
permitted processor profile. The default adapter is unavailable. P1's processor
string, registered image alias and structural budget ceiling are not grants,
funding or proof that policy is still current.

After both SQL identity checks and bounded existing-attempt routing establish
genuinely new work, a deterministic required-policy availability preflight must
refuse an unavailable adapter before freezing a new journal intent, readiness
probes, registry resolution or storage work. This preflight performs no external
I/O. Matching SQL winners retain fresh authority checks while bypassing today's
policy, registry, readiness and journal dependencies. Existing commit_pending
attempts still take SQL-only reconciliation even if today's adapter is unavailable.
A resumable uncommitted attempt requires the same availability check before
revalidation or external work, without replacing its frozen evidence.

Readiness and policy preparation then run outside SQL locks. Freeze the immutable
registry configuration once for genuinely new work.
On exact-attempt resume, validate that frozen evidence/configuration without a
new registry resolution. Recheck accepts the caller's Connection and performs
bounded SQL/pure checks only: no separate connection, storage, provider, readiness
probe or journal I/O. A test adapter must not become a product activation flag.

Participating publication and authority writers use this order:

1. All affected projects in sorted order, before any subordinate locks.
2. Organization, then current caller membership.
3. Caller key scope, then caller key row when applicable.
4. Existing target scope, then target job rows in consistent sorted order.
5. Under those locks, repeat both operation identities and fresh authority;
   return a matching replay before applying new-work policy.
6. Recheck new-work policy and exact prepared associations. Publish queued job
   with reserved=0, job scope, verified object metadata/refs, operation, alias,
   first origin and one fixed job.create audit in the same transaction.

Do not lock a foreign target before scope validation or substitute another
default after waiting. New rows are protected by the held project exclusion
and real unique/composite constraints, not invented locks on absent rows.
Policy mutation must participate in the same exclusion or use validated
immutable/versioned evidence that cannot change before commit; an adapter
without that proof remains unavailable. AR-010 integration later composes its
account/generation protocol; this package grants no dispatch or reservation.

Use actual transactional modes, SQLite FK enforcement and bounded PostgreSQL
lock/statement waits; reject effective autocommit and dirty pooled connections.
Allocate no new source/project sequence here. Acknowledge commit, release SQL,
then freshly authorize disclosure on the original context/target. Revocation,
key expiry and default changes are checked again. No successful response follows
a failed disclosure check, and no storage/network/journal I/O runs under SQL locks.

## Phase and fixed errors

The coordinator classifies its own typed failures before the HTTP boundary;
AdmissionStorageError is not already a public Fault. Generic ValueError is
never assumed to be invalid client input. Cleanup cannot replace the first
classification or expose driver/journal exceptions.

| Observed phase/result | Fixed result and action |
| --- | --- |
| Malformed client intent at its documented input boundary | invalid_request; no preparation. |
| Invalid internal policy/configuration evidence | Fixed dependency_unavailable before possible commit; uncertainty rules below after commit may have begun. |
| Invalid identity, inaccessible scope, accessible denied action | Existing unauthenticated/not_found/forbidden; no disclosure. |
| Proven mismatch of client/key/canonical identity | idempotency_conflict; no new job. Metadata collision alone is not this error. |
| Known precommit dependency failure with no possible SQL commit | dependency_unavailable; any retry keeps original identity and obeys durable journal routing. |
| Confirmed precommit metadata-conflict rollback | At most one linked reprepare; second conflict refuses as above. |
| Unknown storage work before SQL | Preserve unknown receipt/counts; bounded exact-attempt reverify only with a complete journal proving no commit_pending. Otherwise outcome_uncertain. |
| Commit attempted, acknowledgment/rollback ambiguous | outcome_uncertain, retryable=false; SQL-only reconciliation. |
| Commit acknowledged, journal append/fsync/close fails | outcome_uncertain, retryable=false; retain original IDs internally; no fresh preparation on retry. |
| Commit acknowledged, fresh disclosure database unavailable | outcome_uncertain, retryable=false; never retryable pre-admission dependency_unavailable. |
| Commit acknowledged, fresh disclosure explicitly denied | Preserve the typed 401/403/404 denial, without Accepted; do not erase the committed operation. |
| SQL reconciliation has no matching operation or cannot establish one | outcome_uncertain, retryable=false; no configuration/upload fallback. |
| SQL winner and final authority established | Original Accepted; only a legitimate alias may be newly committed. |

A known rollback in memory does not become durable absence evidence after a
restart. Retryable precommit errors do not promise that a subsequent attempt
will progress past a conservative journal refusal. Never turn journal evidence,
a completed upload or a submitted binding into SQL commit proof. Preserve fixed
public messages, fresh response IDs and the operation's original persisted origin.

## Required acceptance fixtures

- Eight concurrent same-identity submissions: one job/operation/job.create audit;
  every accepted response has original IDs. Same body/new key binds one alias;
  conflicting key/client/body, foreign principal/project and moved defaults refuse.
- Real policy, membership and token changes during uploads and before disclosure;
  test both sides of observed PostgreSQL lock waits and zero external I/O while
  SQL is open/locked. Viewer status is not creator replay permission.
- Registry/readiness/storage/journal outages with an existing SQL winner: no
  new preparation or upload; missing alias still requires atomic current authority.
- Either locator bound alone, changed client with the same unresolved key, or
  changed key with the same unresolved client: no preparation or SQL mutation.
  Truncated/failed reads never become absence; full locator binding must agree.
- Restart after durable commit_pending with absent/unavailable SQL: same submit
  uses SQL-only recovery. Actual process death before/after commit, lost response
  and lost acknowledgment never invent replacement IDs or overwrite first origin.
- Interrupted journal writes/reads and upload uncertainty, acknowledged-commit
  append/close failure, and post-commit disclosure failure retain the table above.
- Concurrent identical shared bytes and descriptor replacement: exact seven-field
  comparison, one confirmed-rollback child attempt, second-collision refusal,
  unchanged old receipts and real additional work accounting. Equal bytes in
  different projects never share scoped authority.
- Failure after every SQL publication stage rolls back job/scope/metadata/refs/
  operation/alias/audit together; old history remains unchanged. Driver modes,
  privilege errors and cleanup failure cannot return success or raw canaries.
- Maximum 8 MiB task, 64 KiB configuration and bounded metadata journal; task
  bytes never enter the intent journal. Lock/contention and process-death proof
  require actual hosted PostgreSQL, not skipped collection or SQLite alone.

Reuse artifact storage/metadata, AdmissionRepository and the existing journal
mechanics. RunPublisher, PublicationIntent, Database.enqueue and WorkAdmission
are not substitutes for this authority boundary. HTTP submit/status/cancel stay
with AR-008-B; list/detail stay with AR-006-B. P3, worker dispatch, runtime-ready
profiles, deployment and paid execution remain unassigned or separately gated.
