# Context, proposal quality and experiment selection

Review date: 2026-10-19 (America/Los_Angeles); recorded 2026-10-20 UTC.
Status: planning amendment for review. No model calls or method reproductions.

This supplements the accepted [C20 audit](PRIOR_METHOD_AUDIT.md) and
[C21 design](TOTAL_BUDGET_PROTOCOL.md). Their source records and the
[owner decision](OWNER_DECISION_2026-10-20.md) remain unchanged. The nine selected
engineering scopes remain approved; this document does not activate deferred
RB-07, adapters, reusable repairs, paid studies or held-out screening.
C02 remains the execution authority until a separately reviewed amendment.
The active backlog remains 150 tasks, 538 edges and 440 base engineering days.

## What the product actually does

The five audited files (config.py, worker.py, policy.py, experiments.py and
engine.py) are unchanged between main `555d28c` and reviewed
artifact branch `24096f7`. This is a source audit, not inspection of a running
deployment.

| Component | Current behavior and limitation |
| --- | --- |
| Model | `Settings.model_name` and `model_url` have no default model ID. One configured `ChatPolicy` serves execution, proposals and continuation. There is no separate diagnosis model. [config](../../agent_rewind/config.py), [worker](../../agent_rewind/worker.py). |
| Historical model evidence | October 6 validation used `gpt-6-astra`, high reasoning, 128,000 maximum input tokens, 8,192 maximum output tokens and no provider seed. Allowlisted response metadata confirms five baseline and two branch responses. This does not establish today's deployed settings. [Validation](../VALIDATION.md). |
| Provider request | Chat Completions, configured model, JSON-object response, `max_completion_tokens`, `store: false`; optional seed and reasoning effort. Temperature/top-p are not set. [policy](../../agent_rewind/policy.py). |
| Initial context | System instructions, Action JSON schema, task instruction and sorted workspace filenames. File contents enter only through recorded tool observations. |
| Location ranking | Deterministic score: four points for tool failure, three for finish, two times capped repeated-action count, workspace-change indicator and a small earlier-step preference. Top three locations by default. This is a heuristic, not causal attribution. [experiments](../../agent_rewind/experiments.py). |
| Alternative generation | Copies the pre-action conversation, appends the template below, makes one proposal call per location with requested seed offset 777, rejects the identical action and adds an unchanged-observation control. No automatic full-repository or failed-suffix context. |
| Replay | Restores the original checkpoint and applies the replacement. The diagnostic prompt is not inserted into continuation. Continuation policy identity must match the original run. [engine](../../agent_rewind/engine.py). |
| Receipt gap | The prompt digest covers the system instruction, not the appended schema, diagnostic template or complete permitted context. Discovery discards its separate provider decision receipt. Historical summary records three proposals without complete individual usage linkage. Full proposal attribution and charging are future work, not an existing guarantee. |

Current public proposal template, with runtime substitutions shown:

```text
This run failed its independent evaluator. Propose one different action at this decision, without accessing evaluator files. Original action: <original action>. Diagnostic hypothesis: <heuristic reason>
```

The public system instruction constrains the agent to Linux workspace tools,
JSON actions, no network, fresh shells and explicit testing. It is not an
evidence-backed diagnosis procedure. The complete source is linked above;
private task prompts, traces and credentials are not published.

Audit identities: policy SHA-256
`662a84c9ce5b397a6d26ee8a7b08335d6a1365d0e2cd56a4e8f14315ade06570`;
experiments
`5b857c898fc753d24168262a83ad8594ed36b7dcb25d49f6a687195e59590923`;
system prompt
`2f6da4a61acf7c3a079b6f807bfd4f30420858923d23c507f04e789c4273e4b1`.
Historical private evidence remains in the existing owner-readable evidence
store; it is not copied into this repository.

## Research objective and candidate method

Measure independently confirmed useful interventions per fixed total resource
budget on naturally occurring coding failures. Report retry recovery separately.
A useful intervention is conditional on a particular failure; it need not be
the uniquely responsible decision. Product reliability and research superiority
are separate claims.

The proposed extension has three parts, to be tested independently before a
combined comparison:

1. Build bounded, checkpoint-consistent context instead of relying on a heuristic
   label alone.
2. Generate distinct, falsifiable repair hypotheses; use a separate critique
   step to identify unsupported assumptions and duplicate actions.
3. Compare a cost-aware choice of the next diagnostic read, proposal or screening
   continuation against the approved uniform and standard successive-halving
   controls. Fresh confirmation remains reserved and sealed.

