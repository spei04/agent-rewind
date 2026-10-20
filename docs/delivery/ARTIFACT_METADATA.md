# Scoped artifact metadata and format-1 storage

AR-009-A · preparatory implementation · customer admission remains disabled.

The C04 object graph is represented by `artifact_objects` and `artifact_refs`.
An object has an immutable server-selected ID, project, plaintext SHA-256,
format version, plaintext byte count, storage locator and UTC creation time.
The database uniquely identifies an object by both ID and
(project, digest, format version). References bind project, owner kind, owner ID,
object ID and a fixed C04 role. Composite foreign keys bind both the object and
the owner's `resource_scopes` row to the same project. Budget evidence additionally
requires a provider-call owner. The system sentinel has no customer ref.

## Authorization and storage boundary

The consumer must freshly authorize principal, project, action and actual owner
ancestry before invoking `artifact_metadata.resolve_ref`. That function performs
only a scoped SQL join on project, owner kind/ID, role and digest; missing or
foreign associations return no metadata. Resolving by a naked locator or hash
is unsupported. Consumers must recheck scope if it changes across storage I/O;
a retained descriptor is not lasting access authority.

`ArtifactObject` is frozen and validates IDs, digest, format, locator, size and
timestamp. The reader accepts the readonly structural `ArtifactDescriptor`
interface and snapshots/revalidates it into that frozen type before storage I/O;
this adds no authorization grant. `record_verified` inserts or verifies an exact prior row, including
ID and creation time; conflicting retries refuse without overwriting. Callers
must reuse the frozen metadata identity. `register_ref` inserts one scoped
association; an exact duplicate returns false. These are transaction primitives
for trusted code with a verified storage receipt, not public endpoints or proof
that a caller-supplied digest represents a stored object.

AR-009-B still owns upload/verify-before-transaction, complete reachable-child
registration, coherent root/job/event publication, interruption/orphan handling
and corruption integration. None of those paths is activated here. An object
write alone publishes no SQL reference or branchable result.

Immutability is enforced through insert/verify-only repository operations and
immutable local publication. There is no update/delete repository API. Trusted
SQL administrators can still alter rows; this slice does not claim database
UPDATE-denial triggers. Runtime identities must receive only the reviewed
privileges, with privileged repair handled separately. SQLite requires foreign
keys on **every** connection. `configure_artifact_engine(engine)` installs a
connect hook before first use; existing pooled connections are not silently
modified. Both write primitives refuse an FK-off connection, including one
already inside a transaction. PostgreSQL enforces the composite constraints.

## Encrypted storage protocol

`ArtifactStorage` defines `put_verified(metadata, bytes)` and
`read_verified(metadata)`. The local reference adapter uses the existing Fernet
format as version 1; it never changes the encryption key or re-encrypts retained
objects. New locators are `objects/<project_id>/v1/<digest>`. Explicitly registered
legacy `objects/<digest>` locators remain readable. Equal bytes in two projects
have separate object identities and new locators; a shared physical legacy file
still requires independent authorized references. Legacy writes are refused.

The caller must provide a plaintext limit, at most the existing 512 MiB workspace
configuration ceiling. This is an individual-object memory/read bound, not
streaming workspace reconstruction or a total-workspace claim. Metadata byte
count tightens the read further. The Fernet envelope bound is computed before
reading/decrypting; exact plaintext length and digest must match afterward.
Reads detect an excess byte, handle short reads, reject symlinks/FIFOs/directories,
and use directory descriptors to reject symlink traversal within the object path.
The readiness defaults remain exactly 4096 plaintext/5560 ciphertext bytes.

A new local write uses a private temporary inode, flush/fsync and non-replacing
hard-link publication. Concurrent losers verify the existing complete object;
a corrupt existing object is never overwritten. Failure can leave an unreferenced
complete object but cannot create a completed SQL root. Temporary files are
removed on handled failures; crash-orphan inventory and GC remain later work.
Fixed artifact error codes omit locators, ciphertext and cryptographic exceptions.

Successful write receipts separately report logical writes, actual local
write/read attempts, plaintext/ciphertext size and verified cache hit. An initial
missing lookup counts as an attempted read; a raced temporary write still counts
as work. These counters describe the local adapter. They are not S3/GCS billing,
modeled deduplication savings or complete distributed telemetry. No new cloud
storage adapter is implemented; the legacy `Artifacts` implementation remains
unchanged behind disabled customer routes.

## Explicit migration and recovery

Run the existing explicit migrator with target `ar_0004_artifacts` only after
`ar_0003_ownership` has completed with its original adopted or fresh intent:

```sh
rewind migrate upgrade --target ar_0004_artifacts
```

The migrator retains writer exclusion, owner authority, source digest, relational
closure and literal catalog checks. Installation and the updated installed
fingerprint commit atomically. Original rows, reservations, adoption mapping,
source provenance and historical catalog files remain unchanged. Reentry verifies
the existing revision; conflicting schema or metadata is refused.

The new tables start empty. No stored hash is guessed into an authorized owner
reference, and no legacy ciphertext is rewritten. Unregistered legacy roots
therefore fail closed until later verified reachability registration. The release
manifest remains `migration_only` with completed ownership required. Fresh schema
installation does not mean customer readiness.

A failed transaction leaves the previous revision. Downgrade is unsupported;
use a separately verified backup with a compatible inspection release. The
existing [recovery procedure](../RECOVERY.md) still requires separate preservation
of object bytes, encryption keys and global roles. The hosted synthetic restore
test is required to verify this catalog on the same pinned PostgreSQL cluster; it does not prove
production disaster recovery, cross-version restore or customer-serving rollback.

## Verification and limits

Tests cover SQLite composite violations and default-off refusal, exact/conflicting
reentry, concurrent duplicate object/ref operations, independent project identities,
bounded reads, nonregular files, corrupt-winner preservation, unchanged sentinel
limits and all 18 frozen legacy ciphertexts. Migration tests preserve the literal
14 historical rows and 245000 microUSD reservation total and reject partial
ownership or catalog drift.

PostgreSQL profile capture and acceptance use the existing pinned hosted
PostgreSQL 16 service. The first capture is diagnostic only; the literal profile
must be independently reviewed before the corresponding migration tests can pass.
Hosted evidence and independent source review are required before acceptance.
No provider calls, new infrastructure, customer data or broader admission are
authorized by these tests.
