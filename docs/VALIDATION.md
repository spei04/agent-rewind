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

### Remaining F3 controls

The targeted composed phase has 35 applicable cases per interpreter: 10 pure
mapping checks, 9 SQLite cases and 16 PostgreSQL cases. Python 3.12 retains
17 source-applicable pure/SQLite passes from `9e01a773` plus two corrected
receiver cases at `3bd0fc99`; Python 3.11 has 19 pure/SQLite originals at
`3bd0fc99`. The 16 PostgreSQL cases ran on `3bd0fc99` for each interpreter.
These are separate original groups, not one combined rerun.

The stopped Python 3.12 group first passed conditional-update and competing-writer
checks, then failed while opening an extra SQLite connection without the required
checkout receipt. That failure occurred before the bare or foreign persistence
entry was tested. The original remains retained; the correction only uses the
existing `owned_connect` fixture helper. Runtime, guards and assertions are
unchanged. Both corrected receiver modes now verify refusal, consumed events,
complete state preservation and closed connections.

The SQLite cases cover legacy completion and original inspection, genuine
service-key authority and revocation before terminal writes, wrong organization
or project scope, actual conditional UPDATE refusal, and competing expiry writers.
The winning writer committed one exact evidence identity and timestamp. The
loser returned native SQLITE_BUSY without beginning its transaction and retained
`cleanup_failed=true`; it made no protected write. Only the winner has a clean
commit acknowledgment. Native key rows and authority were tested, not HTTP
authentication.

The PostgreSQL originals passed and were independently reviewed under the
unchanged limits. They cover native expiry/cancel and exact original readback,
legacy and service-key paths, scope refusals, uncertain commits, actual deferred
SQLSTATE `23514`, conditional UPDATE rowcount zero, and competing terminal
writers. A separate native observer proved the blocked-writer relation; one
writer committed one exact evidence row and the loser made no protected write.
Bare and borrowed scopes were refused on distinct idle and active connections.
Source, environments, database/role baselines and private data were preserved;
the database stopped and all owned processes were reaped.

Both original collect-only runs at `1a703ecc` observed the same 9,198 ordered
IDs: all 8,988 previous IDs remain in order, with 210 additions. No test or
fixture bodies ran. Expected skip allowances remain 45 on Python 3.11 (10 early,
35 late) and 31 on Python 3.12; actual CI skip outcomes remain to be verified.

Only the four version count/digest leaves changed in `b9ed477f`. The retained
16 CI controls passed in one original run, and the direct-array validator
matched both inventories and their partitions. Runtime and test definitions
were unchanged by that metadata update. These results do not relabel the
separate targeted native groups or their retained failures.

