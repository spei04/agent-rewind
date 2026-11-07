# F4 outcome and correction plan

**R3 stopped before product tests.** R1 retirement and the preflight producer succeeded. The admission reader then rejected a request missing the run's clock fields. F4 candidate `e02ad6be0a44d282085e534212ce237377d6be64` remains frozen and unaccepted.

The owner approved exactly one attempt from the [reviewed preparation package](https://github.com/spei04/agent-rewind/blob/b2bd4765c40fbfc13cac14878404c775fcc36c34/docs/F4_VALIDATION_PLAN.md). That attempt is consumed. No retry, paid provider call, new infrastructure, hosted CI or production deployment occurred.

## Observed outcome

| Boundary | Actual result |
| --- | --- |
| R1 future-access retirement | Original writer and reader exited 0; exact receipt and readback verified. No physical reclamation or historical refund. |
| R3 preflight | Original caller exited 0. Producer saved an active configured allocation with 4 GiB fresh scratch and the original clock. |
| Admission readback | Remote SSH returned 1; Mac wrapper returned its generic unsuccessful code 124. Both streams reached EOF and the declared owned local group was cleaned up. |
| Product stages | Metadata, Python 3.11, Python 3.12 and installed-package stages were all skipped. Sixteen expected stage paths were independently checked and absent. |
| Failure closeout | Original adapter exited 0 within its window; candidate acceptance remained false. Its retention scope was limited, as described below. |

The reader received neither `phase_t0_unix` nor `phase_expiry_unix` in its nested payload. `readAdmission()` placed the clock only on the outer Mac request. The remote reader immediately called the full authority validator, which rejected the missing origin with `approval:live-original-origin`.

This was a caller/reader contract defect. It was not a timeout, producer-preflight failure or product-test failure. Static reconstruction found the same omission in the unused `retainRootExit()` path; that path did not run.

The defect escaped the earlier independent source review and 32 Python plus 17 JavaScript preparation checks. Those historical checks remain valid for their tested scope; they did not establish successful admission-reader integration.

## Clock and scheduling evidence

All times below are UTC on November 7, 2026. The original runtime origin was **00:54:48.824**, with expiry **01:24:48.824**. The initial calls shared one 180-second preflight deadline, **00:57:48.824**; their Mac work cutoff was ten seconds earlier.

| Observation | Time / duration |
| --- | ---: |
| Retirement readback returned to the host | 00:55:17.135 |
| First and only preflight dispatch | 00:56:29.653 |
| Preflight producer caller returned | 00:56:58.212 |
| Admission-readback caller launched | 00:57:02.766 |
| Failed reader returned | 00:57:14.330 |
| Time remaining at failed-reader return | 34.494 seconds before the shared deadline |
| Original failure-closeout adapter returned | 00:58:04.367 |

The host gap between retirement readback and preflight dispatch was 72.518 seconds. A local capacity-binding lookup error was caught before `begin()` was invoked; the subsequent actual preflight was dispatched once on the original clock. The gap used scheduling margin, but the evidence does not attribute the entire gap to that exception. It did not cause the observed missing-origin rejection. No original operation was replayed and no clock was reset.

The failed reader took 11.564 seconds at the outer boundary. Its remote error was followed by the wrapper's normal bounded cleanup. Primary transport and cleanup errors were null. These facts do not justify increasing the timeout.

## Evidence and retained reservations

The original administrative closeout retained three caller envelopes. It omitted the failed admission-reader envelope. The original failed-reader and final-closeout buffers were later copied from the stopped operator without replay, verified against their original hashes, and saved as a private supplemental record. This post-closeout preservation does not retroactively complete the original closeout.

The closeout's `BEFORE_FULL_ALLOCATION` status describes its local branch. A remote configured allocation was already written and remains retained as written. A local reader failure is not evidence that no grant exists and does not release it.

Independent review accepted **failed-attempt evidence only**. Review completion took 284 seconds; the conservatively recorded receipt observation was 313.063 seconds after review start, outside the 300-second delivery limit. No full-sealer review timing, product acceptance or runtime success is inferred.

Current obligations remain:

- Future scratch: the other original 4 GiB hold plus the new R3 4 GiB grant. R1's future 4 GiB hold was retired once; R2's earlier retirement is not credited again.
- Normal output ceiling: 448 MiB. Failure-retention ceiling: 1,536 MiB. Neither authorizes another attempt.
- Scratch reservation history: the inherited 12 GiB record remains unchanged. The separately granted R3 4 GiB makes the cumulative reservation lineage 16 GiB. This is not measured physical usage; retained evidence and unknown usage remain preserved. A fresh R4 grant would add another 4 GiB, independently of retiring old future access.
- Approved accounting: 13,814 seconds prior consumption plus the 1,800-second runtime ceiling, totaling 15,614 seconds. Early failure does not create a reusable attempt.
- Joint cloud floor: 36,630,481,792 bytes, including Physics's new 65 MiB and Rewind's 320 MiB output reservations once. Safety's existing 256 MiB was already counted.
- Research cap: $200 total. The $36.567974 historical reservation remains separate from unknown settled spending and unknown available balance.

No files were deleted or physical space claimed as reclaimed. The original adapter returned 195.543 seconds after T0; external completion was separately observed. Supplementary preservation and review are explicitly later observations.

Private evidence identities:

| Record | SHA-256 |
| --- | --- |
| Owner approval | `1afc5d15e2e1b142464437469725c9d272659fb9698eb3d3541e203a9e4a2a4c` |
| R1 retirement | `ce1b2326befdf844483fe13dcfd605d8ca37af303c7533581f08f73c83f9b2e2` |
| Configured R3 allocation | `f441f5c7b31b17b9cdd4f2d6654f3e123448b1702967cb34afa1594b4ed360ab` |
| Supplemental original outputs | `0fe1a0830133af534b902c59411ad9fca8750a6f8485997c4ab0b75e9f6a5d2c` |
| Actual failed-attempt review | `dc196b9b5554c6f102d6d35fa4bd8946b959a879152b2b964fa790b4d648f0c4` |

## Next source work

This is a correction plan, not authorization to rerun R3 or increase a limit. Effort estimates below do not change execution or storage ceilings. These provisional operational follow-ups belong to the existing F4 gate; this record does not rebaseline the enterprise schedule.

1. **F4-C1 — Repair the two clock contracts.** Runtime; approximately half a day, high confidence. Add the original T0/expiry to the admission-readback and root-exit payloads that invoke full authority. Preserve operation-specific schemas; do not inject fields into unrelated strict payloads. Acceptance requires positive producer-to-reader tests plus missing, mismatched and invalid-clock refusals using the actual builders and authority checks.

2. **F4-C2 — Preserve failed control outputs and factual grant state.** Runtime; approximately half a day, medium confidence. Extend the ordinary closeout/export route to retain every attempted original control envelope, including a failed admission readback. Keep output bounds and private permissions. Distinguish a written remote allocation from an absent local reader result. Test successful preflight followed by reader failure, unknown grant state, exact raw hashes, overflow handling and no automatic release.

3. **F4-C3 — Test the integrated failure path.** Quality; half to one day, medium confidence. Develop fixtures alongside C1/C2, then verify the corrected producer/consumer boundaries together. Cover remote exit 1 becoming generic outer 124, EOF and owned cleanup, retained failed output, and persistent invocation state across control calls. Use isolated fixtures with no real grants, provider calls, hosted CI or live retry. A mock that merely repeats the expected payload is insufficient.

4. **F4-C4 — Review the complete successor package.** Lead and Quality; approximately half a day, medium confidence, after C1–C3. Repin the changed dependency graph, verify the invocation sequence and preservation path, update current accounting, and prepare any subsequent execution proposal with all existing holds retained. Preserve the failed R3 package unchanged.

Runtime owns the sequential changes to the shared operator files; Quality's fixture and contract work can proceed independently. Each implementation change must include its regression tests and be independently reviewable. The exit gate is a complete reviewed source package with passing integration checks and honest remaining resource obligations—not another successful-looking source matrix.

The eventual product qualification still requires 16 metadata cases, 320 focused cases on each Python version, and installed-package smoke, with original exits, evidence joins, cleanup and timely external completion. Full native-path, database/dialect, concurrency, protected CI and production gates remain separate. F5, P2 and the live failure-to-repair workflow remain open.

## Accepted source correction

C1–C3 are independently accepted as source corrections only. The final result is 28 JavaScript and 37 Python checks, including expected refusals. Both cloud workers exited 0 with completed output and release observations in 0.114210 and 0.227691 seconds respectively. Whole-file syntax checks passed. Quality verified all 29 indexed members and 44 graph/index references. The old preparation estimate was explicitly nonbinding; the consumed R3 runtime supplies no reusable time or execution credit. This work creates no new runtime authority.

The previous 2,621,440-byte source pool stays fixed and retained. A separate **1,572,864-byte** package allowance fits within the unchanged **268,435,456-byte** source category. The fresh complete census, including source parent directories, shared Git once and the entire F4 evidence tree, measured **149,680,128 bytes** at 01:17:19 UTC. Adding the new maximum and the existing 1 MiB publication margin gives **152,301,568 bytes**. Ignored checkout state is outside this source category.

The cloud check measured **38,758,760,448 free bytes**, above the conservative **36,632,054,656-byte** floor that retains all earlier commitments and adds the new source maximum. No current additional named commitment was known at admission; later writes must recheck the floor. No old reservation or unknown usage was released.

| Source package partition | Maximum bytes |
| --- | ---: |
| Corrected source and fixtures | 1,310,720 |
| Results, independent review and metadata | 131,072 |
| Directory allocation overhead | 65,536 |
| Bounded failure records | 65,536 |
| **Total** | **1,572,864** |

Runtime authored the corrected control code and stopped manifest. Quality authored the fixtures and independently verified the complete saved package. Lead reviewed the interfaces, isolation and resource records. The private start record is pinned by SHA-256 `d857df4314d2d74b495b872fbb4c8330d3bd4d58b5a5f5f3dd6d60015100dcea`.

The source workers ran after independent isolation review, with a **10-second** external limit each and retained records inside the 128 KiB results/review allowance. They exercised actual producers and authority validators through fixture-only adapters. Ambient filesystem, network, provider and process access is denied; no real approval documents, live operator capsule, retirement writer or product stage may execute. Only an affected changed unit may be rerun during development, with its earlier failure retained.

Preparation is conservatively tracked from 01:11:10 UTC. The 1,800-second planning estimate is not an execution allowance or an owner-imposed engineering cutoff. Its actual charge remains pending through source work, checks, review and publication; completion needs a later external observation. Earlier post-closeout preservation, review and publication intervals remain recorded separately; overlapping observations are not added as independent elapsed time or reported as measured CPU.

The corrected source index is `2396774fdd20d902448c8a98beeae9229f53d1be6c59d95c44ce728fffd2b35d`; Quality's accepted review is `6ff2d92ed548e410a2809a4ebe91d4a34b670317e50f7799ec6050504531ecca`. At review completion the private package used 770,048 allocated bytes, including all prior working versions and source-check failures. Metadata/results used 73,728 of 131,072 bytes.

The first JavaScript check exited 1 because its synthetic closeout template inserted undefined fields. The production JSON validator rejected them. That original failure was saved; only the changed fixture was rerun, and Python then ran for the first time. The accepted results are **source checks**, with zero product tests or live operator executions.

The corrected factory and administrative entrypoint remain disabled. The API exports the original final control output after its wait completes, but exporting into memory is not durable storage. C4 must add a bounded writer, original exit observation and independent readback before a future all-original-retention claim. It cannot recursively attest to its own future completion.

## C4 validation proposal

The distinct R4 package has passed its affected source checks. **Independent review accepted the saved source package for a separate owner decision.** The production candidate remains `e02ad6be0a44d282085e534212ce237377d6be64`; no product stage, new retirement, runtime grant, provider call, hosted CI or infrastructure change occurred during this preparation.

Runtime implemented the authority, retirement and resource contracts. Integration implemented the operator sequences and terminal persistence. Quality authored the affected fixtures; Lead and Integration independently reviewed their isolation and interfaces. The saved implementation provides:

- One admission sequence using a private copy of the supplied capacity and identity data. Allocation state is committed only after the reader's full checks.
- Explicit original-clock propagation and one-use operation ordering. Failed closeout suppresses root exit, including through the direct method.
- A bounded terminal writer and separate reader that retain exact original control bytes, including failed or incomplete controls. Their own final completion still requires external observation.
- Same-realm lexical loading that preserves the consumed R3 operator's globals and capsule. The distinct R4 identity was initialized in the original main VM realm at 08:17:20.840 UTC, with every pre-existing global descriptor unchanged. No factory was evaluated and no clock started.

| Affected source checks | Passed | Original completion |
| --- | ---: | --- |
| Terminal helper and storage boundaries | 66 | Python exit 0; 0.719855 seconds |
| Actual operator factory with closed transport fixtures | 25 | JavaScript worker exit 0; 0.969 seconds |
| Authority, historical integrity, deadlines and actual JavaScript payload joins | 36 | Python exit 0; 0.386 seconds |
| **Total** | **127** | Both streams complete; no stderr or unresolved worker |

The 36 authority cases include 18 qualifier cases; those 18 are not counted again. The earlier 65 accepted C1–C3 checks were not rerun. These checks use synthetic process/filesystem adapters and do not substitute for native product validation.

The first bootstrap stopped before either worker because its recipe retained one stale input hash. The first JavaScript worker then exposed a fixture comparison that treated object key order as significant; the corrected comparison still requires complete structural equality after caller mutation. Two subsequent result emissions exceeded the unchanged 49,152-byte cap. All failed originals remain retained; no pass count is inferred from a failed emission.

The final result transport removes redundant base64 encoding from exactly two terminal-export values on the wire. Before Python receives the result, the reader reconstructs every original field and verifies each export's bytes/hash and the complete original result's length/hash. The final raw output was **24,704 bytes**; wire content was **241,705 bytes**, restoring the exact **285,742-byte** original result. The 1 MiB decoded limit and 8-second work / 10-second total worker limits remain unchanged. The largest actual control request was 3,113,429 bytes; the logical maximum export plus actual proof/entry wrapper measured **4,002,121 bytes**, below the 4 MiB limit.

The literal administrative writer bound includes partial success plus failure records, all terminal metadata/failure slots and directory allocation:

| Reachable branch | Maximum KiB |
| --- | ---: |
| Full success | 8,048 |
| Sealer fails after writing its index; root exit suppressed | 7,984 |
| Admission reader fails after partial writes | 6,640 |
| Preflight fails after partial writes | 5,776 |
| **Existing partition limit** | **8,192** |

Configured output retains 40 MiB, installed-package output 16 MiB, and administration/review/terminal evidence 8 MiB within the existing proposed 64 MiB normal envelope. No stream cap was reduced to obtain this fit.

### Source resources and preservation

The separate **2,097,152-byte** preparation allowance remains inside the unchanged 256 MiB source category. It includes current sources, fixtures, original results, review/approval records and revision preservation. External Quality review and future owner approval reserve 32 KiB and 64 KiB inside the metadata partition; the future retirement receipt reserves 16 KiB inside the correction partition. Final accounting uses actual-or-reserved values once.

The final read-only audit at **08:17:53.132 UTC** passed. The 94-file package used **1,642,496 allocated bytes**. Including the actual 8 KiB review, future 64 KiB approval, 32 KiB final-record forecast and 16 KiB retirement receipt once gives **1,765,376 of 2,097,152 bytes**. Metadata is **258,048 / 262,144 bytes** and correction is **196,608 / 196,608 bytes**. The complete source category plus remaining named records and the existing publication margin is **153,272,320 / 268,435,456 bytes**. Cloud free space measured **39,013,183,488 bytes**, above the source-only floor; this does not admit a future runtime.

The audit verified 45 current source/input references and 10 immutable R3 references. The R3 grant remains unchanged; all 19 new runtime roots, new approval and retirement receipt were absent. Both existing checkouts remain active dependencies and were retained. No checkout removal or disk savings are claimed.

Preserved working revisions temporarily exceeded the internal correction partition: the measured allocation was 229,376 bytes, or 245,760 bytes including the future receipt reservation, against its 196,608-byte limit. The overall 2 MiB preparation allowance remained intact. Verified archival and reconstruction records preserve the prior bytes and this accounting history; they do not erase the overshoot. A later abandoned archive encoding was removed only after its inputs were verified retained; its individual allocation was not measured and is conservatively bounded at 16 KiB. No historical R3 evidence or current operative source was deleted. Temporary consolidation used at most 8 KiB of the already reserved late-metadata allowance and was released after verification.

Workspace environment operations retain pinned uv 0.11.21. The frozen installed-package helper retains its explicit, pre-existing uv 0.13.4 requirement. Both executables were hash-checked and returned the expected versions; no installation, replacement, version impersonation or candidate-helper edit occurred.

### Original preparation completion witness

The original preparation writer exited **0**, with both streams complete and exact readback, at Unix time **1794039640.058**. Its separate external completion was observed at **1794039647.359**: November 7, 2026, **00:20:47.359 PST** (08:20:47.359 UTC). This is an observation of the original save; no writer or source check was replayed.

| Original completion accounting | Exact seconds |
| --- | ---: |
| Source preparation: `ceil(1794039647.359 - 1794013870)` | 25,778 |
| Carried interval: `ceil(1794039647.359 - 1794012888.824)` | 26,759 |
| Actual prior: `13814 + 26759` | 40,573 |
| Proposed campaign ceiling at that observation: `40573 + 1800` | 42,373 |

The original approval question included these exact counters. They describe that observation, not the later evidence-publication work. This follow-up is charged conservatively through its later externally observed completion `E2`, using the same original origins and no intervening wait exclusion. The revised decision message must state `E2` and its resulting exact counters; it supersedes the original question's accounting. Preparation and carried intervals overlap and are never added together.

Private witness `PREPARATION.external-completion-witness.v1.json` is **3,247 bytes**, SHA-256 `54c966224cee2e38df0bc08aa6a13e54f5a34c855ecd8e382a5bc2907e8c4b08`. It preserves the original writer's exact returned output, exit/EOF observation, external completion, counters and private session binding. Its own original save/readback also exited 0. The witness uses 4 KiB within the existing final-record reservation; total final records currently use 16 KiB of 32 KiB. Metadata plus future approval uses 241,664 of 262,144 bytes; the preparation pool with future reservations uses 1,748,992 of 2,097,152 bytes.

The bound original receipt is **8,617 bytes**, SHA-256 `e720c8a6652c6926b6c6f998003a4d846d265300b675df3eb51f5743b392b4ce`; entry `2fed2645d99b78dab5e55d4958dafe088a08b8a83ebec69718bda322102dfe1b` and independent review `eca9d982cc4e00288d23c690092db45d48c2321128a56717e6962ca50ac3e544` remain unchanged. The actual private session's SHA-256 identity fingerprint is `bfe2e3c049a810f4f7a4c8e12a490bbc59660a367c1d872dbe17f234ade57af2`; its identity stays private.

The receipt deliberately retains `external_completion_pending=true` and null future budget counters: bytes written before a process returns cannot attest to that process's later exit or tool completion. The external witness and eventual approval supply those observations without rewriting the receipt. The later completion will remain a separate observation, not a replacement timestamp for the original writer. No new runtime origin, retirement, approval or product acceptance was created.

### Separate execution decision

A future owner decision must bind the stopped entry, accepted review, preparation receipt, externally observed preparation completion and actual private R4 session. The proposal is to retire **only R3's unused 4 GiB future scratch access**, verify the retirement writer and independent readback, and then admit **one fresh 30-minute R4 validation**. No R1/R2 credit is repeated, no historical charge is refunded, and no file deletion or physical reclamation is claimed.

Future scratch would transition from 8 GiB to 4 GiB after retirement, then to 8 GiB after fresh R4 admission. The inherited 12 GiB reservation history remains unchanged; adding the actual R3 grant makes current cumulative reservation lineage 16 GiB. A fresh R4 grant would make that lineage 20 GiB. These are reservation records, not measured physical use.

The proposed new normal/failure reservations are 64 MiB and 256 MiB, taking their cumulative totals to 512 MiB and 1,792 MiB. The exact 16 metadata / 320 Python 3.11 / 320 Python 3.12 / existing installed-package qualification inventory, continuous 1,800-second phase, stage-start cutoffs and original 120-second closeout remain unchanged. There are no retries, paid provider calls, new infrastructure or hosted CI in this proposal.

| State, before any later commitments | Required free bytes |
| --- | ---: |
| Source preparation only | 36,634,151,808 |
| Administrative phase / verified-retirement successor | 36,969,696,128 |
| Full fresh runtime while retaining every old scratch hold | 41,264,663,424 |

Fresh complete capacity reconciliation remains mandatory. A historical free-space observation cannot admit a future run.

Source preparation is conservatively accounted from 01:11:10 UTC, including review, publication and all unexcluded delays. Its planning estimate was nonbinding. Preserve R3's immutable 15,614-second authorization ceiling and consumed attempt separately. For final externally observed completion `E`, the preparation charge is `ceil(E - 1794013870)`; the carried interval is `ceil(E - 1794012888.824)`. Future actual prior consumption is 13,814 plus that carried interval; a separate fresh 1,800 seconds produces the proposed campaign ceiling. Overlapping observations are counted once. These elapsed-wall-time figures are not CPU measurements or reusable runtime. The final decision request must state the observed completion and resulting exact counters.

### Evidence and remaining product gates

- Stopped entry: `2fed2645d99b78dab5e55d4958dafe088a08b8a83ebec69718bda322102dfe1b`.
- Core source index: `3b9304ce18f5b89ba7ef5cbe95dd6439bbb1f29ba057945bd32185acbf0c6c8b`.
- Final verification graph: `e12d5b430353e4b4ca33768e873e31c57517a82f073a4fcef857148d4c33c404`.
- Independent review: `eca9d982cc4e00288d23c690092db45d48c2321128a56717e6962ca50ac3e544`.

F4 qualification does not enable the live customer workflow. The current compatibility release intentionally keeps customer/auth routes unavailable and worker claims disabled. F5, worker P2, AR-012-B integration and an admitted release profile remain prerequisites for a usable failure-to-branch workflow. Static dashboard evidence remains labeled as such.

[Assignments](ASSIGNMENTS.md) · [Roadmap](PLAN.md) · [Execution backlog](EXECUTION_BACKLOG.md#ar-010-b)
