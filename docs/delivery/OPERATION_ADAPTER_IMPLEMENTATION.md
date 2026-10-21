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
