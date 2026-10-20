# Engineering assignment log

Execution backlog approved on 2026-10-19. The project lead coordinates three independent contributor slots, reviews each delivery, integrates tested changes, then assigns dependency-ready work to the free slot. These are logical contributor roles, not six confirmed full-time hires; the prior staffing/calendar scenario remains unconfirmed. Task-specific external funding, data, customer and release gates still apply.

| Date | Engineer | Task | Branch | Status / next action |
| --- | --- | --- | --- | --- |
| 2026-10-19 | A — workflow/contracts | AR-001-A: supported workloads and buyer workflows | work/workflow-contracts | Verified; [PR #13](https://github.com/spei04/agent-rewind/pull/13) merged at 074a49f. Six targeted tests, core and gVisor CI passed; lead review accepted internal scope. |
| 2026-10-19 | B — backend/interfaces | AR-004-A: baseline interface and compatibility inventory | work/interface-inventory | Verified; [PR #14](https://github.com/spei04/agent-rewind/pull/14) merged at 8c20226. Pytest collection fix reviewed; nine scoped tests, core and gVisor CI passed. |
| 2026-10-19 | C — quality/migrations | AR-005-A: historical migration fixtures | work/migration-fixtures | Verified; [PR #15](https://github.com/spei04/agent-rewind/pull/15) merged at 0ef6ad2. 35 scoped tests, lint/type checks, core and gVisor CI passed; frozen identities reviewed. |
| 2026-10-19 | A — workflow/contracts | AR-001-B: usefulness metrics and interaction acceptance | work/workflow-contracts | Verified; [PR #16](https://github.com/spei04/agent-rewind/pull/16), merge de05f0b. 25 scoped tests, core and gVisor CI passed; internal metrics accepted. |
| 2026-10-19 | B — platform/trust boundaries | AR-003-A: trust boundary and deployment threat review | work/trust-boundaries | Verified; [PR #17](https://github.com/spei04/agent-rewind/pull/17) merged. Nine static checks, core and gVisor CI passed; lead accepted trust model, live topology remains unverified. |
| 2026-10-19 | C — corpus/quality | AR-002-A: corpus permission and provenance manifest | work/corpus-permissions | Verified; [PR #18](https://github.com/spei04/agent-rewind/pull/18), merge 096b48f. 46 scoped tests, lint/type checks and CI passed; offline validator only, no real ingestion. |

| 2026-10-19 | A — platform/contracts | AR-011-A: error, readiness and telemetry contract | work/error-contracts | Verified; [PR #19](https://github.com/spei04/agent-rewind/pull/19), merge ea85d2c. 53 scoped tests, core and gVisor CI passed; design only. |

| 2026-10-19 | B — platform/capacity | AR-003-B: capacity, ownership and funding record | work/capacity-decision | Verified; [PR #20](https://github.com/spei04/agent-rewind/pull/20), merge be2ce1f. Nine arithmetic tests, core/gVisor CI and lead review passed; CAP-01 retained. |
| 2026-10-19 | C — quality/contracts | AR-012-A: proposed contract and fixture validation harness | work/contract-harness | Verified; [PR #22](https://github.com/spei04/agent-rewind/pull/22), merge 8c3a7b9. 70 scoped tests, independent correction recheck and core/gVisor CI passed. |

| 2026-10-19 | A — research protocol | AR-002-B: natural failure and held-out split protocol | work/natural-failure-protocol | Verified; [PR #21](https://github.com/spei04/agent-rewind/pull/21), merge d90a1b9. 166 scoped tests, independent correction review and core/gVisor CI passed. |

| 2026-10-19 | B — independent reviewer | RV-001: peer review of merged corpus validator | work/capacity-decision (read only) | Completed: epoch timestamp strings bypass published date-time syntax; B assigned bounded correction. |

| 2026-10-19 | B — backend correction | AR-002-A / RV-001: strict timestamp syntax | fix/corpus-timestamp-syntax | Verified; [PR #23](https://github.com/spei04/agent-rewind/pull/23) merged. 91 corpus tests independently rerun by lead; core/gVisor CI passed, fixture bytes unchanged. |
| 2026-10-19 | C — independent reviewer | RV-002: natural-failure protocol review | work/contract-harness (read only) | Completed; two findings fixed by A; B independently rechecked corrected 820c0a9 and accepted. |
| 2026-10-19 | A — independent reviewer | RV-003: contract harness review | work/natural-failure-protocol (read only) | Completed; TEMP SQL and scalar-reference findings fixed by C; A rechecked corrected a5dcdcb and accepted. |

| 2026-10-19 | B — backend/platform | AR-004-B: reconcile and propose M1 contract freeze | work/m1-contract-freeze | Verified: PR #24 merged at 4a1a5ae; 147 targeted tests independently rerun, A/C reviews accepted, core/PostgreSQL and gVisor CI passed. |

| 2026-10-19 | A — consumer review | AR-004-B: workflow/client and research contract review | work/natural-failure-protocol (read only) | Accepted exact 22c4376 for FE/RS; 77 scoped tests plus full checker passed, legacy-config/recovery/correlation semantics verified. |
| 2026-10-19 | C — quality/security review | AR-004-B: preservation, authority and migration review | work/contract-harness (read only) | Accepted exact 22c4376 for PL/QE/SEC after nullability/fresh-state corrections; structural/negative checks passed. Runtime migration/security evidence remains required. |

Each delivery records its commit, targeted checks, limitations and reviewer disposition here. A completed assignment frees its checkout for the next task after integration and consumer checks. Private evidence and credentials never belong in this log.

The managed checkout tool could not operate on the cloud repository from this local chat (reported “Not a git repository”). These independent contributors use ordinary cloud Git worktrees; no project copy was recreated on the Mac. Only the lead updates roadmap/backlog status and this assignment log, avoiding concurrent edits.

## Current management checkpoint

- **Goal:** durable failed-run capture, checkpoint restoration, useful intervention selection and honest matched-trial evidence; enterprise readiness still requires the later deployment/security/recovery gates.
- **Verified delta:** eighteen delivery/security/management PRs (#13–25, #27, #29, #34, #35 and #36) merged. The accepted CI delivery baseline, 13465c1, passed 495 tests on each supported Python version and three real gVisor tests, security/package checks and protected-main candidate delivery. PR #34 merged at b497dfc and records the current roadmap/evidence update. Explicit installation/adoption is merged at 385e5ecf with 656 hosted tests per Python version. Runtime guards and new real-agent experiments remain outstanding.
- **Active assignments:** M1 contracts and G0 development record are verified. Current assignments under issue #37: A independent synthetic PostgreSQL recovery work; B integration review; C runtime revision guard. Explicit migration (issue #28) and reference configuration (issue #30) are verified. Secure CI/candidates are verified. Versioned metadata is prepared-only; customer admission is not accepted.
- **Capacity risk:** CAP-01 identifies repeated unchanged-file uploads; retained bytes alone do not predict object-operation cost. Reviewed C04 assigns the publication/read controls; measured throughput and cost evidence are still required before production sizing.
- **Next evidence-producing milestone:** reviewed contracts plus the AR-005-B/C vertical slice: explicit schema adoption/upgrade and runtime revision guard, proving original rows/artifact/event identities survive and incompatible schemas refuse admission. The following native-run replay must use production-shaped gVisor and preserve controls; a single passing branch is not a reliable improvement claim.
- **Blocker:** shared studio-agent root filesystem has about 140–150 MiB headroom and fluctuates with other active projects. Shared Physics Platform capacity work owns the cross-project storage recommendation. Our active paths are the primary agent-rewind checkout and three ordinary agent-rewind-worktrees/engineer-{a,b,c} checkouts; A and C own their pinned venvs, B has no installed environment. No new heavy downloads/builds/venvs until safe capacity exists. C refreshed only its existing owned runtime/dev environment after measuring a bounded dependency delta; final locked checks run on hosted CI. Removed only the primary repository’s unused reproducible type-check cache after confirming no type-checker process; observed free space rose by 74,346,496 bytes (70.9 MiB). Active environments, private evidence and other projects were preserved. Needed before broader runtime integration: at least 2 GiB sustained headroom for temporary DB/tests; use hosted CI for heavier checks meanwhile.
- **Budget:** existing validation authorization remains $200. Last recorded conservative reservations are $36.567974; invoice-level actual spend has not been reconciled, so $163.432026 is only provisional remaining authorization. This execution batch made zero provider calls and provisioned zero paid resources. Reconcile before any new live experiment; production/study funding remains separately gated.

- 2026-10-19 lead dependency review: 514 edges pass acyclic/producer/schedule checks after three missing prerequisite links. Conditional first-fortnight work now finishes freeze; readiness follows revision guards. Total effort remains 427 days; longest effort path is 146 days. Current capacity remains three contributor slots.

- 2026-10-19 C independently rechecked the lead dependency/status update: numerical checks passed; four stale timing/dependency references were corrected. GitHub parent issues #1–3 are closed only for verified internal specification scope; #4–12 remain open.

- 2026-10-19 lead reconciled final C04 consumer dependency (AR-011-B before AR-009-A): 515-edge DAG and conditional schedule pass, 146.5-day effort path. No runtime work starts before the reviewed development-scope G0 record.

- 2026-10-19 lead prepares AR-004-C development decision from existing authorization; A reviews the record transition. Runtime assignments start after that check. Next: C migration, B independent migration tests/review, A reference configuration.

- 2026-10-19 AR-004-C verified: A accepted the lead decision record and transition checks; 435 core tests (one environment skip), checker, lint/format passed. ARCH0/G0 satisfied only for development/testing. External production/data/funding/operator gates remain open.

| Date | Engineer | Task | Branch | Status / next action |
| --- | --- | --- | --- | --- |
| 2026-10-19 | B — delivery/platform | AR-051-A: secure CI and installable candidate delivery | work/secure-delivery | In progress; preserve current checks, add pinned inputs/security scans/CI gate and main-only verified artifacts. Repository settings owned by separate coordination. |
| 2026-10-19 | A — independent reviewer | AR-051-A: CI/delivery boundary review | existing checkout, read only | In progress; verify PR isolation, required-check semantics, artifact allowlist and runtime-only smoke. |
| 2026-10-19 | C — migrations | AR-005-B: versioned installation/adoption | work/schema-adoption | In progress after PR #25; issue #28. Explicit install/adopt/upgrade/status with preservation and fail-closed tests; PostgreSQL evidence on hosted CI. |

Owner explicitly confirmed build/test scope with production spending and partner data gated. The CI/CD priority adds no deployment or publication authorization.

2026-10-20 handoffs: A independently accepted cryptography security PR #27 at 2f182d6 after exact scope, upstream advisory/API compatibility and green core/gVisor checks; lead merged at 7058286. B owns subsequent locked tooling/security patch changes and coordinates the Alembic dependency with C. Seven immediate post-merge alerts require rescan read-back; no advisory is suppressed. Existing local environments do not prove the new frozen dependency set.

Current dependency audit: AR-051-A is now an explicit 2-day M1 task with verified E0/AR-004-A/AR-003-A prerequisites and G1 integration exit. Ledger has 146 tasks, 51 parents, 519 edges, 429 base days and unchanged 146.5-day effort path. Conditional first-ten-day schedule remains valid; three current contributors are not six confirmed human hires.

2026-10-20 review: A independently rechecked the 146-task dependency/status extension and identified stale live summary numbers; lead synchronized those figures and retained dated history. GitHub advisory read-back after PR #27 reports zero open alerts; main runs [39345612303](https://github.com/spei04/agent-rewind/actions/runs/39345612303) and [39345583552](https://github.com/spei04/agent-rewind/actions/runs/39345583552) passed. CI implementation is under independent review in [PR #29](https://github.com/spei04/agent-rewind/pull/29), initial head 7c31b14. Hosted checks and protected-main delivery evidence remain pending.

| Date | Engineer | Task | Branch | Status / next action |
| --- | --- | --- | --- | --- |
| 2026-10-20 | B — delivery/platform | AR-051-A | work/secure-delivery | Verified; PR #29, exact review 7c31b14, main 13465c1, protected-main run 39346262029 and artifact 12230273836 passed. |
| 2026-10-20 | A — independent review | AR-051-A | read only | Accepted exact source; lead and repository coordinator verified actual main candidate independently. |
| 2026-10-20 | A — platform/configuration | AR-033-A | work/reference-config | Assigned/in progress; issue #30, existing free checkout reused; offline C14 inputs/topology, no provisioning. |
| 2026-10-20 | B — independent migration review | AR-005-B | read only | Three draft findings sent to C: public routine writer paths, source fingerprint corruption, and legacy superuser writer exemption. Await corrected exact commit and PostgreSQL tests. |
| 2026-10-20 | C — migrations | AR-005-B | work/schema-adoption | In progress; 55 focused local tests reported. Adds bounded explicit retired-role input and catalog/provenance corrections before hosted PostgreSQL acceptance. |

[CI evidence](delivery/CI_EVIDENCE_2026-10-20.md) records the successful protected-main run, checksum verification, seven rounded job-minutes, short retention and single-owner review limitation. Production/data/spending gates remain unchanged. The three existing cloud worktrees remain active and are being reused; no redundant checkout was created.

| Date | Engineer | Task | Branch | Status / next action |
| --- | --- | --- | --- | --- |
| 2026-10-20 | A — configuration | AR-033-A | work/reference-config | Delivered 83aabb8 in [PR #36](https://github.com/spei04/agent-rewind/pull/36); lead requested peak pool-overflow/process accounting and nonblocking regular-file loading, both fixed. B accepted exact source and independently reran 70 scoped tests; hosted locked CI pending. |
| 2026-10-20 | B — independent review | AR-033-A, then AR-005-B | read only | Reference configuration accepted; returned to migration catalog/transaction/retired-role review at ea34f3b. |
| 2026-10-20 | C — migrations | AR-005-B | work/schema-adoption | [PR #35](https://github.com/spei04/agent-rewind/pull/35), head ea34f3b. Initial PostgreSQL run exposed fixture-comment parsing and missing frozen catalog; corrected without changing fixture bytes. Dedicated DB-only CLI, namespace protection, strict raw JSON validation and reviewed PG16 profile now await hosted rerun. |
| 2026-10-20 | A — independent review | AR-005-B complementary review | read only, exact ea34f3b | Reassigned after configuration delivery to migration CLI least privilege, bounded inputs/redaction and installed resource packaging. B retains overall migration acceptance. |

The next runtime task AR-005-C remains unscheduled until AR-005-B is accepted and integrated. AR-033-B remains blocked on actual ENV0 approval; a validated synthetic configuration does not authorize infrastructure. No paid resources, model calls or partner-data access in this batch. The existing three cloud worktrees are reused; approximately 139 MiB shared free space keeps heavy testing on hosted CI.

2026-10-20 integration: PR #36 merged at 4abc352 after independent B review of 83aabb8 and all required hosted checks in run 39347427475. Issue #30 closed for offline configuration only. C14 is available; ENV0 stays open. All three existing checkouts remain assigned; no checkout or environment was created.

2026-10-20 queue: [issue #37](https://github.com/spei04/agent-rewind/issues/37) records AR-005-C runtime guards and recovery. It is not started and waits for accepted AR-005-B. The recovery evidence must distinguish PostgreSQL transaction rollback from an actual backup/restore rehearsal.

2026-10-20 lead tracker review: A independently accepted afbbc361 after one historical-source wording correction. The 146-task/519-edge graph, 429-day estimate, task-card parity and prerequisite/gate ordering remain valid; AR-005-C remains unstarted.

| Date | Engineer | Task | Branch | Status / next action |
| --- | --- | --- | --- | --- |
| 2026-10-20 | C — migrations | AR-005-B | work/schema-adoption | Verified; PR #35 merged at 385e5ecf after exact 6cf49a8 source review and run 39348158044: 656 core tests per Python version, 42 PostgreSQL cases, three gVisor tests, security/package/CI gate pass. |
| 2026-10-20 | A/B — independent reviewers | AR-005-B | read only | Accepted complementary CLI/input/package and catalog/transaction/role scopes; preserved fixture/profile identities. Actual PostgreSQL backup/restore remains next-slice work. |
| 2026-10-20 | C — backend | AR-005-C runtime guard | reused engineer-c checkout, new branch from 385e5ecf | Assigned after prerequisite merge; versioned compatibility manifest, read-only API/worker refusal, no customer activation or DDL. |
| 2026-10-20 | A — recovery | AR-005-C PostgreSQL recovery work | reused engineer-a checkout, new branch from 385e5ecf | Assigned after prerequisite merge; synthetic backup/restore tests and recovery guide, using existing pinned hosted service. Owns disjoint files; no new infrastructure. |
| 2026-10-20 | B — independent reviewer | AR-005-C integration | reused engineer-b checkout, read only | Review initial interface and exact guard/recovery deliveries before a coherent PR is accepted. |

All three checkouts remain active and are reused. Shared filesystem headroom is approximately 131 MiB; heavier validation stays on hosted CI. A retains its existing old-lock environment without claiming frozen dependency validation; C owns its refreshed locked environment. No new model calls, infrastructure or partner-data access. No task was started before its prerequisites were integrated.

2026-10-20 review clarification: B confirmed that AR-005-C has no approved customer-serving rollback target. The card now distinguishes inspection-reader compatibility, actual PostgreSQL restoration and refusal of runtime rollback without an active release profile; C04 scope and production gates are unchanged.
