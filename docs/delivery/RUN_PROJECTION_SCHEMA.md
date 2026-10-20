# Run projection schema and catalog review

AR-006-A schema component only. The revision remains migration-only; customer
admission and the live generation-fenced writer remain unavailable.

The additive revision is `ar_0005_run_index`. Its DDL adds `run_index` and the
nonnegative `projects.run_sequence` counter. The run row is bound to its project,
source record and explicit `resource_kind='run'` scope through foreign keys.
The parent foreign key includes the project. Project sequence uniqueness and
positive values are enforced by SQL; commit-order allocation still requires
the project lock held through the caller's complete publication transaction.
The initial projection reason is null or `unfenced_execution`. AR-006-C owns the
later stale-projection repair and restricted audit integration.

## SQLite literal provenance

The explicit DDL was reviewed at source
`9cdf93c8efad88d6d943a65fc29f347b7a2fbd7f`, then corrected at
`4db1975e0f185a3dc36665bfeff7df9a6c71463f` after independent review reproduced
SQLite text length/pattern handling of embedded NUL. New hexadecimal checks
require exact character and byte lengths. Tests require CHECK refusal itself,
rather than relying on a missing foreign-key target.

A fresh in-memory database was migrated to the existing artifact revision,
verified against its accepted literal, then passed through the explicit new
DDL and catalog reader. The resulting 15-table literal is
`agent_rewind/migrations/profiles/sqlite_projection.json`.

- Literal file SHA-256: `d2fd7d0a464d9a22b4644006b915839a74b356b55c62abf8ecb4e3463bfe206d`.
- Canonical catalog SHA-256: `2ff8e4c98648bcb6837baa5f5186f7bb18b78b97f72710647988e67481b661dc`.
- Lead and Engineer A independently accepted the corrected source and catalog.
  Engineer A additionally exercised 12 actual-NUL cases across the four
  hexadecimal fields. All 13 prior non-project table catalogs are unchanged;
  `projects` gains only its counter and associated check.
- The earlier candidate from source `9cdf93c` was rejected as authority and
  remains a private, indexed diagnostic. Historical packaged profiles are
  unchanged.

SQLite reflection does not encode index direction. The catalog reader therefore
also checks the named index through SQLite PRAGMA metadata: exactly
`project_id ASC, created_at DESC, run_id DESC`, binary collation, nonunique and
nonpartial. Replacing it with all ascending columns or another order refuses.

## Remaining evidence

The PostgreSQL literal has not yet been accepted. Its dedicated real PostgreSQL
test captures only bounded synthetic catalog metadata and fails while that
literal is absent. The captured shape must be independently compared with the
accepted artifact catalog and reviewed DDL before a literal is committed.
Tests then compare the actual database shape with that reviewed literal.

Combined cohort/state/backfill, publication integration, PostgreSQL rollback,
concurrency and restore verification remain separate required evidence.
This schema review does not certify those behaviors or production readiness.
