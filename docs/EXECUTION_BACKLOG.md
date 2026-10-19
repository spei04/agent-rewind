# Agent Rewind — execution backlog

**Revision:** 2026-10-19 · **Owner:** spei04 · **Status:** Proposed; awaiting execution-backlog approval.

This is the assignable execution companion to [the roadmap](PLAN.md). It covers 50 work packages as 145 independently reviewable PR-sized tasks. No application implementation, production provisioning or paid inference was started in preparing this packet. All task statuses are **Not started**. Existing product code and historical test evidence are the starting point, not completion evidence for these tasks.

The [machine-readable backlog](../contracts/proposals/execution-backlog.json) records the same task fields, contract producers, gates, first-fortnight allocations and dependency audit. Maintain the roadmap summary, this document, that ledger and affected GitHub issues together. IDs are permanent; never renumber completed evidence. The roadmap remains authoritative for product/architecture requirements; task-level edges here replace coarse package-level start assumptions. A future contract is a required producer deliverable, not an already implemented interface.

## Approval boundary and readiness

The instruction “Do not start implementation until I approve the execution backlog” is enforced by **E0**. Day 1 means the first staffed working day after that approval. E0 authorizes only its recorded scope; it does not satisfy architecture, funding, data rights, cloud access, customer, assessor or release gates. M0 and explicitly marked fixture/design preparation can proceed after E0; runtime M1 implementation also requires G0. Later tasks become assignable only when their exact prerequisites and contract-producer reviews pass. No task is scheduled on the assumption that an unavailable credential, future schema or customer approval already exists.

Recommended approval: accept this backlog as the staged delivery baseline, authorize M0 and the named preparatory tasks, and approve the M1 migration-first scope at G0. Keep later milestone implementation and external spending tied to their recorded entry gates. This avoids repeatedly revisiting accepted one-organization/gVisor architecture while preserving decisions that genuinely remain open.

## Planning review and corrections

Reviewed PLAN, README and the current-release architecture, deployment, security, research, extension and validation documents; the M1 OpenAPI/logical schema/24-case acceptance proposal; and all 12 existing planning issues. Current-release documents were treated as evidence of present behavior, not promises of future capabilities.

| ID | Finding | Correction |
| --- | --- | --- |
| REV-01 | Five/ten-day packages had generic a/b splits with no assignable PR boundary. | 145 specific tasks, 0.5–4 engineering days each, with scope, exclusions, contracts, tests, review and acceptance. Parent IDs retained for traceability. |
| REV-02 | Real storage/KMS/runtime verification depended on IaC scheduled after runtime, creating a coarse milestone loop. | AR-033-A/B are early M4 foundation tasks after G0/ENV0; AR-033-C/D integrate and independently reinstall later. Task graph, not package-level all-to-all edges, governs starts. |
| REV-03 | Reference cloud uses GCS but current artifact implementation only provides local/S3 paths. | AR-016-C explicitly implements native GCS and real-store conformance. No assumption that S3 support proves GCS compatibility. |
| REV-04 | 42–50 week GA and 28–34 week pilot forecasts were derived from unlevelled package estimates and unconfirmed staff. | Retire dated windows. 427 base engineering days; 145.5-day effort-only longest path excludes role contention and external waits. Reforecast after Day 10 and each gate using actual throughput; no committed launch date. |
| REV-05 | Uniform effort estimates concealed research, independent review and customer integration uncertainty. | Each task has confidence/range. 25% portfolio reserve is separate; audit fixes, procurement gaps, customer remediation and staffing/vendor waits remain explicitly unestimated gates. |
| REV-06 | Five M1 operations cannot support all branch, study, admin, export and SDK consumers. | Contract producer PRs AR-027-A/029-A/032-A/034-A precede their services/consumers; runtime consumers cannot start on an absent future schema. |
| REV-07 | Logical artifact and idempotency scope references lacked explicit matching composite unique/FK constraints. | Tighten m1.data-model.json artifact/project/owner and operation/principal/kind constraints; add corresponding scope-negative assertions to existing planned acceptance cases. |
| REV-08 | Pilot adoption metric requested three partners while onboarding scope funded two. | Use two partners weekly for four weeks, both adopting a resulting regression or policy fix; any third partner is an expansion. Sample shortfall requires honest gate review. |
| REV-09 | Four-week pilot and 30-day launch review were mixed with engineering days. | P28 and D30 are minimum elapsed-time gates after both onboarding measurement and accepted rollout respectively; approval/wait never auto-completes from passage of time. |
| REV-10 | The $200 historical validation cap was not a budget for a statistically powered natural-failure study or recurring production infrastructure. | PAID0 reconciles the existing authorization; STUDYFUNDS0, ENV0 and SCALEFUNDS0 require concrete funded scopes. No spending occurred in backlog preparation. |
| REV-11 | Aggregate six-engineer capacity hid heavy verification and platform ownership. | Role rollups expose QE 111.5 days and PL 86 days; two-week allocation stays <=0.5 delivery day/role/day. Independent reviewers and support coverage are external capacity dependencies. |
| REV-12 | A ten-day security package implied arbitrary unknown remediation could be scheduled and completed in advance. | AR-044 splits scope/triage/retest. SECFIX0 requires finding-specific fix PRs estimated after the assessment; prohibited blockers cannot be risk-accepted away. |
| REV-13 | Planning artifacts, existing tests and live validation risked being read as enterprise implementation evidence. | All execution tasks Not started; contracts pending; 24 M1 cases planned, not executed. Existing current-release docs and historical validation remain separate from future readiness gates. |
| REV-14 | M1 org/project/job caps do not by themselves cap a fan-out study spanning many child jobs. | AR-020-A/B explicitly introduce study-scoped ledger accounts and project/study/call closure; AR-022-A tests atomic study-wide caps under parallel child dispatch. |

## Estimates, staffing and uncertainty

