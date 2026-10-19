# Capacity, ownership and funding decision record

AR-003-B · C03 capacity supplement v1 · 2026-10-19 · planning estimates, not purchase authorization.

Use a small dedicated installation for the first measured workload: separate API, HA metadata, encrypted object storage and two trusted worker hosts with gVisor. Keep admission bounded until CPU, memory, file-object operations, inference latency and provider quotas have been measured together. Preserve the $200 **total validation ceiling**. The current approval authorizes three contributor slots for development/testing; it does not name human production operators, select a production region/IdP, approve recurring cloud charges or increase the model budget.

The existing $1,000–$3,000/month roadmap allowance is plausible only for some small-file assumptions. Repeated unchanged-file uploads can exceed it from object operations alone. Do not approve an operating budget from new-byte growth alone. The [calculator](../../scripts/capacity_estimate.py) and [versioned inputs](../../contracts/fixtures/capacity-budget.json) reproduce the scenarios below without cloud or provider calls.

## Observed facts and unmeasured assumptions

| Evidence | Recorded fact | What it does not establish |
| --- | --- | --- |
| Current source `config.py`, `models.py`, `runner.py` | Default workspace 32 MiB and sandbox memory 512 MiB; maximum 100 decisions, 120-second command and 2,000 initial source/evaluator files; `runsc` production requirement. | Repository-size suitability, peak worker RSS, runtime capacity or sustained throughput. |
| Current `worker.py` and `experiments.py` | Each worker process claims one job; a study executes arms sequentially. | Distributed study fanout, 8/64 live-slot admission or a global tool semaphore. Those require later implementation. |
| Current `web/app.js` | Visible authenticated workbench polls runs/studies/jobs every 4 seconds; a running selected run adds a detail request. | Measured request rate: nominal polling alone is 0.75–1 requests/second per active browser, but hidden tabs, busy requests, actions and trace sizes change load. |
| Current `Artifacts.put` | Local storage skips an existing hash path; the S3 path calls `put_object` every time, even for unchanged content. Each workspace capture traverses every file. | A future GCS adapter's caching/billing behavior. Content-addressed storage does not imply deduplicated PUT requests. |
| Read-only development-host counters on 2026-10-19 | Four visible logical CPUs; MemTotal 16,369,284 kB; about 98 MiB filesystem free at inspection. | Production sizing or performance. The nearly full shared development disk is unsuitable for new builds/downloads/load experiments; no cleanup or disk expansion was performed by this task. |
| Roadmap workload targets | Pilot 20 continuations/hour; forecast 200/hour; assumed 20 decisions, 10-minute mean duration and 16 MiB new stored bytes/continuation. | No load benchmark, customer distribution, natural-failure corpus or p95/p99 latency has been measured for these assumptions. |
| Historical validation record | $36.567974 in reported reservations under the $200 ceiling. | Current live ledger, invoice spend, refunds, remaining provider credits or authority for a new paid study. No private ledger or billing account was read here. |

The full workload envelope and service-level targets remain in [PLAN.md Section 5](../PLAN.md). These calculations clarify assumptions; they do not silently change those targets. The capacity scenario is conditional on later admission/fanout/permits being implemented. Today more parallel work means multiple worker processes, and study parallelism remains limited by its sequential execution.

## Resource and throughput recommendations

| Parameter | First pilot sizing hypothesis | Forecast hypothesis; not committed capacity |
| --- | --- | --- |
| Dedicated workers | 2 × `e2-standard-4` (4 vCPU/16 GiB each), in separate zones where supported | 16 × same type for an illustrative 64 live slots and 32 simultaneous tools; resize from benchmarks before committing |
| Worker process / tool caps | Target 4 live continuation slots and 2 active sandbox tools per host; 8/4 total | Same 4/2 per host; one-host loss reduces permits and requires queueing, not a promise of unchanged throughput |
| Metadata | Cloud SQL PostgreSQL Enterprise HA, 2 vCPU/8 GiB | 8 vCPU/32 GiB HA to price a candidate, not a claim it meets 200 requests/second |
| API | 2 allocated instances, 1 vCPU/1 GiB each, instance-based Cloud Run billing for conservative full-time calculation | 4 × 2 vCPU/2 GiB; autoscaling maximum must fit the DB connection/admission budget |
| Evidence | Regional Standard object storage, 90-day retained scenario and 2× byte reserve | Same assumptions; actual immutability/retention/DR policy awaits C13/ENV0 |
| Restore / sandbox limits | Benchmark supported 32/128/512 MiB workspace classes; keep current default until evidence supports a change | Separate large-task pool only after measured resource contention; no speculative cluster rewrite |