Configured final checks passed, and [PR130](https://github.com/spei04/agent-rewind/pull/130)
passed all seven required jobs before merging at `f516bc9c`. Original PR
receipts verified the complete inventories, ordered selections and declared
skips. The installed-package check exercised the synthetic SQLite failure path;
loading a PostgreSQL profile did not establish installed PostgreSQL execution.

The original protected-main [run 41241550155, attempt 1](https://github.com/spei04/agent-rewind/actions/runs/41241550155)
then passed all six underlying jobs but failed the required CI gate:

| Core leg | Passed | Skipped | Session seconds | Limit |
| --- | ---: | ---: | ---: | ---: |
| Python 3.11 early | 4,795 | 10 | 1,751.939918 | 2,700 |
| Python 3.11 late | 4,358 | 35 | 1,784.933394 | 2,700 |
| Python 3.12 all | 9,167 | 31 | 3,928.283202 | 3,600 |

The exact overrun was 328.283202 seconds. Independent inspection of the
retained originals confirmed all 9,198 ordered IDs, expected skips and the
7,086 selected terminal phase outcomes. Those outcomes do not override the
elapsed-time failure. Main candidate delivery was skipped; this attempt did
not complete F3. The originals remain retained, and the limits, test inventory
and full Python 3.12 order remain unchanged.

A local comparison of the test-only PostgreSQL snapshot helper passed all
21 old/new observations, including raw input effects. Across two existing
Python 3.12 cases, unprofiled helper time fell from 3.852227 to 0.746533 seconds
and the pytest child from 31.475356 to 28.414980 seconds. This was one
fixed-order comparison; its limited scope does not establish repeatability
or recovery of the full-session overrun.

The shared schema reader at `cbca3810` keeps the existing per-table column
limit before batching the other five PostgreSQL reflection families. Each call
uses fresh connection-bound observations; native guards and SQLite behavior
are unchanged. All 26 focused cases passed on each interpreter: 13 new
PostgreSQL regressions, 10 retained PostgreSQL cases and three SQLite controls.
Independent review checked the original ordered results and state preservation.
Coverage includes the 32/33-column boundary, empty catalogs, invalid reflection
maps, genuine table disappearance, and fresh observations after native changes
and rollback.

An original private SQLite launcher failed before pytest because its input path
still pointed to an earlier preparation directory. That failure has no test
credit and remains retained. A corrected continuation supplied the remaining
four groups; the earlier 23 PostgreSQL passes were preserved. Dependency
reconciliation also remains explicit: two existing Python 3.12 packages were
aligned with the unchanged lockfile before these correctness runs. The earlier
helper comparison retains its original environment qualification.

A subsequent unprofiled comparison ran the old and new schema readers in the
same repaired Python 3.12 environment, with the same optimized test helper.
Across the same two cases, the pytest child fell from 29.370009 to 25.655575
seconds and the combined setup/call/teardown phases from 23.944531 to 20.403707
seconds. All 21 ordered state snapshots matched. Helper timings were 0.785178
and 0.766862 seconds; these measure the test oracle, not the production reader.
The candidate branch, source, environments and database baseline were restored
and verified. This was one fixed-order local comparison, not evidence of
repeatability or recovery of the full CI overrun.

Fresh ordinary collection at source 19abe5ee observed 9,211 identical ordered
IDs on each interpreter. All 9,198 previous IDs remain once and in order; the
13 additions are catalog regressions. No test or fixture bodies ran.
Independent review verified the existing partitions (4,805 / 4,406 / 9,211)
and expected skips (10 / 35 / 31). Only the two count and two ordered-digest
fields changed in the CI baseline. The direct-array validator and 16 retained
CI controls passed; the original analysis and pre-mutation preparation failures
remain retained separately. These are inventory and gate controls, not a
successful full CI session.

The original [PR131 run 41289850037, attempt 1](https://github.com/spei04/agent-rewind/actions/runs/41289850037)
at `1c0572f5` completed all 9,211 ordered outcomes, but failed the required
elapsed-time gate. The Python 3.11 early and late receipts were 1,934.435499
and 1,093.779826 seconds, within their unchanged 2,700-second limits.
Python 3.12 completed 9,180 passes and 31 expected skips; its exact UTC
receipt duration was 3,708.034295 seconds, exceeding 3,600 by 108.034295
seconds. The pytest summary of 3,708.14 seconds is a separate observation.
Independent review verified the original receipts, expected skips and 7,242
selected terminal phase facts. Those facts do not override the duration
failure or establish full F3 delivery.

The receipt validator now rejects a zero interval as well as a negative one.
Its focused boundary regressions cover all three legs, one microsecond (the
smallest positive serialized UTC interval), exact upper limits and one
microsecond over. Timestamp, type, schema, source and outcome rules remain
unchanged. UTC fields remain audit evidence; no monotonic duration is inferred
or synthesized. Fresh inventory and required CI apply to the final composed
correction. Local diagnostic profiles are not measured full-session savings.

A separate fixture-only correction at `651fcb2f` retains all 255 native
provision transactions, current-role observations and per-commit state. It
reuses the unchanged source digest only inside the four exclusive PostgreSQL
capacity fixtures, verifies it before the first provision and again before the
last commit, and leaves generic provisioning and production readers unchanged.

The four retained cases and one new final-source-mismatch regression passed
once on each interpreter. The regression observes 255 real transactions and
254 acknowledged prefixes, refuses the changed final source, and verifies
rollback plus native, Python and ciphertext preservation. All reader time and
transfer limits remain unchanged. Independent review verified the originals
and complete database/process release.

In the matched unprofiled Python 3.12 comparison, the four existing cases'
JUnit times totaled 87.521 seconds before and 48.762 after. The added regression
took 11.005 seconds, leaving a local slice reduction of 27.754 seconds. Python
3.11 has correctness and limit evidence, with no matched timing baseline.
These are emitted JUnit timings from one comparison, not full-session savings
or repeatability evidence. The original 108.034295-second CI overrun and all
session limits remain unchanged.

The fresh SQLite fixture candidate at `996afee8` passed 15 focused controls
on each interpreter. These check independent copies, source and target
ownership, tamper refusal and cleanup. The earlier run with 13 passes and an
exception-note assertion failure remains separate; its later assertions were
not credited until the corrected run passed. The new controls cost 7.736
seconds in Python 3.12 JUnit output and 7.404 seconds on Python 3.11. Their
respective child runtimes were 10.003728 and 9.453193 seconds.

The original `fac9f546` baseline then passed all 102 selected existing cases
once, in 27 fixed groups. Whole-phase durations totaled 270.127504 seconds;
child runtimes totaled 375.578187 seconds. The candidate's first fresh-claim
setup failed the existing native oracle: `PRAGMA foreign_keys` returned
`0`, where the required value is `1`. No candidate case passed and no
later candidate group ran. Durable database equality alone was insufficient:
the copied engine also needs the existing connection configuration. Backend
owns that correction, Quality adds native enforcement coverage, and Review
checks it before continuation.

The original results, source and environment checks, process release and
baseline-to-candidate handoff are retained. Lost SSH responses were recovered
from completed originals without repeating test bodies. The first baseline
release index incorrectly listed itself with an empty-file hash; a corrected,
versioned index excludes itself and preserves that original. This metadata
correction does not change results or costs.

The comparison is incomplete and establishes no SQLite savings or full-suite
margin. The 108.034295-second CI overrun, the session limits and the remaining
F3 delivery gates remain unchanged.

Full F3 acceptance still precedes F4/F5/P2. No new model calls,
public preview, live startup or production acceptance follows from these checks.

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
