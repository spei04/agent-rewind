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

| 2026-10-19 | B — platform/capacity | AR-003-B: capacity, ownership and funding record | work/capacity-decision | In review; [PR #20](https://github.com/spei04/agent-rewind/pull/20), 9ffa2fc. Nine arithmetic tests and lead review passed; CI pending. CAP-01 flags repeated object-write costs. |
| 2026-10-19 | C — quality/contracts | AR-012-A: proposed contract and fixture validation harness | work/contract-harness | Assigned after AR-002-A delivery; AR-004-A and AR-005-A prerequisites verified. |

| 2026-10-19 | A — research protocol | AR-002-B: natural failure and held-out split protocol | work/natural-failure-protocol | Assigned after AR-011-A delivery; corpus/metrics prerequisites verified. No paid experiment or real data ingestion. |

| 2026-10-19 | B — independent reviewer | RV-001: peer review of merged corpus validator | work/capacity-decision (read only) | Assigned while research protocol finishes; inspect 096b48f, no implementation or new dependencies. |

Each delivery records its commit, targeted checks, limitations and reviewer disposition here. A completed assignment frees its checkout for the next task after integration and consumer checks. Private evidence and credentials never belong in this log.

The managed checkout tool could not operate on the cloud repository from this local chat (reported “Not a git repository”). These independent contributors use ordinary cloud Git worktrees; no project copy was recreated on the Mac. Only the lead updates roadmap/backlog status and this assignment log, avoiding concurrent edits.

## Current management checkpoint

- **Goal:** durable failed-run capture, checkpoint restoration, useful intervention selection and honest matched-trial evidence; enterprise readiness still requires the later deployment/security/recovery gates.
- **Verified delta:** seven PRs (#13–19) merged: workflows, inventory, frozen legacy fixtures, measurement criteria, trust boundaries and offline corpus permissions, and safe error/readiness contracts. All passed core and gVisor CI. Integrated core at de05f0b passed 96 tests (one environment-dependent skip), lint and formatting. No migration or new real-agent experiment has shipped.
- **Active assignments:** A natural-failure research protocol, B independent corpus-validator review, C contract/fixture validation harness. Capacity estimates are in CI (PR #20); AR-004-B waits for both protocol and capacity evidence.
- **New capacity risk:** CAP-01 identifies repeated unchanged-file uploads; the same retained bytes can incur very different object-operation costs. AR-004-B must assign measurement/publication controls before accepting production sizing.
- **Next evidence-producing milestone:** reviewed contracts plus the AR-005-B/C vertical slice: explicit schema adoption/upgrade and runtime revision guard, proving original rows/artifact/event identities survive and incompatible schemas refuse admission. The following native-run replay must use production-shaped gVisor and preserve controls; a single passing branch is not a reliable improvement claim.
- **Blocker:** shared studio-agent root filesystem has about 100 MiB headroom and fluctuates with other active projects. Shared Physics Platform capacity work owns the cross-project storage recommendation. Our active paths are the primary agent-rewind checkout and three ordinary agent-rewind-worktrees/engineer-{a,b,c} checkouts; A and C own their pinned venvs, B has no installed environment. No new downloads/builds/venvs until safe capacity exists. Needed before broader runtime integration: at least 2 GiB sustained headroom for temporary DB/tests; use hosted CI for heavier checks meanwhile.
- **Budget:** existing validation authorization remains $200. Last recorded conservative reservations are $36.567974; invoice-level actual spend has not been reconciled, so $163.432026 is only provisional remaining authorization. This execution batch made zero provider calls and provisioned zero paid resources. Reconcile before any new live experiment; production/study funding remains separately gated.
