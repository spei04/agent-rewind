# Complete run publication: preparatory implementation

AR-009-B provides a runnable complete-graph coordinator and scoped verified
consumer. **Live worker publication is unavailable.** The required adapter must
supply AR-010-A/B generation and database-time lease fencing; AR-006-A owns the
later event/run projection writer. The packaged `UnavailableLiveWriter` refuses
before SQL capture, source access or upload. There is no environment bypass,
owner-only fallback, schema change, customer admission or historical adoption.
Tests install explicitly synthetic future fence/root tables. Those tables are
not application migrations and do not prove a deployed live-worker integration.

`RunPublisher.prepare` authorizes the trusted authenticated project context,
captures bounded scoped run/ancestor/event rows, derives the graph, rechecks the
source identity, reuses existing project/digest/format object identities, and
freezes an immutable intent in the required private journal. Caller-supplied
source readers must enforce the passed byte limit before materializing input.
They are internal captured-byte adapters, not an unscoped customer hash API.

`publish` verifies every reachable object and performs verified put-if-absent
storage outside SQL transactions. It then uses one connection and transaction
for the required current fence, scoped authorization/source checks, immutable
object metadata, exact references and root writer. Inherited references must
already exist under their actual ancestor owner. The root is a run `result`
reference, with a distinct `publication_schema: 1` envelope binding publication,
project, run, job, worker, generation, manifest, ancestry and event identities.
It cannot be loaded as a legacy schema-1 workspace. The writer's SQL inspection
must additionally bind the complete immutable intent; root content alone is
insufficient evidence of this publication's commit.

The supported closure includes task, events, checkpoints, workspaces, file
blobs and evaluation. SQL event artifact digests, embedded event chain hashes,
previous/head links and actual ancestor owners are checked independently.
Checkpoints retain their owner's seed. Workspace byte content, mode, kind and
integer mtime (including negative timestamps) are preserved. Tool/action/state
payloads are opaque leaves, not arbitrary digest references. Incomplete runs,
unknown schemas, job/config/result root families, study attachments and provider
budget evidence are unsupported; no completion or branchability is invented.

`read` uses the existing scoped metadata resolver and verified bounded loader.
It checks descriptor size before storage, reauthorizes after each load, and
rechecks every owner/reference/descriptor after all graph I/O. A missing,
corrupt, unregistered or changed child is an explicit fixed error, never an
empty workspace. This is not a network-response linearizability guarantee.

## Durable retry and retained uploads

Provision a durable private journal root outside the artifact `objects` tree
before constructing `PublicationJournal`: owner-only directory mode 0700, with
its parent creation durably flushed by deployment tooling. Intent directories
and files are created with modes 0700/0600, no symlink following, one nonblocking
local `flock` per intent and exclusive numbered records. Files and parent entries
are fsynced. Accepted existing evidence is revalidated and fsynced before retry.
This is local filesystem serialization, not a distributed journal or lock.

`load_intent(context, publication_id)` reconstructs the exact frozen descriptor
IDs, timestamps and graph. It does not regenerate object identities. Retry first
performs fresh authorized SQL inspection of the complete root and every exact
reference/descriptor. An already committed attempt can be recognized after its
lease expires or job completes; all new writes still require a live fence.

| Observation | Required interpretation |
| --- | --- |
| Upload started, no verified receipt | Backend work UNKNOWN; never count it as zero |
| Upload verified, SQL absent/rolled back | Identifiable retained upload, not a published root |
| SQL commit pending or acknowledgement failed | Commit UNKNOWN until authorized exact SQL inspection |
| Exact complete root and references observed | Committed; no repeat upload needed |
| Different descriptor/root or changed frozen input | Conflict; never overwrite the frozen intent |
| Torn/gapped evidence, unsafe mode, cap or fsync failure | Refuse further work; preserve evidence for operator review |

Successful artifact receipts retain logical writes, backend read/write requests,
cache hits and plaintext/ciphertext bytes separately. Journal filesystem work is
not included in artifact backend counters. Failed/incomplete calls retain UNKNOWN
backend work; these receipts are not cloud billing or cache-savings estimates.
Absent SQL references do not authorize deletion. No garbage collector is supplied.
A new intent using a competing winner's descriptor is permitted only after the
old attempt is conclusively not published; uncertainty must be resolved first.

## Bounds and evidence

The preparatory profile allows 64 ancestry edges, 100 run steps, 10,000 entries
per workspace, 16,000 owner/role object references, 32,000 traversed graph edges,
and 64 MiB retained unique plaintext including the envelope. JSON objects are
limited to 8 MiB. Repeated paths count separately toward a workspace's logical
byte limit. These are representation/work limits, not a measured Python RSS
ceiling. Scoped SQL readers retain their existing stricter lineage limits.

Journal limits are 8 MiB for the intent, 16 KiB per record, 100,000 records and
32 MiB total intent plus record bytes. Enumeration stops at the count bound.
There is no background retry, scheduling, evidence repair or deletion API.

The local suite exercises actual synthetic Engine captures, failed parent and
successful branch graphs, immutable identity reuse, post-upload authority loss,
transaction rollback, durable intent reload and process death before/after SQL
commit. Opt-in PostgreSQL tests use the existing pinned disposable CI service
for transaction visibility, exact reentry, rollback and competing publishers.
Hosted evidence is required before acceptance; SQLite tests alone do not prove
PostgreSQL locking or the unavailable future production fence.
