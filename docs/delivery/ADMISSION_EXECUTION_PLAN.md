# Admission execution plan

2026-10-21 · AR-008-A/P1, P2, P3 and aggregate A are Verified; see [accepted P3 delivery](#accepted-p3-delivery--2026-10-21). Issues #80/#81/#82/#83 are closed. AR-008-B remains Not started. These preparatory services supply no deployed registry, available new-work HTTP admission, customer-ready profile or spending authority.

## Entry and delivery boundaries

AR-008-A retains direct prerequisites AR-007-C and AR-009-B, both Verified for their preparatory scope. All three sequential packages and the full internal service matrix passed independent review, matching PR/main checks and candidate verification. Their accepted merge and review evidence are recorded in the ledger. Parent #8 stays open for AR-008-B, which retains AR-008-A and AR-011-B. No outer dependency is removed or added.

| Delivery | Scope | Base / planning range | Handoff |
| --- | --- | --- | --- |
| AR-008-A/P1 | Strict client intent/defaults, immutable configuration registry/interface and versioned envelope | 2 / 2–3 BE days | Accepted typed identities, canonical vectors and concrete registry/ref design |
| AR-008-A/P2 | Additive admission migration, constraints and bounded identity repositories | 2 / 2–3 BE days | Accepted literal profiles, preservation/restore and SQL identities |
| AR-008-A/P3 | Reusable admission/publication/recovery coordinator | 3 / 3–5 BE days | Accepted contention, crash, revocation and uncertain-commit behavior |
| AR-008-B/P1 | Bounded Operation reads and same-Connection cancellation | 2 / 2–3 BE days | Accepted A and reviewed producer/cancellation checkpoint |
| AR-008-B/P2 | Exactly submit, status and cancellation HTTP operations | 2 / 2–3 BE days | Accepted merged B/P1 and full three-route evidence |

A retains 7 [7–11] days. The separate [operation HTTP plan](OPERATION_HTTP_EXECUTION_PLAN.md) replaces B's provisional 3 [3–5] with two sequential 2 [2–3] BE packages, total 4 [4–6], medium-low confidence. B remains Not started; its accepted-A prerequisite, including P3 merge/main/candidate evidence, is now satisfied. This re-estimates approved status/cancellation and three-route work; it adds no feature, calendar, staffing, data or spending authority. Review the explicit stored-failure producer decision and same-Connection cancellation boundary before B runtime. The original historical schedules and immutable C21/owner decisions remain unchanged. Three contributor slots are not six human FTEs.

The admission-only checkpoint 1d284ba retained 151 aggregate tasks and 543 outer edges, with 154 planned PRs: 452 base days, 765.1 summed upper days, an alternative 565-day allowance at 25%, and a 166.5-day effort-only path. Those are historical checkpoint totals. The subsequent [observability reconciliation](OBSERVABILITY_EXECUTION_PLAN.md) changes the current portfolio totals recorded in the [roadmap](../PLAN.md) and [execution ledger](../../contracts/proposals/execution-backlog.json). External waits and role contention remain outside the effort path.

## Concrete P1 checkpoint

Before broad code or DDL, review the registry representation, mutation/rollout ownership, bounded immutable entries and exact typed resolver. There is no deployed native-v1 registry in the accepted runtime. The implementation must freeze image identity, provider endpoint/model revision, adapter/prompt/tool-policy/configuration digests, processor permission, token/reasoning/seed options, price version and integer rates as required by C04. Credentials remain server-side; a configuration cannot expand processor permission. No API-side Docker query/pull, provider discovery or fallback to today's Settings is permitted.

Review execution_config_ref versus execution_config_digest explicitly: opaque locator, content digest, object ID and scoped artifact reference are distinct identities. Define their validated association and required composite constraints/transaction checks before P2. Do not invent a foreign key equating a digest to an object ID, weaken historical catalog profiles, or add an unreviewed registry mutation endpoint.

Strict SubmitRun/TaskDefinition parsing materializes m1-review-2 defaults and preserves exact source text, Unicode and file modes. Reject duplicate JSON keys, unknown fields, nonfinite values, booleans in integer positions, ambiguous paths and over-limit canonical content. Integer microUSD remains authoritative; legacy TaskSpec conversion requires round-trip equality. The digest excludes transport credentials and mutable installation defaults. Configuration plaintext remains bounded to 64 KiB; task materialization retains the 8 MiB bound.

A trusted generated request correlation is an explicit service input, separate from canonical client intent. It originates in the server request boundary, never a client header/body, actor or configuration digest. The first persisted operation/failure origin is retained on retries; each poll's request/header ID stays distinct. P2/P3 own the agreed operation metadata and persistence; B wires the trusted input. Do not repurpose legacy jobs.error or fabricate historical origin IDs. Later worker failures remain their producer's integration obligation.

## Migration and preservation

P2 owns the next accepted linear additive revision for operations, operation_keys and common job payload/config metadata. It does not own AR-010-A's generation/ledger schema. Keep operation uniqueness by project/principal/kind/client ID, alias uniqueness by project/principal/kind/key hash, the composite alias-to-operation identity and actual job/project scope constraints. Bound selected metadata before returning it to Python.

Preserve all 14 original fixture rows, 18 encrypted objects, hash heads and 245000 historical reservation units, including legacy audit and original payload bodies. Prior literal profiles remain unchanged; independently review newly captured SQLite/PostgreSQL deltas. Historical version-1 jobs retain NULL config and remain non-dispatchable without an explicit compatible mapping. Never guess defaults or rewrite history to satisfy the new schema. Explicit operator migration, least privilege, rollback/restart and actual synthetic PostgreSQL restore are acceptance evidence; customer-serving rollback/activation is not claimed.

The common configuration invariant applies to every future new legacy run/branch/study/investigate job. Schema/config association belongs here; actual later legacy branch/study admission must prove source-policy/image compatibility and preserve version-1 bodies. Unsupported mapping remains unavailable. No study submission or provider retry policy is added to A.

## Publication and recovery

The planning-only [P3 entry checkpoint](ADMISSION_COORDINATOR_ENTRY.md) fixes same-submit restart routing, immutable linked attempts, phase-specific errors and the policy/lock interface. Its accepted-merged-P2 and explicit-assignment prerequisites are now satisfied; the document itself adds no runtime or authority. P3 implementation/source review and final hosted/main/candidate acceptance are complete for the internal service matrix.

1. Authenticate and resolve the trusted original project context; authorize the action and resolve **both** scoped client-operation and key-alias identities before readiness, mutable registry lookup or storage.
2. For a matching existing operation, reauthorize before disclosure and atomically bind any legitimate new alias. Return the original accepted IDs and stored configuration identity even if current defaults change or storage is unavailable. Changed canonical intent or an alias bound elsewhere conflicts; changing service-key principal is not recovery.
3. Only a genuinely new operation freezes approved configuration and uploads/verifies task, configuration and envelope outside any SQL transaction. Existing artifact receipts/metadata primitives are reusable; raw Database.enqueue and complete-run RunPublisher are not admission substitutes.
4. Under one owned transaction, follow the common project-before-grant/caller/job hierarchy, recheck current authority and both uniqueness constraints, and publish verified objects/refs, job, scope, operation, aliases, trusted origin and restricted audit atomically. A racing loser resolves the winner instead of creating a second identity.
5. A lost commit acknowledgment returns outcome_uncertain. Reconcile only the original canonical operation identity through authorized SQL; do not automatically upload again, create another job, reinterpret an upload journal as a commit receipt or change the operation/configuration identity.

Unreferenced uploads are acknowledged as orphans with actual confirmed/uncertain write evidence, not committed jobs or free work. No GC, deletion, cloud billing claim or new publication journal framework is included. No storage, network, provider or readiness probe runs while SQL locks are held.

## Required evidence and later consumers

The service matrix includes CT-M1-008/010/011/012: eight concurrent identical requests yielding one job/operation/creation audit; same client/body plus new key alias; conflicting key/client/canonical body; changed source whitespace versus equivalent defaults; revoked caller nondisclosure; configuration change plus storage-outage recovery; SQL rollback; and process death before/after commit with original-identity recovery. Prove current membership/token exclusion and final authorization, scoped constraint failures, fixed errors and no returned success after ambiguous commit. Local PostgreSQL skips never count as hosted execution.

AR-008-B first supplies the bounded operation read/cancel adapters, then wires exactly three of the five frozen M1 HTTP operations: submit, operation status and cancellation. Its [execution plan](OPERATION_HTTP_EXECUTION_PLAN.md) separates unsupported legacy error text from a validated stored failure envelope; no GET invents historical correlation or a producer. AR-006-B owns run list/detail/cursors. B adds strict transport limits and stable errors, passes trusted context/correlation, preserves terminal cancellation and verifies HTTP replay before readiness/config/storage. The unavailable WorkAdmission boundary remains in force until the required integration is accepted; no raw enqueue fallback is allowed.

AR-010-A/B still own budget/generation/permit and worker dispatch. Adding them as reverse prerequisites would cycle through AR-008-B; instead retain disabled preparatory interfaces and later integration acceptance. AR-012-B closes the full M1 behavior matrix. AR-008-A introduces no HTTP, worker, paid execution, customer-ready profile or activation. All production, spending and data gates remain unchanged.

The producer-boundary finding raised at the admission-only checkpoint is resolved by the separately reviewed [observability execution plan](OBSERVABILITY_EXECUTION_PLAN.md). Both AR-011-C packages wait for Verified AR-010-B; there is no early foundation start. That plan owns the revised telemetry estimate and dependency, while admission retains correlation persistence. The frozen metric vocabulary and external gates remain unchanged.

2026-10-21 implementation assignment: C implements AR-008-A/P1 in its retained checkout from f08b1ca; B reconciles acceptance in primary then independently reviews contracts/security; A completed the read-only AR-006-B cursor audit and will author a separate planning amendment after reviewing this delta, with no 006-B runtime assigned. Lead owns integration/delivery. A reviews admission boundary tests after its planning handoff. The reviewed P1 design uses explicit bounded immutable optional native-v1 entries and separate client/config identities; 9 MiB raw JSON is bounded before parse, the fully materialized TaskSpec is at most 8 MiB, and canonical configuration plaintext at most 64 KiB. No SQL/route/P2 work, deployed registry or admission availability is claimed. The accepted planning review does not count as runtime verification; full package checks/accepted merges remain required.

2026-10-21 source handoff: AR-008-A/P1 is Implemented; verification pending. C authored parser 4c6a558, configuration 0e6cb05, envelope 1dde230 and packaging/guide e699394; lead integrated unchanged file contents as 7ea387f/3f74d69/d0448d4/02424e0 onto reviewed c390726. B independently accepted each runtime component for source and test design. Author validation passed 230 focused admission/package-helper/workflow/contract/model/legacy/artifact-metadata tests in 10.37 seconds, strict types, lint/security lint, formatting and whitespace. Final independent composed execution, actual installed wheel/sdist smoke, hosted checks, accepted merge and protected-main candidate remain required. No SQL/HTTP/storage/worker activation or provider call occurred; P2/P3 remain Not started.

## Accepted P1 delivery — 2026-10-21

[PR #85](https://github.com/spei04/agent-rewind/pull/85) reviewed source
bc2a784cd40ded5c18ee5b67c2d3d7f5ec1c948e merged as
81905a5ace65823c91196771f7cd2474a9117306. A independently passed 228 tests,
128 boundary probes and three validators; B accepted component, package and
composition source. [PR checks](https://github.com/spei04/agent-rewind/actions/runs/39539994853)
and [protected-main checks](https://github.com/spei04/agent-rewind/actions/runs/39541051449)
passed 2170/2176 core tests on Python 3.11/3.12 with 9/3 expected skips and one
existing warning per job, actual PostgreSQL, three gVisor cases, installed
package smoke, security, gate and main delivery. Lead verified candidate
12320076132 (483833 bytes), its exact four files, source/manifests and hashes;
the private indexed release record remains outside checkouts, review 2026-11-20.
P1 is Verified; lead closes #81 only. Aggregate #80 and parent #8 remain open.

C starts P2 #82 in the reused matching-lock checkout; B reviews schema/contracts
and A preservation/boundaries as available. P3 #83 remains Not started until
accepted merged P2. No estimates, dependencies or frozen contract bytes change.
A independently owns AR-006-B/P1 in PR #89; its unmerged package/estimate changes
are not imported into this admission branch. C's separate listing-session
PostgreSQL test handoff d9fa9a8 (17 opt-in cases) received A's source/test-design
acceptance; 14 local session tests passed and all 17 PostgreSQL cases explicitly
skipped. The close-failure case depends on A's e85ccd80 correction. This is no
local PostgreSQL execution or listing acceptance claim; all C test consumers
were released before checkout reuse. Admission P2 adds no coordinator,
HTTP/worker/ledger/generation, provider access or customer activation.

## P2 implementation checkpoint — 2026-10-21

P2 #82 is **Implemented; verification pending** in [PR #90](https://github.com/spei04/agent-rewind/pull/90). C completed the additive ar6 schema, connection-bound identity repositories, exact reviewed SQLite/PostgreSQL profiles, installed-package wiring and migration/restore/process-death tests. A/B independently accepted source and test design; B verified the actual captured PostgreSQL literal before its exact freeze. The failed capture run remains historical evidence, not release acceptance.

A independently checked composed source `01b3b65`: 461 tests passed, 78 actual-PostgreSQL cases skipped explicitly and one existing warning. Lead's full Ruff/security checks, formatting (202 files), strict typing (86 source files), frozen lock and all three validators passed. Matching hosted P2 migration, repository/contention, restore, SIGKILL and installed-package checks, accepted merge and protected-main candidate verification remain required. [Storage evidence and limits](ADMISSION_STORAGE.md) retain exact source/literal identities.

Lead owns admission delivery, B reviews independently and C releases the reused checkout after progress validation. Aggregate #80/parent #8 remain open; P3 #83 is Not started. Listing P1 #87 is now Verified after accepted merge `ed0d6c48b8db3533c1bb20a75df93d7efc89fc7c`, successful PR/main runs 39547572853/39548734170 (2419/2427 core tests and three gVisor cases) and verified candidate 12323231309. A is assigned listing P2 #88 in reused primary work/scoped-run-routes; aggregate #86 remains open. No runtime, historical contract/profile, dependency, estimate, paid execution or activation change is made by this checkpoint.

## P2 merged; verification pending — 2026-10-21

[PR #90](https://github.com/spei04/agent-rewind/pull/90) merged reviewed source
`4135c6fd1376cb630bf9b94e7c958c70e996a023` as `41759bb`.
[PR run 39550589433](https://github.com/spei04/agent-rewind/actions/runs/39550589433)
passed 2571/2579 core tests on Python 3.11/3.12 with 11/3 expected skips, actual
PostgreSQL migration/repository/restore/process-death coverage, three gVisor tests,
installed-package checks, security and gate.
[Protected-main run 39552010828](https://github.com/spei04/agent-rewind/actions/runs/39552010828)
and candidate verification remain pending. P2 stays **Implemented; verification pending**,
with ledger accepted-merge/review-evidence fields null until final acceptance.
P3 #83 remains **Not started**; aggregate #80 and parent #8 stay open.

Lead composed reviewed listing route source `1954f3e` with admission main
`41759bb` as `47abde4164fbf136b16ca6b4e9b170923d4ea844`. B accepted the exact
source union; A independently passed 217 tests with no skips and one existing
warning in 71.51 seconds, plus the combined source smoke sequence through
ar6/migration-only/readiness refusal. These composition checks are source-level
evidence, not installed-wheel or PostgreSQL execution. Lead full lint/security,
formatting (203 files), strict typing (86 files), frozen lock and all three
validators passed. Listing P2 #88 remains Implemented; verification pending in
draft PR #91. Lead owns delivery; A/B reviews are available and C releases primary
after this docs-only reconciliation. No runtime, estimates, dependencies, frozen
history or activation changes.

## Accepted P2 delivery — 2026-10-21

[PR #90](https://github.com/spei04/agent-rewind/pull/90) reviewed source
`4135c6fd1376cb630bf9b94e7c958c70e996a023` merged as
`41759bb240d7aac0f17bd1c113e6b66d11e06b8b` with the same tree.
[PR checks](https://github.com/spei04/agent-rewind/actions/runs/39550589433) and
[protected-main checks](https://github.com/spei04/agent-rewind/actions/runs/39552010828)
passed 2571/2579 core tests on Python 3.11/3.12 with 11/3 expected skips and one
existing warning per job. A independently audited both completed runs: the
quiet-PostgreSQL setup marker was present, all 36 new admission PostgreSQL cases
ran (two schema, 20 repository, 14 migration/recovery including three SIGKILL
cases), and there were no new PostgreSQL skips or catalog-capture markers.
Three gVisor cases, installed-package smoke, security, gate and main delivery passed.
A/B source, preservation, catalog and test-design reviews remain scoped evidence.

Lead verified candidate **12324805344** (**544761 bytes**), its exact four files
and all source, manifest, package and archive hashes. The indexed private record
`release-records/reviewed-delivery-20261021-pr90-41759bb.json` remains outside
checkouts. P2 is **Verified**, issue #82 is closed, and aggregate #80/parent #8
remain open. This accepts the additive schema/repository delivery, not a
coordinator, HTTP admission, worker dispatch or customer activation.

P3 #83 is **In progress** in C's retained checkout from accepted `41759bb`.
C authors runtime/unit/fault tests; B independently reviews security/source;
A independently authors the separate PostgreSQL suite after an immutable stable
interface handoff; lead integrates. The first checkpoint covers frozen-envelope
restoration, SQL-only creator recovery/alias and fresh disclosure. Required
new-work adapters remain unavailable. The complete contention, rollback,
process-death, lost-acknowledgment, journal, policy/revocation and zero-I/O-under-locks
matrix remains required before P3 or aggregate acceptance.

Listing P2 #88 remains **Implemented; verification pending** in PR #91.
At this checkpoint, run 39552811585 at `9b1473f` has package/security/isolation
success with core jobs pending; no listing accepted merge or candidate is claimed.
The admission release proof does not satisfy listing's separate delivery gates.

## P3 implemented; verification pending — 2026-10-21

P3 [#83](https://github.com/spei04/agent-rewind/issues/83) is **Implemented;
verification pending** in [draft PR #92](https://github.com/spei04/agent-rewind/pull/92).
B accepted runtime `302571f` plus uncertainty correction `4440ee3`, the ten
residual coordinator cases in `e5a75ec`, and A's corrected 32-case PostgreSQL
publication suite `458c1114`. A independently executed the original runtime
selection: **157 passed, zero skips, 52.93 seconds**. The internal new-work path
retains unavailable defaults and the real migration-only guard.

Lead validated composed source `edf85ae42ee8f3e78ecc8021e2df18b52f09c908`:
**530 passed, 94 explicit PostgreSQL skips, no warnings, 117.85 seconds**.
The selection covered every admission test module plus artifact metadata/storage,
publication journal and execution backlog. The skips are 26 coordinator,
32 publication, 20 repository, 14 migration and two schema cases; this is no
local PostgreSQL execution claim. Full Ruff/security, formatting (217 files),
strict mypy (93 files), pinned-lock and all three validators passed. Owned
Python 3.12.3/imports/manifests and clean source were verified before and after.

The earlier published `1878cfb` checkpoint's
[run 39558425762](https://github.com/spei04/agent-rewind/actions/runs/39558425762)
passed **2748/2758** core tests on Python 3.11/3.12 with **13/3 expected skips**,
all **26 PostgreSQL recovery cases**, installed-package/security checks,
three gVisor cases and the gate. This is **early recovery evidence only**;
it does not validate the later new-work publication composition.

All **32 new PostgreSQL publication/crash cases** remain locally skipped and
require matching hosted execution. Final-source installed-package/CI proof,
accepted merge and protected-main/candidate verification remain pending.
P3's `accepted_merge_commit` and `review_evidence` stay null; aggregate #80
and parent #8 stay **In progress/open**. AR-008-B stays **Not started**.
Lead owns delivery, with A/B reviewers available and C releasing the reused
checkout after this progress handoff. Accepted listing records remain unchanged.
No HTTP/worker/ledger/generation wiring, customer-ready profile, provider call,
paid resource or activation follows.

## Accepted P3 delivery — 2026-10-21

P3 #83 and aggregate #80 are **Verified/closed**. Reviewed source
`a09e26d422b9aa379c2bd27f188c8a468122517d` merged through the strict gate in
[PR #92](https://github.com/spei04/agent-rewind/pull/92) as
`4c86c52a14e45fee6a27f8b4410310ced064cf31`. Their identical source tree is
`8486a757d18b3a70020912113aedb4252e074e26`.

[PR run 39574109747](https://github.com/spei04/agent-rewind/actions/runs/39574109747)
and [protected-main run 39576754575](https://github.com/spei04/agent-rewind/actions/runs/39576754575)
both passed. Python 3.11 ran 2860 passes/13 skips and Python 3.12 ran
2870 passes/3 skips, each with one warning. All 33 publication and 26 recovery
PostgreSQL cases executed on both versions. Ten skips are Python-3.12-only
SQLite transaction cases; three Docker cases are covered separately by three
passing gVisor cases in each run (3.37s PR, 3.08s main). Security, installed
wheel/sdist smoke, the strict CI gate and main candidate delivery passed.
B independently audited exact source identity, PostgreSQL opt-ins and expected
skip accounting.

Lead verified candidate `12335133060` (585266 bytes) in memory: exactly the
wheel, source archive, candidate manifest and SHA256SUMS; source/parent/tree,
pinned manifests and package hashes match. Archive SHA-256:
`16bf27c304e967324d5baf6660092a25ad8949ca126b422b772b4e066d836ad8`.
Private owner-readable evidence is indexed outside checkouts as
`release-records/reviewed-delivery-20261021-pr92-4c86c52.json`.

A reproduced the old migration-guard fixture failure on actual PostgreSQL
16.15, split clean original-adoption and restricted-policy cases in `350a702`,
and passed all 59 publication/recovery cases with zero skips in 184.69s.
A/C independently checked the correction; runtime guards, grants, profiles and
historical fixtures were not weakened. The instance is stopped and has no
remaining disposable databases or roles.

Earlier runs `39569954081` and `39562014839` remain failed evidence: respectively
2858/2868 passes with one failure per version, and 2828/2838 passes with 19 shared
failures. Indexed diagnostics retain those failures and their corrections.
Earlier pending sections above are dated history, superseded by this acceptance.

The internal CT-M1-008/010/011/012 admission/recovery service matrix is accepted.
AR-008-B #93/#94/#95 and worker #96/#97/#98 remain Not started; parent #8 stays
open. HTTP integration, worker/ledger/generation, full M1 integration, G1,
customer data, provider execution and production activation retain their
separate gates. No effort, dependency, historical contract or spending change
is made by this acceptance.
