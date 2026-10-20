# Scoped run projection and resumable backfill

AR-006-A is a preparatory implementation. This document records the proposed
implementation contract; tests and runtime delivery remain pending. Customer
admission and live worker publication remain disabled. AR-010-A/B supplies the
missing generation/database-time fence, and AR-012-B owns integrated live-path
acceptance. Initial backfill is distinct from AR-006-C mutable repair and its restricted
audit, which depends on AR-006-A and AR-010-B before AR-012-B. AR-006-B owns
conservative current-job read suppression. This slice does not rewrite historical
audit or source rows.

## Schema and explicit transitions

`ar_0005_run_index` follows the accepted artifact revision. It adds
`projects.run_sequence BIGINT NOT NULL DEFAULT 0` with a nonnegative constraint,
and the C04 `run_index` fields. A physical `resource_kind` discriminator constrained
to `run` joins `(project_id,resource_kind,run_id)` to `resource_scopes`. The record
FK, unique `(project_id,run_id)`, same-project parent FK and unique
`(project_id,published_seq)` remain mandatory. Published sequences are positive.
The descending `(project_id,created_at,run_id)` index supports the later listing
slice; no cursor or route implementation is included here.

Explicit `initialize_run_index(engine)` validates completed ownership/current
catalog and installs empty projection metadata. It does not read artifacts or
require decryption/provider credentials. The existing install/adopt target stays
ar_0002. All supported revisions remain `migration_only`; old release profiles
refuse the unknown revision. Original catalog literals and source provenance stay
unchanged; new SQLite/PostgreSQL literals require independent review.

The schema transition records a bounded `migration_progress` phase `run_index`.
Its cursor contains only version, initialization time, frozen source/scope/order
identities, total/count/last run and verification digest. It contains no plaintext,
raw exceptions, paths, keys or customer names. Empty cohorts can complete without
an artifact reader. Nonempty cohorts remain pending until evidence is verified.

## Frozen cohort and verification boundary

`backfill_run_index(engine, source, batch_size=1000)` is an explicit offline
operator operation. The reader interface is
`source(project_id, owner_run_id, role, digest, max_bytes) -> bytes`.
It is internal operator evidence access, not a customer hash API. An explicit
local legacy reader will use the existing bounded ciphertext/decrypt utilities;
it never registers artifact objects/references or supplies a live adapter.

Before invoking that reader, validate every SQL run/job/study dependency and
actual project scope, including all ancestor ownership. Use the existing bounded
lineage rules for incomplete study trials. Missing/foreign/cyclic/ambiguous
lineage refuses with a fixed source-invalid diagnostic before any byte read.
Build deterministic parent-before-child order, using run ID to break ordering
ties. Parent IDs that sort after child IDs cannot bypass the parent FK.

Freeze the original source dataset digest plus a separate canonical scope digest
and ordered cohort digest at initialization. Verification binds each run's SQL
manifest, original creation value, owning job facts, logical event-reference
history and owner-specific verified artifact references. Evidence digests include
the source identity and verified graph identity. Deduplicated bytes never replace
owner-specific scope checks. Recompute source/scope/order identities before each
batch; late or lexically earlier records are a changed cohort, never silently
skipped behind a completed cursor. New publications use the separate writer
interface after backfill completion.

Artifact verification runs outside the mutation transaction and outside project
locks. Reuse complete-graph validation and shared bounded parsing for supported
partial captures; do not fabricate a publication/generation identity to make
legacy evidence resemble live fenced output. Verify event artifact SHA256 and
embedded chain hash separately, checkpoint/workspace/blob closure, ancestor
prefix ownership and terminal evaluation/final workspace when present.
Missing/corrupt/unsupported evidence produces a fixed evidence diagnostic and
leaves the cohort quarantined at its previous progress. It does not publish a
partial prefix, synthesize completion or claim that missing bytes are valid.

Retain compact projection/evidence metadata, discarding each graph's plaintext
before verifying the next run. Revalidate the complete frozen SQL source/scope
identity under migration writer exclusion before accepting any prepared evidence.
A stale capture is refused; preparation alone never authorizes a write. The
operator must supply a frozen, immutable byte source for the cohort. Evidence
proves the bytes read during preparation, not continued filesystem availability
at SQL commit: SQL revalidation cannot detect later external deletion or
reencryption. This is not filesystem/SQL atomicity; subsequent consumers must
still refuse unavailable or corrupt bytes.

## Bounds

The offline profile caps the cohort at 10,000 runs and 32 MiB of retained canonical
cohort/projection/evidence metadata. These are representation bounds, not measured
Python RSS. Existing stricter per-operation lineage limits still apply: 2,048
nodes, 4,096 edges, 64 ancestry edges and 16 MiB retained lineage metadata.
SQL row byte checks precede materialization; event identity rows remain at most
256 bytes, and record/job rows use the existing 2 MiB bound.