These worker caps are target configuration, not existing implementation. A sandbox tool has a one-vCPU limit, so two concurrent tools reserve room on a four-vCPU host for worker orchestration, encryption, archive handling and gVisor overhead. Four model-waiting continuations still hold Python/workspace memory. Do not multiply only the 512 MiB guest limit: include workspace copies, archive buffers, container/image overhead, all worker processes and the host reserve. Measure peak RSS during capture/restore and fail-closed limits before setting a supported host packing density.

With arrival rate `λ` continuations/hour and mean duration `T` minutes, mean live slots are `λ × T / 60`. Pilot: 3.33 average versus 8 admitted slots. Forecast: 33.33 versus 64. At 20-minute inference-bound duration, forecast average becomes 66.67, already above the proposed cap. Admission must queue/throttle; a faster machine does not cure a provider-latency or tokens-per-minute limit.

Model decisions/minute are `λ × decisions / 60`: 6.67 pilot and 66.67 forecast. Obtain actual requests/minute, input/output/reasoning-token limits, p50/p95 latency and provider throttling before scaling workers. A 32 MiB full restore per decision would imply 3.56 MiB/s pilot or 35.56 MiB/s forecast reads; this is a conservative benchmark pattern, not the current normal loop, which carries workspace state in memory. New artifact bytes average 0.089/0.889 MiB/s respectively under the 16 MiB assumption. Request fanout and burst latency can dominate those modest byte rates.

Use an explicit connection equation before any deployment: `API replicas × bounded pool + workers × bounded pool + coordinators + operator reserve ≤ 70% of observed DB max_connections`. Example pilot candidate: `2×5 + 8×2 + 10 = 36`, requiring at least 52 allowed DB connections before other consumers. Forecast `4×5 + 64×2 + 10 = 158`, requiring at least 226, plus any future coordinator overhead. Current engine creation does not configure these per-process caps; AR-011/033/040 must implement/configure and measure them. No database max_connections value was assumed from machine size.

## Dated list-rate inputs

These are USD on-demand **us-central1 (Iowa) pricing examples checked 2026-10-19**, excluding discounts/free tiers, tax and account-specific terms. This region is a calculation input, not an approved residency decision. Recheck official rates and the chosen edition/region before provisioning.

