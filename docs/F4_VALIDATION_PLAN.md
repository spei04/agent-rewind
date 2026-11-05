# F4 validation — attempt result and next work

Status: replacement 2 is closed. Preflight passed; the following admission-reader step failed. No validation stage started. The candidate remains unaccepted.

The preflight returned exit 0 after checking the frozen source, both Python environments, tool identities, process ownership and capacity. Both fixed observers succeeded and proved cleanup. The follow-up reader expected `consumer_scan_initial.success` and `consumer_scan_final.success`; the producer stores that field inside `observation`. The resulting `KeyError` is an evidence-reader defect, not a failed preflight or product test.

The approved plan says: “A failed or unknown result stops later stages. There is no retry or clock reset within this authorization.” The attempt therefore stopped. The successful preflight and separate reader exception are retained unchanged.

| Stage | Planned checks | Actual result |
| --- | --- | --- |
| Metadata | Contract/inventory checks and 16 tests | Not started |
| Python 3.11 | 320 selected tests | Not started |
| Python 3.12 | 320 selected tests | Not started |
| Package | Isolated staging and installed-package checks | Not started |

Independent review confirmed the original successful preflight, absence of its five known process identities, and absence of all 16 stage-related paths. The closeout sealer exited 0; the original exit receipt was retained within its 120-second limit. Retention and cleanup were accepted. Candidate validation was not.

Known closeout evidence occupies 233,472 allocated bytes across 22 files, with 177,280 apparent bytes. Configured outputs and named scratch charge zero. Anonymous live usage was not measured. These observations do not release reservations or bound a future run.

## Reader correction

The correction must read the retained producer schema and preserve its success and release-proof checks. The source audit covers configured and package caller envelopes, command summaries, saved readbacks, package issuance, closeout and the independently observed exit receipt. Fields must be checked on the record that actually emits them; successful cleanup must remain separate from candidate acceptance.

The correction passed 27 bounded retained-data controls and independent source review. The reviewed reader is pinned to the closed attempt and always returns runtime_authorized=false. A future entry needs a reviewed successor reader with its exact new identity, document references and actual foreground-exit evidence; the invocation must call that pinned implementation instead of repeating inline schema assumptions. No runtime retry follows from this work. Frozen candidate `e02ad6be0a44d282085e534212ce237377d6be64` and all accepted operator sources remain unchanged.

## Remaining-stage continuation

All four validation stages remain necessary, in their original order. The simplest supported scope retains their existing limits and the fresh entry, independent review and closeout checks. It requires a separate reviewed entry and execution decision; the closed attempt cannot be reopened.

The capacity review distinguishes historical charges, retained evidence and future disk commitments. Existing policy retains replacement 2's full reservation; terminal cleanup does not automatically authorize reuse.

The proposed exception is limited to its unused 4 GiB scratch reservation:

| Decision requirement | Proposed treatment |
| --- | --- |
| Owner | Agent Rewind/F4, administered by Lead |
| Original allocation | Replacement 2 configured allocation `ab7b1a049f0533f481372510d8bc386f0bfcc4ab8f31776f0128ee3b2fee63d0` |
| Terminal evidence | Four skipped stages; 16 absent stage paths; five absent process identities; independently accepted cleanup and closeout |
| Retained bytes | Named scratch and configured output: 0 B. All 233,472 allocated bytes of closeout evidence remain retained. |
| Future bound | Reassign exactly 4,294,967,296 bytes to one distinct, subsequently frozen attempt; replacement 2 cannot use it again. |
| Authority | Explicit recorded reassignment decision and reviewed allocation changes are required; this proposal applies neither. |

Every earlier scratch hold, all retained normal/failure reservations, and 7,200 charged campaign seconds remain. Historical allocations and failures are immutable. Anonymous historical use remains unmeasured. Unresolved commitments retain their original holds.

If the exception is explicitly adopted, the separate continuation would have these deltas:

| Resource | Held or charged now | Proposed delta | Proposed total |
| --- | ---: | ---: | ---: |
| Normal output | 384 MiB | +64 MiB | 448 MiB |
| Failure output | 1,280 MiB | +256 MiB | 1,536 MiB |
| Prospective scratch | 12 GiB | 0 net; reassign 4 GiB | 12 GiB |
| Campaign time | 7,200 seconds | +1,800 seconds | 9,000 seconds |
| Source allowance | 256 MiB | None | 256 MiB |

The resulting capacity requirement would be 38,632,450,304 bytes, including the existing margin. Against the last closeout observation of 39,617,396,736 bytes free, that leaves 984,946,432 bytes. This is illustrative arithmetic, not fresh admission or an applied reservation change. Without the explicit exception, the existing holds remain unchanged; another full envelope would have a 3,310,020,864-byte deficit at that observation.

The new allocation must name the precise reassignment and its approval reference; it cannot claim without qualification that every old prospective hold was retained. Retire the old attempt's future access without altering its historical allocation, seal the distinct future attempt and complete producer/consumer reference map, independently review the changed contracts, and obtain the separate execution grant. Fresh capacity, source, environment and process checks must still pass.

No paid model calls, new infrastructure, native validation, hosted CI, new checkout, deletion or retrospective cost refund are included. The $200 total API budget is unchanged.

The original private entry hash `3f4f07105c7360bce3a7039d45cb5c829016203b4f79dd03a8d2a10473f781e1` and plan hash `4c040e631104672d368b8507bc672b3a96abcad90603cd9ab9e85d2d36570f51` identify the consumed authorization. Original evidence stays immutable. Runtime validation, production readiness and research comparisons remain separate gates.