Each graph retains at most 64 MiB plaintext, 16,000 scoped references, 32,000 edges,
100 logical steps and 10,000 workspace entries. JSON has the existing 8 MiB bound.
An invocation additionally caps aggregate plaintext returned by the reader at
1 GiB and bounded capture SQL work at 250,000 statements. Metadata accumulators
are checked before insertion. No batch retains 1,000 full graphs. Progress is
bounded to 64 KiB; a write batch inserts at most 1,000 rows. Revalidating the
frozen cohort on resume is conservative offline work, not a throughput claim.
Diagnostics are fixed codes; no unbounded per-record error list is returned.

## Status and time

Interpret the actual finite stored numeric creation value as its exact binary
rational. Round rational microseconds to nearest with ties-to-even, then construct
a UTC timestamp. Reject invalid dynamic types, nonfinite values and out-of-range
UTC dates. Preserve the original SQL float without normalization or rewriting.

Verified terminal task failure (`success=false`) remains `complete`. Complete
redacted capture remains nonbranchable. Explicit execution failure remains
`failed`, with no invented terminal artifacts. A partial/running capture requires
verification of every committed logical event, allowing the documented one-event
lag without inventing completion; the index head is the last verified event hash,
not its artifact address. Legacy owner/lease fields do not establish a compatible
generation-fenced execution. Such running history is `incomplete` and
nonbranchable even if an old lease appears unexpired. The future live running
path must use current database time and the required compatible fence.

## Atomic batch and publication interface

Each backfill transaction uses existing migration writer exclusion, rechecks the
frozen cohort/evidence binding and the exact written prefix, and inserts the next
parent-closed batch. It advances project counters, rows and progress together.
Interruption rolls back all three; identical retry keeps row/timestamp/sequence
identities. Source history and installation/ownership provenance are unchanged.

`ProjectionPublicationWriter(delegate: PublicationWriter)` composes with the
accepted complete-graph coordinator. The delegate remains required and SQL-only;
`UnavailableLiveWriter` still refuses before source/storage access. The wrapper
uses the same connection for current fence, exact root inspection/publication,
projection insertion and artifact references. It cannot call legacy separate-
transaction `save_event`/`finish_run` methods. Initial insertion or exact existing
projection replay is supported; mutable repair is a later explicit integration.

Source producers must acquire affected owning job/run locks in consistent order,
then revalidate before any event/source/ancestry/by-job mutation. Complete source
graphs remain immutable. After source locks, allocate a new sequence by locking
and incrementing that project's counter in the insertion transaction and hold it
through commit. No artifact/journal/network I/O occurs under this lock. Do not use
preallocated database sequences. The same-project writer that began later cannot
commit a low pre-watermark sequence after a higher committed one; rollback leaves
no consumed counter. Independent projects do not share that counter lock.

## Required verification before acceptance

Use frozen legacy rows/ciphertexts/reservation totals, exact event heads and equal
creation times; assert preservation after each one-row batch and fresh-process
resume. Test orphan/cycle/foreign/missing ownership, source/scope/evidence drift,
late records, malformed dynamic cells, every declared bound, partial/failed/
redacted capture and deterministic time rounding. Failure between row/counter/
progress changes must leave no partial batch.

Actual PostgreSQL CI must cover reviewed literal catalogs and physical constraints,
least-privilege refusal, crash/restore/resume, autocommit refusal, shared-project
blocking/reversed scheduling/rollback, independent-project progress, and a
watermark excluding a later older-created publication. Run the actual graph
coordinator with the required synthetic future fence adapter to prove refs/root/
projection rollback and exact retry on one connection. Fixture execution is not
proof that the unavailable production fence exists. Installed-package smoke,
read-only revision guard, lint/type/security checks and independent source review
remain required; no production or customer acceptance is implied by this design.

## Source capture boundary

The operator path takes one consistent SQL read snapshot (PostgreSQL repeatable
read/read-only; explicit SQLite read transaction), retaining only the capped
cohort metadata. It closes that connection before invoking the byte reader.
Original row/cell preflight precedes the legacy parser; scoped lineage validation
precedes any artifact request. The internal project-only SQL reader is not a
public authentication context, and ordinary scoped repository authorization is
unchanged. Each run's graph bytes are discarded after verification; only compact
projection/evidence identities survive to the later SQL-only source recheck.

Actual interrupted Engine tests include an initial zero-event run, a proposal
failure with unreachable orphan checkpoints, and the separately committed event
which is one step ahead of its running or failed manifest. These preserve source
rows and classify conservatively; they do not fabricate terminal evidence.

Cohort captures are canonical immutable byte strings in a read-only association
map, with immutable run order and project tuples. Their per-run, project and byte
digests bind the cohort before the first reader callback. Only one capture is
decoded at a time; that representation and compact prepared metadata count toward
the combined 32MiB canonical-metadata bound. This is not a measured Python RSS
claim. Additive identity cells use dialect-aware SQL byte lengths before fetch,
including SQLite text containing embedded NUL characters.
