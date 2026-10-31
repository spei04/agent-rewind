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

## Private recorded walkthrough

The separate recorded-view helper reuses the current workbench with finite, reviewed
private responses. It shows the October 6 controlled fault injection above, including
the unsuccessful controls and eight confirmation pairs executed at that time. It
does not run a model, repair, evaluator, worker or new confirmation trial.

After independent review of the private response manifest, run in the existing cloud
checkout (keep this foreground session owned and time-bounded):

~~~sh
.venv/bin/python scripts/recorded_walkthrough.py --recording /absolute/private/path/response-map-dashboard-v3.json --port 8081 --browser-port 18081
~~~

Use an owned SSH tunnel with local forwarding
127.0.0.1:18081 to remote 127.0.0.1:8081, then open
[the private recorded workbench](http://127.0.0.1:18081/). The helper binds loopback only,
preloads an owner-readable response map, checks exact viewer-asset hashes and refuses
all mutations and routes outside that finite recording. It does not start the
production API or change its migration-only readiness/authentication policy.

Acceptance requires a persistent recorded/read-only notice with source and scope
available in Recording details; recorded failed and repaired trajectories, checkpoint
contents, all eight control/treatment pairs and uncertainty; unavailable editing
actions; and server-side write refusals. The $36.567974 historical reservation across five jobs is distinct from an
unknown bill or available balance. The $1.668527 usage-derived ceiling covers only
67 recorded calls and excludes three proposal calls. New provider calls are zero.
Original exports stay private and unchanged; derived responses need redaction review
before viewing. Any external sharing remains a separate decision.

The first private browser acceptance passed on 2026-10-31 (Pacific), following
the preview restart at 16:57:33 UTC. Lead verified the failed D3 finish and pre-action
invoice.py, parent comparison, the treatment's D3 write and repaired D4 file,
and an unsuccessful control's evaluator assertion. All eight control/treatment
pairs, the interval and scope were readable. The full-width historical/source/cost
notice and RECORDED badge were visible, with mutation controls disabled.
The earlier layout finding was corrected in the private served overlay; on-disk
workbench assets were unchanged at that checkpoint. That acceptance covered the private
recorded view, not a fresh execution, deployed service or public release.

At the user's request, the later dashboard uses a plain black-and-white layout,
compact run rows with short IDs, simple headings and expandable Recording details.
The final private browser check passed at viewer source `ef7a0bd8` after the
17:27:44 UTC restart on 2026-10-31 (Pacific). It verified D3 files before action,
the treatment's repaired D4 file, eight confirmation pairs and interval, and the
failed control's actual 2292 versus expected 2334 evaluator result. Compare retains
decisions, action fields, file modes and text diffs. The unchanged control shows
equal 420 modes and “No text differences.” without inferring a change.

The scoped UI, authority and recording checks cover 66 cases per interpreter
(Python 3.11 and 3.12). Each Compare correction ran only its six affected renderer
cases; the other 60 retain unchanged-source applicability. The original test-host
failure, layout finding, omitted comparison details and misleading change labels
remain retained. Bundle `9c9260d2` changes only viewer/asset metadata; all 183
recorded responses remain identical. The private preview expired at its scheduled
18:27:44 UTC deadline on October 31; both listeners and owned processes were
verified absent. The code and recording remain saved, with zero new provider calls.
This is historical controlled evidence, not fresh confirmation, live readiness
or a public release.

## Private F3 component checks — 2026-10-31

These engineering checks are separate from the recorded dashboard and research
results. Private source `137bb2bc` adds original inspection and expiry alongside
completion. Fifteen focused SQLite cases per interpreter passed before the
row-count correction (30 originals); two affected positives per interpreter
passed on corrected source (four further passes). The other originals retain
their reviewed source applicability, not new-source execution credit.

At aligned source `4df33d67`, one fresh restricted PostgreSQL completion passed
on each interpreter. Stable producer grants preceded genuine claim and dependency
observation; the public F2 observer still refused those writer grants. Independent
checks verified the exact native state/evidence delta, timestamp, digests,
ciphertexts, event consumption and clean commit acknowledgment. Both completions
used 483 of 512 Work units, with elapsed samples below one second. Source,
environment and database/role baselines were preserved; PostgreSQL and test
processes were stopped and reaped.

The original row-count refusal and the separate pre-native launcher refusal remain
retained. These PostgreSQL positives do not cover original inspection, expiry or
cancel=true. Earlier independent SQLite ACK/cleanup outcomes remain scoped to
`131e6bc0`.

A later native phase at `78855715` passed eight SQLite and ten PostgreSQL cases on
each interpreter. It covers uncertain commit/cleanup outcomes, changed native
owner/generation/origin, replaced transaction bodies, and PostgreSQL transaction
identity and INSERT-permission refusal. Independent review verified full native
state, consumed events, source/environment preservation and complete process
cleanup. All 36 cases passed without skips.

Composition `48fb0e91` preserves that runtime and oracle. It also includes the
reviewed strict-value tests (36 new cases per interpreter on their own source)
and installed-smoke preparation; the latter has only source/static validation.
The [remaining assignments](ASSIGNMENTS.md#assignment-history) cover reconciliation,
service-key/legacy paths, deferred constraints and actual competing writers.
Full F3 delivery, installed-package execution, live startup and production
acceptance remain incomplete.

## Historical live procedure

The following describes the historical live procedure; current migration-only
readiness does not enable it.

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
