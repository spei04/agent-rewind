# Metadata installation and adoption

This release prepares versioned metadata. It does not activate customer access,
create real organizations or projects, backfill ownership, verify encrypted history,
or release budget reservations. Every successful operation returns
`state=prepared` and `customer_ready=false`. Ownership and integrity verification
remain prerequisites for a later release. The application/worker startup guard is
a separate delivery task; do not treat this migration command as that guard.

## Supported profiles and authority

The supported production migration profile is PostgreSQL 16, ordinary permanent
tables in `public`, using the exact historical baseline or this release's frozen
versioned schema. CI pins its PostgreSQL 16 image. Custom schemas, routines,
triggers, rules, views, partitions, foreign tables, row security, altered
collations/indexes/constraints and physical dropped columns are refused. SQLite
supports local development and deterministic preservation tests. Unsupported or
partial state requires investigation and recovery, never automatic stamping or
`create_all`. Checked-in catalog profiles are reviewed release inputs; a database's
own stored fingerprint cannot authorize its shape.

Use a dedicated migration identity that owns the database or public schema.
Declare every former PostgreSQL application role in `legacy_writer_roles` (1–64
distinct unquoted role names, lowercase letters/digits/underscores) within the private adoption mapping. Disable each role with
NOLOGIN and NOSUPERUSER, drain its existing sessions, and remove application-role
membership paths. The current migrator cannot be a declared legacy writer. This
explicit operator inventory is bound into persisted intent; the database cannot
discover historic role purposes. SQLite requires an empty/absent role inventory
and its process/OS drain procedure.

Application identities must not own either, have schema creation authority,
inherit or assume a writer role, or use a superuser. PostgreSQL's cluster
administrators remain trusted control-plane authorities outside the application's
security boundary; database locks cannot protect against malicious administrators.
Every other session in the target database blocks migration, including superusers,
background sessions and sessions with restricted activity visibility. Retry after
the operator has genuinely drained these sessions. The migration command does not
terminate sessions, revoke credentials or guess which processes belong to an app.

Table locks are held across classification, stamping, DDL, provenance insertion
and commit; advisory locks serialize migrators. They complement the durable
revocation of legacy writer authority, rather than proving that credentials stay
disabled after commit. Timeout defaults to five seconds and is bounded to 1–30;
statement execution is bounded separately. SQLite takes an exclusive transaction
with the same bounded wait. Concurrent writers/migrators fail with `migration_busy`
or a drain/privilege diagnostic. Do not retry by disabling these checks.

## Read-only inspection

Migration commands load only metadata connection settings; artifact decryption,
model-provider and identity-provider secrets are neither required nor read by the
migration configuration. An explicit DSN is required; with only the migration DSN,
status uses that connection read-only.

Use `rewind migrate status`. `--source-digest` additionally streams known legacy
rows into a stable source digest, with one-million-row, one-GiB-total and
16-MiB-per-row limits. Oversized or invalid content is refused. Digests bind values,
not encryption keys or private row content. Inspection never initializes a missing
SQLite file, changes database contents, adopts a schema or reveals credentials.
The Python interface `schema_status(engine)` exposes the same read-only result for
the later startup guard. Database errors cross the CLI as fixed diagnostic codes.

## Empty installation

Set the ordinary `REWIND_DATABASE_URL` and separately configure the private
`REWIND_MIGRATION_DATABASE_URL` for PostgreSQL mutations. Keep credentials out of
command history and source control. `rewind init` creates local secret placeholders;
it does not initialize metadata unless an installation key is supplied explicitly.

```sh
rewind migrate status
rewind migrate install --installation-key my-installation
rewind migrate status
```

Retain the installation key with the deployment record. Repeating the same fresh
installation is a no-op; a different key or legacy origin is a conflict. No legacy
backup/drain evidence is invented for a fresh database. A subsequent
`rewind migrate upgrade` accepts only known versioned state and this release's
explicit target revision. The compatibility Python helper `Database.migrate`
requires an installation key for empty initialization; without one it only upgrades
known versioned state and never implicitly adopts legacy data.

## Explicit historical adoption

Before adoption, stop old APIs, workers, credentials and background writers, take
and verify a recoverable database and object-store backup, and keep the encryption
key in its existing private backup process. Terminal job state is required;
`running` with an expired lease is still nonterminal. Existing reserved amounts
remain holds, and are never interpreted as charges or released by migration.

