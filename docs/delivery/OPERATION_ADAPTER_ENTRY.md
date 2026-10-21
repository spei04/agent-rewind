# Operation adapter entry checkpoint

Entry design for independent review. Its proposed limits and interfaces are not runtime acceptance. The separate PR #92 error-context correction is preserved at 8e935baa; this document changes no runtime source.

2026-10-21 · Design only, against accepted planning source `8382131ff70a92f8dd41fefa1eb7a9c8b33d340d` and runtime producer source `5d3ff3096d81f159a457870a1f4fa57590a06cc2`.
[AR-008-B #93](https://github.com/spei04/agent-rewind/issues/93),
[P1 #94](https://github.com/spei04/agent-rewind/issues/94) and
[P2 #95](https://github.com/spei04/agent-rewind/issues/95) were **Not started** at this entry-design checkpoint; see the [current P1 assignment](OPERATION_HTTP_EXECUTION_PLAN.md#p1-implementation-assignment--2026-10-21).
P1 runtime requires accepted AR-008-A/P3 main/candidate evidence and a separate
implementation assignment. This checkpoint adds no producer, schema, HTTP
route, available default adapter, profile, worker or customer activation.

The [two-package plan](OPERATION_HTTP_EXECUTION_PLAN.md) now estimates 6 [6–10] BE
days: P1 4 [4–7] and unchanged P2 2 [2–3], medium-low confidence. All outer
prerequisites remain unchanged. This document freezes a bounded initial
support table rather than assuming a stored-failure producer exists.
Frozen C04 remains authoritative; no wire field or error vocabulary changes.

## Interfaces and ownership

Proposed focused service in `agent_rewind/operation_service.py`:

```python
class OperationService:
    def __init__(
        self, engine: Engine, authority: RequestAuthority,
        *, artifact_loader: ArtifactLoader | None = None,
    ) -> None: ...

    def read_operation(
        self, principal: VerifiedPrincipal, context: ProjectContext,
        operation_id: str,
    ) -> OperationView: ...

    def cancel_operation(
        self, principal: VerifiedPrincipal, context: ProjectContext,
        operation_id: str,
    ) -> CancellationView: ...
```

`OperationView` is a strict ten-field value with the frozen names:
id, project_id, job_id, client_operation_id, status, cancel_requested,
result_run_id, budget_microusd, reserved_microusd, error.
`CancellationView` contains exactly operation_id, cancel_requested, status.
Use focused typed mappings or immutable validated values, not another resource
framework. The initial supported Operation always has error=null; there is no
new stored Error representation in this package.

These methods own their connections. Callers provide an authenticated
`VerifiedPrincipal` and original named-project `ProjectContext`; neither is a
lasting grant. Never reselect a changed legacy default. Methods enforce the real
runtime schema compatibility guard before customer rows. Test readiness is
instance-local and must not modify profiles or a global guard.

The read service owns short read-only SQL phases separated from one optional
artifact load. Cancellation owns one mutation transaction plus a short fresh
disclosure phase. Neither method calls readiness, registry/config resolution,
admission, a provider, Docker, or an unscoped Database read/mutation method.
No connection or lock crosses storage I/O.

Use `agent_rewind/operation_reads.py` only for the concrete bounded row/receipt
composition if that separates it clearly from service orchestration. Reuse:
- `admission_repository.py:AdmissionRepository.get_operation` semantics:
  project-viewer access, exact operation/config/job association; this is not
  creator-bound submit/reconcile. Its `StoredOperation` remains the identity.
- `admission_records.py:OPERATION_LIMITS`, `bounded_columns`,
  `operation_value`, `verify_job_configuration` and `scoped_descriptor`.
- `legacy_reads.py:LegacyReads/ReadBudget.matching_query` source and by-job
  receipt semantics, and the bounded descriptor columns in
  `published_reader.py` / `artifact_metadata.py`.
- `scoped_artifacts.py:ArtifactLoader` for validated format, locator,
  encryption, byte count and digest; no raw `Artifacts.json` fallback.
- `scoped_locks.py:lock_authority/lock_resource`,
  `admission_transaction.py:TransactionOutcome/admission_transaction` for
  cancellation only, and the existing fixed `job.cancel` audit semantics.

Budget-aware connection-bound helpers must cover inherited closure reads too.
If a small extraction is necessary to provide the same bounded operation
validation without an unaccounted `RequestAuthority.check(resource=...)`
closure, retain `get_operation` and other existing callers as compatible
wrappers. Do not bypass resource validation or silently treat the outer
service budget as covering an uninstrumented helper. Project authority may be
checked separately from the budgeted resource closure, preserving visibility
before action denial. No listing/cursor or new worker prerequisite is required.

## SQLite callback ownership amendment — accepted entry

This amendment responds to the independent first-checkpoint finding that a
clean transaction and a Connection.info marker cannot establish native callback
ownership: sqlite3 has no progress-handler getter. It is a design prerequisite,
not accepted implementation. B and the lead accepted exact entry 5bedede on
2026-10-21; C independently confirmed the complete acquisition map. The dormant
helper d1b7ce20 is independently accepted as a component after B/C source review,
67 lead tests and an original/corrected pool-substitution probe. C is assigned
complete caller integration with Database factory activation disabled. Activation
and dependent services require separate reviewed checkpoints. C retains overall P1 ownership. P1 remains In
progress, P2 Not started, and neither accepted-merge field changes.

The bounded implementation belongs in one dependency-light internal
`agent_rewind/sqlite_ownership.py` helper, narrow Database construction, and
the three known callback consumers: operation_work, listing_session and
migrations.compatibility's inspection scope. Explicit connection-context adapters
and the complete 33-site acquisition map below are also P1 work; the factory
cannot be enabled with that ordinary-caller integration omitted. No schema/profile/HTTP or global
SQL budget change is included. The current configure_runtime_engine SQLite
no-op cannot certify an existing Engine; PostgreSQL construction, pre-ping,
transaction settings and work=None behavior remain unchanged.

### Capability and lease interfaces

Proposed internal interfaces, whose names may be narrowed during source review:

```python
create_owned_sqlite_engine(url, *, connect_timeout, pool_timeout) -> Engine
require_owned_sqlite(engine) -> SQLiteCapability
acquire_progress(connection, *, owner) -> ProgressLease
owned_connect(engine) -> ContextManager[Connection]
owned_begin(engine) -> ContextManager[Connection]
cleanup_snapshot(receipt) -> CleanupVerdict
require_clean(verdict) -> None

class ProgressLease:
    def install(self, callback, instruction_interval) -> None: ...
    def release(self) -> None: ...
```

The factory creates an explicit file-backed QueuePool and tracked sqlite3
Connection subclass from birth, before dialect bootstrap. An opaque private
capability binds the engine, pool record, physical connection and checkout
generation. It is not a caller-supplied boolean, connection.info assertion or
retroactive certification. No foreign creator/DBAPI/pool is accepted. Reject
:memory:, empty SQLite URLs, memory/shared-cache URI modes, StaticPool and
untracked/custom engines at the new operation boundary. Existing untracked
CLI, migration and private readiness/probe paths keep their existing behavior
and explicit separation; they cannot be passed off as operation-owned engines.

Acquisition checks capability/generation and native state without SQL, before
any consumer PRAGMA, listener or callback change. A private per-physical-handle
lock serializes checkout generation, direct-handler attempts and lease state;
check_same_thread=False and the GIL alone are not ownership proof. Do not hold
that state lock across SQL or user callbacks. Acquisition atomically claims a
unique owner object; a known active lease refuses a nested borrower without clearing,
rolling back, invalidating or closing the outer owner's connection. The
borrower has acquired nothing and must not enter owned cleanup. No helper may
interpret that refusal as a reason to discard the active outer owner.

Only the matching live lease can install/replace/remove its callback through
the private native path. Partial installation is tracked before an operation
can fail; release is idempotent for that lease and must still attempt owned
removal after budget or provenance failure. Wrong-owner/stale-generation
release has no native effect. An ordinary direct Python set_progress_handler
call, including a clear, marks foreign/uncertain provenance and refuses
**before** replacing the native callback. This also covers a retained idle raw
reference; its next checkout is rejected/discarded. A direct attempt during a
live lease leaves that callback intact, but the owner must refuse success and
quarantine after its own cleanup. A refused direct call is a recorded
foreign-access attempt, not evidence that an unknown callback was installed:
the poison prevents later reuse because exclusive ownership was violated.
Unknown partial native install/remove is a separate, stronger uncertainty
state. No unknown callback is claimed restored.

This is cooperative in-process ownership, not a sandbox against malicious
Python. Explicit base-class/native bypass, arbitrary subclass mutation or C
extension access is outside the proof. Arbitrary retained raw SQL is not
intercepted: a live native transaction is detected, but committed raw writes
are not made safe or authorized by this mechanism.

### Construction, checkout and return ordering

1. Database selects the owned factory only for supported application file-backed
   SQLite. Install provenance/lifecycle hooks before first checkout. Factory
   construction gives a pristine no-handler connection to dialect bootstrap;
   the first and every later checkout must verify the recorded physical
   identity/generation and idle/untainted state.
2. Set **pool_pre_ping=False only on this owned SQLite pool**. The current
   Database pre-ping runs before SQLAlchemy's checkout event, so a checkout
   guard alone is insufficient. Do not move a SELECT/PRAGMA into the guard.
   A closed handle fails the consumer's first bounded SQL and is discarded;
   there is no transparent replay of request work. PostgreSQL keeps its
   existing pre-ping policy; untracked legacy engines are not reconfigured.
3. Set **pool_reset_on_return=None only on this owned SQLite pool**. Replace
   implicit pool rollback with explicit no-SQL lifecycle validation at reset/
   checkin. Native in_transaction must be false, no progress lease may remain,
   and provenance/generation must be clean. Unknown state, a failed property
   read, a retained handler attempt or an active transaction never returns a
   usable record to the pool. Do not silently rely on a clean logical
   SQLAlchemy transaction to prove clean native state.
4. Each ordinary caller still owns its SQLAlchemy Connection/transaction
   cleanup. SQLAlchemy Connection.close may roll back before pool events;
   disabling pool reset does not disable that behavior. The proposed tracked
   native rollback guard therefore refuses before native execution while a
   progress lease is live or a partial install/remove leaves native state
   unknown. A refused direct handler attempt alone, with a known empty native
   callback, does not block mandatory rollback; it still forbids reuse.
   Opted-in commit remains the owned, budgeted transaction path. Opted-in work removes
   owned callbacks/listeners before rollback/settings restoration/close.
   Mandatory native cleanup is independent of exhausted counters or accounting
   errors, and BaseException cannot skip the remaining bounded attempts.
   Lifecycle hooks perform no restoration SQL and cannot certify settings that
   a consumer failed to restore. Connection.close can stop before releasing its
   pool record when rollback refuses: supported callers must still detach their
   own lease, invalidate/discard and finish bounded close. Prove pool
   checkedout=0 and physical replacement under this exact fault; a checkin hook
   that was never reached or eventual GC is not cleanup evidence. A nested
   borrower must never call this cleanup against the active outer owner.
5. A dirty return is quarantined: remove its physical handle from eligibility,
   invalidate/discard it and refuse successful reuse. Active lease on return
   means the owner has incorrectly released its checkout; this differs from
   refusing a nested borrower that still holds the outer checkout. Physical
   close may abort a remaining transaction; never report that as acknowledged
   application rollback or commit. If close/discard itself fails, retain the
   quarantine and make bounded cleanup attempts without a new SQL operation,
   infinite retry or returning the handle to the pool. Report cleanup failure;
   do not promise resource reclamation when the driver repeatedly fails.
   Reset/checkin guards must not throw before returning or retiring the pool
   record; quarantine/error state is retained separately and the checkout is
   released. Partial invalidation and a second close need bounded fault tests;
   no pooled handle may become eligible merely because reporting failed.
6. Compatibility inspection uses the same lease on owned engines and completes
   its entire rollback/restoration/release phase before operation work starts.
   It may not nest a callback scope under operation/listing work. It retains
   its separate bounded budget and actual migration-only guard. Existing
   untracked inspection paths remain explicit legacy behavior, not ownership
   evidence. Checkout guards/lease checks run before native effects in every
   owned compatibility, listing and operation path.

Before disabling reset, source review must inventory **all** callers of the
Database-owned engine, not just the three callback installers: Database
connect/begin methods (record/event/job/key/audit reads and writes), initialize/
upgrade/install, ping/compatibility, Auth/RequestAuthority/scoped repositories,
ScopedActions, published/legacy/scoped-list readers, artifact engine hooks and
admission repositories/coordinator transactions. Preserve their successful
commit/rollback/close behavior and prove each returns native idle without a
lease. Raw BEGIN helpers need native-state tests because SQLAlchemy may not
know their transaction. Lifecycle validation does not require hardcoded
default PRAGMAs: configure_artifact_engine deliberately retains foreign_keys=ON,
and migration setup may retain an operator-selected busy_timeout. Each scoped
consumer restores its own saved settings; migration/projection and ordinary
caller regressions prove that policy is preserved. Retained raw SQL/PRAGMA
mutation is unsupported and cannot be detected beyond native transaction
state; no setting-restoration guarantee is inferred for that path.
Worker disposal must not reintroduce a dirty record;
checked-out owners keep their cleanup obligations. Do not silently reconfigure
the separately constructed readiness worker, CLI engines or arbitrary tests.
If this inventory exposes an incompatible caller, report it before widening the
factory boundary or enabling a fallback.

### Retained cleanup verdict and ordinary callers

A successful callback release proves only removal of that callback. It does
not prove Connection.close, pool return or physical disposal succeeded.
The factory and helpers retain one private CheckoutReceipt per checkout
attempt/generation, separate from the reusable pool record. Internal lifecycle
observations are mutable and finite; cleanup_snapshot returns an immutable
verdict with no raw exception text. No verdict grants authority.

Before engine.connect, the helper opens a private request-local checkout-attempt
scope. The attempt exists even if no Connection is yielded. Factory creation
and pool checkout bind any obtained physical handle/record to this attempt and
generation before bootstrap or customer SQL. A bare acquisition on the owned
factory without this scope is unsupported and refuses; it must not silently
bypass the final-verdict obligation. Use an ordinary context-local stack,
not a shared global current-owner variable. A failed guard must not request
SQLAlchemy's transparent disconnect/retry path.

For an early timeout/refusal with no handle acquired, the attempt records
verified no-acquisition. Once a physical handle or pool record is obtained,
failure before yield requires observed return or quarantine/disposal and
pool-slot release. Creation/bootstrap/checkout hooks must retain the attempt
identity through these errors. Neither the absence of a yielded Connection
nor a log line proves cleanup. A missing terminal observation remains failure;
bounded disposal is still attempted without GC or an infinite retry.
Distinguish creation/connect-hook failure before checkout from engine_connect
failure after a pool proxy was obtained but before Connection construction
returns. Retain enough public checkout-proxy ownership in the attempt to
release/dispose that latter proxy; a pool record alone is not proxy cleanup.
Both stages need independent injected-failure proof, including a secondary
close failure and checkedout=0. Do not rely on constructor cleanup or private
SQLAlchemy overrides.

Reset/checkin hooks record idle return, quarantine and failure without throwing
before record return. The tracked native close method records attempted/returned/
failed disposal on the matching generation before rethrowing, so a driver
exception that SQLAlchemy subsequently logs or suppresses remains visible.
An event exception before native close leaves disposal unconfirmed. Keep
physical-disposal evidence distinct from pool-slot release; close is not an
acknowledged transaction rollback. Single injected failures must demonstrate
checkedout=0 and replacement; repeated driver failure remains explicit
unreclaimed-resource uncertainty, never eligibility for reuse.

After Connection.close returns, the owner takes the immutable snapshot and
requires: close acknowledgment, the expected terminal pool return or clean
disposal, no live lease and no latched cleanup/provenance failure. The check
does no SQL, callback change or pool lookup. It reads the retained attempt,
not whichever generation now occupies the record. A concurrent next borrower
cannot erase this outcome; late/stale observations cannot affect the new
borrower. If close raises, or terminal proof is absent, no successful result
is possible even if the record later appears idle.

owned_connect and owned_begin are narrow context managers using public
Engine/Connection operations. They pass through PostgreSQL and explicitly
untracked engines unchanged. On owned SQLite they establish the checkout
attempt, preserve the existing transaction semantics, close and inspect the
receipt before yielding a successful context exit. No Engine facade,
SQLAlchemy private connection-class override, global monkeypatch or arbitrary
engine certification is allowed. owned_begin must retain whether commit was
attempted/acknowledged; postcommit close failure cannot be reported as a known
rollback or trigger automatic replay.

Manual session owners use the same private attempt/receipt primitive around
their existing connect/cleanup sequence, not a second context that commits or
closes behind their outcome state. They retain the receipt before release and
check it after their bounded close attempts. Existing primary typed denial or
BaseException survives secondary cleanup failure; without a primary, read
cleanup failure maps to fixed dependency_unavailable. Cancellation before
commit with acknowledged rollback and proven cleanup retains its known-failure
mapping; attempted/acknowledged commit plus cleanup failure is outcome_uncertain.
Ordinary mutation callers preserve their existing safe boundary and never
return success or claim rollback after commit acknowledgment. The wrappers
must not invent a retryable error to hide that uncertainty.

The owned-engine requirement belongs at the future OperationService entry,
before its first SQLite acquisition, including the separate schema compatibility
probe. Its low-level component helpers may retain explicitly untracked legacy
and test paths; those paths do not certify ownership. Optional lease selection
returns no lease only for a genuinely unregistered engine. A known owned engine
whose current pool loses provenance must refuse before effects and must never
fall back to the untracked path. PostgreSQL retains its existing behavior.

Failed nested lease acquisition is different: it returns no lease or ownership
receipt for the outer Connection and must perform no outer cleanup. The
already active owner retains its original receipt. A successfully acquired
lease whose install later fails does own removal/cleanup. An ordinary checkout
that succeeds but later fails to acquire its own lease still owes its own
checkout cleanup; this does not authorize cleaning a borrowed active owner.

### Exact acquisition map and integration gate

The immutable a59e074 source contains these **33 acquisition sites in 14
modules** (a conditional begin/connect expression is one site). Preserve
public behavior and existing local context boundaries; only the necessary
mechanical acquisition/final-verdict adaptation belongs here.

| Module | Sites | Required boundary |
| --- | ---: | --- |
| database.py | 18 | Use owned_connect/owned_begin through narrow private Database contexts for every record/event/job/key/audit method; no bare factory acquisition remains |
| artifact_publication.py | 1 | Preserve its read/write conditional transaction owner with the corresponding wrapper |
| auth.py | 1 | Existing credential SELECT context uses owned_connect; failure cannot return an authenticated result |
| cli.py | 1 | The Database-backed context uses owned_connect; this is distinct from separately constructed operator engines |
| migrations.compatibility.py | 2 | Connectivity and inspection use owned_connect; inspection releases its lease/settings before context close and final verdict |
| migrations.service.py | 2 | Wrapper preserves explicit operator transaction/retained-PRAGMA policy; untracked operator engines remain pass-through |
| projection_source.py | 1 | Wrapper encloses existing read snapshot/restoration, then checks final cleanup |
| published_reader.py | 1 | Existing read-phase owner uses owned_connect; final cleanup precedes result |
| request_authority.py | 1 | Existing authority context uses owned_connect; no accepted decision after failed cleanup |
| scoped_actions.py | 1 | Existing mutation owner uses owned_connect without changing commit/rollback/uncertainty observations |
| scoped_repositories.py | 1 | Existing shared repository context uses owned_connect |
| admission_transaction.py | 1 | Manual owner retains/checks the private receipt with its TransactionOutcome, including work=None |
| listing_session.py | 1 | Manual owner retains/checks receipt after callback/settings/rollback/close cleanup |
| operation_work.py | 1 | Manual owner retains/checks receipt across read phases and optional transaction work |

The count is an audit baseline, not permission to ignore a new caller. Recheck
all acquisitions at the exact implementation source and fail the integration
gate if an owned-factory path remains bare or lacks a final verdict. Helpers
receiving an existing Connection must not close it or consume its owner's
receipt. No runtime raw_connection acquisition was found in this map; such
direct access remains unsupported on the owned factory. Engine-bound
inspect/reflection/metadata create_all/drop_all would also bypass the wrappers
and is unsupported unless supplied an owned Connection. The audited catalog
inspection and Alembic migration environment already consume a Connection;
preserve that boundary rather than create a second checkout.

Separately constructed CLI/migration, readiness-worker and private probe/test
engines retain untracked behavior and are not certified by these wrappers.
Database-backed CLI/migration calls in the table are covered. Other indirect
Auth/repository/coordinator/worker consumers inherit the mapped boundary;
their tests must establish that inheritance. Arbitrary external raw handles
are not a supported ordinary caller. This complete adaptation is an entry/
acceptance obligation, not a promise supplied merely by installing pool hooks.

### Required independent proof and reforecast

Use owned file-backed QueuePool(size=1, max_overflow=0) tests and preserve
legacy/untracked control cases. Prove:

- compatibility, listing and operation permutations reuse a clean physical
  connection with original timeout/query_only settings and no surviving
  callback; compatibility completes before operation work;
- nested acquisition changes no callback, SQL, settings, transaction or outer
  close state; wrong-owner/released-generation handles cannot clear a lease;
- direct handler/clear attempts and retained-idle references refuse, taint and
  force replacement; no unknown callback restoration claim;
- checkout executes no pre-ping/guard SQL, and reset performs no implicit SQL;
  active native transactions, raw BEGIN, dead handles and uncertain property
  reads are quarantined, with successful replacement after bounded cleanup;
- premature Connection.close while leased refuses implicit native rollback;
  supported cleanup still releases the pool checkout without GC, preserving an
  unrelated active outer owner on nested acquisition refusal;
- partial acquire/install/release, callback exceptions, exhausted accounting,
  restoration/close/discard failures and BaseException preserve original
  denial/interruption and still attempt remaining cleanup; no success follows
  unconfirmed cleanup or post-ACK failure;
- reset/checkin failures observed only after close refuse read/cancel success;
  native close failures remain recorded even if library logging suppresses
  them; a later checkout cannot overwrite the retained earlier verdict;
- early creation/bootstrap/checkout refusal proves no acquisition or terminal
  slot release/disposal without a yielded Connection; every mapped ordinary
  context observes a failed verdict and preserves an existing primary;
- ordinary Database and all shared-engine callers above preserve transactional
  behavior, including work=None and initialization; unsupported/custom/memory
  operation engines refuse without changing legacy callers; PostgreSQL
  settings, restricted roles and existing timeout/cleanup tests remain intact.

These are implementation gates, not evidence already supplied by a clean
transaction or passing fixture. Add actual installed-package/provenance smoke
for the new internal helper when it exists; no package bytes change here.
The first ownership draft estimated P1 at 3 [3–5]. Explicit post-close
verdicts and the 14-module caller adaptation cannot remain implicit in that
one-day increment. P1 is now **4 [4–7] BE days**, medium-low, versus the original
2 [2–3]. P2 stays 2 [2–3]; aggregate AR-008-B becomes **6 [6–10]**. No additional task, package, outer edge, activation or
resource is introduced. If safe ordering cannot be demonstrated within this
boundary, return the finding rather than certify an arbitrary engine.

## Concrete limits

These are proposed service refusal limits, not measured throughput promises.
They are deliberately below generic multi-graph limits and do not expand them.
One request shares the same budget across preflight, post-I/O, final comparison,
authority/closure rechecks and cancellation disclosure.

| Dimension | Limit and enforcement |
| --- | --- |
| Logical target | One operation and its original associated job; no list scan to discover a result |
| Descriptors | One required admission_config descriptor and zero or one result descriptor; no configuration/workspace/event body read |
| Result plaintext | At most 4,096 bytes and one loader invocation; descriptor size is checked before calling the loader, whose actual ciphertext/plaintext allocation must obey that bound |
| Operation SQL row | Existing per-cell OPERATION_LIMITS; at most two candidate rows, with invalid/overflow candidates retained as markers |
| Associated job SQL row | All 16 fields, at most 4,096 bytes in aggregate; per-cell caps below, preserved SQL NULL/type information |
| Record source body | Existing 2 MiB per-record ceiling, reduced to remaining request byte budget before transfer/JSON decode |
| Cumulative source work | At most 256 record/job row visits, 512 lineage edges and depth 64; repeated validation counts again |
| Retained original receipts | At most 4 MiB canonical encoded input in total, including operation/job/config/ref receipts; no separate uncounted receipt domain |
| SQL statements | At most 512 cumulative statements after the separately bounded schema guard; include authority, closure, timeout/setup and final checks |
| Final statement | At most 259 expected identities: 256 source identities, one operation and two descriptors; LIMIT expected+1 (maximum 260), at most 64 bound parameters |
| Final returned data | Only domain tag plus bounded identity, at most 64 bytes per row and 16,640 bytes total; compare expected cardinality and identities |
| Response | At most 2,048 canonical UTF-8 bytes; all required null/false fields remain present |
| SQL-active work | At most 10 seconds accumulated across SQL phases; PostgreSQL statement timeout no more than min(5 seconds, remaining), lock timeout min(3 seconds, remaining); SQLite also at most 20 million cumulative VM instructions |

Job cell caps in bytes: id 32, kind/status 20 each, created/lease_until 64 each,
payload/result 64 each, owner 64, cancel/payload_version 8 each,
budget/reserved 24 each, error 1,200, actor 256,
execution_config_ref/execution_config_digest 64 each. Check all before transfer,
including SQLite embedded-NUL and dynamic BLOB/type cases; avoid Boolean
decoding coercing malformed cells. Budget and reserved must be strict integers
with budget>=1 and reserved>=0; no float conversion, invoice calculation or
assumption reserved<=budget. Preserve original raw source/type/null receipts.

Read phases use ordinary read-only transactions, not SQLite BEGIN IMMEDIATE.
Supported DBAPI modes must be checked before starting; PostgreSQL is READ
COMMITTED with local search path/read-only/timeouts, SQLite owns a query_only
snapshot and progress handler only for that checkout. Remove owned hooks,
restore settings and roll back/close on every path; invalidate/discard when
cleanup cannot be confirmed. The narrowly owned SQLite pool lifecycle above is
the only engine-policy exception; do not steal another session's callback. Admission's mutation transaction is reused
only for cancel through the optional work scope below; the current helper alone
does not enforce this service's cumulative limits. Native timeout/progress exhaustion fails closed, and successful
phase exit also checks the cumulative clock. Storage duration is not covered by
this SQL-active budget; no end-to-end timeout or filesystem latency guarantee is
claimed. No background timeout thread or event-loop bridge is introduced.

Supported-limit tests must execute actual matching mixed receipts and real
PostgreSQL SQL, with deterministic instruction/query ceilings. Over-count and
encoded-byte checks precede rowset construction/indexing. If implementation
cannot meet these limits, return the concrete measured finding for review;
do not widen limits or substitute partial responses to get a green test.

## Initial status, result and error support

Validate operation/config/job identity and job types before this table. The
current viewer can differ from the operation creator; config actor must still
equal the original creator. There is no `operation` resource_scope kind:
operations bind to their actual job and its existing project/job scope.

| Job status | SQL jobs.error | Initial behavior |
| --- | --- | --- |
| queued or running | NULL | error:null; keep validated execution status and cancel boolean |
| succeeded | NULL | error:null; preserve succeeded even if evaluator success=false |
| cancelled | NULL | error:null; cancellation alone is not invented failure evidence |
| failed | NULL | 503 dependency_unavailable: required safe failure evidence is absent |
| Any recognized status | Any non-NULL value, including JSON-looking text or an empty string | 503 dependency_unavailable; do not parse or expose legacy error text |
| Unknown status, malformed types, contradictory operation/config association | Any | Refuse before rendering; no partial response |

This is an explicit initial producer decision: **no stored Error envelope is
supported**, because none of the current producers writes one. In
`worker.py:work_once`, the exception path produces a fixed exception-class
string, and `database.py:complete_job` stores that string in jobs.error.
`admission_repository.py:insert_operation` persists the admission origin in
operations.failure_correlation_id; that ID proves neither an error code nor a
safe four-field envelope. A non-null ID cannot promote legacy text to a trusted
failure. NULL correlation does not by itself block a healthy error:null row,
but cannot support failure data.

Do not fabricate a migration marker, correlation, failure code or error:null
to make a failed row renderable. No status GET writes anything. Later support
for a real bounded stored envelope requires the owning producer/representation
review and actual producer vectors; it is not implemented by this entry.
When such support exists, a verified stored outcome_uncertain is HTTP 200
Operation data with its persisted original request_id, while each poll still
has a fresh X-Request-ID. Until then, its JSON-looking jobs.error text refuses
exactly like other unsupported text. No synthetic positive may imply an
implemented worker producer.

The producer handoff is owned by AR-010-B: P1 freezes and implements the
complete bounded version/encoding/provenance/parser and consumer extension,
including an operator-only idempotent historical-marker policy preserving
original rows/bytes, audit and ciphertexts; P2 integrates both completion and
lease-expiry producers under their distinct fences. Current jobs.error
String(300) neither proves encoding fit nor truncates safely. If P1 needs
additive DDL, its owner/revision, captured catalog and preservation/rollback/
restore evidence must be decided before code, with broader work reforecast.
No reverse AR-008-B prerequisite is added: the initial refusal table above
remains valid until accepted producer evidence supports the consumer extension.
AR-011-C consumes the completed producer and AR-012-B verifies integration;
neither owns this missing producer implementation.

Result handling is independent of error:null on supported rows:
- SQL NULL jobs.result becomes result_run_id:null without storage I/O.
- A non-null digest requires exactly one matching same-project job-owned
  role=result reference and format-1 object. Enumerate the owner/role candidates
  before filtering malformed/digest-mismatched candidates; zero, multiple,
  foreign or invalid associations refuse, not first/latest selection.
- Freeze all seven descriptor fields: id, project_id, digest, locator,
  format_version, byte_count, created_at. Verify bytes through the loader,
  including digest/length, then strict UTF-8 JSON with no duplicate keys and
  exactly `{"run_id": <32 lower-hex characters>}`.
- Prove the scoped run's relational lineage and run.job_id equals the operation's
  original job_id. No records.by_job/run_index heuristic substitutes for this
  link; no complete/branchable/evaluator outcome is inferred from the ID.
  This endpoint does not claim graph replay/completion verification.

Unsupported failure data is rejected before result storage work. The requested
operation and its original associated job form the primary visibility boundary:
missing/inaccessible operation or original job ownership is not_found (404)
before result I/O. Once that boundary is established, the optional result run
and its ancestors are secondary evidence. Missing, inaccessible/foreign,
corrupt, over-limit or mismatched secondary run/ref/ancestor evidence is
fixed dependency_unavailable (503), including ResourceNotFound raised only by
that secondary proof. Never disclose a partial result ID.

Keep fresh principal/project authority calls outside this secondary-proof
translation. On secondary evidence failure, recheck the caller's current
original-project authority before emitting 503; a revoked caller must retain
the typed 401/403/404 denial. In particular, revocation during result I/O is 404,
while a still-authorized caller with foreign result/ancestor evidence gets 503.
No broad ResourceNotFound catch may turn authorization loss into dependency.

## Original receipts and final read phase

Preflight retains the validated original operation row (all bounded fields,
including accepted_response, config digest, creator and failure correlation),
all 16 original job fields, common configuration association and its seven-field
descriptor, plus the optional original job/result descriptor/ref identity.
Use the original values as expectations; later SQL never replaces them.

Every run/job/ancestor loaded through lineage and every discovered by_job
membership joins the same request receipt budget. The final phase has no more
storage. Compose **one bounded SQL statement** from the original source
receipt query plus operation/config/ref domains. A materialized bounded
JSON/JSONB rowset and exact primary/composite-key joins avoid correlated
repeated scans; retain the existing by_job anti-join for unexpected members.
Compare original source bodies/type/null fields, every owner/scope, operation
association and all seven descriptor values, including created_at. Also check
candidate cardinality so a new malformed/extra config or result ref cannot
disappear behind a digest filter. Return only bounded matching identities;
missing, substituted, duplicated or extra identities refuse the whole response.

Fresh project read authority on the same original context follows the statement.
No later artifact load or protected data query is allowed before returning.
This is optimistic revalidation at READ COMMITTED, not a response-linearizability
guarantee. A single Connection alone does not create a snapshot across statements.

## Cancellation transaction and disclosure

Cancellation deliberately does not render results or failure data. It may
cancel a visible failed job whose status view is unsupported; no storage read
or error-string parse is needed.

1. Perform bounded current project/read visibility and retain the original
   operation/config/job association. Foreign/unknown operation is not_found
   before cancel action classification; an accessible viewer is forbidden.
2. Own one `admission_transaction` and `TransactionOutcome`. Acquire
   project UPDATE exclusion, organization SHARE, current caller membership
   SHARE, caller key scope/key SHARE when applicable, then original target
   job scope SHARE and job UPDATE. Use the established project-first hierarchy.
   Lock the exact scoped operation row within this transaction as well
   (SHARE is sufficient for an immutable association), then compare it with
   the original operation/config/job association. No operation-row lock may
   precede project exclusion. A changed association is refusal, never permission
   to cancel a replacement job.
3. Revalidate current config association and cancel authority on the same
   Connection immediately before effect. Retain membership/token expiry and
   role-ceiling checks after lock waits. Ordinary administrative UPDATE/DELETE
   of held grant/key/scope/operation rows must block through commit.
4. Set cancel=True. Only queued changes to cancelled; running and all terminal
   statuses retain their status. Preserve result/error/owner/lease/budget/reserved.
   Persist exactly the existing fixed `job.cancel` audit targeting the same job
   with the current actor. Capture the three-field response from that effect.
5. Return no success before acknowledged commit and confirmed cleanup. Perform a
   bounded fresh disclosure check of original operation/config/job association
   and current cancel authority. A worker may advance status after commit; do
   not reject an otherwise valid committed snapshot merely because execution
   progressed, and do not substitute the new worker status for the captured
   Cancellation response.

Extract only a narrow connection-bound cancel effect/audit helper from
`scoped_actions.py:ScopedActions.cancel` if needed. Its existing public
`cancel(principal, context, job_id) -> None` retains its transaction, behavior
and callers; operation cancellation must not call it after a separate lookup.
No generic action framework or legacy transaction refactor is part of P1.
Repeated cancellation requests may record repeated fixed intent audits, as
existing behavior does; they never refund reservations or dispatch work.

### Cancellation work scope and cleanup

The existing admission helper has native per-statement/lock timeouts, but no
aggregate clock or SQL-count hook. The proposed minimal extension is an optional
internal work scope; all existing callers retain `work=None` and their current
setup, transaction outcome mapping and behavior:

```python
class TransactionWork(Protocol):
    def attach(self, connection: Connection) -> None: ...
    def remaining_timeouts_ms(self) -> tuple[int, int]: ...
    def check(self) -> None: ...
    def control_attempt(self, kind: Literal["commit", "rollback", "close"]) -> None: ...
    def detach(self) -> None: ...

admission_transaction(
    engine: Engine, outcome: TransactionOutcome,
    *, work: TransactionWork | None = None,
) -> Iterator[Connection]
```

OperationService supplies one request-owned budget. The optional argument is
internal composition, not a public authorization, fault-injection or ready
switch. Its counters/time are shared with separate read-only preflight and
disclosure scopes. The future implementation must establish these mechanics:

1. Attach to the acquired Connection before the first setup SQL; use only
   Connection-local listeners and the owned SQLite progress callback. Track
   each successful listener/callback installation, including partial attach.
   Count setup, authority, receipt, effect and native-timeout control SQL.
   Raw-cursor control SQL must debit the same counter explicitly; it is not
   visible to ordinary SQLAlchemy cursor-execution listeners.
2. Check effective driver mode as today. For this opted-in scope only, narrow
   native setup accepts the finite remaining statement/lock millisecond caps:
   no more than 5,000/3,000 and no more than remaining SQL-active time. Values
   below one millisecond refuse; zero must never mean an unlimited timeout.
   Install PostgreSQL local limits before other setup SQL, without a SELECT
   before SET TRANSACTION; preserve the existing default setup for work=None.
   Before ordinary statements, check the cumulative budget and refresh native
   limits. A fixed, counted raw-cursor setter avoids recursive listener calls;
   it must not create a repeated adjustment loop or bypass customer SQL counts.
3. Check after setup/before yielding and immediately before commit. Cursor
   events do not account for body fetch/parse work or DBAPI commit/rollback/close.
   The helper must check that elapsed work, apply fresh nonzero remaining native
   caps, and call control_attempt("commit") **before** marking commit_attempted.
   After actual commit returns, first mark commit_acknowledged, then check the
   budget again. A post-ACK deadline cannot be classified as a known rollback.
4. Reserve the fixed bounded control/cleanup attempt allowance inside the 512
   total before work begins. The helper explicitly accounts for DBAPI commit,
   rollback and close attempts; direct timeout restoration is counted too.
   Exhaustion never skips cleanup. Detach owned listeners/progress callbacks
   before rollback/restoration/close so an exhausted callback cannot interrupt
   cleanup. Cleanup accounting records the reserved attempts without throwing
   a new budget-exhaustion error. Each cleanup action follows the helper's
   existing bounded attempt/discard/reclose rules, not an automatic work retry.
5. Partial attach or detach failure must still reach rollback/discard/close.
   If removal cannot be confirmed, mark cleanup_failed, discard the physical
   connection and refuse success; preserve the original typed denial through
   secondary cleanup failures. Detach is idempotent over the scope's own tracked
   registrations, never another owner's callbacks. The phase clock also covers
   final fetch/parse before the last check; owned hooks cannot survive release.
6. After ACK and confirmed release, attach a fresh **read-only** disclosure
   scope to another Connection with the same remaining counters/time. Check
   before its first SQL, after its final fetch, and at successful phase exit.
   No budget reset, mutation retry or connection held across phases is allowed.

Expiry before commit with acknowledged rollback and clean release is
dependency_unavailable. Expiry after commit is attempted or acknowledged, or
during committed disclosure, is outcome_uncertain; the effect/audit is not
undone or repeated. Typed authority denials retain 401/403/404. The 10-second
value is a successful-completion/refusal ceiling, not a hard real-time limit
on connection establishment, native interruption latency, storage or emergency
cleanup. Work-budget listeners remain Connection-local. Only the factory-born
SQLite lifecycle guards above may use engine/pool events; they perform no SQL
or request-budget accounting. No background timeout thread or new service is
introduced. Optional work and ownership implementations require exact-source
review and actual SQLite/PostgreSQL proof before P1 acceptance.

## Fixed failures and transaction stages

Public service methods preserve IdentityInvalid, ResourceNotFound and
ActionForbidden for the existing 401/404/403 boundary. New finite service
refusals use existing `Fault` codes; no response/error class accepts raw data.
P2 later maps these through the unchanged four-field Error machinery.

| Stage/condition | Exact disposition |
| --- | --- |
| Runtime compatibility incompatible | Fault(schema_incompatible), 503; no customer rows |
| Compatibility/service unavailable; bounded metadata/result/failure unsupported or malformed after ownership is established | Fault(dependency_unavailable), 503; never raw text or partial view |
| Missing/inaccessible requested operation or original associated job ownership | ResourceNotFound / 404; no result I/O |
| Visible operation's secondary result/ref/run/ancestor proof fails, with fresh caller authority still valid | Fault(dependency_unavailable), 503; no result ID or partial response |
| Invalid authenticated principal / visible denied action | IdentityInvalid / 401 or ActionForbidden / 403 |
| Malformed public operation ID | Existing identifier/not_found service behavior after project authority; P2 preserves frozen transport/authority precedence |
| Cancellation failure before commit with acknowledged rollback and clean release | Fault(dependency_unavailable), 503; no success or automatic retry |
| Commit attempted without known acknowledgment; rollback/cleanup uncertainty; acknowledged commit followed by dependency/association disclosure failure | Fault(outcome_uncertain), 503, retryable=false; never a second mutation |
| Postcommit typed identity/access denial | Preserve the typed 401/404/403; do not claim cancellation was rolled back |
| Unexpected Exception inside admission_transaction, including effect/audit/work callbacks | Preserve that helper's existing mapping: dependency_unavailable before commit with known rollback, outcome_uncertain on commit/rollback uncertainty; never a generic client conflict |
| Unrelated programming exception outside SQL/native-session translation boundaries | Existing sanitized internal_error boundary; no raw cause or driver text in public output |

Translate the helper's finite AdmissionError to the same-code Fault only after
SQL release. Explicit cleanup/commit/disclosure observations may tighten a
dependency to outcome_uncertain; they do not reconstruct a raw exception already
translated by the helper or weaken a typed denial. Existing admission callers
and their mappings remain unchanged. Native read-session boundaries translate
driver/timeout/budget/cleanup failures to dependency_unavailable; unrelated
programming exceptions outside those boundaries reach sanitized internal_error.
There is no blanket catch-all relabeling every adapter bug as a dependency.

The read path has no mutation uncertainty: a read-only timeout/cleanup failure
is dependency_unavailable. Cancellation must preserve explicit commit/rollback/
cleanup observations; a DBAPI close failure cannot turn an attempted commit
into a retryable no-effect claim. No cancellation idempotency-key, alias, new
operation or new endpoint is introduced.

## Test construction and independent seams

Start from the real ar6 fixtures in `tests/test_admission_repository.py` and
`tests/test_admission_repository_postgres.py`, or the fresh no-preseeded-publication
fixture in `tests/test_admission_publication_postgres.py`. Publish a legitimate
synthetic native-v2 operation/job with actual task/config/payload metadata/refs
through existing preparation/repository helpers. Preserve the original creator,
config digest, operation Accepted and job scope. Add a different same-project
viewer to prove status access is not creator replay; submit/reconcile with that
viewer must still refuse.

For healthy null rows, use queued/running/succeeded/cancelled with result/error
NULL and strict budget/reserved values. For unsupported failures, set failed
with NULL error and each non-null legacy/JSON-looking/error-canary variant;
all refuse without artifact access. There is no supported failure-envelope
positive fixture in initial P1. Test original correlation is retained as source
metadata and never emitted as a fabricated nested Error.

For result positives, use a real synthetic Engine capture with an explicit
same-project run scope and the operation's job ID, plus an actual encrypted
job-owned format-1 result object containing exactly that run ID. A complete
success=false run tests execution status versus evaluator grade. No need to
adopt unregistered historical artifacts or fabricate a publication journal.
Use unrelated same-project and foreign-project runs for link refusals.

Unit/SQLite and actual PostgreSQL tests must cover:
- all status/error rows, exact required null/false fields and integer types;
  noncreator viewer, foreign scope, malformed selected cells before Python
  decode, raw-error canaries and unsupported loader;
- result ref/body/format/digest/length/created_at changes, same-project wrong job,
  authorized foreign run/ancestor 503 versus caller revoked during result-load
  404, and by_job phantom; mutation of an early receipt during a
  later final check; no partial response, no connection checked out during I/O;
- exact matching maximum mixed receipts, count/byte/native-work boundaries and
  cleanup, unchanged pool settings/handler release, unsupported DBAPI modes,
  SELECT-only PostgreSQL role and no read DML/audit;
- separate writer changes operations.job_id while cancellation waits on project
  exclusion; both membership/key revocation schedules, current expiry, worker
  terminal transition, repeated intent, terminal/reservation preservation;
- setup SQL/control accounting, partial hook attach/detach cleanup and shared
  remaining disclosure budget; actual deadline crossed during body fetch/parse
  before commit leaves exact rows/audit unchanged after acknowledged rollback;
  deadline crossed after real ACK/disclosure preserves one effect/audit and
  returns uncertainty without a repeated mutation; work=None callers unchanged;
- real stage rollback after effect/audit, lost commit acknowledgment and close/
  disclosure failures; fixed safe result and no duplicate audit/automatic retry;
- real migration-only zero customer sinks and explicit per-instance synthetic
  supported-profile controls, retaining prior ScopedActions regressions.

PostgreSQL read fixtures use a genuinely SELECT-only role. Cancellation adds
only the necessary row-lock privilege on operations: SELECT plus column-level
UPDATE(kind), where kind is constrained to run, for the exact row SHARE lock.
This is an explicit minimal UPDATE grant, not zero UPDATE permission. Prove real
SHARE succeeds and the same role cannot UPDATE job_id/principal/config
associations or INSERT/DELETE operations. Assert cancellation never changes an
operation row. Other required job/audit/grant privileges remain explicit. A
separate owner connection may drive replacement races, but cannot substitute for
restricted-role proof; read_operation must still pass with SELECT-only access.

Observe locks with PostgreSQL barriers/events and pg_blocking_pids, native
timeouts and real commits; no arbitrary sleeps or product fault switches.
Use function wrappers, SQLAlchemy cursor events and Connection.commit/close
wrappers as test seams. A owns the separate independent actual-PG/test-design
review after implementation assignment; no tests are authored by this document.

Before runtime, A/B/lead review this finite support table, ceilings, session
cleanup and cancellation lock/disclosure choices. A producer/schema expansion,
unmeetable measured limit or changed contract is a concrete review finding, not
implicit authority to broaden P1. All task statuses, estimates, outer edges,
accepted histories and external gates remain unchanged.

## Independent service composition review — 2026-10-21

A independently reviewed immutable component 97ef62c against entry 579c54b.
The lead accepted the following constraints for the existing service scope;
this review starts no service implementation. Caller integration and separately
reviewed factory activation remain prerequisites.

Cancellation must retain an immutable association receipt independently of the
fresh 16-field job validation. Preserve the original operation's 14 fields,
job id/kind/payload/actor/payload_version/budget, config digest/reference and
seven-field config descriptor/reference. Legitimate worker changes to status,
reserved amount, result and lease must not overwrite that association or make
post-commit disclosure fail merely because state advanced. Validate each fresh
job row and capture the mutation's response. GET continues to require its full
16-field job receipt. The existing strict repeated ReceiptBook job comparison
cannot be reused unchanged across cancellation preflight and disclosure.

A PostgreSQL SELECT with two native timeout SETs consumes three charged
statements. Per-node reads therefore cannot support 256 visited nodes inside
the existing 512-statement ceiling, even before authority and setup work.
Use bounded set-oriented frontier/cache reads with the shared visit, edge and
byte limits and original receipts. An outer counter or a wider ceiling does
not solve this requirement.

The final relational comparison needs a narrow source-domain bridge: the
component ReceiptBook's operation/job/config/result domains and the older
13-column job comparison do not cover the complete service. Preserve native
types and all 16 job fields; include by-job discovery and config/result candidate
cardinality in the same final statement within 259 identities, 4 MiB retained
receipts and 64 bound parameters. Separate successful comparisons do not prove
one coherent final observation.

Cross-row validation must explicitly enforce operation payload_version=2,
config digest/reference equality and the original creator's actor identity.
The current viewer's identity is authorization context, not a replacement for
the creator. Bounded cell and descriptor primitives alone do not establish
these associations. These constraints add no new producer, outer dependency,
resource authority or wider runtime support.

## Factory activation entry review — 2026-10-21

A audited the immutable caller checkpoint 27c9405 against entry b5d6335. The
minimal constructor change stays inside Database.__init__: parse the SQLAlchemy
URL and select the owned factory only for sqlite or sqlite+pysqlite with a
nonempty file path, no :memory: path, no file: URI, no query and no authority
components. Pass the existing connection and pool timeout constants. Keep
PostgreSQL construction and configure_runtime_engine unchanged; separately
constructed operator/probe engines and unsupported legacy memory/custom/URI
paths stay explicitly untracked. This adds no Settings flag, profile, dependency
or authority to certify injected engines. The future operation service still
requires ownership before its first SQLite acquisition.

Activation must keep the shared file-backed Settings/Database fixtures owned.
Adapt Database-backed setup and readback acquisitions to owned contexts rather
than opting the regression suite out. Affected categories include publication
and route fixtures, schema-compatibility snapshots, API/Auth/storage/engine tests,
and capture-based publication/projection/reader/legacy suites, including helpers
that receive a Database engine indirectly. Preserve assertions and explicit
untracked component controls, native transaction-mode and permission negatives.
A provenance refusal must not silently replace the behavior a test was meant
to exercise. This mechanical fixture adaptation is a separately reviewable
checkpoint within the existing P1 scope.

The installed smoke must change its dormant-default assertion only with the
reviewed activation. Prove owned construction, real migration-only compatibility,
ordinary Database operations, callback cleanup and pool reuse, with customer
admission still unavailable. Also prove constructor laziness, the supported URL
matrix, unchanged PostgreSQL behavior and no automatic certification of injected
engines. The offline operator engine used by the existing migration smoke may
remain untracked.

Correct and independently accept both caller restoration findings before any
activation implementation. Then review constructor/new activation tests and the
existing-fixture adaptation independently before combining them. This entry
review does not itself activate the factory, implement services, advance P1,
widen budgets or change outer dependencies.


## Bounded primitive checkpoint — accepted entry, 2026-10-21

B and the lead accepted C's concrete handoff against a2220eb and ced548b after
the composed factory/fixture component passed at 97d39edf. C owns the narrow
operation_reads factoring and a focused operation_sources module; A independently
reviews security/test design. This checkpoint precedes service orchestration.

Factor the existing all-16-field job decoder without changing read_job's strict
receipt behavior. Record optional result candidates as an observed zero or one
valid scoped descriptor with exact owner/role/cardinality. A SQL NULL result
permits that observation with no artifact load or inferred result ID; a non-NULL
result requires one matching descriptor and the existing bounded verified loader.
The final GET statement must preserve observed absence/cardinality as well as
all operation/job/source/descriptor fields, scope and by-job discovery.

The accepted schema-2 run envelope has no admission source-run ancestry. The
existing Lineage rules require every run-job cohort member to be a run with an
explicit null parent; study and non-null-parent members are already invalid.
Load the complete same-project by-job cohort, preserve multiple root runs, and
require the exact returned result ID to belong to it. Foreign incoming aliases
remain excluded by the existing scoped rules. This equivalence needs executable
negative controls before it is relied on in services.

One job plus 255 cohort records consumes 256 source visits and 510 edges;
operation/config/result identities bring the maximum to 259. Materialize at
most remaining_visits+1 SQL candidates, then gate COUNT and aggregate raw
returned-cell bytes before projecting bodies. Overcount, malformed or oversized
candidates produce small explicit refusal markers; they must never be filtered
or trimmed into success. Preserve the exact canonical 4 MiB retention cap after
the raw-transfer gate. The single final typed relational comparison must include
native types, original scope, candidate counts and by-job anti-joins within the
existing 64-bind/260-row limits.

Cancellation retains a separate immutable operation/config/job association:
all original operation/config fields and refs, plus job id, kind, created,
payload, budget, actor, payload_version and config reference/digest. Preserve
native type distinctions and large integer accounting without float conversion;
reserved greater than budget remains a valid accounting value.
Fresh all-16-field job validation must not overwrite it, and strict GET mutable
job/result/ref equality must not be carried across commit acknowledgment.
Legitimate worker progress may change status, result/ref, reservation or lease
without replacing the captured cancellation response. Shared visits do not reset
between phases: three full validations allow at most 84 roots per phase, rather
than 255. Proposed 74 GET/162 cancellation charged-attempt figures are design
estimates requiring actual traces; the existing ceiling remains 512.

First freeze: pure association/observation factoring, cohort and final-query
primitives, and focused SQLite/PostgreSQL tests. Require maximum matching
capacity, overflow and aggregate-before-transfer controls, native types, extra
malformed refs, absent-to-present refs and by-job phantoms. Existing schema has no
by-job JSON or project-scope index: test substantial nonmatching same-project and
foreign records under the same VM/time limits. Small result size alone does not
establish scan cost or enterprise throughput. An unmet measured requirement is a
review finding; this entry authorizes no index, migration or wider budget.

No service method, HTTP, profile, worker or failure-producer implementation is
part of this primitive checkpoint. Actual service integration and full P1
SQLite/PostgreSQL/hosted/delivery evidence remain subsequent gates. Task states,
outer dependencies, package count, estimates and external authority are unchanged.

## Cancellation phase entry — 2026-10-21

The bounded GET primitives at `691ad661` are accepted as a component. Their strict
receipt book must not be carried unchanged across cancellation phases. This
entry specifies the missing cancellation-only retention seam; it adds no task,
dependency, estimate, budget, schema, HTTP or activation change. Implementation
starts only after the exact entry receives independent review.

Use one focused internal `operation_cancellation.py` module:

```python
CancellationReceipts(
    work: OperationWork, original_context: ProjectContext, operation_id: str
)
CancellationReceipts.phase() -> ContextManager[CancellationPhase]
CancellationReceipts.original -> CancellationAssociation
CancellationPhase.book -> ReceiptBook
CancellationPhase.associate(
    operation: RawReceipt, job: RawReceipt, configuration: RawReceipt
) -> None
CancellationPhase.verify(connection: Connection, cohort: RunCohort) -> None
```

These objects own no connection, authorization, transaction, storage or response.
Keep ordinary GET `ReceiptBook()` and `verify_read_snapshot()` semantics intact.
Add only the private accounting/liveness hook needed for existing bounded
readers to consume the phase book; do not introduce another general framework.

One request owns the original context/operation identity, one OperationWork,
cumulative 256 source visits/512 edges, and at most one active phase generation.
A nested or stale acquisition owns nothing and must leave the active phase
untouched. Every bounded loader/query entry must validate a retained phase-book
handle before SQL; checking only the `phase.book` property is insufficient.
Actual active-phase failure aborts this owner without a retry or budget reset.

Each phase reads fresh op14, full job16, config7/reference and a complete cohort.
`associate()` validates the association, reserves the initial immutable snapshot
before a potentially large cohort read, and promotes it only after final
verification. Later phases compare against that original snapshot, including
job.created and budget. Require the supplied cohort's exact raw receipts to
match its active book, not merely its IDs.

One exact live-retention calculation covers the original association and current
phase rows/observations, including canonical wrapper overhead, within 4 MiB.
Charge both retained job representations; count the union of logical
(domain, id) identities within 259. Include the original reservation in
`remaining` before SQL COUNT/SUM permits body transfer. Promotion must not
temporarily retain an uncharged duplicate. Final serialized input also fits
4 MiB. Do not add a cumulative decode-byte cap.

The narrow cancellation final query reuses typed/materialized SQL for exact
current-phase op/job/config/cohort, scopes, configuration candidate cardinality
and by-job phantoms. Filter the admission_config role before its candidate
LIMIT. Exclude GET result observations, result ref counts, result descriptors
and rendering. Job16.result must remain equal within a phase; result artifact
refs are ignored in every cancellation phase, including malformed/added refs,
without storage access or refusal. Configuration refs remain exact.

Mutation verification occurs immediately before intentional cancel/status writes
under the retained locks. Capture the effect's three-field response then; do not
compare the old full job16 after that deliberate write or refresh original
receipts to hide it. Post-ACK disclosure uses a new phase and retains the captured
response while allowing valid worker/job.result/cohort advancement. Fresh
authority remains a separate required service check after final SQL; association
is not authorization.

A phase encloses its connection/transaction acquisition, cleanup and ACK
observation. Closing it releases mutable buffers/live-byte charges only.
Original association, visits, edges and the same OperationWork counters remain.
Sealed, closed and stale handles cannot resume SQL; stale close cannot release a
later phase. Pure phase cleanup preserves primary exceptions. The service and
transaction outcome classify post-ACK uncertainty and typed denials; the receipt
owner does not claim that responsibility.

Before cancellation service wiring, prove on SQLite and actual PostgreSQL:

- Three 84-root phases succeed at 255 visits/504 edges; three 85-root phases
  refuse before the third cohort's bodies transfer, without reset or refund.
- Valid new runs and worker/job.result progress between phases succeed.
  Within-phase job/result/cohort changes refuse; result artifact ref changes
  alone remain ignored. Original association and config scope/count/descriptor
  drift refuse.
- Original-plus-phase canonical byte/identity limits, expansion, promotion,
  release and reuse obey the same caps while cumulative work never decreases.
- Retained stale books, nested acquisition and failed-phase reuse cause zero
  SQL, preserve the active owner and retain the original exception.
- Maximum matching cases and scoped/foreign distractors retain the existing
  SQL/VM/time/bind bounds. Later lock/authority/effect/ACK/disclosure tests remain
  required for the service; this helper checkpoint does not replace them.
