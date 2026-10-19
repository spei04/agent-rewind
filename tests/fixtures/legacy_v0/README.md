# Synthetic unversioned history fixture

This is the preservation corpus for AR-005-A and contract C04. It represents the
storage formats at application commit
`8f1ae757005c95c50a789e4fa0a10aae9b3c4024`, before explicit schema revisions.
The source-file checksums in `manifest.json` cover the database, artifact,
engine, model and worker implementations used to review the fixture shapes.

Every value was constructed for this test. No deployment dump, customer trace,
provider request, real credential or private evidence was used. The public
Fernet key in the manifest is deliberately synthetic (`bytes(range(32))` encoded
with URL-safe base64). The two API-key hashes represent synthetic expired keys;
one is also revoked. Never load this corpus into a running deployment.

## Frozen preservation contract

- `baseline.sql` contains explicit historical DDL and literal rows for all five
  original tables. It does not call current application schema creation code.
- `manifest.json` records the SQL checksum, original row values, independent row
  checksums, run IDs, equal fractional creation timestamps, event heads,
  expanded branch event hashes, reservation totals, schema structure and every
  object address and ciphertext checksum.
- `objects/` contains 18 frozen Fernet tokens. Addresses are SHA-256 hashes of
  plaintext bytes. Ciphertext is also pinned, including the original encryption
  timestamp and IV. JSON uses sorted keys, compact separators and UTF-8.
- A complete unsuccessful parent has two steps. Its successful branch forks at
  step two, inherits the first event and adds two events. These are synthetic
  evaluator outcomes, not model or research evidence.
- Three terminal jobs retain reservations of 125,000, 85,000 and 35,000 microUSD
  (245,000 in total). Reservations are historical holds, not measured billing.
  Job payloads and result objects follow the original worker formats.
- Workspaces include file contents, an empty directory, modes and modified times.
  The fixture image and evaluator are synthetic identifiers and must not run.

The checksums are fixed expectations. Do not regenerate the corpus from the
current application to make a migration test pass. A deliberate correction must
be reviewed as a preservation-contract change, with its reason and exact
identity differences. Add a new version for a different historical format.

## Independent variants

`materialize_legacy(destination, variant)` in `tests/legacy_fixture.py` writes an
independent, owner-readable copy into a new directory. It refuses an existing
destination and never changes the checked-in corpus. No symlink or hard link is
used. Mutation descriptors are in the manifest:

| Variant | Expected distinction |
| --- | --- |
| `known` | All five original tables and intact encrypted history. |
| `unknown_schema` | An unexpected nullable column on `jobs`; intact data and objects. |
| `partial_schema` | Missing `audit` and `api_keys` tables; retained tables and objects stay intact. |
| `corrupt_ciphertext` | Original schema and DB rows, but one event object fails Fernet authentication. |
| `corrupt_address` | Original schema and DB rows, but one event object decrypts to bytes that do not match its address. |

Corruption variants share the known schema fingerprint. A matching schema is
therefore insufficient evidence that stored history is healthy. The schema
fingerprint here is a fixture checksum, not the future migration adoption rule.

## Verification and reuse

From the repository root, after installing the pinned development dependencies:

```sh
.venv/bin/pytest tests/test_legacy_fixtures.py -q
```

The tests independently calculate checksums with the standard library, compare
all literal rows, verify each encrypted object, traverse parent/branch history
through the existing reader, validate worker payload shapes, and demonstrate
that changed IDs, times, hashes and reservations fail preservation assertions.

Future migration tests can use `materialize_legacy` and
`assert_preserved_rows(database_path)`. The latter permits new tables while
requiring all original table rows and columns to remain identical. It must be
called after an actual upgrade to establish migration preservation; passing it
on an unchanged fixture does not establish upgrade correctness.

## Limits and remaining validation

This compact SQLite fixture covers data identity and representative malformed
legacy shapes. It does not establish PostgreSQL DDL compatibility, concurrent
migration locking, transactional interruption recovery, writer drain, live
lease behavior, backup restoration, S3/KMS access or production readiness.
AR-005-B must add PostgreSQL adoption and refusal tests against a real temporary
PostgreSQL database, plus explicit locking and interruption tests. No migration
implementation or production schema classifier is introduced here.
