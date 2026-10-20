# Total-budget evaluation protocol proposal

RA-01-B / proposed C21 · 2026-10-20 · **design only; owner choices pending**

This proposal asks whether a frozen procedure produces more independently
confirmed useful interventions and more recovered tasks within the same total
resource limits. These are separate endpoints. A fresh retry can recover a task
without producing an intervention effect; its intervention endpoint is
**not applicable**, never an invented zero-effect result.

The [accepted prior-method audit](PRIOR_METHOD_AUDIT.md) constrains comparisons
and novelty. The [machine-readable design](../../contracts/research/evaluation-design.json)
contains the decision fields, synthetic arithmetic examples and complete
proposed work cards. No policy, estimator, adapter or experiment is implemented
here. No new funding or data permission is granted. The existing $200 ceiling is
not renewed or increased; PAID0 reconciles any use of the existing allowance; a new natural-failure study
requires its own STUDYFUNDS0 funding decision and remaining-funds evidence.

## Authority and proposed owner gate

Internal review may accept C21 as a **design artifact**. That alone must not
unlock C08/C09 producers. Add a proposed zero-effort owner decision gate,
**RESEARCHSCOPE0**, dependent on RA-01-B, before both AR-020-A and AR-024-A.
The execution ledger records this pending gate separately. The gate
requires an actual dated owner decision tied to the accepted C21 digest covering:

- Baselines and information strata, including whether optional adapters are selected.
- Practical thresholds to take into calibration, with permission to narrow scope
  if those thresholds prove infeasible.
- Exact approved follow-up IDs, estimates and exclusions; an empty expansion set
  is a valid explicit choice.
- Nested-protocol disposition: retain current C02, or authorize only guarded
  engineering design for the proposed replacement.
- Recorded independent internal design review.

The JSON gate is a synthetic pending-decision template, not the live approval
ledger. Its all-pending values remain unchanged when source review is recorded
in delivery evidence. Actual gate decisions belong to the execution ledger with
dated evidence; a fixture boolean or delegated interpretation is not owner sign-off.
Until these inputs are recorded, the gate is pending and consumer design readiness
is false even if C21 is marked reviewed. The gate does **not** require completed
AR-024-C/AR-026-A calibration before C08/C09 can be designed; that would create a
cycle. It also does not substitute for the later independent statistical review,
C02 execution amendment, DATA0, STUDYFUNDS0, production or operator gates.

Current [C02](../delivery/NATURAL_FAILURE_PROTOCOL.md) prohibits held-out
outcome screening. It remains authoritative. This proposed nested evaluation
cannot run until a versioned replacement receives explicit execution approval,
with independent statistical review and permitted-data/funding gates. Merely
approving a schema that can represent discovery does not permit such discovery.

## Population, endpoint and denominator contract

Freeze eligibility before method outcomes: permitted natural task failures,
verified capture/restore, stable independent evaluator, supported native sequential
coding environment and original baseline budget policy. Keep the original
baseline-attempt inventory, including successes and pre-assignment exclusions.
Record failures by C02 taxonomy; injected failures demonstrate mechanics only.

Use the same assigned eligible tasks for every applicable method. A method that
cannot propose, exhausts its budget, lacks a supported checkpoint or encounters
an outage does not get to delete its task from the assigned denominator.
Post-assignment permission revocation is retained as an unobserved/withdrawn
assignment, with no further processing; it is not silently replaced.

| Quantity | Definition and interpretation |
| --- | --- |
| Conditional frozen-edit effect | For one fixed task/checkpoint/edit, Delta = E[Y_edit - Y_no_edit] under the frozen paired continuation distribution. It is not a unique causal-fault claim or a population estimate. |
| Paired harm probability | H = P(Y_no_edit=1, Y_edit=0) under the declared pairing/coupling. This discordance risk depends on that coupling; do not call it an identified individual causal-harm probability. |
| Distinct-task confirmed yield | Number of assigned tasks with one candidate meeting its predeclared fresh-confirmation net-benefit and validity gates, divided by all assigned tasks. At most one credit per task and method. A failure to certify is not proof of no effect. |
| End-to-end recovery | Fraction of assigned tasks with a valid successful final artifact produced by the frozen procedure within its cap. Include fresh retries and successful discovery attempts. Keep operationally missing outcomes unknown. |
| Cost/resource outcomes | Full method-attributable one-shot costs and actual physical charges, plus tokens, CPU, elapsed time and concurrency separately. Primary comparisons use fixed caps; actual spend is also reported. |

Report complete task counts: confirmed, no candidate, no effect, harm, inconclusive,
missing, invalidated, exhausted, cancelled and unsupported. These labels need an
explicit priority plus the full fault vector; do not add overlapping labels as
though they were disjoint counts. Publish successes/failures/missing denominators
for recovery separately from confirmation dispositions.

