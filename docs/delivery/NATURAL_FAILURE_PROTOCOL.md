# Natural-failure and held-out evaluation protocol

AR-002-B · C02 · Internal engineering protocol awaiting independent statistical
and human pilot review. [Synthetic cases](../../contracts/fixtures/natural-failure-protocol.json)
exercise decisions and arithmetic; no model trials, new customer data, measured
power or natural-failure result is supplied. This extends the
[permission/provenance contract](CORPUS_PERMISSIONS.md) and preserves the complete
attempt denominators in [USEFULNESS.md](USEFULNESS.md).

## Question, population and failure taxonomy

The scientific question is whether a frozen intervention-selection procedure
produces useful edits across a declared population of naturally failed,
compatible coding tasks. A separate question asks whether one specific frozen
edit improves completion probability when continuing one saved failed prefix.
Neither implies that an edit identifies the unique original cause of failure.

Register the task population, source families, workload strata, eligibility
rules, baseline agent, grader and operating limits before collecting outcomes.
Keep every attempted baseline in an accounting table, including successes and
ineligible/missing cases. Conditioning on natural failures is the stated target
population; it does not estimate the agent's unconditional reliability. Record
both eligible baseline attempts and naturally failed tasks so that this selection
is visible. Do not search random seeds until a preferred failure appears: use
predeclared seed/attempt allocations and retain every resulting run.

| Class | Required observation | Treatment in analysis |
| --- | --- | --- |
| Natural task failure | Declared ordinary agent/budget policy; complete execution; verified capture/restore; valid independent evaluator; task fails. | Eligible failure population if all frozen permission/workload criteria pass. |
| Task success | Same valid execution/grade boundary, with success=true. | Retain in baseline population; not a failed-task investigation. |
| Infrastructure failure | Provider/DB/worker/runtime outage, lost lease or interrupted execution. | Operational outcome/missing task grade; not an ordinary incorrect solution. |
| Capture failure | Missing/corrupt checkpoint, incomplete state, redaction or unsupported restore. | Retain in capture denominator; quarantine from branch-effect analysis. |
| Evaluator failure | Grader harness crashes, times out, becomes inconsistent, or fails reference controls. | Quarantine affected results; do not count as task failure. |
| Unknown outcome | No trustworthy grade or uncertain dispatched/provider effect. | Preserve missingness and reservation; no fabricated failure or paid retry. |
| Injected/synthetic failure | Forced early finish, intentionally broken policy, manipulated output, or synthetic test policy. | Mechanics/control evidence only; excluded from natural-failure claims. |

Multiple faults can coexist. Retain the full fault vector and a reviewed primary
classification; the priority used by synthetic tests is only a deterministic
quarantine rule. A valid grader may deliberately classify candidate exceptions
as task failures, but its frozen result taxonomy must distinguish those from a
broken grading harness. Exit code alone cannot make that distinction. Planned
AR-018/024 work must test the classification and grader threat model.

Ordinary step/time/budget limits are eligible only when registered before the
outcome and representative of the declared workload. Lowering a limit to force a
failure changes the population to an injected challenge. The existing validation
with an artificial early stop establishes neither a natural-failure benchmark
nor generality, regardless of how many replay branches pass.

## Permission, identity and immutable records

Before any source loading or model processing, apply current C02 permission,
revocation, processor, purpose and storage policy. A syntactically valid public
manifest is not customer authorization. Split metadata is a separate private
record referencing the validated corpus bytes/digest and task IDs; it does not
weaken or rewrite manifest permissions. Each phase uses its authorized purpose;
new confirmation processing requires independent-confirmation permission.

Freeze the protocol revision/digest, eligibility/classification rules, corpus and
split manifest digests, task/source revisions, checkpoint/event-chain identity,
model revision and observed provider fingerprint policy, processor profile,
adapter/prompt/configuration digest, pinned image/tool policy, evaluator source
and command digests, budget/stopping policy and candidate-selection procedure.
The fixture's model names, identities and review flags are fictional placeholders.

