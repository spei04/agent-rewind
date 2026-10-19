# Usefulness metrics and interaction acceptance

AR-001-B · C01 · Internal measurement contract for the two accepted
[workflows](WORKFLOWS.md). Targets come from [the roadmap](../PLAN.md). Internal
review is assigned to the delegated project lead; actual partner recruitment,
weekly use, interviews and adoption evidence remain pending PARTNER0/PILOT.
[Metric fixtures](../../contracts/fixtures/usefulness.json) are synthetic.

This document specifies measurements and acceptance cases. It adds no product
instrumentation, user interface, telemetry pipeline or customer evidence.

## Cohort and attempt identity

Register the supported-workload cohort before evaluating capture outcomes. Freeze
its ID, workload eligibility rule, permitted task references, model/adapter and
environment versions, start/end dates and exclusion rationale. Eligibility is
about the declared workload boundary, not whether capture later succeeds. A
failed, abandoned or missing attempt cannot be relabeled unsupported afterward.
Report any genuine classification correction as a cohort revision with both old
and new counts; it cannot silently improve the original cohort's rate.

An investigation case is a particular failed-run diagnosis question; an attempt
is one operator's execution of a measurement arm for that case. Assign distinct
case, attempt, organization and arm IDs. Retries remain linked attempts and are
reported separately; only the predeclared primary attempt per arm enters the
primary timing comparison. Do not choose the best retry. A transport retry with
the same attempt ID must be idempotent. Duplicate or conflicting IDs in analysis
input are rejected instead of counted twice.

Use pseudonymous references in measurement exports. Keep permission documents,
customer identities, raw code, prompts, credentials and proprietary reports in
approved private storage. Export only allowed aggregates and nonsecret evidence
references. Retention and processor permissions follow the deployment/corpus
policy; this contract grants no permission to collect new customer data.

## Capture and restore target

**Target: at least 80%** of the predeclared supported-workload cohort can be
captured and restored without changing product core code.

- Denominator: every registered eligible primary attempt, including capture
  failures, restore failures, abandoned attempts and missing outcomes.
- Numerator: eligible attempts with a persisted capture and a verified restore
  of a declared tool boundary using the supported adapter and deployed core.
  A visible trace, a submitted job, or a successful task alone does not qualify.
- Rate: `verified_capture_and_restore / eligible_registered_attempts`.
- Report unsupported attempts separately with their registered reason and count;
  report total registrations as eligible plus unsupported. Denominator zero
  means insufficient evidence, never 100% success.
- A task that fails its grader may still count as captured/restored. An
  investigation abandoned before restore does not. Runtime interruptions or
  redaction that prevent restore remain failures in the supported denominator.

Record sample size and uncertainty alongside the point estimate; the 80% target
is a pilot threshold, not proof of a population success rate. No minimum capture
sample has yet been approved. Agree and freeze its size and workload strata at
pilot protocol review; passing on a tiny sample cannot establish generality.

## Investigation timing target

**Target: 50% reduction in median active engineer investigation minutes on at
least 20 predeclared cases**, paired against the prior workflow where possible.
The clock starts when the operator opens the failed run for the registered
investigation and ends when a reviewer accepts its intervention report. A report
may conclude positive effect, no effect, harm, uncertainty or no viable
intervention. All are completed investigations when reviewed; a model or tool
error without a reviewed report is not completion.

Record both wall-clock elapsed time and active engineer minutes. Active minutes
sum nonoverlapping intervals spent inspecting, configuring, waiting while
actively troubleshooting, and reviewing the report. Idle compute waits are
excluded from active time but remain in elapsed time. Include reviewer effort;
when people work concurrently sum their active person-minutes. Record pauses
and interval coverage, and reject negative durations, overlapping intervals for
the same person, unrecorded review endpoints or missing duration data. Do not
subtract inconvenient troubleshooting or failed branch attempts.

For paired cases, collect a baseline and Rewind arm for each case. Counterbalance
arm order and avoid teaching the same operator a known repair before measuring
its second arm; independent matched operators or parallel comparable cases can
reduce this learning bias. Freeze the allocation and record deviations.

Let `B` and `R` be median active minutes for the same fully reviewed paired case
set. Report `reduction = 1 - R/B`, the absolute minute difference, sample size,
paired-case distribution and uncertainty. This is a ratio of medians, not the
median of pairwise percentage changes. Baseline median zero makes the reduction
undefined and the target unevaluable; negative times are invalid input.