For recovery with S valid successes, F valid failures and U unknown outcomes,
report [S/N, (S+U)/N], N=S+F+U, alongside any labeled complete-case rate.
For example, three recoveries, one failure and one missing task give [0.6,0.8].
Pure fresh retry has that valid recovery result and a not-applicable intervention
yield. An all-missing method is not assigned zero true success probability.
Discovery success may count as observed recovery but never as confirmed effect.
For recovery, the eligible artifact pool comprises every charged, valid
discovery, treatment, no-edit control and fresh-retry continuation produced by
the frozen procedure. Select the first independently successful artifact in a
precommitted ordering of assigned attempt IDs, only after any sealed confirmation
plan reaches its terminal barrier. Do not reveal confirmation results early to
extend search. A control success earns recovery credit, never intervention-effect
credit. The same selection rule applies across applicable methods; all-missing
or invalid graders cannot manufacture a recovered artifact.

## Frozen policy and nested evaluation proposal

Split by repository family, task/derivative family and task-specific evaluator
content; related patches and generated variants stay together. Freeze the split,
sampling weights and population before evaluation. Generic container/command
identities may be shared as C02 permits; copied task-specific grader content may
not cross the boundary. Exclude outer holdout from training, prompt tuning,
candidate-library construction and preprocessing.

The proposed first design allows **within-task adaptation only**. Each held-out
task gets a predeclared cap; costs or outcomes from one held-out task cannot change
another task's policy, proposal pool, cap, order or stopping rule. Unused task
budgets are not transferred. Cross-task adaptive portfolios require a separate
batch/episode sampling and inference design and are outside this proposal.

Within an outer held-out task, a frozen policy could read only the registered
task input, factual prefix and designated task-local discovery outcomes/cost
receipts. It must not read hidden expected answers in the answer-blind stratum,
other held-out task outcomes, or any confirmation result. This permission is a
**proposed replacement**, not an exception to current C02.

Freeze the policy/model/adapter/prompts, evaluator, image/tools, checkpoint/event
chain, allowed-observation schema, price revision, resource caps, selection rule,
family allocation and fixed sample plan. Every decision receipt identifies its
allowed input receipt IDs and their project/study/method/task/policy-run scope, frozen policy digest, policy state digest, chosen
candidate/action and budget quote. A restarted coordinator must reconstruct the
same decision, not invent a new policy run.

Select at most one candidate per (method, task) for confirmation, then freeze its edit,
checkpoint and sample-plan digests. Confirmation uses fresh disjoint attempts,
predeclared paired assignments and the same validated snapshot. A provider seed
is not assumed to guarantee identical random numbers; register the actual pairing
and provider-fingerprint policy. No discovery outcome is reused as a confirmation
observation. No confirmation feedback, outcome-driven replacement, sample-size
extension or early success stop is permitted. Operational abort produces an
explicit incomplete/inconclusive plan, preserving holds and denominators.

## Budget and cost contract

Use integer USD micros for monetary admission and separately bounded resource
coordinates for calls, tokens, CPU, time and concurrency. No conversion from a
sample count to a fictional measured price. Before every potentially paid action,
require a conservative quote from a pinned price schedule and enforceable request
bounds, including maximum output/continuation and grading. Unknown pricing or
unbounded requests fail closed.

Keep two ledgers linked by immutable IDs:

1. **Actual physical charges:** unique invoices/calls/reservations against the
   authorized study account. A shared artifact generated once has one physical
   charge, not several fabricated invoices.
2. **Method comparison costs:** predeclared attributable input costs plus that
   method's execution. A common proposal pool costing 30 is charged 30 to each
   compared method that would need it, although only 30 was physically invoiced.
   Never divide its cost by the number of methods or give shared inputs away.

Count baseline capture, diagnosis, proposals, restoration, replay, grading,
confirmation, failures, uncertain calls and method-specific offline preparation.
Common provider pretraining is outside the experimental cost boundary for every
method; additional method-specific training/indexing is inside it. Record excluded
external costs explicitly. Primary one-shot cost includes all attributable
offline preparation. Secondary amortized scenarios use an advance-fixed reuse
denominator, retain the unamortized total and never determine actual cash
authorization. Do not choose the reuse denominator from successful outcomes.

Global closure is required before task admission:

- Method: offline attribution + shared attribution + sum(frozen task caps)
  <= method total cap, in every applicable resource coordinate.
- Physical account: settled + held (including uncertain) + protected confirmation
  reserves <= actual authorized account cap.
- Task/method/project/study hierarchy: every applicable cap must admit atomically;
  checking only one level is insufficient.

