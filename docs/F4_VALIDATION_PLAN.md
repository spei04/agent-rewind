# F4 validation repair — proposed execution

Status: source and complete-entry reviews accepted. Execution remains stopped pending approval.

The previous approved attempt passed preflight, then failed before any pytest case ran. Its inventory validator still required the prior attempt's output directory. The failed attempt and original caller records are retained; independent review accepted the failure evidence and cleanup, not a validation pass.

The correction binds each run to one immutable attempt record. It covers output directories, configured and package allocations, staged package paths, operational receipts, and closeout. Historical inputs and the frozen candidate `e02ad6b` remain unchanged.

The proposed validation runs in this order:

1. Fresh source, environment, process ownership and capacity checks, with two fixed read-only privileged process observations.
2. A short harness-only contract check: accept the current binding; reject a wrong attempt reference, the exact old output path, and an allocation from another attempt. Each rejection must reach its intended guard. This fits within the existing metadata stage limit.
3. The inventory check and the unchanged 16 metadata tests.
4. The unchanged 320 selected tests under Python 3.11, then 320 under Python 3.12.
5. Package validation using the existing isolated staging and installed-package checks.
6. Independent evidence review, retained original caller records, final accounting and observed closeout exit.

There is one proposed 30-minute attempt. Preflight has 180 seconds; the four stages retain their existing start cutoffs and limits; independent review has at most 300 seconds; closeout has at most 120 seconds. The contract check has at most 10 seconds inside the metadata stage's existing 120 seconds. A failed or unknown result stops later stages. There is no retry or clock reset within this authorization.

| Reservation | Retained before proposal | New proposal | Total if approved |
| --- | ---: | ---: | ---: |
| Normal retained output | 320 MiB | 64 MiB | 384 MiB |
| Failure evidence | 1,024 MiB | 256 MiB | 1,280 MiB |
| Owned scratch space | 8 GiB | 4 GiB | 12 GiB |
| Campaign time | 90 minutes | 30 minutes | 120 minutes |

The normal-output cap would increase from 320 to 384 MiB. The failure category cap remains 1,536 MiB: 1,024 MiB retained plus 256 MiB proposed equals 1,280 MiB held. The other 256 MiB is unallocated ceiling headroom; it grants no additional write allowance and is not treated as a reservation or refund. The source-preparation allowance remains 256 MiB. Earlier reservations remain charged. The current prospective capacity requirement is 37,230,739,456 bytes, plus a 1 MiB entry margin and any subsequently discovered commitments. A fresh capacity check must pass; this proposal is not a capacity admission.

No paid model calls, new infrastructure, native validation, hosted CI, or new checkout are included. The $200 total API budget is unchanged.

The source review must verify every producer/consumer path, exact script and binding identity, allocation lineage, resource value, selector order, and stop condition. Static review is not runtime proof. The additional harness checks exercise private control code; they do not establish product or research performance. Passing this validation would qualify the frozen candidate for the next delivery step. Research still requires comparable real-failure baselines and independent confirmation of repairs.

The reviewed execution target is frozen: private entry SHA-256 `3f4f07105c7360bce3a7039d45cb5c829016203b4f79dd03a8d2a10473f781e1`, private plan SHA-256 `4c040e631104672d368b8507bc672b3a96abcad90603cd9ab9e85d2d36570f51`. The private record preserves exact source pins, review records, caller interfaces and capacity qualifications. Approval applies to one bounded attempt against these identities; later execution still requires fresh admission checks.
