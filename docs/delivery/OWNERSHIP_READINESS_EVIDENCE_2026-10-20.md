# Ownership and safe-readiness verification — 2026-10-20

AR-007-A and AR-011-B are Verified for their bounded development scope. The
packaged release remains **migration-only**: customer admission is disabled.
Neither task closes full M1 authorization/admission/ledger acceptance, approves
production deployment, or supplies partner-data, funding or external certification.

| Delivery | Reviewed source and merge | Matching hosted evidence |
| --- | --- | --- |
| Ownership [PR #43](https://github.com/spei04/agent-rewind/pull/43) | 5f450b3193c5434bd0646e65eacbf0a215a24be5; merge 5172c7e | [39354218945](https://github.com/spei04/agent-rewind/actions/runs/39354218945): 865 passed, three Docker skips and one existing HTTPX warning on each Python 3.11/3.12 job; three gVisor tests; security, package and CI gate passed. |
| Combined readiness [PR #46](https://github.com/spei04/agent-rewind/pull/46) | aafc08d33e599f09b84329735dadacbeaca639bd; merge 3098589ea07d2a5d4341319206e718092a05d422 | [39354594971](https://github.com/spei04/agent-rewind/actions/runs/39354594971): 969 passed, three Docker skips and one existing warning on each supported Python job, with real PostgreSQL configured; three gVisor tests; security, package and CI gate passed; zero PR artifacts. |

Engineer B independently reviewed source, integration equivalence and exact-head
hosted conclusions. Engineer C independently reviewed readiness lifecycle and
ownership integration; the lead reviewed both. These are internal technical
reviews, not separate-human GitHub approval or external statistical/security certification.

Ownership adds four tables and explicit resumable initialization/backfill. Nine
real PostgreSQL ownership cases include least-privilege refusal, writer exclusion,
atomic checkpoints, actual process death, constraints and checkpoint dump/restore
followed by resume. Literal source rows and historical accounting remain preserved.
Interrupted study children resolve only through unique job/source ancestry; no
trial outcome or arm identity is invented. Exact observed PostgreSQL enum-rendering
normalization preserves the original frozen profile/fingerprint. This is capped,
offline relational closure, not a claim of scalable throughput or decrypted
artifact closure. Scoped repositories and route enforcement remain later work.

Readiness uses one supervised Linux subprocess per API process, a one-second
probe response deadline, bounded IPC and encrypted installation-only sentinel
reads, at most one physical probe and a positive cache no older than five seconds.
Deadline/cancellation kills the child; physical capacity remains owned until reap.
Parent death, partial frames, stalled transport, repeated cancellation and sentinel
installation/metadata mismatch are covered. OS scheduling and uninterruptible
kernel cleanup are not hard-real-time guarantees. Positive test workers are
synthetic; the real migration-only profile cannot authorize customer work.

Safe boundary tests cover fixed errors, generated correlation, sensitive exception
canaries, actual logging-sink failures, default stderr JSON diagnostics, missing
requested records versus corrupt internal evidence, authorization before work
readiness and readiness before upload/commit. The existing health/liveness split
is preserved. Connection capacity includes the fixed extra readiness connection
per API process. Installed wheel/sdist smoke runs outside the source checkout and
exercises the merged ownership and readiness resources.

## Protected-main candidate evidence

The lead inspected each short-retention archive in memory: exactly the four
allowlisted wheel, sdist, manifest and SHA256SUMS files; source/lock identity,
manifest digests and checksum entries agreed. No archive or raw log was retained.
Owner-readable release records and an index remain outside temporary checkouts.
This records installable candidate delivery, not package publication or deployment.

| Source / successful main run | Artifact | Archive bytes / SHA-256 | Expiry |
| --- | --- | --- | --- |
| 5172c7e / [39354527314](https://github.com/spei04/agent-rewind/actions/runs/39354527314) | 12234886355 | 299368 / `456dd2806b1936d70daf2c8709dc68adb8032a62e4fcd2b310b65c25e335ccef` | 2026-10-27T01:40:31Z |
| 3098589 / [39355582613](https://github.com/spei04/agent-rewind/actions/runs/39355582613) | 12235441207 | 320524 / `b0cf3bc13268f49531f43a922a6218be7d0dd847ea335c313cea6b4dac35c24f` | 2026-10-27T01:52:36Z |

Ownership wheel SHA-256: `b41ac2a44bd871e2729fa77c355d0c60c0e930716586cc5c126d10eb61910ecb`;
sdist: `c4510395affdd60af914dcbcba8e291711209d30515c7b7601cb1665aa25acb2`.
Readiness wheel: `721ce60288af94c746bfac8567aff4d6d35181131a361e36bd9192e91a1d6887`;
sdist: `e635eaa72e7d038559588baae24cf4810f70615efb981916293b803ba278030d`.

Issues #40/#41 are closed for these children; parent #7/#11 remain open. The
validation cap is still $200; historical reservations are $36.567974 and are not
invoice-reconciled cash spend. This batch made no provider calls, created no paid
resources and used no partner data. Research design approval does not alter these
limits or the separate production, data and statistical review gates.
