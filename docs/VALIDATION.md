# Live integration validation

On 2026-10-06, the service completed a live model run, restored a failed branch,
automatically proposed interventions, and finished a separate confirmation
phase. This is a controlled fault-injection integration test, not a benchmark
of naturally occurring agent failures.

Implementation: `05fd44b`. The
[CI run](https://github.com/spei04/agent-rewind/actions/runs/37415445488)
passed 48 core tests, including PostgreSQL concurrency checks, and three Linux
gVisor integration tests. Linting, type checks, JavaScript syntax, and package
builds passed too.

## Configuration

- Model: `gpt-6-astra`, high reasoning, 8,192 maximum completion tokens.
- API: Chat Completions returning validated JSON actions; actual responses
  reported the `default` service tier.
- Input: a conservative 128,000-token bound checked before dispatch.
- Task: [`invoice-task.json`](../examples/invoice-task.json), with a 30-decision
  allowance and eight independent evaluator cases.
- Live sandbox: Docker/runc on macOS, with the explicit development opt-in.
  Linux gVisor execution was verified separately in CI.
- Seed support: disabled. Trial seeds schedule paired experiments and arm order;
  they do not make live model responses deterministic.

The provider returned the model label `gpt-6-astra`. A dated snapshot was not
advertised in its model documentation at validation time, so future executions
are not guaranteed to use identical model weights.

## Procedure and results

The original agent repaired the task in five decisions and passed all eight
evaluator cases. A manual branch replaced decision 3, the repair action, with
`finish`. That branch failed the evaluator. The original successful run was
preserved.

Automatic investigation proposed three different actions and included an
unchanged-observation negative control. Each candidate received two screening
pairs. The intervention at decision 3 was selected and frozen before eight
fresh confirmation pairs began. The same model configuration was used throughout.

| Phase and intervention | Control passed | Treatment passed |
| --- | ---: | ---: |
| Screening: decision 2 | 2/2 | 2/2 |
| Screening: decision 3, early stop | 0/2 | 2/2 |
| Screening: decision 1 | 2/2 | 2/2 |
| Screening: unchanged-observation negative control | 2/2 | 2/2 |
| Confirmation: frozen decision 3 intervention | 0/8 | 8/8 |

The selected replacement wrote a corrected `invoice.py`; subsequent agent
decisions ran tests and finished. All planned confirmation outcomes were
observed. The estimated improvement was 100 percentage points, with a
conservative 95% interval of **15.65 to 100 percentage points** and a two-sided
exact discordance p-value of **0.0078125**. Screening observations were excluded
from that estimate.

Earlier unchanged continuations could recover because branching resumes fresh
agent decisions after the fork. They do not automatically reproduce the later
injected stop. The unchanged continuation at decision 3 executes that stop and
therefore fails. This distinction is why both arms must start at the same boundary.

The jobs reserved $36.57 in total, below the $200 validation limit. Reservations
include conservative input and maximum-output allowances and are not a provider
billing total. Raw traces and credentials remain private; the published results
contain aggregate outcomes only.

## Reproduce the workflow

1. Configure a model-backed worker and start the API as described in the README.
2. Record the invoice task and inspect the completed run. Its outcome is not
   forced, and its exact decision sequence may differ.
3. If it succeeds, branch at the decision that repairs `invoice.py` and replace
   that action with `{"tool":"finish"}`. Verify that the independent evaluator
   rejects the resulting workspace.
4. Investigate that failed branch with two screening pairs, eight confirmation
   pairs, and seed 600. Preserve the selected candidate before confirmation.
5. Export the study JSON and inspect both arms, missing outcomes, policy identity,
   and the confirmation interval. Do not substitute a successful single replay
   for the completed paired study.

This test establishes that the live execution and experiment pipeline works for
this controlled case. It does not establish diagnostic accuracy across real
repositories, naturally occurring failures, or other model versions. A broader
failure cohort and deployment smoke tests for the adopter's identity provider,
storage, and worker infrastructure remain necessary.
