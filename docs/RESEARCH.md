# Intervention studies

This document describes current fixed-screening/fixed-confirmation mechanics.
The [roadmap research program](PLAN.md#7-research-and-evaluation-program) separates
those mechanics from the proposed budget-aware selection study and records
prior-work overlap. Repeated replay and intervals are not a novelty claim;
no baseline superiority or generalization result has been demonstrated.

The [prior-method audit](research/PRIOR_METHOD_AUDIT.md) is complete. The
[total-budget protocol proposal](research/TOTAL_BUDGET_PROTOCOL.md) defines the
accepted design; the separate [owner decision overlay](research/OWNER_DECISION_2026-10-20.md) records approved core engineering choices and retained execution gates. It does not change the current
mechanics below or authorize held-out adaptive screening.

## Estimand

For a fixed task, observed prefix, checkpoint, policy configuration, image, and
evaluator, estimate the change in completion probability when one action or
observation is replaced. The result is conditional on that observed failure;
it is not a claim about general agent reliability or the unique cause of failure.

## Protocol

1. Rank decisions using visible errors, repeated actions, and workspace changes.
   These scores are an inexpensive proposal mechanism, not measured effects.
2. Ask the configured policy for alternative actions at up to three locations.
   Proposals see the saved context and the fact that the run failed, not hidden
   evaluator source. Reject unchanged proposals.
3. Add an unchanged observation as a negative control.
4. Evaluate each candidate with a fixed number of control/treatment pairs.
5. Select the eligible candidate with the largest conservative lower effect bound;
   break ties by earlier decision. Screening estimates remain exploratory.
6. Persist the winning intervention and its digest before confirmation starts.
7. Run a fixed, fresh confirmation batch with a disjoint seed range.

Each pair gets a trial identifier and randomized execution order. When the model
supports seed requests, both arms receive the same requested seed. Provider seed
support does not establish deterministic sampling or guarantee common random
numbers after contexts diverge. If seeds are unavailable, pairs still share the
same saved prefix and run close together in randomized order.

## Statistics

Let W be pairs where treatment passes and control fails, H the reverse, and N
the number of complete pairs. The estimated effect is `(W - H) / N`.

Compute exact Clopper–Pearson intervals for `P(W)` and `P(H)`, each at 97.5%
coverage. Subtract opposite endpoints. By the union bound, the resulting effect
interval has at least 95% coverage under the independent-pair sampling model.
It is deliberately conservative and remains nonzero-width at the boundary.

The exact two-sided discordance test conditions on `W + H` and tests equal win
and harm probabilities. It is descriptive on screened candidates. Confirmatory
interpretation belongs to the one frozen candidate evaluated on fresh trials.

Pairs with unavailable outcomes remain in the report. For M missing pairs out of
T attempted/planned pairs, report the sensitivity range
`[(W-H-M)/T, (W-H+M)/T]`. Missing outcomes or incomplete confirmation prevent an
"improvement supported" claim. Budget exhaustion is not a stopping rule for a
positive conclusion.

## Threats to interpretation

- Selection on a failed run limits generalization. Evaluate a predeclared corpus
  of tasks before making aggregate reliability claims.
- The proposal policy can favor interventions suited to the observed trace.
  Independent confirmation controls selection of a lucky continuation, not
  overfitting to the underlying task.
- Model versions and provider routing can change. Record returned model and
  fingerprint fields; request pinned models where possible. The service does
  not currently stratify confirmation by provider fingerprint.
- External time, randomness, and concurrency can affect shell tools. This is a
  constrained execution experiment, not a bit-for-bit record of the universe.
- A weak grader yields weak evidence. An immutable file is not proof against
  adversarial test evasion. Use graders designed for the threat model.
- Runs that fail before a complete pair are not silently converted to ordinary
  task failures. Missing-outcome analysis makes that distinction visible.

No model reliability benchmark result is bundled with this release. Test fixture
policies validate the mechanics and are never used by the application worker.

## Proposed context and model comparisons

The [dated amendment](research/CONTEXT_SELECTION_AMENDMENT_2026-10-19.md) audits the actual proposer and proposes checkpoint context, diverse hypotheses, separate critique, model-tier and budget-allocation ablations. Current policy remains as described above. Repository inspection at the allowed checkpoint is distinct from development-only cross-task memory. Factual-suffix diagnosis is a separately gated arm and cannot enter replay history. These are proposed methods, not measured improvements.
