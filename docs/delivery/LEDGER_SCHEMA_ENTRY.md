# Ledger schema and provisioning entry

This is the AR-010-A/P1 design checkpoint, prepared by engineer C from accepted
HTTP component `a439bce8` and the owner-approved ledger execution proposal
`882fa139`. It is a proposal for independent entry review, not a migration,
captured catalog, executable provisioning manifest, runtime implementation or
delivery acceptance. AR-008-B must have its accepted PR, protected-main and
candidate evidence before implementation. A owns the current planning amendment:
P1 schema/provisioning and P2 reservation/concurrency are each 3 [3–5] BE days,
6 [6–10] in aggregate. This document changes neither status nor those estimates.

The authoritative logical fields and obligations remain
[M1 C04](M1_CONTRACT_FREEZE.md#first-migration-slice-and-revision-ownership),
[the frozen data model](../../contracts/proposals/m1.data-model.json) and
[the ledger delivery plan](LEDGER_EXECUTION_PLAN.md). The approved job-account
period means a **finite, immutable, trusted-provisioned authorized execution
window**. It is not reconstructed actual wall time, a renewable lease or the
worker's mutable `max_job_seconds`. No public request or native configuration
schema-1 field is added.

## Scope and proposed interfaces

Implement additive `ar_0007_ledger`, down-revision `ar_0006_admission`, with exactly
the three C04 ledger tables and two jobs columns below. Keep the original thirteen
job columns and all ar6 admission fields unchanged. Initial schema installation,
opening backfill and initial account provisioning form one transaction. Later
account provisioning uses the same explicit, drained operator boundary.

The proposed narrow internal interfaces are:

```python
read_ledger_manifest(path: Path) -> LedgerManifest
validate_ledger_manifest(value: object) -> LedgerManifest
initialize_ledger(
    engine: Engine, manifest: LedgerManifest, *, timeout_seconds: int = 5
) -> LedgerProvisioning
inspect_ledger_state(connection: Connection) -> LedgerState
```

`LedgerManifest` and returned records are immutable validated values. The
initializer owns connection/exclusion/commit; the inspector never commits,
opens another connection or reads files. File validation happens before SQL.
No HTTP handler accepts a manifest, and no default manifest is synthesized.

Expected focused modules are migration input/state/schema/service modules and
one Alembic revision, using existing `MigrationRefused`, canonical encoding,
source hashing, explicit Alembic connection and ownership/profile utilities.
Do not import a private helper merely to bypass its validation. Extract only
concretely shared behavior needed by this caller. The migration transaction
requires a narrow outcome/accounting extension, described below, rather than
pretending its current generic database-failure result proves rollback.

P1 does not reserve, dispatch, claim a job, produce provider evidence, settle,
release, transfer exposure or change worker behavior. P2 supplies bounded
existing-account reservation and the minimum generation/database-time fence.
AR-010-B integrates live worker permit paths. Every new job or period account
still requires drained operator provisioning; a later admitted job without
accounts refuses reservation. This deliberate operational limit is not paid
execution readiness or an online provisioning producer.

## Trusted manifest: exact proposal

The input is an owner-readable regular file, opened with the existing
`O_NOFOLLOW | O_NONBLOCK` pattern, owned by the invoking OS identity and with
no group/other access. Read at most 32,769 bytes, refusing more than **32,768**.
Decode strict UTF-8; reject BOM, duplicate keys, non-finite numbers, fractions,
exponents where integers are required, negative zero, booleans as integers,
unknown members, control characters and nesting deeper than eight. Do not
coerce money, IDs, strings or timestamps. File ownership and its digest do not
grant database authority or authenticate financial evidence.

Exactly these top-level members are required:

| Member | Exact value or rule |
| --- | --- |
| `schema_version` | Integer 1. |
| `installation_key` | Exact existing adoption key, 1–64 ASCII characters under the existing key grammar. |
| `manifest_id` | 32 lowercase hexadecimal characters, operator-chosen immutable replay identity. |
| `operation` | `initialize` or `provision`. Only initialize may advance ar6 to ar7. |
| `source_digest` | 64 lowercase hexadecimal characters; the original five-table source projection observed for this invocation. SQL recomputes it under exclusion. |
| `parent_manifest_digest` | Null for initialize; for provision, the exact latest accepted manifest digest in this installation's ar7 chain. |
| `backup_evidence_digest` | 64 lowercase hexadecimal characters identifying the operator's private, verified pre-change backup record. It is not a provider receipt. Required even for an empty source; existing fresh-adoption null evidence fields are not rewritten. |
| `drain_evidence_digest` | 64 lowercase hexadecimal characters identifying the operator drain record, corroborated by the existing database exclusion checks. |
| `accounts` | 0–64 account objects, strictly sorted by ID, with no repeated ID or scope/start identity. Initialize may be empty only when there are no jobs and no opening exposure. Provision must add at least one account. |
| `opening_accounts` | Initialize: the object below selecting imported organization/project exposure destinations; provision: null. |

Each account object has exactly `id`, `organization_id`, `scope`, `scope_id`,
`project_id`, `job_id`, `period_start`, `period_end`,
`limit_microusd`. These are the C04 identity/period/limit fields; balances and
opening values are **not** caller inputs. All IDs are exact lowercase 32-hex.
Both nullable IDs must be explicitly present. Scope is exactly organization,
project or job, with the frozen null/non-null shape. Every organization ID must
equal the **single existing installation organization**; an extra organization
is unsupported, not an expansion of M1.

Times have exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`, valid Gregorian dates in years
0001–9999, no leap seconds, offsets or infinity, and start < end. Intervals are
half-open. Limits are integers in [0, 2^63−1]; every addition uses checked integer
arithmetic before storage, never float conversion. A job account's limit cannot
exceed that job's unchanged gross `budget`.

For initialize, `opening_accounts` has exactly:

```json
{"organization_account_id": "32hex-or-null", "projects": [
  {"project_id": "32hex", "account_id": "32hex"}
]}
```

The actual JSON value is null for the organization ID only for an empty account
set. The projects array is sorted by project ID, unique, and names one account
for every project containing an imported job. The chosen organization/project
accounts are among `accounts`, have matching scopes, and use the same explicit
import period. That period contains the database-observed initial commit
preparation time; an exact completed retry uses its persisted observation,
not today's period. Job accounts map uniquely by job ID, and their periods are
the approved execution windows; they need not equal the import period.
Opening import is not a fabricated historical provider admission.

Per input: at most 16 projects and 48 job accounts, within the 64-account and
32 KiB limits. A valid simultaneous account/job maximum uses one organization,
15 projects and 48 jobs. The separate 16-project boundary is tested with fewer
jobs. Byte limits independently win; tests must construct actually valid
canonical inputs, not padding or impossible combinations. There is no second
job-window array or duplicate authority source.

Canonical bytes use the existing migration JSON convention: sorted object keys,
compact separators, ASCII escaping, finite exact integers, no insignificant
whitespace. Arrays already have the required order. Re-encode after strict
validation and enforce 32 KiB again. Define manifest digest as
`SHA256(canonical(validated_manifest))`. A digest proves content identity, not
approval, safe origin or financial authenticity. Raw whitespace variation with
the same validated value is the same intent; changed account ID, window, cap,
parent, evidence binding or source digest conflicts under the same manifest ID.

Authority is the explicit trusted operator invocation plus existing database
owner/schema-owner/superuser checks, disabled legacy writer inventory and writer
drain. No browser role, API key, caller string or supplied actor field can grant
provisioning. Record the observed database role, OS UID and initialization time
as provenance outside the canonical manifest. These are attributable observations,
not a signature or proof against a malicious trusted operator.

## Durable binding without another table

Use the existing, feature-owned `migration_progress` namespace:

| Key | Durable content |
| --- | --- |
| `(ar_0007_ledger, ledger_manifest_<manifest_id>)` | The entire validated canonical manifest value, its digest, sequence number, parent digest, database role/OS UID/time, immutable account projection digest and exact inserted-account count. |
| `(ar_0007_ledger, ledger_opening)` | Initial manifest ID/digest, original source digest, sorted original job/opening receipts, their digest, per-project/organization opening totals, total imported jobs and first initialized time. |

Each cursor has `schema_version:1`, an exact member set and at most 65,536 bytes,
the existing metadata ceiling. Initial opening receipts contain the original job
ID, scoped project, original budget and L_j. At most 48 are present. Store each
row's original source digest in `source_digest`, inserted/verified count in
`rows_verified`, and only `status=complete`. This slice has no partially committed
backfill or running/pending phase; a bounded installation that cannot complete
atomically refuses. Schema, all account/opening rows, both initial progress rows,
Alembic head and installed fingerprint commit together.

Sequence begins at zero and increments exactly once per successful new manifest.
A provision manifest extends the sole head under exclusion. No fork, gap,
duplicate digest with another ID, conflicting phase, unknown ar7 phase, cursor
extra key or inconsistent complete/count combination is accepted. The ar7
inspector reads at most 257 manifest rows and refuses more than **256**; aggregate
stored cursor bytes are checked in SQL before transfer and may not exceed
**16 MiB**. Check each cursor's native type and byte bound before JSON decoding.
The original ownership/run-index phases, adoption mapping/digest and historical
backup/drain fields are neither reused nor updated.

Current ownership/projection writers address their own exact revision/phase;
source search at a439 has no generic progress-delete or cleanup path. Add tests
that initialization/provision/retry leave every older progress row byte-for-byte
unchanged. New diagnostics may expose fixed phase/status/count/digest summaries,
not manifest bodies or evidence paths. Runtime roles cannot insert, update,
delete or truncate progress. There is no retention cleanup for these provenance
rows: they are needed as long as the accounts/opening exist.

A completed retry first resolves its manifest ID, then validates the complete
stored canonical manifest and immutable corresponding account/opening projection.
It returns the original result with zero writes, including no timestamp refresh.
It must not reapply opening values or compare current mutable balances to their
initial values. After legitimate future reservations, original `jobs.reserved`
can grow; the initial source digest stays historical. Verify initial L_j against
`legacy_reserved_microusd` and the preserved opening receipts, not today's gross
reserved total. A new manifest still binds/rechecks its own current source
snapshot before and after its transaction.

Never use `installation_adoptions.mapping` as a ledger manifest store or replace
its original digest. Only its existing installed-schema fingerprint changes on
the ar6→ar7 schema transition. New provisioning leaves that fingerprint alone.
Deleting/restoring only migration_progress, stamping ar6 over ar7 or dropping
ledger tables loses authority and must refuse. A verified restore covers all
original and additive tables, metadata, catalog objects and matching encrypted
objects as one recorded recovery point.

## Exact additive schema surface

No fourth C04 table, native-v1 field, account-transfer table or provider-receipt
placeholder is introduced. Use explicit DDL, not the evolving application
metadata's `create_all`.

| Table | Exact ordered fields |
| --- | --- |
| `budget_accounts` (12) | id, organization_id, scope, scope_id, period_start, period_end, limit_microusd, held_microusd, accounted_microusd, project_id, job_id, opening_held_microusd |
| `provider_calls` (18) | id, project_id, job_id, logical_call_id, purpose, request_digest, price_version, state, reserved_microusd, usage_estimate_microusd, provider_request_id, created_at, organization_id, job_resource_kind, lease_generation, organization_account_id, project_account_id, job_account_id |
| `budget_entries` (9) | call_id, account_id, entry_kind, amount_microusd, evidence_ref, created_at, project_id, evidence_owner_kind, evidence_role |
| Added to jobs | lease_generation BIGINT NOT NULL DEFAULT 0; legacy_reserved_microusd BIGINT NOT NULL DEFAULT 0, populated explicitly for preexisting jobs |

Jobs then has **18** columns (13 original + 3 ar6 + 2 ar7),
below the unchanged 32-column catalog limit. IDs/digests/time/money and enum/text
lengths are exactly the frozen model. PostgreSQL uses bounded varchar, BIGINT
and timestamptz. SQLite explicitly checks native storage classes, integer range,
text byte/grammar bounds and canonical time representation; affinity or SQL
UNKNOWN is not validation. Do not erase BLOB or integer/real distinctions by
casting before the refusal test. Booleans are not money.

The catalog includes exactly the frozen primary/unique/composite foreign keys
and CHECKs, with stable ar7-prefixed names for new constraints. Important required
negative checks are:

- Non-null scope branches with exact identity equality; nonnegative balances and
  `held <= limit - accounted` after separately bounding accounted, avoiding
  arithmetic overflow. `opening_held` is immutable imported exposure, not added
  again on every read or assumed always <= held after a later evidenced release.
- One account per job for its immutable window, enforced by UNIQUE(job_id)
  in addition to the frozen scope/start unique key; non-job rows have NULL
  job_id. This implements the approved fixed window, not renewable job accounts. Organization/project periods never overlap for the same scope;
  endpoint equality is valid. Account identities, periods, limits and opening
  values cannot be updated or deleted through this slice.
- Actual job FK plus scoped job composite FK for provider calls; exact frozen
  organization/project/job account triple and organization ownership; constant
  job_resource_kind. Call created_at lies in each of its frozen account periods.
  An old call does not become invalid merely because the current time, lease or
  job generation later advances.
- Call request identity, scope, amount, price, purpose, generation, created time
  and three account IDs are immutable. The structural allowed state set remains
  reserved/dispatching/observed/uncertain/reconciled. No allowed state by itself
  grants dispatch or proves financial reconciliation.
- Entries have the frozen (call, account, kind) primary key, exact project/call
  composite FK, and account membership in that call's triple. Reserve amount is
  R and has no evidence; settle/release require non-null evidence and amounts
  within R. Every call has exactly three reserve entries, one for each distinct frozen
  account. Each present settle or release kind also has exactly three entries
  for those same accounts with equal amounts; a missing level is not accepted
  because the remaining amounts agree. Settle+release cannot exceed R. Entries are append-only in this slice.
- Evidence uses the exact nullable composite FK to
  artifact_refs(project, provider_call, call_id, artifact_id, budget_evidence).
  The existing ref/object FKs establish same-project closure. Missing, foreign,
  swapped-role or deleted evidence cannot be accepted. These relational checks
  do not authenticate an invoice, establish non-charge or authorize release.
- Original job legacy opening is immutable after initialization. A job's budget
  cannot be reduced below its provisioned job-account limit. Generation cannot
  decrease; increment/owner/status/database-time fence semantics belong to P2,
  not to a guessed rewrite of legacy claim/complete methods.

New implicit PK/UNIQUE indexes are captured exactly. Add only explicit lookup
indexes needed by the reviewed rules: provider_calls(job_id), the three frozen
account-ID columns individually, and budget_entries(account_id). The account
scope/start UNIQUE index supplies period lookup. No general indexing or existing
listing-index change is part of this slice. Final exact DDL/index names and
column orders are reviewed with the implementation before accepting its
literal catalogs.

## PostgreSQL executable inventory and SQLite equivalent

Propose exactly one zero-argument trigger function:

`public.ar7_ledger_constraint() RETURNS trigger LANGUAGE plpgsql VOLATILE
SECURITY INVOKER PARALLEL UNSAFE SET search_path = pg_catalog, pg_temp`.

Its body uses schema-qualified public relations and fixed SQL; no dynamic SQL,
external calls, role changes, security-definer authority or configurable path.
It dispatches on its exact trigger/table identity and refuses an unexpected
invocation. It validates only the affected immutable identity/ownership/period,
call triple and entry/evidence closure. Bounded candidate checks retain malformed
or duplicate candidates rather than filtering them into apparent absence.
Single identities use LIMIT 2, account triples have exactly three distinct
IDs, and an entry cohort reads at most ten rows to detect overflow beyond the
three kinds times three accounts. Period overlap uses an existence witness,
not a truncated sum; rollover exposure uses the separate complete bounded
account cohort. Parent job/scope checks read at most two candidate job accounts.
No per-account trigger scans all provider calls or recomputes all historical
entry sums: P2 and later reconciliation own atomic counter/entry transitions;
these structural checks do not claim to prove that accounting algorithm.

Exactly five noninternal constraint triggers invoke it:

| Trigger | Relation / event |
| --- | --- |
| `ar7_accounts_constraint` | budget_accounts AFTER INSERT OR UPDATE OR DELETE |
| `ar7_calls_constraint` | provider_calls AFTER INSERT OR UPDATE OR DELETE |
| `ar7_entries_constraint` | budget_entries AFTER INSERT OR UPDATE OR DELETE |
| `ar7_jobs_constraint` | jobs AFTER UPDATE OR DELETE |
| `ar7_scopes_constraint` | resource_scopes AFTER UPDATE OR DELETE |

All are FOR EACH ROW, DEFERRABLE INITIALLY DEFERRED, enabled in the ordinary
origin mode, with no WHEN clause or column-list shortcut. They recheck the final
transaction state; immutable OLD/NEW changes still refuse even if later reversed.
Parent-side job/scope changes must not invalidate existing job accounts or frozen
call ownership. Existing actual/composite FKs cover project and evidence
parent changes/deletes; test every reverse mutation, not only child insertion.
No trigger acquires a new project/organization exclusion lock after a job or
account row lock. Immutable-field rejection and relational validation are not
permission to mutate financial balances outside the participating protocol.

These checks alone do **not** prevent concurrent-owner overlap write skew.
Authorized account INSERT/identity/window/cap changes are restricted to drained
operator provisioning. Runtime account creation/identity mutation is denied at
the privilege boundary. The same exclusion covers every provisioning path;
there is no hidden online initializer. Trusted table owners/superusers could
bypass/disable constraints and remain explicit control-plane trust. Tests must
demonstrate that unsupported ordinary writers cannot do so.

The operator owns function/tables/triggers; PUBLIC has no function execution
grant, CREATE or ledger write grant. Grant the reviewed migrator table TRIGGER and function EXECUTE for creation,
as required by [PostgreSQL 16 CREATE TRIGGER](https://www.postgresql.org/docs/16/sql-createtrigger.html).
New functions initially grant PUBLIC EXECUTE by default, so revoke it within
the same creation transaction before any commit, following
[PostgreSQL 16 CREATE FUNCTION](https://www.postgresql.org/docs/16/sql-createfunction.html). For the later
restricted reservation role, enumerate SELECT access needed by invoker checks,
INSERT for call/scope/reserve-entry publication and UPDATE only the specific
balance/fence fields used by P2. P1 does not install or enable a worker login.
The reviewed synthetic reservation role receives explicit EXECUTE on this one
invoker trigger function, never PUBLIC EXECUTE or ownership. Before implementation,
a separately assigned actual-PostgreSQL permission probe must confirm the exact
creation/invocation behavior and denied direct privilege escalation. This is an
explicit entry acceptance gate, not executed evidence in this document. Failure
requires review of this entry, not a SECURITY DEFINER or broader table UPDATE
fallback. No caller can SET ROLE to the owner. Runtime cannot alter/drop
functions, change trigger enablement or set replica session behavior.

SQLite has no PostgreSQL deferred constraint-trigger equivalent. Keep **zero**
SQLite triggers/views; run equivalent bounded final-state/immutability validation
inside the same explicit operator or later ledger transaction before COMMIT,
alongside real CHECK/FK enforcement. Raw hostile SQLite owner writes are not
claimed to have deferred cross-table protection. SQLite remains local/test
fallback, not PostgreSQL concurrency proof. A later ledger transaction cannot
skip this validation because a caller labels itself trusted.

## Profiles and exact catalog policy

There are exactly **20** application/profile tables at ar7: the existing 17
plus budget_accounts/provider_calls/budget_entries. Preserve old literal profile
files and source fingerprints. Add separately captured
`sqlite_ledger.json` and `postgresql16_ledger.json`, with logical profile
`ledger_v1`. These filenames identify future artifacts; no hashes or catalog
captures are invented by this design-only checkpoint.

Both independent count gates must recognize the exact proposed revision:
`migrations/schema.catalog` (currently 17 tables) and
`migrations/service.migration_transaction` (currently LIMIT 18 / refuse >17).
Use bounded sentinel reads up to 21 and reject extras; do not allow arbitrary
20-table schemas under an older revision. During the explicit ar6→ar7 operator
transition, only the reviewed target inventory is permitted. The migration
transaction must not require ar7 before it can atomically create ar7.

Extend PostgreSQL catalog capture with exact function/trigger inventories:
schema/name/argument and result identity, language/body definition digest,
volatility, parallel/leakproof/security flags, fixed settings, owner binding,
ACL, trigger relation/event/timing/row/constraint flags/enablement/function target
and definitions. Bound before transfer: at most one allowed public function,
five noninternal public triggers, each function definition <=16 KiB, each trigger
definition <=4 KiB, combined executable metadata <=64 KiB. Unknown overloads,
extra/disabled/renamed triggers, altered body/path/ACL/owner or public rules
refuse. Trusted owner is bound to the validated installation/migrator identity,
not a literal developer role name or an ignored catalog field. Preserve catalog
rejection of unknown schemas, temp objects, views, RLS, partitioning and
unsupported extensions. No btree_gist extension or new dependency is proposed.

The old profiles continue to require zero public functions/noninternal triggers;
there is no broad whitelist shared by ar1–ar6. Captured ar7 profile must also
survive the existing verified dump/restore process without normalizing away
executable differences. If PostgreSQL deparses definitions differently, review
the exact observed equivalence, never a permissive text normalization.

Extend RevisionProfile/ReleaseProfile's explicit revision/profile sets and the
five-revision maximum to exactly six. ar7 remains `mode=migration_only`,
requires completed ownership, run_index and ledger_opening, and validates the
ledger manifest state before reporting the exact incompatible/migration_only
result. Invalid/incomplete ledger progress is not migration_only success.
The two-second runtime inspection, one-second pool and three-second connection
limits stay unchanged. Reading and validating the maximum 256/16 MiB manifest
history inside that two-second scope is not assumed feasible: actual maximum-state
inspection must prove it before that capacity is claimed. A history that cannot
be validated within the unchanged limits fails closed, even if below the stored
cardinality ceiling; no cached digest-only shortcut or timeout increase is
authorized. No ready profile, automatic migration or default
customer/provider activation is created.

## Initialization, opening and later periods

Under the existing migration lock, writer inventory/drain, schema-owner checks,
safe search path and all-table exclusion:

1. Verify completed ar6 for a new initialize, or exact ar7 for a known retry/
   provision, including ownership/projection/admission associations and the
   original source snapshot required for a new manifest. Require the installation's sole
   organization and complete scoped ownership. Resolve a known manifest replay
   before trying to install or provision again.
2. For initialization, require every preexisting job to appear exactly once as
   a manifest job account; no selective import. Support terminal historical
   succeeded/failed/cancelled jobs and unleased queued v2 jobs with reserved=0,
   valid ar6 config association and no owner. Terminal payload_version=1 jobs
   retain their legitimate NULL config fields and remain non-redispatchable;
   never invent a config for them. Version-2 jobs require their existing
   ref/digest/creator association, without claiming financial or execution
   evidence from metadata alone. Refuse running jobs, ambiguous live leases,
   unknown status/kind, missing scope or required v2 association, malformed native amounts,
   negative reserved or reserved > budget. Do not "repair" status, clear a lease
   or infer a window from current settings.
3. Compute each L_j from actual original jobs.reserved under exclusion. Check
   all sums for signed-64-bit overflow. Validate the initial org/project import
   period and exact assignment. Set job opening and held to L_j, accounted=0.
   Project and organization opening/held are the exact sums once per level.
   Limits must already accommodate the imported exposure; refusal never raises
   a limit. The 125000+85000+35000 fixture gives organization/project opening
   **245000**, three job openings, no provider_calls, budget_entries or new
   artifacts.
4. Execute explicit additive DDL, populate legacy_reserved_microusd and generation
   0, insert accounts and progress, validate final constraints/profile and
   re-hash the original five-table source. The original thirteen job columns,
   IDs/timestamps/audit/events/records/keys and encrypted objects stay unchanged.
   Triggers enforcing immutable opening are installed after the controlled
   backfill, within the same transaction, not temporarily disabled at runtime.
5. Update only installed_schema_fingerprint, force deferred constraints
   immediate for a precommit check, re-establish remaining native limits, and
   commit once. Report success only after acknowledged COMMIT and confirmed
   connection cleanup; deferred COMMIT work itself remains part of the bound.

Initialization supports at most 48 existing jobs in this bounded first slice.
A larger installation refuses before mutation, rather than dropping jobs,
splitting opening across partial commits or inventing a broader capacity claim.
A separate reviewed capacity change would be needed.

For later provision, initial opening never changes. New accounts start
opening=held=accounted=0; new jobs retain legacy_reserved=0. Existing accounts,
IDs, balances, periods and caps are immutable through provisioning. Reject a
second job account even with another nonoverlapping period. Reject reopening or
renewing an expired job window. Expiry refuses new claims/reservations/later
dispatch, but it never releases exposure or changes original call account IDs.

No reservation-time creation. Every rollover/provision command repeats the
same drained exclusion and extends the manifest chain. The installed bound is
at most **4096 accounts**; select/count 4097 before materialization and bound
the projected financial/identity cohort to **2 MiB** in SQL before transfer.
Exhausted history refuses safely. There is no deletion/compaction strategy in
this slice and no enterprise-scale throughput claim.

For a new org/project period, prove under exclusion that its current held plus
accounted plus **all older outstanding held for the same scope** fits its
approved cap. Old accounted charges are not silently billed twice in a new
period; unresolved old held is never forgotten. Later P2 reserves R only if that
same carried exposure plus R fits at all relevant scopes, as well as the job's
gross budget and immutable window. Nonzero unexpected future-period holds,
overlap, missing mapping, overflow or a history/work bound prevents proof and
refuses; no LIMIT may discard exposure. Crossing a period boundary does not
move balances or create transfer evidence. Positive rollover with affordable
old holds and negative cap/overflow cases are required; blanket prior-hold
refusal is not full C04 rollover behavior.

## Exclusion and implicit waits

Operator initialization/provisioning reuses the existing fixed migrator advisory
lock, pg_stat_activity visibility/drain check, disabled writer-role inventory
and schema/table ownership checks, then ACCESS EXCLUSIVE table locks. SQLite
uses the existing explicit BEGIN EXCLUSIVE protocol and process/OS drain.
These are controlled offline transactions, not a new online hierarchy exception.
Do not weaken those assumptions because a manifest is well formed.

Later P2 runtime order is original project exclusion first, then its organization
exclusion at the strength required for cross-project shared caps, then fresh
grant/key and target-scope/job locks, then all relevant account IDs sorted
deterministically. Choose organization strength before taking it; never upgrade
the existing SHARE lock late. A writer must not hold an organization lock and
then seek another existing project. Multi-project operator provisioning relies
on the stronger drained boundary rather than reordering runtime locks.
Legacy Database reserve/claim/complete_job are job-first and cannot be wrapped
by subsequently taking project locks.

Existing parent rows and offline exclusion serialize an absent account/period
key. No absent-row SELECT is itself a lock. Actual tests must observe the
second provisioner blocked/refused and then rechecking, not merely mock an
account lookup. Include implicit FK key-share, unique-index conflict, trigger
query and deferred-validation waits; a pre-insert "new ID" observation proves
nothing against an uncommitted collision. Timeouts and rollback cover all such
waits. No trigger or retry may acquire a new earlier lock to repair ordering.

## Bounds, outcomes and recovery

All proposed capacities are support limits requiring implementation evidence,
not observed performance. Preserve current source limits (one million original
rows, 1 GiB cumulative source bytes, 16 MiB per source row) and ownership closure
limits; they are outer refusal bounds, not a promise every such dataset fits
this smaller manifest or the time limit. Never materialize a body before its
SQL native type/cardinality/byte gate. Bound manifest/financial cohorts before
Python accumulation; canonical retention gets its own exact recheck.

The new operator command permits at most 2048 explicit SQL statement attempts,
including setup, catalogs, native setters, DDL, validation, progress and commit
preparation; at most 16 bind values per fixed statement. Use one-row DML
statements, with at most 16 statements in one application iteration; there is
no claim that sixteen complete account rows fit sixteen binds. Trigger-internal SQL is not observed by
SQLAlchemy cursor counters: its fixed affected-row candidate counts and actual
native-time tests must be reported separately. No server-side loop or full
unbounded ledger scan is hidden behind one charged statement.

Keep timeout_seconds integer 1..30, default 5; existing native lock timeout is
that value and statement timeout at most four times it. Add a request-owned
monotonic deadline of 120 seconds for this operator command, refreshing positive
remaining native limits before each statement and COMMIT. It may only tighten,
never enlarge those existing caps. SQLite native progress cancellation must use
the reviewed ownership lease, not replace another consumer's callback.
Connection establishment is separately governed by the existing connection
policy; no claim that an uninterruptible driver connect/close has a hard
wall-clock bound. Cleanup always runs despite exhausted work.

Reserve a finite explicit cleanup allowance within the command attempt ceiling
for rollback, detach/restore, invalidation and close/reclose; adopt the accepted
same-generation cleanup/outcome machinery where its semantics fit. Freeze the
exact attempt ledger with the implementation before acceptance. A counter
failure must not skip a native cleanup action, and no accounting path may reset
the request budget. This is an implementation gate, not a claim the current
migration_transaction already provides it.

| Observation | Operator result / next action |
| --- | --- |
| Invalid/unsafe manifest or conflicting immutable ID/digest/parent | Fixed invalid/conflict refusal, no SQL effects. A generic IntegrityError is not proof of a replay conflict. |
| Unsupported schema/history/privilege/executable/limit | Fixed incompatibility/refusal, no partial migration. Original operator evidence remains available privately. |
| Busy/statement deadline before COMMIT, acknowledged rollback | Fixed migration_busy/database_failure as appropriate; no completed marker or partial accounts. Preserve the original typed refusal/interruption through cleanup. |
| COMMIT attempted without confirmed result, ACK followed by cleanup failure, or uncertain disposal | New fixed ledger_outcome_uncertain at the operator boundary. Never report "rolled back" merely because a later rollback returned. No automatic replay that issues more writes. |
| Re-entry after uncertainty | Fresh drained inspection on a new connection: exact complete ar7 rows/manifest => original completion; exact intact ar6/no ar7 publication => safe known absence; mixed/unknown/corrupt state => refusal and reviewed recovery. |
| Process death before/after real COMMIT | Same SQL-only restart classification; no file-only receipt can authorize completion. |
| Unsafe downgrade or missing provenance | Refuse. Restore the verified consistent pre-change backup, including metadata/catalogs; preserve failed-attempt evidence. |

The existing migration_transaction maps DBAPI exceptions to fixed errors but
does not expose commit-attempt/ACK/cleanup truth. P1 must add a narrow ledger
outcome seam, preserving existing callers, before promising this table. No
source-level exception-string or silent retry heuristic is acceptable. Unknown
programming failures remain visible internally with safe operator output;
raw database strings, DSNs, manifest contents and evidence paths are not public.

## Required tests and review artifacts

The first independently reviewable implementation checkpoint is pure manifest/
progress validation plus explicit DDL and exact catalog capture on disposable
synthetic SQLite/PostgreSQL. It cannot activate a customer profile. The coherent
P1 checkpoint then adds operator exclusion, atomic opening/provision/recovery and
actual PostgreSQL evidence. Do not call a pure schema fixture completed
provisioning.

Required proof includes:

- Strict duplicate/control/UTF-8/numeric/size/version/ID/timestamp tests; valid
  maximum combinations and one-over bounds; same canonical whitespace replay
  versus changed immutable conflict; unsafe files/symlinks/permissions.
- Exact complete original-job coverage, terminal and queued-v2 controls, running/
  missing-window/foreign-scope refusals, native BLOB/REAL/boolean/infinity cases;
  integer 2^53+1 and overflow controls with no float arithmetic.
- The 245000 fixture, empty fresh installation, exact-once completed retry,
  changed manifest/source/parent, old progress preservation and zero fake
  call/entry/evidence rows. Original thirteen-column values and encrypted
  object hashes remain identical before/after and after restore.
- Actual deferred PostgreSQL rejection at COMMIT, then clean reuse; equivalent
  SQLite transaction-final refusal without a PostgreSQL claim. Scope-null SQL
  UNKNOWN, all cross-project/three-account/evidence candidates, reverse parent
  update/delete, immutable field changes and partial three-level entries.
- Exact20-table profiles and both count gates; old ar1–ar6 unchanged profiles;
  extra/modified/disabled function/trigger/ACL/path/owner rejection, restricted
  DDL/role/account-identity denial, no executable wildcard and no ready profile.
- Two actual provisioners for one absent key, cross-project shared organization,
  implicit uncommitted FK/UNIQUE waits, timeout rollback and no partial marker;
  positive/negative rollover with old holds retained and exhausted history.
- Every write phase fault, precommit constraint failure, lost COMMIT ACK, close/
  disposal failure, first interruption/primary denial, physical pool reuse or
  verified replacement. No source outcome is inferred from a generic exception.
- Actual child-process death immediately before COMMIT and after ACK, after a
  durable full-state barrier; independent SQL visibility, reaped process/backend
  drain, fresh connection replay, exact inventory and verified restore.
- Source-bound bounded SQL/native-work traces at supported maximum and
  substantial nonmatching history; refusal/cleanup on exhaustion without widening
  limits. Existing admission/GET/cancel/schema/package/privilege regressions.
- Literal SQLite/PostgreSQL catalog definitions and hashes captured from the
  implementation, a restricted-role grant inventory and rollback/restore
  evidence. Design text is not a substitute for these artifacts.

## Deferred producers and explicit limits

| Obligation | P1 representation / later implementation owner |
| --- | --- |
| Opening imported exposure and gross compatibility | P1 immutable opening/backfill; P2 adds new gross reservations without recharging L_j. |
| Same-scope old holds constrain a new period | P1 provisioning checks and retained IDs; P2 reservation recheck. No balance transfer here. |
| Fenced reserve/one-use dispatch permit | P2 minimum database-time/generation primitives; AR-010-B worker integration, AR-017 wider process/lease behavior. |
| Authentic charge/non-charge evidence | C04 relational slot/FK now; AR-023-A contract and AR-023-B actual durable provider observation later. Usage estimate is not evidence. |
| Atomic settle/release, over-bound incident and audited transfer/opening adjustment | Structural kinds/closure/immutability now; AR-023-C reconciliation paired with AR-023-A historical provenance/transfer contract. Never invent a provider_call to attach opening evidence. |
| Worker failure producer and observability | Existing AR-010-B and AR-012-B handoff unchanged; verifier is not producer. |

C04's mandatory deferred structural checks are included. Full financial-evidence
acceptance, transfer producer/storage representation and over-bound incident
handling are not claimed by reserve-only AR-010-A. Existing AR-023-A/C planning
must explicitly retain that handoff; it is not a new task or a backwards
dependency. No extra table or call-owned fake evidence is selected to conceal
the currently unimplemented historical reconciliation representation.

Entry decisions requiring exact review are the manifest/cursor schema and
capacities, drained-only provision boundary, named executable inventory and
restricted permissions, monotonic operator deadline/outcome seam, and literal
catalog implementation. Any discovered conflict with the frozen logical fields
or required ownership/evidence constraints must be reported before code, not
silently amended or hidden in a catalog allowance. P1 acceptance still requires
independent source/actual-dialect/package/hosted delivery and protected-main
candidate evidence; this document supplies none of those results.
