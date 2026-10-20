# Runtime guard and recovery acceptance — 2026-10-20

[PR #39](https://github.com/spei04/agent-rewind/pull/39) merged at
`0737c7bd236422577457e3dff52da02266d957cf`. The independently reviewed/tested source is
`94dd9cb339f1e68e35e70847ca0539ecb0fafb29`; the merge has the same tree.

## Executed checks

[Hosted run 39350413566](https://github.com/spei04/agent-rewind/actions/runs/39350413566)
passed all required checks. Python 3.11 and 3.12 each passed **758 tests**, with
three Docker skips covered by three passing real gVisor tests in the isolation
job. The configured PostgreSQL 16 service executed 58 cases: 42 migration,
11 runtime guard, four actual recovery, and one existing claims/budget case.
Lint, formatting (72 files), type checking (30 modules), contract validation,
locked dependency security audit, installed-distribution smoke and CI gate passed.
PR delivery was skipped and uploaded zero artifacts. The one existing warning is
the FastAPI/Starlette test-client HTTPX deprecation.

The four recovery cases restore legacy and prepared custom archives into separate
clean targets, refuse a truncated archive without partial state, and terminate a
real blocked data restore before retrying the unchanged archive. Both successful
restores verify 14 literal historical rows, 18 encrypted objects, their authenticated
content addresses and exactly 245000 microUSD in held reservations. Object recovery
is a separate local fixture copy using a public synthetic key; database dumps do
not include objects, encryption keys or cluster roles. Roles already exist in the
same disposable test cluster. This is not a cross-region or full key/role recovery drill.

Runtime checks refuse missing, future/multiple, partial and corrupted metadata
before API/authentication access or worker claims, with no runtime DDL. Least-
privilege PostgreSQL checks, read-only transactions, lock refusal, safe diagnostics,
physical probe capacity across cancellation and fixed nonzero worker refusal are
covered. `/livez` is process liveness; `/healthz` preserves database connectivity.
Compose defaults to metadata inspection and pins the tested PostgreSQL image;
explicit install/upgrade require operator input. Its shared privileged development
role is not a production role pattern.

## Review and observed corrections

A/B accepted guard changes through `e99b3ae`; B accepted C's deployment-consumer
correction `ba345663` and the final image pin. B/C independently accepted A's
restore classifier correction `4b44c06`; B accepted the complete final source and
hosted evidence. This is internal engineering review, not external certification.

Initial run `39349339606` exposed SQLite timeout cleanup and prepared-restore
compatibility failures. Diagnostic run `39349792047` narrowed the remaining mismatch
to six catalog spellings of three enum constraints: PostgreSQL dump/restore moves
whole-array casts to element casts. The implementation recognizes only these exact
observed expressions, retaining the original canonical schema identity. Seventeen
regression cases reject nearby enum/operator/type, constraint-identity/cardinality
and validation changes. No original schema profile, row, ciphertext or fingerprint
was rewritten. Other corrected review findings covered final libpq routing,
cancellation capacity, silent worker refusal and legacy health-probe compatibility.

| Frozen or release file | SHA-256 |
| --- | --- |
| `agent_rewind/migrations/profiles/postgresql16.json` | `10f7b64b8341096a69571da4449076bdffb05cb26dc2407b30cdf710bb8c5008` |
| `agent_rewind/migrations/profiles/sqlite.json` | `d7c949e9bae68f631665a18e450f697bdc5aac8a2357708dfeff6b1be523bb52` |
| `agent_rewind/migrations/release_compatibility.json` | `2c2356000c411a03aab177bff37a348a2aab3e55af193b751de840ecb47e2f27` |
| `tests/fixtures/legacy_v0/baseline.sql` | `62cd159230e9f81336779658b706c161149c24115f6e0f54bdfe4f32c7bdb19a` |
| `tests/fixtures/legacy_v0/manifest.json` | `cd19df65a34668918118f878f5233abff081a54f1f6ebb2512e2e46cd3795b17` |

## Acceptance limits and next work

AR-005-C and the three-task AR-005 package are Verified for development/testing.
The current release intentionally returns `incompatible / migration_only`; it does
not admit customer workloads. No approved customer-serving rollback pair exists.
An old unguarded binary is not a rollback authorization. Pool/connection/server SQL
limits are not a proven deadline for stalled synchronous network reads. AR-011-B
must implement its separate interruptible readiness transport requirement.

AR-007-A (ownership/backfill) and AR-011-B (safe errors/readiness) begin only after
this merge. The 24-case M1 integration suite, customer activation, HA, actual partner
IdP/data, production provisioning, recurring funding and release gates remain open.
No paid production resources, provider calls or partner data were used in this slice.
Private release-control metadata is indexed outside disposable checkouts with
owner-only permissions; no downloaded log or package archive is retained.


Protected-main [run 39350652882](https://github.com/spei04/agent-rewind/actions/runs/39350652882)
also passed at merge `0737c7b`. Candidate artifact `12233147116` contains exactly
wheel, source distribution, candidate manifest and checksums; the lead verified
all hashes and source identity in memory. Its 269597-byte archive SHA-256 is
`714e93dc74bc6a0c5b91d5a044644b95e25f731c8d45192d41c40c2d262d5e4e`.
Retention ends 2026-10-27; the private release record retains the identities,
not the binary. A candidate artifact does not authorize deployment.