For intervention-producing methods, a fixed complete confirmation plan is
reserved **before admitting candidate search**, including its independent grader and worst-case call bounds. A percentage
alone is not proof the sample plan is affordable. Pure recovery-only controls (fresh retry or unchanged continuation) have no
intervention confirmation reserve. They may use their full matched recovery cap
under the frozen retry, grading and stopping policy; no fake reserve handicaps
them. The quote still includes all grading costs. Intervention-producing methods
spend part of that same cap on certification and expose this tradeoff.

Discovery can consume only
settled/held headroom remaining after that protected reserve. Confirmation
dispatch transfers reserved funds into held funds; it does not create extra
headroom. Do not count uncertain charges twice: uncertain is a subset of held.

Synthetic units illustrate the transition: cap 100, settled 20, held 15 (including
uncertain 10), reserve 25 leaves 40 for discovery. Quote 41 refuses. Moving 25 from
reserve to a confirmation hold keeps exposure 60 unchanged. A timeout retains
the hold. An evidence-backed final charge 18 releases only 7; append its receipt
without changing the logical call, phase, candidate or sample identity.

Late reconciliation must reference the original reservation and evidence. Never
rewrite prior selection receipts or treat a newly observed bill as knowledge the
policy possessed earlier. A charge above its quote records the actual amount,
freezes further dispatch and marks a budget breach; it is not clipped to the
quote. Outcome corrections after publication require a versioned report/invalidation
trail. They do not authorize reopening the frozen search or silently repairing
an earlier comparative claim.

## Comparison and reuse contract

Start with unchanged continuation, fresh restart, random eligible location,
latest-error and a frozen heuristic, plus equal allocation over a common proposal
pool. Match model capability/revision, permitted context, sampling policy,
environment/evaluator and all resource caps within a stratum. Equal budgets need
not imply equal rollout counts. Report candidate generation, ranking/allocation
and final confirmation as separate components.

DoVer and CAR remain conditional adaptation candidates under C20's release,
rights, native restoration and estimand constraints. DoVer's released proposer
and REFLECT's primary protocol use answer information; either grant matched
oracle access to every comparator in a separate oracle stratum or label an
answer-blind adaptation. REFLECT requires an author artifact or explicit
paper-adaptation fidelity decision. DAAF's persistent-asset/fresh-start experiment
is a separate study, not a silently substituted checkpoint baseline.

Recommend successive halving as the first standard calibration comparator against uniform
allocation using identical proposals and reserves. Established allocation, cost
awareness and feature sharing are not novel merely because their receipts are
stored here. This common-pool ablation isolates allocation, whereas the end-to-end
method benchmark permits different proposer pipelines or no proposal pool under
matched model/information/resource limits and fully charged costs. A fresh retry
does not purchase an unused intervention pool. No superiority or new algorithm
is claimed by this design.

A reusable repair/policy claim additionally needs a development-frozen repair,
new repository/task families and a preregistered regression cohort including
previously successful tasks. Freeze their permission, success/harm thresholds
and task weights independently. Do not transfer a repair selected using a task's
confirmation into the same held-out claim. Persistent-asset changes and their
training/amortization remain a separate DAAF-like scope decision.

## Statistical choices and explicit feasibility failure

Propose, **pending owner choice and independent review**:

| Owner choice | Recommendation | Practical consequence / unresolved risk |
| --- | --- | --- |
| Core comparisons | Uniform allocation, unchanged continuation, fresh retry, random/latest-error/frozen heuristic; successive halving as the first standard calibration comparator. | Same inputs/caps, separate proposal and allocation effects; no allocation novelty claim. |
| Optional adapters | Gate DoVer/CAR on rights and native fidelity; defer REFLECT/DAAF runtime scope. | Missing artifacts produce an explicit limitation, not an invented benchmark score. |
| Information | Answer-blind primary comparison; oracle-assisted runs only in a separately approved matched stratum. | Hidden answers cannot advantage a single proposer. |
| Useful isolated edit | Family-adjusted conditional net-effect lower bound greater than +0.10. | Ten percentage points is an initial practical target, not a measured user requirement. |
| Harm and reuse | Report paired H descriptively with its coupling. For a reusable repair, require regression-cohort net-completion lower bound at least -0.02. | A separate predeclared previously-successful cohort uses fresh original-policy controls; its one historical success is not p=1. No reuse claim is needed for every isolated edit. |
| Error / precision | Family alpha 0.05, target power 0.80 for calibration, primary population interval width at most 0.20. | These are design goals, not achieved guarantees; insufficient evidence is inconclusive. |
| Nested access | Authorize guarded engineering design only; keep current C02 execution restrictions until replacement approval. | No held-out outcome access from approving this document. |
| Follow-up scope | First review core contracts, controls, exporter and calibration; select optional adapters separately. | Every named PR and its overlap-adjusted effort needs an actual owner decision; evaluation retains separate funding. |

