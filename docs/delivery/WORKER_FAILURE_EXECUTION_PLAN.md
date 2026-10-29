# Worker failure execution plan

Planning reforecast adopted on 2026-10-29 for [AR-010-B/P1 #97](https://github.com/spei04/agent-rewind/issues/97). P1 and [P2 #98](https://github.com/spei04/agent-rewind/issues/98) remain **Not started**, with null accepted merge/review. This plan implements the existing DDL reforecast clause; complete entry design, concrete revision and implementation assignment remain pending. The [machine ledger](../../contracts/proposals/execution-backlog.json) and [checkpoint cards](../EXECUTION_BACKLOG.md#ar-010-b-p1) are authoritative for current status and acceptance.

## Allocation and sequence

P1 is 12 [9–18] BE engineering days, low confidence, replacing its former 2 [2–3]. P2 remains 2 [2–3], medium-low; aggregate #96 is 14 [11–21], low. Checkpoint allocations are included in P1, not extra tasks or effort. Ordinary review, tests and documentation are included; calendar waits, paid work and additional staffing are not implied.

| Checkpoint | Scope | Included days [range] | Confidence |
| --- | --- | ---: | --- |
| F1 | Existing-profile SQLite catalog equivalence and capacity precursor | 2 [1.5–3] | medium-low |
| F2 | Dormant successor schema, profile and migration foundation | 3 [2–4.5] | low |
| F3 | Trusted bounded failure persistence and identity | 2 [1.5–3] | low |
| F4 | Complete bounded successor consumers | 2 [1.5–3] | low |
| F5 | Restart-safe operator markers, preservation, restore and P1 delivery | 3 [2.5–4.5] | low |

## Entry, ownership and acceptance

Before any checkpoint code, require accepted whole AR-010-A including P2 and AR-005-C, complete independently reviewed entry design, lead migration owner/revision decision against the accepted predecessor, this adopted reforecast and source-bound native validation plan. No precursor is an early-entry exception. Each F2–F5 requires the preceding accepted merge. Backend owns implementation/migration, Quality independent behavior/native evidence, Review independent source/security and the lead revision/integration. These are logical roles for later assignment.

Retain accepted C04, AR-005-C guard/recovery, AR-008-B bounded Operation/HTTP and AR-011-B safe-vocabulary producer reviews. Pin the accepted whole AR-010-A source/profile, PR/main receipts and installed artifact before code. Review the exact query/frame/capability and migration/privilege/restore plans; do not assign a revision name now. Actual producer, race, preservation and native capacity proofs are earned during implementation and required for acceptance, not before unimplemented code.

Native/producer/budget proof is earned during implementation and required for acceptance, not a requirement to measure unimplemented code before entry. Each checkpoint needs independent source/security review, scoped actual SQLite/restricted PostgreSQL evidence as specified, configured checks, exact successful PR/main and installed candidate/source equivalence before the next checkpoint. No previous component outcome is relabeled as new-source execution.

Preserve default migration-only/customer-admission/worker-dispatch gates through EVERY checkpoint, including F1, dormant schema F2, persistence F3, successor consumer F4 and explicit offline marker F5. Internal tests/explicit operator code do not activate the default API or worker, install a customer-ready release profile or grant production access. Even complete P1 does not start #98 without its accepted prerequisite/entry handoff or satisfy G1/customer/funding/data gates.

Only final F5 acceptance plus every original P1 requirement can populate P1 accepted merge/review; P2 remains a separate entry and the aggregate waits for both packages. AR-011-C and AR-012-B still require whole AR-010-B; no reverse provider-durability dependency is introduced.

## Fixed contracts and policy

Retain 15 typed relation columns; old ar7 profiles/catalogs/behavior; 259 identities, 4096 selected-job/evidence and each finite frame, 4MiB total book, 64 compiled binds, 260 final-key sentinel, 2048 response. Online one Work:504 ordinary/512 total/8 cleanup/10s/20M SQLite VM; financial2MiB/65536 cumulative rows/4096 accounts and original source bounds unchanged. Offline source/marker uses existing separate bounded LedgerWork2048/120s and source1GiB/16MiB row/1M rows/4096 page contract, never borrowed online.

The planning recommendation is one additive immutable 15-column provenance relation with mutually exclusive verified-failure and historical-marker variants, not extra tables admitted under the frozen ar7 profile. Safe Error is authoritative only in the new relation; supported future verified rows keep jobs.error/result null. Frozen ar6/ar7 catalogs and behavior remain exact. A successor adapter must explicitly validate its profile and typed association; no broad grants or customer-ready default follow.

Verified failure binds trusted admission origin, issued generation/transaction authority and a conditional terminal effect. The current cancel bit is excluded from every durable verified-failure digest, but retained in the full current 16-field job receipt and final comparison. A failed row with cancel=true is valid after authorized cancellation or the expiry route; cancelled plus independently verified failure is distinct from ordinary cancellation with error:null. The bit proves neither origin nor chronology. Normal completion and observed-expiry have separate predicates. Legacy SQLite FOR UPDATE plus an id-only completion UPDATE is not concurrent immutability evidence; participating-writer exclusion and conditional generation effects must prove that invariant in implementation.

Use the accepted finite typed frames, retaining bounded native timestamp-to-Text receipt values without timezone/string normalization; normalize both signed float zeros. Preserve bounded original receipt identities; extend the successor job receipt rather than add a 260th identity. Final revalidation covers generation and unfiltered evidence/absence in the same snapshot. Paid authority rejects any current-job evidence, including malformed candidates, without filtering it into absence. Never fetch/hash full legacy bodies in GET; missing, malformed or unsupported evidence stays safe 503, with no GET writes or invented origin. Pre-dispatch claims require owned exclusion, unfiltered absence across all generations, and a trusted producer invariant that reserves before every possible dispatch. Missing producer authority refuses; unavailable dispatch certainty with valid authority maps conservatively to outcome_unknown. Completed-call evidence is unavailable until its own accepted producer.

Historical markers retain an immutable operator intent and full bounded selected-source witness before execution, reused after interruption or uncertain acknowledgment. Its strict witness still binds cancel and unrelated source drift, so changed-source replay may refuse even while stable GET remains valid. Canonical SQL witness equality is not physical/lexical byte replay; separate offline evidence proves original source/audit/ciphertext preservation. No invented v1 operation, legacy-text conversion, current poll correlation or freshly recomputed intent substitutes for producer authority.

## Evidence and stop conditions by checkpoint

### F1 — Existing-profile SQLite catalog equivalence and capacity precursor

Proposed source boundary: `agent_rewind/migrations/ledger_reader_catalog.py`, `tests/test_ledger_catalog_budget.py`, `focused existing catalog fixtures/controls only if needed`. Names are planning seams, not assigned files/revisions.

Owner: Backend; lead owns scope; Quality raw/whole-path oracles; Review SQL/security.

All common pre-code prerequisites. Review accepts exact query/projection/sentinel and old-observer equivalence design. Lead owns this prerequisite as P1/F1 rather than an early AR-010-A exception.

Actual ar6/ar7 fresh/legacy raw native-observer equality; missing/extra/duplicate table, invalid options/type/null/oversize and forbidden-clause negatives; preserved independent catalog mismatch detection. Measure complete immutable-history and complete principal/key claim/reserve paths under same Work, both supported SQLite interpreters/native versions, recording every target/control/row/bind charge, cleanup, time and VM. Existing PostgreSQL old-profile controls establish unchanged branch behavior; no new PG batching.

Exit: All named positive/negative equivalence cases pass without changed gates; supported complete existing requests fit unchanged limits and measured query deltas reconcile to trace. Record actual remaining capacity. No minimum guessed saving or automatic successor-fit credit.

Allocation basis: Two profile families, literal token semantics, fresh bounded transfer and complete-path accounting require separate source/equivalence and native-measurement work; reuses existing fixtures, not a new framework.

### F2 — Dormant successor schema, profile and migration foundation

Proposed source boundary: `new focused agent_rewind/migrations/failure_schema.py and failure_catalog.py (names provisional at entry)`, `explicit new profile capture files after revision decision`, `narrow version registry/compatibility/state branches in existing migrations/schema.py, compatibility.py, ledger_compatibility.py, ledger_history_sql.py, ledger_state.py`, `focused migration/catalog/privilege tests`. Names are planning seams, not assigned files/revisions.

Owner: Backend migration owner; Review catalog/privilege review; Quality preservation and both-dialect validation; lead reserves revision.

Common prerequisites plus accepted merged F1 and actual capacity report; complete relation/constraints/grants/revision/profile/rollback design independently accepted before this code. Unknown full successor fit is an explicitly planned later implementation test, not evidence fabricated here.

Actual SQLite/restricted PostgreSQL upgrade, exact observed columns/types/constraints/triggers/indexes/privileges, duplicate/invalid variant/native byte/range rejection, forbidden mutation and partial/unknown/future schema refusal; interrupted upgrade/rollback and original-row/audit/ciphertext comparison. Old-version serving guard must refuse successor unless the later complete adapter is selected.

Exit: Exactly one additive relation/profile transition; all predecessor source/ciphertext bytes unchanged except explicit additive schema metadata; known unsupported clients refuse. Captured observed catalog equals proposed profile in both dialects and interrupted upgrade cannot report success.

Allocation basis: New two-dialect DDL, immutable association constraints, captured profiles and compatibility/rollback proofs exceed a parser-only change. Reuses existing migration/restore harnesses.

### F3 — Trusted bounded failure persistence and identity

Proposed source boundary: `new agent_rewind/failure_evidence.py`, `new agent_rewind/failure_persistence.py`, `narrow existing owned-connection/authority seams only if the accepted design requires them`, `focused tests/test_failure_evidence*.py and persistence native fixtures`. Names are planning seams, not assigned files/revisions.

Owner: Backend; Quality independent state/ACK/identity oracles; Review producer/security review.

Common prerequisites plus accepted merged F2; independent API/capability/producer table review, including originating admission producer and actual conditional-generation/exclusion design. The legacy SQLite id-only completion UPDATE is not reused as a concurrency proof.

Strict type/enum/native/encoded one-over and pre-materialization cases, all fixed mappings and secret canaries; bare/foreign/idle/replaced transaction refusal; wrong scope/origin/generation/role, exact repeat/timestamp and conflict; actual both-dialect helper commit/rollback/deferred-failure/uncertain ACK with complete state preservation. Establish real participating-writer exclusion/conditional mutation, not mocked locks; both input classes tested, actual live caller races remain #98.

Exit: One committed semantic identity/timestamp at most per job; exact replay never mutates; invalid/stale/unowned inputs have no protected writes; actual outcome facts agree with retained whole state and cleanup in both dialects.

Allocation basis: Reuses accepted operation/reservation ownership primitives but adds two distinct capability predicates, strict framing and atomic immutable storage. Does not include #98 live wiring.

### F4 — Complete bounded successor consumers

Proposed source boundary: `agent_rewind/operation_reads.py`, `agent_rewind/operation_sources.py`, `agent_rewind/operation_service.py`, `explicit successor migration ledger_compatibility/history/state/service/inspection adapters`, `scoped changes in reservation.py/reservation_rows.py for exact candidate presence checks`, `focused Operation/reservation consumer tests`. Names are planning seams, not assigned files/revisions.

Owner: Backend adapters; Quality independent source-drift/capacity/state oracles; Review query/accounting/authority review.

Common prerequisites plus accepted merged F3; accepted bounded SQL/typed frame/final-absence design and source-bound validation plan, prior Operation adapter producer reviews retained. No forward dependency on AR-012-B/provider durability tables.

Actual supported maximum 259-identity cohort and one-over, combined selected job/evidence4096 and total4MiB, <=64 compiled binds/260 sentinel,2048 wire; wrong/malformed/duplicate/absent evidence and final-snapshot races; fixed error/correlation/evaluator-false cases; post-terminal cancel and expiry mapping. Measure entire successor principal/key claim/reserve and GET/cancel helper paths, all mandatory catalog/history/source/financial/mutation/cleanup costs, both dialects under unchanged limits. Joins are charged and measured, not declared free.

Exit: Every named supported consumer succeeds or produces its specified conservative refusal with truthful cleanup; final native traces contain all work within caps. No static502/470 substitution for measured results and no undocumented current-field drift exemption.

Allocation basis: Bounded adapter reuse reduces work, but exact cross-consumer revision dispatch and near-limit actual whole-path validation remain material risks.

### F5 — Restart-safe operator markers, preservation, restore and P1 delivery

Proposed source boundary: `new focused migrations/failure_inputs.py and failure_service.py (names finalized at entry)`, `existing explicit operator/CLI registry and recovery documentation`, `existing ledger_source/restore interfaces reused without limit changes`, `focused marker/recovery tests using existing process/restore harnesses`, `final distribution/inventory metadata for actual accepted source`. Names are planning seams, not assigned files/revisions.

Owner: Backend operator/recovery; Quality independent preservation/native recovery and artifact comparison; Review source/security/evidence; lead package acceptance.

Common prerequisites plus accepted merged F4; exact offline intent/file authority, exclusion, manifest/progress/catalog and restore plan independently reviewed; actual complete successor native proof from F4 is required at final package acceptance.

Actual SQLite/restricted PostgreSQL fresh/exact repeat/conflict, unauthorized/nonregular/malformed/oversized intent, missing-origin/v1 without fabricated operation, changed source including cancellation, interrupted insert/commit ACK/cleanup and restart with the SAME intent; complete no-source-mutation maps. Existing bounded child/process lifecycle and real PostgreSQL backup/restore prove final authority/ACL/catalog/marker identity. One final integrated source gets required hosted PR/main, package/security and installed-artifact byte/behavior evidence; no discarded first failures.

Exit: Old source/audit/ciphertext preservation exact, same intent/row/timestamp after accepted replay/restore, wrong-source and unsupported cases refuse without writes; actual native original bounds and all final source/CI/candidate identities agree. No partial checkpoint closes #97.

Allocation basis: Real interruption/ACK and owner/ACL-preserving physical restore plus integrated delivery are separate from dormant DDL or parser work. Reuses existing harnesses, no resource purchase.

## Capacity and reforecast boundaries

The retained owner reservation measured 492 ordinary / 494 total Work units. Key-route 502 and hypothetical fused 470 are static arithmetic, not measured fit, savings, latency, VM or memory proof. F1 targets only existing ar6/ar7 SQLite observation, leaving the independent schema.catalog per-table observer and PostgreSQL path intact. Preserve every table-specific supported-clause restriction, exact membership/multiplicity/options, null/invalid/oversize refusal, <=65536 bytes per DDL and <=1310720 cumulative ar7 transfer. No hidden out-of-Work query, stale/global cache or budget relaxation is allowed.

Reforecast at measured F1 capacity, observed F2 catalog/rollback and before F5 recovery. If exact equivalence or complete successor fit fails under existing limits, stop subsequent assignment and refine the design; do not turn a conservative refusal or static calculation into successful capacity evidence. This plan adds no paid/provider/native execution authority, acquisition/held-out work, resources, activation, new external approval gate or scope outside #97.

## Planning arithmetic and history

The adopted change adds ten base/fifteen upper days and four PRs: 155 aggregates, 171 planned PRs, 569 outer edges, 53 parents, 30 gates and 20 contracts. Parent AR-010 is 20 days/10 PRs; M1 is 75.5 and BE 110.5. Total base is 482, upper 814.6 and alternative 25% allowance 602.5; the unchanged effort path is 183.5 days (52.4 hypothetical workweeks at 3.5 delivery days/week). No task/package status, acceptance or external gate changes. Earlier 167 PRs / 472 base / 799.6 upper / 173.5 path and two-day P1 figures remain dated history, not the current forecast.
