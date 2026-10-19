# Pending M1 contract and fixture validation

AR-012-A · C04 · Structural verification only. The three M1 proposal documents
remain pending, and all 24 CT-M1 runtime acceptance cases remain
`planned-not-executed`. Passing this suite neither approves the proposed design
nor implements a behavior case, migration or production-readiness gate.

## Commands and integration

The existing standard-library entrypoint now validates the proposal inventory,
acceptance links and frozen synthetic fixture together:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_m1_contracts.py
```

The installed project environment adds FastAPI's OpenAPI model validation:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/check_m1_contracts.py --openapi-model
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_m1_contract_harness.py tests/test_contract_inventory.py tests/test_legacy_fixtures.py -q
```

CI runs the installed-FastAPI mode before its existing pytest suite. The
PostgreSQL and gVisor jobs retain their existing commands and scope. No new
dependency, database service, container, model call or cloud resource is needed
for this structural checker. Tests include existing fixture decryption and
reader checks, but the checker itself uses only the standard library unless
`--openapi-model` is requested.

A successful report identifies 5 operations, 41 local references, 12 logical
entities, 5 legacy tables, 20 direct and 2 derived projection mappings, 24
**planned** cases, 14 frozen rows, 18 objects and 5 fixture variants. It reports
approval and behavior status separately; it has no behavior-pass count. Failures
return a nonzero exit code with a contract location, case ID or fixture category
that needs review. Refusal messages omit external reference values and raw
parser/model exception bodies.

## Producer and consumer links

The existing [inventory checker](../../scripts/check_m1_contracts.py) remains the
single implementation of API-reference, operation-ID, path-parameter,
security-scheme, TaskDefinition and response-projection mapping checks. Its
`load(root)` four-item tuple and `check(api, data, models, database)` interface
remain compatible with the original inventory tests. No second inventory was
introduced.

The new [link registry](../../contracts/fixtures/m1-contract-links.json) maps each
case in the [acceptance plan](../../contracts/proposals/m1.acceptance.json) to its
owner, API operation IDs, schema names, logical entities/fields and relevant
[frozen fixture variants](../../tests/fixtures/legacy_v0/README.md). A case can
have no API operation when it concerns a migration, storage, accounting or
legacy-only boundary. Such a case must still map to an applicable schema,
entity, field or fixture. These are design traceability links, not test results.

Every planned case has exactly one mapping. Duplicate/unknown case IDs,
incorrect owners, empty mappings, duplicate link members, unknown operations,
schemas, entities, fields or fixture names fail. A field must name a field of
its explicitly linked entity. Every proposed operation and logical entity must
have at least one acceptance mapping. The mapped API response fields retain the
existing stricter inventory check against their actual logical/legacy columns.

New cases, operations, entities or fields require corresponding reviewed links.
The current case count is explicitly bounded to the reviewed 24-case M1 scope;
changing it requires updating the scoped check and tests during design review.
This does not prevent later milestones from defining additional acceptance
plans with their own scope.

## Frozen preservation checks

The suite reads the literal manifest from AR-005-A. It verifies the baseline
commit, explicit synthetic marker, SQL checksum, object inventory/ciphertext
checksums, corruption-file checksums, schema structures and variant fingerprints,
all original row values/checksums, run IDs/timestamps/heads/expanded event hashes,
and the total historical reservations. Schema and corruption variants must
retain their distinct classifications.

Each SQL fixture is evaluated only in an in-memory SQLite database. Input size,
SQL/value lengths, page count and VM work are bounded. File attachment, pragmas
from fixture SQL, virtual tables, views, triggers and unapproved SQL functions
are denied; extension loading is denied. The checked-in objects are read and
hashed without rewriting them. Tests copy only synthetic fixtures before
mutating them, so failure injection cannot corrupt the known-good corpus.

Ciphertext checksum agreement is not a new encryption or migration proof. The
existing `test_legacy_fixtures.py` independently decrypts the objects and checks
plaintext addresses, event-chain semantics and existing reader compatibility.
PostgreSQL adoption, writer drain, transactional interruption, concurrency and
recovery belong to AR-005-B/AR-012-B and remain unimplemented here. The logical
model's prose constraints and transaction descriptions are not executable DDL.

## Approval-state compatibility

The general inventory function is approval-neutral. `check_pending_proposal`
and `check_proposal_suite` are explicitly **proposal-only** entrypoints that
require pending approval metadata for the current design artifacts. This is a
stage-specific gate, not a rule that a contract can never be approved.

AR-004-B/C can replace that gate in a reviewed freeze revision with checks for
the approved scope, contract revision and actual reviewer/disposition evidence.
That revision must update the link registry, command/CI stage and associated
tests together. It must not bypass the structural inventory or turn a contract
approval into a claim that runtime acceptance cases passed. The separate planned
acceptance checks continue rejecting invented execution status until actual
AR-012-B evidence is implemented and reviewed under its own gate.

The original unresolved decisions in [the baseline inventory](BASELINE_INTERFACES.md)
remain design-review inputs. This harness does not choose CSRF-header,
legacy-project, principal-identity, artifact-ownership or accounting semantics.

## Negative evidence and limits

Tests deliberately break local/external references, case and operation IDs,
owner/mapping coverage, entity fields, source/model parity, approval stage,
behavior status, frozen SQL rows/ciphertext, history identities and unsafe file
paths. They also check duplicate JSON members, nesting/file-size limits and
forbidden SQL I/O. Existing known-good fixtures still pass independently.

FastAPI model validation supplements these checks; it is not a complete OpenAPI
or JSON Schema semantic certification. Structural agreement cannot establish
runtime authorization, effective sandbox isolation, legal data permission,
correct billing, atomicity, deployment health or enterprise readiness. No such
claim is recorded by a passing report.
