# Supported investigation workflows

AR-001-A · C01 · Engineering contract ready for review. Buyer interviews and PM
acceptance remain pending; no customer validation is implied. Metrics and pilot
acceptance belong to AR-001-B.

The initial buyer is the team responsible for a coding agent's reliability. The
operator is an agent developer or evaluation engineer. Both workflows use the
native, sequential Python coding environment and the same independent evaluator
for the original run and its branches. Their value hypotheses are less time to
find a useful edit and better evidence for choosing a policy change. These
hypotheses must be tested with permitted customer workloads.

## Workload and entry contract

| Property | Supported boundary |
| --- | --- |
| Execution | One sequential policy issues shell, read_file, write_file or finish actions. |
| Task input | TaskSpec text files, instruction, allowed image identity, evaluator files/command, step/time limits, seed and budget. |
| Restore | The selected tool boundary's /workspace filesystem and complete JSON policy state; image and policy identity must match. |
| Failure eligible for branching | Run status is complete, success is false, branchable is true, and the selected event/checkpoint verifies. |
| Failure not eligible for branching | An interrupted run with status=failed, a redacted restore state, a corrupt chain, missing artifacts, or changed task/image/policy identity. These are diagnostic failures, not replayable task failures. |
| Scope | Controlled Linux Python tasks in one organization's installation; no customer database connection. |
| Output | Parent/branch identity, chosen boundary, intervention, actual and observed results, evaluator outcome and trajectory comparison. Studies add trial accounting and uncertainty. |

A TaskSpec currently allows 1–100 decisions, 1–120 seconds per command, at most
2,000 initial source/evaluator files combined, and an 8 MiB canonical manifest.
Initial files are text, paths are normalized relative paths, and evaluator paths
cannot overlap source paths. Name, instruction, image and evaluator command
limits are 120, 20,000, 300 and 4,000 characters respectively. The fixtures use
30 decisions and 10 seconds per command. Each TaskSpec budget is greater than
zero and at most $200; its example $1 value is illustrative, not a measured cost
or funding authorization. Workspace, output and deployment limits also apply.

Production execution requires an administrator-allowed image pinned by digest,
a compatible worker and the configured isolation policy. The example image is
copied from the current repository configuration; these fixtures do not prove
that it is present, approved in a deployment, or currently vulnerability-free.

## Journey 1: inspect a failure and replace one action

**User and objective.** An agent developer needs to locate a decision that caused
useful work to stop or diverge, and determine whether a concrete edit can repair
the task. The buyer wants a shorter diagnosis cycle, not merely a trace viewer.

**Input example.** `manual-action-recovery` in
[workflows.json](../../contracts/fixtures/workflows.json) requires
`unique_in_order(["b", "a", "b"]) == ["b", "a"]`. The supplied implementation
sorts unique values and fails this requirement. A hypothetical recorded agent
chooses `finish` at decision 1; its tool call succeeds, but the independent
evaluator fails. This distinction prevents a successful tool exit from being
mistaken for a successful task.

**Operator flow.** Open the failed task, inspect the timeline and evaluator
outcome, select decision 1, inspect its pre-action workspace, and submit a
`write_file` replacement containing the order-preserving implementation. The
branch restores the checkpoint, applies the replacement, and continues with the
same policy identity under the branch budget. Compare changed files, decisions,
evaluator result and costs while retaining the original run.

**Executable success.** The fixture's evaluator checks empty input, duplicates
and order. The original source exits 1; the supplied corrected workspace exits
0. A branch earns success only if its final workspace passes this evaluator.
A continuation can still undo the correction or fail; no live outcome is
promised. One passing branch is an example, not evidence of a reliable effect.

**Failure handling.** Missing or invalid restore state blocks branching with an
explanation. Cancellation, provider failure and budget exhaustion remain visible
and must not be presented as an ordinary failed-task outcome. Do not overwrite
the parent or silently alter its task, image, policy configuration or grader.

## Journey 2: locate and evaluate a useful intervention

**User and objective.** An evaluation engineer wants to prioritize plausible
intervention points and learn whether an edit improves completion probability
for a fixed failed prefix. The buyer needs an auditable basis for choosing the
next agent-policy investigation.