Every registered case and both arms remain in the report. For failed, abandoned,
not-started or ongoing arms, retain state, observed effort, reason, censoring time
and missing outcome. A median over completed pairs may be shown as **descriptive
only**. The timing target is inconclusive if any registered primary arm lacks a
reviewed report or complete timing, even when the descriptive subset exceeds
50%. This conservative pilot acceptance rule prevents attrition from manufacturing
an improvement. If fewer than 20 cases were registered, evidence is insufficient.
Do not add replacements selectively; any extension must be registered before its
outcomes are observed and retain the original cohort's result.

When pairing is impossible, predeclare comparable workload strata and separate
baseline/Rewind cohorts with at least 20 cases each. Apply the same full-attempt
accounting and report unmatched counts and selection differences. Label the
comparison observational; it cannot support a causal productivity claim. Do not
pool it with paired observations into one percentage. Review bootstrap intervals
or another declared uncertainty method with the research owner before collecting
pilot data; interval selection and pilot sample size are protocol decisions, not
implemented analysis in this task.

## Partner use and adoption target

**Target: two distinct partner organizations use either accepted workflow in
each of four consecutive weeks, and both adopt a resulting regression or policy
fix.** Freeze the two organization IDs and four adjacent seven-day UTC windows
before the observation period. Count a week only when an authorized operator
finishes a reviewed investigation report; logins, page views, empty submissions
and automated health checks do not count. No-effect, harmful and uncertain
reports qualify as use because an honest conclusion can still be useful.

The target requires all eight organization/week cells. Activity by several people
in one organization cannot substitute for the second organization. Late activity
cannot fill a missed week retroactively; record the missed window and any new
predeclared observation period. Keep failed and abandoned attempts in the
weekly report without counting them as reviewed use.

For adoption, record an owner-reviewed repository revision or equivalent accepted
change reference, its regression/policy-fix classification, the source reviewed
investigation, and verification evidence. Both partner organizations need their
own accepted change. A proposal, export, generated patch or positive verbal
reaction is not adoption. A regression arising from an inconclusive investigation
may qualify if actually adopted; it does not turn that investigation into a
positive intervention-effect result.

## Interaction acceptance for both journeys

These are future browser integration requirements; no current accessibility or
end-to-end pass is claimed. AR-027–029 implement and test them against the frozen
workflow IDs and API contracts.

| Interaction | Required observable behavior | Required integration check |
| --- | --- | --- |
| Open and inspect | Run/task status, restore eligibility and refusal reason are text, not color alone. Timeline decisions have stable labels and keyboard navigation. | Keyboard-only inspection and screen-reader labels expose a failed task and an unbranchable interrupted run distinctly. |
| Select a boundary | Focus follows the selected decision; workspace, actual result and observed result have distinct headings. | Move through decisions without a pointer; no selected state or focus is lost while details load. |
| Edit an intervention | Action and observation editors have labels, field errors and an explicit effect description. Observation edits explain preserved filesystem effects. | Submit invalid and valid edits by keyboard; errors are linked to fields and focus reaches the first invalid field. |
| Submit or cancel | Pending state prevents accidental duplicate submission; cancellation has a visible terminal outcome. | Double activation yields one logical operation; cancel/error/retry messages are announced without stealing focus. |
| Compare outcomes | Parent and branch remain distinguishable; pass/fail/unknown outcomes and changed files are readable without a chart or color key. | Navigate comparison and equivalent textual/table evidence using a keyboard. |
| Inspect a study | Screening and confirmation, frozen candidate, missing outcomes, uncertainty and spending are distinct. | Fixture studies with positive, no-effect, harmful, exhausted and incomplete outcomes have accurate labels; incomplete confirmation never shows supported improvement. |
| Export or close | Export includes provenance and uncertainty; dialog closing restores focus to its launcher. | Keyboard export and Escape/close work; polling does not repeatedly interrupt assistive-technology users. |

All interactive controls need visible focus, semantic roles/names and sensible
reading order. No interaction may require dragging, hover-only disclosure or
color discrimination. Loading, authorization failure and empty states must have
plain explanations and a keyboard-reachable next action. Test at narrow layout
and enlarged text without hiding essential results or controls. Existing UI
behavior must be evaluated at implementation time rather than inferred here.

## Verification and remaining evidence

`tests/test_usefulness_contract.py` validates synthetic arithmetic: 80% versus
70% capture with abandoned attempts included, empty denominators, 50% versus
33.3% timing improvement, insufficient samples, failed/abandoned arms and missing
partner weeks/adoptions. It rejects duplicate identities and negative timings.
The tests are contract arithmetic only; they do not verify telemetry, browser
accessibility, interview results or actual adoption.

Internal target/scope acceptance is delegated to the project lead against the
approved roadmap. Partner identities, data permissions, cohort size/strata,
measurement instrumentation, uncertainty protocol and real use/adoption evidence
remain future gate inputs. A missed target triggers a documented product review;
it must not be rewritten as a successful pilot by removing hard cases.