The synthetic identity contract requires the complete frozen field set, validates
digest/revision formats and bounded named identities, and returns compatible only
when every required value agrees. Missing, unexpected, malformed or changed fields
in either the frozen or observed identity quarantine the comparison. The frozen
provider-fingerprint policy records any explicitly accepted lack of visibility;
an omitted fingerprint is not an implicit exemption. Generic image and evaluator
command identities can legitimately be shared across split groups; task-specific
evaluator content cannot.

Record actual returned model/fingerprint, tool/environment and grader identities
for each attempt. An unexpected change quarantines the affected cohort pending
review; do not silently pool it with the original condition. If a provider
cannot expose/pin a relevant revision, register that limitation and a time-bounded
cohort rather than claiming immutability. Resume only under the original verified
identity or a new protocol revision with separately reported outcomes. Retain
permission changes and incomplete trials; no automatic processor fallback.

## Two distinct levels of holdout

**Within-task confirmation** studies one frozen candidate on the same task and
checkpoint after exploratory screening. Development tasks may generate/screen
several candidates, include unchanged-observation negative controls, then commit
the winner's digest before disjoint fresh continuation trials. These continuations
are new stochastic attempts, not new independent tasks. This is the current
conditional scope described in [RESEARCH.md](../RESEARCH.md).

**Task-held-out evaluation** tests a selection procedure frozen using development
tasks. Repository families, task families and task-specific evaluator families
must be disjoint between development and held-out sets. This protocol forbids
outcome-driven screening on held-out tasks: the frozen procedure uses permitted
instruction/trace/context to choose and commit its candidate before seeing any
new held-out continuation grade. Candidate generation may be stochastic but its
configuration, selection rule, budget and seed allocation are frozen. A procedure
that returns no admissible candidate is an accounted no-proposal outcome, not a
reason to discard the task; its treatment policy is the unchanged continuation.

The present product's full adaptive screening procedure is therefore not silently
validated by this narrower held-out protocol. Evaluating that complete procedure
would require a separately predeclared nested protocol, control of access to its
inner outcomes, fresh outer evaluation and statistical review. Do not relax the
backlog's “no screening on holdout” rule after observing attractive results.

Before splitting, join near-duplicate tasks, forks, shared patches/issues,
repository lineage and task-specific evaluator copies into leakage groups.
Shared generic runner/harness utilities alone do not imply identical tasks, but
record their common dependencies. Assign whole groups with a recorded split
seed and strata; no task ID, task family, repository family, source-content digest,
task-specific evaluator family, or task-specific evaluator artifact digest may
span both sides. All these identities are required; missing evaluator provenance
cannot bypass admission. Exact digest checking is necessary but cannot detect
semantically duplicated tasks by itself: independent corpus review must verify
lineage and near-duplicate grouping.

Seal held-out source/results from procedure tuning, prompt editing and selection
threshold decisions. An authorized evaluation runner may read the task context
needed to operate the frozen procedure; the development team does not receive
intermediate outcome feedback. Record accesses and the unblinding decision. Any
leak creates an explicit contamination record, invalidates confirmatory use of
the exposed group and requires a new untouched group allocation. Keep original
counts; do not rename task IDs or reset the split seed until a result improves.

