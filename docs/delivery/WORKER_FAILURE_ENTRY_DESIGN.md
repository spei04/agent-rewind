# Worker failure P1 — entry design

**Adopted design, not complete entry or implementation authority.** D1v2, D2v4, D3v1 with its accounting amendment, D4v3 and the terminal-cancellation policy have been independently reviewed and adopted. The successor revision and accepted whole ledger predecessor remain pending. This draft activates no customer API, worker, provider or paid run.

This consolidates interfaces for [AR-010-B/P1 #97](https://github.com/spei04/agent-rewind/issues/97). The [worker failure execution plan](https://github.com/spei04/agent-rewind/blob/76f6039316ccad75e9760c48dcda140453bffb87/docs/delivery/WORKER_FAILURE_EXECUTION_PLAN.md) owns F1–F5 scope, allocation, sequence and exits. Source assumptions use immutable 76f6039316ccad75e9760c48dcda140453bffb87 and comparison 0cada5d13627b8029f8179c621938c7cf3ea8117. The interfaces and consistency choices below are source-bound design decisions; no live checkout is an input.

## Entry and operating boundary

Before any checkpoint code: accepted whole AR-010-A and AR-005-C, independently reviewed complete entry, one lead-owned migration/revision decision against the accepted predecessor, adopted reforecast and source-bound native validation plan. Actual native fit, races and recovery are implementation acceptance evidence, not a requirement to measure unimplemented code.

F1 covers existing ar6/ar7 SQLite catalog equivalence/capacity; F2 an empty dormant successor; F3 internal trusted persistence; F4 complete bounded consumers; F5 explicit marking/restore and complete P1 acceptance. Each follows the preceding accepted merge. Live worker integration remains P2. Migration-only/default customer and worker blocking remain through every checkpoint. No provider-durability reverse dependency, early-entry exception or new approval gate is introduced.

### F1 interface reconciliation after CHECK correspondence — 2026-10-29

The [reviewed repair `80f388bd`](https://github.com/spei04/agent-rewind/commit/80f388bd4ed69d1f1dd21ea16144c653a3720e4d) makes the copied clause policy and native CHECK correspondence inherited predecessor behavior. F1 must preserve them, not recreate them as new work.

The fused options/DDL observer must return selected names and the native declaration map: `tuple[list[str], dict[str, tuple[tuple[str | None, str], ...]]]`. The per-table policy/parser helper retains the copied restriction policy and existing `_sqlite_check_declarations` tuples. General `_sqlite_supported_clauses` keeps its independent bounded per-table SQL; fusion assembles the same map from validated rows. Both catalog paths still call `_sqlite_require_reflected_checks` before accepting shape. Preserve null versus empty names, stable duplicate/anonymous order, exact stripped body text and strict reflected record keys/types. Reflection remains the canonical catalog value, never the source of the native map; counts alone are insufficient.

Release complete DDL rows after parsing, but charge the retained declaration name/body slices and Python overhead. A fetch-one loop does not establish unbuffered driver memory. Observed revision flags, membership, transfer/row/sentinel bounds, close/primary-exception rules and PostgreSQL behavior remain unchanged. The execution plan below remains responsible for new-source equivalence and complete-path measurements; this reconciliation grants no F1 implementation or fit acceptance.

## Authoritative storage and native schema — adopted D1v2

Safe failure semantics live only in the selected job_failure_evidence relation. Verified rows require jobs.error/result SQL NULL and no result reference. Legacy text is never parsed or relabeled as authenticated failure. A historical marker records unknown provenance and is not an Error.

| Ordered field | Native type | Value |
| --- | --- | --- |
| schema_version | INTEGER NOT NULL | Integer1 |
| kind | VARCHAR(17) NOT NULL | verified_failure / historical_marker |
| project_id | VARCHAR(32) NOT NULL | Lowercase ASCII hex32 |
| job_resource_kind | VARCHAR(3) NOT NULL | job |
| job_id | VARCHAR(32) NOT NULL | Hex32 primary key |
| operation_id | VARCHAR(32), nullable | Actual operation; permitted marker NULL only |
| lease_generation | BIGINT NOT NULL | 0..signed64 maximum; verified>=1 |
| job_status | VARCHAR(9) NOT NULL | queued/running/succeeded/failed/cancelled |
| cause | VARCHAR(18), nullable | Five closed causes; marker NULL |
| phase | VARCHAR(15), nullable | pre_dispatch/outcome_unknown; marker NULL |
| origin_kind | VARCHAR(16) NOT NULL | admission/migration_marker paired with kind |
| correlation_id | VARCHAR(32) NOT NULL | Original admission correlation or marker ID |
| association_sha256 | VARCHAR(64) NOT NULL | Typed immutable association digest |
| source_sha256 | VARCHAR(64) NOT NULL | Variant-specific source witness |
| created_at_micros | BIGINT NOT NULL | Integer0..253402300799999999 |

Both dialects use these types without defaults, JSON payload, generated fields, sequences or timestamp columns. Sixteen CHECKs are one native scalar rule per column plus one joint variant rule. SQLite checks typeof, exact ASCII byte/character bounds and ranges; PostgreSQL checks declared integer/text types and fixed alphabets. Caller validation still rejects Python bool/float coercion: stored SQLite type cannot recover an input transformed by affinity.

The PK forbids another variant/generation for a job. Three immediate, noncascading FKs bind job_id to jobs, project/job scope to resource_scopes, and (operation_id,job_id,project_id) to operations. One successor-owned operations UNIQUE(id,job_id,project_id) support index supplies the exact parent key. A NULL operation bypasses that composite FK only for the separately guarded real v1 marker with zero operations.

SQLite adds three BEFORE INSERT/UPDATE/DELETE guards. PostgreSQL adds one SECURITY INVOKER guard function, one BEFORE INSERT/UPDATE/DELETE row trigger and one BEFORE TRUNCATE statement trigger: two public functions/seven noninternal triggers/zero rules in total. Original ar7 objects remain exact. Update/delete/truncate and replacement refuse, including no-op UPDATE. The insert guard rejects preexisting job keys before SQLite REPLACE can implicitly delete one; no UPSERT success path exists.

Insertion checks the actual scope/current generation/status and unfiltered 0/1/2 operation cardinality. Verified evidence requires a genuine v2 run, exact same-job/project operation, original non-NULL correlation, terminal status, NULL error/result and no result ref. Failed permits either cancel bit; cancelled requires true. Marker v1 requires zero operations; marker v2 requires its actual operation with NULL origin. Wrong-project/version/invalid rows never disappear through filtering. These checks establish association, not trusted producer identity or phase proof.

### Successor installation and identity

The successor has exactly21 tables/22nd-row overflow sentinel. Old ar7 retains20/21, earlier profiles17. A distinct observer verifies the complete table/index/constraint/executable/ACL inventory before deriving retained ar7 substate, including exact PostgreSQL native column/index/executable metadata projection as well as ordinary table shape; no fake revision, broadened old allowlist or ignored unknown objects. Table-specific SQLite token restrictions and all old profile bytes remain exact.

Current offline transaction code cannot accept a twenty-first table. An explicit successor-owned dispatcher reuses body/xid/cleanup mechanics: SQLite FK-on BEGIN EXCLUSIVE; PostgreSQL existing migrator lock, dedicated actual installation owner, session/writer/role exclusion and ACCESS EXCLUSIVE locks on the exact set. Installation proves/locks old20, then atomically creates/verifies21 and advances the actual version.

D1 retains original adoption/progress bytes, including the ar7 installed fingerprint. Actual alembic successor plus full observed successor profile and accepted deployment identity establishes installation; the old fingerprint describes the separately validated retained ar7 substate. No schema/marker progress table or restamped history. Successor envelopes report actual revision/profile and nested retained ar7; old decoders refuse successor.

D4 source_artifact_sha256 means the exact installed wheel archive digest selected by a trusted accepted release record, with candidate member and installed runtime/profile/source equality. Candidate status alone is not acceptance. installed_profile_sha256 is schema.checksum(observed_shape), which canonicalizes once internally, after equality to the accepted packaged dialect profile; it is not a checksum of already-canonical bytes or pretty-file bytes. Actual installation key/organization and selected scope must match captured intent.

No new physical roles or broad grants: dedicated common installation/table owner for install/marking; explicit SELECT for dormant bounded readers; narrow INSERT plus reviewed jobs effect rights for the later controlled producer. No app UPDATE/DELETE/TRUNCATE/DDL/owner rights on evidence. No PUBLIC EXECUTE or SECURITY DEFINER escalation. SQLite uses controlled owned connections/process authority. Exact native role/trigger behavior remains implementation proof.

## Terminal authority and atomic persistence — adopted D2v4

The private interfaces are:

    TerminalCoordinator(engine, authority)
      complete_failure(principal, context, event: CompletionEvent) -> CreatedFailure
      expire_generation(principal, context, expected: JobFence) -> CreatedFailure
      inspect_original(principal, context, retained: OriginalFailureIntent)
          -> Absent | MatchingOriginal | Conflict
    persist_verified_failure(connection, scope: IssuedTerminalScope)
          -> TentativeCreated

One-use coordinator, one acquisition-inclusive Work, immutable outcome facts. CompletionEvent is opaque and exact-object registered, not constructible from an exception/Fence/cause/callback. Its fixed execution owner first retains an acknowledged ReservationCoordinator claim, then registers execution; an actual trusted failure observation issues one consumed event. Unknown claim ACK issues no execution capability. Current worker.work_once is not already registered; P1 introduces only the internal seam.

Expiry separately observes native owner/generation/lease under locks; no caller time/expired flag is authority. It alone issues lease_expired. Completion issues budget_refused/dependency_failed/internal_fault/dispatch_uncertain from trusted stage evidence. Ordinary cancellation, JobStopped and evaluator false issue none.

Use existing visibility and project→organization→membership/key→job lock order, fresh record authority and exact operation/config association. SQLite owns BEGIN IMMEDIATE; PG READ COMMITTED preserves original xid/body. A private RLock-protected terminal registry binds exact connection/owner/scope/Work/native transaction/event/original receipts/state. Bare/idle/foreign/replaced/poisoned connections cannot gain rights. Finally removes registry entries; only bounded immutable original intent and outcome survive.

Require running v2 run, exact owner/generation/lease, valid cancel, NULL error/result, zero result refs, authentic origin/association and absent evidence. Conditional native UPDATE changes status only and matches every original bounded job field plus generation and original association. Exactly one affected row is required before exactly one evidence INSERT. Zero is stale/refused; unknown/negative/extra count refuses; uniqueness conflict never becomes success.

Completion requires the lease live and chooses failed/cancelled from cancel. Expiry requires the retained lease expired and chooses failed with either bit. No ledger hold/period/call mutation. Flush every accepted successor-profile deferred constraint; the three added FKs are immediate, so the current deferred set remains inherited ar7. Refresh full bounded after-image/current authority, validate body/xid, then take the final native clock. Compare retained eligibility/after-image purely; no SQL follows except inherited commit controls. This linearizes eligibility before COMMIT, not continuous wall-time eligibility through it.

**Initial F3 emits only outcome_unknown.** D1 retains pre_dispatch vocabulary but D2 exposes no issuer/flag. Later enablement requires a reviewed cohort where every possible dispatch consumes one acknowledged durable reservation first, unknown ACK never dispatches/re-reserves, logical identity is one-use and all generations participate in exclusion. Only then can locked unfiltered all-call absence prove pre-dispatch. Completed-call evidence is unavailable.

All five initially emitted causes map to fixed outcome_uncertain, retryable=false and original admission request_id. Missing producer/origin/transaction authority refuses rather than becoming a valid uncertain record. Wire Error remains exactly code/message/request_id/retryable.

Closed private reasons preserve the D2 mapping: invalid_intent/capability_not_issued/invocation_reused→invalid_request; original_identity_conflict→idempotency_conflict; unsupported_profile→schema_incompatible; stale_source/not_eligible/origin_unproved/capacity_exceeded/invalid_native_state→dependency_unavailable. Existing identity/action exceptions retain identity/order. CreatedFailure needs commit ACK and clean completion. An exception code never proves rollback; ACK plus cleanup failure remains committed-cleanup-failed. Separate original inspection never recreates intent, retries writes or grants dispatch.

Legacy Database/worker/direct/admission/artifact/projection/offline writers remain excluded from the bounded initial cohort. SQLite legacy FOR UPDATE plus id-only completion is not concurrency proof. Real participating exclusion and conditional generation effect must establish the invariant.

## Bounded current reads and paid denial — adopted D3

The current job observation keeps original16 fields, including cancel, plus generation/evidence count/unfiltered any-call/evidence15. This extends the existing identity, not a 260th identity.

Durable association binds scope, original operation14, immutable job9 and config8. Verified terminal source binds that association, terminal job15 excluding cancel, generation, any-call and evidence core13 excluding digests. No enclosing raw16 digest reintroduces cancel. Typed frames retain bounded native timestamp-to-Text strings without normalization; normalize only signed float zeros. Marker W remains separate and strict.

| Stable state | Result |
| --- | --- |
| Healthy supported state, NULL error, no verified failure | Existing error:null; marker grants no authority |
| Failed without verified evidence, or non-NULL legacy error | Safe503 without parsing/repair |
| Valid failed evidence, cancel false or true | Stable mapped Error/original admission ID |
| Valid cancelled evidence, cancel true | Error only for independently proved failure |
| Contradictory status/generation/origin/scope/result/evidence | Safe503 after unchanged visibility |
| Any retained source changes during read | Final snapshot refuses; later fresh read may succeed |

GET never hashes full legacy bodies or W, writes, marks or retries internally. Stable post-terminal cancel does not invalidate verified provenance; in-read cancel still fails raw16 matching. Marker replay can refuse strict source drift while a later healthy GET remains valid.

read_successor_job uses one SQL target: scoped bounded J LIMIT2; evidence F candidate-first MATERIALIZED by job_id only LIMIT2; saturated count, unfiltered provider-call EXISTS, guarded transferred cells. Invalid/wrong-project/version/generation rows cannot become absence. Original unsupported legacy bodies refuse before transfer. Proposed three named binds: project/job/remaining.

matching_successor_query uses one native snapshot and two proposed binds: receipts/project. Preserve all raw operation/job/run/descriptor/ref/cohort predicates; additionally match evidence count/cells/native types/generation/any-call. Return original keys under count+1 sentinel<=260; exact duplicate-free set equality and final fresh authority are mandatory. This is not response linearizability after that snapshot.

The successor-only wire is:

    {"v":1,"rows":[...],"observations":[...]}
    non-job = [domain,id,values]
    job = [domain,id,raw16,[generation,count,any_call,evidence15_or_null]]

Fixed field arrays come from the accepted profile. Old ar7 wire/counters are unchanged. Both new counters start35, then charge identical exact canonical row/observation lengths and comma only after first item. Exact/type-aware repeat costs zero, conflict refuses; both counters must equal encoded length before SQL.

GET remaining =4MiB−wire−active_frame. Cancellation remaining =4MiB−22−original_association−wire−active_frame; original is4 bytes for null before capture, exact retained association encoding afterward. Reserve each measured frame before allocation,<=4096; hash/compare and release its buffer before large cohort loading. No uncounted side book/frame or reset of visits/Work.

Analytic, not native/RSS measurements: selected transfer2433 bytes before small validity flags, selected job1376, evidence array412, association frame3331, terminal frame1910, response564. Field-array savings510 exceed extension/header445, making supported complete wire at least65 bytes smaller. Actual serializer/counter/maximal-cohort/native memory lifetime proof remains required.

Every NEW paid claim/reserve denies unfiltered job-key evidence existence, even malformed/stale/unknown/foreign-project candidates. Add NOT EXISTS to existing conditional claim UPDATE, first provider-call INSERT…SELECT and conditional gross UPDATE, plus EXISTS in the existing final fence. Keep all original predicates/rowcounts/clock/authority. Historical original repeat is not paid permission. Proposed bind counts6/18/6 and<=5 final-fence values are analytic; actual compiler/VM/time/plan evidence remains pending.

## Restart-safe operator markers — adopted D4v3

Explicit operator-only commands:

    rewind migrate failure-marker-prepare
    rewind migrate failure-marker-apply
      --intent PATH --intent-sha256 DIGEST --capture-receipt PATH
    rewind migrate failure-marker-inspect
      --intent PATH --intent-sha256 DIGEST --capture-receipt PATH

Prepare captures read-only state and private immutable files after clean release, no marker insertion. Apply checks original input/current source under successor-owned offline exclusion and inserts once or recognizes the exact original. Inspect is separate/read-only after uncertainty. Absence grants no dispatch or automatic retry.

Closed14-field intent: intent_version=1, installation_key, installed_revision, installed_profile_sha256, source_artifact_sha256, organization_id, project_id, job_id, nullable operation_id, marker_id, expected_source_sha256, source_capture_sha256, backup_evidence_sha256, drain_evidence_sha256. Closed15-field capture replaces intent_version/source_capture_sha256 with receipt_version=1, native_dialect and original_five_table_source_sha256.

Each raw/canonical file<=4096. Strict types/lexical/duplicate/unknown/BOM/float/exponent/depth/control/surrogate refusal. Open once no-follow/nonblocking, verify regular owner-only file/size, read<=4097, close and decode that buffer. Capture has no intent hash: exclusive/fsynced capture first, hash its exact original bytes including LF, then exclusive/fsynced intent and directory. No overwrite, circular digest or replacement after partial failure.

W is the original bounded five-table source witness plus selected extensions, retained before execution and reused unchanged, including unrelated source drift and cancel. Canonical SQL equality is not physical/lexical preservation; independent offline evidence preserves raw source/audit/ciphertext. GET never recomputes W.

Apply validates native installed identity/roles/drain, source and unfiltered candidates before effect. Marker has NULL cause/phase and never fabricates v1 operation. The immutable row is the sole marker checkpoint. Repeat returns original identity/timestamp; uncertainty retains intent/capture and changed-source/conflict refuses, never refreshes W.

Closed result_version1 envelope: action, captured/complete/present/absent status, actual installed revision/profile, raw intent digest, marker ID and marker_timestamp,<=2048 bytes. D1 defines marker_timestamp as canonical decimal retained created_at_micros, unchanged on repeat, NULL only for capture/absence. No timezone conversion/new timestamp.

Truthful rollback/ACK facts remain mandatory. Schema downgrade always refuses, even empty. Recovery is verified physical restore with matching artifact/profile/source, not DROP evidence and restamp ar7.

## Fixed limits and remaining acceptance

### Observed repaired-predecessor baseline — 2026-10-29

At [source `0be52817`](https://github.com/spei04/agent-rewind/commit/0be5281750b494729d2aa6e8c64e13bf50f1042b), one bounded synthetic service-key claim/reserve sample per native runtime was independently accepted:

| Python | SQLite | Claim: total Work units | Reserve: total Work units |
| --- | --- | ---: | ---: |
| 3.11 | 3.53.1 | 488 | 504 |
| 3.12 | 3.45.1 | 488 | 504 |

These are original cumulative post-cleanup counters; an ordinary/control/cleanup decomposition was not collected. Both calls acknowledged their commits, preserved all unrelated typed state, and passed exact claim/reservation delta and release checks. The source and owned environments stayed unchanged. Each row is one sample of the current predecessor, with its own native build. F1, the successor schema and broader capacity acceptance still require their planned measurements under unchanged limits. Historical 502/470 arithmetic remains separate from these observations.

### CHECK-repaired predecessor samples — 2026-10-29

The separately reviewed samples on [repair `80f388bd`](https://github.com/spei04/agent-rewind/commit/80f388bd4ed69d1f1dd21ea16144c653a3720e4d) again observed 488 claim / 504 reserve Work units, cumulatively after cleanup, once on each supported interpreter with its own native build. Exact whole-state deltas, transaction outcomes and release were checked. These finite samples do not supply an ordinary/control/cleanup decomposition, reliability or remaining-capacity claim, measured fusion savings, or F1/successor fit. Keep the earlier samples and static estimates above distinct; F1 still needs complete principal/service-key measurements on its own source under unchanged limits.

One online Work:504 ordinary/512 total,8 cleanup,10s/20M SQLite VM. Offline2048/120s is never borrowed. Keep259 identities,4096 selected job/frame,4MiB complete retained book,64 compiled binds,260 sentinel,2048 response; financial2MiB/65,536 rows/4,096 accounts and original source/page bounds unchanged.

492 ordinary owner units is measured on earlier exact source;502 keyed/470 fused are static. Smaller wire, fewer columns or same SQL-target count does not prove successor fit. Trigger/native catalog/plan/time/VM/memory costs remain real.

The linked F1–F5 plan owns finite acceptance: old-profile equivalence; native schema/ACL/rollback; actual issuer/exclusion/conditional effects and uncertainty; maximal inherited reads/final snapshot/paid denial; marker restart/preservation/physical restore; successful PR/main and matching installed artifacts. No historical component proof becomes new-source execution.

Outstanding before code: complete independently reviewed entry, accepted whole AR-010-A and AR-005-C with the accepted predecessor artifact, the exact successor revision/owner decision, and the successor artifact identity/binding design plus implementation assignment and native validation plan. Actual successor wheel/profile bytes and their installed-source equivalence are earned during implementation/delivery, not a pre-code prerequisite. This draft adopts no additional estimate, task status or execution authority.