The earlier possible 2% paired-H cap is **not the recommended universal gate**.
Under independent continuations, control success 0.5 and edit success 0.6 imply
Delta=+0.10 yet H=0.20; even two identical 50%-success policies have H=0.25.
More samples do not solve that mismatch. A common provider seed does not
establish the necessary coupling. The recommended reuse margin concerns
*marginal net completion* on a separately frozen regression population, preserves
task/repository clustering and adds its endpoint to the planned claim family.
Isolated-edit confirmation requires net benefit and validity, not an unvalidated
reuse or broad safety claim.

Freeze a finite family covering every planned method-by-task benefit claim, each
selected reuse/regression claim, and every primary population contrast. A simple
conservative proposal assigns alpha 0.025 to task/reuse confirmation and 0.025 to
population contrasts, then divides each allocation across its full predeclared
family. For example, four methods on ten assigned tasks plus two reuse claims
reserve 42 confirmation claims even if only seven candidates are selected;
three planned population contrasts retain a divisor of three. These are
allocation examples, not implemented intervals or a power guarantee.
Unselected/failed tasks do not shrink that family. The general union-bound
rationale does not require independent tests, but individual interval validity
still needs a justified sampling model. The estimator and precise allocation
belong to C09 and external review; do not reuse an ANOVA formula for binary paired
effects. [NIST's general Bonferroni inequality](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm)

The familiar 100 failures, 10 repositories, 60/40 split and 30 pairs are **calibration
placeholders, not power guarantees or approved minima**. Split fractions apply to
repository families before outcomes, not arbitrary task rows; six development
and four test repositories give very few independent held-out groups. Repeating
one task 30 times does not create 30 independent tasks or repositories.

If the owner nevertheless selects an optional paired-H cap, even 30 independent
pairs with zero harms give unadjusted one-sided 95% upper bound
1 - 0.05^(1/30), approximately 0.095. A 0.02 cap needs at least 149 all-no-harm pairs
before multiplicity, and tighter family alpha needs more. This binomial inversion
assumes independent identically distributed indicators. It is a caution about
that nondefault gate, not a power calculation or evidence that 30 pairs can meet
the recommended net-effect/regression targets.
[NIST exact binomial construction](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)

C09 must separate task-conditional intervals from population inference. Population
comparisons preserve pairing across methods and task nesting within repository
families; reports show task-weighted primary counts and predeclared repository
weighting sensitivity. Few clusters, unstable graders, drift or uncalibrated
missingness block broad population claims. Complete-case estimates are labeled
conditional; missingness bounds and invalidated cohorts remain visible.

AR-024-C and AR-026-A must examine development-only null coverage, selection,
discordance, clustering, drift, multiplicity, missingness and measured resource
costs. Freeze sample size and operational stop/invalidation rules only after
calibration with declared error tolerances. If the sample cannot support the
target within approved money/data, narrow the claim, defer the study or record
an exploratory/null result. Do not infer affordability from the existing $200
ceiling or invent external statistical approval.

## C08/C09 handoff and execution ordering

C08's original producer **AR-020-A** must review the additional fields listed in
the JSON: scoped study/task/policy/decision identities; frozen artifacts and
allowed observations; logical calls/attempts/lease generations and reservation IDs; prices, quotes,
reserves, physical invoices and comparison allocations; phase/seal and linked
reconciliation history. Keep C04 idempotency, scope, uncertainty and fencing
semantics. No new public endpoint or runtime schema is added by this document.

C09's original producer **AR-024-A** must review endpoint applicability,
denominators, paired assignment/coupling, planned hypothesis family, missingness,
interval validity/invalidation, clustering and dual-cost reporting. Its output
must reference the same frozen C08 identities; a discovery receipt cannot be
presented as independent confirmation.

Proposed ordering: RESEARCHSCOPE0 precedes RB-01 and RB-04; accepted original
C08/C09 and runtime foundations remain prerequisites. Accounting and sealing
precede control/allocator integration. Rights/fidelity inspection RB-07 can run
in parallel after the owner gate; actual optional adapters await native restore,
evaluator review and controls. Export and calibration-harness work can proceed in parallel
once their inputs exist. Evaluation waits for both plus corpus, statistical,
funding and data gates; AR-038-C still independently reviews any claim.

The offline checker validates only record completeness, proposed dependency
ancestry, document/card parity and deterministic synthetic accounting/phase
examples. It does not validate statistical coverage, owner approval or runtime
implementation. Its allocation-only common-pool example requires the same model, information,
proposal-pool identity and all resource caps; changing one allocator alone refuses.
That example does not impose identical proposer pipelines on the end-to-end benchmark.

The following PR scopes are **outside the active 433-day DAG**. Each card names
its effort relation: producer/existing-scope amendments estimate the proposed PR,
with overlap against the mapped base task still to reconcile; optional new
adapters/allocation work is net-new scope; study replacement cards replace the
selected existing study rather than fund a second run. These ranges are not
automatically incremental additions to 433. Reconcile remaining base effort and
earlier adaptation ranges before owner approval. A map to an existing task identifies the
integration owner, not permission to bypass that task. Each PR remains disabled
until its actual dependencies and applicable owner conditions pass. REFLECT and
DAAF runtime work remain deliberately unestimated/unselected pending artifacts
and separate scope.

### RB-01 — Version C08 resource and decision receipt extension

- **Objective:** Make selection and total cost independently attributable.
- **Scope / independent PR:** Add proposed identities, allowed-observation references, physical/comparison cost ledgers and reserved-confirmation transitions to the original C08 producer's schema/fixtures.
- **Out of scope:** No database implementation or provider dispatch.
- **Dependencies:** RESEARCHSCOPE0, RA-01-B, AR-012-B, AR-010-B, AR-002-B. Integration owner: AR-020-A; original prerequisites remain.
- **Contracts:** C02, C04, C20, C21, C08; producer acceptance is not granted here.
- **Acceptance:** Producer review accepts same-study identity closure and immutable phase/price/resource fields; a schema fixture cannot mark C08 available.
- **Automated tests:** Reject cross-study calls, missing price bounds, reused phase attempts and changed policy digests.
- **Security / reliability:** No source/secret bodies in receipts; uncertain dispatch keeps holds.
- **Effort / confidence:** 2–3 engineering days, low; producer_amendment.
- **Estimate overlap:** Proposed PR scope total overlaps the mapped producer; reconcile its remaining estimate before assigning any net increment.
- **Responsible / reviewers:** BE; TL, QE
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-02 — Enforce protected reserves and attributable shared costs

- **Objective:** Prevent discovery from consuming confirmation funds or hiding shared input costs.
- **Scope / independent PR:** Extend the existing study ledger with atomic reserve-to-held conversion and distinct shared-input attribution; retain actual invoice uniqueness.
- **Out of scope:** No new payment integration, automatic refunds or new scheduler.
- **Dependencies:** RESEARCHSCOPE0, RB-01, AR-020-B, AR-010-B, AR-023-C. Integration owner: AR-020-B; original prerequisites remain.
- **Contracts:** C04, C08; producer acceptance is not granted here.
- **Acceptance:** Concurrent discovery admits only within every task/method/physical cap; settlement and uncertainty preserve exposure.
- **Automated tests:** PostgreSQL concurrent reserve, duplicate invoice, shared-pool charge, over-quote settlement, lost callback and idempotent late-reconciliation tests.
- **Security / reliability:** Freeze breached accounts; never cap a real invoice down to its quote.
- **Effort / confidence:** 3–5 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** BE; TL, QE
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-03 — Seal task-local selection and confirmation receipt access

- **Objective:** Keep adaptive discovery independent of fresh confirmation.
- **Scope / independent PR:** Add frozen task-local policy state, receipt manifests and confirmation access barriers to the existing coordinator; independent execution generations cannot reuse analytical attempts.
- **Out of scope:** No cross-task adaptive allocation, new estimator or changed confirmation sample size.
- **Dependencies:** RESEARCHSCOPE0, RB-01, RB-02, AR-021-A, AR-023-C. Integration owner: AR-021-A; original prerequisites remain.
- **Contracts:** C08; producer acceptance is not granted here.
- **Acceptance:** Only designated discovery receipts are visible; one candidate/task freezes once; confirmation stays sealed until its fixed plan completes or invalidates.
- **Automated tests:** Crash/restart at freeze, confirmation-to-discovery leakage, task-state sharing, stale generation and partial-confirmation negatives.
- **Security / reliability:** Unknown calls remain held; operational abort is explicit inconclusive, not early success.
- **Effort / confidence:** 2–4 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** BE; TL, QE
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-04 — Extend C09 endpoints, multiplicity and denominator contract

- **Objective:** Separate intervention evidence from retry-inclusive product recovery.
- **Scope / independent PR:** Specify task-conditional effects, paired harm, distinct-task confirmed yield, recovery bounds, planned hypothesis family and repository-cluster reporting in C09 fixtures.
- **Out of scope:** No estimator implementation, power claim or held-out outcome access.
- **Dependencies:** RESEARCHSCOPE0, RA-01-B, RB-01, AR-020-A, AR-002-B. Integration owner: AR-024-A; original prerequisites remain.
- **Contracts:** C02, C08, C09, C21; producer acceptance is not granted here.
- **Acceptance:** Pure retry has not-applicable intervention yield and valid recovery; no missing task or unused hypothesis slot disappears.
- **Automated tests:** Tiny wins/harms/ties/missing tables, duplicate task credit, insufficient clusters, unused family slots and first-success-only bias cases.
- **Security / reliability:** Independent statistics review before estimator/evaluation acceptance.
- **Effort / confidence:** 2–3 engineering days, low; producer_amendment.
- **Estimate overlap:** Proposed PR scope total overlaps the mapped producer; reconcile its remaining estimate before assigning any net increment.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-05 — Add fair retry and common-input controls

- **Objective:** Make inexpensive controls competitive on the recovery endpoint.
- **Scope / independent PR:** Extend existing random/latest-error/heuristic controls with unchanged continuation and fresh restart; use the same permitted information/model/resource vectors and common proposal attribution.
- **Out of scope:** No published-method adapter or adaptive allocator.
- **Dependencies:** RESEARCHSCOPE0, RB-03, RB-04, AR-025-B, AR-014-C. Integration owner: AR-025-B; original prerequisites remain.
- **Contracts:** C08, C09; producer acceptance is not granted here.
- **Acceptance:** Retries receive task-recovery credit; shared proposals are charged equally; identical caps do not imply equal numbers of rollouts.
- **Automated tests:** Answer-access mismatch, unequal call caps, zero/free shared pool, invalid checkpoint and independent grader tampering negatives.
- **Security / reliability:** Untrusted proposals pass existing action/environment/evaluator restrictions.
- **Effort / confidence:** 2–4 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-06 — Implement the proposed successive-halving allocation comparator

- **Objective:** Measure allocation value without changing the proposal pool.
- **Scope / independent PR:** Implement owner-approved successive halving over frozen candidates with within-task updates and immutable resource receipts; compare against uniform allocation.
- **Out of scope:** No novel-algorithm claim, learned cross-task policy or optional confirmation stopping.
- **Dependencies:** RESEARCHSCOPE0, RB-05, AR-024-C, AR-025-A. Integration owner: AR-025-B; original prerequisites remain.
- **Contracts:** C08, C09; producer acceptance is not granted here.
- **Acceptance:** Uniform and selected adaptive policy share inputs and confirmation reserve; caps cannot be borrowed across tasks.
- **Automated tests:** Fixed synthetic candidate ordering, ties, missing rewards, exhausted reserve, partial receipts and deterministic policy-replay tests.
- **Security / reliability:** No confirmation or other held-out task outcomes enter policy state.
- **Effort / confidence:** 3–5 engineering days, low; net_new_optional_scope.
- **Estimate overlap:** Not present in original baseline scope; still unapproved and not added to active estimates.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** Owner approves this calibration comparator; threshold-aware alternatives remain separately scoped
- **Status:** Proposed; implementation authorization false.

### RB-07 — Resolve DoVer artifact, rights and information mapping

- **Objective:** Decide whether an honest DoVer adaptation can be built.
- **Scope / independent PR:** Inspect an exact author release or declare the missing evaluator substitute; freeze license obligations, serial edit mapping and oracle/answer-blind strata.
- **Out of scope:** No baseline execution, copied code or runtime adapter.
- **Dependencies:** RESEARCHSCOPE0, RA-01-A. Integration owner: AR-025-A; original prerequisites remain.
- **Contracts:** C20, C21; producer acceptance is not granted here.
- **Acceptance:** Reviewer accepts a fidelity manifest or records unavailable disposition; unresolved rights block copying.
- **Automated tests:** Static required-artifact/license pin and asymmetric-oracle negative fixtures.
- **Security / reliability:** No untrusted pickle loading; public release access is not code-execution permission.
- **Effort / confidence:** 1–2 engineering days, low; net_new_optional_scope.
- **Estimate overlap:** Not present in original baseline scope; still unapproved and not added to active estimates.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-08 — Implement bounded DoVer coding adaptation

- **Objective:** Compare targeted diagnosis under an explicit coding adaptation.
- **Scope / independent PR:** Translate one approved serial instruction/edit path into existing native replay; emit fidelity/oracle and measured-cost receipts.
- **Out of scope:** No multi-agent platform reproduction, author evaluator replacement without review or public-source ingestion.
- **Dependencies:** RESEARCHSCOPE0, RB-07, RB-05, AR-015-C, AR-018-C. Integration owner: AR-025-B; original prerequisites remain.
- **Contracts:** C08, C09, C20; producer acceptance is not granted here.
- **Acceptance:** Every trial restores the verified native state; oracle access and altered semantics appear in reports.
- **Automated tests:** Restoration equality, edit mapping, ground-truth access restrictions, no-op/irrelevant edit and missing artifact tests.
- **Security / reliability:** Keep answer-blind and oracle strata separate; preserve third-party notices.
- **Effort / confidence:** 3–6 engineering days, low; net_new_optional_scope.
- **Estimate overlap:** Not present in original baseline scope; still unapproved and not added to active estimates.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** DoVer rights and evaluator/fidelity manifest accepted; Freeze exactly one adapter interface/path; an unsupported fidelity gap stops work for re-estimation
- **Status:** Proposed; implementation authorization false.

### RB-09 — Implement bounded CAR resampling adaptation

- **Objective:** Compare checkpoint resampling rankings without mislabeling estimands.
- **Scope / independent PR:** Bind per-trial environment restoration to the pinned contrastive-ranking interface; retain original factual-reference output and separate common confirmation.
- **Out of scope:** No Shapley expansion or surrogate-environment substitution.
- **Dependencies:** RESEARCHSCOPE0, RB-05, AR-015-C, AR-018-C. Integration owner: AR-025-B; original prerequisites remain.
- **Contracts:** C08, C09, C20; producer acceptance is not granted here.
- **Acceptance:** Actual filesystem state resets independently; factual-reference ranking is not exported as a paired-effect estimate.
- **Automated tests:** Dirty-state carryover, observation/action semantics, rank provenance, deterministic no-effect and paired-control separation checks.
- **Security / reliability:** License text/notice completeness must be resolved before reuse.
- **Effort / confidence:** 3–6 engineering days, low; net_new_optional_scope.
- **Estimate overlap:** Not present in original baseline scope; still unapproved and not added to active estimates.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** CAR rights completeness and adaptation fidelity accepted; Freeze exactly one adapter interface/path; an unsupported fidelity gap stops work for re-estimation
- **Status:** Proposed; implementation authorization false.

### RB-10 — Export recomputable phase and dual-cost evidence

- **Objective:** Let another reviewer recompute comparisons without private source.
- **Scope / independent PR:** Extend existing safe export with scoped receipt hashes, allowed observation manifests, all denominators and both actual/attributable cost views.
- **Out of scope:** No partner trace publication or export of model credentials.
- **Dependencies:** RESEARCHSCOPE0, RB-03, RB-04, RB-05, AR-025-C, AR-023-C. Integration owner: AR-025-C; original prerequisites remain.
- **Contracts:** C08, C09; producer acceptance is not granted here.
- **Acceptance:** Independent verifier detects missing receipts, phase reuse, wrong shared charges and duplicate credit.
- **Automated tests:** Tampered/refused/missing records, late adjustment links, permission revocation and reproducible aggregate arithmetic.
- **Security / reliability:** Export minimizes source and preserves private permission boundaries.
- **Effort / confidence:** 2–4 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** QE; TL, QE
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-11A — Extend the development calibration harness

- **Objective:** Determine whether a funded confirmatory claim is feasible.
- **Scope / independent PR:** Extend the existing development-only calibration harness with selected-policy, multiplicity, clustering, missingness and cost-sensitivity cases; freeze the review pack before use.
- **Out of scope:** No held-out tuning, paid trials or guarantee from nominal sample counts.
- **Dependencies:** RESEARCHSCOPE0, RB-04, RB-05, RB-06, AR-024-C. Integration owner: AR-024-C; original prerequisites remain.
- **Contracts:** C02, C09, C21; producer acceptance is not granted here.
- **Acceptance:** Independent review accepts the harness and declared error tolerances before feasibility conclusions; no held-out tuning.
- **Automated tests:** Development synthetic null/harm/heterogeneity/missingness regressions with declared Monte Carlo error; protocol leakage negatives.
- **Security / reliability:** No primary threshold changes after held-out unsealing; any revision needs new data/protocol.
- **Effort / confidence:** 2–4 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-11B — Review calibration evidence and freeze the feasibility decision

- **Objective:** Determine whether a funded confirmatory claim is feasible.
- **Scope / independent PR:** Run the reviewed development harness and independently review its evidence; freeze sample, threshold and affordability decisions or explicitly narrow/block the claim.
- **Out of scope:** No held-out tuning, paid trials or guarantee from nominal sample counts.
- **Dependencies:** RESEARCHSCOPE0, RB-11A, AR-026-A. Integration owner: AR-026-A; original prerequisites remain.
- **Contracts:** C02, C09, C21; producer acceptance is not granted here.
- **Acceptance:** Independent reviewer accepts tolerances and affordable sample or explicitly narrows/blocks the claim.
- **Automated tests:** Recompute evidence hashes, null/coverage summaries, sample/cost arithmetic and immutable protocol identity.
- **Security / reliability:** No primary threshold changes after held-out unsealing; any revision needs new data/protocol.
- **Effort / confidence:** 1–2 engineering days, low; existing_scope_amendment.
- **Estimate overlap:** Proposed PR scope total may replace or extend work already estimated in maps_to; no net increment claimed until overlap review.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** No extra condition beyond stated prerequisites and gates.
- **Status:** Proposed; implementation authorization false.

### RB-12A — Freeze the approved study execution manifest and preflight

- **Objective:** Produce evidence for a bounded claim or a documented null result.
- **Scope / independent PR:** Review the exact corpus/method/sample/budget/permission manifest and pre-dispatch checks as a separate PR before any paid dispatch.
- **Out of scope:** No study execution, new spending authority or broad research claim.
- **Dependencies:** RESEARCHSCOPE0, RB-10, RB-11B, AR-038-A, AR-026-C, STUDYFUNDS0, DATA0. Integration owner: AR-038-A; original prerequisites remain.
- **Contracts:** C02, C08, C09; producer acceptance is not granted here.
- **Acceptance:** Actual owners and independent reviewer accept the immutable execution manifest; every funding/data/protocol prerequisite is linked.
- **Automated tests:** Fail missing or changed permission, funding, estimator, sample, artifact, price and receipt identities.
- **Security / reliability:** Actual study funding is separate from design approval and existing $200 ceiling.
- **Effort / confidence:** 1–2 engineering days, low; replacement_study_scope.
- **Estimate overlap:** Replaces the selected study scope in the mapped AR-038 task; never authorizes a second baseline-plus-amendment study or automatically adds its full estimate.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** Reviewed amended C02 execution permission if inner holdout discovery is used; All selected optional adapters accepted; Independent statistical approval and actual funding record
- **Status:** Proposed; implementation authorization false.

### RB-12B — Execute the approved study and publish its private evidence report

- **Objective:** Produce evidence for a bounded claim or a documented null result.
- **Scope / independent PR:** Execute only the accepted manifest and preserve every attempt/charge; produce the recomputable private report for separate AR-038-C review.
- **Out of scope:** No open-ended follow-up, automatic spending increase or public customer-data release.
- **Dependencies:** RESEARCHSCOPE0, RB-12A, AR-038-A, AR-026-C, STUDYFUNDS0, DATA0. Integration owner: AR-038-B; original prerequisites remain.
- **Contracts:** C02, C08, C09; producer acceptance is not granted here.
- **Acceptance:** Frozen reports include failures, no proposals, invalids, uncertain costs and retry recoveries; claims await AR-038-C.
- **Automated tests:** Pre-dispatch permission/funding/identity checks, immutable plan, exhaustive receipt accounting and independent report reproduction.
- **Security / reliability:** Actual study funding is separate from design approval and existing $200 ceiling.
- **Effort / confidence:** 3–6 engineering days, low; replacement_study_scope.
- **Estimate overlap:** Replaces the selected study scope in the mapped AR-038 task; never authorizes a second baseline-plus-amendment study or automatically adds its full estimate.
- **Responsible / reviewers:** RS; TL, QE, independent statistical reviewer
- **Definition of done:** Scoped PR has independent source review, required automated evidence, immutable contract/version links, updated operator/recovery documentation and a recorded gate disposition. No actual study or expanded authority follows from synthetic checks.
- **Additional conditions:** Reviewed amended C02 execution permission if inner holdout discovery is used; All selected optional adapters accepted; Independent statistical approval and actual funding record
- **Status:** Proposed; implementation authorization false.

## Bounded verification and open decisions

The offline validator checks design invariants, example arithmetic, phase/source
separation, owner-gate closure and dependency/card completeness. Its small
deterministic oracles are specification examples, not a scheduler, estimator,
runtime simulation, authorization service or proof of statistical validity.
Separate synthetic frozen plans bind scoped attempt registration and the full
method/task/reuse/contrast inventory. Their digest consistency checks catch
relabeling or truncation of derived examples; they are not signatures, production
seals or evidence that an owner approved a plan.
Tests must run using the pytest console entry point with PYTHONPATH unset and
file-based checker loading. No study data, model calls or new dependencies are
needed.

Owner choices remain baseline/stratum selection, thresholds to calibrate, nested
protocol disposition and expanded PR scope. Independent reviewers must still
accept estimator/sample feasibility, artifact fidelity and eventual research
claims. C20's unavailable artifacts, unproven feasibility of net-benefit/regression margins,
few independent repositories and unknown real costs are the highest risks.
Independent internal source-review dispositions are recorded with the delivery
revision, separately from the synthetic gate template. No named external or
customer approval is invented.

2026-10-20 internal review: B accepted accounting/interfaces and C accepted scientific/design-example boundaries at exact source d84eb0e. Both independently reran 150 design tests; C added nine refusal probes. The lead verified the combined 219-case audit/backlog/design set after integration as 99ab2c6. Hosted acceptance is pending. These internal dispositions do not satisfy the owner decision, independent statistical, data or study-funding gates.
