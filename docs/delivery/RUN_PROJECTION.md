# Scoped run projection and resumable backfill

AR-006-A is a verified preparatory implementation. This document records its
implementation contract and the bounded acceptance evidence below. Customer
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

Explicit `initialize_projection(engine)` validates completed ownership/current
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
It is internal operator evidence access, not a customer hash API. The explicit
local legacy reader uses the existing bounded ciphertext/decrypt utilities;
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
projection replay is supported; matching replay also requires the current bounded
project counter to cover that immutable sequence. Mutable repair is AR-006-C.
AR-010/012 integration must implement and verify the same lock hierarchy for every
producer needing both project and job/run locks; legacy writers do not comply.

Source producers needing both lock families must acquire all affected project
locks in sorted order, then affected owning job/run locks in consistent order,
then revalidate before any event/source/ancestry/by-job mutation. Complete source
graphs remain immutable. The projection publication wrapper acquires the target
project allocation UPDATE lock before the delegate's job/fence lock and the
coordinator's grant/source SHARE locks. This avoids both shared-lock upgrades and
overlapping parent/child publication cycles. It increments that counter only with the initial row insert and holds the lock
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

## Explicit operator commands

`rewind migrate upgrade --target ar_0005_run_index` installs metadata and freezes
the scoped SQL cohort. It needs only the migration DSN. The following operation
requires a separately frozen legacy byte view and its local encryption key:

```sh
rewind migrate projection-backfill --source-root /private/frozen-run-source --batch-size 1000
```

The source root contains the retained `objects/<digest>` files. The command reads
`REWIND_ENCRYPTION_KEY`; PostgreSQL mutations require the separate
`REWIND_MIGRATION_DATABASE_URL`. No model, provider or identity-provider credential
is needed. Stop legacy writers and preserve the same immutable SQL/byte cohort
through every batch. Missing or invalid evidence refuses the entire batch.
Initialization and completion keep API/worker customer admission disabled.

## Acceptance evidence — 2026-10-20

AR-006-A preparatory run projection is Verified in PR #72 at reviewed source 46639c49502995870eb19faaea218b84a02a95ec. Hosted run 39497717028 passed 1596 tests on Python 3.11 and 1600 on Python 3.12, including all 21 new actual PostgreSQL backfill/publication cases. Three core Docker skips are covered by three passing gVisor cases; four sqlite3 transaction-mode cases are Python-3.12-only. Lint, formatting, strict types, contract/planning validation, dependency security audit, isolated package smoke and CI gate passed. A/B accepted the scoped runtime, transaction, catalog, test and diagnostic corrections. Frozen history, interrupted process recovery, backup/restore/resume, project serialization and publication rollback/retry have synthetic execution evidence. Live generation-aware publication, API listing, mutable repair/audit, customer admission and production acceptance remain gated. No model calls, new paid resources or partner data were used.

[Reviewed source 46639c4](https://github.com/spei04/agent-rewind/commit/46639c49502995870eb19faaea218b84a02a95ec) · [Hosted run 39497717028](https://github.com/spei04/agent-rewind/actions/runs/39497717028) · [PR #72](https://github.com/spei04/agent-rewind/pull/72).

The PostgreSQL recovery test restores a one-row projection checkpoint into a distinct clean database, compares projection rows/counters/progress and the frozen catalog, then resumes the original cohort. It preserves the 14 historical rows, 18 ciphertext objects and 245000 microUSD reservation total. Database roles and object bytes use the existing synthetic fixture in the same disposable cluster; this does not prove cross-region, key, role or customer recovery.

Incomplete backfill reports incompatible/backfill_incomplete; completion reports incompatible/migration_only. Review corrected SQLite transaction cleanup, byte-bounded progress/source reads, immutable capture binding, project-before-job lock order, allocator consistency and JSON catalog sort representation. Catalog literals retain their independently reviewed identities. The Python 3.11 crash-test pre-boundary writers_not_drained refusal in run 39496159334 has no proven cause; bounded child diagnostics were added, without retrying or weakening the production guard. Earlier restore-fixture/control-database and compatibility-assertion errors were corrected before acceptance.

Installed-package and synthetic fence tests do not supply the unavailable production generation fence. Final documentation composition still requires matching hosted checks before integration. Protected-main delivery must then pass, with its identity retained in an owner-readable release record outside disposable checkouts. A candidate package does not authorize deployment.