Engineering effort includes implementation, task tests, ordinary review/rework and task documentation. Core capacity scenario is six roles at 3.5 delivery days/week each; 30% reserved for coordination/support. High range 0.8–1.2x, medium 1–1.5x, low 1–2x; ranges are planning bounds, not calibrated probabilities. 25% program integration reserve is an alternate portfolio allowance, not additive to summed upper ranges. External assessment fees/waits, unbounded finding remediation, hiring, unknown customer gaps and ongoing operations are excluded and require re-estimate.

Base effort: **427 engineering days**. A 25% integration/rework allowance gives **533.75 days**; summing task upper planning bounds gives **720.6 days**. These are alternative views of uncertainty, not budgets to add together and not calendar commitments. Earlier 430-day/538-day totals are superseded. Research execution time and model charges, external assessment lead time/fees, unknown security fixes, customer-required gaps and ongoing support are not disguised inside a fixed ten-day task. An unknown required fix becomes a new ID/PR with scope and tests before its gate can close.

| Primary role | Base delivery days | Single-role capacity lower bound at 3.5 days/week |
| --- | ---: | ---: |
| TL | 73 | 20.9 weeks |
| FE | 23 | 6.6 weeks |
| RS | 57 | 16.3 weeks |
| PL | 86 | 24.6 weeks |
| BE | 76.5 | 21.9 weeks |
| QE | 111.5 | 31.9 weeks |

Roles: TL technical lead/backend, BE execution/backend, PL platform/SRE, FE frontend, RS research, QE quality. PM and SEC are shared reviewers/decision owners; actual names and independent statistical/security reviewers are not yet confirmed. Task effort includes ordinary verification and review work; the 30% availability reserve covers coordination, support and interruptions. Do not double-book primary tasks or assume the six roles are six available employees. QE ownership includes independent integration/rehearsal evidence, while every implementing engineer still writes their task tests.

QE and PL are material resource constraints. At the Day 10 review, redistribute suitable harness ownership to implementing engineers with independent QE review, or fund additional capacity; re-estimate before changing dates. Do not eliminate independent checks to make the schedule fit. No staffing, procurement or recurring infrastructure purchase is authorized by a planning estimate.

## Critical path, parallel tracks and contingencies

The task DAG has **511 edges**, **26 explicit gates**, no cycles and a **145.5-engineering-day longest effort path**. At 70% delivery availability this alone is about 41.6 workweeks before role contention, mandatory elapsed windows and external waits. It is a lower bound, not a launch forecast. Zero effort on an external gate means engineering effort is not estimated; it never means the gate is already satisfied or has zero lead time.

The computed effort path, including integration joins, is:

```text
E0 → AR-001-A → AR-002-A → AR-002-B → AR-004-B → AR-004-C → G0 → AR-005-B →
AR-005-C → AR-007-A → AR-007-B → AR-007-C → AR-008-A → AR-008-B → AR-010-A → AR-010-B →
AR-012-B → AR-014-A → AR-014-B → AR-017-A → AR-023-A → AR-023-B → AR-023-C → AR-025-A →
AR-025-B → AR-025-C → AR-026-B → AR-026-C → AR-029-B → AR-030-B → AR-031-B → AR-031-C →
AR-034-D → G4 → AR-035-B → AR-035-C → AR-036-A → AR-036-B → AR-036-C → AR-038-A →
AR-038-B → AR-038-C → AR-039-C → G5 → AR-047-C → G6 → AR-048-A → AR-048-B →
AR-048-C → AR-049-A → AR-049-B → AR-049-C → AR-050-A → AR-050-B → AR-050-C → G7
```

Calendar-critical competitors include ENV0/IDP0 provisioning, PARTNER0/DATA0 access, affordable sample design, independent assessor availability/remediation, P28 (28 days after both partner onboarding measurements begin), funded support and D30 (30 days after accepted rollout). The longest calendar path can change after any of these resolves.

