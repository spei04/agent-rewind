# Metadata recovery and application rollback

This guide covers the controlled PostgreSQL 16 metadata profile and its frozen
synthetic history. It does not establish production disaster recovery, a regional
RPO/RTO, point-in-time recovery, online restore, or high availability. Real data,
cloud resources and spending retain their separate approval gates.

A successful restore is not authorization to resume agent work. The current
packaged compatibility profile recognizes `ar_0002_adoption` as migration-only.
Its exact prepared schema returns `incompatible / migration_only` from
`runtime_schema_compatibility(engine)` even when `schema_status(engine)` returns
`prepared` and `customer_ready=false`. An unversioned legacy backup also fails
runtime admission. Ownership, integrity and later activation work remain pending.

## Retain a coherent recovery set

Before an authorized migration, drain APIs, workers, old application credentials
and other writers according to [the migration procedure](MIGRATIONS.md). Preserve
one private recovery record containing:

- The source release/commit, PostgreSQL version, schema status, installation
  identity, source dataset digest and the exact adoption intent.
- A verified custom-format database archive, its byte length and SHA-256, and the
  matching PostgreSQL client version. `pg_dump` backs up metadata, not objects or
  encryption keys. A database transaction alone cannot make a separate object
  store consistent; retain the object set for the same drained history.
- The encrypted object inventory, addresses and ciphertext checksums, plus
  independently retained access to its encryption keys. Preserve ciphertext
  bytes and held reservations; migration does not convert a hold into a charge.
- The separately retained role/ownership and disabled-writer inventory, the drain
  record, access controls, recovery owner and retention requirements. A per-database
  dump does not back up cluster roles or prove old credentials remain disabled.
  See the [PostgreSQL 16 pg_dump reference](https://www.postgresql.org/docs/16/app-pgdump.html).

Keep this evidence outside disposable checkouts and public CI artifacts. Do not
paste connection strings, plaintext history, keys or archive contents into logs.
A checksum binds retained bytes; it does not prove that the backup can restore.

## Decide whether to retry, roll back an application, or restore

| Observed state | Required action |
| --- | --- |
| A migration stopped with uncertain acknowledgment | Keep writers stopped. Inspect schema and persisted installation/adoption identity. If the transaction rolled back, retry the same retained intent against the verified baseline. If it committed, the matching retry returns the existing prepared result. |
| A candidate application must be reverted but storage is unchanged | A binary rollback is allowed only when the previous release's independently reviewed compatibility manifest admits the exact current revision, schema and ownership/integrity state, and its read/write contract has passed fixture tests. Preserve the DB and holds; do not downgrade the schema to make a binary start. |
| The previous binary cannot read the current storage contract, the schema is unknown/partial/future, or history is damaged | Keep admission closed. Investigate the discrepancy and restore a verified coherent recovery set into an isolated clean target. Do not stamp revisions, rewrite fingerprints or bypass guards. |
| Restore failed or was interrupted | Keep the target quarantined and retain the original verified archive. Confirm transaction rollback, discard/recreate an uncertain target through the authorized operator workflow, and retry the same archive. Never treat an exit code alone as restored history. |

No admitted production application rollback pair exists in the current profile.
The current fixture demonstrates preservation and migration inspection after
restore, plus the refusal to resume customer work. A previous unguarded build must
not be used to bypass that refusal. Future releases must add an explicit tested
compatibility pair before claiming safe application rollback.

## Restore into a clean target

1. Validate the retained recovery record and archive/object checksums. Confirm the
   source and target identities are different, the target is isolated, writers are
   drained, and the required roles exist with the intended restricted authority.
2. Use the same supported PostgreSQL major version and a nonsuperuser owner for
   the new metadata target. Keep administrative database creation separate from
   the role performing `pg_restore`. Ensure public schema creation is not granted
   to unrelated roles. Do not overwrite the only surviving source.
3. Restore the verified custom archive using `pg_restore --single-transaction
   --exit-on-error --no-owner --no-acl` with privately configured target credentials.
   The latter flags deliberately require operator-reviewed target ownership and
   ACLs; they do not reconstruct source grants. These transaction and ownership
   options are defined in the [PostgreSQL 16 pg_restore reference](https://www.postgresql.org/docs/16/app-pgrestore.html).
   A verified object backup and key
   access must be restored separately without rewriting content addresses.
4. Compare the recovered rows, event/artifact addresses, timestamps, held amounts,
   object inventory and ciphertext checksums against the retained baseline. Where
   authorized, verify authenticated plaintext hashes against the object addresses.
   Keep all diagnostics free of source content and credentials.
5. Run `rewind migrate status` against the target using the explicit metadata DSN.
   For a restored legacy baseline, inspect its source digest before any explicit
   adoption retry. A prepared backup retains its original provenance record; do
   not replace it with a new mapping or invent new evidence.
6. Evaluate the proposed application's packaged compatibility profile. The current
   release must remain blocked as described above. Switching traffic, re-enabling
   credentials and dispatching work need the later readiness/activation gates;
   restore success alone is insufficient.

There is no destructive downgrade command. Keep an old application available only
as an inert recovery artifact until its storage compatibility is established.

## What the synthetic drill proves

`tests/test_migration_recovery_postgres.py` uses the existing digest-pinned
PostgreSQL 16 service from `.github/workflows/ci.yml`. Its container supplies both
`pg_dump` and `pg_restore`; no second image or host client installation is needed.
The test creates disposable source and target databases. The cluster administrator
creates them; dumps and restores authenticate as their nonsuperuser owner.
Configured PostgreSQL tests fail if the service-container ID or matching tools
are missing. Without the explicit synthetic PostgreSQL configuration, these tests
are skipped locally, not recorded as passed recovery evidence.

The independently frozen fixture contains 14 original metadata rows, 18 encrypted
objects and exactly 245000 microUSD in reservations. Both pre-adoption and prepared
archives are restored into clean targets. Tests compare literal row values and
per-row hashes, the reservation sum, all ciphertext hashes and authenticated
content addresses. The object backup is a separate file copy; this is not a live
object-service backup or a key recovery rehearsal. The restored prepared profile
must still refuse runtime admission.

PostgreSQL 16 renders three enum constraints differently after a dump/restore:
whole-array text casts become per-element text casts. The schema classifier maps
only the six observed native/reflected spellings, bound to their original tables
and constraint identities, back to the frozen original representation. The release
profile and stored schema fingerprint are unchanged. Different enum members,
operators, types, constraint names, validation state or cardinality still refuse.
This bounded equivalence comes from [synthetic run 39349792047](https://github.com/spei04/agent-rewind/actions/runs/39349792047); that failing diagnostic run is not restore acceptance.

A truncated archive must fail without committed target tables, after which the
unchanged valid archive must restore successfully. A second test first restores
schema only, then deliberately holds an exclusive lock on the target `jobs` table.
It starts a real data-only restore, observes the specific blocked backend and
terminates it. All target rows must remain absent after transaction rollback;
retrying the same untouched archive must recover every original row and hold.
The test barrier changes only target locking and restore phases, never the backup
bytes. This establishes transactional data-restore interruption behavior, not
arbitrary host loss, filesystem corruption or a production recovery time.

Cluster roles remain available in the same disposable server throughout this
drill. A new-cluster restore, role reconstruction, private key recovery, remote
backup durability, operator exercises and regional recovery remain separate work.
Hosted test results at the integrated source commit are required evidence; reading
this guide, collecting skipped tests, or passing a migration transaction rollback
test does not establish a completed backup/restore rehearsal.
