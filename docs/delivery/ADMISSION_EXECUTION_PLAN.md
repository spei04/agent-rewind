# Admission execution plan

2026-10-21 · Planning reconciliation of existing AR-008-A/B and reviewed C04 obligations. Runtime remains Not started. This document does not supply an implemented registry, admission service, accepted migration, customer-ready profile or spending authority.

## Entry and delivery boundaries

AR-008-A retains direct prerequisites AR-007-C and AR-009-B. AR-009-B's preparatory artifact metadata/storage/publication contracts are Verified; aggregate AR-007-C remains unverified while P2 awaits its final hosted/merge/candidate gates. No admission implementation starts before accepted aggregate AR-007-C. P1 inherits both prerequisites and C04; P2 requires accepted merged P1 and P3 requires accepted merged P2. The aggregate cannot be Verified until all three and the full service matrix pass. AR-008-B retains AR-008-A and AR-011-B. No outer dependency is removed or added.

| Delivery | Scope | Base / planning range | Handoff |
| --- | --- | --- | --- |
| AR-008-A/P1 | Strict client intent/defaults, immutable configuration registry/interface and versioned envelope | 2 / 2–3 BE days | Accepted typed identities, canonical vectors and concrete registry/ref design |
| AR-008-A/P2 | Additive admission migration, constraints and bounded identity repositories | 2 / 2–3 BE days | Accepted literal profiles, preservation/restore and SQL identities |
| AR-008-A/P3 | Reusable admission/publication/recovery coordinator | 3 / 3–5 BE days | Accepted contention, crash, revocation and uncertain-commit behavior |
| AR-008-B | Three HTTP operations: submit, status and cancellation | 3 / 3–5 BE days, provisional | Route integration after accepted A; reforecast from its actual interface |

A replaces 2 [2–3] with 7 [7–11] days; B provisionally replaces 2 [2–3] with 3 [3–5]. Both estimates have medium-low confidence. This is re-estimation of already approved work, not additional feature, calendar, staffing, data or paid-execution approval. Reforecast at the first concrete P1 interface and before B assignment. The original historical schedules and immutable C21/owner decisions remain unchanged. Three contributor slots are not six human FTEs.

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

1. Authenticate and resolve the trusted original project context; authorize the action and resolve **both** scoped client-operation and key-alias identities before readiness, mutable registry lookup or storage.
2. For a matching existing operation, reauthorize before disclosure and atomically bind any legitimate new alias. Return the original accepted IDs and stored configuration identity even if current defaults change or storage is unavailable. Changed canonical intent or an alias bound elsewhere conflicts; changing service-key principal is not recovery.
3. Only a genuinely new operation freezes approved configuration and uploads/verifies task, configuration and envelope outside any SQL transaction. Existing artifact receipts/metadata primitives are reusable; raw Database.enqueue and complete-run RunPublisher are not admission substitutes.
4. Under one owned transaction, follow the common project-before-grant/caller/job hierarchy, recheck current authority and both uniqueness constraints, and publish verified objects/refs, job, scope, operation, aliases, trusted origin and restricted audit atomically. A racing loser resolves the winner instead of creating a second identity.
5. A lost commit acknowledgment returns outcome_uncertain. Reconcile only the original canonical operation identity through authorized SQL; do not automatically upload again, create another job, reinterpret an upload journal as a commit receipt or change the operation/configuration identity.

Unreferenced uploads are acknowledged as orphans with actual confirmed/uncertain write evidence, not committed jobs or free work. No GC, deletion, cloud billing claim or new publication journal framework is included. No storage, network, provider or readiness probe runs while SQL locks are held.

## Required evidence and later consumers

The service matrix includes CT-M1-008/010/011/012: eight concurrent identical requests yielding one job/operation/creation audit; same client/body plus new key alias; conflicting key/client/canonical body; changed source whitespace versus equivalent defaults; revoked caller nondisclosure; configuration change plus storage-outage recovery; SQL rollback; and process death before/after commit with original-identity recovery. Prove current membership/token exclusion and final authorization, scoped constraint failures, fixed errors and no returned success after ambiguous commit. Local PostgreSQL skips never count as hosted execution.

AR-008-B wires exactly three of the five frozen M1 HTTP operations: submit, operation status and cancellation. AR-006-B owns run list/detail/cursors. B adds strict transport limits and stable errors, passes trusted context/correlation, preserves terminal cancellation and verifies HTTP replay before readiness/config/storage. The unavailable WorkAdmission boundary remains in force until the required integration is accepted; no raw enqueue fallback is allowed.

AR-010-A/B still own budget/generation/permit and worker dispatch. Adding them as reverse prerequisites would cycle through AR-008-B; instead retain disabled preparatory interfaces and later integration acceptance. AR-012-B closes the full M1 behavior matrix. AR-008-A introduces no HTTP, worker, paid execution, customer-ready profile or activation. All production, spending and data gates remain unchanged.

The producer-boundary finding raised at the admission-only checkpoint is resolved by the separately reviewed [observability execution plan](OBSERVABILITY_EXECUTION_PLAN.md). Both AR-011-C packages wait for Verified AR-010-B; there is no early foundation start. That plan owns the revised telemetry estimate and dependency, while admission retains correlation persistence. The frozen metric vocabulary and external gates remain unchanged.