| Input | Rate and unit | Primary source |
| --- | --- | --- |
| E2 standard worker | $0.13402284 per e2-standard-4 hour; 4 vCPU/16 GiB, disk excluded | [Compute Engine general-purpose pricing](https://cloud.google.com/products/compute/pricing/general-purpose?hl=en) |
| PostgreSQL Enterprise HA CPU | $0.0826 per vCPU-hour | [Cloud SQL pricing](https://cloud.google.com/sql/pricing?hl=en) |
| PostgreSQL Enterprise HA memory | $0.014 per GiB-hour | [Cloud SQL pricing](https://cloud.google.com/sql/pricing?hl=en) |
| Cloud Run instance-based CPU / memory | $0.000018 per vCPU-second / $0.000002 per GiB-second | [Cloud Run pricing](https://cloud.google.com/run/pricing?hl=en) |
| Regional Standard object bytes | $0.000027397 per GiB-hour | [Cloud Storage pricing](https://cloud.google.com/storage/pricing?hl=en) |
| Regional Standard flat-namespace writes / reads | Class A $0.005 per 1,000 operations; Class B $0.0004 per 1,000 | [Cloud Storage pricing](https://cloud.google.com/storage/pricing?hl=en) |

The worksheet uses 730 allocated hours/month and 3,600 seconds/hour. Cloud SQL's HA rates already account for regional HA; multiplying by two again would double-count. API uses full allocated CPU/memory time rather than assuming unmeasured request duty cycles. Object rates are applied to an explicit projected operation count; they are not a bill for current S3 usage. Future GCS mapping must demonstrate its request semantics and any savings. Same-region routing alone does not price all networking: NAT, load balancing, cross-zone/region traffic and export egress still need configuration-specific estimates.

## Artifact operation fanout

Source writer sites are [`Engine.run`](../../agent_rewind/engine.py): pre-decision `put_workspace`, post-decision `put_workspace`, final `put_workspace`, checkpoint/event JSON each step, and task/evaluation JSON; [`Artifacts.put_workspace` and `put`](../../agent_rewind/artifacts.py): one blob put per file plus a manifest, with unconditional S3 upload; [`api.submit`](../../agent_rewind/api.py) and [`worker.work_once`](../../agent_rewind/worker.py): admission payload and job-result objects.

For a complete original run with `D` executed decisions and approximately `F` entries at every capture, existing writer fanout is:

- Workspace writes: `(2D + 1) × (F + 1)` blob/manifest puts.
- Checkpoint/event plus task/evaluation: `2D + 2` puts.
- Conservative admission/result allowance: 2 puts per continuation, even though one study job can share that overhead across arms.
- Total modeled puts: **`(2D + 1) × (F + 1) + 2D + 4`**. File-count changes, failed attempts, retries, extra reads, nesting and importer behavior can change it.

At D=20, F=50 this is 2,135 writes/continuation; F=2,000 gives 82,085. At 20 continuations/hour × 730 hours, those map to **$155.86 versus $5,992.21/month** at the illustrative GCS Class A rate. Both scenarios assume the same 16 MiB new stored bytes. Thus object-operation cost alone can invalidate the old allowance without any increase in retained-byte growth. These are calculated scenarios from observed source fanout, not measured billing.

Read counts are explicit unmeasured allowances of 1,000 or 40,000 operations/continuation, covering branch restoration/history inspection sensitivity. No cache-hit or batch-upload savings are assumed. Whole-file dedup reduces unique retained bytes; it does not remove repeated S3 upload/encryption work. Fernet encoding, many small objects, retained versions and metadata also affect real bytes; the 2× reserve is a planning margin, not a mathematical bound.

**Architecture review item CAP-01:** AR-004-B must freeze what AR-009/015 and the later GCS adapter measure: unique object writes, repeated writes, ciphertext/upload bytes, request counts per capture/restore, corruption checks and ownership lookup cost. Reuse verified objects through a safe indexed publication protocol or bounded packing only after its integrity/concurrency/lifecycle contract is reviewed; no undocumented HEAD-per-blob optimization, skipped integrity check or assumed free cache. AR-032 must account for references/GC before any format changes. Use measured amplification to reprice before recurring funding approval.

## Bounded monthly scenarios

All rows assume continuous arrival at the stated rate for 730 hours. Bytes are steady-state 90-day retained totals, not the first-month average. A 24-hour day is used for retention volume; monthly operation counts use 730 hours. Pilot evidence: `20 × 24 × 16 / 1024 × 90 × 2 = 1,350 GiB` including safety reserve. Forecast is 13,500 GiB. These are hypothetical workloads and resource caps, not a load-test result.

| Scenario | Worker / DB / API compute | Stored bytes + write/read operations | Priced component subtotal | Separate unpriced-service allowance | Planning range with 25% contingency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pilot, 50 captured entries, 20 continuations/hour | $195.67 / $202.36 / $105.12 | $27.00 + $155.86 + $5.84 | $691.84 | $250–$1,000 | **$1,177–$2,115/month** |
| Pilot, 2,000 entries, same arrival/new bytes | $195.67 / $202.36 / $105.12 | $27.00 + $5,992.21 + $233.60 | $6,755.95 | $250–$1,000 | **$8,757–$9,695/month** |
| Forecast, 50 entries, 200 continuations/hour | $1,565.39 / $809.42 / $420.48 | $270.00 + $1,558.55 + $58.40 | $4,682.24 | $1,000–$3,000 | **$7,103–$9,603/month** |

Planning range = `(priced subtotal + separately stated allowance) × 1.25`. The allowance is an internal input, **not a vendor quote**: SQL disk/backups/PITR, worker boot/image disks, load balancer/NAT/private networking/DNS, KMS/Secret Manager, telemetry, recovery copies, transfer, cloud support and taxes remain unpriced. If any line exceeds its allowance, the range must increase; this is not a binding upper bound or approved monthly cap. Larger burst workers, regional DR, model inference, engineering labor, external review and human support are excluded. Do not buy commitments based on these unmeasured profiles.

Recommended funding approach: retain current development-only authorization; obtain a line-item region-specific pilot budget after AR-015/033 measurements, first selecting a bounded file-count/continuation envelope. Use billing alerts plus admission/concurrency/spend controls; a cloud billing alert does not stop usage. Approve recurring infrastructure separately from research and staffing. A 2,000-file pilot needs either a larger priced budget or demonstrated artifact-operation improvements before adopting the small-file envelope.

## Paid research budget and upper-bound examples

The $200 ceiling is total validation authorization, not a renewable $200 per study or a production monthly allocation. Current API fields permit up to $200 for an individual request; that code limit does not reset the owner's aggregate authorization. Historical reservations are $36.567974, so subtraction gives **$163.432026** as an arithmetic remainder only. Invoice spend and current holds/other reservations are unverified; no paid dispatch is authorized by this worksheet. Reconcile the authoritative ledger and bound each proposed study before any new model call. Keep ambiguous reservations held.

A four-candidate screen with 8 pairs each and 30 confirmation pairs consumes `(4×8 + 30)×2 = 124` continuations. With 20 model decisions per continuation plus 3 discovery calls, an illustrative upper work count is **2,483 calls**. A deliberately hypothetical $0.10/call reservation bound gives **$248.30**, exceeding the entire ceiling before historical reservations. The arithmetic remainder would permit at most **65,820 micro-USD/call** uniformly for that work count, rounding down; real per-call bounds must account for differing context/output sizes and provider pricing. A branch's reused first action can reduce calls, but no saving is assumed here.

Call bound in micro-USD is the ceiling of `input_token_upper × input_USD_per_million + output_token_upper × output_USD_per_million + any separately billed reasoning/cache/tool charges`. Use the actual selected provider's current rates and request limits; $0.10 is not a model price claim. Include proposal discovery, both arms, confirmation, invalid attempts and ambiguous network outcomes. Missing evidence stays missing; do not silently downgrade models, shrink confirmation after observing results or refund uncertainty to fit a study. C02/C08/C09 govern valid protocols; paid research expansion needs separate explicit funding.

## One-time engineering and ongoing ownership

The approved backlog is 427 base engineering days; a 25% integration/rework view is 533.75 days. The separate sum of task upper planning bounds is 720.6 days. These are alternative uncertainty views, not amounts to add. Engineering money is `role-specific effort days × approved loaded day rate`, plus separately priced external assessment/statistical review and unknown remediation. No rate, hiring plan or fee has been approved, so no fabricated labor total is shown. Development contributor slots are not confirmed human FTEs, staff hires or a 24/7 on-call rota; the prior six-role staffing scenario remains a planning comparison.

| Responsibility | Current development ownership | Production/pilot requirement |
| --- | --- | --- |
| Scope, contracts, assignments and integration | Delegated project lead coordinates three contributor slots and review gates. | Product owner approves funded scope and material changes; external waits are not completion. |
| API/DB/auth and migration | Backend owner plus independent peer/lead review per PR. | Named operator for migration windows, backup verification and credential authority. |
| Worker/images/network/keys | Platform task owner and internal security review. | Named primary and secondary human operators, supported hours, escalation/incident plan and tested access. No current on-call commitment. |
| Evaluation/protocol/data | Research task owner; synthetic fixtures only until rights gate. | Named data/evaluator owner, permitted customer workload and approved model processor. |
| Identity and access | Existing auth code and local fixtures. | Actual IdP issuer/client/audience/role mapping, identity administrator and emergency recovery owner. |
| Budget and incident decisions | Project owner retains monetary authorization; lead enforces bounds. | Separate recurring cloud ceiling, research cap/ledger, support costs, alert recipients and shutdown authority. |

Material external inputs still required are: **production region/residency and permitted processors; named human operations/identity owners and support coverage; actual IdP configuration; recurring cloud funding; and any increase to the paid research budget/data permissions.** Routine architecture recommendations in this packet need no extra choices. These inputs can remain open while synthetic development/testing proceeds; ENV0/PARTNER0 and the relevant deployment/research gates remain blocked until actual evidence exists.

## Measurement and review gates

Before funded provisioning, AR-004-B consumes CAP-01 and freezes units/caps; AR-015 measures captures/restores across file-count/workspace distributions with fake providers; AR-033 materializes the approved region/IAM/network profile and line-item cost export; AR-040 records p50/p95/p99 latency, throughput, object operations, peak memory, queue age, DB pool/lock contention and saturation behavior. Capture a source/image/runtime/config identity for every benchmark. No benchmark is scheduled on the nearly full development host by this task.

Reprice at every integration gate when file count, context size, continuation duration, retention, provider quota or region changes. Add capacity only within an approved resource/spend ceiling. Preserve metadata reading during provider outage; stop new inference when ledger authority is unavailable. Do not interpret these proposed SLIs as contracted SLAs before observed pilot operation and recovery drills.

Validation uses Decimal arithmetic, explicit rate units and integer micro-USD budgeting. Tests cover hour/second conversion, retention size, fanout despite equal unique bytes, concurrency sensitivity, rejected unit/negative-input mistakes, discovery/both-arm call counts, the unchanged aggregate cap and separation of estimated allowances from vendor rates. No cloud account or provider is contacted by calculator/tests.

Recorded checks: the exact pytest console entrypoint `pytest -q -p no:cacheprovider tests/test_capacity_contract.py` and standard-library unittest discovery each passed **9 tests**. Scoped Ruff lint/format passed; all local document links resolve and `git diff --check` passed. No dependencies, images or packages were installed; no cloud resources or paid calls were created. SEC/QE/lead review remains required before closing AR-003-B.
