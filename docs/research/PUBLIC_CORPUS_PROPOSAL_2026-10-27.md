# Public coding-failure corpus and field-routing proposal

2026-10-27 · **PROPOSED** · save and independent review only

This document proposes a public-corpus route for the first Agent Rewind study.
Saving or reviewing it authorizes no preparatory implementation, data acquisition,
native recording, held-out access, model call, paid study or production resource.
Cloud access is not approval. The actual owner decision requested below is limited
to a future preparatory engineering amendment; it has not been made.

The reviewed repository base is
[`fc3ba44bfaf5a1c03937006b59a720f654e322da`](https://github.com/spei04/agent-rewind/tree/fc3ba44bfaf5a1c03937006b59a720f654e322da).
The approved machine backlog, PLAN, execution statuses,
[owner decision](OWNER_DECISION_2026-10-20.md), C21 design and historical evidence
remain unchanged. In particular, full F3/P1 remains open and product P2 remains
Not started. This proposal supplies no additional completion credit.

## Decision and research purpose

The proposed first corpus is a pinned, initially Python-only subset of
SWE-rebench V2, with new prospective native recordings of ordinary agent attempts.
A real GitHub issue is not itself an agent failure. A published conversation is
not a resumable checkpoint. Only a captured, compatible, naturally failed run
with a qualified independent evaluator can enter the failure population.

The research question remains whether a frozen experiment-selection procedure
finds more independently confirmed useful interventions under the same total
resource budget. Automatic interventions, repeated replay and confidence intervals
are not themselves a novelty claim. Product reliability, one conditional repair
and a population-level research improvement are different claims.

Public tasks can remove dependence on partner task supply for this particular
research route. They do not replace enterprise pilot operations, partner
permissions, security acceptance, statistical review or production readiness.

## Corpus recommendation and evidence limits

| Source | Proposed role | Limits and rights checks |
| --- | --- | --- |
| [SWE-rebench V2 pinned card](https://huggingface.co/datasets/nebius/SWE-rebench-V2/blob/10483de0f50fe5da545942705a76c6150171af7f/README.md) and [official tooling](https://github.com/SWE-rebench/SWE-rebench-V2) | Primary task source; initially Python-only, with independently qualified tasks and new native agent recordings. | Real issue/PR-derived tasks and reproducible image recipes are useful starting points, not proof of correct grading or checkpoint fidelity. Dataset CC BY 4.0 and tooling MIT do not replace the underlying repository/task/artifact obligations. The card excludes original SWE-bench repositories but does not claim exclusion of every other benchmark. |
| [SWE-bench Verified](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified) and [official harness](https://github.com/SWE-bench/SWE-bench) | Calibration and comparison fixtures. | A public static benchmark has substantial exposure risk; human review does not prove absence of contamination or all evaluator faults. Check the exact dataset/task/repository rights. Harness code licensing does not grant rights to every task or trace. |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith) and [task card](https://huggingface.co/datasets/SWE-bench/SWE-smith) | Synthetic engineering and negative controls. | Generated faults are not the headline natural-failure population. Record the exact language-specific dataset revision and separate task/code/trajectory rights. |
| [NVIDIA Open-SWE-Traces](https://huggingface.co/datasets/nvidia/Open-SWE-Traces) | Optional failure-pattern exploration on development material only. | Trace selection and cleaning can bias the population. Messages and resolved flags do not supply filesystem/process snapshots. Do not ingest reference patches or reuse a transcript as a native restore record. CC BY 4.0 at the dataset layer does not settle all underlying rights. |

The pinned SWE-rebench V2 README was read in memory: **6,629 bytes**, SHA-256
`a20de363f2179078a503c49a09247f84b8c96bc8979d420cad6fcbd84a021205`,
dataset revision `10483de0f50fe5da545942705a76c6150171af7f`.
Review used dataset cards and repository metadata; no task dataset files, images
or models were acquired, and no tasks were admitted or executed. Incidental
landing-page previews were not used as study data. Other sources are options for
later separately pinned qualification, not admitted corpus entries. Future split
and contamination qualification must account for incidental reviewer exposure;
no exposed task is automatically eligible for sealed evaluation.

License review must distinguish the dataset compilation, repository at its base
commit, issue/PR text, patches/tests, container and bundled dependencies,
tooling, and generated traces. Preserve attribution and required notices.
Unknown or incompatible rights quarantine a task; a public URL or SPDX label is
not approval. The public-source route still requires approved processors,
purpose, storage, retention and any intended redistribution separately.

## Eligibility and prospective acquisition

1. Freeze the intended population, supported workload, ordinary baseline
   agent/model/configuration, attempt/seed allocation, limits and exclusion rules
   before outcomes. Keep every attempted baseline: successes, natural failures,
   capture faults, infrastructure faults, evaluator faults and unknown outcomes.
   Do not search seeds or lower budgets until a preferred failure appears.
2. Pin dataset revision/task identity, exact base commit, source materialization,
   platform-specific image digest, harness/parser/command, evaluator artifacts
   and the field-routing policy below. Image tags and branch names are not
   immutable identity. Image and source contents require qualification as well
   as identity.
3. Resolve rights and provenance, including forks, mirrors, shared issues,
   patches and task-specific evaluator copies. Group related material before a
   repository-family split. Held out from this study does not mean unseen during
   model pretraining. Report exposure uncertainty.
4. Qualify the evaluator in clean, separate execution contexts. The exact
   original candidate must fail; the known reference repair must pass; a known
   invalid candidate and a tampering control must fail or be rejected according
   to the frozen taxonomy. Current C02 starts with at least three repetitions
   per control as an engineering check, not a statistical guarantee. Bind tests
   actually executed, parser outcomes and resource errors; exit code alone is
   insufficient. Preserve flaky, missing and wrong results and quarantine the
   affected task.
5. Generate new ordinary baseline runs under the reviewed native recording path.
   Record exact model/tool context and actual versus observed effects. Public
   issue data or external trajectories cannot manufacture native run/checkpoint
   IDs. A pre-recording candidate record is a different type from an admitted
   recorded corpus entry.
6. Verify supported state capture and restore at the intended tool boundary:
   source/workspace bytes, modes and paths, agent state/configuration, image,
   tool policy and event chain. Unsupported process memory, open sockets,
   external services or other uncaptured state makes the task ineligible.
   Unchanged control behavior and state checks cannot be selected for a
   favorable repair result.
7. Freeze candidates before independent confirmation; retain unsuccessful and
   harmful interventions. Equal-budget baselines include unchanged continuation,
   fresh retry, random location, latest error and a frozen heuristic under the
   accepted design. Report retry recovery separately from intervention yield.
   Optional prior-method adapters remain subject to their own rights, fidelity
   and owner gates.
8. Account for all costs: task/image acquisition and storage, qualification
   controls, baseline recording, diagnostic reads, proposal/critique calls,
   screening, fresh confirmation, graders, CPU/memory, failed/uncertain calls,
   retries allowed by protocol, and cleanup. No free shared proposer or hidden
   evaluation pool may advantage a method.

A small development eligibility exercise, for example 10–20 tasks under a
separately approved cap, could estimate failure yield, resource use and exclusion
rates. It is a proposed feasibility step, not a powered sample or permission to
run. No actual source row has yet been shown to meet this proposal.

## Matched controls, confirmation and feasibility

The approved comparison constraints remain: match model revision, permitted
information, evaluator and resource budgets. Compare unchanged continuation,
fresh retry, random admissible location, latest error and a frozen heuristic
under predeclared allocations. Fresh retry receives the full recovery cap;
intervention yield is not an applicable metric for that arm. Uniform allocation
and standard successive halving use the **same proposal pool** for the allocation
ablation. If end-to-end methods use different proposers, attribute all proposal
work and report that separate comparison rather than calling the pool controlled.

Reserve the complete fixed confirmation allocation, including independent
grading and worst-case call bounds, before candidate search. Freeze the selected
candidate, checkpoint and sample-plan identities before fresh, disjoint
confirmation attempts. Search/screening receipts never count as confirmation.
No selective retries, successful-subset reporting or threshold changes after
unsealing. Current C02's held-out restriction remains: the candidate is selected
before any new held-out continuation grade; a fully adaptive nested experiment
requires separate approval.

The existing approved **calibration targets**, not achieved guarantees, are a
family-adjusted useful-edit net-effect lower bound **greater than +0.10**, family
alpha **0.05**, calibration power **0.80**, and primary population interval width
**at most 0.20**. Independent statistics and measured development feasibility
must determine whether an affordable design can support those targets.
Illustrative counts such as **100 failures, 10 repositories or 30 pairs** are
template inputs, not a power calculation or minimum sufficient population.
Repeated pairs within a task do not replace independent repository groups.
Infeasibility narrows or blocks the claim; it does not weaken confirmation
after outcomes.

Full costs include offline training/tuning, indexing and preprocessing; task
qualification/acquisition; every retained or discarded proposal and critique;
screening and control runs; failed, missing and uncertain attempts; independent
graders; baseline recording; confirmation; compute/storage/network and cleanup.
Offline costs cannot be hidden outside the comparison simply because incurred
before the timed run. Record the prespecified attribution/amortization rule and
report both total and online costs.

Keep physical billing separate from per-method attribution. Record shared
physical calls/resources once for invoice reconciliation; disclose their
allocation or charged comparison cost to each method so shared work is not a
free advantage. Attributed comparison totals must not be described as additional
physical invoices. Report human preparation, annotation, review and operations
effort separately, including the conversion rule if monetized. No missing or
uncertain charge is silently zero.

A conditional feasibility screen is:

`O + 2 * T * M * n * c <= reconciled allocated funds`

Here T is the task count, M the compared methods requiring paired confirmation,
n the fresh pairs per task/method, c the assumed all-in cost per continuation
arm, and O all other allocated costs and uncertainty/reserve obligations.
For 10 tasks, four methods and 30 pairs, confirmation alone has **2,400 arms**.
Even a hypothetical untouched $200 ceiling permits at most **$0.08333
(8.33 cents) per arm before every other cost**. This is arithmetic, not a price,
available balance, sample approval or new authorization. Actual remaining
allocated funds are unknown until reconciliation; O and other obligations
reduce this allowance. An average-cost worksheet cannot replace bounded
reservations and stop rules before dispatch.

The proposed result would compare only the approved, faithfully implemented
baselines. It would establish no superiority over optional prior-method adapters
that remain deferred, unavailable or semantically unqualified.

## Existing contracts and unavailable prerequisites

[C02 permissions](../delivery/CORPUS_PERMISSIONS.md) and the
[natural-failure protocol](../delivery/NATURAL_FAILURE_PROTOCOL.md) remain
authoritative. Corpus v1 accepts only synthetic/customer-permitted evidence and
requires recorded run IDs. A versioned public-derived admission extension is
needed; never relabel public data as customer-permitted or fabricate run IDs.

The public-source operating supplement would replace C17 only for the proposed
public AR-038-A/B route. It must retain custody, rights, source/evaluator identity,
run accounting, retention and operating duties. It does not replace the global
customer DATA0/PARTNER0 route, enterprise pilots, G4 or G5.

C06 is still a producer deliverable under AR-014-A. AR-013 sandbox, AR-014
restoration/conformance, G2 and integrated runtime prerequisites are not supplied
by this document. Existing legacy engine/runner code is not acceptance of those
production interfaces.

The pinned legacy TaskSpec uses text-file mappings, at most 2,000 combined
source/evaluator files and an 8 MiB manifest. Engine defaults to a 32 MiB workspace
limit. The adapter must reject unsupported/oversize tasks rather than silently
omit files, enlarge limits or hide mutable source outside captured state.
Native integration is separately reviewable after its contracts exist.

Current C02 permits a frozen held-out procedure to select and freeze a candidate
before seeing any new held-out continuation grade. Qualification/state-fidelity
evidence must remain grade-blind to selection; do not choose tasks for favorable
replay or repair outcomes. Fully adaptive nested held-out discovery is still
unapproved. The C21 engineering decision did not authorize that execution.
Independent statistics, study protocol and funding remain separate.

## Proposed dependency amendment

The following IDs and edges are **proposed only**. They are not inserted into the
approved machine graph, and no existing task is marked complete. An arrow below
means “requires.” The public route adds the stated AR-026-A prerequisite and changes AR-038-A/B
only after a reviewed owner amendment; the customer route and its evidence remain
preserved.

| Proposed node | Requires | Deliverable / gate |
| --- | --- | --- |
| AR-002-C | AR-002-B | Versioned public-derived admission and source-neutral C02 operating supplement; explicit pre-recording candidate type and field policy. |
| PUBLICDATA0 | AR-002-C | Independently reviewed public rights, provenance, evaluator access, processor/purpose/storage and retention decisions. No execution authorization. |
| PUBCAP-A | PUBLICDATA0, G2 | One supported corpus adapter, manifest/custody integration and native acquisition preflight. Pure normalization is only part of this package. |
| CAPTUREFUNDS0 | PAID0, PUBLICDATA0, PUBCAP-A | Separate bounded development and sealed-baseline capture allocations from reconciled existing funds. The sealed phase remains unavailable until the approved AR-026-A decision. |
| PUBCAP-B: development capture | PUBCAP-A, G2, PUBLICDATA0, CAPTUREFUNDS0 | Authorized development-only baseline/qualification evidence and measured feasibility costs; no held-out tuning. |
| AR-026-A: amended prerequisites | Existing AR-024-C, AR-025-B, AR-002-B, AR-024-D; add PUBCAP-B | Independent protocol, sample, threshold, affordability and stopping/invalidation decision. Existing work remains. |
| PUBCAP-C: sealed baseline capture | PUBCAP-A, AR-026-A, G2, PUBLICDATA0, CAPTUREFUNDS0 | Authorized capture under frozen protocol and sealed custody; no adaptive held-out screening permission. |
| AR-038-A: public route | AR-026-A, PUBLICDATA0, PUBCAP-C | Freeze the permitted natural-failure corpus, split, denominator and evaluator identities. |
| STUDYFUNDS0: unchanged requirements | AR-026-A, AR-038-A | Separately approve the actual confirmatory study allocation and feasible claim. |
| AR-038-B: public route | AR-038-A, STUDYFUNDS0, AR-026-C, G3 | Authorized bounded study only after correctness/recovery/statistical acceptance; retain every assigned outcome. |
| AR-038-C: unchanged requirement | AR-038-B | Independent claim, missingness, uncertainty and null-result review. |

The proposed order is development capture → AR-026-A → sealed capture →
AR-038-A. This prevents the cycle that would result from requiring final study
feasibility before collecting any development feasibility evidence. G3 remains
required for actual study execution; it is not required to collect the limited
development inputs needed by AR-026-A. All existing AR-026-A prerequisites remain.

Read-only in-memory review found this proposed extension acyclic. A later
approved amendment must rerun the machine dependency checker and reconcile task
cards, PLAN, EXECUTION_BACKLOG, C02 operating documentation and assignments
together. This save does not change the graph, statuses or aggregate estimates.

## Funding and estimate boundaries

The existing authorization is **up to $200 total**, not a new allocation for this
proposal. Historical **$36.567974 is unreconciled reservation/accounting evidence,
not invoice-reconciled cash spend**. Neither subtracting that number nor observing
cloud access establishes available cash. PAID0 must reconcile invoices,
reservations, uncertain calls and remaining authorized funds before dispatch.

PUBLICDATA0 is a rights/data gate, not a budget. CAPTUREFUNDS0 would approve
specific development and sealed-baseline capture amounts, limits, purposes and
stopping conditions. STUDYFUNDS0 remains a separate confirmatory-study decision.
All draw from the same reconciled ceiling; none automatically renews or adds
$200. If feasible capture and independent confirmation do not fit, narrow/block
the claim or request a separate explicit funding change. No spending is approved
here.

| Provisional incremental parent scope | Engineering days | What is excluded |
| --- | --- | --- |
| Admission/protocol 2–4 plus document/graph reconciliation 1–2 | 3–6 | External rights/owner decisions and statutory/legal advice. |
| PUBCAP-A adapter/manifest/custody 3–5; development capture 1–2; sealed capture 1–2 | 5–9 | Runtime prerequisites, external reviews/waits, actual compute/storage/model charges and a powered-study guarantee. |
| Total proposed increment | **8–15, low confidence** | Calendar promises, parallel staffing assumptions and already budgeted evaluator/statistics/runtime work. |

PCA1 (1–2 days) below refines AR-002-C. PCA2 (2–3 days) refines PUBCAP-A.
These are overlapping details, **not additive estimates or completed parent
packages**. Do not add 3–5 days again or credit savings before remaining native
wiring and review are reconciled.

AR-018-A/B/C already own evaluator protocol, isolated execution/flake handling
and independent attack review (10 nominal days). AR-026-A/B/C already own
feasibility/protocol freeze, distributed crash/resume correctness and evidence
review (10 nominal days). AR-014 owns checkpoint/restore conformance; AR-038-A
already owns corpus curation/freeze. Preserve those tasks and count only the
reviewed corpus-specific delta.

## Smallest preparatory PR package, still proposed

| Package | Scope and acceptance | Required tests — NOT RUN | Owner / estimate |
| --- | --- | --- | --- |
| PCA1 within AR-002-C | Versioned public-source C02 extension; preserve v1 behavior; rights/provenance and private policy references; separate pre-recording candidate record without invented run/checkpoint IDs. A valid declaration is not rights approval. | Schema/runtime parity; v1 compatibility; duplicate/unknown fields; malformed identities and paths; wrong processor/purpose/storage; expired/revoked rights; safe errors. | Engineer A with Engineer C review; 1–2 days, medium confidence, overlapping parent estimate. |
| PCA2 within PUBCAP-A | Pure offline translation of an already supplied, pinned Python SWE-rebench V2 row into distinct typed inference and evaluator manifests. Consume trusted qualification receipts; return explicit next-gate eligibility/quarantine/unsupported decisions. No fetching, image pull, execution or Engine.run integration. | Independently constructed valid and invalid receipts; fail-before/pass-reference/known-invalid/tamper outcomes; hidden-field noninterference; stale receipt refusal; cache identity; secret/answer leakage; unsupported state and denominator preservation. | Engineer A with Engineer B interface and Engineer C review; 2–3 days, medium confidence, overlapping parent estimate. |
| Remaining native PUBCAP-A integration | Bind the accepted adapter to real prospective recording, qualified images, custody and C06 runtime consumers after existing gates. Pure adapter tests do not complete it. | Actual consumer separation, native restore, grader isolation, provenance, resources and interrupted/uncertain execution accounting. | Existing runtime/evaluator owners; re-estimate only the corpus-specific delta after interface acceptance. |

Suggested future code boundaries are one public-corpus contract module/schema,
one SWE-rebench V2 normalizer and their focused tests. These are not present
interfaces or authorization to add files now. A preparatory path must remain
disabled/unconnected until the appropriate integration gate passes.

## Field-routing annex: default deny

A/P/S means the executing agent, intervention proposer and selector. A denial
covers raw values and derived summaries, critiques, embeddings, rankings,
features, identifiers and inserted history. Q is an isolated qualification
custodian applying frozen rules; E is the isolated evaluator; O is trusted
operational orchestration. Q/E/O access is not model-context permission.
This is an information-flow proposal, not implementation of new roles.

The pinned card declares 16 task-level fields, 70 named paths and 65 leaf paths.
The groups below enumerate every known payload path. Parent objects cannot be
passed wholesale merely because one child has an allowed use.

| Field or explicit field group | Agent / proposer / selector | Restricted permitted use |
| --- | --- | --- |
| problem_statement | Qualified instruction only, subject to phase permissions | Q verifies pre-fix provenance and secret/answer contamination. Reject contaminated or ambiguous material, or independently source and pin the original pre-fix issue before fresh capture under a new qualified identity. |
| repo, base_commit, instance_id | Deny supplied metadata | Q lineage/revision/deduplication and O exact source binding. Random opaque task/attempt handles must be unrelated to answer/source. |
| patch, test_patch, FAIL_TO_PASS[], PASS_TO_PASS[] | Deny | E-only reference repair, immutable tests and controls. Controlled Q rights/lineage/evaluator review is allowed; gold-derived ranking is not. |
| pr_description, interface | Deny | Sealed Q lineage and answer-contamination review only. Never merge into instructions, critique or location ranking. |
| image_name | Deny supplied name/tag | Q environment provenance and O platform-specific digest resolution; qualify all transitive contents. |
| install_config | Deny aggregate object | Only explicitly routed children below. |
| install_config.base_image_name | Deny | Qualified Q/O build identity. |
| install_config.docker_specs and every child listed below | Deny | Qualified Q/O environment profile; no prompt or tool-feedback passthrough. |
| install_config.install[] | Deny | Q-reviewed O build plan only; never executed by normalization. |
| install_config.log_parser, install_config.test_cmd | Deny | Qualified E configuration, bound to exact parser and command identities. |
| language | Deny supplied label | Q/O frozen eligibility/profile routing; the actual source language remains naturally visible. |
| license | Deny | Q rights review; the SPDX declaration is not sufficient rights evidence. |
| created_at | Deny | Q temporal/lineage qualification only; unresolved string-versus-integer schema ambiguity quarantines the input. |
| meta, meta.llm_metadata | Deny aggregate objects | Sealed Q audit only; route descendants explicitly. |
| meta.llm_metadata descendants listed below | Deny | Sealed Q audit; unused by default eligibility, sampling or ranking. No difficulty/confidence weighting or automatic URL dereference. |
| meta.num_modified_files, meta.num_modified_lines | Deny | Sealed Q audit, excluded from default sampling as patch-derived signals. |
| meta.pr_author, meta.pr_labels[], meta.pr_url | Deny | Q rights/lineage only; no solution lookup, automatic URL fetch or unapproved inference/stratification features. |

Every install_config.docker_specs child is explicitly covered:

- _variant, bazel_version, bun_version, cargo_version, deno_version,
  docker_version, erlang_version, gcc_version, go_version, helm_version;
- java_version, jdk_version, llvm_version, lua_version, luajit_version,
  neovim_version, node_version, npm_version, nvim_version, pnpm_version;
- python_image, python_version, redis_version, ruby_version, rust_version,
  rustc_version, solana_version, sqlite_version.

Every meta.llm_metadata descendant is explicitly covered:

- code, confidence, difficulty, external_urls[], intent_completeness,
  pr_categories[], reasoning, test_alignment_issues[];
- detected_issues (container), detected_issues.B1, detected_issues.B2,
  detected_issues.B3, detected_issues.B4, detected_issues.B5,
  detected_issues.B6.

Unknown fields and every descendant inherit denial. Unknown keys, duplicate JSON
members, aliases, unexpected types/nulls or container shapes quarantine the input.
The README is not a complete runtime schema and does not establish requiredness
or nullability. Do not invent those rules or silently discard unknown content.

The card's created_at feature is a string, while its prose describes integer
milliseconds. Require an explicit versioned interpretation and source-record
qualification; no guessed coercion or assumption that a timestamp proves pre-fix
provenance.

### Permitted context and transitive leakage

A/P/S receive only audited instruction, admitted base artifacts and
phase-authorized authentic native prefix. Naturally present pre-fix source
symbols, filenames, repository names and existing tests remain allowed by
provenance. This is not a keyword ban on test names or a claim of complete model
blindness to repository origin. Do not add source-derived metadata, hashes,
labels, workspace prefixes or IDs as ranking/context side channels.

Qualification must cover everything transitively agent-readable: image layers,
grader/reference files, patches, post-base Git objects, build/setup logs, caches,
environment values and operational path labels. Denying a dataset string while
leaving its answer in an image is insufficient. Keep evaluator material separate;
retain legitimate pre-fix source and tests.

A real native history containing reference leakage is quarantined and retained.
Deleting an answer after capture cannot create faithful history. A redacted
derivative has a distinct identity and cannot inherit branchability, replay
fidelity or an original-context claim. Do not retrofit a safer instruction into
an already captured run; use a new qualified identity and fresh acquisition.

Use distinct typed inference and evaluator manifests. The pinned
[TaskSpec](../../agent_rewind/models.py) co-locates instruction/files with
evaluator_files/evaluator_command: its complete serialization must never become
an inference payload. Q/raw, E and A/P/S require separate authorized views,
sessions, memory and caches. No model sees a hidden grader result merely because
a different operational component needed it.

### Immutable field-policy and cache receipt

A future trusted receipt must bind:

- Dataset/card revision and SHA-256; raw-row hash; source revision and complete
  observed field inventory.
- Field-policy, schema and normalizer revisions/hashes; per-field dispositions.
- Independently valid qualification receipt, reviewer and frozen eligibility
  rules, with rights/processor/purpose/storage/retention scope and revalidation.
- Separate admitted instruction/base/inference-view hashes and private
  evaluator/reference-test identities.
- Qualified platform/image identities and transitive-content review evidence.
- Honest unsupported/missing evidence and the authorized acquisition phase.

The policy receipt is proposed here; no real row qualification receipt or new
policy digest is fabricated. A later approved artifact must bind the exact final
policy bytes and reviewer disposition.

Full raw-row, permission and evaluator hashes remain private. With separately
valid qualification receipts, fixed eligibility and identical admitted context,
changed excluded fields must not change model-visible bytes, IDs, view hashes,
cache keys, errors, seeds, queue allocation, budgets or rankings. A stale receipt
reused after its bound row changes must fail admission; it is not a valid
noninterference comparison.

Any authorized inference/prefix cache must be keyed only by admitted context and
the appropriate model/configuration identity, with opaque operational handles.
A cached model result is not a fresh stochastic trial. Evaluation-result identity
binds complete candidate/test/harness/parser/command/image/configuration plus
distinct control/attempt identity. Cached grades do not satisfy fresh repetition
or confirmation. Revalidate permission and current policy on reuse.

### Annex acceptance tests — NOT RUN

- Inject solution/secret canaries into each excluded leaf, including nested
  lists/containers, and verify no inference projection or derived hint.
- Compare independently qualified hidden-field variants with identical admitted
  context/eligibility: identical model-visible views/hashes/cache identities,
  errors/handles and allocated order/seed/budget/ranking. Private provenance
  identities may change. Separately reject row mutation with a stale receipt.
- Refuse unknown descendants, aliases, duplicate keys, unexpected nulls/types and
  unresolved created_at representations.
- Prevent setup logs, image labels, operational paths and forged parser feedback
  from crossing into inference. Malicious URLs/install/parser strings cause no
  normalization-time fetch, import or execution.
- Changed private gold/test material invalidates evaluator cache identity without
  becoming a model feature. Distinct control and confirmation attempts cannot
  reuse a cached grade as new evidence.
- Reject wholesale TaskSpec/evaluator-manifest serialization at an inference
  boundary and cross-role session/memory/cache contamination.
- Quarantine authentic-history leakage without rewriting or branchability
  claims. Preserve positive cases containing legitimate base-source test names,
  symbols and paths.
- Exercise original fail, reference pass, known-invalid and tamper controls;
  preserve incomplete, flaky, invalid and missing grades and all denominators.

Pure adapter tests demonstrate translation and refusal properties only.
Actual prompt, critique, ranking, cache, error, history and runtime consumers need
their later separately reviewed enforcement evidence.

## Owner decision requested, not recorded

After independent review, the owner is asked to approve or reject only a
**preparatory public-corpus engineering amendment**: reconcile AR-002-C/PUBCAP-A,
the proposed dependency route, versioned C02 supplement and the two bounded
preparatory PR packages. Record any approval in a new versioned decision with
exact scope/identity; do not reinterpret the older owner decision or C21 bytes.

That decision would still not authorize capture, held-out access, paid calls,
dataset/image acquisition, an adaptive nested study, partner data, new resources
or an increase of the $200 ceiling. Public rights approval, qualified runtime,
CAPTUREFUNDS0, AR-026-A, sealed-capture authorization, G3 and STUDYFUNDS0 retain
their separate meanings and sequence.

## Assignment, review and save record

| Date | Role | Bounded assignment and disposition |
| --- | --- | --- |
| 2026-10-27 | Engineer A | Reviewed primary corpus sources and the pinned field inventory; proposed adapter/eligibility boundaries; saved this single proposed review artifact. No task acquisition or implementation. |
| 2026-10-27 | Engineer B | Reviewed dependency order, public/customer gate separation, typed views and estimate overlap. Proposed graph checked in memory; approved graph unchanged. |
| 2026-10-27 | Engineer C | Independently challenged field routing, instruction provenance, transitive leakage, stale receipts and runtime-enforcement limits. Annex acceptable as a proposal with the incorporated clarifications; not execution approval. |
| 2026-10-27 | Project lead | Authorized saving and independent review only. Any later preparatory amendment decision and all execution/funding gates remain separate. |

This artifact's repository review checks are separate from the required future
tests above, which have not run. Exact saved bytes and any documentation/backlog
validation are reviewed before commit/publication. No source, dependency,
approved graph, owner-decision or C21 changes accompany this proposal.