These are hypotheses informed by prior work. More agents, longer prompts and
more reasoning are not themselves contributions. The accepted comparator uses
a common frozen pool; changing candidate generation changes the experiment and
requires a separate end-to-end comparison.

## Primary-source method matrix

| Source and dated version | Contribution used in this plan | Fidelity, code and evidence limits |
| --- | --- | --- |
| [DoVer v3](https://arxiv.org/html/2512.06749v3), [Causal Agent Replay v1](https://arxiv.org/html/2606.08275v1), [REFLECT v1](https://arxiv.org/html/2606.09071v1), [DAAF v1](https://arxiv.org/html/2609.32498v1) | Existing C20 comparison for intervention, replay, attribution and reusable repairs. | Reuse the accepted [version/license/semantics matrix](PRIOR_METHOD_AUDIT.md). Do not reopen it as a duplicate audit or describe repeated replay as novel. Oracle access, unavailable artifacts and deferred adapters remain explicit there. |
| [SHERLOC v2, August 31, 2026](https://arxiv.org/html/2606.24820v2) (v1 June 23) | Structured diagnostic localization from bounded repository inspection motivates the context/hypothesis arm. | Its retrospective quality filter uses the ground-truth patch; omit that oracle filter from deployable diagnosis. The [localization recipe](https://github.com/NVIDIA-NeMo/Skills/tree/bcf059af55c20a89f797724598f9908d126153e6/recipes/sherloc) at `bcf059af55c20a89f797724598f9908d126153e6` (September 11) has a [root Apache-2.0 license](https://github.com/NVIDIA-NeMo/Skills/blob/bcf059af55c20a89f797724598f9908d126153e6/LICENSE). Python snapshots and default directory exclusions limit adaptation; required evaluation snapshots are not distributed. |
| [Debug2Fix v2, April 21, 2026](https://arxiv.org/html/2602.18571v2) (v1 February 20) | Runtime questions, breakpoints and inspected values motivate a later bounded diagnostic-tool arm. | The paper explicitly says company policy prevents source release; no source pin or code license verified. Direct debugger use and a debugger subagent are distinct conditions. The same model serves main agent and debugger in its experiments; cheaper-diagnoser success is not established. A checkpoint debugger would be an adaptation, with execution cost charged. |
| [ContextBench v3, February 11, 2026](https://arxiv.org/html/2602.05892v3) (v1 February 5) | Secondary measurements for explored, retained and declared code context. | Gold context is patch-informed evaluation data and stays sealed. Context coverage does not prove causal use or successful repair. [Inspected code](https://github.com/EuniAI/ContextBench/tree/1436c28a8eb95496da4ea69ad458b9f8a8eb7d61), June 12, has [root Apache-2.0 licensing](https://github.com/EuniAI/ContextBench/blob/1436c28a8eb95496da4ea69ad458b9f8a8eb7d61/LICENSE). Alternative valid fixes may require different context. |
| [Agent Retrieval Bench v1, July 27, 2026](https://arxiv.org/html/2607.24882v1) | Base-commit corpus hygiene, evidence retrieval and abstention. | Agent pilot measures context selection, with single trajectories and unequal seed-context amounts; it is not executable repair evidence. [Code](https://github.com/eyuansu62/agent-retrieval-bench/tree/07014c986f3deadb1548c62b32c0ffbe6a81465d) at August 4 has [MIT licensing](https://github.com/eyuansu62/agent-retrieval-bench/blob/07014c986f3deadb1548c62b32c0ffbe6a81465d/LICENSE); [corpus licenses remain upstream](https://github.com/eyuansu62/agent-retrieval-bench/blob/07014c986f3deadb1548c62b32c0ffbe6a81465d/DATA_LICENSE.md). Add token matching and repository-aware analysis. |
| [SWE-Replay v2, February 5, 2026](https://arxiv.org/html/2601.22129v2) (v1 January 29) | Direct prior art for automatic coding-checkpoint selection and alternative continuations; add an observable-feature adaptation only through a reviewed baseline proposal. | Archive selection uses exposed reasoning and explored-file features; action-only traces cannot faithfully reproduce that interface. Fixed trajectory-count experiments disable the dollar cost limit and report cached inference costs, differing from complete hard-budget independent confirmation. No author implementation located in paper/homepage/bounded repository search; source pin/license unresolved. |
| [SWE-Search, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/a1e6783e4d739196cad3336f12d402bf-Paper-Conference.pdf) | Tree search, value feedback and a discriminator motivate diversity/critique controls; branching and multi-agent feedback are prior art. | Paper evaluations do not establish our independent-confirmation endpoint. [Author-linked code](https://github.com/aorwall/moatless-tree-search/tree/bc66ea64e3fe96cf3c90f197b4bab9aaa15e1eb9), January 13, 2025, has a [root Apache-2.0 license](https://github.com/aorwall/moatless-tree-search/blob/bc66ea64e3fe96cf3c90f197b4bab9aaa15e1eb9/LICENSE). Inspect transitive/data licenses before any adaptation. |


No method below has been reproduced here. Author benchmark results are not
Agent Rewind results. Paper publication, code availability, usable licensing
and faithful adaptation are separate checks. Current code pins are inspection
identities, not claims to be the exact paper evaluation commit.

## Context contract and information boundaries

A proposed `DiagnosisContextManifest` should bind installation/project/study/method/task/policy-run/phase and frozen policy/state
identities, checkpoint and event-chain digests, workspace/image/tool versions, task text,
original action, allowed observations, selected file/symbol ranges, visible test
errors, prior proposal identifiers, retrieval provenance, token counts,
truncation decisions and all prompt/view digests. Each source item carries a
visibility class and its acquisition receipt. A filename or hash is not access
authorization.

Current-task repository inspection is allowed only at the approved checkpoint:
bounded read-only tools may inspect that task's files, diff, dependencies,
symbols and test configuration. The development-only restriction applies to
stored repair examples, cross-task memory and retriever training. It does not
ban inspecting the current evaluation repository. No unrestricted network,
hidden evaluator source, reference solution patch, future branch outcome or
confirmation result enters the proposal context.

| View / ablation | Information and comparison rule |
| --- | --- |
| V0 current baseline | Saved pre-action conversation plus current failure flag, original action and heuristic reason; record exactly what the current template exposes. Its heuristic reason is derived from the selected action's actual result and workspace changes, so legacy V0 already includes post-action-derived information. Remove post-action-derived ranking and prompt signals or explicitly declare and review equal access before using V0 in a prefix-only C21 comparison. |
| V1 structured checkpoint | V0 plus permitted files/diffs and test errors already available at that checkpoint. Record missing fields rather than fabricating observations. Compare structure against the same evidence as raw excerpts. Token-matched irrelevant context comes from the same allowed checkpoint; it cannot contain hidden answers or future results. |
| V2 factual diagnosis | Optional separately reviewed arm with the original action's later result or full failed factual suffix. Label this extra information explicitly and give equivalent baselines the same access. It is not authorized by the present prefix-only protocol. Never inject the diagnostic suffix into the replayed agent's saved history. |
| V3 retrieved examples | V1 plus versioned development-only examples/memory. Exclude held-out repository/task families from memory, retriever training and tuning. Charge indexing and retrieval, report amortization and prevent near-duplicate leakage. |
| Prior failed proposals | Only receipts from the same authorized study/method/task/policy-run/phase under the frozen policy and state registry. Another method's same-task outcomes are excluded; shared proposal inputs require declared immutable provenance and comparison-cost attribution. Keep confirmation outcomes and other held-out tasks inaccessible. |

Use separate context objects for diagnosis, proposal and continuation. Replay
continues from the authentic checkpoint even when a future reviewed diagnostic
arm can inspect more of the original failed run. Tests must prove this boundary,
including reference chains, cached summaries and export/reimport.

## Hypotheses, proposals and critique

A diagnosis returns bounded records: suspected mechanism, supporting event/file
references, uncertainty and an observable prediction. It cannot assert a unique
cause from a single trace. Generate a predeclared maximum number of distinct
hypotheses, such as wrong file localization, incorrect API assumption, missing
test observation or premature stopping. Diversity is measured by action/file/
hypothesis differences, not the number of samples alone.

The proposer returns one schema-valid replacement per hypothesis, with
preconditions and provenance. The critic sees only the same allowed information,
checks whether the evidence supports the change, rejects invalid/duplicate/
out-of-scope actions and records why. A critic score is a search signal, never
the independent success evaluator. Compare no critique versus critique with
matched total budgets; failed proposals and rejected critiques still cost money.

The original action, unchanged continuation, fresh retries, random locations,
latest-error and frozen-heuristic baselines remain. Keep continuation model,
evaluator and checkpoint fixed when isolating proposal quality.

## Model comparison

Keep the historically validated Astra configuration as the primary reference
until task-level evidence supports a change. Current official documentation
lists these candidate tiers:

| Candidate | Documented fit; planned role |
| --- | --- |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | Complex reasoning/coding reference. Compare its proposal quality and actual cost, not just one successful replay. |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | Alternative for complex coding at a different cost/latency point. Proposed proposer/critic ablation, not an automatic replacement. |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | Efficient tier; proposed breadth/cheap-critique control, with failure analysis on difficult hypotheses. |

These are documented service tiers, not verified parameter-size comparisons.
Documentation does not prove account access or superiority on this workload.
The [model guide](https://developers.openai.com/api/docs/guides/latest-model)
supports task-specific comparison. No new provider request was made to check
availability. Pin a snapshot if available; otherwise record alias, returned model,
provider fingerprint, service tier, request/response settings and observation date.

The current JSON-action chat adapter does not use native function calling.
If an experimental adapter uses native tools, Sol requires Responses, and Luna's
Chat Completions function calling is restricted to no reasoning. Endpoint/tool
changes must be isolated from model comparisons. Mock conformance comes before
any separately authorized paid capability check.

Same-family tiers are the first comparison. A cross-family arm remains
conditional on a named provider/model's official availability, lawful data
processing, account access and adapter conformance. Do not invent a model or
call the largest model universally best. Provider reasoning labels do not imply
equal compute; measure calls, tokens, reasoning usage where exposed, latency and
cost. Common requested seeds do not establish common randomness.

## Budget-aware selection and confirmation

First compare uniform and standard successive halving over the same frozen
candidate pool and confirmation reserve. Then, as a distinct proposed study,
compare end-to-end methods that may acquire more context or create candidates.
Each method pays for its own complete workflow, including diagnosis, retrieval,
critique, rejected proposals, replay, grading and relevant offline preparation.
Keep physical billing separate from comparison attribution; shared inputs may
be billed once but attributed fairly to each method.

A bounded advanced candidate is a development-calibrated expected useful-repair
gain per incremental cost policy. Actions are inspect, propose or screen; the
inputs are allowed discovery receipts, uncertainty, remaining resource caps and
the protected confirmation reserve. Predeclare exploration floor, tie handling,
missing/ambiguous receipt handling and exhaustion behavior. Freeze all fitted
parameters on development tasks. Compare against simpler controls and ablate
the cost term. This is a proposed RB-07 extension, not an implemented algorithm
or a novelty claim; its exact score and calibration must pass review first.

Selection freezes one intervention per (method, task) before fresh fixed-size confirmation.
Confirmation never feeds the same search policy. No optional stopping for a
positive result. Report unsuccessful, missing, invalid and exhausted tasks.
C21 multiplicity, effect threshold, power feasibility and independent statistical
review remain; this amendment does not quietly change them.

## Proposed engineering work, outside the active ledger

Each row is one independently reviewable PR, not an assignment to begin
implementation. Ranges are incremental planning estimates after the listed
accepted producers, with low confidence; re-estimate overlap before activation.
Common definition of done: scoped acceptance and negative tests pass, independent
source/security/statistical review as applicable, receipts and limitations are
documented, and roadmap/issue/contract status agree. A schema example is not a
runtime guarantee.

| ID / role / effort | Objective and implementation boundary | Prerequisites / proposed interface | Acceptance and required automated tests | Exclusions / security and reliability |
| --- | --- | --- | --- | --- |
| RC-01 / RS+TL / 2–3 days | Specify context, model-role, hypothesis and critique receipts; reconcile C02/C08/C09 permission and cost fields. | Accepted C20/C21, AR-020-A and AR-024-A; reviewed amendment authority. Produces proposed context manifest and role-policy identity contract. | Reject missing visibility/provenance, changed frozen policy and ambiguous phase ownership; complete source/model intake fixtures. | No runtime, hidden-data access or model calls. New contracts stay proposed until review. |
| RC-02 / BE / 3–5 days | Assemble bounded checkpoint context with charged read-only retrieval; retain full view digest. | RC-01; AR-014-C branch restoration conformance, AR-023-C full accounting, AR-021-A sealed coordinator. | Truncation determinism; forbidden file/symlink/reference/cache leakage; immutable checkpoint; scope revoked during read; receipt reconciliation. | No cross-task memory, model proposer or factual-suffix arm. |
| RC-03 / BE+RS / 3–5 days | Separate diagnosis/proposal/critique roles with bounded diverse outputs and complete call receipts. | RC-02; AR-025-A proposal boundary and AR-025-B baseline harness. Role-policy identities do not change continuation identity. | Invalid/duplicate action handling; crash/uncertain call accounting; critic isolation; same allowed context; no prompt injection into continuation. | No learned allocator or new provider deployment; no model confidence used as success truth. |
| RC-04 / RS+QE / 2–4 days | Add paired context/critique/model-tier ablation manifest and offline adapter fixtures. | RC-03; AR-024-D simulator and AR-026-A feasibility review. | Token/tool/resource matching, attribution of failed proposals, family split contamination tests, fixed continuation/evaluator and multiplicity-family export. | No paid capability probes or benchmark execution. Cross-family arm stays conditional. |
| RC-05 / RS / 3–5 days | Specify and simulate inspect/propose/screen selection with calibrated cost term; compare to uniform/halving. | RC-03; AR-025-D accepted comparator, AR-024-D and AR-023-C. Separate RB-07 approval and statistical review. | Synthetic null, misleading context, heterogeneous costs, missing receipts, exhausted reserve and state-replay tests; cost-term ablation. | No held-out tuning, optional confirmation stopping or superiority claim. |
| RC-06 / BE+RS / 2–4 days | Add permitted memory retrieval and separately labelled factual-diagnosis information arms. | RC-02, RC-04, AR-002-A rights manifest and AR-002-B split protocol; explicit C02 extension plus DATA0 (actual corpus execution also waits for AR-038-A). New retrieval/view protocol. | Development-only memory, held-out-family/near-duplicate exclusion, index provenance/costs; original suffix never reaches continuation; cache partition and deletion. | No training or online cross-task adaptation; no hidden evaluator or reference patch ingestion. |

The provisional increment is **15–26 engineering days**, not added to the
440-day active plan. RC-01 may overlap contract work; RC-05 overlaps deferred
RB-07, and memory work overlaps later corpus/integration packages. Reconcile
these overlaps before approving a revised ledger rather than adding both totals.

### Dependency review and exit gates

The proposal is acyclic: RC-01 → RC-02 → RC-03 → RC-04; RC-05 can proceed beside
RC-04 only after its own comparator/accounting/simulation prerequisites; RC-06
waits for RC-04, corpus rights and explicit information-policy approval.
External producer IDs refer to the active backlog; they are not assumed ready.
No task is placed ahead of its contract, accounting or snapshot producer.

1. **Design gate:** accepted sources, exact current-model facts, reviewed
   information views and approved bounded scope. C02 amendments require their
   existing reviewers; this planning request alone does not satisfy the gate.
2. **Offline integration gate:** all receipts, permission boundaries, restart,
   accounting and mock-adapter negative tests pass. Compare the simple controls
   before accepting additional complexity.
3. **Development feasibility gate:** separate funding/data/statistical approval,
   frozen development corpus, reconciled prices, measured replay fidelity and
   power feasibility. Record a stop/narrow decision if projected evidence is
   unaffordable or assumptions fail.
4. **Final evaluation gate:** unseen repositories/task families, frozen policies,
   independent confirmation, full failed-task accounting and reviewed claims.
   Reopening search after confirmation starts creates a new study, not an update
   to the old result.

The next engineering slice remains the ready M1 foundation work. The next
research slice is the existing C08/C09 contract producers when their M1/M2
dependencies are accepted; RC-01 can then be reconciled as a separate reviewed
extension. There is no new calendar promise. Review these estimates at producer
acceptance and schedule runtime work only after scope activation.

## Decisions and present limits

Approved core controls and thresholds need no repeat permission. New decisions
are whether to activate the context/role extension, whether to permit the
explicit factual-suffix or memory arms, and whether to activate RB-07 after
baseline evidence. Model availability checks, real data and evaluation spending
retain their existing gates. This document recommends staged ablations, not a
large unvalidated replacement system. No production, research superiority or
generalization claim is established.

## Review record

Engineer A verified the five audited modules, historical-model distinction,
source hashes and five new primary-paper entries. Review required explicit
method/phase identities and recognition that legacy checkpoint ranking itself
uses post-action evidence; the lead applied both corrections, including ranking
and prompt signals. Engineer B independently checked all external prerequisite
IDs, the acyclic six-card dependency graph, 15–26-day arithmetic, accounting
and execution-authority boundaries. The lead checked current official model
documentation and SWE-Search, relative links and unchanged design records.

These are internal planning reviews. They do not replace external statistical
approval, runtime acceptance, source-license intake or paid evaluation gates.
No method was executed or measured for this amendment.
