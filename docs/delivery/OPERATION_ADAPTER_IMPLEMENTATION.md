# Operation adapter implementation checkpoints

Engineer C owns AR-008-B/P1 [#94](https://github.com/spei04/agent-rewind/issues/94).
This working guide accompanies the first implementation checkpoint on
08e5c403. The accepted [entry contract](OPERATION_ADAPTER_ENTRY.md) and
[delivery plan](OPERATION_HTTP_EXECUTION_PLAN.md) remain authoritative. This
checkpoint is preparatory code, not completed P1 acceptance or HTTP activation.

## First checkpoint: work and original receipts

- operation_work.OperationWork is one request's sequential work owner.
  operation_connection(engine, work) owns a native read-only phase.
- admission_transaction(engine, outcome, *, work=None) optionally consumes
  TransactionWork. Existing callers omit work and retain their admission
  transaction behavior and fixed outcome vocabulary.
- operation_reads.read_operation/read_job/read_descriptor take a caller-owned
  Connection, original ProjectContext and ReceiptBook. They return bounded raw
  receipts and validated operation/descriptor values. They do not authenticate,
  authorize, lock, load storage, commit, or make a disclosure decision.

OperationWork shares 512 SQL/control attempts, ten seconds of connection-owned
work and 20 million SQLite VM instructions across all phases. It charges
SQLAlchemy statements and each raw native timeout setter separately. Opaque
executemany is unsupported. Eight attempts are reserved before ordinary work for
rollback, native restoration, discard and bounded reclose; exhaustion never
prevents those cleanup attempts. Commit attempts are also charged. Counters do
not reset when moving from preflight through mutation to disclosure.

The connection-local lifecycle is attach → setup → setup_complete → work →
detach → native cleanup → finish. Attach counts setup but does not refresh
timeouts: the existing SQLite timeout must be saved first (the pooled fixture
uses 741 ms). setup_complete enables per-statement refresh only after the native
setup succeeds. Before COMMIT, control_attempt refreshes the remaining native
limits and charges the commit before commit_attempted becomes true. An actual
commit return sets commit_acknowledged before any subsequent check.

Each ordinary statement uses at most min(5000 ms, remaining time), with lock
waiting at most min(3000 ms, remaining time). Less than one millisecond refuses;
zero never means unlimited. PostgreSQL SET TRANSACTION precedes ordinary
queries. SQLAlchemy cursor listeners do not observe DBAPI commit, rollback or
close, so those controls are explicitly charged. detach removes only this
owner's listeners/progress callback before rollback; finish accounts through
native close. A setup_complete failure rolls back. A detach failure requires
physical discard. Cleanup/accounting failure cannot mask the primary typed
401/403/404 denial or BaseException. Precommit acknowledged rollback remains
dependency_unavailable; attempted/acknowledged commit followed by budget,
cleanup or finish failure remains outcome_uncertain.

Connection acquisition and storage I/O are outside the SQL-active clock; this
does not promise a hard connection or emergency-cleanup wall-time deadline.
The supported engine must lend exclusive native connections with no other
owner's SQLite progress callback. SQLite has no callback introspection; a clean
transaction alone cannot prove callback ownership. The connection ownership
marker refuses known overlap. No global engine listeners or callback takeover
are installed.

Raw operation receipts retain all 14 original columns, including the exact
Accepted string, original principal/correlation and retention fields. Raw jobs
retain all 16 columns, with SQL NULLs and native numeric/boolean types intact;
no ORM Boolean coercion hides an invalid SQLite value. Per-cell CASE expressions
and the 4096-byte job bound execute before driver materialization. Selected
malformed rows remain candidates and refuse rather than disappearing.

Configuration/result candidates use a LIMIT 2 LEFT JOIN before digest/format
validation. Each receipt retains all seven original descriptor fields plus the
reference's artifact ID. Timestamp columns become bounded SQL text before
driver decoding, including PostgreSQL infinity/malformed-value refusal. Scoped format-1 locators, 64 KiB configuration and
4096-byte result limits are checked. ReceiptBook retains at most 259 identities
and 4 MiB of canonical encoded expectations, refusing changed duplicate
identities (including raw type changes). These bounded metadata primitives do
not establish a verified storage receipt or current authority.

## Dependent checkpoints, after independent review

1. Add OperationService.read_operation with real schema guard, fresh named-project
   authority, bounded source closure and the original operation/job/config
   association. Extend the final relational receipt query to include original
   operation and all 16 job columns plus both descriptor/ref receipts in one
   statement. Retain the accepted 256 visits/512 edges/depth 64, <=64 binds,
   259 expected identities, 260 result rows/16,640 bytes and 2048-byte response
   bounds. Do not substitute a later SQL read for retained expectations.
2. Verify an optional job-owned result (one <=4096-byte storage read, zero SQL
   connections held) as exactly a run_id and prove the original job/run ancestry.
   A null result needs no storage. Any non-null legacy error, or failed+NULL,
   remains unsupported 503; no failure envelope producer is invented. Requested
   operation/job invisibility is 404. Secondary proof failure is 503 only after
   fresh principal/project authority still succeeds; revoked callers remain
   typed denials.
3. Add cancel_operation with the accepted project→organization→grants/key→job
   scope/job→operation SHARE order, original association comparison after waits,
   same-Connection fresh action/config checks and shared reviewed cancel effect.
   Keep ScopedActions' legacy callers intact. Audit/effect/ACK and fresh
   disclosure share this work object; no repeat mutation on uncertain outcome.
4. Add exact distribution allowlist entries and installed-package smoke with the
   completed adapters. Run the complete P1 SQLite and actual PostgreSQL matrix
   before claiming package or task acceptance.

## Evidence still required

Focused SQLite tests cover actual pooled native restoration, DML/DDL denial in
read scopes, real VM interruption, setup/fetch/commit/close deadlines, partial
hooks, rollback/close faults, typed denial preservation, cumulative counters,
original raw cells, pre-materialization oversize refusal and changed/multiple
descriptor candidates. Existing admission transaction/coordinator cases remain
regression coverage for work=None.

This checkpoint does not claim PostgreSQL execution. Actual PG tests must prove
remaining native limits/lock waits, SELECT-only reads, READ COMMITTED behavior,
after-ACK/disclosure failure, row-lock privilege and fresh authority races.
Operation cancellation needs explicit SELECT plus minimal UPDATE(kind) on
operations for SHARE locking; prove that job_id/principal/config changes and
INSERT/DELETE remain denied. No HTTP, worker, failure producer, schema, profile,
ledger, provider or customer activation belongs to this checkpoint.


### Cleanup ledger and development checks

The worst injected mutation cleanup path consumes six of eight reserved
attempts: detach-failure discard; rollback attempt; discard when that rollback
cannot run on the invalidated connection; first close; close-failure discard;
second close. Native restoration replaces, rather than adds to, the invalidated
connection path. A setup-failure discard is counted too; PostgreSQL begin is
counted separately from its explicit SET statements. Detach interruption still
removes the other registered hook and releases/discards the connection.

Initial development runs exposed two invalid test mutations: changing only one
of the constrained configuration digest/reference pair, and deleting a scoped
job still referenced by an operation FK. The tests now change both configuration
fields atomically, and use absent/foreign project lookups without corrupting
constraints. That run had 54 passes and those two fixture errors. The next
expanded selection had 87 passes and one accidental numeric expectation typo
(10 charged attempts had been written as 20); the exact ledger assertion was
restored. No schema constraints, production mappings or acceptance limits were
relaxed.


Final author selection before the descriptor timestamp text portability check:
203 passed, zero skips, 77.41 seconds across both new modules and existing
admission transaction/coordinator/submit/repository tests. The four existing
admission modules exercise work=None unchanged, including known-winner rollback,
pending recovery, publication faults and typed denials. The final focused
receipt/work/static checks are reported with the immutable handoff.

Final first-checkpoint focused result: 53 passed, zero skips, 10.73 seconds after
the descriptor timestamp SQL-text correction. Configured Ruff, runtime security
rules, five-file format check, strict mypy on all three changed runtime modules
and diff-check passed. No PostgreSQL server was started or queried. Package
allowlist/installed smoke and all service-level/actual-PG evidence remain later
P1 work, not acceptance claimed by this component.


### Independent cleanup/type findings and correction

Independent review of a59e074 confirmed A-OP-01/02/03. The separate test
checkpoint 09dd1e8 freezes 17 regressions against that runtime: all 17 failed
in 2.46 seconds. They reproduce accounting that skipped native read cleanup,
cleanup KeyboardInterrupt replacing a body denial/interruption and leaking a
one-slot pool checkout, and identical SQLite timestamp bytes stored as BLOB
being accepted as an unchanged descriptor. Failed probes explicitly release
their captured connections in a test finally block.

Cleanup accounting now records its failure separately from every native action.
Rollback, discard, restoration, close, bounded reclose and finish continue after
BaseException. Body/setup failures remain primary. Without a body/setup failure,
the first cleanup interruption is rethrown after cleanup even when an earlier
ordinary cleanup error occurred; ordinary errors retain the existing finite
dependency/commit-uncertainty mapping. The mutation outcome records cleanup
failure and sets rollback acknowledgment only when native rollback returns.
An acknowledged commit is not reclassified as retryable after cleanup failure.

An interrupted native discard has one additional attempt per phase. The read
path remains within eight reserved attempts (rollback, up to two restorations,
two ordinary discard sites, close/reclose, and that one extra discard); the
existing six-attempt mutation chain takes seven when the extra discard is used.
Setup disposal with work attached now runs through the outer owner after detach,
so it cannot replace the original setup failure. Finish is attempted after
native close even when earlier cleanup is interrupted. These are bounded
attempts, not a promise that a permanently failing driver can be repaired.

Descriptor timestamps are converted to bounded SQL text on PostgreSQL only,
before psycopg timestamp decoding. SQLite retains its native value type, so a
BLOB cannot become the original TEXT receipt through a cast. Both an existing
receipt book and a fresh book reject that change without replacing an original
receipt. Candidate cardinality, all seven descriptor fields, and byte bounds
remain unchanged.

Two additional draft cleanup cases initially failed in both scopes (four
failures): interrupted discard needed its bounded retry, and an ordinary
cleanup failure hid a later interruption. The final regression module has 29
passing cases, including setup-primary preservation, multiple interruptions
inside the reserved allowance, and finish after pool release. The complete
selection is 232 passed, zero skips, 79.21 seconds: the three operation modules
plus the unchanged admission transaction/coordinator/submit/repository tests.
The four existing admission modules retain all 150 work=None regression cases.
Configured Ruff/security, six-file format check, strict mypy on three runtime
modules, pinned offline lock validation and diff-check passed using the owned
secondary Python 3.12.3 with PYTHONPATH unset and bytecode/cache disabled.

No PostgreSQL server was started or queried for this correction. Application
engine/native progress-handler provenance remains a separate reviewed entry
requirement before service composition: the current marker does not detect or
restore an arbitrary unmarked foreign callback. No ownership mechanism,
read/cancel service, HTTP route, schema, profile or failure producer is added
by this correction.


### Actual PostgreSQL first-component proof

A separate test-only checkpoint exercises the f10cf23 runtime on the existing
private PostgreSQL 16.15 instance through the opt-in synthetic fixture. The
initial 33 cases all passed in 50.58 seconds; seven additional boundary cases
brought the final run to 40 passed, zero skips/failures/errors, in 59.09 seconds.
No runtime or shared fixture change was needed. The new file is
tests/test_operation_component_postgres.py; without the opt-in connection it
collects as 40 explicit PostgreSQL skips.

The read tests use a nonsuperuser role with SELECT and without table mutation
or schema CREATE privileges. A separate normally DML/DDL-capable nonsuperuser
owner proves native READ ONLY refusals are SQLSTATE 25006 rather than missing
privileges. An actual committed writer demonstrates READ COMMITTED on the same
read transaction. Native statement cancellation (57014) and a held conflicting
table lock (55P03) exercise remaining limits without sleep-based barriers.
Controlled clocks retain budget across connections and verify actual 500 ms,
250 ms and 1 ms settings, sub-millisecond refusal, and the shared 512-attempt
allowance. The exact read/mutation/read ledger includes raw timeout setters,
setup and native controls; pooled settings and physical connection reuse or
replacement are checked after cleanup.

Native rollback/close and accounting interruptions preserve the original typed
denial, release the one-slot pool, and finish the work clock. Precommit expiry
rolls back effects; post-ACK expiry and lost commit acknowledgment remain
uncertain. A later read-phase deadline retains the shared work total. Mapping
that failure after a successful mutation to a service-level uncertain response
is still the future service's responsibility.

The raw-receipt cases use a real initialized ar6 synthetic database and a
SELECT-only noncreator viewer. They preserve the original 14 operation fields,
16 job fields, seven descriptor fields and reference identity; changed receipts,
missing/ambiguous candidates, nonfinite job values and byte overflow refuse.
An instrumented DB result confirms CASE bounds precede Python validation.
PostgreSQL infinity reaches the validator only as bounded text; malformed
timestamp text is rejected by the native timestamp type (22007), rather than
being simulated by bypassing that type. The legitimate 1200-byte VARCHAR(300)
error boundary remains raw data, not an asserted structured Error producer.

The synthetic database/role inventory exactly matched its pre-run baseline
after teardown, with no other client backends. All consumers were closed and
the socket-only instance was stopped. Private owner-only logs, JUnit results,
source/test hashes and cleanup evidence are indexed outside the checkout for
review on 2026-11-20.

This is component evidence only. SQLite engine/progress provenance, actual
operation-row lock privileges, service authority races, final compound receipt
revalidation, effect/audit/disclosure composition and installed-package coverage
remain later P1 obligations. No read/cancel service, HTTP route, schema/profile,
worker/failure producer or customer activation is added by this checkpoint.


### First interruption inside detach

A later immutable review of f10cf23 found that detach itself replaced its saved
interruption at each subsequent failing cleanup hook, even though the outer
owners already preserved their first interruption. A real two-listener removal
sequence therefore exposed a later SystemExit instead of the first
KeyboardInterrupt when there was no body/setup primary.

The separate regression-first selection adds 18 cases across read/mutation
owners, listener-only and progress/listener/marker chains, with no primary,
typed denial or primary interruption. Against the unchanged runtime, six
no-primary cases failed and twelve primary-preservation controls passed in
1.05 seconds. The real callback/listener/marker removals, exact SQL/control
counts, physical discard, pool release, finished clock and effect/rollback
assertions all passed before the six exception-identity failures.

Only the three saved-interruption assignments in detach change: they retain
the first non-Exception BaseException while attempting every later removal.
An earlier ordinary cleanup failure does not hide a later first interruption;
a body/setup primary still takes precedence. All 18 new cases pass in 0.89
seconds. The combined selection is 250 passed, zero skips/failures/errors, in
81.90 seconds, including the unchanged 150 admission work=None cases.
Configured Ruff/security, two-file formatting, strict operation_work mypy,
owned source/manifest checks and diff-check pass. This correction adds no
ownership or service code. PostgreSQL remains stopped; the earlier 40-case
actual PostgreSQL evidence is specifically against f10cf23, not a new run of
this exception-ordering correction. Private regression logs and source hashes
are indexed outside the checkout with review date 2026-11-20.

## Dormant caller and callback integration checkpoint

This checkpoint adapts the existing 33 acquisition sites in 14 modules while
leaving Database.__init__ and its create_engine configuration unchanged. It does
not activate the owned factory or implement OperationService. The source audit
covers Database's 18 acquisitions; Auth, CLI doctor, artifact publication,
projection source, PublishedRunReader, RequestAuthority, ScopedActions and
ScopedRepositories; both migration service and compatibility wrappers; and the
three manual operation/listing/admission owners. Existing Connection.begin
calls remain transaction operations, not additional engine acquisitions.
Catalog reflection already takes the caller's Connection. No Engine-bound
reflection, create_all, or implicit migration acquisition is added.

Ordinary callers use owned_connect/owned_begin. Manual owners keep their own
transaction/outcome decisions and retain connect_owned's receipt through
close_owned, then finish_owned, before choosing success. Migration service
explicitly translates SQLiteOwnershipError to its fixed migration/schema
refusal without manufacturing a DBAPIError. Unregistered engines and PostgreSQL
return receipt=None and retain their explicit legacy behavior.

The three native callback consumers (OperationWork, listing_session and
compatibility inspection) use optional_progress before PRAGMA mutations,
listeners or consumer ownership. None means only an unregistered engine.
A registered engine with a substituted pool refuses; ownership failure never
selects the legacy callback path. An unsuccessful nested lease owns nothing to
remove. Successful leases release before rollback/restoration.

This low-level pass-through is not engine certification. The future
OperationService must call require_owned_sqlite for SQLite **before its first
acquisition, including schema compatibility probes**. It must not catch that
failure to fall back to legacy. PostgreSQL keeps its separately reviewed native
contract. SQLite support remains limited to the factory-born, file-backed
QueuePool provenance in the entry contract, not arbitrary custom/memory engines
or malicious in-process bypasses of the tracked connection.

### Shared cleanup actions

The existing eight-attempt reserve is unchanged. Accounting exceptions are
recorded separately and cannot prevent the associated native action. Pure
quarantine marks uncertain state before the first close, so a pool return cannot
silently reuse failed restoration or callback cleanup.

| Action | Read owner | Mutation owner |
| --- | --- | --- |
| Native rollback | 1 | At most 1, only when needed |
| Restore query_only | 1 | 0 |
| Restore busy_timeout | 1 | At most 1 |
| First observed logical close | 1 | 1 |
| Shared recovery: Connection invalidate | At most 1 | At most 1 |
| Shared recovery: logical reclose | At most 1 | At most 1 |
| Shared recovery: retained public proxy invalidate if still valid, otherwise retained raw close | At most 1 | At most 1 |
| Shared recovery: remaining retained raw close | At most 1 | At most 1 |
| Maximum cleanup controls | 8 | 7 |

The last two recovery slots permit two raw-close attempts when no valid proxy
remains. They never add a third raw attempt or target a new proxy/current pool
occupant. Constructor failure uses the same bounded path and captured receipt;
an incomplete PoolConnectionRecord is never manually checked in. Native calls
performed inside an explicitly counted SQLAlchemy control are not recursively
counted as extra public attempts.

The combined failure regression initially proved that closing raw alone after
pre-action Connection.invalidate and reclose faults left one pool checkout.
The retained public-proxy alternative now returns that slot within the same
bound, retaining the failed verdict. Permanently failing proxy and physical
controls remain an explicit failed/unreturned verdict; bounded attempts do not
promise reclamation of a permanently broken driver. The test restores its own
injected permanent failures and cleans up explicitly.

A post-return close failure can leave a closed raw object in an idle record.
The next checkout refuses/quarantines it before yielding, then a fresh
acquisition can succeed. Cleanup does not invalidate a record that may already
belong to another generation. The historical failed verdict never turns into
success because later disposal was acknowledged.

Body/setup typed denials and interruptions remain primary. Otherwise the first
cleanup interruption is rethrown after all cleanup and clock finish. A commit
ACK followed by failure remains outcome_uncertain; work=None and untracked
paths retain the existing admission semantics. No disposal failure is treated
as successful disclosure.

### Integration development evidence

The new combined-control regression failed with checkedout=1 before the shared
proxy alternative and passed afterward. The original 67 helper cases also
passed. The initial new fixture incorrectly enabled SQLite foreign_keys after
starting an INSERT transaction and named a records column body instead of data;
six failures exposed these fixture errors. The corrected fixture enables FK
before DML and uses the existing records shape, without weakening production
checks. A further expectation was corrected to account for Database.get's
existing id/created metadata. Partial listing setup deliberately discards its
physical connection: the replacement has the factory's 3000 ms timeout, while
successful restoration on the same connection retains the original 741 ms.

The focused new integration suite has 42 passing cases. It includes all six
callback permutations on one native connection, nested refusal preserving the
outer owner, substituted-pool refusal before effects (including on an already
acquired connection), exact eight/seven-action controls, accounting and cleanup
interruptions, permanent-control uncertainty, actual migration-only installation
and ordinary Database calls, fixed migration error translation, partial callback
setup, and unchanged factory nonactivation. Broader regression/static results
are recorded in the immutable handoff. No PostgreSQL server was started for this
checkpoint; earlier component PG evidence does not prove this integration or
the later services. The exact allowlist now includes sqlite_ownership.py,
operation_work.py and operation_reads.py: setuptools already emits all three,
and normal callers now import the ownership helper. The added installed smoke
helper imports the components, exercises owned read-only work against synthetic
SQL, and asserts Database still uses its untracked default factory. The exact
corrected component at 55b3950 passed offline wheel/sdist and isolated installed
smoke on Python 3.12.3. Both archives' 110 runtime members matched that commit;
B independently verified the indexed private source/provenance/artifact record.
The disposable runtime was removed after proof. This is dormant-component
acceptance, not factory activation, Python 3.11/hosted evidence or completed
service acceptance. Completed-service smoke remains later P1 work.

### Restoration quarantine correction

Independent review found two restoration paths that could refuse the current
call yet recycle changed native settings: compatibility inspection after a
restore/listener failure combined with pre-action invalidation failure, and
projection snapshots after query_only restoration failure. Their original eight
one-slot regression cases failed against 27c9405 (1.18 s); the raw connection
remained open despite the failed restoration.

Both scopes now capture a checked owned_receipt before native effects. Capture
proves the original Connection/proxy/generation while idle, returns None only for
a genuinely unregistered engine, and never reacquires an invalidated connection.
The retained receipt is quarantined before attempted native disposal; no later
pool occupant is consulted. A failed nested capture owns no cleanup rights.
The projection owned path independently attempts its rollback/restore/rollback
sequence, retaining a body/setup primary or otherwise the first cleanup
interruption. Explicit untracked and PostgreSQL cleanup policies are unchanged.

Retained capture permits an outstanding checkout after normal engine disposal
only when both predecessor and current successor pools are registered to the
same capability. New acquisition still requires the exact current pool. Two
dispose controls initially failed; the corrected controls preserve both active
generations independently, while a foreign replacement still refuses without
poisoning the original owner. A test initially used the discarded predecessor's
pool counter, which becomes negative after dispose(close=True) resets overflow
accounting; it now proves the original closed Connection, invalid original proxy
and returned generation verdict, plus zero active successor checkouts.

The fifteen correction cases cover both restoration paths, listener removal,
failed invalidation, typed body denials, multiple cleanup interruptions, and
capture after close/invalidation. They require old-raw disposal, zero checked-out
slots, and a fresh writable connection with default native settings. Together
with existing helper/caller, projection, schema, admission and listing cases,
249 tests pass (one existing Starlette warning). Full Ruff/security, format,
strict typing, pinned lock and provenance checks passed. The corrected 55b3950
isolated package proof described above supersedes the historical 27c9405 proof
for this component. Factory activation and operation services remain outside
that restoration checkpoint.

### File-backed Database factory activation

Engineer C owns the constructor/new-test/installed-smoke slice of AR-008-B/P1
#94. The constructor checkpoint is 902cb51; engineer A separately owns adaptation
of existing Database-backed fixtures. These pieces require independent review
and composition before activation acceptance.

Database.__init__ parses the SQLAlchemy URL and selects the owned factory only
for exact sqlite or sqlite+pysqlite, a nonempty file path other than :memory:,
no file: URI, no query and no username/password/host/port. It forwards the existing
3-second connection and 1-second pool timeout constants. Database connections
remain lazy; existing data-directory creation is eager. The legacy URL branch,
PostgreSQL constructor and configure_runtime_engine call remain intact.
Unsupported memory/URI/query/custom-driver forms and independently injected
engines gain no ownership capability; operation services still require the
separate capability gate before their first acquisition.

The new 25-case constructor selection proves actual file-engine laziness,
native initial timeout, relative paths, unsupported-form dispatch, unchanged
PostgreSQL configuration without a server connection, and refusal to certify an
injected engine. The real migration-only control additionally exercises owned
initialization, ordinary Database records, sequential inspection and the public
coordinator refusal before identity/new-work sinks. It preserves the original
post-migration raw connection and native timeout: an initial assertion incorrectly
expected the constructor's 3000 ms after the existing migration policy had
selected 5000 ms. The corrected oracle compares the actual pre-inspection value,
without changing either policy.

The installed component helper now requires the default file-backed Database
to be owned, runs real migration-only compatibility and customer-admission
refusal, verifies ordinary record/audit behavior and zero job creation, checks
query_only restoration/pool release, and retains the separate bounded read/write
denial checks. Other installed helper bodies remain unchanged. The constructor/caller/helper/restoration selection passes 150 cases with no
skips or warnings (3.34 s). Exact activation package evidence belongs to the
immutable handoff; composed existing-fixture evidence remains a separate gate.
No operation read/cancel service, schema/profile readiness, HTTP, worker, failure
producer or customer activation is implemented by this factory change.

### Bounded source primitives — AR-008-B/P1 #94

Engineer C owns this component on work/operation-service-primitives, based on
the accepted composed factory checkpoint 97d39edf. It adds no OperationService,
HTTP, schema/index/profile, worker or failure producer. The unchanged 512 SQL
attempts, 10 seconds and 20 million SQLite instructions bound execution; no
extra cumulative decode-byte threshold is introduced.

operation_reads now separates validate_job_row(row, job_id) and
read_job_state(connection, context, job_id, book) from strict read_job retention.
The pure decoder enforces all sixteen fields, native scalar types, individual
SQL cell limits and the 4096-byte raw-row bound. Every fresh job read consumes a
source visit. read_job still remembers its full original receipt. A
CancellationAssociation captures the fourteen operation fields, seven descriptor
fields plus configuration ref, and immutable job id/kind/created/payload/budget/
actor/version/config identities. require_matches first validates the fresh
sixteen-field job, then compares only that immutable association. Valid worker
status/owner/lease/cancel/reservation/result/error progress does not overwrite
the original GET receipt or establish a new captured cancellation response.
Integer accounting remains exact, including 2**53+1 and reserved above budget.

observe_result records zero or one valid scoped descriptor plus original result
candidate cardinality, even when jobs.result is NULL. Missing, foreign, malformed
or extra candidates cannot disappear into a unique success. A NULL result
triggers no storage or inferred run ID in these primitives. A non-NULL result
must match the descriptor digest; the later service still owns verified loading,
strict payload parsing and fresh authority.

operation_sources.read_run_cohort(connection, context, job, book) loads the whole
same-project by-job cohort in one materialized SQL candidate set. It does not
filter away study/unknown-kind or parent-bearing candidates. remaining_visits+1
bounds selected rows; COUNT, native-type/cell validity and SUM of returned raw
cell bytes gate body projection before the driver materializes the result list.
Refusal rows contain only NULL markers. Exact canonical receipt retention is
checked afterward, retaining original JSON whitespace/type identity. The cache
is validated by the existing Lineage rules without additional SQL; every run
has an explicit null parent, multiple roots remain legal, and foreign incoming
aliases are excluded under the existing scoped semantics. validate_result_member
requires exact membership rather than choosing a first/latest root.

One job plus 255 records uses 256 visits and 510 edges; operation/config/result
bring retained identities to 259. ReceiptBook also retains cohort and zero/one
result observations within the same 4 MiB canonical input ceiling. Unchanged
receipts are not recharged; repeated visits and execution work never reset.
Fresh mutable cancellation state is bounded separately, not fed back into a
strict GET receipt equality check. Three full source phases can therefore fit
at most 84 roots each under the unchanged visit ceiling; no service-level
three-phase capacity is claimed by this component.

matching_query and verify_read_snapshot perform one final relational observation
over all original operation14/job16/source/descriptor/ref values, exact scopes,
configuration/result counts and a by-job anti-join. SQLite compares native typeof
as well as null-safe values, including identical TEXT/BLOB and integer/real
representations; PostgreSQL uses native bigint/bool/double and bounded timestamp
text. Input is at most 4 MiB, the query compiles to 22 binds on both dialects,
and output is at most 260 fixed domain/id pairs. No current row replaces an
original expectation. The caller must reauthorize the original project after
this statement. It is a GET comparison; cancellation disclosure must not reuse
its strict original mutable job/result observations across acknowledgment.

The source tests exercise 255 matching roots, zero matches, overflow, aggregate
raw-body refusal before transfer, canonical escaping overflow, malformed
lineage/native types, extra invalid refs, optional-ref transitions and source/
scope/by-job phantoms. The integer/real control reaches the final SQL itself
after both representations pass pure decoding. Distractor fixtures contain
2,000 same-project other-job and 2,000 foreign rows plus oversized nonmembers.
SQLite measured 101,000 instructions for the maximum clean cohort, and 177,000
including discovery/final comparison with distractors (zero-match: 81,000).
The SELECT-only PostgreSQL trace recorded 26 charged attempts before cleanup,
including its privilege probe/setup, with no UPDATE or schema CREATE grant.
The normal post-cleanup total is 28 by source accounting, not a printed final
measurement. The SQLite distractor trace similarly recorded 16 attempts before
four cleanup actions (20 by source accounting); the clean maximum trace records
20 after cleanup. Final-cap assertions passed after context exit in both suites. These
are synthetic measured capacities, not an index-independent throughput promise:
the schema has no by-job JSON or project-scope index and arbitrary global table
growth can still exhaust unchanged work bounds. The remaining-budget regression
proves fixed refusal and clean owned-pool reuse when prior work leaves too little
SQLite VM budget. Proposed whole-service 74/162 traces remain unmeasured.

Development checks exposed fixture assumptions before final proof: an initial
escaping example did not exceed canonical 4 MiB; legacy Lineage casts SQLite
BLOB JSON and therefore needed an explicit stronger new-type oracle; a second
result fixture reused an existing digest under a different metadata ID; and
corruption fixtures initially hit normal FK/CHECK enforcement before reaching
the intended malformed-candidate read. The fixtures now construct those cases
deliberately without weakening production constraints. One real draft exception
gap in duplicate-key JSON handling is translated narrowly to the existing fixed
metadata refusal, outside any principal/project authority boundary.

Only operation_sources.py is added to the distribution allowlist. It is a
required emitted module, with no new entry point or dependency. Full installed
package/service/hosted acceptance remains a later composed gate; exact focused
test/static and synthetic PostgreSQL evidence is bound to the immutable handoff.