Repositories/tasks are the units for generalization; repeated branches within a
task are nested measurements. Report task and repository-group counts separately
from continuation counts, and use a prespecified analysis that respects that
clustering. Treating correlated repeats as independent population replicates is
the pseudoreplication problem discussed by [Hurlbert (1984)](https://onlinelibrary.wiley.com/doi/10.2307/1942661/full).
The exact grouping above is this project's design choice, not a claim proved by
that paper.

## Evaluator stability and protection

For each frozen evaluator/image, repeat grading of the exact original candidate,
a known valid repair, a known invalid candidate and a tampering control in clean
sandboxes with the same limits. Start with at least three repetitions per control
as an engineering smoke check; this is not a statistical guarantee of a stable
error rate. Record canonical grade/result identity, exceptions, duration and
resource failures. Require repeated expected outcomes and no infrastructure or
grader errors; inconsistent, missing or wrong control outcomes quarantine the
evaluator and affected tasks before study admission.

Expand repetitions/adversarial cases based on the actual grader risk in AR-018.
A stable wrong grader can still pass repeated checks. Human review must examine
test adequacy, grader leakage, candidate imports/test evasion, side effects and
reference correctness. Keep evaluator material unavailable to the policy except
for predeclared allowed feedback; graders run separately and read-only. In the
initial scope, stochastic/model-based grading is excluded unless separately
calibrated and approved. Fixing a grader creates a new identity and invalidates
pooling old/new grades as one unchanged study.

## Pairing, budgets and missing outcomes

For each candidate/control comparison, start both arms from the same verified
checkpoint and fixed task/evaluator/configuration. The control reproduces the
recorded action or observation at that boundary; treatment applies only the
frozen edit. Hold arm budgets, time/step limits and evaluator conditions equal.
Randomize control/treatment execution order within each pair and interleave pairs
across allowed windows. Separate workspaces and call identities prevent shared
mutable state. Record scheduling/provider drift; adjacent timing does not prove
statistical independence. Requested common seeds are advisory, not deterministic
sampling or guaranteed common random numbers after contexts diverge.

Record all planned pair IDs before dispatch. A pair missing either valid grade is
missing for the primary binary comparison, even if the other arm passes. Preserve
both observed effort and costs; do not rerun only failed/missing arms to select a
better outcome. Predeclared recovery may resume the same undispatched work, but
an ambiguous paid call requires reconciliation under its existing identity.
Operational stopping for safety/budget is allowed and yields incomplete evidence;
it is not an early-success stopping rule.

With N complete pairs, W treatment-only successes and H control-only successes,
the conditional estimate is `(W-H)/N`. Ties remain in N. For M missing pairs out
of T planned pairs, report the worst-case range
`[(W-H-M)/T, (W-H+M)/T]`, along with complete-pair estimates and counts. That range
bounds missing binary outcomes; it is not a confidence interval. Zero complete
pairs gives no effect estimate, not zero effect. Incomplete confirmation prevents
a supported-improvement verdict in this protocol.

The exact discordance calculation conditions on W+H and compares W with a
binomial distribution of probability 0.5 under equal win/harm probabilities.
Discrete tests and confidence intervals need not agree unless their constructions
match; use the frozen interval-based decision rule rather than cherry-picking a
p-value or interval. See [Fay (2010)](https://journal.r-project.org/articles/RJ-2010-008/index.html).
The existing conservative interval in statistics.py is a conditional per-task
method; it is not a clustered cross-task confidence interval.

## Selection, multiplicity and outcome decisions

Freeze one primary procedure, population, endpoint, effect threshold and report
family before held-out unblinding. Development rankings and screening estimates
remain exploratory; never pool screening into confirmation. Optional baselines
(such as fixed last-error or random admissible-location selection) use equal
resources and predeclared comparisons. No post-hoc winner across models, tasks,
subgroups or stopping dates may become the single nominal confirmatory result.

For multiple declared confirmatory comparisons, preassign an alpha allocation
whose sum is at most the family budget (proposed 0.05); the union bound supplies
the simple familywise guarantee when each test is valid. More powerful procedures
require their own frozen design and review; sequential rejection methods depend
on explicit validity conditions, as described by [Goeman and Solari (2010)](https://arxiv.org/abs/1211.3313).
This task implements no multiple-testing procedure or sequential monitoring.

| Final decision | Required interpretation |
| --- | --- |
| Supported useful improvement | Full protocol/identity/permission compliance, complete independent outcomes, planned sample achieved and reviewed interval lower bound exceeds the predeclared useful-effect threshold. State the population and uncertainty. |
| Positive but usefulness unestablished | Evidence may exclude zero while failing the practical threshold; do not call the product target met. |
| No supported improvement | Interval includes zero or lacks precision; this is not proof of no effect. Retain adverse and null results. |
| Harm supported | Reviewed interval supports a negative effect; stop promoting the intervention and preserve the evidence. |
| Inconclusive/insufficient | Missing outcomes, insufficient independent groups/trials, identity drift, leakage, invalid grader, budget exhaustion or unreviewed analysis prevents the intended claim. Explain which condition applies. |
| No useful effect within a margin | Only under a separately predeclared equivalence/margin design with adequate precision; absence of significance is insufficient. |

## Effect-size and feasibility worksheet

Before any real experiment, the research owner and independent reviewer must
fill and approve these values. They are intentionally not guessed from the
existing artificial failure or the product's unrelated 20-investigation timing
target.

| Input | Required evidence or decision |
| --- | --- |
| Population and sampling unit | Eligible natural failures, workload strata, independent repository groups, task nesting and sampling weights. |
| Primary effect and minimum useful difference | Conditional completion-probability change or explicit procedure-level estimand, with a predeclared practical margin. |
| Outcome probabilities | Plausible control success, treatment-only wins qW, control-only harms qH, ties, heterogeneity and uncertainty ranges from permitted development data. Delta=qW-qH; same delta with different discordance can need different sample sizes. |
| Error/power targets | Family alpha, multiplicity allocation, target power and precision, all subject to independent review. No power value is asserted here. |
| Clustering and attrition | Repository/task dependence, number of independent groups, expected missingness/outages and drift scenarios. |
| Candidate and trial allocation | Development tasks, candidate count including controls, screening pairs, held-out tasks and confirmation pairs; task and repetition counts remain distinct. |
| Analysis validation | Exact calculations or simulation under null, meaningful effects, heterogeneity, missingness and selection; record method/code/seed and Monte Carlo uncertainty where used. AR-024 owns this work. |
| Cost and operational feasibility | Measured call/resource distributions, per-task caps, held reservations, baseline/discovery/grader cost, concurrency and actual remaining approved funds. |
| Stop/continue rule | Fixed outcomes and sample size, operational stop conditions, null-result response and conditions for a new preregistered revision. |

For within-task development studies, continuation arms equal
`2 * tasks * (screened_candidates * screening_pairs + confirmation_pairs)`.
The synthetic worksheet uses 10 tasks, four candidates including the negative
control, four screening pairs and 20 confirmation pairs: **720 continuation
arms**. Hypothetical $0.10–$0.50 per arm gives **$72–$360**, excluding recording,
proposal generation, grading/infrastructure and uncertain reservations. These are
arithmetic scenarios, not provider prices, measured costs or spending approval.
Held-out selection without screening uses `2 * held_out_tasks * confirmation_pairs`
plus separately recorded proposal/recording costs. The existing $200 ceiling
cannot be treated as a fresh $200 allocation or silently raised by this protocol.

Increasing pairs on one task improves only the information about that task under
its assumptions; it cannot satisfy a shortage of independent repository groups.
If sample-size/precision, permissions or cost feasibility cannot be established,
keep the study exploratory or narrow the claim. A task count in a synthetic test
is not an approved scientific minimum.

## Verification and release boundaries

`tests/test_natural_failure_protocol.py` checks declared split leakage, provenance
links, exact task-specific evaluator-content leakage, complete identity admission
and missing/changed/unexpected identity fields, deterministic evaluator-control
instability, insufficient independent groups, planned/missing-pair arithmetic and the cost
worksheet. It performs no model or grader sandbox experiment and no customer
access. The fixtures' synthetic review flag cannot authorize real processing.

Internal project-lead/contributor review can accept this engineering contract.
Independent statistical review, human rights/provenance verification, actual
corpus selection, power/precision validation, evaluator threat review, pilot
protocol and funding remain pending gates before confirmatory use. Runtime split
access enforcement, study scheduling, statistical estimation and UI claims are
later implementation tasks, not delivered by this document.