| Parallel track | Earliest usable handoff | Work that may overlap | Join / constraint |
| --- | --- | --- | --- |
| Foundation | G0 and reviewed M1 proposal | Migration BE; safe diagnostics PL; QE fixture harness; TL reviews ownership | Scoped repositories before run/object consumers; admission before budget integration |
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
| M0 | 8.5 days | Days 1–9 conditional on real approval; unresolved decisions extend M0 | [G0](#g0): M0 accepted; schemas and initial migration scope reviewed. |
| M1 | 39.5 days | Continue remaining foundation work after G0; first integration is migration plus revision guard | [G1](#g1): Historical identities intact; all 24 M1 behavioral cases, scope/lease/budget concurrency and compatibility pass. |
| M2 | 69 days | Start each task after its foundation inputs; joins G1 plus early staging | [G2](#g2): Real gVisor isolation/restore/cleanup, cloud store/key rotation, fail-closed lease and accounted live smoke verified. |
| M3 | 70 days | Trial/statistics work may overlap M2 after its contracts; joins G2 | [G3](#g3): Resumable distributed studies preserve frozen protocol, missingness and all call accounting; reports independently recompute. |
| M4 | 82 days | Early IaC after G0; UI/SDK after producer APIs; complete after G3 | [G4](#g4): Independent full browser/SDK workflow and fresh install pass with real IdP/GCS/KMS/gVisor and selected adapter. |
| M5 | 50 days | Only after G4 and funded customer/data/recovery gates; >=28-day measurement | [G5](#g5): Two partners, four calendar weeks, supported denominator/product metrics and natural-failure claim review accepted; no pilot blockers. |
| M6 | 78 days | Hardening overlaps stable M3–M5; readiness closure only after G5 | [G6](#g6): Forecast load/24h soak, zone/regional recovery, independent security retest, procurement, support and upgrade evidence pass with no prohibited blocker. |
| M7 | 30 days | Only after G6 and launch approval; >=30-day operating review | [G7](#g7): Controlled launch accepted and 30-day operating review complete; next scope separately approved. |

Integration checkpoints: Day 5 fixture/workflow review; Day 8 G0 decision packet; Day 10 scope/capacity reforecast; AR-005-C historical upgrade and runtime guard; AR-012-B all M1 cases; AR-019-C real runtime/store/key/fault evidence; AR-026-C distributed study integrity; AR-034-D independent browser/SDK flow; AR-035-C pre-ingestion recovery; AR-039-C two-partner pilot review; AR-047-C readiness audit; AR-048-C release decision; AR-049-C accepted rollout; AR-050-C 30-day closure. During active M1–M4 work, merge small reviewed PRs, run daily shared synthetic integration and twice-weekly cross-role reviews. A review meeting is not a passing gate.

## First two weeks — day-by-day

Working days, not dates; no weekend work assumed. Each allocation below is **0.5 engineering day** unless stated otherwise, leaving at least 0.5 day for peer review, decisions, maintenance and contingency. Roles absent from a day perform reviews or remain unallocated; do not invent blocked feature work to fill a calendar. PM/SEC participate in relevant decision reviews, with availability confirmed at E0. This is intentionally conservative while the contracts and staffing are uncertain.

| Week / day | Primary delivery allocation | Checkpoint and dependency condition |
| --- | --- | --- |
| W1 / Day 1 | TL: [AR-001-A](#ar-001-a) (0.5d); BE: [AR-004-A](#ar-004-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | E0 approval and staffing recorded before any scheduled task starts; TL/PM select interview evidence. Others review existing baseline. |
| W1 / Day 2 | TL: [AR-001-A](#ar-001-a) (0.5d); BE: [AR-004-A](#ar-004-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | Workflow and interface inventory PR review; no runtime feature work. |
| W1 / Day 3 | FE: [AR-001-B](#ar-001-b) (0.5d); RS: [AR-002-A](#ar-002-a) (0.5d); PL: [AR-003-A](#ar-003-a) (0.5d); QE: [AR-005-A](#ar-005-a) (0.5d) | Historical fixture manifest finishes; product/privacy/security review uses synthetic examples. |
| W1 / Day 4 | FE: [AR-001-B](#ar-001-b) (0.5d); RS: [AR-002-A](#ar-002-a) (0.5d); PL: [AR-003-A](#ar-003-a) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Review metric denominators, corpus rights shape and denied network paths. |
| W1 / Day 5 | RS: [AR-002-B](#ar-002-b) (0.5d); PL: [AR-003-B](#ar-003-b) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Week 1 integration: reconcile workflow/contract/fixture inventory; unresolved access or staffing gets owner and date. |
| W2 / Day 6 | RS: [AR-002-B](#ar-002-b) (0.5d); PL: [AR-003-B](#ar-003-b) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Freeze proposed split/evaluator assumptions; actual funding and customer rights remain pending conditions. |
| W2 / Day 7 | TL: [AR-004-B](#ar-004-b) (0.5d); PL: [AR-011-A](#ar-011-a) (0.5d); QE: [AR-012-A](#ar-012-a) (0.5d) | Cross-role contract review and negative fixture checks. No behavioral acceptance claimed. |
| W2 / Day 8 | TL: [AR-004-B](#ar-004-b) (0.5d); PL: [AR-011-A](#ar-011-a) (0.5d) | G0 decision packet: named team, funded scope, region/data policy, contracts and first migration slice; send for actual owner decision. |
| W2 / Day 9 | TL: [AR-004-C](#ar-004-c) (0.5d) | Conditional on ARCH0 actual approval; record G0 or keep blocked. Review days 1–8 throughput, role load and unknowns. |
| W2 / Day 10 | BE: [AR-005-B](#ar-005-b) (0.5d); PL: [AR-011-B](#ar-011-b) (0.5d) | Conditional on G0: start migration and safe-error PRs only. Both continue beyond day 10. If G0 pending, no runtime work; resolve decision gaps. |

Day 9 is conditional on actual ARCH0 approval after the Day 8 packet. If it does not arrive, AR-004-C stays blocked and Day 10 implementation does not start. Only already-authorized decision/fixture review continues. Day 10 starts AR-005-B (0.5 of 3 days) and AR-011-B (0.5 of 2 days); neither is falsely marked complete. Project authorization implementation AR-007-A waits for AR-005-C, so it is deliberately absent from the first fortnight. No task is scheduled before a predecessor is complete; same-day finish/start assumptions are not used.

## Interface and schema contract register

C04 links the [M1 API](../contracts/proposals/m1.openapi.json), [logical data model](../contracts/proposals/m1.data-model.json) and [24 planned acceptance cases](../contracts/proposals/m1.acceptance.json). Task test references such as M1-001 mean CT-M1-001 in that file. Other interfaces below are required outputs of their producer PRs. Producers include success, denial, invalid, timeout and uncertain fixtures plus consumer review. No dependent implementation can begin until those fixtures and compatibility rules are available.

| Contract | Producer / availability | Required API/schema/interface |
| --- | --- | --- |
| C01 — Workflow and metrics | [AR-001-A](#ar-001-a) | Two supported journeys, input/output examples, capture denominator, investigation timing, scope and pilot usefulness thresholds. |
| C02 — Corpus/evaluator protocol | [AR-002-A](#ar-002-a) | Rights/source/evaluator manifest; disjoint task families; failure taxonomy; immutable grader, split and private evidence policy. |
| C03 — Trust/deployment decisions | [AR-003-A](#ar-003-a) | One-organization topology; deny-by-default sandbox network; API/worker identities; spending, data and region decisions. |
| C04 — M1 API, schema and acceptance proposals | Existing draft; freeze at G0 | Existing m1.openapi.json, m1.data-model.json and m1.acceptance.json; exact route/schema semantics remain pending until G0. |
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

## Gate register

Every gate below is currently **Not satisfied**. Integration gates join every listed required task; partial packages cannot close a milestone. External conditions require actual evidence from the responsible owner. Elapsed windows require both the minimum duration and valid measurements. No automated checker manufactures human approval.

<a id="e0"></a>

**E0 — external gate; owner: Product owner.** Prerequisites: None. Explicit approval of this execution backlog and which named staff/capacity can start. No implementation before this record.

<a id="arch0"></a>

**ARCH0 — external gate; owner: Product owner with TL/SEC/RS.** Prerequisites: [AR-004-B](#ar-004-b). Actual disposition of M0 architecture/contracts, workload, operating region, staffing, model/infra funding and first migration slice.

<a id="g0"></a>

**G0 — integration gate; owner: TL.** Prerequisites: [AR-001-B](#ar-001-b), [AR-002-B](#ar-002-b), [AR-003-B](#ar-003-b), [AR-004-C](#ar-004-c). M0 accepted; schemas and initial migration scope reviewed.

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

**G1 — integration gate; owner: TL/QE.** Prerequisites: [AR-005-A](#ar-005-a), [AR-005-B](#ar-005-b), [AR-005-C](#ar-005-c), [AR-006-A](#ar-006-a), [AR-006-B](#ar-006-b), [AR-007-A](#ar-007-a), [AR-007-B](#ar-007-b), [AR-007-C](#ar-007-c), [AR-008-A](#ar-008-a), [AR-008-B](#ar-008-b), [AR-009-A](#ar-009-a), [AR-009-B](#ar-009-b), [AR-010-A](#ar-010-a), [AR-010-B](#ar-010-b), [AR-011-A](#ar-011-a), [AR-011-B](#ar-011-b), [AR-011-C](#ar-011-c), [AR-012-A](#ar-012-a), [AR-012-B](#ar-012-b), [G0](#g0). Historical identities intact; all 24 M1 behavioral cases, scope/lease/budget concurrency and compatibility pass.

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

A task is one independently reviewable PR or evidence/decision-record PR. It may introduce a disabled path or a reviewed contract, but cannot merge a newly reachable unsafe partial implementation. Dependent PRs use the merged producer interface; parent packages are not giant implementation PRs. Automatic tests listed here are requirements, not assertions that those tests already exist or pass.

## Assignable task cards

<a id="ar-001"></a>

### AR-001 — Make supported investigations and their business value explicit

M0 / P0 · 2 PRs · 2 engineering days · Not started · [Tracking issue #1](https://github.com/spei04/agent-rewind/issues/1)

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
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-002"></a>

### AR-002 — Protect corpus rights and establish a credible natural-failure evaluation protocol

M0 / P0 · 2 PRs · 2 engineering days · Not started · [Tracking issue #2](https://github.com/spei04/agent-rewind/issues/2)

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
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-003"></a>

### AR-003 — Bound deployment trust, operating responsibility and financial exposure

M0 / P0 · 2 PRs · 2 engineering days · Not started · [Tracking issue #3](https://github.com/spei04/agent-rewind/issues/3)

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-004"></a>

### AR-004 — Resolve architecture and interface decisions before runtime changes

M0 / P0 · 3 PRs · 2.5 engineering days · Not started · [Tracking issue #4](https://github.com/spei04/agent-rewind/issues/4)

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
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-004-b"></a>

#### AR-004-B — Consumer review and M1 contract freeze proposal

- **Objective:** Resolve architecture and interface decisions before runtime changes. This task delivers consumer review and m1 contract freeze proposal.
- **Implementation scope / PR boundary:** Resolve API/schema/test disagreements, explicit composite scope constraints and deferred endpoint ownership.
- **Out of scope:** No implementation sign-off or invented reviewers.
- **Prerequisites:** [AR-002-B](#ar-002-b), [AR-003-B](#ar-003-b), [AR-004-A](#ar-004-a), [AR-005-A](#ar-005-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** BE, PL, FE, RS, QE and SEC review results recorded; incompatible changes have decision owner.
- **Required automated tests:** Run contract structure, dependency and historical-fixture manifest checks.
- **Security and reliability:** Approval evidence is required; silence is not acceptance.
- **Effort / confidence:** 1 engineering days; planning range 1–1.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-005"></a>

### AR-005 — Upgrade stored history safely without changing evidence identity

M1 / P0 · 3 PRs · 6 engineering days · Not started · [Tracking issue #5](https://github.com/spei04/agent-rewind/issues/5)

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
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-005-b"></a>

#### AR-005-B — Explicit Alembic installation and adoption CLI

- **Objective:** Upgrade stored history safely without changing evidence identity. This task delivers explicit alembic installation and adoption cli.
- **Implementation scope / PR boundary:** Add revision chain, baseline fingerprint, writer-drain adoption and explicit project mapping command.
- **Out of scope:** No online data rewrite, automatic downgrade or run projection.
- **Prerequisites:** [G0](#g0), [AR-005-A](#ar-005-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Empty install and known baseline upgrade preserve all manifest identities; unknown schema refuses safely.
- **Required automated tests:** M1-001 through M1-004: fresh/legacy/unknown, transactional interruption and concurrent migrators.
- **Security and reliability:** Migration credential only; lock/timeouts; backup before adoption.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-005-c"></a>

#### AR-005-C — Runtime revision guard and recovery guide

- **Objective:** Upgrade stored history safely without changing evidence identity. This task delivers runtime revision guard and recovery guide.
- **Implementation scope / PR boundary:** Remove runtime create_all, check compatible revision at API/worker readiness and document failed-upgrade recovery.
- **Out of scope:** No HA rolling upgrade claim.
- **Prerequisites:** [AR-005-B](#ar-005-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** No runtime DDL; unsupported revision prevents admission and worker dispatch; compatible rollback demonstrated on fixture.
- **Required automated tests:** Least-privilege DB startup, future revision, upgrade failure and recovery tests.
- **Security and reliability:** Fail closed when schema cannot be read; retain rollback evidence.
- **Effort / confidence:** 1.5 engineering days; planning range 1.5–2.2; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-006"></a>

### AR-006 — Make large run histories queryable through bounded authorized requests

M1 / P0 · 2 PRs · 5 engineering days · Not started · [Tracking issue #6](https://github.com/spei04/agent-rewind/issues/6)

<a id="ar-006-a"></a>

#### AR-006-A — Scoped run projection and resumable backfill

- **Objective:** Make large run histories queryable through bounded authorized requests. This task delivers scoped run projection and resumable backfill.
- **Implementation scope / PR boundary:** Create run_index and bounded progress-marked backfill with parent scope closure and preserved event heads.
- **Out of scope:** No branch or event API redesign.
- **Prerequisites:** [AR-005-C](#ar-005-c), [AR-007-A](#ar-007-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** All known records map or fail with diagnostics; retry resumes without duplicate rows or history edits.
- **Required automated tests:** Interrupted batches, orphan lineage, equal timestamps and mixed historical/new records.
- **Security and reliability:** Unmapped records quarantine; no default cross-project exposure.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-006-b"></a>

#### AR-006-B — Stable cursor listing and run summaries

- **Objective:** Make large run histories queryable through bounded authorized requests. This task delivers stable cursor listing and run summaries.
- **Implementation scope / PR boundary:** Implement scoped list/detail v1 routes with opaque bound cursors, stable tie ordering and fixed page limits.
- **Out of scope:** No full history download or arbitrary search engine.
- **Prerequisites:** [AR-006-A](#ar-006-a), [AR-007-C](#ar-007-c), [AR-011-B](#ar-011-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Traversal has no duplicate/missing rows on fixed corpus; foreign/modified cursor rejected; indexed query plan.
- **Required automated tests:** M1-005/006, concurrent insert semantics, invalid limit and missing/foreign run cases.
- **Security and reliability:** Authorize before loading body; no payload in cursor/errors.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-007"></a>

### AR-007 — Prevent cross-project access through both legacy and new paths

M1 / P0 · 3 PRs · 5.5 engineering days · Not started · [Tracking issue #7](https://github.com/spei04/agent-rewind/issues/7)

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
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-007-b"></a>

#### AR-007-B — Central scoped resource repositories

- **Objective:** Prevent cross-project access through both legacy and new paths. This task delivers central scoped resource repositories.
- **Implementation scope / PR boundary:** Require project/principal context for runs, jobs, studies, keys and artifact resolution.
- **Out of scope:** No route migration or new UI.
- **Prerequisites:** [AR-007-A](#ar-007-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C05; definitions and producer availability in the contract register.
- **Acceptance criteria:** Foreign IDs are denied before decrypt/load; every repository lookup has explicit scope.
- **Required automated tests:** Repository authorization matrix, forged lineage, same hash across projects.
- **Security and reliability:** Default deny and uniform not-found responses for inaccessible resources.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** TL; required reviewers: BE, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-007-c"></a>

#### AR-007-C — Legacy and v1 authorization enforcement

- **Objective:** Prevent cross-project access through both legacy and new paths. This task delivers legacy and v1 authorization enforcement.
- **Implementation scope / PR boundary:** Route all legacy and v1 reads/writes, exports, cancellation and key use through scoped checks.
- **Out of scope:** No session redesign or customer IdP provisioning.
- **Prerequisites:** [AR-007-B](#ar-007-b), [AR-011-B](#ar-011-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C05; definitions and producer availability in the contract register.
- **Acceptance criteria:** Revocation immediately applies to idempotent replay and in-flight API access; bypass inventory empty.
- **Required automated tests:** M1-007/009 route matrix, legacy aliases, cookie CSRF and scoped API keys.
- **Security and reliability:** Keep second-project feature disabled until full route deny suite passes.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-008"></a>

### AR-008 — Make retries safe and admission/cancellation behavior predictable

M1 / P0 · 2 PRs · 4 engineering days · Not started · [Tracking issue #8](https://github.com/spei04/agent-rewind/issues/8)

<a id="ar-008-a"></a>

#### AR-008-A — Canonical request and durable admission identity

- **Objective:** Make retries safe and admission/cancellation behavior predictable. This task delivers canonical request and durable admission identity.
- **Implementation scope / PR boundary:** Implement operation/key alias constraints, default materialization and transactional job/scope/audit publication after upload.
- **Out of scope:** No provider retry policy or study submission.
- **Prerequisites:** [AR-007-C](#ar-007-c), [AR-009-B](#ar-009-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Concurrent same key or client ID creates one job; new key aliases original; changed request conflicts.
- **Required automated tests:** M1-010/012 concurrency, altered source whitespace, canonical defaults, alias conflict and crash after upload.
- **Security and reliability:** Reauthorize retries; preserve exact source text; no network inside DB transaction.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-008-b"></a>

#### AR-008-B — Submit, operation status and cancellation routes

- **Objective:** Make retries safe and admission/cancellation behavior predictable. This task delivers submit, operation status and cancellation routes.
- **Implementation scope / PR boundary:** Expose five M1 operations with task limits, stable errors and atomic cancel intent.
- **Out of scope:** No branch or study endpoints.
- **Prerequisites:** [AR-008-A](#ar-008-a), [AR-011-B](#ar-011-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Accepted IDs stable; invalid inputs never enqueue; cancellation preserves terminal outcomes.
- **Required automated tests:** M1-013/014 path traversal, byte/count limits, cancel races, unauthenticated requests.
- **Security and reliability:** Bound payload processing; cancellation denies new work even if result delivery delayed.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-009"></a>

### AR-009 — Keep published evidence immutable, scoped and complete

M1 / P0 · 2 PRs · 4 engineering days · Not started · [Tracking issue #9](https://github.com/spei04/agent-rewind/issues/9)

<a id="ar-009-a"></a>

#### AR-009-A — Versioned object/ref metadata and storage protocol

- **Objective:** Keep published evidence immutable, scoped and complete. This task delivers versioned object/ref metadata and storage protocol.
- **Implementation scope / PR boundary:** Define storage interface and metadata constraints for immutable objects, verified digest and project-scoped owner references.
- **Out of scope:** No GCS adapter, KMS rotation or GC.
- **Prerequisites:** [AR-007-A](#ar-007-a), [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Composite references cannot cross projects; existing encrypted format remains readable.
- **Required automated tests:** Schema scope violations, legacy ciphertext round-trip and duplicate reference tests.
- **Security and reliability:** Opaque locator is not authorization; encryption key stays server-side.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-010"></a>

### AR-010 — Enforce budget limits before every potentially paid action

M1 / P0 · 2 PRs · 5 engineering days · Not started · [Tracking issue #10](https://github.com/spei04/agent-rewind/issues/10)

<a id="ar-010-a"></a>

#### AR-010-A — Integer ledger and hierarchical reservations

- **Objective:** Enforce budget limits before every potentially paid action. This task delivers integer ledger and hierarchical reservations.
- **Implementation scope / PR boundary:** Implement org/project/job accounts, unique logical calls, ordered row locks and compatibility aggregate.
- **Out of scope:** No online provider dispatch or refunds without receipts.
- **Prerequisites:** [AR-008-B](#ar-008-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Concurrent reservations cannot exceed any cap; periods remain attached to admission; no double accounting.
- **Required automated tests:** M1-018/020 races, deadlock retry, period rollover, repeated logical call and integer boundaries.
- **Security and reliability:** Keep uncertain reservations held; no model call while transaction open.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-010-b"></a>

#### AR-010-B — Lease-fenced admission permits and cancellation accounting

- **Objective:** Enforce budget limits before every potentially paid action. This task delivers lease-fenced admission permits and cancellation accounting.
- **Implementation scope / PR boundary:** Require valid owner/lease/cancel state before issuing permit; expose ledger diagnostics without prompt bodies.
- **Out of scope:** No distributed study scheduling or automatic paid replay.
- **Prerequisites:** [AR-010-A](#ar-010-a), [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Stale owner, cancelled job or DB outage cannot obtain new permit; reconciliation requires evidence.
- **Required automated tests:** M1-019/021 stale token, repeated release, missing DB, terminal job and cancel race.
- **Security and reliability:** No automatic timeout refund; prevent privileged bypass of budget hierarchy.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-011"></a>

### AR-011 — Diagnose failures without exposing secrets or losing request context

M1 / P0 · 3 PRs · 5 engineering days · Not started · [Tracking issue #11](https://github.com/spei04/agent-rewind/issues/11)

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-011-b"></a>

#### AR-011-B — Safe exception mapping and readiness enforcement

- **Objective:** Diagnose failures without exposing secrets or losing request context. This task delivers safe exception mapping and readiness enforcement.
- **Implementation scope / PR boundary:** Implement redacted boundary handlers and safe DB/store/schema readiness responses.
- **Out of scope:** No broad observability platform deployment.
- **Prerequisites:** [G0](#g0), [AR-011-A](#ar-011-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Known faults map to stable codes; unknown faults return safe message and correlated restricted diagnostic.
- **Required automated tests:** M1-022/023 secret canaries, malformed exceptions and dependency outage.
- **Security and reliability:** Readiness prevents unsafe admission; liveness does not disclose dependency secrets.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-011-c"></a>

#### AR-011-C — Trace propagation and operational counters

- **Objective:** Diagnose failures without exposing secrets or losing request context. This task delivers trace propagation and operational counters.
- **Implementation scope / PR boundary:** Propagate request/job IDs and instrument admission, queue delay, failure and budget counters.
- **Out of scope:** No SLO claim or paging rota.
- **Prerequisites:** [AR-011-B](#ar-011-b), [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** Async worker logs correlate without recording payload; bounded series count under many IDs.
- **Required automated tests:** Trace continuity, label cardinality and redaction regression tests.
- **Security and reliability:** Access-restricted logs and controlled retention; no secret-bearing baggage.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-012"></a>

### AR-012 — Detect incompatible or unsafe foundation changes before integration

M1 / P0 · 2 PRs · 5 engineering days · Not started · [Tracking issue #12](https://github.com/spei04/agent-rewind/issues/12)

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
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-012-b"></a>

#### AR-012-B — Integrated M1 concurrency and compatibility gate

- **Objective:** Detect incompatible or unsafe foundation changes before integration. This task delivers integrated m1 concurrency and compatibility gate.
- **Implementation scope / PR boundary:** Wire PostgreSQL/object-backed required checks for all 24 M1 cases and upgrade/legacy compatibility.
- **Out of scope:** No benchmark capacity or enterprise readiness declaration.
- **Prerequisites:** [AR-006-B](#ar-006-b), [AR-008-B](#ar-008-b), [AR-009-B](#ar-009-b), [AR-010-B](#ar-010-b), [AR-011-C](#ar-011-c), [AR-012-A](#ar-012-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C04; definitions and producer availability in the contract register.
- **Acceptance criteria:** G1 evidence records commit, runtime and every pass/fail; no fixture-only substitute for concurrency tests.
- **Required automated tests:** Execute all M1 cases plus old-reader compatibility and fail-closed startup.
- **Security and reliability:** Tests isolate projects and contain no real model credentials.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
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

M2 / P0 · 4 PRs · 11 engineering days · Not started

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-020-a"></a>

#### AR-020-A — Study, pair, trial and attempt contract

- **Objective:** Give every study, logical trial and attempt a durable scoped identity. This task delivers study, pair, trial and attempt contract.
- **Implementation scope / PR boundary:** Freeze logical identities, protocol digests, immutable freeze and attempt/uncertain states; specify study API needs; extend the M1 org/project/job ledger with study-scoped accounts and bind every child attempt/call to its study cap.
- **Out of scope:** No coordinator or estimators.
- **Prerequisites:** [AR-012-B](#ar-012-b), [AR-010-B](#ar-010-b), [AR-002-B](#ar-002-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** RS/QE approve unique outcome rules, missingness and coordinator transition table.
- **Required automated tests:** Schema/transition fixtures reject duplicate logical arm and changed frozen candidate.
- **Security and reliability:** Separate attempt diagnostics from immutable analytical outcomes.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-020-b"></a>

#### AR-020-B — Trial schema and repository migration

- **Objective:** Give every study, logical trial and attempt a durable scoped identity. This task delivers trial schema and repository migration.
- **Implementation scope / PR boundary:** Add normalized studies/pairs/trials/attempts and scoped repositories with fenced updates; migrate study budget accounts and enforce same-project study/job/call relationships.
- **Out of scope:** No fanout dispatch.
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-005-C](#ar-005-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Uniqueness persists under concurrent inserts; all foreign-project relations rejected.
- **Required automated tests:** Upgrade legacy study fixture, FK closure, concurrent insert and stale-attempt tests.
- **Security and reliability:** Preserve historical report interpretation; bounded backfill with explicit version.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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

- **Objective:** Resume studies without silently repeating paid work or changing the protocol. This task delivers durable coordinator phase machine.
- **Implementation scope / PR boundary:** Persist discovery/freeze/confirmation/publication phases and resumable work intents.
- **Out of scope:** No autoscaling or cross-region active-active.
- **Prerequisites:** [AR-020-C](#ar-020-c), [AR-014-C](#ar-014-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08, C06; definitions and producer availability in the contract register.
- **Acceptance criteria:** Completed arms not rerun after coordinator restart; no next-phase dispatch before barrier.
- **Required automated tests:** Restart at each intent/commit boundary and duplicate coordinator claim tests.
- **Security and reliability:** Explicit generation fencing; no implicit paid retries.
- **Effort / confidence:** 4 engineering days; planning range 4–6; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Implementation scope / PR boundary:** Specify call identity, request/price hash, observed usage, remote ID and evidence-based resolution rules.
- **Out of scope:** No provider retry implementation.
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-010-B](#ar-010-b), [AR-017-A](#ar-017-a). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Continuation and proposal calls use same accounting vocabulary; ambiguity never equals refund.
- **Required automated tests:** Receipt schema, conflicting duplicate and unverifiable reconciliation fixtures.
- **Security and reliability:** Receipt excludes prompt/secret; restricted operator reconciliation authority.
- **Effort / confidence:** 2 engineering days; planning range 2–3; medium confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-023-b"></a>

#### AR-023-B — Dispatch receipts and uncertain-call journal

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

- **Objective:** Account for every provider call and preserve uncertainty until reconciled. This task delivers reconciliation command and accounting export.
- **Implementation scope / PR boundary:** Add audited operator reconciliation with evidence attachment and immutable adjustment entries.
- **Out of scope:** No automatic billing integration or silent historical edit.
- **Prerequisites:** [AR-023-B](#ar-023-b), [AR-020-C](#ar-020-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08; definitions and producer availability in the contract register.
- **Acceptance criteria:** Repeated reconciliation idempotent; denied/contradictory evidence cannot release hold.
- **Required automated tests:** Evidence mismatch, replay, cap overflow and concurrent reconcile tests.
- **Security and reliability:** Only scoped privileged operator may reconcile; no manual SQL bypass.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** BE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-024"></a>

### AR-024 — Report intervention effects with correct denominators and uncertainty

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-024-a"></a>

#### AR-024-A — Estimator, missingness and experiment report contract

- **Objective:** Report intervention effects with correct denominators and uncertainty. This task delivers estimator, missingness and experiment report contract.
- **Implementation scope / PR boundary:** Specify task-conditional estimand, paired design, intervals, missing data and invalidation/version fields.
- **Out of scope:** No adaptive stopping or learned estimator.
- **Prerequisites:** [AR-020-A](#ar-020-a), [AR-002-B](#ar-002-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** No generalization claim from one run; report includes all assigned trials and uncertain calls.
- **Required automated tests:** Golden tiny samples, ties, all-failed, all-missing and imbalanced fixtures.
- **Security and reliability:** Protocol fixed before outcomes; distinguish exploratory selection and confirmation.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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

<a id="ar-025"></a>

### AR-025 — Compare useful intervention locations against fair inexpensive baselines

M3 / P0 · 3 PRs · 10 engineering days · Not started

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

- **Objective:** Compare useful intervention locations against fair inexpensive baselines. This task delivers cost-matched ranking baselines and negative controls.
- **Implementation scope / PR boundary:** Implement last-error, uniform-location and bounded search baselines with identical evaluator/call cost caps.
- **Out of scope:** No claim of superiority before held-out study.
- **Prerequisites:** [AR-025-A](#ar-025-a), [AR-024-C](#ar-024-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Baseline comparison records consumed budget and candidate count; negative intervention remains measurable.
- **Required automated tests:** Fixed synthetic failure rankings, budget parity and deliberately irrelevant edit tests.
- **Security and reliability:** Do not cherry-pick baselines or omit unsuccessful branches.
- **Effort / confidence:** 4 engineering days; planning range 4–8; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-025-c"></a>

#### AR-025-C — Recomputable ranking evidence package

- **Objective:** Compare useful intervention locations against fair inexpensive baselines. This task delivers recomputable ranking evidence package.
- **Implementation scope / PR boundary:** Export safe candidate/protocol/receipt hashes and reproduce ranking plus report from stored evidence.
- **Out of scope:** No public release of partner traces.
- **Prerequisites:** [AR-025-B](#ar-025-b), [AR-023-C](#ar-023-c). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C08, C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Independent recomputation matches original; tampering or missing receipt fails verification.
- **Required automated tests:** Corrupt/missing record, changed estimator and reordered receipt fixtures.
- **Security and reliability:** Private source stays private; export obeys project authorization.
- **Effort / confidence:** 3 engineering days; planning range 3–4.5; medium confidence.
- **Responsible role:** QE; required reviewers: TL, domain owner. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

<a id="ar-026"></a>

### AR-026 — Establish experiment correctness before relying on research conclusions

M3 / P0 · 3 PRs · 10 engineering days · Not started

<a id="ar-026-a"></a>

#### AR-026-A — Frozen evaluation and power decision

- **Objective:** Establish experiment correctness before relying on research conclusions. This task delivers frozen evaluation and power decision.
- **Implementation scope / PR boundary:** Preregister useful-location metric, minimum effect, task sample, multiple comparisons and stop/invalidation rules.
- **Out of scope:** No promise that 100 failures fit existing budget.
- **Prerequisites:** [AR-024-C](#ar-024-c), [AR-025-B](#ar-025-b), [AR-002-B](#ar-002-b). E0 applies transitively; required producer contracts must be reviewed.
- **Required contracts:** C02, C09; definitions and producer availability in the contract register.
- **Acceptance criteria:** Protocol frozen before held-out access; affordable sample supports claim or scope explicitly narrows.
- **Required automated tests:** Leakage guard, power arithmetic and protocol immutability checks.
- **Security and reliability:** No open-ended model spend; paid evaluation gated separately.
- **Effort / confidence:** 3 engineering days; planning range 3–6; low confidence.
- **Responsible role:** RS; required reviewers: QE, independent statistical reviewer. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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
- **Implementation scope / PR boundary:** Implement paged timeline/files, idempotent branch admission and bounded comparison from immutable lineage.
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
- **Implementation scope / PR boundary:** Expose scoped idempotent study commands, paged trial status and recomputable report/export.
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
- **Implementation scope / PR boundary:** Implement bounded evidence export, authenticated deletion intent and hold-protected tombstones.
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

M4 / P0 · 4 PRs · 10 engineering days · Not started

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
- **Responsible role:** PL; required reviewers: SEC, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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

M4 / P0 · 4 PRs · 12 engineering days · Not started

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
- **Responsible role:** FE; required reviewers: TL, QE. Named assignee pending staffing.
- **Definition of done:** All task-specific acceptance and tests above, plus the common DoD; actual sign-off/evidence required. No other task is implicitly included.
- **Progress:** Not started; approval/prerequisite gates apply.

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

## Highest-risk assumptions and decisions requiring approval

| Decision / risk | Recommendation | Needed before / owner |
| --- | --- | --- |
| Execution authority | Approve this baseline and M0/preparatory scope; approve first M1 migration slice at G0. Keep future milestones evidence-gated. | E0 then ARCH0/G0 — product owner |
| Actual staffing and delivery rate | Confirm six named core roles or provide real capacity. Replan if fewer people; verification/platform ownership is a bottleneck. No launch date commitment now. | E0 staffing; Day 10/G1 reforecast — product owner/TL |
| Recurring cloud/identity operations | Retain accepted single-organization self-hosted GCP/gVisor direction. Choose region, cloud budget owner/cap, test IdP and funded support hours. Development VM access does not supply these. | ENV0/IDP0/SUPPORT0 — product owner/PL/customer admin |
| Affordable valid research | Retain the existing $200 validation cap; reconcile before smoke. Approve the natural-failure study budget only after sample/power/permission review; narrow the claim if unaffordable or underpowered. | PAID0, DATA0, STUDYFUNDS0 — RS/data owner/product owner |
| Customer availability and scope | Use two design partners for the first pilot, each with permitted restorable workflows; both weekly users and both adopting a regression/policy fix is the proposed exit target. Recruit a third only as separately funded expansion. | PARTNER0/PILOT0/G5 — PM/customers |
| Independent review and unknown fixes | Fund an assessor and independent statistical reviewer; book early. Do not accept unresolved critical/high exploitable defects or missing restoration evidence to meet a date. New findings receive scoped fix tasks and revised estimates. | AUDIT0/SECFIX0/G6 — product owner/SEC/RS |

No question above asks to reapprove the already selected core architecture. The unresolved choices are execution scope, real capacity, specific funding/access, customer evidence and independent review. Future release approval LAUNCH0 remains separate from backlog approval.

## Dependency review, progress and maintenance

Completed planning validation on 2026-10-19: 145 unique task IDs across 50 parents; all required fields present; task sizes <=4 days; all 511 edges resolve; acyclic graph including external/integration/elapsed gates; every implementation task depends on E0; every producer contract is an ancestor of its consumer; every milestone gate joins its required tasks; first-ten-day predecessor and effort-capacity checks pass under explicit E0/ARCH0 timing conditions. Rollups reconcile to 427 days. Conditional schedule validation is not evidence those approvals exist.

The 12 existing GitHub issues remain parent trackers, with task-card links and updated rollups. All 12 bodies, open states and approval labels were read back; both milestone descriptions were updated. Nineteen obsolete coarse parent dependency edges were removed because they cannot represent preparatory child handoffs; exact dependencies remain in the validated 511-edge task/gate graph. No task is closed merely because this backlog exists. Future child issues should be materialized from these IDs when their milestone is authorized; preserve exact scope/dependencies and link them back here. This avoids treating unapproved later contracts as active assignments. No application behavioral tests, load tests, production security assessment, deployment rehearsal or recovery drill was run in this planning-only revision.

Update procedure for each completed PR: update task status and evidence in the machine-readable ledger and this card; recalculate parent/milestone effort/status and dependency changes; update PLAN Section 10/14 and the matching issue; rerun ID/required-field/DAG/contract-availability/first-fortnight allocation checks; verify local links and draft OpenAPI structure. Any added edge, new gate or changed estimate requires schedule revalidation. Do not mark a task Verified without applicable commit/environment evidence, reviewer disposition and explicit limitations.

| Date | Planning progress | Implementation progress / next action |
| --- | --- | --- |
| 2026-10-19 | Review findings resolved into proposed backlog; 145 task cards, task-level dependencies, contracts/gates, conditional daily schedule and milestone rollups prepared and checked. | All execution tasks Not started. Product owner reviews E0 approval scope and unresolved decisions. |
