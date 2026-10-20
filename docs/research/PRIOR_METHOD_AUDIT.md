# Prior-method audit and comparison recommendation

RA-01-A · inspected 2026-10-20 UTC · **design/review only**

The evidence does not establish a new allocation algorithm. Replay intervention,
adaptive diagnosis, threshold search, heterogeneous-cost selection and shared
statistical models all have relevant prior art. The defensible candidate is a
measured adaptation: does selecting experiments using faithful restoration and
actual costs improve **distinct-task confirmed repair yield under a fixed total
budget**, compared with equal allocation and established selection procedures?
This is a hypothesis, not a result or a novelty certification.

The owner approved RA-01's 4–7 engineering days for this audit and the subsequent
protocol review. This file does not authorize adapters, algorithms, experiments,
paid inference, data access or deployment. The existing
[natural-failure protocol](../delivery/NATURAL_FAILURE_PROTOCOL.md), C02 permission
requirements and independent confirmation rules remain in force. RA-01-B must
resolve the proposed discovery-policy changes before implementation.

## Evidence and search boundary

The [structured record](../../contracts/research/prior-methods.json) is the
attribute-level matrix: each statement has a source and an evidence state.
**Paper reported** means the authors describe it; **source inspected** means
selected public source was read, not executed; **inference** is our adaptation
judgment; **unknown** remains unresolved. Every method's reproduction status is
**not executed**. No repository was cloned and no third-party source was run.
A public source tree is evidence of availability, not experimental reproducibility.

The search covered the four requested versioned papers, their author-linked
project/code pages, selected raw GitHub blobs and untruncated repository trees.
Bounded public repository searches used the identifiers/titles “REFLECT err-loc”,
“2606.09071”, “DAAF attribution” and “2609.32498”; author provenance was checked.
The adjacent search covered the seven primary publications below, not an
exhaustive citation graph. “Not located” means not located in this search on the
stated date. Name-matched forks and underlying benchmark repositories were not
substituted for an author's implementation.