**Input example.** `automatic-intervention-evaluation` requires a batching
function to retain its final partial batch. The supplied implementation passes
the visible full-batch smoke test but fails the independent evaluator. In a
hypothetical trace, decision 1 reads the instruction, decision 2 runs the smoke
test, and decision 3 finishes. A candidate replaces decision 2's observation
with a reminder that the passing smoke test does not cover partial batches.
It cites the visible task requirement, not hidden evaluator contents.

**Operator flow.** Inspect the failed task, request ranked intervention
proposals, examine each proposed edit and budget, then run fixed screening.
Compare candidates against unchanged continuations, include a negative control,
freeze the selected candidate before fresh confirmation, and inspect successful,
failed and missing outcomes. If no candidate qualifies, retain that result.
The provided observation is an illustrative candidate; an automatic proposer is
not required to produce it or rank it first.

**Executable success and evidence.** The fixture's original workspace exits 1
and its reference repair exits 0 under the independent evaluator. Editing an
observation does not itself apply that repair. A real continuation must produce
it or another correct implementation. The observation edit keeps the original
shell action's actual filesystem effects and actual result while changing only
what the policy observes. A branch can therefore still fail.

The study estimand is completion-probability change conditional on this task,
checkpoint, policy, image and evaluator. A positive claim requires the frozen
candidate's complete independent confirmation and the declared uncertainty
criterion; all missing pairs and spending remain visible. Screening scores,
one passing replay and advisory provider seeds do not establish a cause, a
stable improvement or deterministic replay. See [research](../RESEARCH.md).
Natural failures, permitted corpus acquisition and task-level generalization
are handled by AR-002; these synthetic examples provide no research result.

## Tool-boundary guarantees and exclusions

A checkpoint is taken before proposing/executing a decision. For an action
intervention, the recorded decision is selected and the replacement action runs
from the saved pre-action workspace. For a tool-result intervention, the
original action's saved post-action workspace and actual result are preserved;
only the observed result changes before policy continuation. Prefix events stay
linked to the parent and are verified when read.

Only supported filesystem state and serializable policy state are restored.
Process memory, running services, background processes, unrecorded policy
caches, arbitrary filesystem objects, external time and external databases are
outside this contract. No network write tool, browser workflow, parallel agent,
additional language, arbitrary framework import or customer database connector
is added by these journeys. A command's processes do not survive a boundary.
Model nondeterminism remains; requested seeds are not reproducibility promises.

Public fixtures contain only original synthetic source with no credentials or
customer data. Evaluator files are unavailable during agent steps and are
mounted read-only for final evaluation. That separation does not make the
simple example graders resistant to malicious candidate code. Their direct
execution during tests is for trusted repository fixtures only, not an approved
way to run user-submitted tasks outside a sandbox.

## Buyer and operator interview guide

Record participant role, permission to retain notes, workflow ID, observed
behavior, timestamp and unresolved objections in private evidence. Do not put
customer source, names, credentials or unapproved quotations in this repository.
No interviews have been performed for this contract.

1. Ask the operator to reconstruct a recent naturally failed coding run and the
   time spent locating the first useful intervention. Which tool/state could
   not be captured, and what fraction of their work falls outside this boundary?
2. Ask the buyer what decision a passing branch would change, and what measured
   effect, uncertainty and investigation time would justify adoption.
3. Ask who owns executable graders and how they detect incorrect passes. Can
   permitted failed tasks be shared with the configured model processor?
4. Ask whether explicit refusal for incomplete/redacted state is acceptable,
   and how abandoned or inconclusive investigations should appear in reports.
5. Ask which isolation, retention, access and deployment obligations block a
   pilot. Establish the operator and security owner without promising a rollout.
6. Ask each workflow's questions in the structured fixture; capture disagreements
   and alternatives before accepting the value hypotheses or pilot metrics.

## Verification and review

The machine-readable examples are synthetic contracts, not recorded model runs.
`tests/test_workflow_contracts.py` checks required journey fields, parses tasks
and interventions against the actual current Pydantic models, checks the chosen
boundary against the task limit, and executes only the trusted example graders
against original and repaired workspaces. It also verifies that the misleading
smoke test can pass while the independent grader fails. No provider, Docker or
cloud call is made by those tests.

TL/BE review covers tool-boundary semantics; QE review covers model validation
and executable fixtures. PM review must confirm that the two journeys reflect
buyer/operator needs and accept their input/failure/intervention/success
examples. That review and subsequent customer validation are pending, not
inferred from an automated check or from backlog approval. AR-001-B consumes
these workflow IDs when specifying measurement and interaction acceptance.