Prepare a private owner-readable regular JSON file (0600, no symlink/FIFO), at most
one MiB. The mapping binds one installation, the inspected source dataset digest,
one proposed organization/project, principal grants and API key dispositions.
IDs are 32 lowercase hex characters and digests 64. OIDC principal IDs use a
64-character stable subject digest. This synthetic example is illustrative:

```json
{
  "schema_version": 1,
  "installation_key": "example-installation",
  "source_dataset_digest": "0000000000000000000000000000000000000000000000000000000000000000",
  "organization_id": "88888888888888888888888888888888",
  "project_id": "99999999999999999999999999999999",
  "selector": "all-verified-legacy-resources",
  "principal_grants": [{
    "principal_id": "oidc:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "role": "maintainer",
    "legacy_default": true
  }],
  "key_dispositions": [],
  "legacy_writer_roles": ["retired_application_role"]
}
```

Empty key dispositions mean no key access is granted by this preparation. An
explicit API-key grant must match a disposition for an existing key. Unknown
members, duplicate grants/keys and duplicate JSON members are refused. The two
evidence digests below identify separately retained private backup/drain records;
the CLI checks their format and binds them durably, but cannot attest that an
operator performed an honest backup or a complete process inventory.

```sh
rewind migrate adopt --mapping /private/adoption.json \
  --backup-evidence <sha256-of-verified-backup-record> \
  --drain-evidence <sha256-of-writer-drain-record> --lock-timeout 5
```

A matching retry after uncertain acknowledgment returns the same prepared state.
Changed source rows, mapping, installation identity or evidence refuse. Original
rows, timestamps, event IDs/hashes, encrypted object addresses/bytes and reservation
amounts remain untouched. No object is decrypted or rewritten here. Consequently,
corrupt ciphertext, address mismatches or orphan history can be schema-prepared,
but cannot be represented as verified or activated. Later ownership/integrity
work must quarantine or refuse these before any customer access.

## Failure, recovery and evidence

A failed transaction rolls back both Alembic stamping and new metadata DDL. A
process killed before commit leaves the original baseline; one killed after commit
leaves the full prepared state. Inspect, then retry exactly the retained intent.
Do not edit the revision table, regenerate fingerprints from the target database,
or use an unverified downgrade. This release deliberately supplies no destructive
downgrade. Restore only the separately verified backup in a drained environment,
verify the literal original rows and object checksums, then inspect before retry.
Re-enabling old writer credentials is not part of recovery or migration success.

`installation_adoptions` contains one immutable origin/mapping/evidence record.
`migration_progress` provides bounded resumable phase metadata for the later
ownership migration; no ownership/backfill phase is marked complete by this slice.
Neither table grants customer access. Hold data and encrypted history are not
converted by this revision.

The SQLite suite exercises real migration/refusal, concurrent writers, interruption
and backup restoration against the independently frozen 14-row/18-object fixture
with 245000 microUSD held. Hosted PostgreSQL tests use separate nonsuperuser
migration/runtime roles, frozen row checksums, schema/privilege negatives, bounded
locks and actual process termination. A missing PostgreSQL catalog profile causes
a bounded synthetic catalog review failure, not automatic acceptance or profile
writing. The profile must be reviewed, committed and tested before this slice can
pass its release gate. Tests and review do not constitute external certification.

### Frozen PostgreSQL profile provenance

The initial PostgreSQL 16 catalog was captured from synthetic, newly created
schemas in hosted run `39346994753`, jobs `118381880748` (Python 3.11) and
`118381880855` (Python 3.12), source `6d68117a2d8a449d5f32e19502511e05d4421612`.
Both captures have identical compact sorted JSON SHA-256
`0483e636e219af53d2ec28ad0c73b0b98bf217fd8948fc29ea912b529a6480ff`.
Internal platform/quality review checked the static catalog against all baseline
columns/constraints, physical columns/indexes and the additive revision DDL.
The checked-in literal profile is reviewed against the explicit revision DDL;
it is not regenerated from the target database during validation. These initial
capture runs intentionally failed and do not establish migration acceptance.
The PostgreSQL image is the digest pinned in `.github/workflows/ci.yml`.
