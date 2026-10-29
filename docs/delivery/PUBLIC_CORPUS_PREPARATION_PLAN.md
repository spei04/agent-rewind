# Public-corpus preparation plan

## Current status

- **Local source:** PCA1 [#120](https://github.com/spei04/agent-rewind/issues/120) remains In progress. Corrected candidate-only v2 is independently reviewed, committed `bb5cfc0d` and composed `47b5b324`; corpus v1 is unchanged. No delivery or merge acceptance.
- **Next owners:** Reviewed collection preparation remains stopped while Backend diagnoses P2's CI GET 503; Review evaluates diagnostics, Quality refreshes collection bindings after composition, and the lead integrates.
- **Limits:** PCA2 and all four aggregates remain Not started; acceptance fields stay null. Scope, prerequisites, estimates, closed acquisition/data/production gates, the $200 cap and $36.567974 unreconciled reservations remain unchanged.

[Current backlog](../EXECUTION_BACKLOG.md#current-status)

<details>
<summary>Prior status and technical planning record</summary>

**Current progress — 2026-10-29 UTC:** PCA1 #120 is In progress under reviewed entry `6491c371`, clarification `a4ce5405` and root grant `6ad5320c`; all acceptance fields remain null. PCA2 and the four aggregate tasks remain Not started. See the [current backlog](../EXECUTION_BACKLOG.md#current-status). The dated technical plan and its original status snapshot below are retained; scope, prerequisites, estimates and external gates are unchanged.

2026-10-27 · technical candidate for independent review · no implementation acceptance

The new owner decision permits preparation of the reviewed proposal at aaa1d9749b196bdef6da69510c74fbbbfb2d2340. The original planning implementation was independently reviewed at 9aa5a204cbaca0b944f841ade84086046caffdb1 against the F3 checkpoint 8fd8bf19179f95da27bb0b223f38fb1192456e87. This successor composes the same planning scope onto corrected P2 source 0e7e3bd7592ee043e8bc5f3c938610d6e99b5a6d. P1 accepted delivery and P2 In progress/null acceptance are preserved. The reused primary checkout owns planning integration; no runtime, corpus schema or normalizer implementation is included.

The machine ledger contains four new aggregate tasks and two nested preparation PRs. An ordinary delivery package cannot express this work because it inherits every aggregate prerequisite. The narrow preparation representation below permits only the two reviewed offline boundaries; it changes no existing package inheritance rule.

| Node | Requires | Meaning |
| --- | --- | --- |
| PUBLICPREP0 | AR-002-B | Recorded scoped owner continuation; only preparation authorized. |
| PCA1, within AR-002-C | AR-002-B, PUBLICPREP0 | New public declaration/candidate contract and schema preserving v1. Accepted source, merge and independent review are required before PCA2. |
| AR-002-C | AR-002-B, PUBLICPREP0, PCA1 | Complete source-neutral C02 operating supplement and reconciliation; remaining duties are not erased by PCA1. |
| PCA2, within PUBCAP-A | PCA1, PUBLICPREP0 | Supplied synthetic rows and independent qualification fixtures; typed inference/evaluator manifests, pure offline, disconnected. |
| PUBLICDATA0 | AR-002-C | Actual independently reviewed public rights, source/evaluator access, processor/purpose/storage and retention decisions; no execution authority. |
| PUBCAP-A | PUBLICDATA0, G2, PCA2 | Remaining qualified native adapter, custody and acquisition preflight. Not started throughout preparation. |
| CAPTUREFUNDS0 | PAID0, PUBLICDATA0, PUBCAP-A | Separately bounded development and sealed allocations from reconciled existing funds. |
| PUBCAP-B | PUBCAP-A, G2, PUBLICDATA0, CAPTUREFUNDS0 | Separately authorized development capture and complete denominator/feasibility evidence. |
| AR-026-A | AR-024-C, AR-025-B, AR-002-B, AR-024-D, PUBCAP-B | Original independent protocol/sample/threshold/affordability decision, with development capture added. |
| PUBCAP-C | PUBCAP-A, AR-026-A, G2, PUBLICDATA0, CAPTUREFUNDS0 | Explicitly authorized sealed baseline capture under the frozen protocol. |
| AR-038-A | AR-026-A, PUBLICDATA0, PUBCAP-C | Public-route corpus/split/denominator/evaluator freeze. |
| STUDYFUNDS0 | AR-026-A, AR-038-A | Original separate actual confirmatory-study allocation. |
| AR-038-B | AR-038-A, STUDYFUNDS0, AR-026-C, G3 | Actual bounded study remains separately gated. |
| AR-038-C | AR-038-B | Original independent claim/missingness/null-result review. |

PCA1 and PCA2 are separately audited dependency nodes with their own statuses and accepted delivery evidence. They cannot be dispatched from a side note, a pending review, or aggregate status. PCA2 must be Not started until PCA1 is Verified with source/merge/review evidence and PUBLICPREP0 is satisfied. Native PUBCAP-A remains Not started until PUBLICDATA0/G2/PCA2 are satisfied. No preparation result completes its aggregate.

PCA1 preserves corpus v1 behavior and bytes. It distinguishes a pre-recording candidate, which cannot have fabricated native identifiers, from a separately admitted recorded entry. A syntactically valid declaration does not establish rights or permission. Caller-owned processor/purpose/storage/revocation policy, exact current time and private identity references remain mandatory.

PCA2 consumes only supplied synthetic rows and independently constructed qualification fixtures in this scope. Trusted receipt bindings cover exact row/card/source/field-policy/schema/normalizer/inference/evaluator/image identities and current rights. Unknown keys, duplicate members, aliases, unexpected shapes/nulls/types, unresolved created_at interpretation, expired/revoked rights, stale receipts, transitive leakage and unsupported/oversize state refuse admission. A source README is not a complete runtime schema; no source requiredness or nullability is guessed.

Inference receives only qualified instruction and admitted base context. Raw row, supplied repository/instance metadata, reference patch/tests, PR/interface text, labels, logs, image/build names and metadata cannot become context, IDs, ranking, cache keys, errors or derived hints. The full TaskSpec serialization is not an inference payload. Independently qualified hidden-field variants with equal admitted context and eligibility must produce equal inference bytes and cache identity; stale receipts after row mutation must fail separately. Qualification must retain original-fail, reference-pass, invalid and tamper outcomes and complete denominators. Synthetic receipts demonstrate validation boundaries, not actual evaluator or rights qualification.

The normalizer performs no network, file acquisition, image pull, dynamic import, build/install/test command execution, model call or Engine.run integration. It reports next-gate eligibility, quarantine or unsupported state honestly. An eligible normalized candidate is not an admitted natural failure or branchable recording. Actual native consumers need later separation, restore, grader, provenance, cost and uncertainty evidence.

| Aggregate | Total base [range] | Included preparation | Residual base [range] |
| --- | --- | --- | --- |
| AR-002-C | 3 [3–6] | PCA1 1 [1–2] | 2 [2–4] supplement/reconciliation |
| PUBCAP-A | 3 [3–5] | PCA2 2 [2–3] | 1 [1–2] native integration |
| PUBCAP-B | 1 [1–2] | None | 1 [1–2] |
| PUBCAP-C | 1 [1–2] | None | 1 [1–2] |
| Total | 8 [8–15] | 3 [3–5], included | 5 [5–10] |

These are low-confidence corpus-specific planning bounds, not calendar commitments. AR-014 checkpoint/restore, AR-018 evaluator isolation/attack review, AR-026 feasibility/statistics/recovery and AR-038 curation retain their original scope/effort. Actual charges, external waits and unapproved remediation remain excluded. Accountable human effort and physical versus attributed costs remain separate.

The route changes only AR-026-A's added prerequisite and AR-038-A/B's research inputs. Exact prior AR-038-A/B records are retained in the versioned technical amendment. C17 is replaced only for those public consumers by the source-neutral C02 operating supplement, which retains custody, rights, source/evaluator identity, run accounting, retention and operational duties. Global DATA0/PARTNER0/C17, AR-035/036/037, all enterprise pilot work and G4/G5 remain unchanged.

The estimate projection is 155 aggregates, two preparation nodes, 167 planned PRs, 53 parents, 30 gates, 20 contracts and 569 edges. Total effort is 472 base / 799.6 upper; the alternative 25% allowance is 590, not additive. RS is 71 and BE 100.5; M0 is 11.5, M2 73, M3 81 and M5 51. The 173.5-day effort-only path still runs through enterprise G4/G5; no completed work or removed enterprise effort is credited. All four new aggregates and PCA1/PCA2 are Not started; previous task/package statuses and acceptance remain unchanged.

Implementation sequence: independently accept the exact technical record and checker/schema design; compose the reviewed planning delta while preserving later delivery records; run all required planning regressions and independent review; accept PCA1 delivery; then start PCA2. New native/runtime, rights, acquisition, capture, held-out, funding and study gates require their own evidence and authorization.

</details>
