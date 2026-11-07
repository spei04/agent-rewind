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
- Historical scratch: 12 GiB, with all prior charges, retained evidence and unknown usage preserved.
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

## C4 operative proposal in preparation

A distinct R4 source package is being authored under existing development authority. It does not create a runtime clock, retirement or grant. The completed correction package and every failed R3 record remain immutable.

A separate **2,097,152-byte** source allowance fits the unchanged 256 MiB category. The fresh census at 01:49:19 UTC measured 150,450,176 source bytes; adding the new package and 1 MiB margin gives 153,595,904 bytes. Free cloud space was 38,704,529,408 bytes, above the 36,634,151,808-byte source floor. Both existing checkouts retain their original heads; no checkout or dependency installation was created.

The authoring plan preserves the 16/320/320/package qualification inventory and the original runtime/closeout limits. It adds the final control export's bounded durable writer and separate reader, explicit success/failure writer maxima, complete operative references and one-use invocation ordering. Only changed interfaces and new persistence behavior will receive new source checks; the accepted 65 checks remain historical evidence.

Current capacity cannot admit another 4 GiB scratch reservation while all earlier holds remain. The draft therefore proposes a future, explicit decision to retire **only R3's unused future access**, followed by fresh R4 scratch after verified retirement. The old allocation file, historical charges, failed evidence and unknown usage remain preserved. No retirement has been applied, no R1/R2 credit is reused, and no physical reclamation is claimed.

| Draft state, before later commitments | Required bytes |
| --- | ---: |
| Source preparation only | 36,634,151,808 |
| Administrative phase / verified-retirement successor | 36,969,696,128 |
| Full new runtime with every old scratch hold retained | 41,264,663,424 |

The proposed new normal/failure reservations would be 64 MiB and 256 MiB, taking their cumulative totals to 512 MiB and 1,792 MiB. These are proposal figures, not execution authorization. The exact terminal writer table and its fit inside the existing normal envelope must be proved before source freeze. Tool selection must also be reconciled explicitly: the workspace names uv 0.11.21, while the inherited package command names 0.13.4.

Source preparation remains continuous from 01:11:10 UTC, including correction, review, publication and successor authoring. Its actual end is still pending. Preserve R3's immutable 15,614-second authorization ceiling and consumed attempt separately from elapsed work. The adapter's 195.543 seconds and external completion's 228.589 seconds are nested observations, not additive. The following 752.587-second preservation/review/publication span is counted once. Future accounting must use the union of observed intervals and a separately observed source-completion time; no CPU-total or reusable-runtime claim follows.

Finally, F4 qualification does not enable the live customer workflow. The current compatibility release intentionally keeps customer/auth routes unavailable and worker claims disabled. F5, worker P2, AR-012-B integration and an admitted release profile remain prerequisites for a usable failure-to-branch workflow. Static dashboard evidence must remain labeled as such.

[Assignments](ASSIGNMENTS.md) · [Roadmap](PLAN.md) · [Execution backlog](EXECUTION_BACKLOG.md#ar-010-b)
