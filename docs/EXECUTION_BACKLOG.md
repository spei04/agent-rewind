# Agent Rewind — execution backlog

**Current delivery checkpoint — 2026-10-23:** HTTP P2/AR-008 remain Verified at cefd222; ledger F1/F2 remain accepted at 2e0eeeab/e8cba52. RC2a has four independently reviewed process-death cases on each of SQLite and PostgreSQL; native RC1’s earlier 25-case result remains separate. Two actual SQLite identical-command cases at f4ba97c9 now pass independent review; PostgreSQL concurrency remains open. The ordinary native capacity attempt at eb2cbc4 passes all four seeded-reader cases under the unchanged two-second deadline. The 4,096-account case took 1.976373s, leaving about 24ms in this one run; repeatability and broader performance remain unproved. F3/P1/#108, aggregate #107 and parent #10 remain **In progress** with null acceptance; P2/#109 remains **Not started**. [Current evidence and remaining gates](delivery/LEDGER_EXECUTION_PLAN.md#f3-sqlite-competing-command-checkpoint--2026-10-23). Totals remain **151 tasks / 161 planned PRs / 544 outer edges; 30 Verified / 1 In progress / 120 Not started tasks; 9 Verified / 1 In progress / 5 Not started delivery packages**. Customer, production and spending gates are unchanged.

**Revision:** 2026-10-23 · **Owner:** spei04 · **Status:** Approved for staged execution; task-specific gates remain applicable.

This is the assignable execution companion to [the roadmap](PLAN.md). It covers 52 work packages as 151 aggregate tasks and 161 planned delivery PRs. No application implementation, production provisioning or paid inference was started in preparing this packet. E0 is satisfied by explicit project-owner approval on 2026-10-19. Initial assignments and subsequent reviews are tracked in [ASSIGNMENTS.md](ASSIGNMENTS.md). Task cards and the machine-readable ledger record current status. Existing product code and historical test evidence are the starting point, not completion evidence for these tasks.

The [machine-readable backlog](../contracts/proposals/execution-backlog.json) records matching fields, contract producers, gates, conditional schedules and dependency audit. Run `python scripts/check_execution_backlog.py` and `python -m pytest -q -p no:cacheprovider tests/test_execution_backlog.py` to check drift. Maintain roadmap, cards, ledger and affected issues together. IDs are permanent; nested packages carry their own accepted merge/review evidence, inherit all aggregate prerequisites and do not add aggregate tasks or duplicate effort. Sequential successors require accepted merged predecessors; aggregate verification requires every package and the full scoped matrix. Optional implementation_prs refine one package into independently reviewed PRs without changing its effort, aggregate identity or acceptance scope. Their checkpoint evidence is separate from package acceptance; a local validator checks consistency of references, not actual GitHub or artifact authenticity. Independent delivery review must verify the protected-main/candidate evidence. AR-007-C, AR-008-A, AR-006-B and AR-008-B are Verified for their recorded internal scopes; their dated delivery plans retain component and failed-attempt evidence. AR-008-B/P2 #95 and aggregate #93 are Verified after reviewed source 065df8c89da384d6e502cf0c15bf174e380c53c7, protected merge cefd222230c800eb2e90c49a3b3c411b394d0393, matching PR/main runs 39683408934/39686498691 (attempt 1) and verified candidate 12387716715. P1 #94 retains accepted merge 03a8e074b51dca7c03d69295e0c18ca0f22dc1da and candidate 12355648523. Parent #8 is Verified/closed. AR-010-A/P1 #108, aggregate #107 and parent #10 remain In progress with null P1 acceptance. P1 entry policy 51af77dc and the HTTP prerequisite are accepted. F1 dormant foundation is Merged; checkpoint accepted after reviewed source c6f32cdd, protected merge 2e0eeeab, matching PR/main attempts 39729061054/39733331352 and verified candidate 12407151544. F2 complete persisted reader is Merged; checkpoint accepted after reviewed source ac3b0a31, protected merge e8cba52, matching PR/main attempts 39780954252/39786131008 and verified candidate 12431486551 with 133 exact runtime members. Failed main attempt 39773689705/1 and the SSH-interrupted first candidate invocation remain separate history. The lead explicitly started F3 on 2026-10-22: independent QE owns the shared-check kernel then compatibility adapter in secondary; platform/security owns the guarded writer/service and finalization/recovery in primary after progress release and reviewed kernel composition. Planning independently reviews integration; the lead owns policy and delivery. Writer and compatibility component evidence does not establish full F3, two-second adapter or joint capacity acceptance. F3 remains In progress with null source/merge/review acceptance. P2 #109 remains Not started/null acceptance behind accepted full P1 and its own reservation/fence entry review. F1/F2/F3 retain the unchanged P1 effort and acceptance scope. Provisioning, recovery and full P1 delivery remain unaccepted. AR-010-B and AR-011-C retain their sequential packages and original aggregate dependencies; AR-006-C, AR-011-C and AR-012-B still wait for the accepted worker aggregate. A future contract is a producer deliverable, not an implemented interface. Default adapters, customer admission, worker integration, full M1/G1 acceptance and external funding/data/production gates remain unavailable or open. Earlier dated failures and component evidence remain historical, not current status.

## Approval boundary and readiness

The instruction “Do not start implementation until I approve the execution backlog” is enforced by **E0**. Day 1 means the first staffed working day after that approval. E0 authorizes only its recorded scope; it does not satisfy architecture, funding, data rights, cloud access, customer, assessor or release gates. M0 and explicitly marked fixture/design preparation can proceed after E0; runtime M1 implementation also requires G0. Later tasks become assignable only when their exact prerequisites and contract-producer reviews pass. No task is scheduled on the assumption that an unavailable credential, future schema or customer approval already exists.

Execution approval is recorded; [G0_DECISION.md](delivery/G0_DECISION.md) now accepts the reviewed M1 migration-first development/test scope under that existing authority. Keep later milestone implementation and external spending tied to their recorded entry gates. This avoids repeatedly revisiting accepted one-organization/gVisor architecture while preserving decisions that genuinely remain open.

## Planning review and corrections

Reviewed PLAN, README and the current-release architecture, deployment, security, research, extension and validation documents; the M1 OpenAPI/logical schema/24-case acceptance proposal; and all 12 existing planning issues. Current-release documents were treated as evidence of present behavior, not promises of future capabilities.

| ID | Finding | Correction |
| --- | --- | --- |
| REV-01 | Five/ten-day packages had generic a/b splits with no assignable PR boundary. | 151 specific tasks, 0.5–7 engineering days each; route/listing/observability/worker-failure/ledger aggregates have two and admission three sequential delivery PRs, with scope, exclusions, contracts, tests, review and acceptance. Parent IDs retained for traceability. |
| REV-02 | Real storage/KMS/runtime verification depended on IaC scheduled after runtime, creating a coarse milestone loop. | AR-033-A/B are early M4 foundation tasks after G0/ENV0; AR-033-C/D integrate and independently reinstall later. Task graph, not package-level all-to-all edges, governs starts. |
| REV-03 | Reference cloud uses GCS but current artifact implementation only provides local/S3 paths. | AR-016-C explicitly implements native GCS and real-store conformance. No assumption that S3 support proves GCS compatibility. |
| REV-04 | 42–50 week GA and 28–34 week pilot forecasts were derived from unlevelled package estimates and unconfirmed staff. | Retire dated windows. 464 base engineering days; 176.5-day effort-only longest path excludes role contention and external waits. Reforecast after Day 10 and each gate using actual throughput; no committed launch date. |
| REV-05 | Uniform effort estimates concealed research, independent review and customer integration uncertainty. | Each task has confidence/range. 25% portfolio reserve is separate; audit fixes, procurement gaps, customer remediation and staffing/vendor waits remain explicitly unestimated gates. |
| REV-06 | Five M1 operations cannot support all branch, study, admin, export and SDK consumers. | Contract producer PRs AR-027-A/029-A/032-A/034-A precede their services/consumers; runtime consumers cannot start on an absent future schema. |
| REV-07 | Logical artifact and idempotency scope references lacked explicit matching composite unique/FK constraints. | Tighten m1.data-model.json artifact/project/owner and operation/principal/kind constraints; add corresponding scope-negative assertions to existing planned acceptance cases. |
| REV-08 | Pilot adoption metric requested three partners while onboarding scope funded two. | Use two partners weekly for four weeks, both adopting a resulting regression or policy fix; any third partner is an expansion. Sample shortfall requires honest gate review. |
| REV-09 | Four-week pilot and 30-day launch review were mixed with engineering days. | P28 and D30 are minimum elapsed-time gates after both onboarding measurement and accepted rollout respectively; approval/wait never auto-completes from passage of time. |
| REV-10 | The $200 historical validation cap was not a budget for a statistically powered natural-failure study or recurring production infrastructure. | PAID0 reconciles the existing authorization; STUDYFUNDS0, ENV0 and SCALEFUNDS0 require concrete funded scopes. No spending occurred in backlog preparation. |
| REV-11 | Aggregate six-engineer capacity hid heavy verification and platform ownership. | Role rollups expose QE 112.5 days and PL 90 days; two-week allocation stays <=0.5 delivery day/role/day. Independent reviewers and support coverage are external capacity dependencies. |
| REV-12 | A ten-day security package implied arbitrary unknown remediation could be scheduled and completed in advance. | AR-044 splits scope/triage/retest. SECFIX0 requires finding-specific fix PRs estimated after the assessment; prohibited blockers cannot be risk-accepted away. |
| REV-13 | Planning artifacts, existing tests and live validation risked being read as enterprise implementation evidence. | Internal M0 specifications and development G0 are reviewed; migration, ownership, readiness and CI have scoped evidence. All 24 M1 runtime cases remain planned, and production/customer evidence remains pending. Historical tests do not close future readiness gates. |
| REV-14 | M1 org/project/job caps do not by themselves cap a fan-out study spanning many child jobs. | AR-020-A/B explicitly introduce study-scoped ledger accounts and project/study/call closure; AR-022-A tests atomic study-wide caps under parallel child dispatch. |
| REV-15 | Approved research design could be bypassed by future experiment/report producers if kept only in prose. | RA-01-A/B and C20/C21 are internally verified; AR-020-A/AR-024-A retain their reviewed design/owner gate and original runtime prerequisites. Deferred scopes remain separately gated. |
| REV-16 | C04 required stale-projection repair with restricted audit, but no independently estimated implementation card owned it. | AR-006-A owns initial projection/rules; AR-006-B conservatively suppresses unsafe reads; AR-006-C implements bounded fenced repair/audit after AR-010-B, before AR-012-B verification. Add 2 base / 3.5 upper days; no new feature or spending authority. |
| REV-17 | AR-007-C promised absent future v1/replay/export routes and excluded the C04 session upgrade; two days omitted renderer and transaction integration. | Own existing routes and reusable authority in two sequential PRs: foundation 2 [2–3], integration 4 [4–7] after accepted merged foundation; aggregate 6 [6–10] BE days, medium-low confidence. Add verified AR-009-B and C04; retain future consumer obligations without reverse dependencies, with full CT-M1-007/008/009 gates still open. |
| REV-18 | Admission identity/configuration, migration and recovery were compressed into two days; five HTTP operations duplicated list/detail ownership. | AR-008-A has three accepted-merge-gated packages, 7 [7–11] days; AR-008-B owns submit/status/cancel through sequential adapter/HTTP packages of 4 [4–7] and 2 [2–3], total 6 [6–10] BE days; both wait for accepted AR-008-A. AR-006-B retains list/detail/cursors. No runtime starts before accepted AR-007-C; no reverse worker dependency or activation follows. |
| REV-19 | AR-011-C whole-task readiness exceeded its available producers. | Add AR-010-B before both sequential PRs, 4 [4–6] PL days; P1 actual HTTP/readiness foundation then P2 durable-origin/worker integration. Preserve the exact five metrics; no early package exception, schema duplication or reverse acceptance edge. |
| REV-20 | Two listing days assumed an existing cursor key and bounded customer projection reader; page size did not bound late-backfill scans. | Two sequential 2 [2–3] TL PRs, 4 [4–6] total, preserve AR-006-B prerequisites/C04. Review dedicated key, finite suppression, original receipts and measured native query ceilings before runtime; no schema/profile or worker-scope expansion. |
| REV-21 | Three HTTP days omitted a bounded Operation producer and operation-bound cancellation transaction. | Sequential P1 4 [4–7] and P2 2 [2–3] BE PRs, 6 [6–10] total, retain AR-008-B prerequisites/C04; B/lead accepted ownership entry 5bedede; helper, caller integration and activation require separate reviews. Freeze supported result/failure evidence and same-Connection effects before runtime; unsupported legacy errors refuse without an invented worker prerequisite. |
| REV-22 | Worker permit/cancel scope omitted the two legacy failure producers, authentic origin and explicit historical-marker ownership. | AR-010-B owns two sequential 2 [2–3] BE packages, total 4 [4–6], medium-low: complete bounded persistence/provenance/parser/consumer and operator-only marker, then live permits plus separately fenced completion/expiry. Freeze any needed migration decision before code; no reverse AR-008-B edge or AR-012-B implementation transfer. |

## Estimates, staffing and uncertainty

Engineering effort includes implementation or design, task tests, ordinary review/rework and documentation. Six logical role totals are demand estimates, not six funded human FTEs. Three contributor slots are active; no measured conversion from those slots to engineering days or a launch calendar is assumed. A hypothetical human role at 3.5 delivery days/week is shown only as a capacity lower bound. Ranges are planning bounds, not probabilities; RA-01 uses approved 2–3 and 2–4 day design ranges. The 25% integration reserve is alternative to summed upper ranges, not additive. External review/operations/funding waits and unestimated follow-up implementation remain excluded.

Base effort: **464 engineering days**. A 25% integration/rework allowance gives **580 days**; summing task upper planning bounds gives **784.6 days**. These are alternative views of uncertainty, not budgets to add together and not calendar commitments. Earlier 430-day/538-day totals are superseded. Research execution time and model charges, external assessment lead time/fees, unknown security fixes, customer-required gaps and ongoing support are not disguised inside a fixed ten-day task. An unknown required fix becomes a new ID/PR with scope and tests before its gate can close.

| Primary role | Base delivery days | Single-role capacity lower bound at 3.5 days/week |
| --- | ---: | ---: |
| TL | 75 | 21.4 weeks |
| FE | 23 | 6.6 weeks |
| RS | 66 | 18.9 weeks |
| PL | 90 | 25.7 weeks |
| BE | 97.5 | 27.9 weeks |
| QE | 112.5 | 32.1 weeks |

Roles: TL technical lead/backend, BE execution/backend, PL platform/SRE, FE frontend, RS research, QE quality. PM and SEC are shared reviewers/decision owners; actual names and independent statistical/security reviewers are not yet confirmed. Task effort includes ordinary verification and review work; the 30% availability reserve covers coordination, support and interruptions. Do not double-book primary tasks or assume the six roles are six available employees. QE ownership includes independent integration/rehearsal evidence, while every implementing engineer still writes their task tests.

QE and PL are material resource constraints. At the Day 10 review, redistribute suitable harness ownership to implementing engineers with independent QE review, or fund additional capacity; re-estimate before changing dates. Do not eliminate independent checks to make the schedule fit. No staffing, procurement or recurring infrastructure purchase is authorized by a planning estimate.

## Critical path, parallel tracks and contingencies

The task DAG has **544 edges**, **27 explicit gates**, no cycles and a **176.5-engineering-day longest effort path**. Under a hypothetical human role at 3.5 delivery days/week this is about 50.4 workweeks before contention and external waits; the three contributor slots have no validated conversion to that staffing scenario. It is a lower bound, not a launch forecast. Zero effort on an external gate means engineering effort is not estimated; it never means the gate is already satisfied or has zero lead time.

The computed effort path, including integration joins, is:

```text
E0 → AR-005-A → AR-012-A → AR-004-B → AR-004-C →
G0 → AR-005-B → AR-005-C → AR-011-B → AR-009-A →
AR-009-B → AR-007-C → AR-008-A → AR-008-B → AR-010-A → AR-010-B →
AR-011-C → AR-012-B → AR-014-A → AR-014-B → AR-017-A →
AR-023-A → AR-023-B → AR-023-C → AR-021-A → AR-021-B →
AR-021-C → AR-022-B → AR-022-C → AR-026-B → AR-026-C →
AR-029-B → AR-030-B → AR-031-B → AR-031-C → AR-034-D →
G4 → AR-035-B → AR-035-C → AR-036-A → AR-036-B →
AR-036-C → AR-038-A → AR-038-B → AR-038-C → AR-039-C →
G5 → AR-047-C → G6 → AR-048-A → AR-048-B →
AR-048-C → AR-049-A → AR-049-B → AR-049-C → AR-050-A →
AR-050-B → AR-050-C → G7
```

Calendar-critical competitors include ENV0/IDP0 provisioning, PARTNER0/DATA0 access, affordable sample design, independent assessor availability/remediation, P28 (28 days after both partner onboarding measurements begin), funded support and D30 (30 days after accepted rollout). The longest calendar path can change after any of these resolves.

| Parallel track | Earliest usable handoff | Work that may overlap | Join / constraint |
| --- | --- | --- | --- |
| Foundation | G0 and reviewed M1 proposal | Migration BE; reference config PL; independent QE review; readiness follows revision guard | Scoped repositories before run/object consumers; admission before budget integration |
| Reference environment | AR-033-A plus ENV0 | Early staging AR-033-B can overlap M1 contracts | One PL owns worker, storage, KMS and IaC; sequence by capacity |
| Execution / study design | G1 plus adapter and trial contract producers | Runtime conformance BE/PL; estimator RS; study schema BE | Same BE cannot own both at once; protocol review before consumers |
| Product | AR-027-A then service handoff | FE timeline/editor; RS synthetic ranking; TL SDK transport | Study/report SDK waits for AR-029-B; full UI cannot consume nonexistent endpoints |
| Enterprise hardening | Stable deployment plus task-specific dependencies | Supply-chain, capacity harness, identity/audit preparation can overlap M3–M5 | QE/PL capacity and assessor lead time; G6 joins all evidence after G5 |
| Pilot partners | G4, agreements and recovery gate | Both customers may supply data concurrently | TL/RS/QE integration work remains resource-serialized unless staffed separately |

Timebox uncertain capability/design tasks to their estimate (for example AR-031-A at three days). If the required result is unavailable, publish the negative finding, choose a supported narrower option or request a new scoped task; do not continue an unbounded spike. If corpus, power or grading validity fails, narrow the research claim and reapprove the evaluation plan. If load/DR/security fails, create measured fix PRs and rerun affected tests; gates remain open. Reserve the portfolio contingency for integration/rework; replenish or re-scope explicitly when exhausted.

## Milestones, exit gates and integration checkpoints

After the first two weeks, use dependency-ready milestone scheduling. The former week-number and quarterly launch windows are retired. At Day 10, G1, G2 and each subsequent gate, replace assumptions with completed-task throughput, role availability, actual customer/assessor dates and measured study costs. Do not publish a committed launch date until those constraints support a resource-leveled schedule.

| Milestone | Base effort | Scheduling after Day 10 | Explicit exit / integration checkpoint |
| --- | ---: | --- | --- |
| M0 | 8.5 days | Internal development freeze verified; external production conditions remain separate | [G0](#g0): M0 accepted; schemas and initial migration scope reviewed. |
| M1 | 65.5 days | Preparatory projection, existing-route scope, admission P1/P2/P3 and aggregate A Verified; listing P1/P2 and aggregate Verified; Operation adapter P1 Verified; HTTP route P2 Verified; repair AR-006-C remains gated | [G1](#g1): Historical identities, 24 behavioral cases, scope/lease/budget compatibility, required CI and installable main candidate evidence pass. |
| M2 | 69 days | Start each task after its foundation inputs; joins G1 plus early staging | [G2](#g2): Real gVisor isolation/restore/cleanup, cloud store/key rotation, fail-closed lease and accounted live smoke verified. |
| M3 | 81 days | Includes 4 base days of RA-01 design before C08/C09 producers; runtime follows its original prerequisites and G2 | [G3](#g3): Resumable distributed studies preserve frozen protocol, missingness and all call accounting; reports independently recompute. |
| M4 | 82 days | Early IaC after G0; UI/SDK after producer APIs; complete after G3 | [G4](#g4): Independent full browser/SDK workflow and fresh install pass with real IdP/GCS/KMS/gVisor and selected adapter. |
| M5 | 50 days | Only after G4 and funded customer/data/recovery gates; >=28-day measurement | [G5](#g5): Two partners, four calendar weeks, supported denominator/product metrics and natural-failure claim review accepted; no pilot blockers. |
| M6 | 78 days | Hardening overlaps stable M3–M5; readiness closure only after G5 | [G6](#g6): Forecast load/24h soak, zone/regional recovery, independent security retest, procurement, support and upgrade evidence pass with no prohibited blocker. |
| M7 | 30 days | Only after G6 and launch approval; >=30-day operating review | [G7](#g7): Controlled launch accepted and 30-day operating review complete; next scope separately approved. |

Completed RA checkpoints: accepted audit before protocol, followed by reviewed design and scope/capacity reconciliation. Historical initial checkpoints were Day 5 fixture/workflow review, Day 8 producer handoff and Day 10 freeze packet; ARCH0/G0 are now satisfied for development. Subsequent integration checkpoints: AR-005-C historical upgrade and runtime guard; AR-012-B all M1 cases; AR-019-C real runtime/store/key/fault evidence; AR-026-C distributed study integrity; AR-034-D independent browser/SDK flow; AR-035-C pre-ingestion recovery; AR-039-C two-partner pilot review; AR-047-C readiness audit; AR-048-C release decision; AR-049-C accepted rollout; AR-050-C 30-day closure. During active M1–M4 work, merge small reviewed PRs, run daily shared synthetic integration and twice-weekly cross-role reviews. A review meeting is not a passing gate.

## First two weeks — day-by-day

The owner-approved ledger amendment adds no calendar allocation. AR-010-A/P1 #108, aggregate #107 and parent #10 remain In progress with null P1 acceptance. P1 entry policy 51af77dc and the HTTP prerequisite are accepted. F1 dormant foundation is Merged; checkpoint accepted after reviewed source c6f32cdd, protected merge 2e0eeeab, matching PR/main attempts 39729061054/39733331352 and verified candidate 12407151544. F2 complete persisted reader remains In progress/null acceptance: source 432bcbc passed PR #113 checks and merged at 08234c, but protected-main attempt 39773689705/1 failed one Python 3.11 timed listing-continuation test; Python 3.12 passed and candidate delivery was skipped. Independent QE owns the isolated test-clock correction; planning/verification updates progress and reviews the correction and delivery evidence; the lead owns integration and fresh protected delivery. Platform/security completed the separate writer feasibility component and prepares reviewed F3 components only. F3 provisioning/opening/replay/recovery remains Not started. P2 #109 remains Not started/null acceptance behind accepted full P1 and its own reservation/fence entry review. F1/F2/F3 retain the unchanged P1 effort and acceptance scope. Full reader, provisioning, recovery and P1 delivery remain unaccepted. The historical rows and opening conditions below remain unchanged; two packages total 6 [6–10] BE effort days, not six staffed days.

The table preserves the conditional foundation scenario from the issue #51 decision: A authored AR-009-A (#53), C authored AR-007-B (#52), and B reviewed/reconciled. Both tasks are now Verified; this is historical allocation evidence, not the next fortnight's schedule. Three contributor slots are not six human FTEs. Each task had 2 base days; no research task is scheduled before its unavailable runtime producers.

| Conditional day | Primary delivery allocation | Required checkpoint |
| --- | --- | --- |
| Delivery Day 1 | Engineer C: [AR-007-B](#ar-007-b) (0.5d); Engineer A: [AR-009-A](#ar-009-a) (0.5d) | C implements scoped repositories; A implements object metadata/storage. B reviews interfaces and activation. |
| Delivery Day 2 | Engineer C: [AR-007-B](#ar-007-b) (0.5d); Engineer A: [AR-009-A](#ar-009-a) (0.5d) | C implements scoped repositories; A implements object metadata/storage. B reviews interfaces and activation. |
| Delivery Day 3 | Engineer C: [AR-007-B](#ar-007-b) (0.5d); Engineer A: [AR-009-A](#ar-009-a) (0.5d) | C implements scoped repositories; A implements object metadata/storage. B reviews interfaces and activation. |
| Delivery Day 4 | Engineer C: [AR-007-B](#ar-007-b) (0.5d); Engineer A: [AR-009-A](#ar-009-a) (0.5d) | C implements scoped repositories; A implements object metadata/storage. B reviews interfaces and activation. |
| Delivery Day 5 | Review, contingency and integration; no new base allocation | Independent review and matching hosted integration; no automatic dependent start. |
| Delivery Day 6 | Review, contingency and integration; no new base allocation | Reserve for measured rework and hosted verification; reforecast the ready M1 queue only after actual acceptance. |
| Delivery Day 7 | Review, contingency and integration; no new base allocation | Reserve for measured rework and hosted verification; reforecast the ready M1 queue only after actual acceptance. |
| Delivery Day 8 | Review, contingency and integration; no new base allocation | Reserve for measured rework and hosted verification; reforecast the ready M1 queue only after actual acceptance. |
| Delivery Day 9 | Review, contingency and integration; no new base allocation | Reserve for measured rework and hosted verification; reforecast the ready M1 queue only after actual acceptance. |
| Delivery Day 10 | Review, contingency and integration; no new base allocation | Reserve for measured rework and hosted verification; reforecast the ready M1 queue only after actual acceptance. |

The historical 2–3 day scenario ranges left days 6–7 for contingency; those rows do not allocate the current wave. Prior preparatory, admission and run-list/detail scopes remain Verified with their separate accepted evidence. AR-008-B/P2 #95 and aggregate #93 are Verified after reviewed source 065df8c89da384d6e502cf0c15bf174e380c53c7, protected merge cefd222230c800eb2e90c49a3b3c411b394d0393, matching PR/main runs 39683408934/39686498691 (attempt 1) and verified candidate 12387716715. P1 #94 retains accepted merge 03a8e074b51dca7c03d69295e0c18ca0f22dc1da and candidate 12355648523. Parent #8 is Verified/closed. AR-010-A/P1 #108, aggregate #107 and parent #10 remain In progress with null P1 acceptance. P1 entry policy 51af77dc and the HTTP prerequisite are accepted. F1 dormant foundation is Merged; checkpoint accepted after reviewed source c6f32cdd, protected merge 2e0eeeab, matching PR/main attempts 39729061054/39733331352 and verified candidate 12407151544. F2 complete persisted reader remains In progress/null acceptance: source 432bcbc passed PR #113 checks and merged at 08234c, but protected-main attempt 39773689705/1 failed one Python 3.11 timed listing-continuation test; Python 3.12 passed and candidate delivery was skipped. Independent QE owns the isolated test-clock correction; planning/verification updates progress and reviews the correction and delivery evidence; the lead owns integration and fresh protected delivery. Platform/security completed the separate writer feasibility component and prepares reviewed F3 components only. F3 provisioning/opening/replay/recovery remains Not started. P2 #109 remains Not started/null acceptance behind accepted full P1 and its own reservation/fence entry review. F1/F2/F3 retain the unchanged P1 effort and acceptance scope. Full reader, provisioning, recovery and P1 delivery remain unaccepted. Parent #6 and repair AR-006-C remain open; AR-011-C and AR-006-C wait for AR-010-B. Research implementation keeps its original runtime prerequisites, with M3 81 and M5 50 base days and external execution gates. This is not a new fortnight or launch calendar.

### Historical RA-01 conditional design schedule — 2026-10-20

This historical table was the **conditional RA-01 review schedule**, anchored to the first staffed working day after the owner's design approval and contributor availability. It is not a reset of the whole program or a promise of ten elapsed days. Three contributor slots remain: A authors the audit/protocol, C independently reviews research, B checks dependency/integration records. The two tasks total 4 base engineering days; ordinary review is included in task estimates, with unallocated capacity reserved for review and contingency. Contributor slots are not six human FTEs and have no measured conversion to human delivery days.

| Conditional day | Primary delivery allocation | Required checkpoint |
| --- | --- | --- |
| RA Day 1 | Engineer A: [RA-01-A](#ra-01-a) (0.5d) | Audit primary sources, available code/licenses and comparison feasibility; public inputs only. |
| RA Day 2 | Engineer A: [RA-01-A](#ra-01-a) (0.5d) | Audit primary sources, available code/licenses and comparison feasibility; public inputs only. |
| RA Day 3 | Engineer A: [RA-01-A](#ra-01-a) (0.5d) | Audit primary sources, available code/licenses and comparison feasibility; public inputs only. |
| RA Day 4 | Engineer A: [RA-01-A](#ra-01-a) (0.5d) | Audit primary sources, available code/licenses and comparison feasibility; public inputs only. |
| RA Day 5 | No new primary delivery allocation; review checkpoint | Independent C/lead audit acceptance required before RA-01-B; elapsed time is not acceptance. |
| RA Day 6 | Engineer A: [RA-01-B](#ra-01-b) (0.5d) | Protocol design consumes accepted C20; freeze no runtime or paid-study authority. |
| RA Day 7 | Engineer A: [RA-01-B](#ra-01-b) (0.5d) | Protocol design consumes accepted C20; freeze no runtime or paid-study authority. |
| RA Day 8 | Engineer A: [RA-01-B](#ra-01-b) (0.5d) | Protocol design consumes accepted C20; freeze no runtime or paid-study authority. |
| RA Day 9 | Engineer A: [RA-01-B](#ra-01-b) (0.5d) | Protocol design consumes accepted C20; freeze no runtime or paid-study authority. |
| RA Day 10 | No new primary delivery allocation; review checkpoint | Review C21 and owner decision list; reforecast M3/M5 and remaining M1 capacity before follow-up assignment. |

RA-01-A's upper estimate needs two additional half-day allocations; RA-01-B's upper estimate needs four more. Shift dependent days until the actual audit review passes; Day 5/10 are scenario acceptance conditions, never automatic approvals. The approved total range is 4–7 engineering days. Unknown reproduction/algorithm/evaluation work is a separately estimated follow-up, not spare capacity inside this design budget.

At that historical checkpoint AR-006-A, AR-007-B, AR-009-A and AR-011-C were the unscheduled approved M1 queue. Current assignments are recorded above; this table does not dispatch work or supersede later acceptance. Reforecast against the same three slots and measured throughput; deferred research adaptations and external execution waits remain separately gated.

### Historical initial conditional schedule — 2026-10-19

Working days, not dates; no weekend work assumed. Each allocation below is **0.5 engineering day** unless stated otherwise, leaving at least 0.5 day for peer review, decisions, maintenance and contingency. Roles absent from a day perform reviews or remain unallocated; do not invent blocked feature work to fill a calendar. PM/SEC participate in relevant decision reviews, with availability confirmed at E0. This is intentionally conservative while the contracts and staffing are uncertain.

| Week / day | Primary delivery allocation | Checkpoint and dependency condition |
| --- | --- | --- |
| W1 / Day 1 | TL: [AR-001-A](#ar-001-a) (0.5d); BE: [AR-004-A](#ar-004-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | E0 approval and staffing recorded before any scheduled task starts; TL/PM select interview evidence. Others review existing baseline. |
| W1 / Day 2 | TL: [AR-001-A](#ar-001-a) (0.5d); BE: [AR-004-A](#ar-004-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | Workflow and interface inventory PR review; no runtime feature work. |
| W1 / Day 3 | FE: [AR-001-B](#ar-001-b) (0.5d); RS: [AR-002-A](#ar-002-a) (0.5d); PL: [AR-003-A](#ar-003-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | Historical fixture manifest finishes; product/privacy/security review uses synthetic examples. |
| W1 / Day 4 | FE: [AR-001-B](#ar-001-b) (0.5d); RS: [AR-002-A](#ar-002-a) (0.5d); PL: [AR-003-A](#ar-003-a) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Review metric denominators, corpus rights shape and denied network paths. |
| W1 / Day 5 | RS: [AR-002-B](#ar-002-b) (0.5d); PL: [AR-003-B](#ar-003-b) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Week 1 integration: reconcile workflow/contract/fixture inventory; unresolved access or staffing gets owner and date. |
| W2 / Day 6 | RS: [AR-002-B](#ar-002-b) (0.5d); PL: [AR-003-B](#ar-003-b) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Freeze proposed split/evaluator assumptions; actual funding and customer rights remain pending conditions. |
| W2 / Day 7 | PL: [AR-011-A](#ar-011-a) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Cross-role contract review and negative fixture checks. No behavioral acceptance claimed. |
| W2 / Day 8 | PL: [AR-011-A](#ar-011-a) (0.5d) | Finish observability producer review; freeze waits for AR-011-A and AR-012-A. |
| W2 / Day 9 | TL: [AR-004-B](#ar-004-b) (0.5d) | Cross-role consumer review against completed producers; resolve compatibility and ownership. |
| W2 / Day 10 | TL: [AR-004-B](#ar-004-b) (0.5d) | Complete freeze proposal and capacity reforecast. ARCH0/AR-004-C/G0 follow reviewed output; no runtime work in this conditional fortnight. |

This original scenario is retained as history, not a record of staffed dates or the current three-contributor allocation. Its dependency ordering remains auditable in historical_schedules; it does not schedule new work.

## Interface and schema contract register

C04 links the [M1 API](../contracts/proposals/m1.openapi.json), [logical data model](../contracts/proposals/m1.data-model.json) and [24 planned acceptance cases](../contracts/proposals/m1.acceptance.json). Task test references such as M1-001 mean CT-M1-001 in that file. Other interfaces below are required outputs of their producer PRs. Producers include success, denial, invalid, timeout and uncertain fixtures plus consumer review. No dependent implementation can begin until those fixtures and compatibility rules are available.

| Contract | Producer / availability | Required API/schema/interface |
| --- | --- | --- |
| C01 — Workflow and metrics | [AR-001-A](#ar-001-a) | Two supported journeys, input/output examples, capture denominator, investigation timing, scope and pilot usefulness thresholds. |
| C02 — Corpus/evaluator protocol | [AR-002-A](#ar-002-a) | Rights/source/evaluator manifest; disjoint task families; failure taxonomy; immutable grader, split and private evidence policy. |
| C03 — Trust/deployment decisions | [AR-003-A](#ar-003-a) | One-organization topology; deny-by-default sandbox network; API/worker identities; spending, data and region decisions. |
| C04 — M1 API, schema and acceptance proposals | Reviewed at m1-review-2 / source 22c4376 | API, logical model and 24 planned cases reviewed; [G0 decision](delivery/G0_DECISION.md) records development scope. |
| C05 — Project ownership and roles | [AR-007-A](#ar-007-a) | Organization/projects/memberships/resource_scopes; project-parent closure; viewer/operator/maintainer/admin actions and deny matrix. |
| C06 — Adapter/checkpoint/runner | [AR-014-A](#ar-014-a) | Capability/version preflight; checkpoint/image/state/evaluator hashes; tool-boundary restore; actual versus observed effects; resource and lease bounds. |
| C07 — Encryption/secret lifecycle | [AR-016-A](#ar-016-a) | Versioned ciphertext envelope, KMS key IDs, legacy format reader, workload identity, rotation/retained-key and bounded decrypt errors. |
| C08 — Durable experiment and receipt | [AR-020-A](#ar-020-a) | Study/pair/trial/attempt IDs; protocol digest; frozen phases; fencing; missing/invalid/uncertain states; logical call/usage/price/receipt links. Extend budget accounts with study scope; every trial/job/provider call belongs to the same project/study and reserves against all applicable caps atomically. |
| C09 — Statistical report | [AR-024-A](#ar-024-a) | Estimand, estimator version, paired assignment, outcomes/missingness/intervals/invalidation; independent confirmation; fixed sample and null calibration. |
| C11 — History/branch/compare API | [AR-027-A](#ar-027-a) | Scoped paged event/file reads, idempotent branch create, bounded trajectory/file compare, provenance and unsupported checkpoint errors. |
| C12 — Study/report API | [AR-029-A](#ar-029-a) | Scoped study admission/status/cancel, paged trials, protocol-linked report/export and privileged audited reconciliation. |
| C13 — Export/retention/deletion | [AR-032-A](#ar-032-a) | Resource graph and reachability, holds, tombstones/journal, export manifests, grace/recheck GC and deletion-after-restore semantics. |
| C14 — Reference installation | [AR-033-A](#ar-033-a) | Versioned IaC inputs/outputs for GCP API, Cloud SQL, GCS, KMS/secrets, gVisor workers, IAM/network, labels, health and teardown. |
| C15 — Administrative identity | [AR-034-A](#ar-034-a) | Project/membership/key administration, IdP/group mapping, CSRF, revocation boundary, last-admin recovery and authorized role matrix. |
| C16 — Release/upgrade manifest | [AR-043-A](#ar-043-a) | Source and dependency pins, image signatures, SBOM/provenance, supported version matrix, protected publication and verified rollback. |
| C17 — Pilot/operating acceptance | [AR-035-A](#ar-035-a) | Per-customer permitted data/processors, residency, budgets, retention, operator/incident ownership and actual agreement/sign-off references. |
| C18 — Capacity workload/SLIs | [AR-040-A](#ar-040-a) | Plan Section 5 workload distributions and latency/error/resource bounds, queue fairness, five-minute burst, 24-hour soak and hardware/cost identity. |
| C19 — Regional recovery manifest | [AR-042-A](#ar-042-a) | Coherent DB/object/key/deletion backups; approved region; RPO/RTO, restore ordering, integrity and off-device evidence. |
| C20 — Prior-method audit design record | [RA-01-A](#ra-01-a); accepted in PR #49 | Versioned primary-source and implementation/license matrix, intervention/observation/verification semantics, cost coverage and reproducible/adaptable/incompatible/unavailable dispositions; bounded comparison recommendation. Design only. |
| C21 — Total-budget evaluation design amendment | [RA-01-B](#ra-01-b); internally accepted in PR #50 | Reviewed design for confirmed-intervention yield versus retry recovery, offline/online costs, selection/confirmation separation, holdout, missingness/multiplicity and scoped follow-up estimates. Input to C08/C09 producers, not their runtime schemas. |

Current availability: C01 workflows/metrics, C02 permission/provenance/protocol and C03 trust/capacity decision records are reviewed internally. C05 ownership/role contracts and AR-011-B bounded readiness are verified for their internal scope; customer admission remains disabled. C20 is the accepted prior-method audit; C21 protocol design is internally reviewed and available; RESEARCHSCOPE0 is satisfied only for the recorded engineering subset. C08/C09 remain unavailable until their original producers consume C21 and complete review. Real partner, statistical, deployment and funding gates remain separate. C04 is reviewed and G0 is satisfied for development/testing; accepted internal runtime deliveries retain their scoped evidence; full M1 acceptance remains gated. C14 version-1 offline configuration is reviewed and available, while actual ENV0 approval and provisioning remain gated. C07 offline envelope and credential design is available after accepted PR #102 and protected-main/candidate proof; format-2 runtime and live KMS/IAM remain gated. The machine-readable register records each current status.


## Gate register

E0 is **Satisfied** by the project owner’s explicit execution approval on 2026-10-19. ARCH0/G0 are satisfied for the recorded development scope; remaining gates stay open until their evidence is recorded. Integration gates join every listed required task; partial packages cannot close a milestone. External conditions require actual evidence from the responsible owner. Elapsed windows require both the minimum duration and valid measurements. No automated checker manufactures human approval.

<a id="e0"></a>

**E0 — external gate; owner: Product owner.** Prerequisites: None. Explicit approval of this execution backlog and which named staff/capacity can start. No implementation before this record.

<a id="arch0"></a>

**ARCH0 — external gate; owner: Product owner with TL/SEC/RS.** Prerequisites: [AR-004-B](#ar-004-b). Actual disposition of M0 architecture/contracts, workload, operating region, staffing, model/infra funding and first migration slice.

Disposition: [G0_DECISION.md](delivery/G0_DECISION.md), existing owner execution authority and exact-source internal reviews; production-specific external gates remain unsatisfied.

<a id="g0"></a>

**G0 — integration gate; owner: TL.** Prerequisites: [AR-001-B](#ar-001-b), [AR-002-B](#ar-002-b), [AR-003-B](#ar-003-b), [AR-004-C](#ar-004-c). M0 accepted; schemas and initial migration scope reviewed.

Disposition: [G0_DECISION.md](delivery/G0_DECISION.md), existing owner execution authority and exact-source internal reviews; production-specific external gates remain unsatisfied.

<a id="env0"></a>

**ENV0 — external gate; owner: Product owner/PL.** Prerequisites: [AR-003-B](#ar-003-b), [AR-033-A](#ar-033-a). Cloud project, approved region, recurring budget, IAM, network ownership and spending alerts available; development SSH access is insufficient.

<a id="idp0"></a>

**IDP0 — external gate; owner: Customer identity administrator.** Prerequisites: [AR-003-B](#ar-003-b), [AR-034-A](#ar-034-a). Actual test IdP tenant/client, group mappings and authorized disposable test users provisioned.

<a id="partner0"></a>

**PARTNER0 — external gate; owner: PM.** Prerequisites: [AR-001-B](#ar-001-b), [AR-002-A](#ar-002-a). Two willing design partners identified, one supported framework selected for capability review; no source ingestion permission implied.

<a id="data0"></a>

**DATA0 — external gate; owner: PM/RS/customer data owner.** Prerequisites: [AR-002-B](#ar-002-b), [PARTNER0](#partner0). Permitted versioned real task samples, allowed processors, evaluator access and private storage available.

<a id="paid0"></a>

**PAID0 — external gate; owner: PL/RS.** Prerequisites: [AR-003-B](#ar-003-b). Reconcile existing $200 authorization against all spend/reservations; record per-smoke cap, configured provider identity/version/rates and available credential. Additional spending needs explicit approval.

<a id="researchscope0"></a>

**RESEARCHSCOPE0 — external gate; owner: Product owner with TL/RS.** Prerequisite: [RA-01-B](#ra-01-b). **Satisfied for the nine selected engineering scopes only.** Explicit owner approval on 2026-10-20 is recorded in the [actual decision](research/OWNER_DECISION_2026-10-20.md), bound to immutable C21. No other gate is satisfied; current C02, statistical review, data/funding and production limits remain. The historical synthetic template is not approval evidence.

<a id="studyfunds0"></a>

**STUDYFUNDS0 — external gate; owner: Product owner/RS.** Prerequisites: [AR-026-A](#ar-026-a), [AR-038-A](#ar-038-a). Approve actual natural-failure study cost and feasible sample after power plan; existing $200 validation authorization does not fund an unlimited study.

<a id="pilot0"></a>

**PILOT0 — external gate; owner: PM/customer/SEC.** Prerequisites: [AR-035-A](#ar-035-a), [PARTNER0](#partner0), [DATA0](#data0). Both partner agreements, data/processor terms, installation funding, credentials, named operators and pilot caps accepted.

<a id="scalefunds0"></a>

**SCALEFUNDS0 — external gate; owner: Product owner/PL.** Prerequisites: [AR-003-B](#ar-003-b), [AR-040-A](#ar-040-a). Bounded scale/HA/DR test resources and cross-region data policy funded and authorized.

<a id="audit0"></a>

**AUDIT0 — external gate; owner: Independent assessor/SEC.** Prerequisites: [AR-044-A](#ar-044-a), [AR-034-C](#ar-034-c), [AR-043-C](#ar-043-c). Authorized independent assessment executed on fixed candidate and private report delivered; procurement and assessor lead time remain unknown.

<a id="secfix0"></a>

**SECFIX0 — external gate; owner: BE/SEC.** Prerequisites: [AR-044-B](#ar-044-b). Every release-blocking finding has its own estimated fix PR, regression test and independent review; fixes merged. Scope/effort unknown until report and excluded from base estimate.

<a id="procure0"></a>

**PROCURE0 — external gate; owner: Customer/PM/SEC.** Prerequisites: [AR-045-B](#ar-045-b). Required procurement/identity/data gaps resolved or explicitly accepted within policy; any required SCIM implementation separately planned and tested.

<a id="support0"></a>

**SUPPORT0 — external gate; owner: Product owner/PL.** Prerequisites: [AR-003-B](#ar-003-b). Named primary/secondary with funded coverage and agreed support hours; six engineering roles alone are not a 24/7 roster.

<a id="p28"></a>

**P28 — elapsed gate; owner: QE/PM.** Prerequisites: [AR-039-A](#ar-039-a). Both partners have at least 28 calendar days of valid pilot measurement; missing sample cannot be treated as success.

<a id="pilotfix0"></a>

**PILOTFIX0 — external gate; owner: TL/PM/QE.** Prerequisites: [AR-038-C](#ar-038-c), [AR-039-B](#ar-039-b). All pilot-blocking defects have reviewed fix/test evidence; any scope/threshold change explicitly approved. Unknown fixes receive new task IDs.

<a id="launch0"></a>

**LAUNCH0 — external gate; owner: Product owner/customer release authority.** Prerequisites: [AR-048-C](#ar-048-c). Actual customer launch authorization for named release, cohort, budget, region, rollback and support coverage.

<a id="d30"></a>

**D30 — elapsed gate; owner: QE/PM.** Prerequisites: [AR-049-C](#ar-049-c). At least 30 calendar days since accepted launch with valid operating evidence.

<a id="g1"></a>

**G1 — integration gate; owner: TL/QE.** Prerequisites: [AR-005-A](#ar-005-a), [AR-005-B](#ar-005-b), [AR-005-C](#ar-005-c), [AR-006-A](#ar-006-a), [AR-006-B](#ar-006-b), [AR-007-A](#ar-007-a), [AR-007-B](#ar-007-b), [AR-007-C](#ar-007-c), [AR-008-A](#ar-008-a), [AR-008-B](#ar-008-b), [AR-009-A](#ar-009-a), [AR-009-B](#ar-009-b), [AR-010-A](#ar-010-a), [AR-010-B](#ar-010-b), [AR-011-A](#ar-011-a), [AR-011-B](#ar-011-b), [AR-011-C](#ar-011-c), [AR-012-A](#ar-012-a), [AR-012-B](#ar-012-b), [G0](#g0), [AR-051-A](#ar-051-a). AR-006-C repair/audit is required transitively through AR-012-B. Historical identities intact; all 24 M1 behavioral cases, scope/lease/budget concurrency and compatibility pass. Required CI and installable main candidate evidence pass; production publication remains separately gated.

<a id="g2"></a>

**G2 — integration gate; owner: PL/QE/SEC.** Prerequisites: [AR-013-A](#ar-013-a), [AR-013-B](#ar-013-b), [AR-013-C](#ar-013-c), [AR-014-A](#ar-014-a), [AR-014-B](#ar-014-b), [AR-014-C](#ar-014-c), [AR-015-A](#ar-015-a), [AR-015-B](#ar-015-b), [AR-015-C](#ar-015-c), [AR-016-A](#ar-016-a), [AR-016-B](#ar-016-b), [AR-016-C](#ar-016-c), [AR-016-D](#ar-016-d), [AR-017-A](#ar-017-a), [AR-017-B](#ar-017-b), [AR-017-C](#ar-017-c), [AR-018-A](#ar-018-a), [AR-018-B](#ar-018-b), [AR-018-C](#ar-018-c), [AR-019-A](#ar-019-a), [AR-019-B](#ar-019-b), [AR-019-C](#ar-019-c), [G1](#g1), [AR-033-B](#ar-033-b). Real gVisor isolation/restore/cleanup, cloud store/key rotation, fail-closed lease and accounted live smoke verified.

<a id="g3"></a>

**G3 — integration gate; owner: RS/QE.** Prerequisites: [AR-020-A](#ar-020-a), [AR-020-B](#ar-020-b), [AR-020-C](#ar-020-c), [AR-021-A](#ar-021-a), [AR-021-B](#ar-021-b), [AR-021-C](#ar-021-c), [AR-022-A](#ar-022-a), [AR-022-B](#ar-022-b), [AR-022-C](#ar-022-c), [AR-023-A](#ar-023-a), [AR-023-B](#ar-023-b), [AR-023-C](#ar-023-c), [AR-024-A](#ar-024-a), [AR-024-B](#ar-024-b), [AR-024-C](#ar-024-c), [AR-025-A](#ar-025-a), [AR-025-B](#ar-025-b), [AR-025-C](#ar-025-c), [AR-026-A](#ar-026-a), [AR-026-B](#ar-026-b), [AR-026-C](#ar-026-c), [G2](#g2). Resumable distributed studies preserve frozen protocol, missingness and all call accounting; reports independently recompute.

<a id="g4"></a>

**G4 — integration gate; owner: TL/QE.** Prerequisites: [AR-027-A](#ar-027-a), [AR-027-B](#ar-027-b), [AR-027-C](#ar-027-c), [AR-028-A](#ar-028-a), [AR-028-B](#ar-028-b), [AR-028-C](#ar-028-c), [AR-029-A](#ar-029-a), [AR-029-B](#ar-029-b), [AR-029-C](#ar-029-c), [AR-030-A](#ar-030-a), [AR-030-B](#ar-030-b), [AR-030-C](#ar-030-c), [AR-031-A](#ar-031-a), [AR-031-B](#ar-031-b), [AR-031-C](#ar-031-c), [AR-032-A](#ar-032-a), [AR-032-B](#ar-032-b), [AR-032-C](#ar-032-c), [AR-033-A](#ar-033-a), [AR-033-B](#ar-033-b), [AR-033-C](#ar-033-c), [AR-033-D](#ar-033-d), [AR-034-A](#ar-034-a), [AR-034-B](#ar-034-b), [AR-034-C](#ar-034-c), [AR-034-D](#ar-034-d), [G3](#g3). Independent full browser/SDK workflow and fresh install pass with real IdP/GCS/KMS/gVisor and selected adapter.

<a id="g5"></a>

**G5 — integration gate; owner: PM/customer/RS.** Prerequisites: [AR-035-A](#ar-035-a), [AR-035-B](#ar-035-b), [AR-035-C](#ar-035-c), [AR-036-A](#ar-036-a), [AR-036-B](#ar-036-b), [AR-036-C](#ar-036-c), [AR-037-A](#ar-037-a), [AR-037-B](#ar-037-b), [AR-037-C](#ar-037-c), [AR-038-A](#ar-038-a), [AR-038-B](#ar-038-b), [AR-038-C](#ar-038-c), [AR-039-A](#ar-039-a), [AR-039-B](#ar-039-b), [AR-039-C](#ar-039-c), [G4](#g4), [P28](#p28). Two partners, four calendar weeks, supported denominator/product metrics and natural-failure claim review accepted; no pilot blockers.

<a id="g6"></a>

**G6 — integration gate; owner: TL/PL/QE/SEC/RS.** Prerequisites: [AR-040-A](#ar-040-a), [AR-040-B](#ar-040-b), [AR-040-C](#ar-040-c), [AR-041-A](#ar-041-a), [AR-041-B](#ar-041-b), [AR-041-C](#ar-041-c), [AR-042-A](#ar-042-a), [AR-042-B](#ar-042-b), [AR-042-C](#ar-042-c), [AR-043-A](#ar-043-a), [AR-043-B](#ar-043-b), [AR-043-C](#ar-043-c), [AR-044-A](#ar-044-a), [AR-044-B](#ar-044-b), [AR-044-C](#ar-044-c), [AR-045-A](#ar-045-a), [AR-045-B](#ar-045-b), [AR-045-C](#ar-045-c), [AR-046-A](#ar-046-a), [AR-046-B](#ar-046-b), [AR-046-C](#ar-046-c), [AR-047-A](#ar-047-a), [AR-047-B](#ar-047-b), [AR-047-C](#ar-047-c), [G5](#g5), [SECFIX0](#secfix0), [PROCURE0](#procure0), [SUPPORT0](#support0). Forecast load/24h soak, zone/regional recovery, independent security retest, procurement, support and upgrade evidence pass with no prohibited blocker.

<a id="g7"></a>

**G7 — integration gate; owner: Product owner/operators.** Prerequisites: [AR-048-A](#ar-048-a), [AR-048-B](#ar-048-b), [AR-048-C](#ar-048-c), [AR-049-A](#ar-049-a), [AR-049-B](#ar-049-b), [AR-049-C](#ar-049-c), [AR-050-A](#ar-050-a), [AR-050-B](#ar-050-b), [AR-050-C](#ar-050-c), [G6](#g6), [D30](#d30). Controlled launch accepted and 30-day operating review complete; next scope separately approved.

## Common task definition of done

Every task below has its own bounded scope and acceptance criteria, and uses this common DoD: required task tests pass on the named commit and supported environment; an independent reviewer records disposition; documentation, safe diagnostics/observability and compatibility/migration/recovery impact are updated or explicitly documented as inapplicable; evidence links include limitations; roadmap, task status, dependencies and affected issues agree. Code changes run configured lint/type/test checks. Decision tasks require real authorized sign-off and validation of the decision record; structural checks cannot substitute for human decisions. Keep source, secrets and customer evidence out of public Git; private evidence records source commit, owner, purpose, access and retention review. A failing mandatory criterion keeps the task open.

A task is one independently reviewable PR or evidence/decision-record PR unless explicit nested delivery packages define sequential reviewed PRs under the same aggregate effort. It may introduce a disabled path or a reviewed contract, but cannot merge a newly reachable unsafe partial implementation. Dependent PRs use the merged producer interface; parent packages are not giant implementation PRs. Automatic tests listed here are requirements, not assertions that those tests already exist or pass.

## Assignable task cards

<a id="ar-001"></a>

### AR-001 — Make supported investigations and their business value explicit

M0 / P0 · 2 PRs · 2 engineering days · Verified · [Tracking issue #1](https://github.com/spei04/agent-rewind/issues/1)

<a id="ar-001-a"></a>

#### AR-001-A — Supported workload and buyer workflow

- **Objective:** Make supported investigations and their business value explicit. This task delivers supported workload and buyer workflow.
- **Implementation scope / PR boundary:** Document two target workflows, tool-boundary replay guarantees, exclusions and customer interview questions.
- **Out of scope:** No additional language or external write tools.
- **Prerequisites:** [E0](#e0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C01; definitions and producer availability in the contract register.
- **Acceptance criteria:** Each workflow has input, failure, intervention and executable success examples reviewed with PM.
- **Required automated tests:** Validate required workflow fields and examples against current TaskSpec limits.
- **Security and reliability:** Exclude customer source and credentials from public examples.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Assigned contributor: Engineer A — workflow/contracts.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-001-b"></a>

#### AR-001-B — Usefulness metrics and interaction acceptance

- **Objective:** Make supported investigations and their business value explicit. This task delivers usefulness metrics and interaction acceptance.
- **Implementation scope / PR boundary:** Specify capture denominator, investigation timing, two-partner pilot target and accessible task flows.
- **Out of scope:** No application UI changes or claimed adoption.
- **Prerequisites:** [AR-001-A](#ar-001-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C01; definitions and producer availability in the contract register.
- **Acceptance criteria:** PM accepts 80% supported capture target, 20-investigation timing sample and two weekly pilot users' organizations.
- **Required automated tests:** Check metric formulas on complete, failed and abandoned investigation fixtures.
- **Security and reliability:** Measure all attempted investigations; no success-only denominator.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Assigned contributor: Engineer A — workflow/contracts.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-002"></a>

### AR-002 — Protect corpus rights and establish a credible natural-failure evaluation protocol

M0 / P0 · 2 PRs · 2 engineering days · Verified · [Tracking issue #2](https://github.com/spei04/agent-rewind/issues/2)

<a id="ar-002-a"></a>

#### AR-002-A — Corpus permission and provenance manifest

- **Objective:** Protect corpus rights and establish a credible natural-failure evaluation protocol. This task delivers corpus permission and provenance manifest.
- **Implementation scope / PR boundary:** Define private corpus manifest with rights, source revision, evaluator identity and allowed processors.
- **Out of scope:** No acquisition or paid model trials.
- **Prerequisites:** [AR-001-A](#ar-001-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02; definitions and producer availability in the contract register.
- **Acceptance criteria:** Manifest rejects missing permissions and records storage owner plus retention review date.
- **Required automated tests:** Schema cases for missing rights, duplicate task IDs and disallowed processor.
- **Security and reliability:** Never commit proprietary tasks; aggregate evidence only.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Assigned contributor: Engineer C — corpus/quality.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-002-b"></a>

#### AR-002-B — Natural failure and held-out split protocol

- **Objective:** Protect corpus rights and establish a credible natural-failure evaluation protocol. This task delivers natural failure and held-out split protocol.
- **Implementation scope / PR boundary:** Define failure taxonomy, task-level split, evaluator stability checks and effect-size feasibility worksheet.
- **Out of scope:** No claim that existing injected failure establishes generality.
- **Prerequisites:** [AR-002-A](#ar-002-a), [AR-001-B](#ar-001-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02; definitions and producer availability in the contract register.
- **Acceptance criteria:** Discovery and confirmation tasks are disjoint; sample-size assumptions and null-result decision are recorded.
- **Required automated tests:** Synthetic split leakage, unstable grader and insufficient-sample fixtures.
- **Security and reliability:** No screening on holdout; model changes invalidate affected comparison.
- **Effort / confidence:** 1 engineering days; planning range 1–2; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Assigned contributor: Engineer A — research protocol.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-003"></a>

### AR-003 — Bound deployment trust, operating responsibility and financial exposure

M0 / P0 · 2 PRs · 2 engineering days · Verified · [Tracking issue #3](https://github.com/spei04/agent-rewind/issues/3)

<a id="ar-003-a"></a>

#### AR-003-A — Trust boundary and deployment threat review

- **Objective:** Bound deployment trust, operating responsibility and financial exposure. This task delivers trust boundary and deployment threat review.
- **Implementation scope / PR boundary:** Map API, trusted worker, untrusted sandbox, IdP, DB, artifacts and model egress; retain one organization per installation.
- **Out of scope:** No cloud provisioning or security certification.
- **Prerequisites:** [AR-001-A](#ar-001-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C03; definitions and producer availability in the contract register.
- **Acceptance criteria:** SEC reviews assets, deny-by-default paths and gVisor worker privilege boundary.
- **Required automated tests:** Machine-check topology inventory and expected denied paths against configuration fixtures.
- **Security and reliability:** No customer DB connection; secrets remain outside sandbox.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Assigned contributor: Engineer B — platform/trust boundaries.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-003-b"></a>

#### AR-003-B — Capacity, ownership and funding decision record

- **Objective:** Bound deployment trust, operating responsibility and financial exposure. This task delivers capacity, ownership and funding decision record.
- **Implementation scope / PR boundary:** Estimate reference cloud resources using measured workload assumptions; request named staffing, region, IdP and operating funding.
- **Out of scope:** No purchases or guaranteed launch date.
- **Prerequisites:** [AR-003-A](#ar-003-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C03; definitions and producer availability in the contract register.
- **Acceptance criteria:** Separate one-time engineering, recurring infrastructure and paid study budgets; preserve existing model cap.
- **Required automated tests:** Check cost arithmetic, units and budget upper-bound examples.
- **Security and reliability:** No implied authority for recurring cloud or customer data use.
- **Effort / confidence:** 1 engineering days; planning range 1–2; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Assigned contributor: Engineer B — platform/capacity.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-004"></a>

### AR-004 — Resolve architecture and interface decisions before runtime changes

M0 / P0 · 3 PRs · 2.5 engineering days · Verified · [Tracking issue #4](https://github.com/spei04/agent-rewind/issues/4)

<a id="ar-004-a"></a>

#### AR-004-A — Baseline interface and compatibility inventory

- **Objective:** Resolve architecture and interface decisions before runtime changes. This task delivers baseline interface and compatibility inventory.
- **Implementation scope / PR boundary:** Map existing routes, SQL tables, event hashes, artifact formats and proposed M1 changes.
- **Out of scope:** No runtime change or contract activation.
- **Prerequisites:** [E0](#e0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Every current writer and reader has migration/compatibility disposition and baseline commit.
- **Required automated tests:** Validate proposed OpenAPI, internal references and logical schema field coverage.
- **Security and reliability:** Inspect fixtures without publishing private traces.
- **Effort / confidence:** 1 engineering days; planning range 0.8–1.2; high confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Assigned contributor: Engineer B — backend/interfaces.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-004-b"></a>

#### AR-004-B — Consumer review and M1 contract freeze proposal

- **Objective:** Resolve architecture and interface decisions before runtime changes. This task delivers consumer review and m1 contract freeze proposal.
- **Implementation scope / PR boundary:** Resolve API/schema/test disagreements, explicit composite scope constraints and deferred endpoint ownership.
- **Out of scope:** No implementation sign-off or invented reviewers.
- **Prerequisites:** [AR-002-B](#ar-002-b), [AR-003-B](#ar-003-b), [AR-004-A](#ar-004-a), [AR-005-A](#ar-005-a), [AR-011-A](#ar-011-a), [AR-012-A](#ar-012-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** BE, PL, FE, RS, QE and SEC review results recorded; incompatible changes have decision owner.
- **Required automated tests:** Run contract structure, dependency and historical-fixture manifest checks.
- **Security and reliability:** Approval evidence is required; silence is not acceptance.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; source, review and checks in [ASSIGNMENTS.md](ASSIGNMENTS.md) and [G0_DECISION.md](delivery/G0_DECISION.md).

<a id="ar-004-c"></a>

#### AR-004-C — Record G0 decision and approved first slice

- **Objective:** Resolve architecture and interface decisions before runtime changes. This task delivers record g0 decision and approved first slice.
- **Implementation scope / PR boundary:** Record product-owner disposition, named engineering capacity, approved scope/budgets and first migration slice.
- **Out of scope:** No code deployment or implicit spending approval.
- **Prerequisites:** [AR-004-B](#ar-004-b), [ARCH0](#arch0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Approval links exist or gate stays blocked; unresolved decisions have owners and next action.
- **Required automated tests:** Validate gate record requires approver, date, scope and referenced contract revision.
- **Security and reliability:** Never self-approve product or security decisions.
- **Effort / confidence:** 0.5 engineering days; planning range 0.4–0.6; high confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Assigned: project lead; independently reviewed by Engineer A.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; source, review and checks in [ASSIGNMENTS.md](ASSIGNMENTS.md) and [G0_DECISION.md](delivery/G0_DECISION.md).

<a id="ar-005"></a>

### AR-005 — Upgrade stored history safely without changing evidence identity

M1 / P0 · 3 PRs · 6 engineering days · Verified · [Tracking issue #5](https://github.com/spei04/agent-rewind/issues/5)

<a id="ar-005-a"></a>

#### AR-005-A — Historical migration fixtures and preservation manifest

- **Objective:** Upgrade stored history safely without changing evidence identity. This task delivers historical migration fixtures and preservation manifest.
- **Implementation scope / PR boundary:** Build synthetic legacy DB/object fixtures plus expected IDs, times, hashes and reservation totals from documented baseline.
- **Out of scope:** No migration implementation; pre-G0 preparation only.
- **Prerequisites:** [E0](#e0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Known, unknown, partially initialized and corrupt legacy shapes are independently identifiable.
- **Required automated tests:** Fixture integrity and checksum tests; no production credentials in dumps.
- **Security and reliability:** Public fixtures synthetic; private evidence remains owner-readable.
- **Effort / confidence:** 1.5 engineering days; planning range 1.2–1.8; high confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Assigned contributor: Engineer C — quality/migrations.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-005-b"></a>

#### AR-005-B — Explicit Alembic installation and adoption CLI

- **Objective:** Upgrade stored history safely without changing evidence identity. This task delivers explicit alembic installation and adoption cli.
- **Implementation scope / PR boundary:** Install linear Alembic baseline/adoption revisions with frozen DDL, exact dialect schema classifier, bounded migrator locks and real legacy-writer exclusion; persist fresh/legacy installation origin and explicit mapping/evidence intent. Preserve original rows, event/artifact identities and reservations. AR-007-A alone owns organization/project/membership/resource DDL and backfill. PostgreSQL adoption requires an explicit nonempty retired-writer-role inventory bound to intent; verify disabled login/superuser and inherited write paths, reject other/ambiguous sessions and indirect public routines. This corrects the legacy compose application-superuser assumption; operator inventory remains attested, not dishonest-admin proof.
- **Out of scope:** No online data rewrite, automatic downgrade or run projection.
- **Prerequisites:** [G0](#g0), [AR-005-A](#ar-005-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Empty install and known baseline upgrade preserve all manifest identities; unknown schema refuses safely.
- **Required automated tests:** M1-001 through M1-004: fresh/legacy/unknown, transactional interruption and concurrent migrators.
- **Security and reliability:** Migration credential only; lock/timeouts; backup before adoption.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Assigned contributor: Engineer C — migrations.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; [PR #35](https://github.com/spei04/agent-rewind/pull/35), merge 385e5ecf, independent exact-source review and [hosted run 39348158044](https://github.com/spei04/agent-rewind/actions/runs/39348158044) passed. 656 tests per Python version, 42 PostgreSQL cases, gVisor/security/package/CI gate. [Evidence and limits](delivery/MIGRATION_EVIDENCE_2026-10-20.md): prepared metadata only; runtime guards and ownership remain separate.

<a id="ar-005-c"></a>

#### AR-005-C — Runtime revision guard and recovery guide

- **Objective:** Upgrade stored history safely without changing evidence identity. This task delivers runtime revision guard and recovery guide.
- **Implementation scope / PR boundary:** Add read-only release-profile revision guards before API admission and worker claims; refuse unknown/partial/future or incomplete state without DDL, and document compatible application rollback versus required backup restore. Confirm all supported CLI initialization now uses AR-005-B versioned migrations.
- **Out of scope:** No HA rolling upgrade claim.
- **Prerequisites:** [AR-005-B](#ar-005-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** No runtime DDL; unsupported or incomplete revisions prevent admission and worker dispatch; supported inspection-reader compatibility and verified backup restoration are demonstrated, while customer-serving rollback refuses without an approved active release profile.
- **Required automated tests:** Least-privilege DB startup, future/multiple revisions, upgrade failure, inspection-only compatibility and actual PostgreSQL backup/restore refusal/recovery tests.
- **Security and reliability:** Fail closed when schema cannot be read; retain rollback evidence.
- **Effort / confidence:** 1.5 engineering days; planning range 1.5–2.2; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Assigned contributors: C (guard), A (recovery), B (independent review).
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; [PR #39](https://github.com/spei04/agent-rewind/pull/39), merge 0737c7b, exact reviewed 94dd9cb and [run 39350413566](https://github.com/spei04/agent-rewind/actions/runs/39350413566) passed 758 tests per Python version, 58 PostgreSQL cases and 3 gVisor tests. [Evidence and limits](delivery/GUARD_RECOVERY_EVIDENCE_2026-10-20.md). Customer admission remains disabled.

<a id="ar-006"></a>

### AR-006 — Make large run histories queryable through bounded authorized requests

M1 / P0 · 4 PRs across 3 aggregate tasks · 9 engineering days · In progress · [Tracking issue #6](https://github.com/spei04/agent-rewind/issues/6)

<a id="ar-006-a"></a>

#### AR-006-A — Scoped run projection and resumable backfill

- **Objective:** Make large run histories queryable through bounded authorized requests. This task delivers scoped run projection and resumable backfill.
- **Implementation scope / PR boundary:** Create run_index and bounded progress-marked backfill with parent scope closure and preserved event heads. Add the constant run resource discriminator and composite project/resource scope FK, immutable commit-ordered per-project sequence, frozen cohort/source/scope/evidence identities and resumable initial inserts. Reuse pure projection classification and expected-state verification rules for later repair. Compose the required same-Connection publication writer with AR-009-B; the unavailable live generation-fence adapter must refuse before storage.
- **Out of scope:** No branch or event API redesign, mutable stale/lost-job repair, restricted repair-audit integration, legacy artifact-ref adoption, generation schema, live worker activation or customer admission; AR-006-C owns repair after AR-010-B.
- **Prerequisites:** [AR-005-C](#ar-005-c), [AR-007-A](#ar-007-a), [AR-009-B](#ar-009-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register. Reviewed C04 development/testing scope and existing G0 apply. AR-009-B supplies the accepted preparatory publication coordinator; AR-010-A/B still own generation-aware live integration. The retained C04 repair requirement is explicitly assigned to AR-006-C, with AR-012-B integrated acceptance.
- **Acceptance criteria:** All supported cohort records map or fail with fixed diagnostics; retry resumes without duplicate rows, source/history edits or sequence reassignment. Recheck the frozen source, scope and exact prior prefix each batch; late or changed records require explicit new cohort preparation. Projection/root/ref writes commit or roll back together; current migration-only release never enables customer admission.
- **Required automated tests:** Interrupted batches and fresh-process resume; orphan/cross-project lineage and scope FKs; equal timestamps with independent exact-float rounding oracle; missing/corrupt/redacted/zero-event evidence; source/scope/evidence drift; PostgreSQL rollback, reversed completion, project concurrency, restore and actual publication composition; old-reader fail-closed compatibility; overlapping parent replacement/child publication, allocator corruption and actual process death before/after commit.
- **Security and reliability:** Unmapped or unverifiable records refuse without source repair or default cross-project exposure. Verify captured bytes outside SQL/write locks and recheck immutable source identities before commit; bound cohort, ancestry, retained metadata, aggregate bytes and queries. No owner-only substitute for the required generation/database-time fence. Acquire sorted affected project exclusion before any owning job/run locks, with sequence allocation only after current fence/source validation; matching replay refuses an allocator below its published sequence.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Assigned contributors: Engineer C — runtime, evidence/backfill/publication and CLI; Engineer B — schema, catalog and PostgreSQL recovery/concurrency tests; Engineer A and lead — independent review and integration.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Verified; [issue #71](https://github.com/spei04/agent-rewind/issues/71), [PR #72](https://github.com/spei04/agent-rewind/pull/72), reviewed source 46639c4; [hosted run 39497717028](https://github.com/spei04/agent-rewind/actions/runs/39497717028) and [scope/evidence](delivery/RUN_PROJECTION.md). AR-006-B is now Verified; AR-006-C and parent AR-006 remain open.

<a id="ar-006-b"></a>

#### AR-006-B — Stable cursor listing and run summaries

- **Objective:** Make large run histories queryable through bounded authorized requests. This task delivers stable cursor listing and run summaries.
- **Implementation scope / PR boundary:** Deliver two sequential accepted-merge-gated PRs: dedicated signed-cursor configuration and bounded scoped projection reader, then exactly the frozen v1 GET list/detail routes. Apply conservative current-job suppression and original source/projection/job receipt checks without repairs or artifact/event I/O; consume trusted named-project authority and reauthorize before return.
- **Out of scope:** No submit/status/cancel, rich legacy route changes, event/workspace/artifact reads, arbitrary filters, persistent repair/audit (AR-006-C), worker fence, schema/profile migration, customer activation or paid execution.
- **Prerequisites:** [AR-006-A](#ar-006-a), [AR-007-C](#ar-007-c), [AR-011-B](#ar-011-b).
- **Required contracts:** C04. C04 and direct prerequisites AR-006-A/AR-007-C/AR-011-B remain Verified for development scope. AR-006-B/P1 #87 remains Verified at accepted merge ed0d6c48b8db3533c1bb20a75df93d7efc89fc7c. P2 #88 and aggregate #86 are Verified after reviewed source 5ab8984b13622f3d9a9363f5fe303d71b8a80529 and accepted PR #91 merge cd021542981aadf5d8d0e2be280e2e19068b80c9. PR/main runs 39556621316/39558270300 passed 2620/2628 core tests on Python 3.11/3.12, with 11/3 expected skips and one warning each; actual PostgreSQL, installed-package/security checks, three gVisor cases and delivery gates passed. B independently audited source and both runs; lead verified candidate 12327092547 (547434 bytes), its exact four files and source/tree/parent/manifests/package/archive hashes. Issues #88/#86 are closed after lead read-back. Parent #6 and AR-006-C remain open. No reverse admission/worker dependency, customer activation or full CT-M1-007/008 acceptance is implied.
- **Acceptance criteria:** Fixed-corpus traversal has no duplicate or missing rows; initial commit-ordered watermark excludes later backfills, including old timestamps. Strict principal/project/limit/filter-bound cursors refuse tampering and expiry; actual indexed query work is bounded or safely refused. Complete success=false remains complete, while redacted or incompatible current-job evidence never becomes unsafe branchable output.
- **Required automated tests:** CT-M1-005/006: ties and exact UTC timestamps, fixed limits and cursor expiry/rotation/omitted-limit policy, reversed publication and late backfills; finite suppression matrix, malformed selected metadata before transfer, whole-request receipt and revocation races, zero blob/event I/O, actual PostgreSQL SELECT-only plans/work limits and native timeout cleanup; exact HTTP schemas/headers and migration-only guard.
- **Security and reliability:** Fresh identity and named-project visibility precede cursor/key details. LIST-only signing key is independent of artifact encryption; no secret/source/cursor in diagnostics. Set-oriented bounded reads retain original metadata and final SQL receipts; no N+1 default, automatic retry, partial page or abandoned timeout thread. Query ceilings are provisional until P1 fixture review; no global engine behavior changes.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium-low confidence.
- **Responsible role:** TL; A completed P2; lead owns delivery/integration, B source/security and C independent execution reviews are accepted.
- **Definition of done:** Both packages require independent review, matching checks and accepted merged-source evidence in order; aggregate completion requires the full scoped read/cursor/suppression and actual PostgreSQL matrix. Preserve historical bytes, migration-only admission and remaining CT-M1-007/008/G1 gates.
- **Progress:** Verified; [issue #86](https://github.com/spei04/agent-rewind/issues/86) and P2 #88 are closed. P1 #87 remains Verified; P2 accepted merge cd021542981aadf5d8d0e2be280e2e19068b80c9 has matching PR/main/candidate proof. See [accepted P2 evidence](delivery/RUN_LISTING_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). Parent #6 and AR-006-C remain open.

<a id="ar-006-b-p1"></a>

#### AR-006-B/P1 — Signed cursors and bounded scoped projection reads

- **Objective:** Implement the frozen cursor and SQL-only run-summary boundary without HTTP activation.
- **Implementation scope:** Implement dedicated optional cursor key configuration and strict versioned HMAC codec; bounded named-project projection/source/job reads, finite conservative suppression and original single-statement receipt rechecks. Review actual source-field mapping and measure proposed query ceilings at the first design checkpoint; reuse set-oriented scoped helpers and native cleanup.
- **Out of scope:** No HTTP wiring, legacy route changes, artifact/event I/O, source/projection writes, mutable repair/audit, schema/index migration, worker integration or customer-ready profile.
- **Prerequisites:** [AR-006-A](#ar-006-a), [AR-007-C](#ar-007-c), [AR-011-B](#ar-011-b).
- **Required contracts:** C04. C04 signed cursor and RunSummary; accepted AR-006-A projection/commit sequence, AR-007-C named authority and AR-011-B safe errors; reviewed RUN_LISTING_EXECUTION_PLAN.md key lifecycle, finite suppression and provisional query-work proof.
- **Acceptance criteria:** Cursor grammar and principal/project/filter/limit/watermark/expiry binding are exact; missing key affects only authorized list reads. Selected malformed metadata refuses before unsafe materialization; complete failure/redaction and unfenced partial states follow the reviewed finite table. Fixed-corpus traversal and bounded native SQL cleanup are demonstrated on SQLite and actual PostgreSQL.
- **Required automated tests:** Cursor size/signature/duplicate-member/expiry/rotation and omitted-limit vectors; exact timestamp ties, commit-order rollback and old-timestamp backfills; source/job/scope changes, malformed dynamic cells and max-page shared ancestry; deterministic SQLite VM limits plus actual PostgreSQL plans/timeouts, connection cleanup and zero storage/event reads.
- **Security and reliability:** No derived or automatically generated signing key; authority precedes cursor/config diagnostics. Preserve original receipts across reads and reauthorize at the end; no silent malformed-row omission or snapshot-based revocation claim. Proposed resource ceilings require fixture evidence and remain local to this adapter.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** TL; A authored P1, B/C independent reviews accepted; lead verified delivery.
- **Definition of done:** Independent interface/security review, meaningful SQLite and actual PostgreSQL evidence, matching hosted checks and accepted merge are required before P2; aggregate remains unverified.
- **Progress:** Verified; [issue #87](https://github.com/spei04/agent-rewind/issues/87) is closed after accepted [PR #89](https://github.com/spei04/agent-rewind/pull/89) merge ed0d6c48b8db3533c1bb20a75df93d7efc89fc7c, successful PR/main runs 39547572853/39548734170 and verified candidate 12323231309. Exact [accepted P1 evidence](delivery/RUN_LISTING_EXECUTION_PLAN.md#accepted-p1-delivery--2026-10-21); no customer activation.

<a id="ar-006-b-p2"></a>

#### AR-006-B/P2 — Frozen v1 run list and detail integration

- **Objective:** Expose exactly the frozen scoped v1 list and detail operations through the accepted read boundary.
- **Implementation scope:** Wire only the two frozen v1 GET list/detail routes to accepted P1 and fresh named-project authority; preserve exact RunSummary/errors/request-ID/no-store contracts, conservative current-job suppression and final response reauthorization. Add installed-package smoke and full route tests while retaining the unchanged migration-only guard.
- **Out of scope:** No submit/status/cancel ownership, rich legacy representation or audit changes, new profile/schema, artifact/event access, persistent repair, worker fences or production/customer activation.
- **Prerequisites:** [AR-006-B/P1](#ar-006-b-p1).
- **Required contracts:** C04. Accepted merged P1 and inherited C04; exact frozen GET list/detail OpenAPI and seven-field RunSummary, CT-M1-005/006 plus the scoped read contribution to CT-M1-007/008.
- **Acceptance criteria:** Both actual routes satisfy CT-M1-005/006 with authority-before-cursor errors, LIST-only key dependence, strict limits and continuation, fixed summary shape and fresh revocation refusal. Detail does not require the signing key; current migration-only schemas still refuse before customer sinks.
- **Required automated tests:** Actual list/detail response and 401/404/403/422/503 precedence, duplicate query parameters and omitted continuation limit; principal/project/key binding and revocation during reads, full finite suppression matrix, zero blob/event/repair access, real schema guard and isolated installed-package smoke.
- **Security and reliability:** No raw database or hash fallback, broad guard exception or customer-ready profile. Errors are fixed and bounded; no partial response after source/authority drift. Existing legacy run.read audit remains with its accepted route, not a new unscoped v1 side effect.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** TL; A completed implementation; lead owns delivery, with B source/security and C execution review accepted.
- **Definition of done:** Independent route/security review, matching hosted and protected-main evidence and accepted merge establish both packages and the complete list/detail matrix; aggregate completion does not close future replay, repair or G1 gates.
- **Progress:** Verified; [issue #88](https://github.com/spei04/agent-rewind/issues/88) is closed after [PR #91](https://github.com/spei04/agent-rewind/pull/91), accepted merge cd021542981aadf5d8d0e2be280e2e19068b80c9 and [matching PR/main/candidate evidence](delivery/RUN_LISTING_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). Only the frozen v1 run list/detail routes; unchanged migration-only profiles and no artifact/event/repair writes.

<a id="ar-006-c"></a>

#### AR-006-C — Fenced stale-projection reconciliation and restricted audit

- **Objective:** Persist conservative corrections to stale or lost-job projections with attributable, idempotent audit evidence while preserving immutable run history.
- **Implementation scope / PR boundary:** Implement bounded explicit reconciliation using AR-006-A classification and expected-state verification rules after AR-010-B supplies the live worker fence. Lock all affected projects in sorted order before the scoped run/job and applicable publication state; compare expected source/projection identity and current database-time lease, generation, cancellation and job state. Atomically persist a conservative status/branchability correction plus restricted additive audit with fixed reason, old/new status and source identity. Preserve published_seq, created_at, hashed source bodies, historical rows and the legacy audit table. One bounded repair-and-restricted-audit PR after the projection and live worker fence producers. If additive audit persistence needs a schema revision, include its narrow migration, literal profiles, compatibility and restore checks here; do not repurpose preserved legacy audit. No background scheduler or broad retention system.
- **Out of scope:** No provider execution/refund, scheduler, API redesign, fabricated completion, legacy audit/source rewrite, artifact adoption, new evidence capture or production/customer activation.
- **Prerequisites:** [AR-006-A](#ar-006-a), [AR-010-B](#ar-010-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register. Existing C04 stale-projection repair/audit requirement, now explicitly assigned under approved staged execution. AR-006-A provides pure rules; AR-010-B provides live fence integration. No new product feature, data access, spending or production authority.
- **Acceptance criteria:** Repeated reconciliation is idempotent with no duplicate audit; stale owners and mismatched source/scope/generation refuse without changes. Correction and audit commit together or neither does. An unverified partial/lost run cannot become complete or branchable. Existing immutable identities and all original fixture rows remain byte/value-identical; no customer activation follows this PR alone.
- **Required automated tests:** Real PostgreSQL concurrent takeover/cancel and repair races, unavailable database, process failure/rollback between repair and audit, duplicate invocation, scope/source drift and bounded batches; old-reader/profile refusal and restore; original-row preservation and unchanged sequence/timestamps.
- **Security and reliability:** Fresh scoped authorization and database-time live fence are required. Fail closed on ambiguity; emit only fixed safe diagnostics. Audit access is restricted and additive outside preserved legacy audit/source rows; no raw artifact, provider payload or secret in audit. Bound row/lock/query work and retain unresolved cases for explicit retry.
- **Effort / confidence:** 2 engineering days; planning range 2–3.5; medium confidence. Medium confidence: 2–3.5 days assumes reusable AR-006-A rules and accepted AR-010-B live fence. Exact additive audit persistence/compatibility work must be checked at entry; re-estimate a concrete gap rather than hide it in AR-012-B verification.
- **Responsible role:** BE; required reviewers: TL, QE, SEC. Named assignee pending staffing.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off. AR-012-B must independently exercise the integrated repair path before G1; this task does not certify that gate.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-007"></a>

### AR-007 — Prevent cross-project access through both legacy and new paths

M1 / P0 · 4 PRs across 3 aggregate tasks · 9.5 engineering days · Verified

<a id="ar-007-a"></a>

#### AR-007-A — Project ownership schema and role decision matrix

- **Objective:** Prevent cross-project access through both legacy and new paths. This task delivers project ownership schema and role decision matrix.
- **Implementation scope / PR boundary:** Implement organization/project/membership/resource scope tables and explicit legacy ownership backfill.
- **Out of scope:** No shared multi-tenant SaaS or SCIM.
- **Prerequisites:** [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C05; definitions and producer availability in the contract register.
- **Acceptance criteria:** Ownership is complete or second-project admission stays disabled; role/action matrix frozen.
- **Required automated tests:** Composite FK, ambiguous mapping, revoked membership and admin boundary tests.
- **Security and reliability:** Organization admin derived from identity; never request role fields.
- **Effort / confidence:** 1.5 engineering days; planning range 1.5–2.2; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Assigned contributor: Engineer C — ownership schema/backfill; Engineer B — independent review.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; [PR #43](https://github.com/spei04/agent-rewind/pull/43) and exact-source internal review/hosted validation accepted. [Evidence and limits](delivery/OWNERSHIP_READINESS_EVIDENCE_2026-10-20.md). Customer admission remains disabled; full M1 is not complete.

<a id="ar-007-b"></a>

#### AR-007-B — Central scoped resource repositories

- **Objective:** Prevent cross-project access through both legacy and new paths. This task delivers central scoped resource repositories.
- **Implementation scope / PR boundary:** Require project/principal context for runs, jobs, studies, keys and artifact resolution
- **Out of scope:** No route migration or new UI
- **Prerequisites:** [AR-007-A](#ar-007-a). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C05; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Foreign IDs are denied before decrypt/load; every repository lookup has explicit scope
- **Required automated tests:** Repository authorization matrix, forged lineage, same hash across projects
- **Security and reliability:** Default deny and uniform not-found responses for inaccessible resources
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Engineer C — scoped repositories; independent review assigned by lead
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Verified; [issue #52](https://github.com/spei04/agent-rewind/issues/52), entered after verified direct prerequisites.

<a id="ar-007-c"></a>

#### AR-007-C — Existing-route authorization and reusable project authority

- **Objective:** Prevent cross-project access in every existing route and supply the trusted authority boundary for later route producers.
- **Implementation scope / PR boundary:** Upgrade to issuer-bound v2 sessions; implement fresh explicit default/named-project authority with 401/404/403 distinctions; adapt every existing data route to scoped repository and verified published-graph/ref reads without raw-hash fallback; commit scoped cancellation and human-maintainer key issuance/revocation with fresh authority and audit atomically; wire work creation to a required unavailable admission adapter that refuses before readiness probes, storage or enqueue.
- **Out of scope:** No new v1/debugger/study/export routes, session infrastructure or IdP provisioning, historical artifact adoption, customer-ready schema profile, live publication, or actual work admission. The required C04 v2 session format upgrade is included; durable admission/replay/frozen config and worker integration remain with AR-008-A/B and AR-010-B.
- **Prerequisites:** [AR-007-B](#ar-007-b), [AR-011-B](#ar-011-b), [AR-009-B](#ar-009-b). E0/G0 and reviewed producer contracts apply; all direct inputs are Verified.
- **Required contracts:** C04, C05; [existing-route plan](delivery/EXISTING_ROUTE_AUTHORITY_PLAN.md) records the exact boundary and future consumers.
- **Acceptance criteria:** Exhaustive existing-route inventory has no unscoped data bypass; inaccessible/default-ambiguous resources return 404 and insufficient action rights in an accessible project return 403; v1 cookies are rejected; identity-only me/logout remain usable after project revocation without exposing project/resource IDs; revocation prevents protected return/mutation; cancel and key changes are atomic; unavailable admission refuses before readiness probes and causes no storage, artifact, secret, job or audit writes. CT-M1-007/009 current-route subsets alone cannot close the full cases; CT-M1-008 remains planned for durable replay producers.
- **Required automated tests:** Existing-route/alias matrix; v2 issuer collision and old-cookie refusal; missing/ambiguous default, named/cross-project and shared-object probes; CSRF/exact Origin; me/logout after revocation and DB failure; real PostgreSQL revocation-before-return and mutation races, cancel/key rollback and terminal cancellation; unavailable adapter fails before readiness probes, storage, enqueue and all writes/provider access; actual schema guard still denies customer routes.
- **Security and reliability:** Keep migration-only schema guard and customer/second-project activation gates; authorize before expensive I/O and reauthorize before return/commit; project-before-job lock hierarchy; token role intersects current membership and never grants key administration; no client-selected legacy scope, raw artifact fallback or raw enqueue.
- **Effort / confidence:** 6 engineering days; planning range 6–10; medium-low confidence. Reforecast after the first immutable identity/reader handoff at about 1.5–2 engineering days.
- **Responsible role:** BE; C owns Auth/routes/verified views/UI, B owns atomic scoped mutations; A independently reviews identity/read/security and B's mutation implementation; B independently reviews C's transaction consumption; C checks action-interface integration; lead integrates.
- **Definition of done:** P1 and P2 each have independent review, matching checks and a recorded accepted merge. Aggregate completion additionally requires the full P2 existing-route/transaction matrix. A independently reviews identity/read/security and B's mutation implementation; B independently reviews C's transaction consumption; C checks action-interface integration; lead integrates. Only partial coverage of CT-M1-007/009 is attributed here; CT-M1-008 and future-route gates remain planned. No customer activation or full M1 acceptance follows.
- **Progress:** Verified for preparatory existing-route scope in PR #79 at reviewed db5f992 / accepted merge e117aaa, matching PR/main checks and candidate 12318112434; [accepted P2 evidence](delivery/EXISTING_ROUTE_AUTHORITY_PLAN.md#accepted-p2-delivery--2026-10-21). CT-M1-007/009 remain partial overall and CT-M1-008/G1/customer gates remain open.

Two independently reviewable delivery PRs: AR-007-C/P1 foundation 2 [2–3] days, then AR-007-C/P2 full existing-route integration 4 [4–7] days after accepted merged P1. P1 does not wire Auth/session issuance, routes, UI, mutations or admission. Aggregate AR-007-C remains unverified until P2 and the full existing-route matrix are accepted.

<a id="ar-007-c-p1"></a>

#### AR-007-C/P1 — Identity, authority and verified-reader foundation

- **Objective:** Provide tested reusable identity/project decisions and one verified publication-read boundary before changing HTTP behavior.
- **Implementation scope:** Implement a strict issuer-bound v2 codec and identity helpers without wiring Auth/session issuance; fresh default/named project authority with typed 401/404/403 decisions; a shared journal-free verified reader that resolves a unique published root and performs a final compound ownership/ref/authority recheck. Delegate the existing RunPublisher.read consumer to that reader with preserved behavior.
- **Out of scope:** No Auth/session issuance wiring, existing-route/renderer/UI changes, key/cancel mutations, admission integration, new schema/profile, live writer or customer activation.
- **Prerequisites:** [AR-007-B](#ar-007-b), [AR-011-B](#ar-011-b), [AR-009-B](#ar-009-b).
- **Required contracts:** C04, C05. C04 issuer/principal/v2 codec and safe-error grammar; C05 role/scope/token intersection; accepted AR-009-B root/graph/ref fidelity, unique-root rejection and read reauthorization. The shared reader must not require a publication journal or live writer.
- **Acceptance criteria:** Helpers reject invalid/v1 session encodings without issuing cookies; default/named authority preserves inaccessible404 versus accessible-action403; reader rejects zero/ambiguous roots, foreign/nested refs and revoked authority before protected return; RunPublisher.read retains supported output/failure semantics and uses the shared reader; every existing auth/route/UI/mutation behavior remains unchanged.
- **Required automated tests:** Codec issuer collision/strict shape/version and safe-error tests; default/named role and service-key intersections; shared-object and unique-root denial; compound recheck after I/O and real PostgreSQL revocation races; existing publication-reader regressions prove delegation preserves semantics; package smoke includes reusable modules.
- **Security and reliability:** No journal needed for reads and no connection held across storage I/O; bound graph/ref operations; final compound recheck before return; preserve migration-only guard and unavailable live writer.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; C implements, A identity/security/read review, B transaction review, lead integration.
- **Definition of done:** Independent A identity/read and B transaction review accepted; matching hosted checks and behavior-preservation regressions pass; record accepted merged source and review evidence before P2 starts. This closes P1 only, not aggregate AR-007-C or any route-activation gate.
- **Progress:** Verified; [issue #76](https://github.com/spei04/agent-rewind/issues/76), [PR #78](https://github.com/spei04/agent-rewind/pull/78), accepted merge 51a2b1fefc40fc871426a47e3f3865fcbeef5bec. PR #78 source 923647d85ac8acc68f5334c2edcad40c6638d59a accepted by A for identity/read security and B for authority/SQL semantics; merge 51a2b1fefc40fc871426a47e3f3865fcbeef5bec has the identical reviewed tree. PR run 39528447469 and protected-main run 39529350057 passed 1789 tests on Python 3.11 and 1793 on Python 3.12, including all 46 new PostgreSQL cases; package/security and three gVisor tests passed. Candidate 12314568373 archive, exact four-file set, source/pinned manifests and package/SHA256SUMS hashes independently verified. Private release record is indexed outside disposable checkouts.

<a id="ar-007-c-p2"></a>

#### AR-007-C/P2 — Complete existing-route authority integration

- **Objective:** Replace all existing unscoped route consumers and mutations using the accepted foundation, preserving compatibility and fail-closed admission.
- **Implementation scope:** Wire accepted P1 into Auth/v2 cookie issuance, every existing route/renderer and explicit-role UI; implement exact me/logout/schema exceptions, atomic cancel/key/scope/membership/audit mutations and the required unavailable work adapter; finish exhaustive existing-route and real PostgreSQL race/rollback evidence.
- **Out of scope:** No new v1/debugger/study/export route, historical artifact adoption, active schema profile, live publication or actual admission/paid dispatch; later producers retain their C04 obligations.
- **Prerequisites:** [AR-007-C/P1](#ar-007-c-p1).
- **Required contracts:** C04, C05. Accepted merged P1 codec/typed authority/journal-free verified reader; C04 exact route exceptions, project-before-job transaction and frozen-config/admission refusal boundaries; C05 current membership/key scope; AR-011-B errors/readiness, with unavailable-adapter refusal before readiness invocation.
- **Acceptance criteria:** All existing routes use fresh scoped authority and verified evidence with no raw-hash/raw-enqueue fallback; current revoked users can use identity-only me/logout safely; cancel/key effects and restricted audit are atomic; explicit role gates UI actions; unavailable admission refuses before readiness probes/storage/enqueue; the full current-route matrix passes before aggregate completion.
- **Required automated tests:** Exhaustive route/alias 401/403/404 and legacy-shape matrix; old-cookie refusal and v2 issuance, CSRF/exact Origin, me/logout revoked/default/DB-error cases; real PostgreSQL revocation-before-return, mutation races, terminal cancel and rollback at each stage; key/default/secret one-time handling; shared-object cross-project probes; zero readiness/storage/enqueue/provider calls with unavailable adapter; real migration guard refusal.
- **Security and reliability:** P2 starts only after accepted merged P1; fresh authorization before I/O and effect/return; account/project/job lock discipline; no service-key escalation or cookie-role fallback; all customer/live/external gates unchanged.
- **Effort / confidence:** 4 engineering days; planning range 4–7; medium-low confidence.
- **Responsible role:** BE; C owns Auth/routes/verified views/UI, B owns atomic scoped mutations; A independently reviews identity/read/security and B's mutation implementation; B independently reviews C's transaction consumption; C checks action-interface integration; lead integrates.
- **Definition of done:** A independently reviews identity/read/security and B's mutation implementation; B independently reviews C's transaction consumption; C checks action-interface integration; lead integrates. Matching hosted full current-route/PG matrix and accepted merge must be recorded. Lead may then verify aggregate AR-007-C for preparatory scope only; CT-M1-007/009 remain partial overall and CT-M1-008 remains planned until later actual producers pass.
- **Progress:** Verified; accepted merge e117aaae0ef1f4ff4c293747482364a0791bc5d0, independent component/integration reviews, PR/main runs 39535364867/39536476328 and lead-verified candidate 12318112434; [accepted P2 evidence](delivery/EXISTING_ROUTE_AUTHORITY_PLAN.md#accepted-p2-delivery--2026-10-21).

<a id="ar-008"></a>

### AR-008 — Make retries safe and admission/cancellation behavior predictable

M1 / P0 · 5 PRs · 13 engineering days · Verified · [Tracking issue #8](https://github.com/spei04/agent-rewind/issues/8)

<a id="ar-008-a"></a>

#### AR-008-A — Canonical request and durable admission identity

- **Objective:** Make retries safe and admission/cancellation behavior predictable. This task delivers canonical request and durable admission identity.
- **Implementation scope / PR boundary:** Deliver three sequential accepted-merge-gated PRs: strict canonical request and immutable native-v1 configuration/envelope foundation; additive operation/key-alias/common-job-config schema and repositories; reusable admission/recovery coordinator with upload outside SQL and atomic same-Connection job/scope/ref/operation/alias/audit publication. Consume accepted AR-007-C authority; resolve both scoped request identities before readiness, current configuration or storage and reauthorize before disclosure/publication.
- **Out of scope:** No HTTP or available legacy WorkAdmission wiring, worker dispatch, ledger/generation implementation, customer-ready profile, GC, paid execution, provider retry policy or study submission; legacy branch/study configuration compatibility remains a later producer obligation.
- **Prerequisites:** [AR-007-C](#ar-007-c), [AR-009-B](#ar-009-b). E0/G0 and reviewed producer contracts apply; no runtime starts before accepted inputs.
- **Required contracts:** C04; [admission execution plan](delivery/ADMISSION_EXECUTION_PLAN.md) distinguishes proposed interfaces from accepted producers.
- **Acceptance criteria:** Eight concurrent identical requests create one job, operation and creation audit; same client ID/body with a new key adds one alias to the original operation, while either identity with changed canonical intent conflicts. Authorized replay returns the original accepted IDs without current configuration or storage access; revoked access reveals none. Unknown commit acknowledgment reconciles only the original identity in SQL.
- **Required automated tests:** CT-M1-008/010/011/012: eight concurrent winners, alias and composite-FK conflicts, canonical defaults and altered source whitespace, changed configuration/storage-outage recovery, revocation and nondisclosure, rollback and process death before/after commit; additive migration/restore preserves all 14 original rows, 18 ciphertext objects, hash heads and 245000 historical reservation units.
- **Security and reliability:** Preserve source bytes, integer money and original trusted correlation; no storage/network or provider I/O inside SQL. Lock project before grants/caller/targets and recheck current authority plus both unique identities before commit. Preserve old profiles and nondispatchable historical v1 NULL configuration; never infer legacy defaults or use upload-journal evidence as committed identity.
- **Effort / confidence:** 7 engineering days; planning range 7–11; medium-low confidence.
- **Responsible role:** BE; C implemented the service, A authored and corrected the PostgreSQL suite, A/C accepted the correction, B independently audited source and hosted evidence, and lead completed merge/main/candidate delivery.
- **Definition of done:** Each of P1/P2/P3 has independent review, matching required checks and accepted merged-source evidence before its successor starts. Aggregate completion requires the complete synthetic admission/recovery, preservation, PostgreSQL race and commit-uncertainty matrix. Record remaining HTTP/worker/activation gates; no external or production gate is satisfied.
- **Progress:** Verified; [#80](https://github.com/spei04/agent-rewind/issues/80) and P1/P2/P3 #81/#82/#83 are closed. [Accepted P3 evidence](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p3-delivery--2026-10-21) records PR #92 source, merge, actual PostgreSQL matrix, protected-main checks and candidate verification. HTTP integration and admission activation remain separate gates.

Three delivery PRs: P1 2 [2–3], P2 2 [2–3], P3 3 [3–5] BE days. All three accepted-merge gates and the complete internal admission/recovery service matrix passed. AR-008-B retains its own integration and accepted-delivery requirements.

<a id="ar-008-a-p1"></a>

#### AR-008-A/P1 — Canonical request and immutable configuration foundation

- **Objective:** Canonical request and immutable configuration foundation.
- **Implementation scope:** Implement strict SubmitRun/TaskDefinition parsing, m1-review-2 default materialization and canonical intent digest; define bounded immutable native-v1 configuration registry/interface and task/config/version-2 envelope identities. Review registry representation/mutation and scoped ref-versus-digest association before freezing the interface; specify trusted origin-correlation input separately from client intent.
- **Out of scope:** No admission SQL mutation, HTTP wiring, worker or provider access, deployed registry claim, customer-ready profile, or changes to legacy body bytes.
- **Prerequisites:** [AR-007-C](#ar-007-c), [AR-009-B](#ar-009-b). Accepted merged predecessor evidence is mandatory.
- **Required contracts:** C04. C04 SubmitRun/TaskDefinition and canonical revision m1-review-2; bounded 64 KiB common configuration; explicit registry mutation/representation checkpoint; planned typed frozen configuration/envelope and trusted origin input.
- **Acceptance criteria:** Duplicate keys, unknown members, nonfinite values and booleans in integer fields refuse; equivalent defaults hash equally while changed source bytes differ. Frozen configuration/image identity is explicit and bounded, contains no credentials, and cannot be silently resolved from current Settings; integer budget conversion round-trips exactly.
- **Required automated tests:** Canonical default/Unicode/source-whitespace/file-mode vectors; duplicate JSON and strict type/path/size negatives; image/profile mismatch and secret exclusion; exact envelope/config association and trusted-correlation separation.
- **Security and reliability:** No API-side Docker, provider discovery or credential persistence; validate all bounds before materialization and preserve source text. Server-generated correlation never comes from body/header/actor/config digest.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; C implements the pure parser/immutable registry/envelope foundation; B contract/security and A boundary-test review, lead integration.
- **Definition of done:** Independent reviewer acceptance, matching hosted checks and a recorded accepted merge are required before the next package starts; preserve migration-only and external gates.
- **Progress:** Verified in [#81](https://github.com/spei04/agent-rewind/issues/81); accepted merge 81905a5ace65823c91196771f7cd2474a9117306, A/B independent reviews, matching PR/main checks and candidate evidence are recorded in [accepted P1 delivery](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p1-delivery--2026-10-21). Pure preparation only; no admission activation.

<a id="ar-008-a-p2"></a>

#### AR-008-A/P2 — Additive admission schema and identity repositories

- **Objective:** Additive admission schema and identity repositories.
- **Implementation scope:** Implement the next linear additive operations/operation_keys and common job configuration revision with exact scoped constraints, bounded repositories, operator migration, literal profile review and restore evidence. Preserve historical v1 jobs with NULL config and their non-dispatchable meaning; validate descriptor/ref/digest associations rather than equating opaque refs with digests.
- **Out of scope:** No coordinator, HTTP routes, worker claims, budget/generation schema, guessed legacy configuration, historical source rewrite or activation.
- **Prerequisites:** [AR-008-A/P1](#ar-008-a-p1). Accepted merged predecessor evidence is mandatory.
- **Required contracts:** C04. Accepted P1 identities/config association; C04 operations/operation_keys plus payload_version/execution_config job extension and operation failure_correlation_id; migration-only compatibility and immutable historical bytes.
- **Acceptance criteria:** Unique client and key identities plus composite project/principal/kind/job scope constraints hold in SQLite and PostgreSQL; partial/foreign metadata refuses. All 14 original rows, 18 ciphertext objects, hash heads and historical reservation total 245000 remain unchanged through migration and restore; prior catalog profiles are unchanged.
- **Required automated tests:** Real PostgreSQL and SQLite positive/negative constraints, least privilege, rollback/process interruption, restart/idempotent migration, literal profile review and synthetic backup/restore; exact historical fixture/hash/reservation preservation and old-reader fail-closed checks.
- **Security and reliability:** No runtime DDL; one accepted linear predecessor and explicit operator commands; fixed bounded failures and no relaxed catalog profiles. New trusted failure-origin metadata must not repurpose legacy jobs.error or fabricate an original request ID.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; C completed schema/repositories and recovery tests; A preservation/boundary and B contract/security reviews accepted; lead completed hosted/main/candidate delivery.
- **Definition of done:** Independent reviewer acceptance, matching hosted checks and a recorded accepted merge are required before the next package starts; preserve migration-only and external gates.
- **Progress:** Verified; [#82](https://github.com/spei04/agent-rewind/issues/82) is closed. Reviewed 4135c6f merged in [PR #90](https://github.com/spei04/agent-rewind/pull/90) as 41759bb240d7aac0f17bd1c113e6b66d11e06b8b. PR/main runs 39550589433/39552010828 passed 2571/2579 core tests, 11/3 expected skips, actual PostgreSQL, three gVisor tests and installed-package/security/gate checks. Lead verified candidate 12324805344 (544761 bytes), exact four files and source/manifests/package/archive hashes. See [accepted delivery](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). This completes only the P2 schema/repository scope.

<a id="ar-008-a-p3"></a>

#### AR-008-A/P3 — Atomic admission and original-identity recovery

- **Objective:** Atomic admission and original-identity recovery.
- **Implementation scope:** Implement reusable two-stage admission and SQL-only original-identity reconciliation: authorize and resolve both scoped identities before readiness/current config/storage; for a new operation freeze approved config and upload/verify task/config/envelope outside SQL; then fresh same-Connection authority, uniqueness and atomic job/scope/ref/operation/alias/audit publication. Persist trusted origin once and retain it on replay.
- **Out of scope:** No HTTP wiring, available legacy admission adapter, worker dispatch, paid calls, ledger/generation, GC, customer-ready profile or upload-journal-based recovery.
- **Prerequisites:** [AR-008-A/P2](#ar-008-a-p2). Accepted merged predecessor evidence is mandatory.
- **Required contracts:** C04. Accepted P1/P2 plus scoped RequestAuthority, confirmed artifact write/metadata primitives and fixed Accepted/error grammar; SQL reconciliation owns operation identity, not the run-publication journal.
- **Acceptance criteria:** Eight concurrent requests produce one accepted job/operation/creation audit; same client/body new key aliases that operation and either-key/body conflict refuses. Config changes or storage outage cannot alter a committed response; revoked access discloses no identity. Lost commit acknowledgment returns outcome_uncertain and only the original identity is reconciled in SQL, with no automatic new upload or job.
- **Required automated tests:** CT-M1-008/010/011/012 service matrix: eight-way contention, same-client/new-key race, key-to-other-client conflict, altered canonical body, changed config/storage outage, revocation before return/commit, rollback and actual process death before/after commit, confirmed-orphan upload receipts and safe uncertain outcome.
- **Security and reliability:** Project-before-grant/caller/job lock hierarchy; current authority and both unique identities rechecked under the owned transaction; no I/O while locked. Unreferenced uploads are not committed jobs, receipts are not authority, and caller changes cannot recover another principal's operation.
- **Effort / confidence:** 3 engineering days; planning range 3–5; medium-low confidence.
- **Responsible role:** BE; C implemented runtime/unit/fault coverage, A authored and corrected the PostgreSQL suite, A/C reviewed the correction, B accepted final source and hosted proof, and lead completed protected delivery.
- **Definition of done:** Independent reviewer acceptance, matching hosted checks and a recorded accepted merge are required before the next package starts; preserve migration-only and external gates; aggregate acceptance additionally requires the complete admission/recovery matrix.
- **Progress:** Verified; [#83](https://github.com/spei04/agent-rewind/issues/83) is closed. Reviewed a09e26d merged as 4c86c52a14e45fee6a27f8b4410310ced064cf31 in [PR #92](https://github.com/spei04/agent-rewind/pull/92); PR/main runs 39574109747/39576754575 passed 2860/2870 tests, 13/3 expected skips, all 33 publication plus 26 recovery PostgreSQL cases and three gVisor cases. Lead verified candidate 12335133060 (585266 bytes), exact four files and identity/checksums. [Accepted P3 delivery](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p3-delivery--2026-10-21) preserves prior failures and current limits. Default adapters and customer admission remain unavailable.

<a id="ar-008-b"></a>

#### AR-008-B — Submit, operation status and cancellation routes

- **Objective:** Make retries safe and admission/cancellation behavior predictable. This task delivers submit, operation status and cancellation routes.
- **Implementation scope / PR boundary:** Deliver two sequential accepted-merge-gated PRs: a bounded operation status and same-Connection cancellation adapter, then exactly the frozen submit/status/cancel HTTP operations. Consume accepted AR-008-A replay/publication and named-project authority; freeze result and stored-failure producer support before runtime. AR-006-B retains run list/detail/cursors. P1 also establishes factory-born file-backed QueuePool SQLite provenance and a shared progress lease for operation/listing/compatibility; all ordinary shared-engine callers require cleanup proof. P1 owns explicit owned_connect/owned_begin contexts and generation-bound post-close verdicts across the complete audited acquisition map.
- **Out of scope:** No run list/detail/cursors, branch/study/export routes, generic operation framework, worker failure producer or dispatch, new ledger/lease/schema/profile, customer activation or paid validation.
- **Prerequisites:** [AR-008-A](#ar-008-a), [AR-011-B](#ar-011-b). Both packages wait for accepted AR-008-A including P3 merge/main/candidate evidence; planning does not start runtime.
- **Required contracts:** C04; [operation HTTP execution plan](delivery/OPERATION_HTTP_EXECUTION_PLAN.md) fixes the producer/transaction checkpoint and later three-route boundary.
- **Acceptance criteria:** Exact Accepted, Operation and Cancellation fields preserve required nulls, original IDs/correlation and integer accounting values. Unsupported result/failure evidence refuses safely; no raw error or guessed run is exposed. Cancellation binds the original operation/job association under current authority in one transaction, preserves terminal outcome/reservations, and never returns success after uncertain commit.
- **Required automated tests:** CT-M1-007/008/009/010/011/012 route subsets and CT-M1-013/014: bounded original operation/job/ref receipts and revocation, same-Connection cancellation races/rollback/acknowledgment, exact transport limits and schemas, replay before current dependencies, original failure versus polling correlation, real migration-only zero-I/O guard and installed-package isolation; actual PostgreSQL evidence is required. Prove owned SQLite pre-ping/reset ordering, nested-owner no-effects refusal, foreign/retained-idle handler detection, dirty quarantine, ordinary caller cleanup and unchanged PostgreSQL/untracked legacy behavior. Every mapped ordinary caller must observe late lifecycle/native-close failures; checkout-before-yield and stale-generation cases require terminal proof.
- **Security and reliability:** Identity and scoped visibility precede action and input diagnostics. No raw error/result/hash fallback or client-derived origin; unsupported producer evidence fails closed. Preserve project-first lock ordering, fresh disclosure authority and no external I/O under SQL locks. Keep migration-only/customer and later paid-dispatch gates, without a reverse worker prerequisite.
- **Effort / confidence:** 6 engineering days; planning range 6–10; medium-low confidence.
- **Responsible role:** BE; platform/security authored runtime, planning/verification supplied independent tests/source review, the delivery reviewer audited hosted evidence, and the lead integrated and accepted the candidate.
- **Definition of done:** Both packages require independent review, matching hosted checks and accepted merged-source evidence in order; aggregate verification requires the complete three-route service/HTTP and actual PostgreSQL matrix. Preserve fixed errors, existing-route behavior, historical evidence and later worker/customer/G1 gates; full M1 integration remains with AR-012-B. B/lead accepted ownership entry 5bedede with C acquisition-map review. The composed owned-factory and fixture checkpoint 97d39edf is accepted as a component after independent source/package review and 1,273 local passes with 250 explicit PostgreSQL skips. The bounded GET/cohort/receipt primitive 691ad661 is accepted as a component after B source review, A's independent 174 SQLite and 18 actual PostgreSQL passes across separate runs, and exact-source package verification. A added three PostgreSQL race/permission controls at cbed928. GET service 28d47cc9 has B/lead source review, 312 combined author passes, 19 separate actual PostgreSQL passes and independently verified exact 112-member installed-package evidence. Earlier primitive source 5e1766d passed matching component CI 39601721324. The caught-read failure latch is corrected at 9f73448d and accepted by B, C and the lead: 55 independent SQLite cases pass, including the original reproducer; author evidence covers 134 SQLite and 40 actual PostgreSQL cases across full runs plus affected reruns. Composition 950a4160 preserves the exact reviewed source union and passes 85 independent GET SQLite and 19 actual PostgreSQL service cases. Cancellation service 1ce9469f is accepted by B and the lead; 68 independent SQLite cases pass at composed source 0f031962. Independent PostgreSQL evidence covers 65 distinct cases across the initial 62 passes and three affected/new passes at 5461917a/ce8a2f04, including two physical QueuePool recovery controls; this is assembled evidence, not one 65-pass run. Composition f9172462 preserves the exact 377-file source union. Installed smoke 71d33737 and all 113 Git/wheel/sdist/installed runtime members are independently verified; final-source package, hosted checks and candidate are accepted at merge 03a8e074. P1 and P2 are Verified after their separate accepted HTTP entry and delivery gates; accepted source, hosted attempts and candidate proof are recorded in the dated delivery plan.
- **Progress:** Verified; #93/#95 and parent #8 are closed after [accepted P2 delivery](delivery/OPERATION_HTTP_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). P1 #94 retains its own accepted merge/review record. Default adapters/customer admission and later gates remain unavailable or open.

<a id="ar-008-b-p1"></a>

#### AR-008-B/P1 — Bounded operation reads and atomic cancellation

- **Objective:** Provide the exact operation response and cancellation transaction boundary without HTTP wiring.
- **Implementation scope:** Implement a bounded operation/job view with original source, config, scope and artifact descriptor receipts plus final fresh authority. Resolve non-null results through the scoped job result ref and exact run/job lineage. Review and freeze the supported stored-failure format and producer mapping before runtime; unsupported evidence refuses. Add operation cancellation with association, authority, effect and fixed audit on one Connection, preserving existing legacy cancellation behavior. Add one internal factory-born SQLite capability/progress-lease helper, narrow Database file-backed QueuePool construction and mechanical operation/listing/compatibility consumers; no retrospective engine certification. Mechanically adapt all 33 audited acquisition sites in 14 modules through narrow public-API contexts or the retained manual-owner receipt; no Engine facade/private SQLAlchemy override.
- **Out of scope:** No HTTP routes, worker/failure-envelope production, schema or profile changes, GET repair/migration markers, artifact hash fallback, new accounting or provider cancellation.
- **Prerequisites:** [AR-008-A](#ar-008-a), [AR-011-B](#ar-011-b). Accepted predecessor evidence is mandatory; all aggregate prerequisites remain binding.
- **Required contracts:** C04. C04 Operation ten-field and Cancellation three-field contracts; accepted AR-008-A operation/config identities and origin, AR-007-C named authority/scoped actions, bounded scoped artifact reads and AR-011-B fixed errors; OPERATION_HTTP_EXECUTION_PLAN.md producer and transaction checkpoints.
- **Acceptance criteria:** Viewer status reads disclose only the authorized project and valid original operation/job association. Null result remains null; non-null evidence requires exact scoped ref and run lineage. Supported stored failures retain original correlation, including outcome_uncertain as data; unsupported evidence refuses. Cancellation locks and rechecks the association, preserves terminal outcomes and gross reservations, and reports only an acknowledged committed intent. Owned SQLite disables pre-ping and implicit pool reset only with explicit native-idle/lease/provenance validation and dirty quarantine; known active nested owners refuse before effects. PostgreSQL and explicit untracked legacy paths retain their behavior. A retained generation-specific verdict must prove close/terminal pool release and no latched failure before success, including ordinary callers and early checkout failures without a yielded Connection.
- **Required automated tests:** SQLite and actual PostgreSQL malformed/oversized metadata and result/failure producer cases; original operation/job/config/ref drift and final revocation; viewer read versus cancel denial, foreign scope, queued/running/terminal intent, repeated cancellation, observed operation replacement and worker/member/key races, rollback and lost acknowledgment with bounded cleanup. Include factory provenance, all three lease-consumer permutations, pre-ping/reset/Connection.close ordering, direct handler and retained-idle attempts, partial hooks/BaseException/discard cleanup and all ordinary Database-engine callers under the new pool policy. Prove suppressed native-close errors remain visible, concurrent reuse cannot overwrite a prior receipt, all ordinary contexts refuse late failure, and original primary/commit-ACK semantics survive.
- **Security and reliability:** Project then organization, caller grants/key and target exclusion follows accepted ordering; no separate get-then-cancel transaction or storage under locks. Bound bodies before decoding and preserve original receipts; unsupported legacy error strings never become trusted envelopes or null success. No accounting refund or running-provider interruption claim. Lifecycle-only engine/pool hooks perform no SQL; request-budget listeners remain Connection-local. No arbitrary-engine flag, callback restoration claim or malicious in-process bypass proof.
- **Effort / confidence:** 4 engineering days; planning range 4–7; medium-low confidence.
- **Responsible role:** BE; C authored the services, A provided independent test/package proof, B reviewed source/delivery and the lead integrated and accepted the candidate.
- **Definition of done:** Independent producer/security review freezes the finite source-support and cancellation tables before implementation; bounded SQLite and actual PostgreSQL tests, matching hosted checks and accepted merged-source evidence complete P1 before P2. No HTTP availability or aggregate completion follows. B/lead accepted ownership entry 5bedede, with independent C acquisition-map review; The composed owned-factory and fixture checkpoint 97d39edf is accepted as a component after independent source/package review and 1,273 local passes with 250 explicit PostgreSQL skips. The bounded GET/cohort/receipt primitive 691ad661 is accepted as a component after B source review, A's independent 174 SQLite and 18 actual PostgreSQL passes across separate runs, and exact-source package verification. A added three PostgreSQL race/permission controls at cbed928. GET service 28d47cc9 has B/lead source review, 312 combined author passes, 19 separate actual PostgreSQL passes and independently verified exact 112-member installed-package evidence. Earlier primitive source 5e1766d passed matching component CI 39601721324. The caught-read failure latch is corrected at 9f73448d and accepted by B, C and the lead: 55 independent SQLite cases pass, including the original reproducer; author evidence covers 134 SQLite and 40 actual PostgreSQL cases across full runs plus affected reruns. Composition 950a4160 preserves the exact reviewed source union and passes 85 independent GET SQLite and 19 actual PostgreSQL service cases. Cancellation service 1ce9469f is accepted by B and the lead; 68 independent SQLite cases pass at composed source 0f031962. Independent PostgreSQL evidence covers 65 distinct cases across the initial 62 passes and three affected/new passes at 5461917a/ce8a2f04, including two physical QueuePool recovery controls; this is assembled evidence, not one 65-pass run. Composition f9172462 preserves the exact 377-file source union. Installed smoke 71d33737 and all 113 Git/wheel/sdist/installed runtime members are independently verified; final-source package, hosted checks and candidate are accepted at merge 03a8e074. P1 is Verified; P2 is In progress under separate HTTP entry and delivery gates. The exact caller map and post-close verdict boundary must be independently accepted and completely implemented before factory wiring is accepted; no missed bare acquisition is certified.
- **Progress:** Verified; [accepted P1 delivery](delivery/OPERATION_HTTP_EXECUTION_PLAN.md#accepted-p1-delivery--2026-10-21) records reviewed source 1b0d1fe4, merge 03a8e074b51dca7c03d69295e0c18ca0f22dc1da, successful PR/main runs 39616207090/39620379652 and verified candidate 12355648523. Issue #94 is closed. Component results and failed runs remain separately recorded; no HTTP or aggregate completion follows.

<a id="ar-008-b-p2"></a>

#### AR-008-B/P2 — Frozen submit, operation status and cancellation HTTP

- **Objective:** Expose exactly the three remaining frozen M1 HTTP operations through accepted services.
- **Implementation scope:** Wire submitProjectRun, getProjectOperation and cancelProjectOperation to accepted coordinator and P1 adapters. Preserve migration/security guard, actual authentication and named visibility before manual transport validation; pass exact key hash and trusted server origin, retain replay before current dependencies, and document exact request/response/error/header schemas. Add isolated installed-package smoke and the full HTTP matrix.
- **Out of scope:** No list/detail changes, legacy admission fallback, new reconcile endpoint, worker/ledger/generation integration, ready profile, customer activation or provider calls.
- **Prerequisites:** [AR-008-B/P1](#ar-008-b-p1). Accepted predecessor evidence is mandatory; all aggregate prerequisites remain binding.
- **Required contracts:** C04. Accepted merged P1 and inherited C04; exact frozen Accepted, Operation, Cancellation and four-field Error schemas, operation IDs, path/header/body limits, CT-M1-007/008/009/010/011/012 route subsets and CT-M1-013/014.
- **Acceptance criteria:** Raw JSON and exact Idempotency-Key validation retain duplicate detection and canonical limits after authority. Accepted replay retains IDs/config/origin despite current dependency outages; unknown commit never creates new work. Every route preserves exact status/headers/null fields, cookie and key authority, original nested failure versus fresh polling correlation, and real migration-only refusal before customer sinks.
- **Required automated tests:** Actual cookie and scoped-key routes with two populated projects, viewer/operator and revoked/foreign precedence; duplicate headers/JSON, chunked 9 MiB and materialized 8 MiB boundaries, exact encoding/media type and schemas; eight-request replay/contention, changed defaults/storage outage, fixed uncertainty/error mapping, cancellation races, original/fresh correlation, zero prohibited sinks and isolated installed wheel/sdist smoke.
- **Security and reliability:** No eager validation before identity/visibility, collapsed duplicate headers or client-provided origin. Cookie mutations retain CSRF/exact Origin; GET remains read-only. Default required adapters refuse before readiness/storage, existing committed replay bypasses new-work dependencies, and exceptions map only through reviewed finite safe boundaries.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; platform/security authored runtime, planning/verification supplied independent tests/source review, the delivery reviewer audited hosted evidence, and the lead integrated and accepted the candidate.
- **Definition of done:** Independent HTTP/security review, actual PostgreSQL integration, matching hosted installed-package/security/gVisor checks, accepted merge and protected-main candidate evidence establish P2 and aggregate completion. Preserve historical records, existing routes and later AR-010/AR-012-B/customer gates.
- **Progress:** Verified; #95 closed after reviewed source 065df8c, protected merge cefd222, matching PR/main runs 39683408934/39686498691 attempt 1 and verified candidate 12387716715. [Accepted P2 delivery](delivery/OPERATION_HTTP_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21) records exact evidence and limits.

<a id="ar-009"></a>

### AR-009 — Keep published evidence immutable, scoped and complete

M1 / P0 · 2 PRs · 4 engineering days · Verified

<a id="ar-009-a"></a>

#### AR-009-A — Versioned object/ref metadata and storage protocol

- **Objective:** Keep published evidence immutable, scoped and complete. This task delivers versioned object/ref metadata and storage protocol.
- **Implementation scope / PR boundary:** Define storage interface and metadata constraints for immutable objects, verified digest and project-scoped owner references
- **Out of scope:** No GCS adapter, KMS rotation or GC
- **Prerequisites:** [AR-007-A](#ar-007-a), [AR-005-C](#ar-005-c), [AR-011-B](#ar-011-b). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C04; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Composite references cannot cross projects; existing encrypted format remains readable
- **Required automated tests:** Schema scope violations, legacy ciphertext round-trip and duplicate reference tests
- **Security and reliability:** Opaque locator is not authorization; encryption key stays server-side
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Engineer A — artifact metadata/storage; independent review assigned by lead
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Verified; [issue #53](https://github.com/spei04/agent-rewind/issues/53) closed after [PR #55](https://github.com/spei04/agent-rewind/pull/55), reviewed integration 260e1d1 and matching hosted run 39364861264; preparatory migration-only scope.

<a id="ar-009-b"></a>

#### AR-009-B — Atomic publication boundary and corruption handling

- **Objective:** Keep published evidence immutable, scoped and complete. This task delivers atomic publication boundary and corruption handling.
- **Implementation scope / PR boundary:** Wire upload/verify before DB publication; read requires scoped ref and validates format/digest.
- **Out of scope:** No automated orphan deletion.
- **Prerequisites:** [AR-009-A](#ar-009-a), [AR-007-B](#ar-007-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Partial writes never produce completed reference; orphan remains identifiable; corruption explicit.
- **Required automated tests:** M1-015/017 object timeout, DB rollback, wrong digest and equal bytes in two projects.
- **Security and reliability:** No cross-project dedup oracle; bounded errors and no raw object URL disclosure.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Engineer C implements; Engineer A reviews failure/security behavior and Engineer B reviews contracts/transactions.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified preparatory scope; [issue #69](https://github.com/spei04/agent-rewind/issues/69), [PR #70](https://github.com/spei04/agent-rewind/pull/70). Reviewed integration 5923bbe and hosted run 39461271604: 1431 tests per Python, eleven actual PostgreSQL publication cases and all required checks. Live adapter/run projection and full M1 gates remain separate.

**Publication integration boundary (2026-10-20):** AR-009-B provides the preparatory run-graph publication coordinator and complete scoped manifest reference, with a required same-transaction fence/writer interface. AR-010-A owns the unavailable generation schema and database-time live fence; AR-006-A owns run-projection integration. The current live adapter must refuse rather than fall back to an owner-only check. Contract fixtures test atomic publication, but do not close live-worker or full M1 acceptance; AR-010-A/B and AR-012-B retain those integration gates. No historical adoption or unsupported job/study/provider graph production is added.

<a id="ar-010"></a>

### AR-010 — Enforce budget limits before every potentially paid action

M1 / P0 · 6 PRs · 10 engineering days · In progress · [Tracking issue #10](https://github.com/spei04/agent-rewind/issues/10)

<a id="ar-010-a"></a>

#### AR-010-A — Integer ledger and hierarchical reservations

Tracking: [#107](https://github.com/spei04/agent-rewind/issues/107) · In progress.

- **Objective:** Deliver the scoped integer ledger, trusted fixed-period provisioning and conservative reservation/generation primitives before live worker integration.
- **Implementation scope / PR boundary:** Two sequential accepted-merge-gated packages: exact additive ledger schema/catalog/provisioning/opening backfill, then connection-bound reservations, minimum generation fences and no-reset rollover. Preserve the three frozen ledger tables, original account triple, gross job reservations and prior outstanding exposure.
- **Out of scope:** No public SubmitRun/native-v1 changes, automatic lifetime policy, live worker/ChatPolicy dispatch, settlement/release/transfer command, invoice ingestion, incident-latch table, production profile or spending.
- **Prerequisites:** [AR-008-B](#ar-008-b). Accepted protected-main HTTP delivery and exact manifest/interface/SQL entry review are required before either implementation package; E0 applies transitively.
- **Required contracts:** C04. The owner-approved finite authorized-window interpretation and [ledger execution plan](delivery/LEDGER_EXECUTION_PLAN.md) preserve the frozen public API and native-v1 configuration.
- **Acceptance criteria:** Concurrent reservations cannot exceed any organization/project/job cap or double-count a logical call. One finite immutable authorized job execution window is supplied by trusted provisioning; retries, claims, restarts and billing rollover never renew it. Expiry prevents new paid work while preserving holds and original identities. Migration, restoration and retry preserve historical opening exposure and exact scoped constraints.
- **Required automated tests:** CT-M1-018/020 plus relevant generation/lease controls: historical 245000 opening exposure, signed-64-bit/native-type boundaries, absent/overlapping period races, deferred commit rejection, exact executable-catalog drift, restart/restore; eight-way reservations, shared organization caps, prior-period holds, repeated/conflicting calls, wait-time generation/cancel/window changes, rollback/lost acknowledgment and actual PostgreSQL cleanup.
- **Security and reliability:** Use trusted bounded provisioning and SQL-derived openings, never mutable worker timeouts, user amounts or invented timestamps. Stable scope exclusion precedes jobs and sorted accounts; select stronger organization mode before downstream locks. No external I/O under SQL locks, no automatic account creation, no refund on timeout, no fabricated call-owned evidence and no generic trigger/function allowance.
- **Effort / confidence:** 6 engineering days; planning range 6–10; medium-low confidence.
- **Responsible role:** BE; platform/security owns P1 runtime in secondary work/ledger-schema. Planning/verification owns independent tests after accepted progress handoff and stable interfaces; lead integrates, with independent delivery/security review.
- **Definition of done:** Both packages require independent exact-entry/source review, local and hosted SQLite/actual PostgreSQL evidence, installed-package/security checks and accepted merged-source/candidate evidence in order. AR-008-B must have accepted protected-main delivery before implementation; P2 additionally waits for accepted merged P1. The whole aggregate precedes AR-010-B; later worker, reconciliation and full M1/customer gates remain separate.
- **Progress:** In progress in #107 under the explicit P1 #108 assignment after accepted HTTP delivery and P1 entry 51af77dc. P1/P2 acceptance remains null; P2 #109 is Not started until accepted P1 and its own entry review. Parent #10 remains open/In progress.
- **Delivery boundary:** Two sequential acceptance packages across four BE PRs: P1 has F1 dormant schema/operator/guard foundation, F2 complete bounded persisted reader, and F3 trusted provisioning/opening/replay/recovery; P2 reservation/minimum generation/rollover remains one PR after accepted full P1. P1 and P2 each retain 3 [3–5] days, total 6 [6–10], medium-low, with inherited AR-008-B and no early package acceptance.
- **Contract readiness:** Frozen C04 remains authoritative. The owner approved proposal 882fa139 on 2026-10-21: fixed job lifetime is one finite immutable authorized execution window from trusted provisioning, not an observed completion interval or renewable worker timeout. Exact P1 manifest/schema/authority/native bounds/replay, SQL privilege and outcome/recovery policy is independently accepted at 51af77dc. Implementation must prove exact DDL/catalog, constraints, bounds and recovery against that policy. P2 reservation/fence entry requires separate review after accepted P1. No public API/native configuration or ready-profile amendment is made.

<a id="ar-010-a-p1"></a>

#### AR-010-A/P1 — Ledger schema, trusted provisioning and opening backfill

Tracking: [#108](https://github.com/spei04/agent-rewind/issues/108) · In progress.

Implementation PRs: [F1 foundation](#ar-010-a-p1-f1), [F2 reader](#ar-010-a-p1-f2), [F3 operator and recovery](#ar-010-a-p1-f3). Issue #108 stays open through F1/F2; only full P1 acceptance closes it.

- **Objective:** Represent scoped accounts, logical calls and evidence-backed entries with explicit trusted provisioning and preserved historical exposure.
- **Implementation scope:** One additive linear revision after ar6 for the three frozen ledger tables and job generation/legacy-reservation fields. Freeze and implement the exact bounded operator manifest, canonical digest, ownership/authority, replay/conflict semantics and SQL-derived opening backfill. Update both catalog inspection and migration exclusion to the exact 20-table profile; allow only reviewed PostgreSQL deferred constraints/functions, definitions and owner/security/search-path/privilege state. Preserve older literal profiles, resume/restore and migration-only compatibility.
- **Out of scope:** No HTTP/public SubmitRun/native-v1 changes, automatic deadline policy, live worker claims/dispatch, settlement/release/transfer commands, invoice ingestion or new incident tables.
- **Prerequisites:** [AR-008-B](#ar-008-b). All inherited prerequisites remain required; implementation waits for accepted HTTP and exact entry review.
- **Required contracts:** C04. Frozen C04 accounts, immutable call/account triple and periods, unique entries and same-call/project evidence closure; existing operator migration/backup/restore contracts. Owner-approved finite nonrenewable job execution window; exact manifest, bounded source inventory, executable catalog and transition/restore semantics must be frozen at entry.
- **Acceptance criteria:** Opening exposure is copied once from original jobs.reserved, aggregated once per account level and never fabricated as a provider call; historical fixture exposure remains 245000 microUSD. Missing trusted historical bounds, conflicting ownership/periods or caps below exposure refuse. Original rows/fields/ciphertexts remain intact except explicitly declared additive backfill. Fresh, resumed and restored states agree; extra/changed/disabled executable objects and unsupported profiles refuse before customer work.
- **Required automated tests:** SQLite and actual PostgreSQL historical opening/preservation and integer/native bounds; missing/conflicting/oversized manifest, cross-project/null shape and concurrent absent/overlapping periods; deferred commit rejection and same-call evidence constraints; wrong/extra/disabled trigger/function inventory, restricted runtime DDL denial, interrupted pre/post-commit migration and exact backup/restore.
- **Security and reliability:** Select stable scope exclusion before jobs/accounts and freeze explicit plus implicit FK/trigger waits; sorted existing accounts alone cannot protect absent periods. No caller-supplied opening amounts, silent cap increase or generic executable-object permission. New and historical jobs need explicit provisioning; absence refuses without settings/infinity fallback. Unsupported settlement/transfer mutations stay unavailable.
- **Effort / confidence:** 3 engineering days; planning range 3–5; medium-low confidence.
- **Responsible role:** BE; platform/security runtime author, planning/verification independent owned tests after stable interfaces and released ownership, lead integration and independent delivery/security review.
- **Definition of done:** Before implementation, independent entry review freezes exact manifest/native bounds/authority and schema, function-body, security/search-path, privilege and profile policy plus the preservation/restore matrix. Implementation-generated exact DDL and literal dialect catalog captures must match that reviewed policy and pass independent comparison before delivery acceptance. Reviewed implementation passes local and hosted actual-database/package/security checks with accepted merge and protected-main candidate. This completes only P1; P2 and whole AR-010-A remain unaccepted until their own gates.
- **Progress:** In progress in #108 after explicit lead handoff from accepted planning 9f6ea6e; P1 entry 51af77dc and HTTP delivery cefd222 are accepted. Accepted merge/review evidence remains null until actual implementation and delivery proof pass. First manifest/DDL/catalog checkpoint does not complete P1.

<a id="ar-010-a-p1-f1"></a>

#### AR-010-A/P1/F1 — Dormant ledger schema and operator foundation

- **Objective:** Merge the independently testable internal foundation without claiming provisioning or ledger package completion.
- **Implementation scope:** Strict immutable manifest/progress inputs, explicit ar7 DDL and literal dialect catalogs, owned factory/work/transaction/lifecycle controls and the private transaction-body guard. Preserve ar1–ar6 behavior and generic upgrade refusal; no supported customer profile or public operator activation.
- **Out of scope:** No complete persisted reader, initialize/provision success path, opening backfill, replay/recovery completion, P2 reservation work or customer activation.
- **Required contracts:** C04. Accepted P1 entry 51af77dc, unchanged C04 and reviewed factory/work/outcome/guard seams; exact pinned native dependencies, 2048 total work units and one deadline remain mandatory.
- **Acceptance criteria:** Exact reviewed dormant source passes independent native/source/security review, old-profile regressions, matching PR and protected-main checks and a source-bound candidate. Its merge is only an internal checkpoint; issue #108 and both P1 delivery acceptance fields remain open/null.
- **Required automated tests:** Strict inputs, explicit catalog/constraints, SQLite and actual PostgreSQL ownership/outcome/work/cleanup/guard faults on both supported interpreters; unchanged existing callers; hosted database, gVisor, package/security and exact candidate runtime identity.
- **Security and reliability:** No generic executable-object allowance, partial LedgerState, customer ar7 readiness or public CLI activation. Keep native SQL and callback generation visible to the existing work/outcome owner; retain failed hosted attempts.
- **Definition of done:** Reviewed source, scoped local/native evidence, successful exact-source PR/main checks and independently verified candidate are linked before the foundation checkpoint is accepted; every remaining P1 gate stays required.
- **Prerequisites:** [AR-008-B](#ar-008-b).
- **Responsible role:** BE.
- **Effort allocation:** Included in AR-010-A/P1; no additional effort or acceptance package.
- **Progress:** Merged; checkpoint accepted.
- **Checkpoint evidence:** c6f32cdd2633d5022d4ebdbc78589920a7f3d9dc / 2e0eeeab45eb97c925454a7c9e23f2ddfcc47249. Independently reviewed dormant foundation; PR 111 run 39729061054 and protected-main run 39733331352, both attempt 1, passed required checks. Candidate 12407151544 has verified archive SHA256 746fd89d18ad35604ee92b6043352d0d6589bb4c9151cbc62ff7ed94af4d2479 and 124 exact runtime members; durable release record reviewed-delivery-20261021-pr111-2e0eeea.json SHA256 b28fd23a35b3b3e8cc02418912cf215898f44baf57bf73ef60489dcb03dbf1e8.
- **Tracking PR:** https://github.com/spei04/agent-rewind/pull/111.

<a id="ar-010-a-p1-f2"></a>

#### AR-010-A/P1/F2 — Complete bounded persisted ledger reader

- **Objective:** Prove complete persisted ledger inspection within the accepted native byte, row, work and deadline bounds.
- **Implementation scope:** Validate complete manifest/progress provenance, native financial state, source ownership/evidence closure and canonical digests using explicit observed fixed-page/keyset query families. Prove combined setup, catalog, graph, reference, financial and transaction costs at supported maximum states.
- **Out of scope:** No partial LedgerState, hidden server-cursor FETCH, new work budget, provisioning/writer activation, relaxed maximum-state claim or P2 behavior.
- **Required contracts:** C04. Accepted P1 entry and F1 guard/transaction seam. Exact query families, dialect plans, canonical projection shape and combined budget proof require independent review before traversal implementation; the conditional 215-page bound alone is not an accepted reader.
- **Acceptance criteria:** A complete reader returns only fully validated persisted state; malformed/oversized/incomplete state refuses without writes. Native maximum-state and one-over cases prove the shared 2 MiB, 2028 ordinary-unit and 120-second limits with no hidden SQL. Matching scoped PR/main/candidate evidence is accepted before F3.
- **Required automated tests:** SQLite and actual PostgreSQL malformed native rows, graph/ownership/evidence and provenance attacks; byte and row boundaries; exact per-page SQL/native traces, exhausted work/deadline and no-write controls; complete supported-state positives and old-profile isolation.
- **Security and reliability:** Inspect authority before reads, retain invalid candidates rather than converting them to absence, bound every object/prefix/graph family and reuse one transaction/work owner. Keep customer operator activation unavailable.
- **Definition of done:** Independent exact query/source/native-capacity review and matching PR/main/package/security/candidate checks accept the complete internal reader; P1 remains In progress with null package acceptance.
- **Prerequisites:** [AR-008-B](#ar-008-b), [AR-010-A/P1/F1](#ar-010-a-p1-f1).
- **Responsible role:** BE.
- **Effort allocation:** Included in AR-010-A/P1; no additional effort or acceptance package.
- **Progress:** Merged; checkpoint accepted.
- **Entry:** Accepted 2026-10-22 [implementation entry](delivery/LEDGER_EXECUTION_PLAN.md#f2-reader-implementation-entry--2026-10-22); [checkpoint accepted](delivery/LEDGER_EXECUTION_PLAN.md#accepted-f2-reader-and-f3-handoff--2026-10-22).
- **Checkpoint evidence:** ac3b0a31edb1ff06393b12943eabd31e0ae232b5 / e8cba52f2979b9b8d2f2047de6856f82ba8e0502. Independently reviewed complete bounded reader and retained native boundary evidence; PR 114 run 39780954252 and protected-main run 39786131008, both attempt 1, passed all required checks. Candidate 12431486551 has verified archive SHA256 9dff927ab83464b63066126f121f2efa5f74942b419dfa078ac578372515c56f and 133 exact runtime members; durable release record reviewed-delivery-20261021-pr114-e8cba52.json SHA256 3f74e257d52532dc7c72a6bfeaf2594760816309435d8f31cba72ceba824338d. Earlier failed main and interrupted verifier evidence remain separate; full P1 acceptance stays null.
- **Tracking PR:** https://github.com/spei04/agent-rewind/pull/114.

<a id="ar-010-a-p1-f3"></a>

#### AR-010-A/P1/F3 — Trusted provisioning, opening, replay and recovery

- **Objective:** Complete the approved P1 operator vertical slice with preserved historical exposure and evidence-backed recovery.
- **Implementation scope:** Integrate trusted initialization/provisioning, SQL-derived original opening exposure, immutable accounts/windows, canonical replay/conflict handling and bounded post-uncertainty inspection. Complete concurrent absent-period exclusion, child interruption and owner/ACL-preserving backup/restore with the F1/F2 foundation.
- **Out of scope:** No supplied opening amounts, silent cap increase, renewed execution window, automatic paid retry/refund, live worker/ChatPolicy activation, settlement/transfer commands or P2 reservations.
- **Required contracts:** C04. All unchanged AR-010-A/P1 and C04 acceptance contracts, frozen entry 51af77dc and accepted F1/F2; operator returns, native types, authority, catalog/privilege, outcome and restore policy retain their exact meanings.
- **Acceptance criteria:** Every original field/row/ciphertext is preserved except declared additive backfill; historical exposure remains exactly 245000 microUSD and is copied once per level without fabricated provider calls. Fresh/resumed/restored state agrees; incomplete authority, native bounds or recovery proof refuses. Full P1 matrix and final protected-main candidate must pass.
- **Required automated tests:** Actual SQLite/PostgreSQL trusted manifest and cap/period conflicts, opening preservation, replay/no-write and concurrent absent-period cases; deferred constraints/privilege denial, lost ACK and bounded absence proof, child-death/restart, owner/function ACL restoration and integrated maximum-state inspection.
- **Security and reliability:** Keep stable scope exclusion before downstream locks, conservative unknown outcomes and original immutable identities. No customer-ready claim or P2 handoff until the full P1 acceptance record is independently reviewed.
- **Definition of done:** All F1/F2/F3 checkpoint evidence plus every existing full-P1 source, native, preservation/recovery, package/security, PR/main and final candidate gate is accepted. Only that final merge/review record may populate P1 acceptance; P2 still requires its own entry review.
- **Prerequisites:** [AR-008-B](#ar-008-b), [AR-010-A/P1/F2](#ar-010-a-p1-f2).
- **Responsible role:** BE.
- **Effort allocation:** Included in AR-010-A/P1; no additional effort or acceptance package.
- **Progress:** In progress.
- **Entry:** Lead authorized implementation on 2026-10-22 after accepted F2; shared-check kernel first, with unchanged full P1 gates.
- **Checkpoint evidence:** Pending; no accepted source/merge/review.
- **Tracking PR:** Not assigned.

<a id="ar-010-a-p2"></a>

#### AR-010-A/P2 — Integer reservations, generation fence and rollover proof

Tracking: [#109](https://github.com/spei04/agent-rewind/issues/109) · Not started.

- **Objective:** Provide conservative connection-bound reserve-only primitives with current generation authority, repeat-stable call identity and bounded prior-period exposure.
- **Implementation scope:** Implement minimum claim/live-fence and existing-account reservation primitives after accepted P1. Atomically bind logical call and resource scope, three reservation entries and three account balances, while retaining the gross job counter. Check current plus prior outstanding organization/project holds under stable scope exclusion; inspect the original scoped identity after uncertain acknowledgment without granting a new dispatch opportunity.
- **Out of scope:** No live ChatPolicy/worker wiring, network dispatch, cancellation refund, settlement/reconciliation/transfer production, automatic account creation or broad process-recovery feature.
- **Prerequisites:** [AR-008-B](#ar-008-b), [AR-010-A/P1](#ar-010-a-p1). All inherited prerequisites remain required; implementation waits for accepted HTTP and exact entry review.
- **Required contracts:** C04. Accepted merged AR-010-A/P1 plus inherited AR-008-B and C04. Freeze connection-bound claim_generation/require_live_job/reserve inputs, units, finite exceptions, immutable call bindings and bounded SQL before implementation; AR-010-B consumes the fence later and AR-023-A/C own authentic reconciliation evidence.
- **Acceptance criteria:** No cap is exceeded by concurrent reservations or rollover and no logical call is counted twice at one level. Exact repeats retain original project/job/request/purpose/amount/price/account bindings; changes conflict. Refresh database time after waits and validate owner/generation/running/cancel plus immutable execution window; generation advances only on successful claim. Keep balances/call IDs in original periods and include prior outstanding holds in new org/project admission. jobs.reserved remains legacy opening plus gross new reservations; uncertainty never releases exposure or creates new work.
- **Required automated tests:** SQLite and actual PostgreSQL eight-way shared-cap contention and different projects sharing an organization; no-reset rollover with outstanding holds; repeated/conflicting calls, signed-64-bit and 2**53+1 controls; cancellation/generation/window expiry while blocked; every write-stage rollback, lost acknowledgment and physical connection cleanup. Preserve accepted admission, operation GET/cancel behavior and untouched historical rows.
- **Security and reliability:** Keep project(s), organization/grants/key, original scope/job and sorted account ordering; acquire any stronger organization mode before downstream locks. No job-first legacy wrapper or late lock upgrade, no external I/O, float/bool money, invoice inference, implicit mutable settings or automatic paid retry/refund. Overflow or incomplete bounded prior-exposure proof refuses; expired windows retain all existing obligations.
- **Effort / confidence:** 3 engineering days; planning range 3–5; medium-low confidence.
- **Responsible role:** BE; independently reviewed entry and implementation assignment pending. TL/QE and security review; independent actual PostgreSQL proof.
- **Definition of done:** Independent source/security review and matching local/hosted actual PostgreSQL concurrency, finite outcome, preservation, package and recovery evidence establish accepted P2 and the whole aggregate. Both packages and accepted AR-008-B remain mandatory before AR-010-B or integrated M1 claims; no worker/customer/spending activation follows.
- **Progress:** Not started; accepted merge and review evidence are null. No runtime assignment.

<a id="ar-010-b"></a>

#### AR-010-B — Lease-fenced admission permits and cancellation accounting

Tracking: [#96](https://github.com/spei04/agent-rewind/issues/96) · Not started.

- **Objective:** Enforce budget limits before every potentially paid action. This task delivers lease-fenced admission permits and cancellation accounting.
- **Implementation scope / PR boundary:** Deliver two sequential accepted-merge-gated PRs: bounded structured worker-failure persistence, authentic origin and historical-marker/consumer handoff, then live permit/configuration/cancellation and both completion/lease-expiry producer integrations. Require current owner/lease/generation/cancel authority before new paid work or normal completion; expiry uses a database-time conditional transition of the observed generation. Preserve scoped immutable common configuration and historical non-dispatchability.
- **Out of scope:** No distributed study scheduling, automatic paid replay, provider retry/refund without evidence, telemetry/exporter vocabulary, API feature or reverse AR-008-B prerequisite; no production/customer activation or paid validation.
- **Prerequisites:** [AR-010-A](#ar-010-a), [AR-005-C](#ar-005-c). Both packages inherit these prerequisites and wait for the whole accepted AR-010-A, not only its schema P1; E0 applies transitively.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Stale owners, cancelled jobs and DB outages cannot obtain a new permit. Both worker-failure paths persist only reviewed bounded safe Error evidence with authentic originating correlation; polling never invents origin or exposes legacy text. Reconciliation requires evidence; expiry cannot overwrite a newer generation/completion, and operator-only historical markers preserve original rows, audit and ciphertexts.
- **Required automated tests:** CT-M1-009/019/021/022: immutable configuration and stale-token checks, repeated release, DB outage, terminal/cancel races, shared lock ordering, both actual failure producers and bounded parser/native storage, secret canaries and stable stored versus fresh polling correlation, operator-only idempotent markers and historical preservation/restore, atomic rollback/acknowledgment/restart and actual PostgreSQL completion/expiry races.
- **Security and reliability:** No automatic timeout refund, paid replay or guessed failure origin. Use the common C04 project-first hierarchy for permits, publication, cancellation and source mutation; never retain a conflicting job lock while entering project exclusion. Allowlist codes/messages and phase-correct retryability; unknown provider outcome retains its hold. Ordinary completion needs a live worker fence; expiry must conditionally match the observed generation using database time.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium-low confidence.
- **Responsible role:** BE; independent TL and QE review.
- **Definition of done:** Both packages require independent source/security review, matching hosted checks and accepted merged-source evidence in order. Aggregate verification requires actual SQLite/PostgreSQL producer, parser, preservation, lock/race and recovery evidence plus the existing permit/configuration/cancellation matrix. AR-011-C and AR-012-B still consume accepted whole AR-010-B; no early completion or activation follows.
- **Progress:** Not started; neither package is assigned runtime work.
- **Delivery boundary:** Two sequential independently reviewable BE PRs: P1 bounded failure persistence/provenance, historical-marker decision and consumer handoff 2 [2–3] days; P2 permit/configuration/cancellation and both worker producer integrations 2 [2–3] after accepted merged P1. Aggregate 4 [4–6], medium-low; both inherit AR-010-A and AR-005-C.
- **Contract readiness:** Frozen C04 already requires safe stored Error, originating correlation and explicit historical migration markers. AR-010-B owns the missing producer handoff: P1 freezes and implements the chosen version/encoding/native bounds/provenance/parser and marker policy, P2 integrates normal completion and lease expiry. Before code, any required additive DDL needs explicit owner, linear revision, captured catalog, preservation and rollback/restore decisions; reforecast broader work. AR-008-B retains unsupported-evidence 503 until this producer is accepted; no reverse edge, invented envelope or early AR-011-C/AR-012-B acceptance.

<a id="ar-010-b-p1"></a>

#### AR-010-B/P1 — Bounded worker failure persistence and provenance

Tracking: [#97](https://github.com/spei04/agent-rewind/issues/97) · Not started.

- **Objective:** Implement the complete chosen bounded stored-failure representation and consumer handoff before wiring either live worker failure path.
- **Implementation scope:** Freeze version/encoding, allowlisted safe code/message and phase-specific retryability mappings, exact byte/native-type/work bounds, authentic originating correlation and immutable job/operation association. Implement persistence/parser helpers and the bounded AR-008-B consumer extension using original receipts and fresh authority. Define and implement an operator-only idempotent historical migration-marker path that preserves original job rows/bytes, audit, ciphertexts and hash history; a marker never promotes raw legacy text into a trusted Error. Before code, decide whether existing storage suffices; any additive DDL requires explicit migration owner/revision, captured catalogs and preservation/rollback/restore proof within P1, with reforecast if broader.
- **Out of scope:** No live completion/expiry wiring, paid dispatch, guessed schema/version, automatic legacy-text conversion, GET-triggered markers, new Error fields/metrics, history rewrite or production activation.
- **Prerequisites:** [AR-010-A](#ar-010-a), [AR-005-C](#ar-005-c). All aggregate prerequisites remain required; a package is not an early entry exception.
- **Required contracts:** C04. Frozen C04 four-field Error and Operation.error data, original failure versus fresh poll correlation and historical marker; AR-010-A generation/ledger identities, AR-005-C history, accepted AR-008-B bounded Operation adapter and AR-011-B safe vocabulary. ENTRY review must inspect worker.work_once, Database.complete_job, Database.claim, jobs.error String(300) and operations.failure_correlation_id.
- **Acceptance criteria:** Only supported bounded versioned/provenance-checked failure evidence is returned as nested Error, including outcome_uncertain as HTTP 200 data with stable original correlation and a fresh poll header. Unknown provider outcome retains its hold and retryable=false; evaluator false is not a worker failure. Missing/malformed/unsupported evidence remains safe 503. Historical markers are explicit, operator-only, repeat-stable and additive to preserved evidence; neither a poll ID nor an exception string proves origin.
- **Required automated tests:** SQLite and restricted actual PostgreSQL storage/parser vectors for both producer inputs, native type/byte overflow and pre-materialization bounds; all allowlisted mappings and secret canaries; stable original correlation across polls, evaluator false and provider uncertainty; operator authorization, repeated/interrupted marker application, exact old rows/audit/ciphertexts/hash preservation and backup/restore. If DDL is chosen, prove linear upgrade, frozen predecessor profiles, rollback and restart with captured catalog checks.
- **Security and reliability:** Current VARCHAR(300) is a representation constraint, not a complete encoding/provenance fit proof: PostgreSQL rejects overflow while SQLite width is not enforcement, and the current producer does not truncate. Freeze actual canonical size and native bounds before persistence; no raw exception/provider/SQL/source/token payload. No inferred authentic origin, mutable overwrite or client/poll-derived marker. Preserve scoped receipts, visibility/action errors and current authority in the consumer.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; independent TL and QE review.
- **Definition of done:** Independent entry review accepts the complete representation, producer mapping, marker and bounded consumer design before code, including explicit migration ownership/evidence if needed. Implement that chosen P1 boundary and pass SQLite/actual PostgreSQL, package/security and preservation checks at reviewed source; accepted merged P1 is required before P2. Reforecast instead of hiding broader DDL or migration work in P2.
- **Progress:** Not started; accepted_merge_commit and review_evidence remain null.

<a id="ar-010-b-p2"></a>

#### AR-010-B/P2 — Live permit and completion/expiry failure integration

Tracking: [#98](https://github.com/spei04/agent-rewind/issues/98) · Not started.

- **Objective:** Integrate the accepted bounded failure producer with live permits, cancellation and both worker terminal transitions.
- **Implementation scope:** Require scoped immutable common configuration and current generation/cancel authority before dispatch for all newly admitted jobs. Integrate permit/reservation/publication fences and diagnostics without prompt bodies. Route normal worker completion/failure through accepted P1 persistence under a current owner/generation/live-lease fence. Replace the lease-expiry failure producer with a database-time conditional transition of the observed generation under shared project-first exclusion; it must not require an expired worker permit or overwrite a new generation/completion. Persist corresponding outcome/correlation evidence atomically and retain evidence-based cancellation/reconciliation.
- **Out of scope:** No new storage representation or hidden migration decision, historical redispatch, distributed scheduling, automatic paid retry/refund, telemetry expansion, provider cancellation guarantee, customer activation or paid validation.
- **Prerequisites:** [AR-010-A](#ar-010-a), [AR-005-C](#ar-005-c), [AR-010-B/P1](#ar-010-b-p1). All aggregate prerequisites remain required; a package is not an early entry exception.
- **Required contracts:** C04. Accepted merged AR-010-B/P1 plus inherited AR-010-A and AR-005-C; C04 ledger/permit/publication/cancel hierarchy, scoped common configuration and authentic stored Error/origin. Both worker.work_once→Database.complete_job and Database.claim lease-expiry writes must consume the same reviewed persistence contract with distinct fences.
- **Acceptance criteria:** Stale owner/generation, expired normal worker lease, cancellation or DB failure prevents a new permit and stale publication. Conditional expiry affects only the observed still-expired generation and preserves any newer terminal result. Both actual producers commit safe failure/correlation with their intended terminal state; acknowledgment loss stays uncertain without automatic replay/refund. Historical rows remain non-dispatchable; accepted evidence reaches the Operation consumer and later telemetry without invented origin.
- **Required automated tests:** Actual SQLite and PostgreSQL producer paths plus bounded observed races: stale/live owner and generation, worker completion versus DB-time expiry, reclaim/new completion versus stale expiry, simultaneous reservation/publication/cancel, repeated release and DB outage. Inject failure at outcome/correlation/audit/commit boundaries and verify rollback, acknowledgment uncertainty and restart; exercise CT-M1-009/019/021/022 correlation/canary/unknown-hold controls and original history preservation with no paid provider calls.
- **Security and reliability:** Acquire affected project exclusions before organization/grants/target locks according to C04; no job-to-project inversion. Normal completion and expiry have different authority proofs; never require the already-expired worker's live permit for expiry or accept a stale observed generation. Preserve gross reservations and unknown holds, no automatic timeout refund or privileged budget bypass, and no raw errors or prompt bodies in diagnostics.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** BE; independent TL and QE review.
- **Definition of done:** Independent review and matching hosted SQLite/actual PostgreSQL race, atomicity, recovery, package/security and full permit/configuration/cancellation evidence establish accepted merged P2 and aggregate completion. Both packages and all inherited prerequisites must be accepted before AR-011-C or AR-012-B claims integrated producer evidence; full M1/customer/funding gates remain separate.
- **Progress:** Not started; accepted_merge_commit and review_evidence remain null.

**Producer entry checkpoint (planning only, 2026-10-21):** Current worker.work_once passes an exception-class string to Database.complete_job; Database.claim separately writes a fixed lease-expiry failure string. jobs.error is String(300), not a truncating formatter or a versioned Error envelope; operations.failure_correlation_id alone is not failure provenance. Freeze exact representation/version, native size and parser bounds, phase-specific safe mappings, original correlation and operator-only historical-marker storage before code. If additive DDL is required, name its owner and next linear revision, capture reviewed catalogs, and include old-history preservation, interruption/rollback and restore evidence in P1; reforecast broader work rather than hiding it in P2. Preserve original 14 historical rows, audit, 18 ciphertext objects, hash heads and 245000 reservation units. AR-008-B retains its accepted unsupported-evidence 503 until this producer is available; AR-011-C consumes it and AR-012-B verifies it after whole-task acceptance. No status, outer dependency or frozen C04 change follows.

<a id="ar-011"></a>

### AR-011 — Diagnose failures without exposing secrets or losing request context

M1 / P0 · 4 PRs across 3 aggregate tasks · 7 engineering days · In progress · [Tracking issue #11](https://github.com/spei04/agent-rewind/issues/11)

<a id="ar-011-a"></a>

#### AR-011-A — Error, readiness and telemetry contract

- **Objective:** Diagnose failures without exposing secrets or losing request context. This task delivers error, readiness and telemetry contract.
- **Implementation scope / PR boundary:** Specify stable error code/request ID envelope, readiness checks and bounded label vocabulary.
- **Out of scope:** No runtime change; pre-G0 design only.
- **Prerequisites:** [AR-004-A](#ar-004-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Consumer examples distinguish denied, invalid, unavailable and uncertain without revealing internals.
- **Required automated tests:** Validate success/error fixtures and reject high-cardinality secret labels.
- **Security and reliability:** Redaction before logging; never emit source, tokens or raw provider bodies.
- **Effort / confidence:** 1 engineering days; planning range 0.8–1.2; high confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Assigned contributor: Engineer A — error and telemetry contracts.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-011-b"></a>

#### AR-011-B — Safe exception mapping and readiness enforcement

- **Objective:** Diagnose failures without exposing secrets or losing request context. This task delivers safe exception mapping and readiness enforcement.
- **Implementation scope / PR boundary:** Implement redacted boundary handlers and bounded DB/store/schema readiness. Own the installation-only sentinel provisioning command and bounded byte-read primitive: 4096-byte plaintext, capped ciphertext, one-second deadline, one in-flight check and five-second positive cache. AR-009-A consumes the primitive through a separate scoped interface.
- **Out of scope:** No broad observability platform deployment.
- **Prerequisites:** [G0](#g0), [AR-011-A](#ar-011-a), [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Known faults map to stable codes; unknown faults return safe message and correlated restricted diagnostic.
- **Required automated tests:** M1-022/023 secret canaries, malformed exceptions and dependency outage.
- **Security and reliability:** Readiness prevents unsafe admission; liveness does not disclose dependency secrets.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Assigned contributor: Engineer A — safe errors/readiness; Engineer B — independent review.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; [PR #46](https://github.com/spei04/agent-rewind/pull/46) and exact-source internal review/hosted validation accepted. [Evidence and limits](delivery/OWNERSHIP_READINESS_EVIDENCE_2026-10-20.md). Customer admission remains disabled; full M1 is not complete.

<a id="ar-011-c"></a>

#### AR-011-C — Trace propagation and operational counters

- **Objective:** Diagnose failures without exposing secrets or losing request context. This task delivers trace propagation and operational counters.
- **Implementation scope / PR boundary:** Deliver two sequential accepted-merge-gated PRs after all aggregate producers are Verified: bounded trusted correlation and the exact five-metric collector at actual HTTP/readiness boundaries, then worker/queue/provider/recovery integration consuming accepted admission origin persistence and ledger fences.
- **Out of scope:** No admission or worker schema ownership, exporter/network deployment, new metric names or labels, budget amounts, exported drop metric, SLO/paging claim, paid execution, runtime activation or reconstructed origin from client input.
- **Prerequisites:** [AR-011-B](#ar-011-b), [AR-005-C](#ar-005-c), [AR-010-B](#ar-010-b). E0 applies transitively; every package waits for all aggregate prerequisites.
- **Required contracts:** C04; frozen observability vocabulary and producer availability in the contract register.
- **Acceptance criteria:** Trusted persisted origin remains unchanged across retries and polls while each HTTP request has a fresh generated ID; actual HTTP/readiness and worker transitions produce only frozen metric names, labels and values. Bounded local diagnostics retain drop state; full integration evidence cannot be replaced by zero counters or mock-only producer callbacks.
- **Required automated tests:** CT-M1-022/023 correlation continuity, repeated polls/replays, unknown/readiness-cache states, exact metric vocabulary, series and buffer bounds, secret canaries and sink failure; actual accepted worker/queue/provider/recovery transitions distinguish observed, uncertain and rejected outcomes without new retries.
- **Security and reliability:** Telemetry is best effort and locally bounded; it cannot replace fail-closed transactional audit or ledger receipts, trigger retries, expose identifiers as labels or block responses indefinitely. HTTP attempts/replays are not committed-job counts; budget_exhausted is reported only from the actual classified HTTP error.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium-low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named runtime assignee pending prerequisites.
- **Definition of done:** Both packages have independent review, matching checks and accepted merge evidence in order; aggregate acceptance requires actual producer integration, correlation/redaction, bounded collector/drop behavior and failure tests. Freeze observation semantics and resource bounds at the first design checkpoint; no external gate is satisfied.
- **Progress:** Not started; both P1/P2 blocked on AR-010-B. See the [execution plan](delivery/OBSERVABILITY_EXECUTION_PLAN.md); no runtime assignment.

<a id="ar-011-c-p1"></a>

#### AR-011-C/P1 — Bounded correlation and HTTP/readiness telemetry

- **Objective:** Implement bounded trusted correlation and the exact frozen metric collector at actual HTTP and readiness boundaries.
- **Implementation scope:** Implement trusted request/correlation helpers, the five-metric collector, actual HTTP/readiness observations and bounded local diagnostic/drop state. Freeze observation points, readiness cache/unknown semantics, histogram buckets, buffer limits and installation-level series limits at the first design checkpoint.
- **Out of scope:** No early start before AR-010-B, durable-origin schema, worker integration claim, network exporter, new metric/label vocabulary, budget amounts or paid calls.
- **Prerequisites:** [AR-011-B](#ar-011-b), [AR-005-C](#ar-005-c), [AR-010-B](#ar-010-b). Accepted merged predecessor evidence is mandatory.
- **Required contracts:** C04. C04 observability.contract.json and ERROR_READINESS_TELEMETRY.md; accepted AR-011-B boundary/readiness and AR-005-C compatibility; all aggregate producer prerequisites including AR-010-B.
- **Acceptance criteria:** Fresh generated HTTP IDs remain distinct from write-once persisted origin; HTTP attempts and replays count HTTP observations rather than committed jobs. Readiness observations distinguish fresh, cached and unknown evidence under the frozen semantics. Sink failure is bounded and observable locally without replacing required audit.
- **Required automated tests:** Actual HTTP success/error/replay and readiness transition tests; exact five-metric names and finite label values; bounded cardinality/buffers, local drop state, secret canaries and failing-sink behavior; fresh request versus original correlation separation.
- **Security and reliability:** No raw request/body/exception/customer fields or identifiers in labels; no automatic exporter/network or retry. Required audit/ledger failure still follows its fail-closed owner contract; zero-valued worker counters do not establish worker coverage.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** PL; independent SEC/QE review; named runtime assignee pending prerequisite acceptance.
- **Definition of done:** Independent review and matching checks verify actual HTTP/readiness behavior and frozen resource/observation semantics; accepted merged-source evidence is required before P2. Aggregate remains unverified.
- **Progress:** Not started; every aggregate producer and accepted-merge prerequisite remains mandatory.

<a id="ar-011-c-p2"></a>

#### AR-011-C/P2 — Worker and durable-origin integration evidence

- **Objective:** Connect bounded telemetry to accepted durable admission and worker transitions.
- **Implementation scope:** Consume accepted AR-008-A/B trusted origin persistence and AR-010-B worker/ledger fences for actual queue, provider and recovery observations. Preserve original operation/job origin on retry while poll/request IDs remain fresh; reuse the accepted P1 collector and diagnostics.
- **Out of scope:** No duplicate admission/ledger DDL, change to dispatch/fencing/receipt authority, new exporter or labels, budget amount reporting, provider retry policy, paid execution or customer activation.
- **Prerequisites:** [AR-011-C/P1](#ar-011-c-p1). Accepted merged predecessor evidence is mandatory.
- **Required contracts:** C04. Accepted P1; C04 trusted failure_correlation_id from AR-008-A/B and queue/ledger/worker authority from AR-010-B; frozen call_outcome values observed/uncertain/rejected and exact five metrics.
- **Acceptance criteria:** Actual producer paths preserve origin and distinguish provider outcomes observed, uncertain and rejected. HTTP attempts/replays remain separate from job commits; budget_exhausted appears only for an actual classified HTTP error. Recovery and diagnostic loss cannot change money, admission, retries or fail-closed audit behavior.
- **Required automated tests:** Actual synthetic queue/provider/ledger transition and recovery evidence using accepted producer interfaces; uncertain/rejected/observed outcomes, correlation across retry/polls, committed identity preservation, diagnostic saturation/drop and audit/ledger failures. Mock-only collector or zero-counter evidence cannot satisfy integration.
- **Security and reliability:** No telemetry-triggered retry or refund; no raw provider response, credential, payload or ID labels. Durable origin and ledger truth stay with their producers; best-effort diagnostics cannot acknowledge a missing audit or receipt.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium-low confidence.
- **Responsible role:** PL; independent SEC/QE review; named runtime assignee pending prerequisite acceptance.
- **Definition of done:** Independent review, matching checks and accepted merge establish actual producer integration and the full bounded/redacted evidence matrix; aggregate completion requires both packages. AR-012-B performs downstream foundation acceptance without a reverse edge.
- **Progress:** Not started; every aggregate producer and accepted-merge prerequisite remains mandatory.

<a id="ar-012"></a>

### AR-012 — Detect incompatible or unsafe foundation changes before integration

M1 / P0 · 2 PRs · 5 engineering days · In progress · [Tracking issue #12](https://github.com/spei04/agent-rewind/issues/12)

<a id="ar-012-a"></a>

#### AR-012-A — Proposed contract fixture validation harness

- **Objective:** Detect incompatible or unsafe foundation changes before integration. This task delivers proposed contract fixture validation harness.
- **Implementation scope / PR boundary:** Add structural checks for OpenAPI/schema/acceptance links and baseline fixtures without runtime behavior claims.
- **Out of scope:** No claim that planned acceptance cases are implemented.
- **Prerequisites:** [AR-004-A](#ar-004-a), [AR-005-A](#ar-005-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Malformed refs, duplicate IDs and missing contract mappings fail with actionable diagnostics.
- **Required automated tests:** Deliberately broken contract fixtures rejected; current proposed set accepted.
- **Security and reliability:** Fixtures remain synthetic and approval status stays pending.
- **Effort / confidence:** 2 engineering days; planning range 1.6–2.4; high confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Assigned contributor: Engineer C — quality/contract integration.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; current assignment, checks and review in [ASSIGNMENTS.md](ASSIGNMENTS.md).

<a id="ar-012-b"></a>

#### AR-012-B — Integrated M1 concurrency and compatibility gate

- **Objective:** Detect incompatible or unsafe foundation changes before integration. This task delivers integrated m1 concurrency and compatibility gate.
- **Implementation scope / PR boundary:** Wire PostgreSQL/object-backed required checks for all 24 M1 cases and upgrade/legacy compatibility; independently validate AR-006-C live stale-projection repair and restricted audit integration; verify the deferred v1, durable replay and common-config consumer obligations from AR-007-C against their actual producers; preparatory route subsets do not satisfy all CT-M1-007/008/009 cases.
- **Out of scope:** No benchmark capacity or enterprise readiness declaration.
- **Prerequisites:** [AR-006-B](#ar-006-b), [AR-006-C](#ar-006-c), [AR-008-B](#ar-008-b), [AR-009-B](#ar-009-b), [AR-010-B](#ar-010-b), [AR-011-C](#ar-011-c), [AR-012-A](#ar-012-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register. C04 reviewed for development/testing at source 22c4376 and G0 recorded. Other contracts require their listed producers and task-specific gates; no runtime or production acceptance is implied.
- **Acceptance criteria:** G1 evidence records commit, runtime and every pass/fail; no fixture-only substitute for concurrency tests.
- **Required automated tests:** Execute all M1 cases plus old-reader compatibility and fail-closed startup; actual generation/cancel races and atomic idempotent repair/audit under PostgreSQL; mixed admission/publication/cancellation and overlapping parent/child operations verify the common account/project/job lock order.
- **Security and reliability:** Tests isolate projects and contain no real model credentials.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-013"></a>

### AR-013 — Execute untrusted code within an accountable Linux sandbox boundary

M2 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-013-a"></a>

#### AR-013-A — Pinned worker image and sandbox launch profile

- **Objective:** Execute untrusted code within an accountable Linux sandbox boundary. This task delivers pinned worker image and sandbox launch profile.
- **Implementation scope / PR boundary:** Build pinned Linux worker image with runsc, UID/resource limits, read-only base and offline sandbox network.
- **Out of scope:** No Kubernetes or arbitrary customer images.
- **Prerequisites:** [AR-009-B](#ar-009-b), [AR-011-C](#ar-011-c), [AR-033-A](#ar-033-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C03, C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Image identity and preflight reject missing runsc or insecure production profile.
- **Required automated tests:** Linux CI runtime selection, UID, filesystem and network denial tests.
- **Security and reliability:** No privileged host socket mounted into sandbox; model egress only trusted worker.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-013-b"></a>

#### AR-013-B — Runtime resource ownership and cleanup

- **Objective:** Execute untrusted code within an accountable Linux sandbox boundary. This task delivers runtime resource ownership and cleanup.
- **Implementation scope / PR boundary:** Tag every container/workspace with attempt owner and lease; reconcile abandoned resources with bounded cleanup.
- **Out of scope:** No trial coordinator or process-memory snapshots.
- **Prerequisites:** [AR-013-A](#ar-013-a), [AR-033-B](#ar-033-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Normal exit, worker kill and stale resource sweeps leave no active orphan outside grace policy.
- **Required automated tests:** Kill worker before/after launch, cleanup repeat and foreign-owner resource tests.
- **Security and reliability:** Cleanup cannot delete resources owned by another valid attempt.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-013-c"></a>

#### AR-013-C — Adversarial gVisor isolation matrix

- **Objective:** Execute untrusted code within an accountable Linux sandbox boundary. This task delivers adversarial gvisor isolation matrix.
- **Implementation scope / PR boundary:** Exercise production worker profile against fork/output/disk bombs, forbidden mounts, metadata and credential access.
- **Out of scope:** No claim that sandbox testing proves absence of escapes.
- **Prerequisites:** [AR-013-B](#ar-013-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C03, C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** All mandatory denial/resource limits pass on reference worker; unsupported workload list explicit.
- **Required automated tests:** Real runsc tests, cgroup limits, deadline cleanup and network/metadata probes.
- **Security and reliability:** Failure blocks production execution; do not fall back silently to runc.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-014"></a>

### AR-014 — Restore only supported state and explain why a checkpoint cannot branch

M2 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-014-a"></a>

#### AR-014-A — Adapter and checkpoint manifest contract

- **Objective:** Restore only supported state and explain why a checkpoint cannot branch. This task delivers adapter and checkpoint manifest contract.
- **Implementation scope / PR boundary:** Specify capability negotiation, serialized state version, image/tool identities, path policy and hash manifest.
- **Out of scope:** No second adapter implementation.
- **Prerequisites:** [AR-006-B](#ar-006-b), [AR-012-B](#ar-012-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Unsupported process/external state rejected before branch; native adapter fixtures reviewed by RS/PL.
- **Required automated tests:** Manifest schema, capability mismatch, missing image/state and malicious paths.
- **Security and reliability:** Only tool-boundary state; no credential or private environment capture.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-014-b"></a>

#### AR-014-B — Restoration preflight and native adapter compatibility

- **Objective:** Restore only supported state and explain why a checkpoint cannot branch. This task delivers restoration preflight and native adapter compatibility.
- **Implementation scope / PR boundary:** Implement preflight and native adapter restore against versioned manifest and immutable source.
- **Out of scope:** No filesystem memory mapping or external service rollback.
- **Prerequisites:** [AR-014-A](#ar-014-a), [AR-009-B](#ar-009-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Missing/corrupt/incompatible state blocks branch with actionable reason; source remains unchanged.
- **Required automated tests:** Binary/Unicode files, symlinks, permissions, image mismatch and legacy snapshot fixtures.
- **Security and reliability:** Reject traversal/special devices; bounded extraction; no host file access.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-014-c"></a>

#### AR-014-C — Branch boundary restoration conformance

- **Objective:** Restore only supported state and explain why a checkpoint cannot branch. This task delivers branch boundary restoration conformance.
- **Implementation scope / PR boundary:** Verify action substitution and observed-tool-result substitution from identical parent checkpoints.
- **Out of scope:** No statistical effect claim from one branch.
- **Prerequisites:** [AR-014-B](#ar-014-b), [AR-013-C](#ar-013-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Parent hash never changes; actual filesystem effects and observed result are distinct in recorded evidence.
- **Required automated tests:** Read/write/action/finish branches, interrupted checkpoint, altered observation and negative replay cases.
- **Security and reliability:** Independent evaluator runs fresh; no leaked evaluator state in continuation.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-015"></a>

### AR-015 — Keep artifact memory, disk and restore latency within admitted bounds

M2 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-015-a"></a>

#### AR-015-A — Streaming object IO with explicit bounds

- **Objective:** Keep artifact memory, disk and restore latency within admitted bounds. This task delivers streaming object io with explicit bounds.
- **Implementation scope / PR boundary:** Stream encrypted artifact reads/writes with max bytes/file count, digest verification and cancellation.
- **Out of scope:** No cross-project cache or GC.
- **Prerequisites:** [AR-009-B](#ar-009-b), [AR-013-A](#ar-013-a), [AR-014-A](#ar-014-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04, C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Oversized/truncated/corrupt objects fail before publication without unbounded memory.
- **Required automated tests:** Memory bound, partial stream, timeout, cancel and checksum failures.
- **Security and reliability:** Per-project quotas; no decompression bomb or key material in temp files.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-015-b"></a>

#### AR-015-B — Scoped immutable cache and eviction

- **Objective:** Keep artifact memory, disk and restore latency within admitted bounds. This task delivers scoped immutable cache and eviction.
- **Implementation scope / PR boundary:** Add content cache keyed by project, format and verified digest with bounded eviction.
- **Out of scope:** No shared remote cache service.
- **Prerequisites:** [AR-015-A](#ar-015-a), [AR-014-A](#ar-014-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Cache hit equals uncached content; failed verification never reusable; owner change denies access.
- **Required automated tests:** Concurrent readers/eviction, corruption, disk pressure and project isolation.
- **Security and reliability:** No mutable hard links or unauthorized hash probes.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-015-c"></a>

#### AR-015-C — Snapshot capacity and restore benchmark

- **Objective:** Keep artifact memory, disk and restore latency within admitted bounds. This task delivers snapshot capacity and restore benchmark.
- **Implementation scope / PR boundary:** Measure plan baseline/forecast file counts and byte distributions, cache cold/warm restore and cleanup.
- **Out of scope:** No extrapolated fleet scale or universal replay latency promise.
- **Prerequisites:** [AR-015-B](#ar-015-b), [AR-014-C](#ar-014-c), [AR-033-B](#ar-033-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Report measured p50/p95, memory/disk ceilings and admitted size limits with reproducible fixtures.
- **Required automated tests:** Automated benchmark assertions on configured limits plus deliberately oversized workload.
- **Security and reliability:** Synthetic repositories only; baseline tied to hardware/image identity.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-016"></a>

### AR-016 — Protect cloud evidence and credentials throughout key and storage lifecycles

M2 / P0 · 4 PRs · 11 engineering days · In progress

<a id="ar-016-a"></a>

#### AR-016-A — Envelope encryption and cloud credential contract

- **Objective:** Protect cloud evidence and credentials throughout key and storage lifecycles. This task delivers envelope encryption and cloud credential contract.
- **Implementation scope / PR boundary:** Define object key/version envelope, legacy read path, workload identity and key lifecycle states.
- **Out of scope:** No cloud resource creation.
- **Prerequisites:** [AR-009-B](#ar-009-b), [AR-003-B](#ar-003-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C07; definitions and producer availability in the contract register.
- **Acceptance criteria:** PL/SEC review explicit encrypt/decrypt authorization, old-key retention and fail-closed behavior.
- **Required automated tests:** Envelope schema, unknown key, denied decrypt and legacy format fixtures.
- **Security and reliability:** No plaintext master key in DB or sandbox; use scoped runtime identity.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Execution assigned to engineer A; named human staffing remains unconfirmed.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified for offline C07 design after accepted PR #102 merge 2bb75695, matching PR/main checks and independently verified candidate 12341062437. Runtime format-2, live KMS/IAM and external gates remain open.
- **Tracking:** https://github.com/spei04/agent-rewind/issues/99

<a id="ar-016-b"></a>

#### AR-016-B — KMS envelope implementation and secret delivery

- **Objective:** Protect cloud evidence and credentials throughout key and storage lifecycles. This task delivers kms envelope implementation and secret delivery.
- **Implementation scope / PR boundary:** Implement wrapping/unwrapping and trusted-worker secret retrieval with bounded in-memory lifetime.
- **Out of scope:** No unattended key deletion.
- **Prerequisites:** [AR-016-A](#ar-016-a), [AR-033-B](#ar-033-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C07, C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Current and legacy objects read under allowed identity; disabled/revoked key gives safe error.
- **Required automated tests:** Real staging KMS deny/rotate, unavailable secret service and provider credential canaries.
- **Security and reliability:** Restrict decrypt to required objects; no secret in artifacts/logs.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-016-c"></a>

#### AR-016-C — Native GCS artifact backend and consistency conformance

- **Objective:** Protect cloud evidence and credentials throughout key and storage lifecycles. This task delivers native gcs artifact backend and consistency conformance.
- **Implementation scope / PR boundary:** Implement native Cloud Storage adapter with conditional immutable writes, bounded reads and object metadata validation.
- **Out of scope:** No S3 compatibility assumption or second cloud.
- **Prerequisites:** [AR-016-A](#ar-016-a), [AR-033-B](#ar-033-b), [AR-015-A](#ar-015-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04, C07, C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Storage conformance suite passes against real private bucket; concurrent writes preserve immutable content.
- **Required automated tests:** Upload timeout, generation conflict, IAM denial, corruption and deleted object tests.
- **Security and reliability:** Use workload identity; private bucket; no public signed access path.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-016-d"></a>

#### AR-016-D — Key rotation and retained-object recovery rehearsal

- **Objective:** Protect cloud evidence and credentials throughout key and storage lifecycles. This task delivers key rotation and retained-object recovery rehearsal.
- **Implementation scope / PR boundary:** Exercise new writes on new key, historical reads, interrupted rotation and restore with retained keys.
- **Out of scope:** No legal assurance or permanent key destruction.
- **Prerequisites:** [AR-016-B](#ar-016-b), [AR-016-C](#ar-016-c), [AR-015-B](#ar-015-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C07; definitions and producer availability in the contract register.
- **Acceptance criteria:** Old/new ciphertext readable only by intended principals; rollback procedure does not orphan evidence.
- **Required automated tests:** Partial rotation, old-key disable/re-enable, backup restore and cache invalidation tests.
- **Security and reliability:** Deletion blocked while retained object/backups require key; record operator approval.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-017"></a>

### AR-017 — Prevent stale workers from dispatching new work or publishing invalid evidence

M2 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-017-a"></a>

#### AR-017-A — Heartbeat failure and stale-owner dispatch fence

- **Objective:** Prevent stale workers from dispatching new work or publishing invalid evidence. This task delivers heartbeat failure and stale-owner dispatch fence.
- **Implementation scope / PR boundary:** Make heartbeat DB errors cancel local execution; require owner/generation checks before new call and publish.
- **Out of scope:** No provider exactly-once guarantee.
- **Prerequisites:** [AR-010-B](#ar-010-b), [AR-013-B](#ar-013-b), [AR-014-B](#ar-014-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Expired/lost lease stops new dispatch and result publication even when old worker resumes.
- **Required automated tests:** Pause/kill heartbeat, DB outage, owner takeover and stale completion races.
- **Security and reliability:** Do not treat running remote call as cancelled; mark unknown outcome conservatively.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-017-b"></a>

#### AR-017-B — Checkpoint commit and orphan-attempt recovery

- **Objective:** Prevent stale workers from dispatching new work or publishing invalid evidence. This task delivers checkpoint commit and orphan-attempt recovery.
- **Implementation scope / PR boundary:** Publish complete checkpoint metadata only after artifact verification and fenced transaction; retain incomplete diagnostics.
- **Out of scope:** No distributed study phase scheduling.
- **Prerequisites:** [AR-017-A](#ar-017-a), [AR-014-C](#ar-014-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Crash cannot expose partial branchable checkpoint; recovery preserves immutable parent.
- **Required automated tests:** Crash at upload/commit/publish, lost acknowledgment and repeated recovery tests.
- **Security and reliability:** Partial data quarantined; no automatic replay of potentially dispatched paid call.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-017-c"></a>

#### AR-017-C — Execution cancellation and fault matrix

- **Objective:** Prevent stale workers from dispatching new work or publishing invalid evidence. This task delivers execution cancellation and fault matrix.
- **Implementation scope / PR boundary:** Automate cancellation at queued, sandbox, provider-wait and publication boundaries with resource inventory.
- **Out of scope:** No production chaos on customer data.
- **Prerequisites:** [AR-017-B](#ar-017-b), [AR-013-C](#ar-013-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Cancelled work cannot reserve/publish new effect; residual provider charge stays visible.
- **Required automated tests:** Race permutations, job deadline, worker restart and cleanup audit.
- **Security and reliability:** No silent refund or stale-owner success; bounded wait for local termination.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-018"></a>

### AR-018 — Keep candidate behavior from corrupting the independent success criterion

M2 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-018-a"></a>

#### AR-018-A — Evaluator protocol and adversarial fixture suite

- **Objective:** Keep candidate behavior from corrupting the independent success criterion. This task delivers evaluator protocol and adversarial fixture suite.
- **Implementation scope / PR boundary:** Specify independent grader launch, immutable hidden inputs, timeout and invalid-result taxonomy.
- **Out of scope:** No subjective LLM-only success grading.
- **Prerequisites:** [AR-002-B](#ar-002-b), [AR-013-A](#ar-013-a), [AR-014-A](#ar-014-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02, C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Candidate cannot change evaluator inputs or pass through malformed/missing output.
- **Required automated tests:** Golden true/false/invalid grades; candidate writes evaluator paths and spoofs outputs.
- **Security and reliability:** Grader fresh sandbox and distinct files; no secrets as test answers.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-018-b"></a>

#### AR-018-B — Evaluator isolation and flake quarantine

- **Objective:** Keep candidate behavior from corrupting the independent success criterion. This task delivers evaluator isolation and flake quarantine.
- **Implementation scope / PR boundary:** Implement fresh evaluation run, explicit invalid/timeout/flake records and quarantine policy.
- **Out of scope:** No automatic evaluator repair or hidden retries.
- **Prerequisites:** [AR-018-A](#ar-018-a), [AR-013-C](#ar-013-c), [AR-014-B](#ar-014-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02, C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Flaky or compromised evaluator never yields confident success label; repeats identified.
- **Required automated tests:** State leakage, grader crash, malicious candidate and unstable-grade regression tests.
- **Security and reliability:** No deletion of inconvenient outcomes; separate candidate and grader privileges.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-018-c"></a>

#### AR-018-C — Independent evaluator attack review

- **Objective:** Keep candidate behavior from corrupting the independent success criterion. This task delivers independent evaluator attack review.
- **Implementation scope / PR boundary:** Run adversarial test pack and record gaps with security/research review.
- **Out of scope:** No certification or unbounded red-team engagement.
- **Prerequisites:** [AR-018-B](#ar-018-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02; definitions and producer availability in the contract register.
- **Acceptance criteria:** All release-blocking evaluator escapes fixed or workload denied; claims bounded.
- **Required automated tests:** Replay malicious fixtures plus grader reproducibility suite in reference environment.
- **Security and reliability:** Do not let same developer's self-review satisfy independent review.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-019"></a>

### AR-019 — Verify integrated execution and recovery with reproducible fault evidence

M2 / P0 · 3 PRs · 8 engineering days · Not started

<a id="ar-019-a"></a>

#### AR-019-A — Integrated runtime failure harness

- **Objective:** Verify integrated execution and recovery with reproducible fault evidence. This task delivers integrated runtime failure harness.
- **Implementation scope / PR boundary:** Compose DB/object/worker fault controls and verify checkpoints, resources, budget holds and trace linkage.
- **Out of scope:** No customer environment disruption.
- **Prerequisites:** [AR-015-C](#ar-015-c), [AR-016-D](#ar-016-d), [AR-017-C](#ar-017-c), [AR-018-C](#ar-018-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C07; definitions and producer availability in the contract register.
- **Acceptance criteria:** Same scenario repeatable with safe synthetic inputs; every fault has expected terminal/uncertain state.
- **Required automated tests:** Linux gVisor crash grid and artifact/lease invariants across process restarts.
- **Security and reliability:** Fault injection isolated to staging with explicit resource labels.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-019-b"></a>

#### AR-019-B — Bounded live-provider restore smoke test

- **Objective:** Verify integrated execution and recovery with reproducible fault evidence. This task delivers bounded live-provider restore smoke test.
- **Implementation scope / PR boundary:** Run one predeclared native-agent failed run and branches on gVisor with model/runtime/usage receipts.
- **Out of scope:** No natural-failure or statistically reliable effect claim.
- **Prerequisites:** [AR-019-A](#ar-019-a), [PAID0](#paid0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C02; definitions and producer availability in the contract register.
- **Acceptance criteria:** Captured checkpoint restores and independent evaluator checks branches; any failed/unknown result reported.
- **Required automated tests:** Automated transcript/receipt/hash checks; provider failure path tested with fake transport first.
- **Security and reliability:** Use reconciled remaining authorization cap; never expose credential or spend without permit.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-019-c"></a>

#### AR-019-C — G2 runtime evidence and operational handoff

- **Objective:** Verify integrated execution and recovery with reproducible fault evidence. This task delivers g2 runtime evidence and operational handoff.
- **Implementation scope / PR boundary:** Assemble runtime inventory, isolation/restore/fault results and supported limitations.
- **Out of scope:** No declaration of enterprise readiness.
- **Prerequisites:** [AR-019-B](#ar-019-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C07; definitions and producer availability in the contract register.
- **Acceptance criteria:** PL, QE, SEC accept required tests; any mandatory failure keeps G2 open.
- **Required automated tests:** Evidence manifest completeness and independent rerun of representative restoration.
- **Security and reliability:** Store sensitive evidence privately with commit, operator and retention date.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-020"></a>

### AR-020 — Give every study, logical trial and attempt a durable scoped identity

M3 / P0 · 3 PRs · 11 engineering days · Not started

<a id="ar-020-a"></a>

#### AR-020-A — Study, pair, trial and attempt contract

- **Tracking issue:** [#57](https://github.com/spei04/agent-rewind/issues/57); blocked until the prerequisites below are accepted.

- **Objective:** Give every study, logical trial and attempt a durable scoped identity. This task delivers study, pair, trial and attempt contract.
- **Implementation scope / PR boundary:** Freeze logical identities, protocol digests, immutable freeze and attempt/uncertain states; specify study API needs; extend the M1 org/project/job ledger with study-scoped accounts and bind every child attempt/call to its study cap. Approved RB-01 addition: Add proposed identities, allowed-observation references, physical/comparison cost ledgers and reserved-confirmation transitions to the original C08 producer's schema/fixtures.
- **Out of scope:** No coordinator or estimators. No database implementation or provider dispatch.
- **Prerequisites:** [AR-012-B](#ar-012-b), [AR-010-B](#ar-010-b), [AR-002-B](#ar-002-b), [RA-01-B](#ra-01-b), [RESEARCHSCOPE0](#researchscope0). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08, C21, C02, C04, C20; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** RS/QE approve unique outcome rules, missingness and coordinator transition table. Producer review accepts same-study identity closure and immutable phase/price/resource fields; a schema fixture cannot mark C08 available.
- **Required automated tests:** Schema/transition fixtures reject duplicate logical arm and changed frozen candidate; Reject cross-study calls, missing price bounds, reused phase attempts and changed policy digests.
- **Security and reliability:** Separate attempt diagnostics from immutable analytical outcomes. No source/secret bodies in receipts; uncertain dispatch keeps holds.
- **Effort / confidence:** 3 engineering days; planning range 3–4; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-020-b"></a>

#### AR-020-B — Trial schema and repository migration

- **Tracking issue:** [#58](https://github.com/spei04/agent-rewind/issues/58); blocked until the prerequisites below are accepted.

- **Objective:** Give every study, logical trial and attempt a durable scoped identity. This task delivers trial schema and repository migration.
- **Implementation scope / PR boundary:** Add normalized studies/pairs/trials/attempts and scoped repositories with fenced updates; migrate study budget accounts and enforce same-project study/job/call relationships. RB-02 primitive layer: normalized reserve-to-held transitions and separate unique physical invoices/shared-input attribution under study/method/task closure. This schema acceptance does not establish the complete accounting invariant; AR-023-C owns end-to-end settlement/reconciliation evidence.
- **Out of scope:** No fanout dispatch
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-005-C](#ar-005-c). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Uniqueness persists under concurrent inserts; all foreign-project relations rejected
- **Required automated tests:** Upgrade legacy study fixture, FK closure, concurrent insert and stale-attempt tests; PostgreSQL competing protected-reserve transitions and shared-input attribution closure
- **Security and reliability:** Preserve historical report interpretation; bounded backfill with explicit version
- **Effort / confidence:** 4 engineering days; planning range 4–7; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-020-c"></a>

#### AR-020-C — Study lifecycle commands and frozen protocol enforcement

- **Objective:** Give every study, logical trial and attempt a durable scoped identity. This task delivers study lifecycle commands and frozen protocol enforcement.
- **Implementation scope / PR boundary:** Implement create, freeze, cancel and status service commands with immutable plan digest and audit.
- **Out of scope:** No public study API yet.
- **Prerequisites:** [AR-020-B](#ar-020-b), [AR-007-C](#ar-007-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Cannot alter candidate, estimator, sample plan or evaluator after freeze; cancelled remains visible.
- **Required automated tests:** State transition matrix, double-freeze, unauthorized cancel and ambiguous prior outcomes.
- **Security and reliability:** No confirmation access during discovery; all changes attributed.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-021"></a>

### AR-021 — Resume studies without silently repeating paid work or changing the protocol

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-021-a"></a>

#### AR-021-A — Durable coordinator phase machine

- **Tracking issue:** [#61](https://github.com/spei04/agent-rewind/issues/61); blocked until the prerequisites below are accepted.

- **Objective:** Resume studies without silently repeating paid work or changing the protocol. This task delivers durable coordinator phase machine.
- **Implementation scope / PR boundary:** Persist discovery/freeze/confirmation/publication phases and resumable work intents. Approved RB-03 addition: Add frozen task-local policy state, receipt manifests and confirmation access barriers to the existing coordinator; independent execution generations cannot reuse analytical attempts.
- **Out of scope:** No autoscaling or cross-region active-active. No cross-task adaptive allocation, new estimator or changed confirmation sample size.
- **Prerequisites:** [AR-020-C](#ar-020-c), [AR-014-C](#ar-014-c), [AR-023-C](#ar-023-c). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08, C06; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Completed arms not rerun after coordinator restart; no next-phase dispatch before barrier. Only designated discovery receipts are visible; one candidate/task freezes once; confirmation stays sealed until its fixed plan completes or invalidates.
- **Required automated tests:** Restart at each intent/commit boundary and duplicate coordinator claim tests; Crash/restart at freeze, confirmation-to-discovery leakage, task-state sharing, stale generation and partial-confirmation negatives.
- **Security and reliability:** Explicit generation fencing; no implicit paid retries. Unknown calls remain held; operational abort is explicit inconclusive, not early success.
- **Effort / confidence:** 4 engineering days; planning range 4–7; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-021-b"></a>

#### AR-021-B — Recovery, retries and terminal missingness

- **Objective:** Resume studies without silently repeating paid work or changing the protocol. This task delivers recovery, retries and terminal missingness.
- **Implementation scope / PR boundary:** Recover coordinator after worker/provider uncertainty using ledger status; retry only provably undispatched work.
- **Out of scope:** No guessing remote completion from timeout.
- **Prerequisites:** [AR-021-A](#ar-021-a), [AR-023-B](#ar-023-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Unknown dispatch stays unresolved/invalid per protocol; outcome denominator preserved.
- **Required automated tests:** Lost response, expired lease, duplicate callback and exhaustion fixtures.
- **Security and reliability:** Budget remains conservative; operator actions audited.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-021-c"></a>

#### AR-021-C — Coordinator state explorer and recovery regression suite

- **Objective:** Resume studies without silently repeating paid work or changing the protocol. This task delivers coordinator state explorer and recovery regression suite.
- **Implementation scope / PR boundary:** Build bounded state exploration for cancellation/crash ordering and publish reproducible failing traces.
- **Out of scope:** No formal proof of all distributed executions.
- **Prerequisites:** [AR-021-B](#ar-021-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** No duplicate logical outcome or protocol mutation across enumerated valid interleavings.
- **Required automated tests:** Model-based transition tests plus PostgreSQL multi-process crash tests.
- **Security and reliability:** Test evidence redacted; seeds recorded for reproduction.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-022"></a>

### AR-022 — Run trials concurrently without starvation, budget bypass or phase leakage

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-022-a"></a>

#### AR-022-A — Fair admission and concurrency permits

- **Objective:** Run trials concurrently without starvation, budget bypass or phase leakage. This task delivers fair admission and concurrency permits.
- **Implementation scope / PR boundary:** Implement per-project/study worker slots, bounded pending queue and weighted fair scheduling.
- **Out of scope:** No Kubernetes scaler or custom queue service.
- **Prerequisites:** [AR-021-A](#ar-021-a), [AR-017-C](#ar-017-c), [AR-020-C](#ar-020-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** One saturated project cannot starve admitted peers; permits released only by fenced transition; all child reservations atomically enforce study, job, project and organization caps.
- **Required automated tests:** Concurrent acquisition, crash reclaim, saturation and budget exhaustion; parallel child jobs exhausting one study cap cannot overspend it.
- **Security and reliability:** Caps enforced server-side; prevent priority privilege escalation.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-022-b"></a>

#### AR-022-B — Multi-worker execution and cancellation barriers

- **Objective:** Run trials concurrently without starvation, budget bypass or phase leakage. This task delivers multi-worker execution and cancellation barriers.
- **Implementation scope / PR boundary:** Dispatch independent trials to trusted workers and join frozen arm counts under cancel/retry.
- **Out of scope:** No same-seed deterministic model guarantee.
- **Prerequisites:** [AR-022-A](#ar-022-a), [AR-021-C](#ar-021-c), [AR-023-C](#ar-023-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Parallel run matches serial logical result set; no confirmation leak or duplicate completion.
- **Required automated tests:** Multi-worker races, out-of-order results, partial cancel and coordinator restart.
- **Security and reliability:** Leases and budget permit precede each attempt; missing results explicit.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-022-c"></a>

#### AR-022-C — Fairness and phase-boundary integration checkpoint

- **Objective:** Run trials concurrently without starvation, budget bypass or phase leakage. This task delivers fairness and phase-boundary integration checkpoint.
- **Implementation scope / PR boundary:** Run two-project mixed-duration workload and verify fairness, bounded queue and phase integrity.
- **Out of scope:** No forecast-scale soak claim.
- **Prerequisites:** [AR-022-B](#ar-022-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Measured wait/resource bounds satisfy admitted workload contract; no starvation in configured stress suite.
- **Required automated tests:** Long/short task mix, worker loss and repeated cancel/load tests.
- **Security and reliability:** Overload sheds work predictably instead of consuming unbounded resources.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-023"></a>

### AR-023 — Account for every provider call and preserve uncertainty until reconciled

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-023-a"></a>

#### AR-023-A — Provider receipt and reconciliation interface

- **Objective:** Account for every provider call and preserve uncertainty until reconciled. This task delivers provider receipt and reconciliation interface.
- **Implementation scope / PR boundary:** Specify call identity, request/price hash, observed usage, remote ID and evidence-based resolution rules. Specify authentic, bounded non-call-owned evidence and provenance for historical opening-hold adjustments and actual account/period transfers before those paths activate; do not fabricate provider calls to fit the current call-owned budget_evidence role.
- **Out of scope:** No provider retry implementation.
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-010-B](#ar-010-b), [AR-017-A](#ar-017-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Continuation and proposal calls use same accounting vocabulary; ambiguity never equals refund. The chosen evidence representation distinguishes imported openings and real transfers from invoices, retains original identity/exposure and rejects unsupported or contradictory adjustment authority.
- **Required automated tests:** Receipt schema, conflicting duplicate and unverifiable reconciliation fixtures. Historical-opening and transfer evidence/provenance, duplicate/conflicting adjustment identities and unsupported call-owned-evidence negatives.
- **Security and reliability:** Receipt excludes prompt/secret; restricted operator reconciliation authority. No fake call, guessed receipt or invented transfer table; freeze the durable evidence/consumer contract before implementation and preserve existing C04 obligations.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-023-b"></a>

#### AR-023-B — Dispatch receipts and uncertain-call journal

- **Tracking issue:** [#59](https://github.com/spei04/agent-rewind/issues/59); blocked until the prerequisites below are accepted.

- **Objective:** Account for every provider call and preserve uncertainty until reconciled. This task delivers dispatch receipts and uncertain-call journal.
- **Implementation scope / PR boundary:** Record dispatch intent before network and observed response after; route discovery and continuation through ledger.
- **Out of scope:** No invoice truth inferred from token estimate.
- **Prerequisites:** [AR-023-A](#ar-023-a), [AR-020-B](#ar-020-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Every paid call has reservation and receipt or explicit unknown; no orphan proposal spend.
- **Required automated tests:** Crash before send/after send/before persist, provider timeout and duplicate response.
- **Security and reliability:** Do not retry ambiguous remote calls automatically; retain hold.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-023-c"></a>

#### AR-023-C — Reconciliation command and accounting export

- **Tracking issue:** [#60](https://github.com/spei04/agent-rewind/issues/60); blocked until the prerequisites below are accepted.

- **Objective:** Account for every provider call and preserve uncertainty until reconciled. This task delivers reconciliation command and accounting export.
- **Implementation scope / PR boundary:** Add audited operator reconciliation with evidence attachment and immutable adjustment entries. Approved RB-02 addition: Extend the existing study ledger with atomic reserve-to-held conversion and distinct shared-input attribution; retain actual invoice uniqueness. Complete RB-02 integration only here after AR-023-B dispatch journal and AR-020-C lifecycle: prove protected reserve conversion, timeout holds, invoice uniqueness, actual over-quote charges, per-method attribution and late adjustments together. Consume the accepted AR-023-A evidence contract for audited idempotent historical opening-hold adjustments and actual account/period transfers, with explicit original-identity and exposure-preservation proof.
- **Out of scope:** No automatic billing integration or silent historical edit. No new payment integration, automatic refunds or new scheduler.
- **Prerequisites:** [AR-023-B](#ar-023-b), [AR-020-C](#ar-020-c). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08, C04; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Repeated reconciliation idempotent; denied/contradictory evidence cannot release hold. Concurrent discovery admits only within every task/method/physical cap; settlement and uncertainty preserve exposure. AR-020-B acceptance alone cannot satisfy this completion gate; AR-021-A and later export consumers wait for this accepted full accounting invariant. An opening or transfer adjustment requires authentic supported evidence and scoped operator authority; unsupported representation leaves prior obligations intact.
- **Required automated tests:** Evidence mismatch, replay, cap overflow and concurrent reconcile tests; PostgreSQL concurrent reserve, duplicate invoice, shared-pool charge, over-quote settlement, lost callback and idempotent late-reconciliation tests. Actual SQLite/PostgreSQL opening/transfer adjustment authorization, evidence mismatch, duplicate replay, atomic rollback/acknowledgment, preserved old period IDs and no exposure reset.
- **Security and reliability:** Only scoped privileged operator may reconcile; no manual SQL bypass. Freeze breached accounts; never cap a real invoice down to its quote. Never manufacture a provider call for an imported opening, silently move balances at rollover or release exposure before accepted evidence; no new reverse prerequisite is imposed on reserve-only AR-010-A.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-024"></a>

### AR-024 — Report intervention effects with correct denominators and uncertainty

M3 / P0 · 4 PRs · 12 engineering days · Not started

<a id="ar-024-a"></a>

#### AR-024-A — Estimator, missingness and experiment report contract

- **Tracking issue:** [#62](https://github.com/spei04/agent-rewind/issues/62); blocked until the prerequisites below are accepted.

- **Objective:** Report intervention effects with correct denominators and uncertainty. This task delivers estimator, missingness and experiment report contract.
- **Implementation scope / PR boundary:** Specify task-conditional estimand, paired design, intervals, missing data and invalidation/version fields. Approved RB-04 addition: Specify task-conditional effects, paired harm, distinct-task confirmed yield, recovery bounds, planned hypothesis family and repository-cluster reporting in C09 fixtures.
- **Out of scope:** No adaptive stopping or learned estimator. No estimator implementation, power claim or held-out outcome access.
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-002-B](#ar-002-b), [RA-01-B](#ra-01-b), [RESEARCHSCOPE0](#researchscope0). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C09, C21, C02, C08; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** No generalization claim from one run; report includes all assigned trials and uncertain calls. Pure retry has not-applicable intervention yield and valid recovery; no missing task or unused hypothesis slot disappears.
- **Required automated tests:** Golden tiny samples, ties, all-failed, all-missing and imbalanced fixtures; Tiny wins/harms/ties/missing tables, duplicate task credit, insufficient clusters, unused family slots and first-success-only bias cases.
- **Security and reliability:** Protocol fixed before outcomes; distinguish exploratory selection and confirmation. Independent statistics review before estimator/evaluation acceptance.
- **Effort / confidence:** 3 engineering days; planning range 3–5; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-024-b"></a>

#### AR-024-B — Estimator implementation and independent golden checks

- **Objective:** Report intervention effects with correct denominators and uncertainty. This task delivers estimator implementation and independent golden checks.
- **Implementation scope / PR boundary:** Implement versioned estimates and intervals with independent reference calculations.
- **Out of scope:** No real-model spending.
- **Prerequisites:** [AR-024-A](#ar-024-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Golden calculations match within declared tolerances; invalid inputs rejected.
- **Required automated tests:** Exact small-sample enumeration, permutation/invariance and numerical boundary tests.
- **Security and reliability:** No dropped failures or misleading zero uncertainty.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-024-c"></a>

#### AR-024-C — Null, coverage and heterogeneous-task simulation

- **Objective:** Report intervention effects with correct denominators and uncertainty. This task delivers null, coverage and heterogeneous-task simulation.
- **Implementation scope / PR boundary:** Run reproducible simulations for null calibration, power, correlated/missing outcomes and task heterogeneity.
- **Out of scope:** No universal causal attribution claim.
- **Prerequisites:** [AR-024-B](#ar-024-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Coverage/error tolerances predeclared; failing regimes constrain supported claims.
- **Required automated tests:** Fixed-seed simulation regression and independent statistical review pack.
- **Security and reliability:** No tuning thresholds on final test set; uncertainty disclosed.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-024-d"></a>

#### AR-024-D — Selected-policy calibration harness extension

- **Tracking issue:** [#66](https://github.com/spei04/agent-rewind/issues/66); blocked until the prerequisites below are accepted.

- **Objective:** Determine whether a funded confirmatory claim is feasible.
- **Implementation scope / PR boundary:** Extend the existing development-only calibration harness with selected-policy, multiplicity, clustering, missingness and cost-sensitivity cases; freeze the review pack before use. Consume the separately accepted unchanged AR-024-C baseline null/coverage simulator and AR-025-D comparator; add selected-policy integration without moving baseline readiness after its consumers.
- **Out of scope:** No held-out tuning, paid trials or guarantee from nominal sample counts.
- **Prerequisites:** [RESEARCHSCOPE0](#researchscope0), [AR-024-C](#ar-024-c), [AR-025-D](#ar-025-d). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C02, C09, C21; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Independent review accepts the harness and declared error tolerances before feasibility conclusions; no held-out tuning.
- **Required automated tests:** Development synthetic null/harm/heterogeneity/missingness regressions with declared Monte Carlo error; protocol leakage negatives.
- **Security and reliability:** No primary threshold changes after held-out unsealing; any revision needs new data/protocol.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** RS; required reviewers: TL, QE, independent statistical reviewer. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.


<a id="ar-025"></a>

### AR-025 — Compare useful intervention locations against fair inexpensive baselines

M3 / P0 · 4 PRs · 14 engineering days · Not started

<a id="ar-025-a"></a>

#### AR-025-A — Candidate provenance and budgeted proposal interface

- **Objective:** Compare useful intervention locations against fair inexpensive baselines. This task delivers candidate provenance and budgeted proposal interface.
- **Implementation scope / PR boundary:** Version proposal records, checkpoint candidate identity, permitted edits and discovery call budget.
- **Out of scope:** No training a learned ranking model.
- **Prerequisites:** [AR-018-C](#ar-018-c), [AR-023-C](#ar-023-c), [AR-024-A](#ar-024-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08, C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Each ranking candidate links to original evidence and only uses discovery data.
- **Required automated tests:** Invalid checkpoint, disallowed edit, provenance hash and budget exhaustion tests.
- **Security and reliability:** No hidden confirmation result access; model output treated untrusted.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-025-b"></a>

#### AR-025-B — Cost-matched ranking baselines and negative controls

- **Tracking issue:** [#63](https://github.com/spei04/agent-rewind/issues/63); blocked until the prerequisites below are accepted.

- **Objective:** Compare useful intervention locations against fair inexpensive baselines. This task delivers cost-matched ranking baselines and negative controls.
- **Implementation scope / PR boundary:** Implement last-error, uniform-location and bounded search baselines with identical evaluator/call cost caps. Approved RB-05 addition: Extend existing random/latest-error/heuristic controls with unchanged continuation and fresh restart; use the same permitted information/model/resource vectors and common proposal attribution.
- **Out of scope:** No claim of superiority before held-out study. No published-method adapter or adaptive allocator.
- **Prerequisites:** [AR-025-A](#ar-025-a), [AR-024-C](#ar-024-c), [AR-021-A](#ar-021-a). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C09, C08; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Baseline comparison records consumed budget and candidate count; negative intervention remains measurable. Retries receive task-recovery credit; shared proposals are charged equally; identical caps do not imply equal numbers of rollouts.
- **Required automated tests:** Fixed synthetic failure rankings, budget parity and deliberately irrelevant edit tests; Answer-access mismatch, unequal call caps, zero/free shared pool, invalid checkpoint and independent grader tampering negatives.
- **Security and reliability:** Do not cherry-pick baselines or omit unsuccessful branches. Untrusted proposals pass existing action/environment/evaluator restrictions.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-025-c"></a>

#### AR-025-C — Recomputable ranking evidence package

- **Tracking issue:** [#64](https://github.com/spei04/agent-rewind/issues/64); blocked until the prerequisites below are accepted.

- **Objective:** Compare useful intervention locations against fair inexpensive baselines. This task delivers recomputable ranking evidence package.
- **Implementation scope / PR boundary:** Export safe candidate/protocol/receipt hashes and reproduce ranking plus report from stored evidence. Approved RB-10 addition: Extend existing safe export with scoped receipt hashes, allowed observation manifests, all denominators and both actual/attributable cost views.
- **Out of scope:** No public release of partner traces. No partner trace publication or export of model credentials.
- **Prerequisites:** [AR-025-B](#ar-025-b), [AR-023-C](#ar-023-c), [AR-025-D](#ar-025-d). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08, C09; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Independent recomputation matches original; tampering or missing receipt fails verification. Independent verifier detects missing receipts, phase reuse, wrong shared charges and duplicate credit.
- **Required automated tests:** Corrupt/missing record, changed estimator and reordered receipt fixtures; Tampered/refused/missing records, late adjustment links, permission revocation and reproducible aggregate arithmetic.
- **Security and reliability:** Private source stays private; export obeys project authorization. Export minimizes source and preserves private permission boundaries.
- **Effort / confidence:** 4 engineering days; planning range 4–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-025-d"></a>

#### AR-025-D — Implement the successive-halving allocation comparator

- **Tracking issue:** [#65](https://github.com/spei04/agent-rewind/issues/65); blocked until the prerequisites below are accepted.

- **Objective:** Measure allocation value without changing the proposal pool.
- **Implementation scope / PR boundary:** Implement owner-approved successive halving over frozen candidates with within-task updates and immutable resource receipts; compare against uniform allocation.
- **Out of scope:** No novel-algorithm claim, learned cross-task policy or optional confirmation stopping.
- **Prerequisites:** [RESEARCHSCOPE0](#researchscope0), [AR-025-B](#ar-025-b), [AR-024-C](#ar-024-c), [AR-025-A](#ar-025-a). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C08, C09; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Uniform and selected adaptive policy share inputs and confirmation reserve; caps cannot be borrowed across tasks.
- **Required automated tests:** Fixed synthetic candidate ordering, ties, missing rewards, exhausted reserve, partial receipts and deterministic policy-replay tests.
- **Security and reliability:** No confirmation or other held-out task outcomes enter policy state.
- **Effort / confidence:** 3 engineering days; planning range 3–5; low confidence.
- **Responsible role:** RS; required reviewers: TL, QE, independent statistical reviewer. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.


<a id="ar-026"></a>

### AR-026 — Establish experiment correctness before relying on research conclusions

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-026-a"></a>

#### AR-026-A — Frozen evaluation and power decision

- **Tracking issue:** [#67](https://github.com/spei04/agent-rewind/issues/67); blocked until the prerequisites below are accepted.

- **Objective:** Establish experiment correctness before relying on research conclusions. This task delivers frozen evaluation and power decision.
- **Implementation scope / PR boundary:** Preregister useful-location metric, minimum effect, task sample, multiple comparisons and stop/invalidation rules. Approved RB-11B addition: Run the reviewed development harness and independently review its evidence; freeze sample, threshold and affordability decisions or explicitly narrow/block the claim. Consume reviewed AR-024-D harness evidence in this separate feasibility PR; do not hide harness implementation in the decision or infer approval of a paid study.
- **Out of scope:** No promise that 100 failures fit existing budget. No held-out tuning, paid trials or guarantee from nominal sample counts.
- **Prerequisites:** [AR-024-C](#ar-024-c), [AR-025-B](#ar-025-b), [AR-002-B](#ar-002-b), [AR-024-D](#ar-024-d). E0 applies transitively; required producers must be accepted.
- **Required contracts:** C02, C09, C21; future interfaces remain unavailable until their own producer review.
- **Acceptance criteria:** Protocol frozen before held-out access; affordable sample supports claim or scope explicitly narrows. Independent reviewer accepts tolerances and affordable sample or explicitly narrows/blocks the claim.
- **Required automated tests:** Leakage guard, power arithmetic and protocol immutability checks; Recompute evidence hashes, null/coverage summaries, sample/cost arithmetic and immutable protocol identity.
- **Security and reliability:** No open-ended model spend; paid evaluation gated separately. No primary threshold changes after held-out unsealing; any revision needs new data/protocol.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee at dependency-ready handoff.
- **Definition of done:** Task acceptance and automated checks pass at a recorded commit; independent reviewer disposition, safe diagnostic evidence, documentation and compatibility/recovery impact are recorded; roadmap/backlog status and dependency evidence updated. Decisions require actual authorized sign-off.
- **Progress:** Not started; original prerequisites and task-specific review gates apply.

<a id="ar-026-b"></a>

#### AR-026-B — Distributed study crash/resume acceptance

- **Objective:** Establish experiment correctness before relying on research conclusions. This task delivers distributed study crash/resume acceptance.
- **Implementation scope / PR boundary:** Run synthetic multi-worker study across selection, freeze, confirmation and publication faults.
- **Out of scope:** No pilot product usefulness claim.
- **Prerequisites:** [G2](#g2), [AR-022-C](#ar-022-c), [AR-023-C](#ar-023-c), [AR-025-C](#ar-025-c), [AR-026-A](#ar-026-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08, C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Results recompute; every assigned outcome and charged/uncertain call accounted; all barriers respected.
- **Required automated tests:** Full crash grid, cancel/budget race and independent report verifier.
- **Security and reliability:** No new paid study required for deterministic failure coverage.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-026-c"></a>

#### AR-026-C — G3 evidence review and study operator guide

- **Objective:** Establish experiment correctness before relying on research conclusions. This task delivers g3 evidence review and study operator guide.
- **Implementation scope / PR boundary:** Record reviewed study correctness/statistics evidence and operator actions for uncertainty.
- **Out of scope:** No launch approval.
- **Prerequisites:** [AR-026-B](#ar-026-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08, C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** RS/QE/TL approve protocol integrity and known limitations; failures block G3.
- **Required automated tests:** Manifest completeness plus independently rerun golden report and uncertainty recovery.
- **Security and reliability:** Honest null/missingness presentation; private evidence retention documented.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-027"></a>

### AR-027 — Let engineers inspect and branch large recorded runs through stable contracts

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-027-a"></a>

#### AR-027-A — Timeline, files, branch and comparison API contracts

- **Objective:** Let engineers inspect and branch large recorded runs through stable contracts. This task delivers timeline, files, branch and comparison api contracts.
- **Implementation scope / PR boundary:** Extend proposed v1 API with paginated events/files, branch submission and comparison; define observed versus actual fields.
- **Out of scope:** No study API or runtime endpoints.
- **Prerequisites:** [AR-006-B](#ar-006-b), [AR-014-A](#ar-014-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** FE/BE agree success, denied, nonbranchable, conflict and oversized-result fixtures.
- **Required automated tests:** OpenAPI compatibility, scope matrix and field semantics fixture checks.
- **Security and reliability:** Redacted content explicit; never confuse synthetic observation with filesystem truth.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-027-b"></a>

#### AR-027-B — History and branch API services

- **Objective:** Let engineers inspect and branch large recorded runs through stable contracts. This task delivers history and branch api services.
- **Implementation scope / PR boundary:** Implement paged timeline/files, idempotent branch admission and bounded comparison from immutable lineage; consume AR-007-C trusted project authority and reauthorize bounded timeline/files/branch/compare results; no raw-hash lookup after an initial scope check.
- **Out of scope:** No browser interface or study report.
- **Prerequisites:** [AR-027-A](#ar-027-a), [AR-014-C](#ar-014-c), [AR-008-B](#ar-008-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** Parent stays unchanged; rejected restore returns reason; large history never loads all content.
- **Required automated tests:** API contract, project denial, pagination, branch retry and compare bound tests.
- **Security and reliability:** Apply permissions before file access; branch budget and cancellation use existing permits.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-027-c"></a>

#### AR-027-C — Accessible paginated debugger timeline

- **Objective:** Let engineers inspect and branch large recorded runs through stable contracts. This task delivers accessible paginated debugger timeline.
- **Implementation scope / PR boundary:** Build typed timeline/file inspection, branchability indicators and keyboard navigation.
- **Out of scope:** No custom visual design framework rewrite.
- **Prerequisites:** [AR-027-B](#ar-027-b), [AR-012-B](#ar-012-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** Large histories use bounded paging; keyboard/screen-reader journey works and errors preserve context.
- **Required automated tests:** Browser empty/error/permission states, accessibility checks and large fixture interactions.
- **Security and reliability:** Escape untrusted tool output; avoid source in browser telemetry.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-028"></a>

### AR-028 — Make intervention differences and unsuccessful outcomes understandable

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-028-a"></a>

#### AR-028-A — Intervention editor and branch submission UI

- **Objective:** Make intervention differences and unsuccessful outcomes understandable. This task delivers intervention editor and branch submission ui.
- **Implementation scope / PR boundary:** Add action/tool-result edit form with provenance, validation, budget and idempotent submission state.
- **Out of scope:** No automatic proposal ranking UI.
- **Prerequisites:** [AR-027-C](#ar-027-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** User sees edit type and parent boundary; double-click/retry creates one branch.
- **Required automated tests:** Browser form limits, interrupted request, conflict, stale access and cancel flows.
- **Security and reliability:** Treat pasted content as data; explicit actual/observed distinction.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-028-b"></a>

#### AR-028-B — Trajectory comparison and evidence navigation

- **Objective:** Make intervention differences and unsuccessful outcomes understandable. This task delivers trajectory comparison and evidence navigation.
- **Implementation scope / PR boundary:** Render bounded event/file diffs, divergent decisions and parent/control/treatment links.
- **Out of scope:** No claim that visual difference proves causality.
- **Prerequisites:** [AR-028-A](#ar-028-a), [AR-027-B](#ar-027-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** Compared artifacts match server identity; missing/redacted outcomes visibly distinct.
- **Required automated tests:** Diff fixtures, large files, binary content, cross-project navigation and keyboard tests.
- **Security and reliability:** No executable HTML from source/tool output; scope every drill-down.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-028-c"></a>

#### AR-028-C — Branch workflow end-to-end acceptance

- **Objective:** Make intervention differences and unsuccessful outcomes understandable. This task delivers branch workflow end-to-end acceptance.
- **Implementation scope / PR boundary:** Test native capture to edited branch and comparison with real API/DB/gVisor fixture.
- **Out of scope:** No pilot customer acceptance.
- **Prerequisites:** [AR-028-B](#ar-028-b), [AR-014-C](#ar-014-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11; definitions and producer availability in the contract register.
- **Acceptance criteria:** An independent operator completes journey and verifies unchanged parent plus expected branch outcomes.
- **Required automated tests:** Browser/API E2E including unsuccessful branch, permission loss and timeout.
- **Security and reliability:** Use synthetic source; record safe screenshots/evidence only.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-029"></a>

### AR-029 — Expose study progress, uncertainty and costs without overstating evidence

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-029-a"></a>

#### AR-029-A — Study, report and reconciliation API contracts

- **Objective:** Expose study progress, uncertainty and costs without overstating evidence. This task delivers study, report and reconciliation api contracts.
- **Implementation scope / PR boundary:** Specify study create/status/cancel/report/export and privileged reconciliation routes with immutable protocol references.
- **Out of scope:** No endpoint implementation or billing system.
- **Prerequisites:** [AR-020-C](#ar-020-c), [AR-023-C](#ar-023-c), [AR-024-B](#ar-024-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C12; definitions and producer availability in the contract register.
- **Acceptance criteria:** RS/FE/QE approve pending, uncertain, invalid, no-effect and success examples.
- **Required automated tests:** OpenAPI/ref validation, role matrix and report-schema golden checks.
- **Security and reliability:** No false precision; no privileged reconciliation by viewer/operator.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-029-b"></a>

#### AR-029-B — Study and report API integration

- **Objective:** Expose study progress, uncertainty and costs without overstating evidence. This task delivers study and report api integration.
- **Implementation scope / PR boundary:** Expose scoped idempotent study commands, paged trial status and recomputable report/export; consume AR-007-C trusted project authority for new study/report/export routes and reauthorize after artifact I/O.
- **Out of scope:** No new estimator or UI.
- **Prerequisites:** [AR-029-A](#ar-029-a), [AR-022-C](#ar-022-c), [AR-026-C](#ar-026-c), [AR-008-B](#ar-008-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C12; definitions and producer availability in the contract register.
- **Acceptance criteria:** API matches persisted state and ledger; export includes missing outcomes and protocol/version hashes.
- **Required automated tests:** Contract cases, concurrent cancel/reconcile, foreign project and report tampering.
- **Security and reliability:** Reauthorize exports; no raw prompt or secrets in summary.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-029-c"></a>

#### AR-029-C — Study progress and evidence workbench

- **Objective:** Expose study progress, uncertainty and costs without overstating evidence. This task delivers study progress and evidence workbench.
- **Implementation scope / PR boundary:** Build budget/queue/phase controls and effect report with uncertainty, missingness and invalidation.
- **Out of scope:** No marketing claims or advanced statistical authoring.
- **Prerequisites:** [AR-029-B](#ar-029-b), [AR-027-C](#ar-027-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C12; definitions and producer availability in the contract register.
- **Acceptance criteria:** Users can distinguish exploratory example from confirmation; uncertain spend and no effect visible.
- **Required automated tests:** Browser all report states, progress reconnect, cancellation and accessibility.
- **Security and reliability:** No success-only chart or hidden spend; safe untrusted rendering.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-030"></a>

### AR-030 — Let customers integrate through a versioned supported Python client

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-030-a"></a>

#### AR-030-A — Versioned Python client transport and run APIs

- **Objective:** Let customers integrate through a versioned supported Python client. This task delivers versioned python client transport and run apis.
- **Implementation scope / PR boundary:** Implement typed client transport, scoped auth, idempotency persistence, list/run/operation/cancel methods.
- **Out of scope:** No study/branch client or extra language SDK.
- **Prerequisites:** [AR-008-B](#ar-008-b), [AR-012-B](#ar-012-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Timeout retry reuses identity; errors expose safe typed code; existing client compatibility documented.
- **Required automated tests:** Mock transport plus real API contract tests, retries and revoked keys.
- **Security and reliability:** No automatic credential discovery or prompt logging.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-030-b"></a>

#### AR-030-B — Capture, branch and study SDK methods

- **Objective:** Let customers integrate through a versioned supported Python client. This task delivers capture, branch and study sdk methods.
- **Implementation scope / PR boundary:** Add supported adapter capture, branch/compare and study/report methods with protocol versions.
- **Out of scope:** No arbitrary third-party framework support.
- **Prerequisites:** [AR-030-A](#ar-030-a), [AR-027-B](#ar-027-b), [AR-029-B](#ar-029-b), [AR-014-C](#ar-014-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C11, C12; definitions and producer availability in the contract register.
- **Acceptance criteria:** Client preserves exact state and IDs; generated request fixtures match server contract.
- **Required automated tests:** Native capture roundtrip, unsupported adapter, changed schema and resume/cancel tests.
- **Security and reliability:** No credential capture; project scope mandatory.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-030-c"></a>

#### AR-030-C — SDK compatibility examples and integration gate

- **Objective:** Let customers integrate through a versioned supported Python client. This task delivers sdk compatibility examples and integration gate.
- **Implementation scope / PR boundary:** Publish synthetic examples covering capture, branch, study, export and safe deletion; test supported client/server matrix.
- **Out of scope:** No ecosystem-wide compatibility promise.
- **Prerequisites:** [AR-030-B](#ar-030-b), [AR-032-B](#ar-032-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11, C12, C13; definitions and producer availability in the contract register.
- **Acceptance criteria:** Examples execute in clean environment and document unsupported state and uncertain outcomes.
- **Required automated tests:** N/N-1 declared matrix, expired key, interrupted response and stale cursor.
- **Security and reliability:** Example credentials placeholders only; never publish private evidence.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-031"></a>

### AR-031 — Prove that one real external agent framework meets the restoration contract

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-031-a"></a>

#### AR-031-A — Partner adapter capability and selection spike

- **Objective:** Prove that one real external agent framework meets the restoration contract. This task delivers partner adapter capability and selection spike.
- **Implementation scope / PR boundary:** Timebox selection of one partner framework with documented serializable state and capture hooks.
- **Out of scope:** No commitment to all popular frameworks.
- **Prerequisites:** [AR-002-B](#ar-002-b), [AR-014-A](#ar-014-a), [PARTNER0](#partner0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Prove metadata-level compatibility or reject and select supported alternative; record adapter contract.
- **Required automated tests:** Synthetic capability/preflight fixtures for real framework state shape.
- **Security and reliability:** Review package/license/data rights; no production token capture.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-031-b"></a>

#### AR-031-B — Selected framework capture and restore adapter

- **Objective:** Prove that one real external agent framework meets the restoration contract. This task delivers selected framework capture and restore adapter.
- **Implementation scope / PR boundary:** Implement only approved sequential tool-boundary capture/restore and explicit unsupported state errors.
- **Out of scope:** No framework fork or general agent orchestration.
- **Prerequisites:** [AR-031-A](#ar-031-a), [AR-030-B](#ar-030-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Adapter restores permitted real sample with same state manifest and evaluator identity.
- **Required automated tests:** Framework version fixtures, missing state, unsupported async/tools and branch conformance.
- **Security and reliability:** Strip credential/runtime handles; deny external side effects.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-031-c"></a>

#### AR-031-C — Partner adapter compatibility and upgrade guide

- **Objective:** Prove that one real external agent framework meets the restoration contract. This task delivers partner adapter compatibility and upgrade guide.
- **Implementation scope / PR boundary:** Validate permitted representative tasks, record admitted denominator and framework compatibility matrix.
- **Out of scope:** No claim that sample proves broad workload coverage.
- **Prerequisites:** [AR-031-B](#ar-031-b), [DATA0](#data0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** At least one permitted task restores end to end; incompatible tasks counted and documented.
- **Required automated tests:** Golden framework versions, state mismatch, corrupted capture and evaluator replay.
- **Security and reliability:** Private workloads stay in approved storage; logs redacted.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-032"></a>

### AR-032 — Honor retention, export and deletion without breaking live evidence

M4 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-032-a"></a>

#### AR-032-A — Retention graph, export and deletion contracts

- **Objective:** Honor retention, export and deletion without breaking live evidence. This task delivers retention graph, export and deletion contracts.
- **Implementation scope / PR boundary:** Define owned resource graph, holds, tombstones, deletion journal, export schema and endpoint role matrix.
- **Out of scope:** No destructive API implementation.
- **Prerequisites:** [AR-007-C](#ar-007-c), [AR-009-B](#ar-009-b), [AR-016-A](#ar-016-a), [AR-020-C](#ar-020-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C13; definitions and producer availability in the contract register.
- **Acceptance criteria:** Explicit rules cover branch lineage, frozen studies, shared refs, backups and restored deletions.
- **Required automated tests:** Schema/graph fixtures for hold, referenced parent, orphan and cross-project relations.
- **Security and reliability:** Deletion restricted and audited; key retention tied to backups.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-032-b"></a>

#### AR-032-B — Scoped export and tombstone lifecycle

- **Objective:** Honor retention, export and deletion without breaking live evidence. This task delivers scoped export and tombstone lifecycle.
- **Implementation scope / PR boundary:** Implement bounded evidence export, authenticated deletion intent and hold-protected tombstones; consume AR-007-C trusted project authority for bounded lifecycle export/delete and reauthorize at effect/return boundaries.
- **Out of scope:** No physical GC or instant backup erasure promise.
- **Prerequisites:** [AR-032-A](#ar-032-a), [AR-029-B](#ar-029-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C13; definitions and producer availability in the contract register.
- **Acceptance criteria:** Held/referenced evidence not physically removed; exports authorized and hash-verifiable.
- **Required automated tests:** Concurrent export/delete, denied deletion, broken ref and hold race tests.
- **Security and reliability:** No public artifact URLs; tombstone propagation before reclamation.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-032-c"></a>

#### AR-032-C — Reachability GC and deletion replay

- **Objective:** Honor retention, export and deletion without breaking live evidence. This task delivers reachability gc and deletion replay.
- **Implementation scope / PR boundary:** Implement mark/grace/recheck sweep with concurrent fork protection, orphan tracking and restore journal replay.
- **Out of scope:** No cross-installation purge or legal certification.
- **Prerequisites:** [AR-032-B](#ar-032-b), [AR-016-D](#ar-016-d). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C13, C07; definitions and producer availability in the contract register.
- **Acceptance criteria:** Live refs never deleted; tombstones reapply after restore; interruption resumes safely.
- **Required automated tests:** Fork-versus-sweep, old backup restore, legal hold, partial delete and repeat GC.
- **Security and reliability:** Bound delete batch and privileged operator scope; preserve required keys/evidence.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-033"></a>

### AR-033 — Make the reference installation reproducible and its trust boundaries testable

M4 / P0 · 4 PRs · 10 engineering days · In progress

<a id="ar-033-a"></a>

#### AR-033-A — Reference infrastructure inputs and trust topology

- **Objective:** Make the reference installation reproducible and its trust boundaries testable. This task delivers reference infrastructure inputs and trust topology.
- **Implementation scope / PR boundary:** Specify versioned deployment config, region, identities, private ingress, DB/store/KMS and resource labels.
- **Out of scope:** No cloud provisioning or worker image build.
- **Prerequisites:** [G0](#g0), [AR-003-B](#ar-003-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Independent reviewer can map every flow and role to approved threat model and cost line.
- **Required automated tests:** Config schema, topology/IAM policy lint and missing budget/region rejection.
- **Security and reliability:** No public DB, shared credentials or sandbox access to cloud metadata.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Assigned contributor: Engineer A — reference configuration.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified; [PR #36](https://github.com/spei04/agent-rewind/pull/36), merge 4abc352, B accepted exact 83aabb8. 70 scoped tests and hosted locked core/gVisor/security/package/CI gate passed. [C14 configuration](delivery/REFERENCE_CONFIGURATION.md) is available; ENV0 and actual provisioning remain gated.

<a id="ar-033-b"></a>

#### AR-033-B — Early staging foundation and scoped identities

- **Objective:** Make the reference installation reproducible and its trust boundaries testable. This task delivers early staging foundation and scoped identities.
- **Implementation scope / PR boundary:** Provision isolated Cloud SQL, private Cloud Storage, KMS, Secret Manager, service identities and worker host skeleton.
- **Out of scope:** No complete product installation or customer rollout.
- **Prerequisites:** [AR-033-A](#ar-033-a), [ENV0](#env0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Authorized API/worker identities reach only intended services; budget alerts and teardown inventory exist.
- **Required automated tests:** IaC plan/policy, denied public access, IAM allow/deny and connectivity smoke.
- **Security and reliability:** Dedicated staging project; no customer source; funded bounded resources only.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-033-c"></a>

#### AR-033-C — API and gVisor worker deployment composition

- **Objective:** Make the reference installation reproducible and its trust boundaries testable. This task delivers api and gvisor worker deployment composition.
- **Implementation scope / PR boundary:** Deploy versioned API/workers with private ingress, health checks and secret/workload identity wiring.
- **Out of scope:** No independent installation acceptance yet.
- **Prerequisites:** [AR-033-B](#ar-033-b), [AR-013-C](#ar-013-c), [AR-016-D](#ar-016-d), [AR-011-C](#ar-011-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Synthetic admitted run executes with real DB/GCS/KMS and cleans resources.
- **Required automated tests:** Deployment smoke, dependency unavailable, credential denial and image rollback.
- **Security and reliability:** No key in image/env dump; production rejects insecure runner.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-033-d"></a>

#### AR-033-D — Clean install and teardown rehearsal

- **Objective:** Make the reference installation reproducible and its trust boundaries testable. This task delivers clean install and teardown rehearsal.
- **Implementation scope / PR boundary:** Have a different operator install from pinned config in fresh approved staging and destroy test resources.
- **Out of scope:** No customer installation or regional DR proof.
- **Prerequisites:** [AR-033-C](#ar-033-c), [AR-029-B](#ar-029-b), [AR-032-C](#ar-032-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Documented process succeeds without undocumented state; teardown removes only its labeled resources.
- **Required automated tests:** Install/upgrade smoke, missing permission/secret and idempotent teardown checks.
- **Security and reliability:** State storage protected; no destructive teardown of shared/live installation.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-034"></a>

### AR-034 — Support real enterprise identity workflows and independent product acceptance

M4 / P0 · 4 PRs · 12 engineering days · In progress

<a id="ar-034-a"></a>

#### AR-034-A — Administrative identity lifecycle contract

- **Objective:** Support real enterprise identity workflows and independent product acceptance. This task delivers administrative identity lifecycle contract.
- **Implementation scope / PR boundary:** Specify project/membership/key admin endpoints, IdP mapping, revocation and browser recovery states.
- **Out of scope:** No SCIM or multiple IdPs per installation.
- **Prerequisites:** [AR-007-C](#ar-007-c), [AR-003-B](#ar-003-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15; definitions and producer availability in the contract register.
- **Acceptance criteria:** SEC/TL approve role separation, last-admin recovery and session/key revocation expectations.
- **Required automated tests:** OpenAPI fixtures for admin denial, membership revoke and invalid mapping.
- **Security and reliability:** No self-assigned admin; recovery requires explicit audited operator procedure.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** FE; required reviewers: SEC, TL, QE. Execution assigned to engineer C; named human staffing remains unconfirmed.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Verified for offline contract and synthetic fixtures after accepted PR #103 merge 9ee75e7, matching PR/main checks and candidate verification. C15 is available for development consumption; runtime and external gates remain open.
- **Tracking:** https://github.com/spei04/agent-rewind/issues/100

<a id="ar-034-b"></a>

#### AR-034-B — Identity administration services and UI

- **Objective:** Support real enterprise identity workflows and independent product acceptance. This task delivers identity administration services and ui.
- **Implementation scope / PR boundary:** Implement membership/key admin service and accessible settings UI, using reviewed scoped repositories.
- **Out of scope:** No broad identity platform rewrite.
- **Prerequisites:** [AR-034-A](#ar-034-a), [AR-033-C](#ar-033-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15; definitions and producer availability in the contract register.
- **Acceptance criteria:** Admin can revoke access and keys; non-admin cannot enumerate or mutate membership.
- **Required automated tests:** API and browser role matrix, CSRF, last-admin lockout and token revocation.
- **Security and reliability:** Do not expose key secret after initial creation; protected audit entries.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-034-c"></a>

#### AR-034-C — Real IdP provisioning and deprovisioning exercise

- **Objective:** Support real enterprise identity workflows and independent product acceptance. This task delivers real idp provisioning and deprovisioning exercise.
- **Implementation scope / PR boundary:** Exercise actual permitted test IdP login/logout, group mapping, revoked user/session and access changes.
- **Out of scope:** No certification across all enterprise IdPs.
- **Prerequisites:** [AR-034-B](#ar-034-b), [IDP0](#idp0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15; definitions and producer availability in the contract register.
- **Acceptance criteria:** Denied user loses all API/browser access within documented revocation bound.
- **Required automated tests:** OIDC issuer/audience/key rotation failures and live deprovisioning script.
- **Security and reliability:** Dedicated test accounts; no personal credentials in public evidence.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-034-d"></a>

#### AR-034-D — Independent integrated product acceptance

- **Objective:** Support real enterprise identity workflows and independent product acceptance. This task delivers independent integrated product acceptance.
- **Implementation scope / PR boundary:** Run independent install-to-capture-to-investigate-to-confirm-to-compare-to-export/delete workflow.
- **Out of scope:** No customer pilot or production readiness claim.
- **Prerequisites:** [G3](#g3), [AR-028-C](#ar-028-c), [AR-029-C](#ar-029-c), [AR-030-C](#ar-030-c), [AR-031-C](#ar-031-c), [AR-032-C](#ar-032-c), [AR-033-D](#ar-033-d), [AR-034-C](#ar-034-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11, C12, C13, C14, C15; definitions and producer availability in the contract register.
- **Acceptance criteria:** All journey/error/uncertain cases pass; evidence maps to requirements and configuration.
- **Required automated tests:** Full browser/SDK E2E, cancellation, insufficient budget, unauthorized access and recovery.
- **Security and reliability:** Use permitted fixtures; untested gate stays open.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-035"></a>

### AR-035 — Admit pilot data only after deployment, permission and recovery prerequisites

M5 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-035-a"></a>

#### AR-035-A — Pilot data, processor and operator agreement checklist

- **Objective:** Admit pilot data only after deployment, permission and recovery prerequisites. This task delivers pilot data, processor and operator agreement checklist.
- **Implementation scope / PR boundary:** Specify per-partner region, processors, data rights, spend cap, retention, contacts and incident responsibilities.
- **Out of scope:** No contract negotiation performed by engineering.
- **Prerequisites:** [AR-003-B](#ar-003-b), [AR-026-A](#ar-026-a), [AR-032-A](#ar-032-a), [PARTNER0](#partner0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** PM/SEC/customer review owners and all agreement fields; public document contains no private terms.
- **Required automated tests:** Validate required agreement references and expiry fields; fail incomplete intake.
- **Security and reliability:** No data ingestion before signed permissions; no implied legal approval.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-035-b"></a>

#### AR-035-B — Isolated pilot deployment and access preflight

- **Objective:** Admit pilot data only after deployment, permission and recovery prerequisites. This task delivers isolated pilot deployment and access preflight.
- **Implementation scope / PR boundary:** Install approved release per partner with scoped identities, quotas, safe telemetry and deprovisioning path.
- **Out of scope:** No shared SaaS deployment.
- **Prerequisites:** [G4](#g4), [AR-035-A](#ar-035-a), [PILOT0](#pilot0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Both installation inventories verified; no cross-installation access; named primary/secondary operators.
- **Required automated tests:** Private ingress, live IdP, encrypted store and model egress allow/deny smoke.
- **Security and reliability:** Use least privilege; no shared customer keys or database.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-035-c"></a>

#### AR-035-C — Pre-ingestion load and backup/key recovery drill

- **Objective:** Admit pilot data only after deployment, permission and recovery prerequisites. This task delivers pre-ingestion load and backup/key recovery drill.
- **Implementation scope / PR boundary:** Test expected pilot workload and complete DB/object/key restore before customer data, using synthetic evidence.
- **Out of scope:** No forecast enterprise load certification.
- **Prerequisites:** [AR-035-B](#ar-035-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17, C07, C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Pilot capacity and declared RPO/RTO pass; failed recovery blocks ingestion.
- **Required automated tests:** Timed restore, missing key, restored deletion, bounded load and cancellation.
- **Security and reliability:** Restore in isolated environment; validate scope and deletion journal.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-036"></a>

### AR-036 — Validate onboarding and daily operation for the first design partner

M5 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-036-a"></a>

#### AR-036-A — Partner one capture integration

- **Objective:** Validate onboarding and daily operation for the first design partner. This task delivers partner one capture integration.
- **Implementation scope / PR boundary:** Configure selected supported workflow and capture permitted real runs through SDK.
- **Out of scope:** No custom unsupported tool families.
- **Prerequisites:** [AR-031-C](#ar-031-c), [AR-035-C](#ar-035-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Partner operator imports sample without core-code fork and sees compatibility reasons.
- **Required automated tests:** Partner-specific permitted contract fixtures and restore smoke.
- **Security and reliability:** Customer owns credentials; no source committed publicly.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-036-b"></a>

#### AR-036-B — Partner one workflow and regression handoff

- **Objective:** Validate onboarding and daily operation for the first design partner. This task delivers partner one workflow and regression handoff.
- **Implementation scope / PR boundary:** Run agreed branch/confirmation/export workflow and document regression use, including failures.
- **Out of scope:** No generalized effect estimate yet.
- **Prerequisites:** [AR-036-A](#ar-036-a), [AR-030-C](#ar-030-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11, C12, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Operator completes supported journey and records all attempted investigations.
- **Required automated tests:** Workflow verification, report recomputation and permission revocation smoke.
- **Security and reliability:** Use only pilot-approved model cap; no selective publication of successes.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-036-c"></a>

#### AR-036-C — Partner one operator acceptance

- **Objective:** Validate onboarding and daily operation for the first design partner. This task delivers partner one operator acceptance.
- **Implementation scope / PR boundary:** Record customer acceptance, compatibility denominator, limitations and operational escalation handoff.
- **Out of scope:** No automatic acceptance from elapsed time.
- **Prerequisites:** [AR-036-B](#ar-036-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Named operator accepts or issue remains blocked; all critical pilot blockers resolved.
- **Required automated tests:** Rerunnable onboarding checklist and alert/escalation test.
- **Security and reliability:** Customer acceptance is an external decision; sensitive evidence private.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-037"></a>

### AR-037 — Validate repeatable onboarding for a second distinct design-partner workflow

M5 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-037-a"></a>

#### AR-037-A — Partner two distinct workflow integration

- **Objective:** Validate repeatable onboarding for a second distinct design-partner workflow. This task delivers partner two distinct workflow integration.
- **Implementation scope / PR boundary:** Configure a second approved team/workflow to test repeatable onboarding within same supported adapter.
- **Out of scope:** No expansion to unapproved frameworks.
- **Prerequisites:** [AR-031-C](#ar-031-c), [AR-035-C](#ar-035-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C06, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Independent installation accepts sample and exposes unsupported cases without bespoke core fork.
- **Required automated tests:** Second partner capture/restore and scope/isolation tests.
- **Security and reliability:** Separate credentials and data permissions.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-037-b"></a>

#### AR-037-B — Partner two investigation and operator handoff

- **Objective:** Validate repeatable onboarding for a second distinct design-partner workflow. This task delivers partner two investigation and operator handoff.
- **Implementation scope / PR boundary:** Run branch/confirmation/regression export for distinct permitted workload.
- **Out of scope:** No aggregate success claim from handpicked runs.
- **Prerequisites:** [AR-037-A](#ar-037-a), [AR-030-C](#ar-030-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C11, C12, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Second team completes workflow with documented unsuccessful and uncertain cases.
- **Required automated tests:** Report verifier, branch immutability and access revocation smoke.
- **Security and reliability:** Respect per-partner budgets and evaluator access.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-037-c"></a>

#### AR-037-C — Partner two acceptance and compatibility comparison

- **Objective:** Validate repeatable onboarding for a second distinct design-partner workflow. This task delivers partner two acceptance and compatibility comparison.
- **Implementation scope / PR boundary:** Record operator sign-off and compare onboarding friction/unsupported states with partner one.
- **Out of scope:** No third partner requirement for pilot exit.
- **Prerequisites:** [AR-037-B](#ar-037-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Second team accepts; comparison identifies reusable issues and explicit supported denominator.
- **Required automated tests:** Rerunnable second onboarding and operator incident contact test.
- **Security and reliability:** No private comparison data disclosed across customers.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-038"></a>

### AR-038 — Measure natural-failure intervention usefulness under a frozen affordable protocol

M5 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-038-a"></a>

#### AR-038-A — Permitted natural-failure corpus freeze

- **Objective:** Measure natural-failure intervention usefulness under a frozen affordable protocol. This task delivers permitted natural-failure corpus freeze.
- **Implementation scope / PR boundary:** Curate allowed naturally failed runs, deduplicate task families, freeze splits and evaluator identities.
- **Out of scope:** No real paid trials yet.
- **Prerequisites:** [AR-026-A](#ar-026-a), [AR-036-C](#ar-036-c), [AR-037-C](#ar-037-c), [DATA0](#data0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02, C09, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Provenance/permissions complete; no injected-stop substitution; insufficient corpus blocks broad claim.
- **Required automated tests:** Manifest validation, leakage/duplicate task checks and evaluator stability tests.
- **Security and reliability:** Minimize source retention; no held-out outcomes in selection.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-038-b"></a>

#### AR-038-B — Preregistered useful-location evaluation

- **Objective:** Measure natural-failure intervention usefulness under a frozen affordable protocol. This task delivers preregistered useful-location evaluation.
- **Implementation scope / PR boundary:** Execute bounded cost-matched location study with fixed candidates, controls, attempts and stopping rules.
- **Out of scope:** No guaranteed positive result or unsupported cross-task generalization.
- **Prerequisites:** [AR-038-A](#ar-038-a), [STUDYFUNDS0](#studyfunds0), [AR-026-C](#ar-026-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** All assigned trials and failures reported; intervals and costs recompute; nulls retained.
- **Required automated tests:** Automated protocol/ledger/verifier checks plus frozen statistical pipeline.
- **Security and reliability:** Funding gate before dispatch; no optional stopping or holdout leakage.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-038-c"></a>

#### AR-038-C — Independent research claim and null-result review

- **Objective:** Measure natural-failure intervention usefulness under a frozen affordable protocol. This task delivers independent research claim and null-result review.
- **Implementation scope / PR boundary:** Have independent statistical reviewer check estimand, sampling, missingness and claims against evidence.
- **Out of scope:** No open-ended new study without revised budget/backlog.
- **Prerequisites:** [AR-038-B](#ar-038-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Review supports bounded claim or records narrowing/research redesign decision.
- **Required automated tests:** Independent recomputation and invalidation/negative-control checks.
- **Security and reliability:** No marketing claim beyond validated population and protocol.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-039"></a>

### AR-039 — Decide pilot readiness from complete customer and operating evidence

M5 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-039-a"></a>

#### AR-039-A — Pilot measurement start and denominator audit

- **Objective:** Decide pilot readiness from complete customer and operating evidence. This task delivers pilot measurement start and denominator audit.
- **Implementation scope / PR boundary:** Enable safe timing, usage, incident, cost and compatibility measurement for both onboarded partners.
- **Out of scope:** No assumption that pilot elapsed before both onboardings.
- **Prerequisites:** [AR-036-C](#ar-036-c), [AR-037-C](#ar-037-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Start timestamp, baseline timing method and eligible investigation denominator agreed.
- **Required automated tests:** Metric formulas, event deduplication, privacy and missing telemetry tests.
- **Security and reliability:** No source or user secrets in analytics; count unsuccessful attempts.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-039-b"></a>

#### AR-039-B — Four-week pilot measurement report

- **Objective:** Decide pilot readiness from complete customer and operating evidence. This task delivers four-week pilot measurement report.
- **Implementation scope / PR boundary:** Analyze at least 28 calendar days for both partners, 20 investigation target and weekly workflow use.
- **Out of scope:** No automatic pass when 28 days elapse.
- **Prerequisites:** [AR-039-A](#ar-039-a), [P28](#p28). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Coverage, median timing change, cost, incidents and adoption compared with approved thresholds.
- **Required automated tests:** Recompute aggregates from permitted events; detect missing days/small sample.
- **Security and reliability:** Do not hide outages or insufficient sample; document uncertainty.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-039-c"></a>

#### AR-039-C — Pilot exit and scope-change review

- **Objective:** Decide pilot readiness from complete customer and operating evidence. This task delivers pilot exit and scope-change review.
- **Implementation scope / PR boundary:** Review two-partner evidence, operator feedback, unresolved defects and research result with PM/SEC.
- **Out of scope:** No launch approval or silent target reduction.
- **Prerequisites:** [AR-039-B](#ar-039-b), [AR-038-C](#ar-038-c), [PILOTFIX0](#pilotfix0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** G5 accepted only with agreed metrics and no blocking defect; failure produces explicit replan.
- **Required automated tests:** Evidence completeness, denominator and blocker-status checks.
- **Security and reliability:** User/customer decisions required; no invented adoption/sign-off.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-040"></a>

### AR-040 — Establish measured forecast capacity and honest installation limits

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-040-a"></a>

#### AR-040-A — Forecast load model and benchmark harness

- **Objective:** Establish measured forecast capacity and honest installation limits. This task delivers forecast load model and benchmark harness.
- **Implementation scope / PR boundary:** Encode Section 5 baseline/forecast/burst mixes, artifact distributions, project skew and provider stub behavior.
- **Out of scope:** No target reduction after seeing results.
- **Prerequisites:** [AR-022-C](#ar-022-c), [AR-033-C](#ar-033-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C18; definitions and producer availability in the contract register.
- **Acceptance criteria:** Workload model and pass/fail SLIs frozen before performance runs; seed/hardware recorded.
- **Required automated tests:** Harness self-check for request mix, measured percentiles and forced saturation.
- **Security and reliability:** Synthetic data; no accidental paid model invocation during load.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-040-b"></a>

#### AR-040-B — Forecast load, burst and 24-hour soak

- **Objective:** Establish measured forecast capacity and honest installation limits. This task delivers forecast load, burst and 24-hour soak.
- **Implementation scope / PR boundary:** Run forecast workload, five-minute burst and 24-hour soak including worker loss.
- **Out of scope:** No extrapolation from single host to arbitrary fleet.
- **Prerequisites:** [AR-040-A](#ar-040-a), [AR-033-D](#ar-033-d), [SCALEFUNDS0](#scalefunds0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C18; definitions and producer availability in the contract register.
- **Acceptance criteria:** Report queue/latency/error/resource/cost results; configured caps survive overload and no evidence loss.
- **Required automated tests:** Automated SLI assertions, ledger audit, fairness and leak trend checks.
- **Security and reliability:** Spend and resource limits approved; load isolated from pilots.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-040-c"></a>

#### AR-040-C — Capacity bottleneck decision and repeatability pack

- **Objective:** Establish measured forecast capacity and honest installation limits. This task delivers capacity bottleneck decision and repeatability pack.
- **Implementation scope / PR boundary:** Identify dominant measured bottleneck and document supported installation sizing/limits.
- **Out of scope:** No unestimated rewrite of queue or database.
- **Prerequisites:** [AR-040-B](#ar-040-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C18; definitions and producer availability in the contract register.
- **Acceptance criteria:** Reproducible report plus prioritized remediation tasks; passing envelope clearly separated from failed targets.
- **Required automated tests:** Independent sample rerun and analysis arithmetic checks.
- **Security and reliability:** Performance fixes require new bounded reviewed tasks, not hidden scope.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-041"></a>

### AR-041 — Recover from zonal and dependency failures without duplicating logical work

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-041-a"></a>

#### AR-041-A — Zone failure and connection recovery contract

- **Objective:** Recover from zonal and dependency failures without duplicating logical work. This task delivers zone failure and connection recovery contract.
- **Implementation scope / PR boundary:** Define API/stateless worker failover, Cloud SQL reconnect, claim recovery and expected error budget impact.
- **Out of scope:** No regional active-active design.
- **Prerequisites:** [AR-019-C](#ar-019-c), [AR-021-C](#ar-021-c), [AR-033-C](#ar-033-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Runbook identifies all single-zone dependencies and safe failure modes.
- **Required automated tests:** Configuration/HA policy checks and simulated reconnect behavior.
- **Security and reliability:** No duplicate paid replay; stale workers fenced after failover.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-041-b"></a>

#### AR-041-B — Zonal, DB, object and provider outage drills

- **Objective:** Recover from zonal and dependency failures without duplicating logical work. This task delivers zonal, db, object and provider outage drills.
- **Implementation scope / PR boundary:** Inject approved staging zone/DB/object/provider failures and restore service with recorded timeline.
- **Out of scope:** No customer outage drill without separate agreement.
- **Prerequisites:** [AR-041-A](#ar-041-a), [AR-033-D](#ar-033-d), [SCALEFUNDS0](#scalefunds0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** Declared availability/recovery target met or specific gap blocks readiness.
- **Required automated tests:** Fault scripts, lease/ledger invariants and post-fault end-to-end consistency.
- **Security and reliability:** Scope fault privileges to staging; abort/runbook before injection.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-041-c"></a>

#### AR-041-C — Failover evidence and operator replay

- **Objective:** Recover from zonal and dependency failures without duplicating logical work. This task delivers failover evidence and operator replay.
- **Implementation scope / PR boundary:** Independent operator repeats representative failure/recovery using recorded runbook.
- **Out of scope:** No enterprise SLA based on a single drill.
- **Prerequisites:** [AR-041-B](#ar-041-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14; definitions and producer availability in the contract register.
- **Acceptance criteria:** No undocumented operator knowledge; all logical outcomes and reservations accounted.
- **Required automated tests:** Report verification, recovery-time calculation and repeated fault regression.
- **Security and reliability:** Private diagnostic retention and least-privilege emergency access.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-042"></a>

### AR-042 — Recover coherent evidence, identities, keys and deletion state after regional loss

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-042-a"></a>

#### AR-042-A — Regional recovery, key and deletion-journal contract

- **Objective:** Recover coherent evidence, identities, keys and deletion state after regional loss. This task delivers regional recovery, key and deletion-journal contract.
- **Implementation scope / PR boundary:** Define coherent DB/object/key backup set, off-region retention, deletion replay and restore ordering.
- **Out of scope:** No automatic cross-region replication of unapproved data.
- **Prerequisites:** [AR-016-D](#ar-016-d), [AR-032-C](#ar-032-c), [AR-035-C](#ar-035-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C19; definitions and producer availability in the contract register.
- **Acceptance criteria:** RPO/RTO and residency approved; no missing key/manifest/deletion dependency.
- **Required automated tests:** Backup manifest schema, version matching and retention/hold validation.
- **Security and reliability:** Backups encrypted and access-separated; enforce approved region/data policy.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-042-b"></a>

#### AR-042-B — Regional restore rehearsal and integrity checks

- **Objective:** Recover coherent evidence, identities, keys and deletion state after regional loss. This task delivers regional restore rehearsal and integrity checks.
- **Implementation scope / PR boundary:** Restore to isolated alternate approved region from recorded backups; recover keys and replay deletions.
- **Out of scope:** No production failover or destructive key removal.
- **Prerequisites:** [AR-042-A](#ar-042-a), [SCALEFUNDS0](#scalefunds0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C19; definitions and producer availability in the contract register.
- **Acceptance criteria:** Timed restore meets 15-minute RPO/4-hour RTO target or remains blocker; history/ledger verifies.
- **Required automated tests:** Missing/corrupt backup, unavailable key, restored tombstone and full workflow checks.
- **Security and reliability:** Restored identity/egress restricted before data access; no resurrection of deleted evidence.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-042-c"></a>

#### AR-042-C — Independent DR exercise and recovery evidence

- **Objective:** Recover coherent evidence, identities, keys and deletion state after regional loss. This task delivers independent dr exercise and recovery evidence.
- **Implementation scope / PR boundary:** Have secondary operator repeat restore from runbook and record recovery gap dispositions.
- **Out of scope:** No claim backup success equals recoverability.
- **Prerequisites:** [AR-042-B](#ar-042-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C19; definitions and producer availability in the contract register.
- **Acceptance criteria:** Independent drill passes target with source commit, timestamps and evidence inventory.
- **Required automated tests:** Automated backup age/integrity checks and recovery report validation.
- **Security and reliability:** Off-device private evidence retained; unique incident/release records preserved.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-043"></a>

### AR-043 — Publish only traceable verified releases and recover from compromised inputs

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-043-a"></a>

#### AR-043-A — Release artifact and provenance contract

- **Objective:** Publish only traceable verified releases and recover from compromised inputs. This task delivers release artifact and provenance contract.
- **Implementation scope / PR boundary:** Specify pinned dependency/image inputs, SBOM, attestations, signature verification and supported versions.
- **Out of scope:** No certification or production promotion.
- **Prerequisites:** [AR-012-B](#ar-012-b), [AR-013-C](#ar-013-c), [AR-033-C](#ar-033-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Release manifest links source/tests/images/config; verification policy reviewed with SEC.
- **Required automated tests:** Manifest/schema lint, unsigned artifact rejection and dependency pin checks.
- **Security and reliability:** Signing identity isolated from untrusted pull requests; no long-lived signing secrets.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-043-b"></a>

#### AR-043-B — Signed build and vulnerability gate pipeline

- **Objective:** Publish only traceable verified releases and recover from compromised inputs. This task delivers signed build and vulnerability gate pipeline.
- **Implementation scope / PR boundary:** Implement reproducible release pipeline, SBOM/provenance and severity/exception expiry policy.
- **Out of scope:** No assertion scanners find all vulnerabilities.
- **Prerequisites:** [AR-043-A](#ar-043-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Only verified reviewed sources publish signed candidates; blocked vulnerabilities cannot bypass gate.
- **Required automated tests:** Tampered artifact, untrusted PR, expired exception and scanner failure tests.
- **Security and reliability:** Least-privilege CI tokens; protect release credentials and provenance.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-043-c"></a>

#### AR-043-C — Supply-chain compromise and rollback rehearsal

- **Objective:** Publish only traceable verified releases and recover from compromised inputs. This task delivers supply-chain compromise and rollback rehearsal.
- **Implementation scope / PR boundary:** Exercise revoked build/signature, compromised dependency and recovery to trusted artifact.
- **Out of scope:** No exploit research outside authorized staging.
- **Prerequisites:** [AR-043-B](#ar-043-b), [AR-033-D](#ar-033-d). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Operator detects invalid provenance, stops rollout and restores verified compatible version.
- **Required automated tests:** Verification failure, key rotation/revocation and rollback regression.
- **Security and reliability:** Private vulnerability evidence; no malicious dependency execution in live environments.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-044"></a>

### AR-044 — Resolve independently identified security risks before enterprise release

M6 / P1 · 3 PRs · 8 engineering days · Not started

<a id="ar-044-a"></a>

#### AR-044-A — Independent assessment scope and booking brief

- **Objective:** Resolve independently identified security risks before enterprise release. This task delivers independent assessment scope and booking brief.
- **Implementation scope / PR boundary:** Define authorized API/auth/storage/worker/CI scope, assessor access, exclusions, timing and retest window.
- **Out of scope:** No security assessment performed or vendor purchased.
- **Prerequisites:** [AR-003-A](#ar-003-a), [AR-034-A](#ar-034-a), [AR-043-A](#ar-043-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** SEC/PM approve brief and select independent assessor; funding/lead-time tracked separately.
- **Required automated tests:** Scope inventory and evidence access checks; mandatory surfaces cannot be omitted.
- **Security and reliability:** No production secrets in assessment pack; assessor least privilege and retention terms.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-044-b"></a>

#### AR-044-B — Assessment finding triage and bounded remediation tickets

- **Objective:** Resolve independently identified security risks before enterprise release. This task delivers assessment finding triage and bounded remediation tickets.
- **Implementation scope / PR boundary:** Map actual assessor findings to severity, exploit path, owner, fix PR, regression test and retest criterion.
- **Out of scope:** No promise all unknown remediation fits this estimate.
- **Prerequisites:** [AR-044-A](#ar-044-a), [AUDIT0](#audit0), [AR-034-C](#ar-034-c), [AR-043-C](#ar-043-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Every finding has disposition; critical/high exploitable issues block G6; estimates revised using findings.
- **Required automated tests:** Finding import/dedup and severity/closure evidence completeness checks.
- **Security and reliability:** Private details stay private until disclosure approved; no risk acceptance for prohibited blockers.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-044-c"></a>

#### AR-044-C — Independent security retest and closure record

- **Objective:** Resolve independently identified security risks before enterprise release. This task delivers independent security retest and closure record.
- **Implementation scope / PR boundary:** Provide fixed candidate to independent assessor and verify original exploits plus regressions.
- **Out of scope:** No compliance certification or automatic risk acceptance.
- **Prerequisites:** [AR-044-B](#ar-044-b), [SECFIX0](#secfix0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Assessor confirms no unresolved critical/high exploitable finding; residual policy-allowed risks accepted by owner.
- **Required automated tests:** Re-run finding-specific regression tests and evidence verification.
- **Security and reliability:** Do not close from developer assertion; retain private report and disclosure restrictions.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-045"></a>

### AR-045 — Make customer procurement claims match implemented and verified controls

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-045-a"></a>

#### AR-045-A — Customer audit, identity and data evidence pack

- **Objective:** Make customer procurement claims match implemented and verified controls. This task delivers customer audit, identity and data evidence pack.
- **Implementation scope / PR boundary:** Assemble verified control map, audit sample, data-flow/processor/retention record and support limitations.
- **Out of scope:** No SOC 2/ISO certification or legal guarantee.
- **Prerequisites:** [AR-032-C](#ar-032-c), [AR-034-C](#ar-034-c), [AR-035-C](#ar-035-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C13, C15, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Every control links evidence or is marked unavailable; no claimed certification.
- **Required automated tests:** Artifact link/checksum, redaction and required control coverage checks.
- **Security and reliability:** Share only authorized customer evidence; no secrets/raw third-party source.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-045-b"></a>

#### AR-045-B — Enterprise identity and procurement gap decision

- **Objective:** Make customer procurement claims match implemented and verified controls. This task delivers enterprise identity and procurement gap decision.
- **Implementation scope / PR boundary:** Review required controls with two partners; decide whether SCIM or other gaps block target contract.
- **Out of scope:** No unplanned SCIM implementation.
- **Prerequisites:** [AR-045-A](#ar-045-a), [AR-036-C](#ar-036-c), [AR-037-C](#ar-037-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C15, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Record customer requirement, scope decision and separate estimated tasks if needed.
- **Required automated tests:** Contract requirement-to-evidence completeness and role matrix review.
- **Security and reliability:** Do not imply current OIDC meets unreviewed procurement controls.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-045-c"></a>

#### AR-045-C — Customer evidence delivery and approval record

- **Objective:** Make customer procurement claims match implemented and verified controls. This task delivers customer evidence delivery and approval record.
- **Implementation scope / PR boundary:** Prepare bounded customer-safe package and record actual customer/security dispositions.
- **Out of scope:** No closing procurement by engineering assertion.
- **Prerequisites:** [AR-045-B](#ar-045-b), [AR-044-C](#ar-044-c), [PROCURE0](#procure0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Accepted packet or explicit unresolved blocker; scoped obligations trace to release/runbooks.
- **Required automated tests:** Export permissions, redaction and version consistency checks.
- **Security and reliability:** No disclosure of one customer's evidence to another.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-046"></a>

### AR-046 — Provide funded, practiced incident response with primary and secondary coverage

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-046-a"></a>

#### AR-046-A — SLO dashboards and actionable alerts

- **Objective:** Provide funded, practiced incident response with primary and secondary coverage. This task delivers slo dashboards and actionable alerts.
- **Implementation scope / PR boundary:** Implement documented admission/queue/runtime/error/budget SLIs and actionable error-budget alerts.
- **Out of scope:** No promised 24/7 support without staffing.
- **Prerequisites:** [AR-011-C](#ar-011-c), [AR-033-C](#ar-033-c), [AR-040-A](#ar-040-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C18; definitions and producer availability in the contract register.
- **Acceptance criteria:** Each alert has owner, threshold, runbook and bounded label cardinality; thresholds derived from plan.
- **Required automated tests:** Metric fixtures, alert firing/recovery and notification routing tests.
- **Security and reliability:** No source/PII in labels; restrict operational dashboards.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-046-b"></a>

#### AR-046-B — Primary and secondary incident runbooks

- **Objective:** Provide funded, practiced incident response with primary and secondary coverage. This task delivers primary and secondary incident runbooks.
- **Implementation scope / PR boundary:** Write practiced incident triage, provider uncertainty, key loss, customer communications and escalation procedures.
- **Out of scope:** No unilateral customer messaging or unsupported SLA.
- **Prerequisites:** [AR-046-A](#ar-046-a), [AR-041-C](#ar-041-c), [AR-042-C](#ar-042-c), [SUPPORT0](#support0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C19; definitions and producer availability in the contract register.
- **Acceptance criteria:** Named primary/secondary coverage and severity response expectations accepted.
- **Required automated tests:** Runbook command smoke, access checks and escalation routing fixtures.
- **Security and reliability:** Break-glass access audited and time-bounded; redact communications.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-046-c"></a>

#### AR-046-C — Operator game day and support acceptance

- **Objective:** Provide funded, practiced incident response with primary and secondary coverage. This task delivers operator game day and support acceptance.
- **Implementation scope / PR boundary:** Run secondary-led outage/recovery drill and evaluate detection, response, accounting and evidence retention.
- **Out of scope:** No fatigue-free on-call assumption.
- **Prerequisites:** [AR-046-B](#ar-046-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C19; definitions and producer availability in the contract register.
- **Acceptance criteria:** Both operators can execute within agreed targets; unresolved operational gaps block G6.
- **Required automated tests:** Incident event/time assertions, alert routes and restored workflow verification.
- **Security and reliability:** Staging-only fault budget; preserve required incident evidence privately.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-047"></a>

### AR-047 — Prove supported upgrades and audit actual enterprise readiness evidence

M6 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-047-a"></a>

#### AR-047-A — Supported version and upgrade compatibility matrix

- **Objective:** Prove supported upgrades and audit actual enterprise readiness evidence. This task delivers supported version and upgrade compatibility matrix.
- **Implementation scope / PR boundary:** Define supported N/N-1 readers, API/SDK/adapter/image/DB combinations and safe rollback boundary.
- **Out of scope:** No unlimited backwards compatibility.
- **Prerequisites:** [AR-005-C](#ar-005-c), [AR-033-D](#ar-033-d), [AR-043-B](#ar-043-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Unsupported versions rejected; tested upgrade path and write compatibility explicit.
- **Required automated tests:** Matrix generation/coverage, incompatible revision and legacy event digest tests.
- **Security and reliability:** No unsafe downgrade; retain backup and key dependencies.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-047-b"></a>

#### AR-047-B — Upgrade, rollback and interrupted migration rehearsal

- **Objective:** Prove supported upgrades and audit actual enterprise readiness evidence. This task delivers upgrade, rollback and interrupted migration rehearsal.
- **Implementation scope / PR boundary:** Exercise supported upgrade/rollback on realistic synthetic history, active jobs drained and partial migration faults.
- **Out of scope:** No production migration execution.
- **Prerequisites:** [AR-047-A](#ar-047-a), [AR-032-C](#ar-032-c), [AR-043-C](#ar-043-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04, C13, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Data, scopes, ledger and old evidence survive; failed rollback restores coherent backup.
- **Required automated tests:** N/N-1 full matrix, interruption, future writer and restored deletion cases.
- **Security and reliability:** No live destructive schema test; preserve audit/evidence continuity.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-047-c"></a>

#### AR-047-C — Enterprise readiness evidence assembly

- **Objective:** Prove supported upgrades and audit actual enterprise readiness evidence. This task delivers enterprise readiness evidence assembly.
- **Implementation scope / PR boundary:** Audit every requirement against actual commit/environment evidence with pass/fail/not-tested disposition.
- **Out of scope:** No final launch authorization.
- **Prerequisites:** [G5](#g5), [AR-040-C](#ar-040-c), [AR-041-C](#ar-041-c), [AR-042-C](#ar-042-c), [AR-044-C](#ar-044-c), [AR-045-C](#ar-045-c), [AR-046-C](#ar-046-c), [AR-047-B](#ar-047-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** All mandatory G6 evidence fresh and reviewed; scoped residual risks have authorized owner.
- **Required automated tests:** Evidence checksum/link, requirement coverage and release identity checks.
- **Security and reliability:** No written-plan substitution for test or independent review; no unearned readiness claim.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-048"></a>

### AR-048 — Prepare a supported release that an independent operator can use

M7 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-048-a"></a>

#### AR-048-A — Supported release, installation and limitations package

- **Objective:** Prepare a supported release that an independent operator can use. This task delivers supported release, installation and limitations package.
- **Implementation scope / PR boundary:** Publish release candidate notes, supported matrix, installation/upgrade/recovery guide and honest product limits.
- **Out of scope:** No wider architecture expansion.
- **Prerequisites:** [G6](#g6), [AR-047-C](#ar-047-c), [AR-043-C](#ar-043-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Independent engineer can identify compatibility, cost/retention constraints and claim boundary.
- **Required automated tests:** Documentation examples, config validation and supported-version consistency checks.
- **Security and reliability:** No credentials/private findings in public docs; evidence claims traceable.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-048-b"></a>

#### AR-048-B — Independent onboarding and support rehearsal

- **Objective:** Prepare a supported release that an independent operator can use. This task delivers independent onboarding and support rehearsal.
- **Implementation scope / PR boundary:** Have new operator install candidate and run standard recovery/support request from docs.
- **Out of scope:** No customer production launch.
- **Prerequisites:** [AR-048-A](#ar-048-a), [AR-046-C](#ar-046-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** No undocumented prerequisite or privilege escalation; issues resolved with bounded follow-up.
- **Required automated tests:** Clean-room install, failed setup, support routing and rollback checks.
- **Security and reliability:** Use approved synthetic tenant and scoped credentials.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-048-c"></a>

#### AR-048-C — Release acceptance and launch decision packet

- **Objective:** Prepare a supported release that an independent operator can use. This task delivers release acceptance and launch decision packet.
- **Implementation scope / PR boundary:** Record TL/PL/QE/SEC/RS/customer sign-offs, residual risk, canary scope and rollback triggers.
- **Out of scope:** No rollout before LAUNCH0.
- **Prerequisites:** [AR-048-B](#ar-048-b), [AR-045-C](#ar-045-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Required signatures and verified artifact identity complete; user decides launch.
- **Required automated tests:** Release manifest and gate completeness checker rejects stale/missing evidence.
- **Security and reliability:** No automatic sign-off; private evidence index with access owner.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-049"></a>

### AR-049 — Launch in bounded cohorts with observable rollback criteria

M7 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-049-a"></a>

#### AR-049-A — Canary deployment and bounded traffic verification

- **Objective:** Launch in bounded cohorts with observable rollback criteria. This task delivers canary deployment and bounded traffic verification.
- **Implementation scope / PR boundary:** Deploy verified release to approved canary scope with health/error/budget/research integrity checks.
- **Out of scope:** No simultaneous all-customer rollout.
- **Prerequisites:** [AR-048-C](#ar-048-c), [LAUNCH0](#launch0). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Canary holds within agreed limits or rolls back; running jobs/ledger remain consistent.
- **Required automated tests:** Canary workflow, fault trigger, artifact verification and rollback rehearsals.
- **Security and reliability:** Explicit customer scope and deploy authority; no broader promotion.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-049-b"></a>

#### AR-049-B — Progressive promotion and rollback acceptance

- **Objective:** Launch in bounded cohorts with observable rollback criteria. This task delivers progressive promotion and rollback acceptance.
- **Implementation scope / PR boundary:** Promote staged customer cohorts only after observed canary gate; maintain version/rollback record.
- **Out of scope:** No unapproved region/customer expansion.
- **Prerequisites:** [AR-049-A](#ar-049-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C14, C16; definitions and producer availability in the contract register.
- **Acceptance criteria:** Each cohort accepted or halted independently; failed cohort cannot trigger blind next promotion.
- **Required automated tests:** Promotion gate, rollback trigger, job drain and compatibility checks.
- **Security and reliability:** Maintain audit trail and customer operator contacts.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-049-c"></a>

#### AR-049-C — Launch operating baseline and customer handoff

- **Objective:** Launch in bounded cohorts with observable rollback criteria. This task delivers launch operating baseline and customer handoff.
- **Implementation scope / PR boundary:** Verify supported customer journeys, alert/support ownership and baseline adoption/cost metrics.
- **Out of scope:** No assumption 30-day review already passed.
- **Prerequisites:** [AR-049-B](#ar-049-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C16, C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Operators accept release and timestamp establishes post-launch review window.
- **Required automated tests:** Post-deploy end-to-end smoke, alert routing and metrics completeness.
- **Security and reliability:** No secret/payload leakage in release evidence; support coverage active.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-050"></a>

### AR-050 — Use the first month of production evidence to decide what comes next

M7 / P1 · 3 PRs · 10 engineering days · Not started

<a id="ar-050-a"></a>

#### AR-050-A — Thirty-day operating evidence and adoption analysis

- **Objective:** Use the first month of production evidence to decide what comes next. This task delivers thirty-day operating evidence and adoption analysis.
- **Implementation scope / PR boundary:** Analyze at least 30 calendar days of SLOs, incidents, budgets, compatibility and weekly use.
- **Out of scope:** No automatic success declaration from elapsed time.
- **Prerequisites:** [AR-049-C](#ar-049-c), [D30](#d30). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** All days/attempts accounted; results compared with approved goals and uncertainty.
- **Required automated tests:** Metrics recomputation, missing telemetry and incident/cost reconciliation checks.
- **Security and reliability:** Privacy-preserving aggregates; no cherry-picked customer outcomes.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-050-b"></a>

#### AR-050-B — Post-launch incident and product decision review

- **Objective:** Use the first month of production evidence to decide what comes next. This task delivers post-launch incident and product decision review.
- **Implementation scope / PR boundary:** Review operational failures, useful-location results and customer feedback with named owners.
- **Out of scope:** No open-ended new implementation.
- **Prerequisites:** [AR-050-A](#ar-050-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Prioritized fixes/risks and scope decisions recorded; owners accept follow-ups.
- **Required automated tests:** Evidence-to-action completeness and blocker-status checks.
- **Security and reliability:** No undocumented risk acceptance; required incident evidence retained.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-050-c"></a>

#### AR-050-C — G7 closure and next-quarter backlog proposal

- **Objective:** Use the first month of production evidence to decide what comes next. This task delivers g7 closure and next-quarter backlog proposal.
- **Implementation scope / PR boundary:** Record launch review disposition and propose demand-backed next priorities with contracts/estimates.
- **Out of scope:** No implementation of next-quarter candidates.
- **Prerequisites:** [AR-050-B](#ar-050-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C17; definitions and producer availability in the contract register.
- **Acceptance criteria:** Product/security/research/operators accept closure or explicit blocker; expansion remains separately gated.
- **Required automated tests:** Gate record and backlog dependency/estimate validation.
- **Security and reliability:** No shared SaaS/network trust expansion without new approved design.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.


<a id="ar-051"></a>

### AR-051 — Secure continuous integration and verify traceable installable candidates

M1 / P0 · 1 PR · 2 engineering days · Verified · [Tracking issue #26](https://github.com/spei04/agent-rewind/issues/26)

<a id="ar-051-a"></a>

#### AR-051-A — Secure CI and verify installable release candidates

- **Objective:** Make integration checks mandatory and produce traceable installable main candidates without granting pull requests publication authority.
- **Implementation scope / PR boundary:** Preserve lint, format, types, Python compatibility, unit/PostgreSQL/gVisor and package checks. Pin actions and infrastructure inputs, use read-only tokens and frozen dependencies, add static/dependency scans and bounded Dependabot updates. Always run CI gate over every required job. Successful main checks build wheel/sdist candidates, install outside checkout, verify import provenance/archive allowlists, and retain checksums/source/lock identity with promotion/rollback instructions.
- **Out of scope:** No package publication, production deployment, paid services, model calls or repository-settings mutations. AR-043 retains signed releases, SBOM/attestation and broader supply-chain acceptance.
- **Prerequisites:** [E0](#e0), [AR-004-A](#ar-004-a), [AR-003-A](#ar-003-a), all verified before assignment. G1 consumes this delivery evidence.
- **Required contracts:** C03 reviewed trust boundaries and AR-004-A baseline inventory.
- **Acceptance criteria:** Independently reviewed exact PR commit passes required checks; failed, skipped or cancelled prerequisites fail CI gate. Successful main run produces only allowlisted installable candidate files with recorded identities. PRs have no privileged trigger, secrets, delivery uploads or write token. Applicable advisories receive tested fixes, with final alert state and limitations recorded.
- **Required automated tests:** Workflow negatives for missing/skipped/cancelled gates and PR delivery; installed wheel/sdist smoke outside checkout with module provenance; archive/path allowlist rejection; lint/type/unit/PostgreSQL/gVisor and supported Python jobs; frozen dependency audit without blanket ignores; actual main artifact-generation evidence.
- **Security and reliability:** Verified full-SHA actions, immutable Postgres/runsc, no persisted checkout credentials, explicit token permissions, bounded jobs/retention/update cadence and PR concurrency without cancelling active main delivery. No credentials/private evidence in archives. Main-only delivery does not establish branch protection; settings need separate read-back.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; B implements, A independently reviews, lead integrates.
- **Definition of done:** Task acceptance, exact-commit independent review, successful PR checks and actual main candidate run with safe evidence; roadmap/backlog and issue updated. This does not close AR-043 or authorize production.
- **Progress:** Verified via PR #29 and actual protected-main delivery; [evidence record](delivery/CI_EVIDENCE_2026-10-20.md).

## Highest-risk assumptions and decisions requiring approval

| Decision / risk | Recommendation | Needed before / owner |
| --- | --- | --- |
| Execution authority | E0 and development-only ARCH0/G0 accepted. Continue approved migration and CI slices; future milestone/external gates remain applicable. | Recorded in G0_DECISION.md; no repeat approval required |
| Actual staffing and delivery rate | Use the three active contributor slots and measured review throughput; six logical role totals do not imply six human hires. Reforecast unscheduled M1 and research consumers when capacity is assigned; no launch date commitment. | E0 staffing; Day 10/G1 reforecast — product owner/TL |
| Recurring cloud/identity operations | Retain accepted single-organization self-hosted GCP/gVisor direction. Choose region, cloud budget owner/cap, test IdP and funded support hours. Development VM access does not supply these. | ENV0/IDP0/SUPPORT0 — product owner/PL/customer admin |
| Affordable valid research | Retain the existing $200 validation cap; reconcile before smoke. Approve the natural-failure study budget only after sample/power/permission review; narrow the claim if unaffordable or underpowered. | PAID0, DATA0, STUDYFUNDS0 — RS/data owner/product owner |
| Customer availability and scope | Use two design partners for the first pilot, each with permitted restorable workflows; both weekly users and both adopting a regression/policy fix is the proposed exit target. Recruit a third only as separately funded expansion. | PARTNER0/PILOT0/G5 — PM/customers |
| Independent review and unknown fixes | Fund an assessor and independent statistical reviewer; book early. Do not accept unresolved critical/high exploitable defects or missing restoration evidence to meet a date. New findings receive scoped fix tasks and revised estimates. | AUDIT0/SECFIX0/G6 — product owner/SEC/RS |

No question above asks to reapprove accepted architecture or issue #51 choices. The nine selected engineering scopes and calibration targets are approved; optional adapters/reuse, held-out execution, actual study funding/data, independent statistics and production remain separate.

## Dependency review, progress and maintenance

Current dependency validation, 2026-10-21: **151 aggregate tasks, 159 planned delivery PRs, 52 parents, 544 acyclic edges, 27 gates and 20 contracts**. Base **464 days**, upper **784.6**, alternate 25% allowance **580**; M1 **65.5**, M3 **81**, RS **66**, PL **90**, BE **97.5**, QE **112.5**. The effort-only path is **176.5 days**. Run the execution checker for task/card/parent/schedule and producer ancestry, and the evaluation-design checker for the immutable historical proposal plus actual approval overlay. Neither proves runtime behavior or independent statistical approval.

Issues #1–5/#7/#8/#9 are closed for their recorded internal scope; parent #6/#10/#11/#12 remain open. AR-008-B/P2 #95 and aggregate #93 are Verified after reviewed source 065df8c89da384d6e502cf0c15bf174e380c53c7, protected merge cefd222230c800eb2e90c49a3b3c411b394d0393, matching PR/main runs 39683408934/39686498691 (attempt 1) and verified candidate 12387716715. P1 #94 retains accepted merge 03a8e074b51dca7c03d69295e0c18ca0f22dc1da and candidate 12355648523. Parent #8 is Verified/closed. AR-010-A/P1 #108, aggregate #107 and parent #10 are In progress after the explicit lead handoff to platform/security in the existing secondary checkout, work/ledger-schema, from 9f6ea6e. P1 entry policy 51af77dc and the HTTP prerequisite are accepted. P1 product proof and acceptance remain pending; P2 #109 is Not started/null acceptance behind accepted P1 and its own exact reservation/fence entry review. Schema b2e19be and bounded operator 80023cbc are independently accepted internal checkpoints. The 100-case independent SQLite/factory/lifecycle selection passes on both Python versions; native PostgreSQL evidence is separately reviewed. Platform/security implements only the reviewed private transaction-body guard in the reused secondary; delivery prepares independent controls, while planning/verification preserves hosted evidence for draft PR #111. Full reader traversal awaits explicit observed paging and work-budget review. Inspection, provisioning, recovery and full P1 delivery remain unaccepted. Previous accepted implementation issues remain closed, and earlier failed attempts stay in their dated delivery records. AR-006-C and both AR-011-C packages wait for AR-010-B. RA-01-A/B and #51 retain their accepted engineering/design scope; external execution gates remain open. Exact task/gate dependencies, not coarse parent relationships, control assignment.

Update procedure for each completed PR: update task status and evidence in the machine-readable ledger and this card; recalculate parent/milestone effort/status and dependency changes; update PLAN Section 10/14 and the matching issue; rerun ID/required-field/DAG/contract-availability/first-fortnight allocation checks; verify local links and draft OpenAPI structure. Any added edge, new gate or changed estimate requires schedule revalidation. Do not mark a task Verified without applicable commit/environment evidence, reviewer disposition and explicit limitations.

| Date | Planning progress | Implementation progress / next action |
| --- | --- | --- |
| 2026-10-19 | Review findings resolved into proposed backlog; 145 task cards, task-level dependencies, contracts/gates, conditional daily schedule and milestone rollups prepared and checked. | All execution tasks Not started. Product owner reviews E0 approval scope and unresolved decisions. |

| 2026-10-19 | E0 approved by project owner; three independent contributor assignments started. | AR-001-A, AR-004-A and AR-005-A in progress; task-specific gates remain applicable. |

Execution dependency review, 2026-10-19: added AR-011-A and AR-012-A before AR-004-B, and AR-005-C before AR-011-B. All 514 edges resolve; graph, producer ancestry, day-by-day ordering and role capacity rechecked. Total effort remains 427 days; the longest effort path increases from 145.5 to 146 days. AR-012-A is verified at merged 8c3a7b9; its 24 runtime cases remain planned.

Contract-consumer dependency review, 2026-10-19: AR-009-A now waits for the AR-011-B bounded byte-read primitive. All 515 edges, contract ancestors and conditional schedule pass; total effort remains 427 days, longest effort path is 146.5 days (about 41.9 workweeks at the stated availability, excluding contention/waits). Previous 514-edge checkpoint remains historical.

G0 execution checkpoint, 2026-10-19: AR-004-B/C verified; ARCH0/G0 satisfied for development/testing under existing owner authority. First runtime assignment is AR-005-B, followed by AR-005-C; AR-033-A configuration may proceed in parallel. No new deployment/spending/data approval is inferred.

2026-10-20 priority checkpoint: B owns AR-051-A secure CI/candidates, A reviews CI/dependencies, C implements AR-005-B in issue #28. PR #25 records explicit build/test authorization; PR #27 updates cryptography after independent compatibility/advisory review and exact-head core/gVisor success. No production, model spending or customer-data gate was opened.

2026-10-20 delivery checkpoint: AR-051-A verified at merged 13465c1 with independent exact-head review, protected-main run 39346262029 and artifact 12230273836. A reassigned to AR-033-A (issue #30), B to independent AR-005-B review, C continues migration. Migration review exposed the legacy application-superuser assumption; the scoped C04 adoption erratum adds explicit retired writer roles and real exclusion tests. No production gate closes.

2026-10-20 configuration checkpoint: AR-033-A verified in PR #36 at 4abc352 after independent B review and hosted locked checks. C14 now includes process/overflow connection bounds and safe regular-file loading. A reassigned to complementary migration CLI/input/package review; B owns catalog/transaction acceptance, C implements fixes. AR-005-C still waits for accepted AR-005-B; AR-033-B still waits for ENV0.

2026-10-20 migration integration: AR-005-B verified in PR #35 at 385e5ecf; AR-005-C starts only after that merge. C runtime guards and A recovery work own disjoint files in reused checkouts; B independently reviews both for one coherent integration. PostgreSQL backup/restore evidence remains pending, distinct from the already executed transaction/process-death rollback tests. Parent #5 remains open; G1 and customer admission are not accepted.

AR-005-C acceptance clarification: the reviewed C04 adoption profile is migration-only. Demonstrate supported inspection-reader compatibility and real backup restoration; do not label an old unguarded application a customer-serving rollback target. A future active-release rollback pair needs its own approved compatibility profile and deployment evidence.

2026-10-20 guard/recovery integration: AR-005-C and parent AR-005 verified in PR #39, merge 0737c7b, after exact 94dd9cb internal review and run 39350413566 (758 tests per Python version; 58 PostgreSQL and 3 gVisor cases). [Acceptance evidence](delivery/GUARD_RECOVERY_EVIDENCE_2026-10-20.md) distinguishes actual backup/restore from transactions, narrowly documented cast equivalence and customer-serving rollback refusal. C begins AR-007-A (#40); A begins AR-011-B (#41); B reviews both, using existing checkouts. Their exact prerequisites are now satisfied. No other gate or task status is promoted.

<a id="ra-01"></a>

## Research amendment RA-01

Historical initial design authorization (superseded for the selected engineering scope by the owner decision above): on 2026-10-20 the owner approved the fixed total-budget confirmed-repair objective and **4–7 engineering days of audit/protocol design**. The original claim correction and four primary-source references remain in [PLAN Section 7](PLAN.md#7-research-and-evaluation-program). RA-01-A/B now belong to the active ledger; they add 4 base days and 7 upper-range days to the historical 146-task/429-day baseline. No method is treated as reproduced from reading its paper. No runtime/adapters/algorithm expansion, threshold/power choice, new spending or partner data is approved by this activation.

| Producer / consumer | Required handoff |
| --- | --- |
| RA-01-A → C20 → RA-01-B | Accepted primary-source/implementation/license/semantics audit, available after PR #49 review and integration. |
| RA-01-B → C21 → AR-020-A/C08 and AR-024-A/C09 | Accepted evaluation-design amendment plus satisfied RESEARCHSCOPE0 before original schema/statistical producers start. C21 is not those runtime interfaces. |
| AR-024-C, AR-025-A/B/C, AR-026-A, AR-038-A/B/C | Existing producer paths now include RA-01-B transitively. Original runtime, holdout, DATA0/STUDYFUNDS0 and independent statistical gates remain. |
| Remaining M1 | Ownership/readiness are verified; unscheduled approved queue and review contention are reforecast separately. |

<a id="ra-01-a"></a>

### RA-01-A — Prior-method novelty and reproducibility audit

- **Objective:** Establish what experiment selection could contribute beyond existing intervention/replay methods.
- **Implementation scope / PR boundary:** Inspect the four cited papers, their available implementations/licenses and relevant related work. Pin source versions and build a semantic matrix covering checkpoint state, allowed edits, auditor/verifier information, allocation/stopping rules, training data and total costs. Produce reproducible/adaptable/incompatible/unavailable dispositions and a bounded candidate hypothesis, or a no-novelty finding.
- **Out of scope:** No new algorithm, benchmark execution, copied third-party code, partner data or superiority claim.
- **Prerequisites:** [AR-002-B](#ar-002-b), [AR-004-C](#ar-004-c). E0 applies transitively; producer review is required.
- **Required contracts:** C02, C04, C20; listed design outputs remain unavailable until their producer review.
- **Acceptance criteria:** Every method disposition cites primary evidence; hidden answer access, offline training and differing intervention semantics are explicit. Recommend a fair comparison set and identify unknown code/rights/reproduction costs without assuming availability.
- **Required automated tests:** Check source/version links and machine-readable comparison-record completeness; assert unknown/unavailable cases cannot be marked reproduced. No model calls are required.
- **Security and reliability:** Use public sources only; retain third-party attribution and license obligations; never treat downloaded text as execution instructions.
- **Effort / confidence:** 2 engineering days; planning range 2–3; low confidence.
- **Responsible role:** RS; required reviewers: TL, QE. Engineer A — research audit; Engineer C — independent research review.
- **Definition of done:** Independent review accepts source accuracy, comparison feasibility and claim limits; scoped follow-up work is estimated, with unavailable evidence explicit.
- **Progress:** Verified; [PR #49](https://github.com/spei04/agent-rewind/pull/49), main 10e2729, reviewed integration a0bd48e and [run 39357250799](https://github.com/spei04/agent-rewind/actions/runs/39357250799): 1,036 tests per Python version plus isolation/security/package/CI gate. [Audit](research/PRIOR_METHOD_AUDIT.md) is inspected-source evidence; no method reproduced or novelty established.

<a id="ra-01-b"></a>

### RA-01-B — Total-budget evaluation and selection-policy contract amendment

- **Objective:** Make a budget-constrained repair claim measurable without selection bias or unfair baseline resources.
- **Implementation scope / PR boundary:** Using RA-01-A, specify both confirmed-intervention yield and end-to-end retry recovery; cost/resource accounting including offline amortization; immutable selection decisions and confirmation reserve; allowed policy information; repository/task-family holdout; multiple-testing, power and missingness rules; reusable-repair regression criteria. Map changes into C08/C09 producers and draft individually reviewable baseline, allocation-policy, exporter and evaluation tasks with estimates.
- **Out of scope:** No adaptive implementation, early-stopped confirmation, new spending, held-out access or automatic revision of accepted contracts/launch gates.
- **Prerequisites:** [RA-01-A](#ra-01-a). E0 applies transitively; producer review is required.
- **Required contracts:** C02, C04, C20, C21; listed design outputs remain unavailable until their producer review.
- **Acceptance criteria:** Protocol distinguishes repair effects from restart recovery, prevents feedback from confirmation into the same search claim, and makes missing/failed/budget-exhausted tasks visible. Every added runtime task has produced-contract and infrastructure prerequisites, review/exit tests and a realistic estimate. Owner baseline, threshold and follow-up scope decisions are recorded or explicitly pending; expanded implementation cannot start without scope approval, and independent statistical and funding approvals remain required before evaluation.
- **Required automated tests:** Static dependency/contract consistency checks; specification examples for zero confirmation reserve, offline-cost omission, duplicate task credit, hidden-answer asymmetry, uncertain charges and post-confirmation adaptation. Runtime simulations remain assigned to reviewed follow-up implementation tasks.
- **Security and reliability:** No hidden grader/held-out leakage; immutable provenance and full charge ledger; existing DATA0/STUDYFUNDS0 and confirmation invariants retained.
- **Effort / confidence:** 2 engineering days; planning range 2–4; low confidence.
- **Responsible role:** RS; required reviewers: TL, QE. Engineer A authors; C reviews scientific semantics; B reviews accounting and dependencies.
- **Definition of done:** Independent internal review accepts the protocol/design; owner baseline, threshold and follow-up scope decisions are recorded or explicitly left pending. Active DAG and estimates reflect only approved work; no consumer starts before its producer. Independent statistical approval remains required before funded evaluation.
- **Progress:** Verified for internal design scope; [PR #50](https://github.com/spei04/agent-rewind/pull/50), accepted source d84eb0e and integrated 80098a8, [hosted run 39359376626](https://github.com/spei04/agent-rewind/actions/runs/39359376626): 1,188 tests per Python version plus isolation/security/package/CI gate. B/C accepted accounting, scientific and design-checker boundaries; lead passed 219 combined targeted cases. The unchanged historical C21 retains fourteen proposed work packages; actual owner [decision #51](https://github.com/spei04/agent-rewind/issues/51) now selects nine engineering scopes through the separate reconciliation. External review and execution gates remain. PR #50 merged at 555d28c after final matching-head run 39359708075.

Dependency audit: the historical 527-edge design ledger becomes 538 edges / 150 tasks after reconciliation. No original edge is removed. Full accounting at AR-023-C precedes selection; unchanged AR-024-C precedes the comparator and separate AR-024-D harness, then AR-026-A feasibility review. Base increases by 7 to 440 days, upper by 14 to 744.6, and the effort-only path by 6 to 152.5. M3 rises to 81; M5 remains 50 with unresolved execution/calibration uncertainty.

Remaining owner decisions concern deferred adapters/reuse/held-out execution and actual study funding; selected core engineering choices need no repeat approval. Independent statistical approval, permitted data and evidence of feasibility remain required. Null findings and narrower claims remain valid.

2026-10-20 audit handoff: RA-01-A and C20 accepted in PR #49, main 10e2729, after corrected exact-head hosted checks. A begins RA-01-B; C owns scientific review and B accounting/dependency review. The existing 148-task/524-edge/433-day design ledger is unchanged in size; future runtime proposals remain outside it.

2026-10-20 owner-decision guard: RESEARCHSCOPE0 is Not satisfied and waits for RA-01-B. AR-020-A and AR-024-A now depend on it, preventing internally reviewed design from being mistaken for owner approval of baselines, thresholds, nested evaluation or expanded scope. The defensive change yields 527 edges / 27 gates; task counts, 433 base days and the 146.5-day effort path are unchanged. Proposed runtime work remains outside the active ledger.

2026-10-20 protocol proposal: [C21 design and 14 follow-up cards](research/TOTAL_BUDGET_PROTOCOL.md) specify fair recovery/intervention endpoints, complete physical and comparison costs, sealed fresh confirmation and proposed thresholds. Source b8b2cba is under final checker review. Follow-up effort is classified by overlap with existing tasks; no automatic addition to the 433-day ledger. RESEARCHSCOPE0 remains Not satisfied.

2026-10-20 approved implementation reconciliation: [actual decision and mapping](research/OWNER_DECISION_2026-10-20.md) activates only the nine approved scopes; C21 proposal bytes remain historical and unchanged. New AR-025-D is the standard comparator; AR-024-D makes the selected-policy harness independently reviewable after the unchanged baseline simulator. No original work or prerequisite was removed. A/009-A and C/007-B are In progress after verified dependencies; B owns reconciliation and independent review.

2026-10-20 scoped repositories accepted: AR-007-B Verified in PR #54, main 9b33ddd, after A/B review through 2a3c52d and hosted run 39364339490 (1,281 tests per Python version, actual PostgreSQL cases, three gVisor cases and security/package/CI gate). Review corrected SQL revocation/finite metadata boundaries and post-storage authorization. AR-009-A remains under integration; C reuses its checkout to combine its accepted fixture drain fix with A storage. No new provider calls or resources. Full route isolation and customer admission remain gated.

2026-10-20 artifact primitives accepted: AR-009-A Verified in [PR #55](https://github.com/spei04/agent-rewind/pull/55), merged at b42b5aba60ffb58635f71d3f4a616b4ade36334d. B independently accepted A's storage corrections through 24096f7 and C's exact integration 260e1d14f8b6b67264db3a8f0f889237ef34a3b4; the latter preserved parent module/profile bytes and the exact package allowlist union. [Hosted run 39364861264](https://github.com/spei04/agent-rewind/actions/runs/39364861264) passed 1324 tests per Python version, actual PostgreSQL constraints/concurrency/restore, three gVisor cases, isolated package smoke, security and CI gate. Issue #53 is closed. ar_0004_artifacts remains migration-only; publication coordination, full route isolation, customer admission, cloud storage and real power-loss evidence remain outside this acceptance. Eleven approved research implementation issues #57–67 remain blocked by their unchanged runtime prerequisites. No new provider calls, paid resources, data access or scope approval.

## Proposed context and model work — not active assignments

The [context/selection amendment and RC-01–06 cards](research/CONTEXT_SELECTION_AMENDMENT_2026-10-19.md#proposed-engineering-work-outside-the-active-ledger) supply objectives, PR boundaries, exclusions, dependencies, interfaces, acceptance tests, security/reliability, roles, effort and definition of done. They supplement C20/C21 and preserve the nine approved scopes. These six proposed PRs are excluded from active DAG totals and scheduling. Their dependency review and four exit gates are in the amendment; runtime starts require explicit scope/contract review and existing data/funding/statistical gates.

2026-10-20 final approval reconciliation: [PR #56](https://github.com/spei04/agent-rewind/pull/56) merged at d408e5d1b10191dacbfe43a78f43df6de08b5950 after independent source/composition review and [run39365454903](https://github.com/spei04/agent-rewind/actions/runs/39365454903), with1350 passing tests per Python version, actual PostgreSQL, installed distributions, three gVisor tests and all required gates. Issue #51 is closed; its eleven mapped runtime issues remain blocked on their prerequisites. The separate [context planning amendment](research/CONTEXT_SELECTION_AMENDMENT_2026-10-19.md) is internally reviewed; RC-01–06 remain proposed and excluded from active totals. No new paid evaluation, held-out access or production scope.

2026-10-20 next replay-path assignment: AR-009-B is In progress in [issue #69](https://github.com/spei04/agent-rewind/issues/69), after accepted AR-009-A/007-B on main 4e509a2. C owns complete graph verification and atomic scoped publication; A reviews failure/security behavior and B reviews contracts/transactions. The observable gate is all verified run/checkpoint children and the root becoming visible together, or no completed root on upload, corruption, scope, fence or SQL failure. The generation-aware live adapter and run projection remain later integration work, with no owner-only fallback. Existing C checkout is reused; primary retains the reviewed architecture explanation. No new paid calls, infrastructure or partner data; reconcile historical reservations against actual spend before paid validation.

2026-10-20 publication acceptance: AR-009-B preparatory publication is Verified in [PR #70](https://github.com/spei04/agent-rewind/pull/70): reviewed integration 5923bbe passed hosted run [39461271604](https://github.com/spei04/agent-rewind/actions/runs/39461271604) with 1431 tests on each supported Python version, all eleven actual PostgreSQL publication cases, three gVisor cases, security, isolated package smoke and the required CI gate. A accepted graph/fidelity and diagnostic behavior; B accepted transaction/ownership and full source-writer contracts. Live worker publication stays unavailable until AR-006-A and AR-010-A/B are integrated and AR-012-B verifies the complete path. Customer admission, historical adoption and production gates remain open. No prerequisite, estimate, customer or paid-study gate changed.

2026-10-20 projection assignment and retained repair ownership: from accepted main 7c0571ba1cbff1dfe9902bd92f63cea574d8f1fa, AR-006-A starts only after Verified AR-005-C/007-A/009-B and development G0. Issue #71 records C capture/backfill/publication and B schema/revision/compatibility after this planning checkpoint; A/lead and reciprocal scoped reviews remain required. B exclusively reconciles primary planning files on work/run-projection-integration, while C uses work/run-projection in its existing checkout. No branch switch or new checkout/environment is needed. AR-006-C makes the existing C04 repair/audit requirement assignable: BE 2 base days, range 2–3.5, medium confidence; depends on AR-006-A/010-B and is required before AR-012-B. AR-006-B owns conservative read suppression only. Live worker publication, customer admission and external gates stay closed. The split reflects implementation boundaries, not a dependency cycle. No paid call, data access or cap change.

Recomputed live planning totals: 151 tasks, 52 parents, 27 gates, 20 contracts and 542 acyclic edges; 442 base / 748.1 upper / 552.5 alternate 25% allowance days, with a 154.5-day effort-only path. M1 is 43.5 days and BE 79.5; other role/milestone totals are unchanged. Historical C21/owner issuance records and prior schedules remain unchanged; these estimates do not establish a calendar or new staffing.

2026-10-20 projection acceptance: AR-006-A preparatory run projection is Verified in PR #72 at reviewed source 46639c49502995870eb19faaea218b84a02a95ec. Hosted run 39497717028 passed 1596 tests on Python 3.11 and 1600 on Python 3.12, including all 21 new actual PostgreSQL backfill/publication cases. Three core Docker skips are covered by three passing gVisor cases; four sqlite3 transaction-mode cases are Python-3.12-only. Lint, formatting, strict types, contract/planning validation, dependency security audit, isolated package smoke and CI gate passed. A/B accepted the scoped runtime, transaction, catalog, test and diagnostic corrections. Frozen history, interrupted process recovery, backup/restore/resume, project serialization and publication rollback/retry have synthetic execution evidence. Live generation-aware publication, API listing, mutable repair/audit, customer admission and production acceptance remain gated. No model calls, new paid resources or partner data were used. Parent AR-006 stays In progress. Dependencies, estimates and gates are unchanged.

2026-10-20 existing-route planning reconciliation: [AR-007-C plan](delivery/EXISTING_ROUTE_AUTHORITY_PLAN.md) retains original C04/C05 obligations in one preparatory PR with four reviewable commits. Estimate replaces 2 [2–3] with 6 [6–10] BE days, medium-low; direct verified AR-009-B is added as a consumed graph-reader producer. B owns planning, C design/implementation after acceptance, A security/auth/read and B transaction review; runtime remains Not started. Current totals: 151 tasks, 543 acyclic edges, 446 base / 755.1 upper / 557.5 alternate allowance and 160.5 effort-path days; M1 47.5 and BE 83.5. Historical owner/C21 records and daily schedules remain unchanged; no full future-route, customer, paid or production gate is promoted.

2026-10-20 smaller-PR correction supersedes the preceding one-PR/four-commit proposal: the user requested separately reviewable deliveries. AR-007-C/P1 is the 2 [2–3] day foundation with unwired strict v2 helpers, fresh authority, shared journal-free verified reader and preserved RunPublisher.read delegation; AR-007-C/P2 is the 4 [4–7] day complete integration after accepted merged P1. Both retain migration-only limits; aggregate AR-007-C stays Not started until implementation begins and cannot be Verified before accepted P2/full route matrix. Issue #75 is the aggregate tracker. Refusal by the unavailable admission adapter precedes readiness probes, storage and enqueue. A/C/lead accepted the split in principle; exact delta review remains required.

The aggregate graph and effort stay 151 tasks, 543 edges, 446 base / 755.1 upper / 557.5 alternate allowance and 160.5 effort-path days. Delivery accounting is now explicitly 152 planned PRs; parent AR-007 has four PRs across three aggregate tasks. Nested package checks require inherited prerequisites/contracts, sum base/ranges without double counting, accepted merged P1 before P2, and complete package evidence before aggregate verification. Historical decisions and prior daily schedules remain unchanged.

2026-10-20 foundation assignment: A/lead accepted exact planning correction 839f3a7. P1 is In progress with C; A and B independently review its runtime handoffs. P2 remains Not started pending accepted merged P1, aggregate #75 remains In progress, and the current ready/unassigned queue contains only AR-011-C. Historical conditional daily allocations are preserved.

2026-10-20 P1 hosted correction: final run [39526088575](https://github.com/spei04/agent-rewind/actions/runs/39526088575) at e7442b5 failed one PostgreSQL fixture before the maximum-reference reader query: repeated project parameters inferred conflicting text/varchar types. Python 3.11 passed 1778 with seven skips; Python 3.12 passed 1782 with three skips; each had one failure and one existing warning. The other 45 new PostgreSQL cases, package/security and three gVisor tests passed. B delivered fixture-only dbfbae0, preserving all 16,000 rows and assertions; A accepted the exact fixture correction and the lead owns matching hosted verification. P1 remains Implemented; verification pending, P2 Not started and aggregate #75 In progress. B/C completed read-only P2 interface and test preparation; the accepted 4 [4–7] engineering-day estimate and prerequisite gate remain. No new checkout, model call, paid resource or partner data was used.

2026-10-20 P1 query correction: C delivered 8222644, integrated as 8be6316, after a bounded SQLite probe found repeated JSON rowset scans. A/B accepted materialized, exact-object-ID matching with the original single-statement snapshot, complete descriptor/ownership checks and input/result bounds retained. A independently verified 16,000 matching refs within about 4.21 million VM instructions under a 20-million ceiling, plus foreign/substituted/missing refusals; 61 reader/publication tests passed. Unsupported SQLite versions refuse before storage. Lead integration passed 314 focused tests with 53 explicit local PostgreSQL skips, lint/format/security rules, strict types and all planning/contract validators. PostgreSQL fixture correction dbfbae0 remains included. These results do not establish PostgreSQL performance: final matching hosted execution, package checks and accepted merge remain required. P1 is Implemented; verification pending; P2 remains Not started and aggregate #75 In progress. No new checkout, dependency installation, paid call or partner data was used.

2026-10-20 P1 accepted delivery: PR #78 source 923647d85ac8acc68f5334c2edcad40c6638d59a accepted by A for identity/read security and B for authority/SQL semantics; merge 51a2b1fefc40fc871426a47e3f3865fcbeef5bec has the identical reviewed tree. PR run 39528447469 and protected-main run 39529350057 passed 1789 tests on Python 3.11 and 1793 on Python 3.12, including all 46 new PostgreSQL cases; package/security and three gVisor tests passed. Candidate 12314568373 archive, exact four-file set, source/pinned manifests and package/SHA256SUMS hashes independently verified. Private release record is indexed outside disposable checkouts. P1 is Verified; P2 #77 is In progress after this prerequisite, with the full current-route/transaction matrix still required before aggregate #75 can close. Customer, production, research-execution and spending gates are unchanged.

2026-10-21 P2 implementation complete: A independently accepted final UI source 6565555 with 38 shipped-JS passes, including credential-switch and same-credential access-loss races, own CSRF/logout and later recovery. B accepted route transaction consumption; C independently accepted boundary-test correction 3420314 and distinct GET/HEAD OpenAPI IDs 291efaf. Lead integrated UI as e2621c7/26f55b5; 159 combined route/UI/guard tests passed, one opt-in PostgreSQL case skipped, one existing TestClient warning (29.68 seconds). Earlier full local ee528e1 passed 1,770 with 219 opt-in skips and four warnings. Initial hosted run 39533947726 at 72c0606 failed both core jobs on the obsolete artifact-test hook; 1,975/1,981 passed, one failed each, nine/three skipped, while package/security and three actual gVisor tests passed. That failure is retained as historical evidence. P2 is Implemented; verification pending in PR #79. Final matching hosted checks, accepted merge, protected-main checks and candidate verification remain required; aggregate #75 remains In progress. No new checkout, dependency installation, paid call, partner data or production activation.

2026-10-21 observability producer reconciliation: [AR-011-C plan](delivery/OBSERVABILITY_EXECUTION_PLAN.md) retains the approved correlation/five-metric scope as two sequential PRs, 4 [4–6] PL days. Both packages inherit AR-010-B alongside AR-011-B/AR-005-C; P2 also waits for accepted merged P1. No early foundation assignment or reverse AR-012-B edge is allowed. A/C independently accepted the preceding admission plan at 1d284ba; the separate observability source awaits their review. Current computed totals: 151 tasks, 155 delivery PRs, 544 acyclic edges, 454 base / 768.1 upper / 567.5 alternate allowance and 168.5 effort-path days; M1 55.5, PL 90. Historical schedules/decisions/contracts remain unchanged. P2/AR-007-C stays verification pending; this is planning only, with no runtime, funding or activation claim.

2026-10-21 acceptance/status reconciliation: [accepted P2 evidence](delivery/EXISTING_ROUTE_AUTHORITY_PLAN.md#accepted-p2-delivery--2026-10-21) closes #7/#75/#77 for preparatory existing-route scope. C starts admission P1 #81 under aggregate #80, after Verified AR-007-C/009-B; #82/#83 remain Not started and merge-gated. A completed read-only AR-006-B planning; a separate amendment follows independent review of this checkpoint, with no runtime assignment or estimate change here. B reconciles current status then reviews contracts/security; lead owns integration. Planning 1d284ba/9a70fdc was accepted by A/C and f08b1ca by A, with 54 independent backlog passes and three validators. Task IDs, estimates, dependencies, frozen contracts/gates and historical schedules remain unchanged.

2026-10-21 listing-plan amendment: [AR-006-B execution plan](delivery/RUN_LISTING_EXECUTION_PLAN.md) separates cursor/bounded SQL foundation from the frozen two-route integration, each 2 [2–3] TL days. Both packages remain Not started; P2 needs accepted merged P1. Existing aggregate dependencies/C04 and all outer edges/statuses are unchanged. Recomputed totals: 151 tasks, 156 delivery PRs, 544 edges, 456 base / 771.1 upper / 570 alternative allowance, M1 57.5, TL 75 and 168.5 effort-path days. A authors planning only; B/lead review is pending. Historical records and frozen contracts remain unchanged.

2026-10-21 admission foundation handoff: AR-008-A/P1 is Implemented; verification pending. C authored parser 4c6a558, configuration 0e6cb05, envelope 1dde230 and packaging/guide e699394; lead integrated unchanged file contents as 7ea387f/3f74d69/d0448d4/02424e0 onto reviewed c390726. B independently accepted each runtime component for source and test design. Author validation passed 230 focused admission/package-helper/workflow/contract/model/legacy/artifact-metadata tests in 10.37 seconds, strict types, lint/security lint, formatting and whitespace. Final independent composed execution, actual installed wheel/sdist smoke, hosted checks, accepted merge and protected-main candidate remain required. No SQL/HTTP/storage/worker activation or provider call occurred; P2/P3 remain Not started. [Implementation boundary](delivery/ADMISSION_FOUNDATION.md).

2026-10-21 admission foundation acceptance and storage assignment: AR-008-A/P1 is Verified after accepted PR #85 merge 81905a5 and matching PR/main checks plus candidate verification. C owns AR-008-A/P2 (#82) additive schema and bounded repositories in the retained checkout; P3 (#83) remains Not started until accepted merged P2. Aggregate #80 and parent #8 remain open. A authored AR-006-B/P1 in draft PR #89 under accepted plan 9b97a09; its plan and accepted admission progress are composed here, with independent review and hosted proof pending. B reviews admission contracts/security; A reviews preservation/boundary evidence as available; lead owns integration and delivery. Accepted source bc2a784, merge 81905a5, PR/main runs 39539994853/39541051449 and candidate 12320076132 are recorded in [accepted P1 delivery](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p1-delivery--2026-10-21). C's short listing PostgreSQL test handoff d9fa9a8 received A source/test-design acceptance with explicit local skips; no actual local PostgreSQL proof or listing completion is claimed. Historical evidence, schedules, profiles, contracts and all unrelated task statuses remain unchanged. No coordinator, HTTP/worker wiring, ledger/generation schema, provider call or customer-ready activation follows. CT-M1-008/010/011/012 service acceptance remains with P3 and later integration.

2026-10-21 progress reconciliation: C records admission P2 #82 as Implemented; verification pending after A/B source/catalog/crash-test acceptance and A's independent 461 passes/78 explicit PostgreSQL skips/one warning at composed 01b3b65. Lead static/lock/three-validator checks passed; matching hosted P2 checks, accepted merge and main candidate remain required. Listing P1 #87 is Verified at merge ed0d6c4 after successful PR/main runs 39547572853/39548734170 (2419/2427 core plus three gVisor tests) and verified candidate 12323231309; #87 is closed and A starts P2 #88 in reused primary work/scoped-run-routes. Lead owns admission P2 delivery, A owns listing P2 in primary, B reviews independently and C releases its checkout after this progress-only validation. Aggregate #80/#86 remain In progress, admission P3 Not started. Metrics remain 151 tasks/156 PRs/544 edges/456 base/771.1 upper/570 alternative/168.5 effort path; no runtime, historical evidence/contracts/profiles, estimates or gates changed.

2026-10-21 delivery progress reconciliation: Admission P2 #82 remains Implemented; verification pending after PR #90 merged reviewed 4135c6f as 41759bb and PR run 39550589433 passed 2571/2579 core tests (11/3 expected skips), actual PostgreSQL, three gVisor cases and package/security/gate checks. Protected-main run 39552010828 and candidate acceptance remain pending; accepted-merge/review-evidence fields stay null and P3 #83 Not started. Listing P2 #88 is Implemented; verification pending in draft PR #91: B accepted 1954f3e, C independently passed 181 tests/no skips/one warning (70.92 seconds). At composed 47abde4, B accepted the source union and A passed 217 tests/no skips/one warning (71.51 seconds) plus the combined source smoke sequence; this is no installed-wheel or PostgreSQL claim. Lead owns both delivery gates; A/B reviewers are available and C releases primary after this progress-only validation. Aggregates #80/#86 and parents remain open. Metrics remain 151 tasks/156 PRs/544 edges/456 base/771.1 upper/570 alternative/168.5 effort-path days. Dated history, runtime/tests/lock, frozen contracts/profiles, scope/effort and gates are unchanged.

2026-10-21 admission P2 acceptance and P3 assignment: AR-008-A/P2 #82 is Verified and closed after reviewed 4135c6f merged as 41759bb, successful PR/main runs 39550589433/39552010828 (2571/2579 core passes, 11/3 expected skips, actual PostgreSQL, three gVisor cases and installed-package/security/gate checks), and lead-verified candidate 12324805344 (544761 bytes, exact four files and source/manifests/package/archive hashes). See [accepted P2 evidence](delivery/ADMISSION_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21). C starts P3 #83 in the retained checkout from accepted 41759bb; B reviews security/source, A independently owns PostgreSQL tests after the stable interface handoff, and lead integrates. The first checkpoint is frozen-envelope restoration plus SQL-only creator recovery/alias and fresh disclosure; new-work adapters remain unavailable and the full P3 matrix is still required. Aggregate #80/parent #8 stay open. Listing P2 #88 remains Implemented; verification pending in PR #91, with no accepted merge or candidate claim; its delivery is separate from admission acceptance. All historical evidence, scope, estimates, dependencies, gates, contracts/profiles and runtime/lock bytes remain unchanged.

2026-10-21 admission P3 implementation handoff: P3 #83 is Implemented; verification pending in draft PR #92, with accepted-merge/review-evidence fields null and aggregate #80/parent #8 In progress/open. B accepted runtime 302571f/4440ee3, e5a75ec's ten residual cases and A's corrected 32-case PostgreSQL suite 458c1114. A independently passed 157 original runtime cases without skips (52.93 seconds); lead's composed edf85ae selection passed 530 with 94 explicit PostgreSQL skips, no warnings (117.85 seconds), plus full static/lock/three-validator checks. Early published 1878cfb run 39558425762 passed 2748/2758 core, 13/3 expected skips, 26 actual PostgreSQL recovery cases and package/security/three gVisor/gate checks; it does not prove the later publication path. All 32 new publication/crash cases require hosted execution, followed by final-source package/CI, accepted merge and protected-main/candidate proof. Lead owns delivery, A/B reviewers are available and C releases its reused checkout after this progress-only validation. AR-008-B remains Not started; accepted listing records, dated history, 151 tasks/156 PRs/544 edges/456 base/771.1 upper/570 alternative/168.5 effort-path metrics, scope, gates, runtime/tests/lock and frozen contracts/profiles are unchanged.

2026-10-21 ownership entry accepted and helper assigned: B/lead accepted exact 5bedede after 54 independent backlog passes and three validators; C independently confirmed 33 acquisition sites across 14 modules. P1 remains 4 [4–7] BE days and aggregate B 6 [6–10], medium-low; current totals remain 461 base / 779.1 upper / 576.25 alternative / 173.5 effort-path days. A is assigned only the dormant helper and focused tests, with no Database activation or consumer edits. C retains P1 ownership; caller integration and activation receive separate reviews. The e490a27 component suite passed 40 actual PostgreSQL cases with restored baseline and stopped instance. Separate correction 97ef62c passed B source review and 18 lead regression cases in 0.88 seconds after six pre-fix failures; full author suite passed 250 cases. These component results do not verify P1 or enable HTTP, workers, customer data or spending. Dated pending checkpoints remain historical.

2026-10-21 encryption contract acceptance: AR-016-A offline C07 is Verified after reviewed source db9a1855620674a2ad615dba340f471384fad8f3 merged in PR #102 as 2bb75695b69ae62f4f69acd4c3df5876652b3095 with an identical tree. PR run 39584005704 and protected-main run 39586072558 passed 2970/2980 tests on Python 3.11/3.12 with 13/3 expected skips and one existing warning each; all 33 publication and 26 recovery PostgreSQL cases ran on both versions. Package/security/CI gate, three gVisor cases and main delivery passed. A authored the contract, C independently accepted the corrected schema and B accepted composition and both CI runs. Lead verified candidate 12341062437 (585234 bytes), exact four files, source/parent/tree, pinned manifests and package/archive hashes; indexed private release record reviewed-delivery-20261021-pr102-2bb7569.json is retained outside checkouts. C07 is available for development contract consumption; format-2 runtime, live KMS/IAM, migration/rotation/deployment and external gates remain open.

2026-10-21 dormant ownership helper accepted and caller integration assigned: A authored d1b7ce20; B accepted API/provenance and C accepted lifecycle/test design. Lead independently passed all 67 helper cases in 0.50 seconds and reproduced the original237114 pool-substitution flaw in memory: old code entered the caller and created a foreign connection before exit refusal; corrected code refused with zero caller/body/connection creation and no pool-slot leak. Six author negative cases failed against the original while two normal-dispose controls passed; final author combined suite passed 169 cases with no skips and one existing warning. Public QueuePool.recreate registers only successors of owned predecessors; full checkout attestation precedes yield and observed same-generation disposal does not clear failure. This is component source acceptance, not full P1, hosted delivery, installed-package or activation proof. C is assigned complete caller integration against the accepted 33-site/14-module map with Database factory activation disabled. A/B review; lead owns integration/delivery. C15 PR #103 merged reviewed881096a as9ee75e7 after 3040/3050 PR passes; protected-main39589239743 and candidate acceptance remain pending.

2026-10-21 accepted C15 delivery: AR-034-A offline C15 is Verified after reviewed source 881096a73224f2ca307d31ebfe26d66c86f8229a merged in PR #103 as 9ee75e785224fc2856e4666e32ef62631ef93454 with an identical tree. PR run 39586855528 and protected-main run 39589239743 passed 3040/3050 tests on Python 3.11/3.12 with 13/3 expected skips and one existing warning each; all 33 publication and 26 recovery PostgreSQL cases ran on both versions. Package/security/CI gate, three gVisor cases and main delivery passed. C authored the contract, A independently accepted the corrected contract and schema, and B accepted composition and both CI runs. Lead verified candidate 12342151758 (585143 bytes), exact four files, source/parent/tree, pinned manifests and package/archive hashes; indexed private release record reviewed-delivery-20261021-pr103-9ee75e7.json is retained outside checkouts. C15 is available for development contract consumption. Administrative services/UI, durable mapping/recovery storage, real IdP and production acceptance remain gated; AR-034-B still waits for AR-033-C and its concrete storage/effort entry decision.

2026-10-21 owned caller progress: The corrected dormant caller 55b3950 is independently accepted as a component after A/B review, 124 lead regression passes and exact-source isolated package proof. C owns factory activation and dedicated smoke tests; A owns existing Database-backed fixture adaptation in the reused primary. Activation and dependent services require separate review; P1 remains In progress and P2 Not started. The accepted component is not merged P1 delivery; hosted activation/service evidence remains required. Assignment and source-bound evidence are recorded in ASSIGNMENTS.md.

2026-10-21 factory component accepted: The composed owned-factory and fixture checkpoint 97d39edf is accepted as a component after independent source/package review and 1,273 local passes with 250 explicit PostgreSQL skips. C now implements bounded cohort/final-receipt/association primitives; A reviews their test design and B reviews source/hosted evidence. Full service and P1 delivery acceptance remain pending; P1 remains In progress and P2 Not started. Draft PR #105 is the existing planned P1 and adds no package or effort. The accepted primitive entry is in OPERATION_ADAPTER_ENTRY.md; assignments and source-bound evidence are in ASSIGNMENTS.md.

2026-10-21 foundation CI and fixture correction: Draft PR #105 run 39596377455 at 97d39edf failed the same four optimized doctor-command fixture cases on both Python versions. Python 3.11 passed 3,326 with 14 skips in 978.18 seconds; Python 3.12 passed 3,337 with three skips in 1,050.02 seconds; each had one existing warning. All 40 operation-component, 33 publication and 26 recovery PostgreSQL cases executed on both versions. Package/security and three gVisor cases passed, but the CI gate failed and the main-only candidate delivery job correctly skipped. B's exact skip identities are source-derived (11 Python-3.12-only SQLite cases plus three Docker cases), consistent with the logged aggregate counts.

A corrected only test_cli_doctor.py at a92db83 after reproducing all four failures. Engine/Connection doubles now follow direct connect and close semantics while the real owned_connect remains exercised; all original artifact, runner and optimization assertions remain. The doctor/CLI/sentinel selection passed 37 cases with no skips, and static checks passed. B and the lead accepted the narrow source; no production guard changed. Full failed-run and correction evidence are privately indexed outside checkouts with owner-only permissions and a 2026-11-20 review date. C continues the separate primitive implementation and actual PostgreSQL proof; A next reviews that frozen checkpoint. Corrected matching hosted checks, complete service composition and accepted P1 delivery remain pending. P1 stays In progress, P2 Not started; estimates, dependencies and activation gates are unchanged.

2026-10-21 bounded primitive component accepted: C froze 691ad661 with bounded complete-cohort discovery, a single typed final receipt query, the pure full-job decoder and immutable cancellation association. B independently accepted its SQL/security/native-type and cardinality boundaries. A verified the exact 366-path composition at 1985202 and passed 174 SQLite/component cases in 45.41 seconds, then all 15 original actual PostgreSQL cases in 41.63 seconds. A's test-only cbed928 adds three PostgreSQL controls that passed in 9.80 seconds: same-project reassignment invalidates the snapshot, foreign-project reassignment stays excluded, and actual write denial is followed by clean reads. The original tests and production source remain unchanged. The initial new-test NullPool cleanup-oracle diagnostic is preserved; it was not a production defect. PostgreSQL baseline was restored and the existing instance stopped.

Measured examples reached 255 roots/259 identities and 4,000 scoped/foreign distractors within unchanged limits (101,000/177,000 SQLite VM instructions; 22 final-query binds and 26 PostgreSQL attempts observed before cleanup, including setup/probe; the normal post-cleanup total of 28 is derived from source). These examples do not establish throughput for arbitrary unindexed tables. C built exact-source wheel/sdist; the lead independently matched all 111 runtime members in each archive, hashes, pinned manifests and actual isolated smoke/CLI evidence. Disposable build runtime cleanup recovered 126,238,720 filesystem bytes; both active cloud checkouts remain. Private source-bound evidence is indexed with owner-only permissions and a 2026-11-20 review date.

This accepts the strict GET receipt and association primitives, not OperationService or multi-phase cancellation. The next cancellation entry must share cumulative request work while releasing phase-local mutable evidence; worker progress between phases must not be compared with an earlier GET snapshot. A reviews that entry, B prepares the concrete phase API, C prepares GET composition, and the lead owns integrated CI/delivery. The first failed hosted run remains historical; the doctor correction is included in the composed source. P1 stays In progress and P2 Not started, with unchanged scope, effort, dependencies and external gates.

2026-10-21 GET source and package evidence accepted: B and the lead reviewed 28d47cc9. C passed 312 combined cases with 19 explicit PostgreSQL skips, then all 19 actual GET PostgreSQL cases with zero skips in 58.36 seconds. Completed OIDC/API-key requests measured 40/48 SQLite and 50/62 PostgreSQL attempts; these are bounded synthetic examples, not arbitrary-scale throughput. The lead verified the source-bound logs and restored/stopped database baseline. Exact wheel, sdist and installed-tree proof matched all 112 runtime members; isolated installed GET/result/refusal scenarios and a separate real migration-only guard passed. The disposable runtime was removed, recovering 126,410,752 filesystem bytes.

The earlier primitive source 5e1766d passed draft PR #105 CI 39601721324: 3,406/3,417 tests, expected 14/3 skips, all 117 targeted PostgreSQL cases on both Python versions, package/security, three gVisor cases and the CI gate. This is component CI; no protected-main or complete service acceptance follows.

Cancellation helper d8975224 remains blocked on one independently reproduced failure-latch defect. Its original 43 SQLite cases passed in the lead's run, but an additional schema-legal oversized-job-metadata test caught a read failure, repaired the metadata and successfully retried the same phase. A owns the narrow correction and its SQLite/PostgreSQL regressions; B reviews it and C checks unchanged GET behavior. The lead owns composition and the written cancellation-service handoff. P1 remains In progress, P2 Not started; task counts, estimates, dependencies, funding and activation gates are unchanged.


### 2026-10-21 — corrected phase ownership and service assignment

The caught-active-read blocker is closed at 9f73448d. B accepted exact source and indexed evidence, C accepted unchanged ordinary GET behavior, and the lead independently passed 55 SQLite cases in 36.06s including the unchanged original failing probe. The author’s final 134 SQLite and 40 actual PostgreSQL coverage is assembled from full runs plus 9/4 affected test-only reruns; the original 11/4 regressions and intermediate diagnostic failures remain preserved.

The lead composed exact GET 28d47cc9, corrected helper 9f73448d and accepted cancellation entry b65d38f7 at 950a4160. B verified 372 unchanged union paths, the exact guide append union and 113-member distribution allowlist. Independent lead GET execution passed 85 SQLite cases in 57.59s; C passed 19 actual PostgreSQL cases without skips in 61.07s. Completed GET traces remain 40/48 SQLite and 50/62 PostgreSQL attempts for OIDC/API-key callers. The exact synthetic database baseline was restored with zero other clients and the server stopped. Installed proof at 28d47cc9 remains distinct from this composition; a final 113-member service package and hosted delivery are still required.

A is assigned cancellation runtime/effect extraction and SQLite tests in the reused primary checkout. C is assigned independent actual PostgreSQL service tests in the reused secondary checkout and coordinates the sole existing database lifecycle. B independently reviews both deliveries; the lead owns composition, evidence and delivery. The [cancellation service entry](delivery/OPERATION_CANCEL_ENTRY.md) freezes three phases, original associations, the stable 85-root pre-effect refusal, malformed-ID authority ordering and phase-specific uncertainty mapping. No helper or GET support-table expansion is authorized. P1 remains In progress; P2 Not started. No task status, dependency, estimate, spending or production/data gate changes.

## Service composition and final delivery checkpoint — 2026-10-21

The same-Connection cancellation implementation at 1ce9469f has independent source review and 68 independently executed SQLite passes at 0f031962 (43.63 seconds). Its author selection passed 274 new/existing cases; six strengthened test observations were rerun separately. Completed cancellation traces are 88/106 SQLite and 119/146 PostgreSQL attempts for OIDC/API-key callers, within the unchanged 512-attempt/10-second SQL-active limits.

C's PostgreSQL evidence covers 65 distinct cases across runs: 62 initial passes, one corrected organization contention case and two physical QueuePool recovery cases. The first run's nonexistent-column fixture and a later tuple-initialization typo are preserved as test failures; neither required a runtime change. The two pool cases prove closed old physical connections, zero occupied slots, an idle replacement and a successful subsequent cancellation after confirmed rollback or acknowledged commit. The exact original database/role inventory was restored, with zero other clients and the socket-only server stopped.

Composition f9172462 preserves the exact 377-file union of reviewed runtime, independent PostgreSQL tests and installed smoke. The 71d33737 package proof passes isolated service GET/cancellation, a separate untouched real migration-only guard, CLI and all 113 Git/wheel/sdist/installed runtime member comparisons. The service marker follows the service scenarios and real-guard checks; separate package and CLI evidence records the remaining checks. Final source binding and matching hosted checks remain required; older component CI does not cover this composition.

The core CI job receives a bounded 30-minute scheduling window because the preceding Python 3.12 suite already took 1,106.67 seconds and this composition adds execution coverage. Product, native SQL, test wait and other job deadlines remain unchanged. A owns final installed proof, B reviews final source/CI inventory, C reviews integration evidence, and the lead owns delivery. P1 remains In progress; P2 Not started. No task status, dependency, estimate, spending or production/data gate changes.

2026-10-21 approved ledger planning reconciliation: The owner approved the finite nonrenewable execution window and two-package plan at proposal 882fa139. AR-010-A now has P1 schema/provisioning/opening backfill 3 [3–5] and P2 reservation/minimum-generation/rollover 3 [3–5], total 6 [6–10] BE days, medium-low. Both remain Not started/null acceptance; accepted HTTP delivery and exact entry review precede code, accepted P1 precedes P2, and AR-010-B waits for the whole aggregate. AR-023-A/C explicitly retain historical-opening/actual-transfer evidence ownership without a new table, fabricated call or reverse dependency. Current metrics are 151 tasks/159 PRs/544 edges/464 base/784.6 upper/580 alternate/176.5 effort path; no old schedule, runtime, frozen contract, other estimate/status or external gate changes.

## Accepted HTTP P2 checkpoint — 2026-10-21

AR-008-B/P2 #95 and aggregate #93 are Verified after reviewed source 065df8c89da384d6e502cf0c15bf174e380c53c7, protected merge cefd222230c800eb2e90c49a3b3c411b394d0393, matching PR/main runs 39683408934/39686498691 (attempt 1) and verified candidate 12387716715. P1 #94 retains accepted merge 03a8e074b51dca7c03d69295e0c18ca0f22dc1da and candidate 12355648523. Parent #8 is Verified/closed. [Exact evidence](delivery/OPERATION_HTTP_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21) confirms the scoped delivery; counts are 30 Verified / 0 In progress / 121 Not started tasks and 9 Verified / 0 In progress / 6 Not started delivery packages. Ledger implementation is not assigned in this first ordered checkpoint. Approved metrics, history and all later gates are unchanged.

## Ledger P1 assignment checkpoint — 2026-10-21

AR-010-A/P1 #108, aggregate #107 and parent #10 are In progress after the explicit lead handoff to platform/security in the existing secondary checkout, work/ledger-schema, from 9f6ea6e. P1 entry policy 51af77dc and the HTTP prerequisite are accepted. P1 product proof and acceptance remain pending; P2 #109 is Not started/null acceptance behind accepted P1 and its own exact reservation/fence entry review. Planning/verification authors independent owned tests only after the progress patch is accepted and runtime interfaces are stable; the lead integrates and the delivery reviewer independently reviews. The lead updated/read back #107/#108/#10 In progress and #109 Not started. Only P1 is assigned; worker and P2 reservation work remain gated. Counts are 30 Verified / 1 In progress / 120 Not started tasks and 9 Verified / 1 In progress / 5 Not started delivery packages; 544 edges, 159 PRs and all approved estimates remain unchanged.


## Ledger first schema checkpoint — 2026-10-21

The first schema checkpoint is independently accepted at b2e19be after 65
native PostgreSQL passes (107 combined schema passes and 18 deliberate dialect
skips). Four scope-reversal defects found during review are repaired; the
original failed evidence is retained. The 209 previous migration regressions
pass. [Checkpoint evidence and remaining work](delivery/LEDGER_EXECUTION_PLAN.md#first-schema-checkpoint--2026-10-21)
separate this result from the unfinished operator, recovery and full P1 delivery.

Platform/security revises startup and cleanup accounting before operator
implementation; planning prepares independent fault controls and delivery
reviews the design and hosted planning evidence. P1 remains In progress and P2
Not started. Task/package totals, acceptance fields, 544 dependency edges,
159 planned delivery PRs, estimates and external gates are unchanged.

## Ledger operator verification checkpoint — 2026-10-22

Corrected source at 3716811 passes all 79 independent SQLite and nonconnecting
factory checks: 14 transaction, 37 work-boundary and 28 factory cases in 2.47
seconds. Four initial transaction failures, three native setter-expiry failures
and reservation-delay failures were retained before the respective fixes.
Separate authored checks pass 41 cases; these are not one combined full-suite run.
[Exact scope and remaining gates](delivery/LEDGER_EXECUTION_PLAN.md#operator-sqlite-verification-checkpoint--2026-10-22)
distinguish this checkpoint from accepted operator or P1 delivery.

Platform/security owns native PostgreSQL and both-interpreter validation in the
existing secondary checkout. Independent QE prepares further PostgreSQL coverage
and waits for the verified database handoff; delivery reviews source and evidence.
The lead maintains the public checkpoint and assignment log. P1 stays In progress
with null delivery acceptance; P2 stays Not started. Task/package counts, 544
dependency edges, 159 planned PRs, estimates and external gates are unchanged.


## Ledger operator native and lifecycle checkpoint — 2026-10-22

The bounded operator at 80023cbc is independently accepted for its factory,
work accounting, transaction outcomes and cleanup. All 100 independent
SQLite/factory/lifecycle cases pass on both supported interpreters. Separate
PostgreSQL evidence passes 131 cases together on Python 3.11; Python 3.12 has
47 earlier cases followed by 18 expanded cases. These overlapping selections
are not summed into a full-suite result.

[Exact scope and remaining work](delivery/LEDGER_EXECUTION_PLAN.md#operator-native-and-lifecycle-checkpoint--2026-10-22)
include inspection/provenance, the actual 245000 opening, replay, concurrency,
capacity, recovery and hosted delivery. P1 stays In progress/null acceptance;
P2 stays Not started. The next bounded reader receives source review before
implementation. Estimates, dependencies, funding and external gates are unchanged.


## P1 implementation PR refinement — 2026-10-22

The lead approved three internal implementation PRs within unchanged P1:
F1 dormant foundation (#111), F2 complete bounded reader, F3 trusted
provisioning/opening/replay/recovery. Each successor waits for accepted
predecessor source/delivery evidence. Full P1 acceptance remains null until
all components and the complete final PR/main/candidate gate pass; P2 and
AR-010-B retain their existing prerequisites. Issue #108 stays open through
F1/F2. The current forecast is 161 delivery PRs, AR-010-A four and parent
AR-010 six. Task/package identities, 544 outer edges and approved effort
remain unchanged; prior dated forecasts remain history.

Original run39724247038/1 retained successful database cores, package/container
and isolation evidence but failed static security and the CI gate. Correction
and private guard ff65892 have internal acceptance; 281 selected checks passed
on each Python version. Fresh foundation delivery remains required. The
[delivery plan](delivery/LEDGER_EXECUTION_PLAN.md#current-p1-implementation-sequence--2026-10-22)
records exact results, remaining gates and the structural-versus-authenticated
evidence distinction.


### F3 implementation checkpoint — 2026-10-22

F2 remains accepted at e8cba52. Composition 5f575667 includes actual provisioning
and two reviewed runtime performance fixes. Eight SQLite provisioning cases
pass on each supported Python version. The new PostgreSQL slice comprises
two passes at 015ac758 and six continuation passes at 42ec316a; both failed
attempts remain separately recorded.

The runtime fixes replace repeated period scans with adjacent-period checks
and trim legal outer JSON whitespace after unchanged raw-size/BOM checks.
Their 337 focused tests pass on each interpreter under the unchanged two-second
inspection limit. Later JSON-oracle and read-query observer corrections change
tests only. Four native capacity cases collect on both interpreters, with four
affected SQLite regressions passing; their PostgreSQL execution is pending.

Next work covers native capacity, remaining writer boundaries, uncertainty,
concurrency, process death, owner/ACL restore and protected PR/main/candidate
delivery. F3/P1/AR-010-A remain In progress with null acceptance; P2 is Not
started. Counts, estimates, dependencies, funding and production gates are
unchanged. See the [current delivery record](delivery/LEDGER_EXECUTION_PLAN.md#f3-provisioning-and-capacity-checkpoint--2026-10-22).


### F3 recovery evidence before native validation — 2026-10-23

F2 remains accepted at e8cba52. This checkpoint adds actual SQLite recovery
tests and corrects native capacity observation; runtime files and the lockfile
are unchanged from 232130d. The corrected recovery selection passes **23 cases
on Python 3.12** in 70.69 seconds. Thirty-five command observations distinguish
10 service closures after cleanup failure from 25 clean idle pool returns.
All 23 fresh inspections perform zero DDL/DML.

Native capacity at ee2dc3e2 has **one control pass, one 4,096-account timeout,
and two unrun cursor cases**. The whole instrumented runtime wrapper took
1.40977 seconds for the control and returned schema_unavailable at 2.01115
seconds for the account maximum under the unchanged two-second deadline.
The earlier fetch-count observer failure remains separate. These results
do not establish complete native capacity; retained traces cannot isolate
product CPU time from observer overhead.

Next work is diagnosis of the capacity failure and native recovery validation,
then process interruption, concurrency, owner/ACL restore, remaining writer
boundaries and matching two-interpreter protected PR/main/candidate delivery.
F3/P1/AR-010-A remain **In progress** with null acceptance; P2 is **Not started**.
Counts, estimates, dependencies, funding and production gates are unchanged.
See the [delivery record](delivery/LEDGER_EXECUTION_PLAN.md#f3-recovery-and-native-capacity-checkpoint--2026-10-23).


### Current F3 native recovery and capacity evidence — 2026-10-23

F3 now has **25 actual PostgreSQL recovery passes on Python 3.12** at
7738aec6, alongside the previously accepted 23 SQLite recovery cases. Independent
review verifies physical outcomes, fresh inspection and service cleanup before
test-harness disposal. This is component evidence; final matching delivery on
both supported interpreters remains required.

The exact Unicode-character validation optimization at 54844ac passes **312
focused tests on each interpreter**. It preserves the accepted character set
and all parser/deadline rules. The subsequent native capacity run still has
**one control pass, one 4,096-account timeout and two unrun cursor cases**:
1.63709s for the control and schema_unavailable at 2.00466s for the maximum.
The optimization does not close native capacity. Earlier failures remain
separately recorded; isolated parser timings cannot establish native capacity.

Composition f09c727 combines the native recovery tests and optimization;
its runtime and lockfile match 54844ac. Native recovery evidence remains bound
to 7738aec6. Next work is process interruption and competing operators in one
checkout, with capacity diagnosis in the other. Owner/ACL restore, remaining
writer boundaries and protected PR/main/candidate delivery remain open.
F3/P1/AR-010-A stay **In progress** with null acceptance; P2 stays **Not started**.
Counts, estimates, dependencies, customer/data and spending gates are unchanged.
See the [delivery record](delivery/LEDGER_EXECUTION_PLAN.md#f3-native-recovery-and-capacity-diagnosis--2026-10-23).
