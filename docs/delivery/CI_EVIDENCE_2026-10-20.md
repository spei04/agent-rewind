# CI and candidate delivery evidence — 2026-10-20

AR-051-A is verified for continuous integration and installable candidate delivery.
This record does not authorize package publication, deployment or customer data.

| Evidence | Identity / result |
| --- | --- |
| Reviewed implementation | [PR #29](https://github.com/spei04/agent-rewind/pull/29), exact head `7c31b14a04f8be1e4d0bce75a43f1ea9d0ea3abf`; Engineer A independently accepted, lead reviewed/integrated |
| Merged source | `13465c10add08020b1be67b20ed081c0bc27f3e4` |
| PR validation | [Run 39346080653](https://github.com/spei04/agent-rewind/actions/runs/39346080653): core 3.11/3.12, PostgreSQL, gVisor, security, package and CI gate passed; delivery skipped; zero artifacts |
| Protected-main delivery | [Run 39346262029](https://github.com/spei04/agent-rewind/actions/runs/39346262029): every required job and Main candidate delivery passed |
| Test evidence | 495 tests passed on each Python version; the three Docker tests skip in the core environment and pass in the separate real gVisor job. Ruff/format/types/contracts, strict dependency audit and isolated package smoke passed |
| Candidate | Artifact `12230273836`, `candidate-13465c10add08020b1be67b20ed081c0bc27f3e4-1`, 219,290 bytes |
| Retention | Expires 2026-10-27 00:13:52 UTC; seven-day candidate retention, not a durable release store |
| Runtime inputs | Frozen lock with cryptography 50.0.2, Alembic 1.20.0 and build backend setuptools 83.0.0; manifest/lock agreement checked before consumption |
| Advisory state | Authenticated repository read-back: zero open Dependabot alerts; strict locked audit reported no known vulnerabilities. This is advisory-database evidence, not a reachability/security certification |
| Observed runner use | Seven rounded job-minutes for this main run. Future changes run the full matrix; Dependabot's dynamic jobs add separate usage. This is duration evidence, not an invoice or recurring spending forecast |

The lead fetched the artifact in memory and verified the exact four-file allowlist:
wheel, sdist, `candidate.json` and `SHA256SUMS`. Every checksum matched; manifest
and lock digests matched the exact source commit. No archive was extracted or
persisted on the Mac. A separate repository coordinator independently confirmed
the main/PR runs, artifact members, checksums and source identity.

| Digest | SHA-256 |
| --- | --- |
| GitHub artifact archive | `8ee8e02fe694b0ae7458eaa38f6513073fdd9821ea92abaa5aa9433c015a7b04` |
| Wheel | `6130c44c89296595cba8e18c42d51119817ffe2c245b4d7b45061cc4d43cefab` |
| Source distribution | `838b50c2d8220eea84c499d08139b040fd54cb3854340e8ad3d527650b7868ce` |
| uv.lock | `f7394a652f9f54b010ea953cf2951a3723c62b56c35427a44cc1af88f24b9a59` |
| pyproject.toml | `64cad07784a5a4850bda3f3f8652464d0e048cc87c4a8f3bd8349cdf048282b3` |

Repository settings were independently read back after the coordinator applied
them: PR-only main updates, up-to-date `CI gate` restricted to GitHub Actions
app 15368, admin enforcement, resolved conversations, no force pushes/deletions,
and full-SHA action pinning. The sole-owner repository has zero required GitHub
approvals; internal engineer review is recorded honestly and is not a second
human GitHub approval.

The [delivery runbook](CONTINUOUS_DELIVERY.md) describes input updates, candidate
verification, promotion ownership and rollback limits. Later AR-043 work still
owns signed releases, attestations and broader supply-chain acceptance. Production
region, funding, IdP, operator, data and release gates remain open. This batch made
no provider calls and provisioned no paid resources. An owner-readable indexed
identity/evidence record is retained outside temporary checkouts; the package
candidate itself expires as stated above.
