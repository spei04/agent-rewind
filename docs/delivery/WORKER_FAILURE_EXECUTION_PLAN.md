# Worker failure execution plan

F1 is **Merged; checkpoint accepted** at [main89](https://github.com/spei04/agent-rewind/commit/89a43e4355413ba5cca96e09c410c63c634138fb) after PR128/main/candidate delivery. F2 schema/catalog/profile components are accepted at `76437340`; Backend now implements the owned transaction, Quality supplies independent native oracles and Review checks each stage under source handoff 22608a0f. P1 and aggregate AR-010-B remain **In progress** with null final acceptance; F2 is **In progress** with null acceptance; F3-F5 and [P2 #98](https://github.com/spei04/agent-rewind/issues/98) remain **Not started**. The [machine ledger](../../contracts/proposals/execution-backlog.json) and [checkpoint cards](../EXECUTION_BACKLOG.md#ar-010-b-p1) are authoritative; five planned F1-F5 PRs, estimates and sequential gates are unchanged.

## Allocation and sequence

P1 is 12 [9–18] BE engineering days, low confidence, replacing its former 2 [2–3]. The retained P2 estimate is 2 [2–3], medium-low; aggregate #96 is 14 [11–21], low. Those figures predate the admitted-startup audit and require a coordinated reforecast before P2 assignment. Checkpoint allocations are included in P1, not extra tasks or effort. Ordinary review, tests and documentation are included; calendar waits, paid work and additional staffing are not implied.

| Checkpoint | Scope | Included days [range] | Confidence |
| --- | --- | ---: | --- |
| F1 | Existing-profile SQLite catalog equivalence and capacity precursor | 2 [1.5–3] | medium-low |
| F2 | Dormant successor schema, profile and migration foundation | 3 [2–4.5] | low |
| F3 | Trusted bounded failure persistence and identity | 2 [1.5–3] | low |
| F4 | Complete bounded successor consumers | 2 [1.5–3] | low |
| F5 | Restart-safe operator markers, preservation, restore and P1 delivery | 3 [2.5–4.5] | low |

## Entry, ownership and acceptance

### F2 component progress; owned transaction next — 2026-10-30 (Pacific)

Integrated component source `76437340de1685918052799ceebccbc0b5006093`
contains the accepted unregistered schema, independent literal profiles/native
oracle and complete catalog observation. Schema peer `264890a4`, profile peer
`8cb86979`, catalog peer `4385eb88` and independent QA `65e16565`
retain their source and original-outcome qualifications. Catalog coverage is
36 retained SQLite/offline controls plus 18 current PostgreSQL cases per
interpreter, not a fresh combined 54-case run. The original rejected positive,
native-source corrections and assembly incident remain retained.

Backend owns `failure_transaction(engine, outcome, *, work)` and focused
controls in SECONDARY; Quality owns independent native transaction oracles in
PRIMARY. Reuse the existing lifecycle to prove old20/new21 exclusion, ownership,
body/transaction identity, DDL/version rollback and acknowledgment/cleanup
ambiguity. These low-level physical fixtures grant no installed-revision,
readiness or producer authority. Service/migration wiring, complete-path fit and
matching delivery remain required. F2/P1/aggregate acceptance stays null;
F3-F5/P2, all fixed limits, five planned PRs and estimates are unchanged.

### F1 delivery accepted; F2 assigned — 2026-10-30 (Pacific)

Lead acceptance at 2026-10-31T02:36:02.319699Z binds reviewed head `e036d3e7adff0399cc3888266dfbcc3d6b854ea8`, protected merge `89a43e4355413ba5cca96e09c410c63c634138fb` and tree `616ad9817b4526d579de256244d2608f42084fa9`. [Original main 41155393767](https://github.com/spei04/agent-rewind/actions/runs/41155393767), attempt 1, passed all eight jobs and 8,815 exact selected cases per version: Python 3.11 8,770 passes/45 skips, Python 3.12 8,784 passes/31 skips. All 3,936 phase facts for the 656 selected cases per version passed. Original session limits remain 2700/2700/3600 seconds.

Final independent peer `39566b17e1e6db581d0d0c90d56656421b26a0482a9113657d404d42a8567e29` and lead index `70bf4b00f6b01622b241d53b2c0735eac26f7b01e356450b54fbef0278857b8c` accept only F1/internal dispatch foundation delivery. Private durable record `reviewed-delivery-20261031-pr128-89a43e43.json` has SHA256 `b1bef87e46de421f2cd8a5994749e2578681fee861fa1f1ffca368bfcc45787c`. Candidate `13026742056` is 959,189 bytes, SHA256 `e2014f918d08c8a66082a5a9113da2f4e28df35806ca8291c21592a561354b8b`; its wheel SHA256 is `d552cd7d8daf43aedb77477bdc285843353540d949f6c4c6ec7601e3de771fc5`, with all 149 runtime members verified, its own hosted installed smoke/CLI and separate current final-image trust proof.

Source handoff `22608a0f028e60946afa0ad659655ac06f5241fb99a58e3a86d9438e12a6c4f5` preserves e7a70bb9/D1-D4 and accepted predecessor provenance, and assigns Backend F2 schema/native work in SECONDARY. Planning owns PRIMARY metadata; Review independently checks source/evidence; the lead owns integration. F2 keeps `ar_0008_failure_evidence`, down_revision `ar_0007_ledger`, `failure_evidence_v1` and the reserved dialect profile names below. Its first schema commit is an internal review stage of the same F2 PR, not a sixth planned PR. F2/P1/aggregate final acceptance remains null; F3-F5/P2 remain Not started. Full successor fit, startup, research, production and paid allowance are not established.

The original [PR127 failure](https://github.com/spei04/agent-rewind/actions/runs/41144872313) and [superseded incomplete PR128 run](https://github.com/spei04/agent-rewind/actions/runs/41147939612) remain separate retained incidents (indexes `41b0197b` and `546c9223`), alongside the [dated correction history](../ASSIGNMENTS.md#rollback-test-correction--2026-10-30). No retrospective cause or old-run acceptance is inferred.

### Worker P1 entry accepted; F1 assigned — 2026-10-29

At 21:14:57 UTC, lead entry e7a70bb9 accepted D1-D4 and assigned only AR-010-B/P1/F1 to Backend on delivered [M122](https://github.com/spei04/agent-rewind/commit/aed2c20d314e0e361fa4c8e438f839802e1e729b). Preparation b91b0afa and independent review 52a9800d bind the repaired F1 interface; accepted predecessor wheel SHA256 13bb8a8caa1b1c8226b8f57eda367243024a1edb7b2c265ff2453cc27e1501aa and AR-005-C remain prerequisites satisfied by their own evidence. The lead reserved later-F2 ar_0008_failure_evidence, owned by Backend; F1 adds no revision/schema.

AR-010-B, P1 and F1 are In progress with null source/merge/delivery acceptance; F2-F5 and worker P2 remain Not started. Task counts are 31 Verified / 1 In progress / 123 Not started; delivery packages 11 / 1 / 3. Quality owns bookkeeping/corpus handoff and independent oracles; Review checks source/evidence; the lead integrates. GitHub #96/#97 synchronization/readback remains separate lead work. Native fit, later sequential accepted merges, corpus acceptance and production gates are unchanged.

The lead's later-F2 reservation is ar_0008_failure_evidence, down_revision ar_0007_ledger, module agent_rewind/migrations/versions/0008_failure_evidence.py, profile failure_evidence_v1 with sqlite_failure_evidence.json and postgresql16_failure_evidence.json; branch_labels and depends_on are null. Backend owns migration/schema/profile implementation. The fresh M122 collision review and accepted predecessor wheel are bound by entry e7a70bb9. No successor migration is part of F1, and actual successor profile/wheel bytes remain future implementation evidence.

<details>
<summary>Superseded pre-entry status and source statements — 2026-10-29</summary>

Planning reforecast adopted on 2026-10-29 for [AR-010-B/P1 #97](https://github.com/spei04/agent-rewind/issues/97). P1 and [P2 #98](https://github.com/spei04/agent-rewind/issues/98) remain **Not started**, with null accepted merge/review. This plan implements the existing DDL reforecast clause; complete entry design, concrete revision and implementation assignment remain pending. The [machine ledger](../../contracts/proposals/execution-backlog.json) and [checkpoint cards](../EXECUTION_BACKLOG.md#ar-010-b-p1) are authoritative for current status and acceptance.

The [concrete worker failure entry design](WORKER_FAILURE_ENTRY_DESIGN.md) specifies the adopted schema, producer, reader and operator interfaces. Complete prerequisite entry, the successor revision and implementation assignment remain pending.

Before any checkpoint code, require accepted whole AR-010-A including P2 and AR-005-C, complete independently reviewed entry design, lead migration owner/revision decision against the accepted predecessor, this adopted reforecast and source-bound native validation plan. No precursor is an early-entry exception. Each F2–F5 requires the preceding accepted merge. Backend owns implementation/migration, Quality independent behavior/native evidence, Review independent source/security and the lead revision/integration. These are logical roles for later assignment.

Retain accepted C04, AR-005-C guard/recovery, AR-008-B bounded Operation/HTTP and AR-011-B safe-vocabulary producer reviews. Pin the accepted whole AR-010-A source/profile, PR/main receipts and installed artifact before code. Review the exact query/frame/capability and migration/privilege/restore plans; do not assign a revision name now. Actual producer, race, preservation and native capacity proofs are earned during implementation and required for acceptance, not before unimplemented code.

Proposed source boundary: `agent_rewind/migrations/schema.py`, `agent_rewind/migrations/ledger_reader_catalog.py`, `tests/test_ledger_catalog_budget.py`, `focused existing catalog fixtures/controls only if needed`. Names are planning seams, not assigned files/revisions.

Owner: Backend migration owner; Review catalog/privilege review; Quality preservation and both-dialect validation; lead reserves revision.

</details>

The [concrete worker failure entry design](WORKER_FAILURE_ENTRY_DESIGN.md) retains its accepted M122/e7a70bb9/52a9800d provenance. Accepted F1 main89 delivery and source handoff 22608a0f now assign Backend the reserved F2 implementation; Planning synchronizes records and Review independently checks source/evidence.

Before any checkpoint code, require accepted whole AR-010-A including P2 and AR-005-C, complete independently reviewed entry design, lead migration owner/revision decision against the accepted predecessor, this adopted reforecast and source-bound native validation plan. No precursor is an early-entry exception. Each F2–F5 requires the preceding accepted merge. Backend owns implementation/migration, Quality independent behavior/native evidence, Review independent source/security and the lead revision/integration. F1 delivery is accepted; F2 is assigned under its source-bound handoff, while F3-F5 remain separately gated.

Retain accepted C04, AR-005-C guard/recovery, AR-008-B bounded Operation/HTTP and AR-011-B safe-vocabulary producer reviews. Pin the accepted whole AR-010-A source/profile, PR/main receipts and installed artifact before code. Review the exact query/frame/capability and migration/privilege/restore plans; the lead's reserved later-F2 identity is recorded below, with no F1 migration code. Actual producer, race, preservation and native capacity proofs are earned during implementation and required for acceptance, not before unimplemented code.

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

Assigned F1 source boundary: `agent_rewind/migrations/schema.py`, `agent_rewind/migrations/ledger_reader_catalog.py`, `tests/test_ledger_catalog_budget.py`, `focused existing catalog fixtures/controls only if needed`. Only these F1 seams and narrowly required existing controls are assigned; no successor schema/revision implementation.

Owner: Backend; lead owns scope; Quality raw/whole-path oracles; Review SQL/security.

All common pre-code prerequisites. Review accepts exact query/projection/sentinel and old-observer equivalence design. Lead owns this prerequisite as P1/F1 rather than an early AR-010-A exception.

The CHECK correspondence repair is inherited predecessor work. Preserve its native declaration map alongside selected names in the fused observer and both general/bounded reflected comparisons; the [entry interface reconciliation](WORKER_FAILURE_ENTRY_DESIGN.md#f1-interface-reconciliation-after-check-correspondence--2026-10-29) specifies the return shape and retained-slice accounting. Do not duplicate standalone DDL queries to recover a discarded map.

Carry forward the 48 CHECK regression IDs and seven earlier clause-policy regressions. Retain both real jobs rebuilds, positive complete inspection, fresh general/bounded observers, unchanged provenance and refusal/rollback/whole-state assertions; retain the six parser families, digit-bearing ar7 identifier, FOREIGN-name reset and four fresh/legacy ar6/ar7 equality cases. Adapt only the earlier audit regression's passive per-table-query witness to actual fused SQL; one fused SQL trace does not prove fetched row order. Independent general SQL remains a structural oracle; shared policy/parser code is not an independent semantic oracle.

Actual ar6/ar7 fresh/legacy raw native-observer equality; missing/extra/duplicate table, invalid options/type/null/oversize and forbidden-clause negatives; preserved independent catalog mismatch detection. Measure complete immutable-history and complete principal/key claim/reserve paths under same Work, both supported SQLite interpreters/native versions, recording every target/control/row/bind charge, cleanup, time and VM. Existing PostgreSQL old-profile controls establish unchanged branch behavior; no new PG batching.

Exit: All named positive/negative equivalence cases pass without changed gates; supported complete existing requests fit unchanged limits and measured query deltas reconcile to trace. Record actual remaining capacity. No minimum guessed saving or automatic successor-fit credit.

Allocation basis: Two profile families, literal token semantics, fresh bounded transfer and complete-path accounting require separate source/equivalence and native-measurement work; reuses existing fixtures, not a new framework.

### F2 — Dormant successor schema, profile and migration foundation

Frozen module boundaries and native acceptance vectors are in the [F2 implementation allocation](WORKER_FAILURE_ENTRY_DESIGN.md#f2-implementation-allocation--2026-10-30): failure_schema, failure_catalog, failure_transaction, failure_service, the reserved thin migration and two literal dialect profiles. This allocates the existing F2 scope; accepted F1 delivery and handoff 22608a0f now permit its implementation, without F2 acceptance.

Owner: Backend implements the owned transaction, then service/migration and focused native checks in SECONDARY; Quality owns independent transaction oracles in PRIMARY; Review independently checks source/privilege/preservation evidence; the lead retains revision/integration ownership. F2 is In progress after accepted F1, with null acceptance.

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

## P2 admitted-startup audit — 2026-10-30

The [dispatch integration audit](WORKER_DISPATCH.md#remaining-admitted-startup-integration--2026-10-30) assigns admission/account provenance, installed execution composition, generation-fenced recording/publication and unpatched startup to explicit downstream work. Direct account insertion does not satisfy existing manifest reconciliation. Freeze that representation and PR boundaries, then reforecast P2 and aggregate scheduling before implementation assignment. The retained two-day P2 estimate and derived aggregate totals are not a complete startup forecast. F2 keeps its one-relation scope and 3 [2–4.5] allocation; F2–F5 entry gates and accepted component statuses are unchanged.

## Capacity and reforecast boundaries

### Observed repaired-predecessor baseline — 2026-10-29

At [source `0be52817`](https://github.com/spei04/agent-rewind/commit/0be5281750b494729d2aa6e8c64e13bf50f1042b), one bounded synthetic service-key claim/reserve sample per native runtime was independently accepted:

| Python | SQLite | Claim: total Work units | Reserve: total Work units |
| --- | --- | ---: | ---: |
| 3.11 | 3.53.1 | 488 | 504 |
| 3.12 | 3.45.1 | 488 | 504 |

These are original cumulative post-cleanup counters; an ordinary/control/cleanup decomposition was not collected. Both calls acknowledged their commits, preserved all unrelated typed state, and passed exact claim/reservation delta and release checks. The source and owned environments stayed unchanged. Each row is one sample of the current predecessor, with its own native build. F1, the successor schema and broader capacity acceptance still require their planned measurements under unchanged limits. Historical 502/470 arithmetic remains separate from these observations.

### CHECK-repaired predecessor samples — 2026-10-29

The separately reviewed samples on [repair `80f388bd`](https://github.com/spei04/agent-rewind/commit/80f388bd4ed69d1f1dd21ea16144c653a3720e4d) again observed 488 claim / 504 reserve Work units, cumulatively after cleanup, once on each supported interpreter with its own native build. Exact whole-state deltas, transaction outcomes and release were checked. These finite samples do not supply an ordinary/control/cleanup decomposition, reliability or remaining-capacity claim, measured fusion savings, or F1/successor fit. Keep the earlier samples and static estimates above distinct; F1 still needs complete principal/service-key measurements on its own source under unchanged limits.

The retained owner reservation measured 492 ordinary / 494 total Work units. Key-route 502 and hypothetical fused 470 are static arithmetic, not measured fit, savings, latency, VM or memory proof. F1 targets only existing ar6/ar7 SQLite observation, leaving the independent schema.catalog per-table observer and PostgreSQL path intact. Preserve every table-specific supported-clause restriction, exact membership/multiplicity/options, null/invalid/oversize refusal, <=65536 bytes per DDL and <=1310720 cumulative ar7 transfer. No hidden out-of-Work query, stale/global cache or budget relaxation is allowed.

Reforecast at measured F1 capacity, observed F2 catalog/rollback and before F5 recovery. If exact equivalence or complete successor fit fails under existing limits, stop subsequent assignment and refine the design; do not turn a conservative refusal or static calculation into successful capacity evidence. This plan adds no paid/provider/native execution authority, acquisition/held-out work, resources, activation, new external approval gate or scope outside #97.

## Planning arithmetic and history

The adopted change adds ten base/fifteen upper days and four PRs: 155 aggregates, 171 planned PRs, 569 outer edges, 53 parents, 30 gates and 20 contracts. Parent AR-010 is 20 days/10 PRs; M1 is 75.5 and BE 110.5. Total base is 482, upper 814.6 and alternative 25% allowance 602.5; the unchanged effort path is 183.5 days (52.4 hypothetical workweeks at 3.5 delivery days/week). No task/package status, acceptance or external gate changes. Earlier 167 PRs / 472 base / 799.6 upper / 173.5 path and two-day P1 figures remain dated history, not the current forecast.
