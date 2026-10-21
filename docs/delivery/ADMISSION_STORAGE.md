# Admission storage foundation

AR-008-A/P2 is **Verified** after [PR #90](https://github.com/spei04/agent-rewind/pull/90) merged reviewed `4135c6f` as `41759bb`, matching PR/main checks passed and the lead verified candidate 12324805344. See [accepted P2 delivery](ADMISSION_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21).
This package adds storage constraints and connection-bound primitives for the
later P3 coordinator. It supplies no HTTP admission, worker dispatch, budget or
generation schema, upload coordinator or customer-ready profile. Existing
release guards remain migration-only.

## Revision and preserved history

The next linear revision is `ar_0006_admission`, after `ar_0005_run_index`.
Its operator initializer requires the exact predecessor catalog and completed
ownership/run-index progress. Before first advancement it binds the current
bounded metadata-only cohort to the completed ar5 source/scope/order/cohort
identity. It does not read artifacts, reclassify results or reset progress.
DDL, installed fingerprint and version stamp share the existing excluded
migration transaction. An unreviewed or unavailable catalog literal refuses.

The revision adds only operations, operation_keys and three job columns:
payload_version (default 1), execution_config_ref and execution_config_digest.
The catalog bound becomes exactly 17 tables, with an 18th-table refusal sentinel.
Existing literal profiles, original COLUMNS and source-profile checksums remain
unchanged. Historical jobs use their original thirteen-column digest projection;
configuration defaults never enter that hash or rewrite original source rows.
The initializer verifies that original source digest again after DDL.

Exact ar6 reentry checks the installed catalog and durable predecessor
progress/provenance without resetting either. It does not pretend later
authorized job rows are still the original backfill cohort. Historical jobs
retain version 1 and both configuration columns NULL; those values are
read-only compatibility, not permission to dispatch them.

## SQL guarantees and repository obligations

SQL separately constrains the unique job ID and the scoped
(project, principal, kind, client_operation_id) identity. The operation references
both the actual jobs row and its same-project job scope. Aliases use the full
(project, principal, kind, operation_id) foreign key and a scoped key-hash primary
key. No membership foreign key can destroy replay history after revocation.

Accepted is physically canonical TEXT containing exactly the operation's
original operation_id and job_id. Its CHECK binds both values to that row.
This changes no frozen response shape. The new identifier/principal constraints
include SQLite type and byte-length checks; embedded NUL cannot hide a suffix.

Job configuration references and digests are 64-character content identities;
artifact object IDs remain 32 characters. Their equality is not an artifact
foreign key or upload receipt. The common bounded repository checker must prove
actual job -> project scope -> job/admission_config reference -> object metadata,
including exact descriptor identity, format, scoped locator and digest.
It must work for configured version-1 jobs without an operations row.
Every new writer must require configuration, including a future legacy writer;
SQL's historical version-1 NULL allowance alone cannot distinguish a new rogue
insert from a retained row.

The composite alias FK does not prove request_digest equality; that comparison
belongs to the same-Connection repository. P3 owns current caller/corpus authority,
both recovery identities before mutable configuration/storage, verified upload
receipts, project-before-grant/key/job locks, atomic publication and uncertain
commit reconciliation. Prepared bindings and these SQL checks are not committed
authority.

The physical timestamps are DATETIME/TIMESTAMPTZ with an ordering CHECK. Finite
aware UTC parsing, chronological order and the initial retention floor of at
least 90 days are bounded repository obligations; SQLite textual ordering and
PostgreSQL's timestamp type alone do not prove them. retain_until is not replay
eligibility or an automatic expiry. This package deletes nothing; retention
through operation lifetime plus 90 days remains a future deletion-policy duty.
Nullable failure correlation preserves schema compatibility; every new P3
operation must supply its trusted first origin, which replay/alias binding
cannot overwrite.

## Reviewed SQLite literal and evidence boundary

The exact SQLite literal is packaged as
`agent_rewind/migrations/profiles/sqlite_admission.json`.
Engineer B independently reviewed its DDL and catalog-source hashes against
`a5918c7`; lead authorized freezing these exact bytes.

- File SHA-256: `2f67620749cda91728bfaa86c921a4ea65b67ea1d9f7f99a1205c41c481a9aac`.
- Size: 33,071 bytes. There are exactly 17 tables. All 14 non-jobs predecessor
  entries and the original 13 job columns, indexes and foreign keys are unchanged.
- Only operations/operation_keys and the three job columns/two job checks are new.
  Historical packaged profiles are unchanged. The private candidate and index
  are owner-readable and identify source, purpose and review date 2026-11-20.

The DDL checkpoint passed 62 SQLite constraint/rollback cases. The next
source/catalog checkpoint passed 132 combined admission/projection/preservation
cases. Fixed initializer error mapping at `162ba6b` passed five catalog cases,
including real oversized-cohort and query-budget refusal without revision/source
changes or a raw exception chain. Eight additional initializer cases verify exact
reentry, completed-cohort drift refusal, old-reader refusal and full rollback
after DDL or fingerprint update. The unchanged fixture retains all 14 historical
rows, 18 ciphertexts, literal event heads and 245000 reserved units; projection
rows/progress/counters are unchanged.

The connection-only repositories have 36 SQLite behavior cases at `dc250f4`.
They do not own commit or publication exclusion. Every metadata read caps
candidate cardinality at two and CASE-bounds selected cells before driver
materialization. Missing/malformed/extra config refs are retained as refusal
candidates, not filtered away to produce false uniqueness. All seven original
descriptor fields are compared for prepared task/config/payload associations.
Finite UTC timestamps and the initial 90-day floor are validated on insert/read.
Typed authentication/authority denials remain separate from fixed storage errors.
No retention timestamp makes replay expire.

## Hosted PostgreSQL capture contract

`tests/test_admission_schema_postgres.py::test_postgres_admission_profile_requires_independent_freeze`
uses only the existing opt-in disposable PostgreSQL 16 fixture. It completes the
accepted ar5 backfill, snapshots projection/progress/counters and bounded cohort
identity, executes raw ar6 DDL in the existing excluded migration transaction,
and rechecks original rows/hash projection/cohort/defaults and table deltas.
It does not install a guessed literal or declare the raw DDL a valid installation.

Until a PostgreSQL literal is independently reviewed and packaged, the test
deliberately fails with the fixed marker
`SYNTHETIC_ADMISSION_POSTGRES16_CATALOG_REVIEW_REQUIRED=`.
Its canonical JSON payload is capped at 192 KiB and contains only synthetic
catalog metadata, the preserved cohort digests/count, predecessor catalog hash,
validated CI source SHA and hashes of the exact DDL/catalog/revision sources.
No DSN, role credential, row body, artifact plaintext or production data is
emitted. Lead retrieves that existing CI log output into indexed private evidence
for independent comparison and freeze authorization. Subsequent matching-source
tests compare the actual catalog to the reviewed literal and exercise the real
initializer. This capture is a review aid, not automatic profile acceptance.

The reviewed PostgreSQL literal is now packaged as
`agent_rewind/migrations/profiles/postgresql16_admission.json`. Hosted capture
run [39547523509](https://github.com/spei04/agent-rewind/actions/runs/39547523509)
at published source `86938b1d6fa451c8c19a6f00a956c6eacbe4e9d6` tested merge
`1201d4fe40bfc444a789570f1325a88ddc52d1b4`. Python jobs 119048965928 and
119048966175 produced byte-identical candidates. Lead verified the tested
source/tree and three DDL/catalog/revision hashes; Engineer B independently
accepted the exact catalog and native constraint semantics before freezing.

- File SHA-256: `970a99d22a06b38c9fb6036a0199d4a1a35d63004b335635359478adc7fc5eef`.
- Size: 79,455 bytes; canonical catalog SHA-256:
  `b94d8e1e8a65614122bfa6bcab5695d68f480305196a42116b018c9b2abfd442`.
- Exactly 17 tables plus the native `$postgres` catalog entry. All 14 prior
  non-job tables/native rows and original 13 job columns are preserved. Only
  the reviewed three job columns/two checks and operations/operation_keys are new.
- The private source/provenance/candidate records remain owner-readable outside
  checkouts, with source, purpose and review date 2026-11-20 recorded.

The capture run failed and is not runtime or release acceptance. Its deliberate
missing-literal gate, dependent missing-profile fixture and stale exact revision
expectation are now resolved in source; the separately reported S608 query rule
was corrected at `af24c727`. The exact fifth release expectation at `9ab73f2`
retains ar6 migration-only status and both completed ownership/run-index phases.
The next matching hosted run must compare the literal, execute the initializer,
repository/contention/backup/restore cases and isolated package smoke, and pass
all required checks. P2 is unverified; P3 and customer admission remain unavailable.

The package allowlist includes the two repository modules, two admission migration
modules, revision and both exact reviewed literals. Installed smoke reads each
packaged literal and advances an
explicit empty ar5 installation to ar6, checks exact reentry and missing/scoped
identity reads, and proves no operation/alias rows were created. It retains the
final migration-only refusal. The exact smoke helper plus delivery helper cases
pass 45 local tests; two actual-PG capture/initializer cases are explicitly skipped
locally. This source-helper result is not isolated wheel/sdist execution evidence.

## PostgreSQL migration and restore test boundary

The separate `test_admission_migration_postgres.py` suite covers incomplete
projection refusal, completed source/scope/cohort drift, rollback after DDL and
fingerprint update, runtime-role and effective-autocommit refusal, and the
17-table limit's eighteenth-table sentinel. It uses the existing disposable
PostgreSQL fixture and observes setup connections draining before the unchanged
single-attempt migration guard. These 11 cases are locally skipped explicitly;
they require the independently approved PostgreSQL literal and hosted execution.
Only the mandatory catalog-capture test deliberately fails while that literal
is absent; dependent execution tests skip pending review.

The restore test preserves each of the original 14 row/hash identities and all
18 ciphertext bytes separately from a complete SQL snapshot containing a new
synthetic job, operation, alias, three object descriptors and scoped references.
It preserves the original 245000 reserved units, run heads, projection rows,
progress and counters. The new job uses the already-adopted maintainer and leaves
the frozen grant inventory and all original job actors unchanged. After restore,
old v1 NULL configs remain unavailable to the common config checker, the exact
new identities/config association resolve, an ar5-only reader refuses ar6, and
initializer reentry remains migration-only. The new object metadata is a SQL
association fixture, not verified upload or available-byte evidence. `pg_dump`
does not back up objects, encryption keys or roles; the historical encrypted
objects are copied and verified separately.

The composed local admission-storage selection passed 117 cases with 33 explicit
PostgreSQL skips. A small SQLite probe also exercised the restore fixture's new
identity setup, exact row snapshot and initializer reentry; it did not execute
PostgreSQL or backup/restore. Actual PostgreSQL schema, contention, restore and
installed-distribution acceptance remain hosted gates, not these local results.

With the exact reviewed PostgreSQL literal packaged, the focused initializer,
catalog, package-helper, compatibility and delivery selection passed 128 tests
with 33 explicit local PostgreSQL skips and one existing Starlette warning.
Configured lint, security rules, formatting and strict typing passed. All eight
predecessor profiles and eighteen frozen contract files remain byte-identical.
These local checks do not replace matching hosted PostgreSQL or installed-package
execution.

## Actual ar6 process interruption evidence

Three additional opt-in PostgreSQL cases execute the real initializer in a child
process and kill that process with SIGKILL after completed ar6 DDL, after final
fingerprint validation before commit, and immediately after acknowledged commit.
Each requires both its exact flushed phase marker and the SIGKILL return code;
other failures expose only the existing bounded refusal diagnostic. The child
has a 30-second deadline, and the separate control database observes backend
exit before fresh connections inspect or retry. No migration retry hides refusal.

The snapshots include actual alembic_version and installation_adoptions row
contents, full catalog, historical source/rows, all progress, run index/counters,
project/grant/scope and artifact metadata. Precommit death must leave exact ar5
state; acknowledged commit must leave the exact reviewed ar6 catalog and matching
fingerprint. Recovery and a second reentry use an independent NullPool engine,
preserve the source and 18 ciphertexts, leave identities empty and v1 configs
NULL, and remain migration-only. These are P2 DDL interruption tests, not P3
upload/publication or uncertain-operation recovery. Actual PostgreSQL execution
is required; local collection/skips cannot prove these assertions. The later PR
execution evidence is recorded in the current delivery checkpoint below.

The unchanged migration exclusion is also covered by the existing PostgreSQL
writer-authority, hidden-session, advisory/table-lock and observed-backend-drain
tests in test_migrations_postgres.py. The ar6 child invokes that same guard once
with the existing safe diagnostic wrapper; it neither retries nor relaxes it.

The interruption handoff passed 42 local initializer/catalog/diagnostic tests;
all 14 PostgreSQL migration cases skipped explicitly. The exact child program
compiles and focused lint/format/whitespace checks pass. No child PostgreSQL
execution or successful interruption/recovery is claimed from these checks.

Current delivery ownership and completed evidence are recorded in
[accepted P2 delivery](ADMISSION_EXECUTION_PLAN.md#accepted-p2-delivery--2026-10-21).
PR/main runs 39550589433/39552010828 passed actual PostgreSQL and installed-package
checks; the lead verified the exact candidate. Aggregate AR-008-A stays In
progress. C owns P3, with B security/source review and A independent PostgreSQL
tests after a stable interface; coordinator acceptance remains outstanding.