| Method / pinned paper | Public implementation inspected | Availability and reproduction disposition |
| --- | --- | --- |
| [DoVer v3](https://arxiv.org/html/2512.06749v3) | [ACV / misc/DoVer at 994ac15](https://github.com/microsoft/ACV/tree/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer) | Adaptation candidate; root MIT text inspected; documented evaluator command incomplete at this pin. No execution. |
| [CausalAgentReplay v1](https://arxiv.org/html/2606.08275v1) | [CAR at db90fa2](https://github.com/jaineet17/causal-agent-replay/tree/db90fa28b97164c35e7c524e4597b8cbdb3035af) | Adaptation candidate; declared Apache-2.0, license text/notice completeness unresolved. Later code pin is not proven to reproduce the paper revision. |
| [REFLECT v1](https://arxiv.org/html/2606.09071v1) | Author implementation not located | Paper describes supplementary artifacts and planned public licensing; no inspected public implementation/license pin. Paper adaptation possible only with an explicit fidelity gap. |
| [DAAF v1](https://arxiv.org/html/2609.32498v1) | Author implementation not located | Release promised; current intervention semantics incompatible with the proposed one-action checkpoint comparison. A separate asset-repair study could be considered later. |

### Replay, information and statistical semantics

DoVer describes trial-level hypotheses and targeted edits, with three validation
replays and a two-success rule. That rule does not replace our fresh confirmation
protocol. Its reported settings do not establish coding-repository holdout
performance. [Paper sections 3–4](https://arxiv.org/html/2512.06749v3)

The released DoVer path exposes a stronger information regime than an ordinary
developer debugging a failure: the
[recommender](https://github.com/microsoft/ACV/blob/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer/scripts/intervention_recommender_trial.py#L146)
receives ground truth while asking that it not be copied into the edit. This is
still oracle-assisted proposal generation. The
[intervener](https://github.com/microsoft/ACV/blob/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer/scripts/intervener_trial.py#L173)
edits team instructions/ledger content; translating that into a sequential coding
action changes the intervention. A
[history/cache loader](https://github.com/microsoft/ACV/blob/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer/scripts/state_loader.py)
and [AG2 restoration](https://github.com/microsoft/ACV/blob/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer/AG2/ag2_checkpoint_system/restoration.py)
exist; their native filesystem fidelity was not exercised here. The
[README](https://github.com/microsoft/ACV/blob/994ac15db6fff8a5131bbf5a26e84e352e676796/misc/DoVer/README.md)
invokes scripts/evaluator_trial.py, absent from the
[untruncated pinned subtree](https://api.github.com/repos/microsoft/ACV/git/trees/81483179f58c3bc7fa729a713288f2dbc00696d3?recursive=1).
This is a specific reproduction prerequisite, not a claim that reproduction is impossible.

CAR's [forward replay](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/replay/forward.py)
copies conversational state but uses a live environment and explicitly defers
real-tool side effects. A coding adapter must independently restore every trial
and preserve the difference between replacing an observation and executing an
action. Its
[contrastive attribution](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/contrastive.py)
uses fixed samples per step and the factual outcome as reference. That is a
different estimand from our repeated paired no-edit control. Its
[Shapley path](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/shapley.py)
uses configured sampling with truncation; its
[budget object](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/budget/budget.py)
multiplies samples by a constant price. Neither establishes measured end-to-end
cost accounting or adaptive evidence allocation. The later
[WhoWhen surrogate](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/bench/surrogate.py)
defaults to ground-truth-conditioned environment simulation; do not present that
as a native coding benchmark.

REFLECT already adapts diagnosis after unsuccessful candidates and stops on
verified success. Expected answers inform localization and diagnosis as well as
verification. Executable SWE patch tests are described; exact snapshot/restore
implementation remains unverified here. [Algorithm 1, sections 3–4 and appendices D/J](https://arxiv.org/html/2606.09071v1)

DAAF repairs registered persistent assets from initial task state. It already
reports matched task repeats and task-level resampling; offline CTCA/training
costs must accompany the smaller online-run count. It cannot serve unchanged as
a saved-checkpoint single-action baseline. [Section 3 and appendices B/E/F/G](https://arxiv.org/html/2609.32498v1)

## Adjacent allocation work and novelty limits

These are objective-level comparisons from primary publications, not imported
guarantees. A generated intervention set, correlated paired outcomes, variable
rollout cost, evaluator missingness and independent confirmation can violate the
assumptions behind a simple bandit reduction. RA-01-B must name and test those
assumptions before selecting a policy.

| Prior objective | Existing contribution relevant here | Consequence for this project |
| --- | --- | --- |
| [Best-arm identification, 2010](https://www.microsoft.com/en-us/research/publication/best-arm-identification-multi-armed-bandits/) | Pure exploration and successive rejects. | Adaptive selection of one winner is established. Repair yield may require several useful candidates. |
| [Non-stochastic best arm, 2016](https://proceedings.mlr.press/v51/jamieson16.html) | Successive halving for finite-resource evaluation. | Include a standard allocation comparator; renaming halving is not a contribution. |
| [Thresholding bandits, 2016](https://proceedings.mlr.press/v48/locatelli16.html) | Identify arms above a threshold within a fixed horizon. | Closer to useful-repair yield than best-arm alone; do not claim threshold-aware search is new. |
| [Cost Aware Best Arm Identification v2](https://arxiv.org/abs/2402.16710v2) | Heterogeneous testing costs, minimum expected cost. | Cost awareness is established; its stopping objective differs from a hard spending cap and multiple confirmed repairs. |
| [Structured fixed-budget BAI, 2022](https://www.ijcai.org/proceedings/2022/388) | Shared generalization model and successive elimination. | Trace-feature sharing plus elimination alone is not new. |
| [Feasible Arm Identification, 2018](https://proceedings.mlr.press/v80/katz-samuels18a.html) | Fixed-pull identification under vector constraints. | Joint success/harm/resource requirements also have prior art. |
| [Test-time compute scaling v1](https://arxiv.org/abs/2408.03314v1) | Prompt-dependent inference allocation. | General compute allocation is not an agent-replay novelty claim. |

## Recommended comparison set

Use two separately reported estimands: (1) confirmed effect of a frozen edit
against a paired no-edit continuation from the same checkpoint, and (2) end-to-end
task recovery under a total resource cap. Fresh restart/retry belongs to the
second; it must not be labeled a checkpoint intervention effect.

1. **Required controls:** unchanged continuation and fresh restart; random
   eligible checkpoint, latest-error checkpoint and frozen deterministic
   heuristic; equal trial allocation over a shared proposal pool. Freeze the
   proposal model, context, temperature, tool policy and allowed information.
   Do not let a better proposer masquerade as a better allocator.
2. **First published-method adaptations:** DoVer's targeted proposal path and
   CAR's resampling ranking, conditional on rights, release and restoration
   gates. Report original-method outputs separately from the common confirmation
   evaluator. Do not replace CAR's factual-reference estimand and call it an
   exact reproduction, or collapse team-instruction edits into action edits
   without identifying the transformation.
3. **Allocation comparators:** uniform allocation plus a declared standard
   threshold/halving procedure over the same frozen candidate set. Add a
   cost-aware alternative only after its assumptions and hard-cap behavior are
   reviewed. Do not combine different candidate generation, allocation and
   confirmation policies into one unexplained comparison.
4. **Conditional references:** REFLECT requires an author artifact or an
   explicitly labeled paper adaptation. DAAF requires a separately approved
   persistent-asset, fresh-start experiment. Neither an unavailable
   implementation nor a semantically incompatible baseline should receive a
   fabricated score or be silently omitted from limitations.

For oracle-assisted methods, either give every compared method the same declared
oracle information in a separate oracle stratum, or create and label an
answer-blind adaptation. Hidden evaluation answers must not enter ordinary
production proposals. DoVer's no-copy instruction and REFLECT's proxy verifier
do not by themselves establish information parity.

Charge proposal/diagnosis, baseline generation, restore, replay, grading,
confirmation and failed/uncertain attempts to the same predeclared resource
accounting. Show currency, tokens, CPU/time and parallelism separately; a constant
sample price cannot stand in for observed total cost. Report any training,
indexing or learned-selection preprocessing both unamortized and under declared
reuse counts. Treat model price/version changes as an explicit comparability
issue, not an invisible advantage. No costs were measured by this audit.

## Discovery, confirmation and generalization handoff

The current protocol prohibits using confirmation outcomes to improve the same
candidate. Preserve that boundary: discover candidates, freeze the selected
edit/policy and its identity, then run the precommitted fresh confirmation.
Repeated seeds for one task are not independent tasks. Count each task once in
confirmed yield; retain failed, unselected, missing, invalidated and
budget-exhausted attempts in the denominator.

The proposed adaptive discovery on evaluation tasks is not automatically allowed
by the existing frozen held-out protocol. RA-01-B must explicitly define an outer
repository/task-family holdout with a frozen search algorithm, a permitted
inner discovery outcome stream and a separately sealed confirmation stream.
Until reviewed, the existing restrictions apply. Include evaluator-content
families, shared patches and generated task derivatives in leakage checks.
Preprocessing/training must exclude the outer holdout.

RA-01-B must also define portfolio multiplicity, practical effect/harm thresholds,
confirmation reserve, inconclusive outcomes, evaluator outages and uncertain
charges. Do not keep sampling until a favorable interval appears. A replay
outage is not a negative task result, and a discovery success is not confirmed
evidence. Independent statistical review and DATA0/STUDYFUNDS0 remain required
before any funded evaluation.

A favorable future result would support an empirical adaptation for the
declared population, not automatically a novel algorithm or universal causal
localizer. If gains disappear against equal-information threshold/cost-aware
controls, accept a null/no-novelty result and retain the engineering product
claim. Broader novelty and generalization remain open questions.

## Proposed follow-up scope, not implementation authorization

Estimates below are engineering judgment with **low confidence**, in engineering
days, assuming accepted C08/C09 replay/evidence interfaces. They exclude native
replay construction, original-system reproduction, paid experiments and external
release delays. They are not added to the active DAG or the approved 4–7-day
design budget. Each adapter first requires a small rights/fidelity checkpoint;
stop and revise the estimate if it fails.

| Independently reviewable package | Estimate | Prerequisites and exit evidence |
| --- | --- | --- |
| Shared proposal controls and information manifest | 2–4 days | RA-01-B accepted; replay/evaluator interfaces available. Same pool and information fixtures, deterministic policy receipts. |
| DoVer adaptation | 4–8 days | Shared controls; missing evaluator path resolved or declared substitute; license review; restoration verified. Explicit edit/oracle transformations and native-state regression. |
| CAR adaptation | 3–6 days | Shared controls; license completeness resolved; restoration verified. Restore-per-trial checks, ranking export, separate reference/confirmation estimands. |
| REFLECT availability/fidelity spike | 1–2 days | Author artifact and license obtained. Pin and inspect interfaces; no implementation estimate until then. |
| DAAF availability/asset-study spike | 1–2 days | Author artifact/license and separately approved asset-study scope. Fresh-start/asset semantics and offline-cost plan; no coding-checkpoint adapter estimate. |
| Standard allocation baselines and receipts | 3–5 days | Shared controls; accepted multiplicity/missingness/reserve/cost interfaces. Separate uniform and adaptive PRs with exhausted-budget/late-result tests. |

The owner must approve the selected baseline set, information strata and any new
runtime work. RA-01-B owns threshold/sample feasibility and budget-policy design.
Release owners must resolve artifact/rights gaps before copying code.
Independent review must accept source fidelity; statistical review must accept
the study design. Neither is implied by a source-link validator.

## Offline checks and review record

Run from the repository root:

~~~sh
python scripts/check_prior_methods.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/test_prior_method_audit.py
~~~

The validator checks versioned links, commit pins, reference integrity, required
dimensions, availability/reproduction consistency and unapproved follow-up
estimates. Inspected code/license references must match their repository and
commit; tree references must match the declared repository and pinned tree
reference. DoVer's tree reference is its inspected subtree object, while CAR's
is its repository commit. Manual review establishes that commit/subtree binding. Tests mutate those records to require actual refusal. These checks
do not fetch URLs, establish license scope, reproduce results, verify scientific
claims or authorize experiments. Link retrieval and source accuracy are manual
review evidence.

Independent source review of this exact artifact is pending until an immutable
revision is supplied. No external reviewer, customer validation or completed
baseline experiment is claimed.
