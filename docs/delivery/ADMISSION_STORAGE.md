# Admission storage foundation

AR-008-A/P2 is in progress in [PR #90](https://github.com/spei04/agent-rewind/pull/90).
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

## Evidence boundary

The first DDL checkpoint passed 62 SQLite constraint/rollback cases. The next
source/catalog checkpoint passed 132 combined admission/projection/preservation
cases, including the unchanged 14-row, 18-ciphertext, literal-head and 245000-unit
fixture, exact projection rows/progress/counters and the 18th-table refusal.
The SQLite candidate has 17 tables, unchanged entries for all 14 non-jobs
predecessor tables and only the three job-column additions; it remains subject
to independent literal review. No PostgreSQL execution, backup/restore acceptance,
completed repository or P2 acceptance is claimed at this checkpoint. Actual
hosted PostgreSQL and independently reviewed profiles remain required.
