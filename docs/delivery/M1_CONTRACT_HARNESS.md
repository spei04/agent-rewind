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

A successful report identifies 5 operations, 50 local references, 12 logical
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

## Narrow M1 reference profile

The checker accepts references only in recognized schema positions: named
component schemas, parameter/header schemas, media schemas in parameter/header
content or request/response bodies, and descendants under `properties`, `items`,
`additionalProperties`, `anyOf`, `allOf` or `oneOf`. References in other OpenAPI
object positions or arbitrary metadata are outside this profile.

Every reference must target a direct named schema at
`#/components/schemas/<name>`, where names use an ASCII letter/underscore followed
by at most 79 letters, digits or underscores. The target must explicitly declare
`type: object` and a `properties` object. Scalar metadata such as `#/info/title`,
non-schema component categories, nested fragments, aliases and non-object target
schemas fail. This matches the current eight named M1 schemas; it is a deliberately
narrow contract profile rather than a full OpenAPI/JSON Schema resolver.

JSON Schema permits boolean schemas, but both `true` and `false` **reference
targets** are explicitly outside this direct-object M1 profile. Existing inline
boolean keywords such as `additionalProperties: false` remain supported. Adding
other legitimate schema or OpenAPI reference forms requires a reviewed profile
extension and semantic regressions, not treating an arbitrary resolved value as
a valid target. FastAPI model parsing alone accepts some references to unrelated
metadata, so it supplements rather than replaces these target/context checks.

## Frozen preservation checks

The suite reads the literal manifest from AR-005-A. It verifies the baseline
commit, explicit synthetic marker, SQL checksum, object inventory/ciphertext
checksums, corruption-file checksums, schema structures and variant fingerprints,
all original row values/checksums, run IDs/timestamps/heads/expanded event hashes,
and the total historical reservations. Schema and corruption variants must
retain their distinct classifications.

Each SQL fixture is evaluated only in an in-memory SQLite database. Input size,
SQL/value lengths, main-database page count and VM work are bounded. Fixture SQL
cannot create TEMP tables, indexes, views or triggers, and cannot access any
non-main database. SELECT-based statements are also outside the fixture input
profile, preventing query-driven temporary materialization; all required frozen
statements use direct DDL and literal rows. Temporary storage is configured in
memory before validation, but that setting is not relied upon as a memory bound.
File attachment, pragmas from fixture SQL, virtual tables, views, triggers and
unapproved SQL functions are denied; extension loading is denied. The checked-in objects are read and
hashed without rewriting them. Tests copy only synthetic fixtures before
mutating them, so failure injection cannot corrupt the known-good corpus.

Ciphertext checksum agreement is not a new encryption or migration proof. The
existing `test_legacy_fixtures.py` independently decrypts the objects and checks
plaintext addresses, event-chain semantics and existing reader compatibility.
PostgreSQL adoption, writer drain, transactional interruption, concurrency and
recovery belong to AR-005-B/AR-012-B and remain unimplemented here. The logical
model's prose constraints and transaction descriptions are not executable DDL.

## Approval-state compatibility

The general inventory remains approval-neutral. The design suite now consumes
[m1.freeze.json](../../contracts/proposals/m1.freeze.json) through the scoped
[review checker](../../scripts/m1_contract_review.py). API/data/acceptance/links/
observability/review records must share revision m1-review-2. All approval states
must agree: pending, or reviewed with an accepted dated reviewer/scope/evidence
record for each BE/PL/FE/RS/QE/SEC/TL consumer. A pending or changes-required review
cannot activate reviewed status. These shape checks do not authenticate evidence;
the lead must verify actual review and record existing user authorization in G0.
The current record remains pending and contains no invented sign-offs.

The review gate supports a future explicit development-scope freeze while keeping
all 24 behavior cases planned-not-executed and production_authorized=false.
Contract review never proves runtime behavior or supplies production authority.
The checker also verifies central observability vocabulary, CSRF, response headers,
retry/sentinel bounds and required ownership/adoption declarations. Logical field
presence is not proof that executable SQL constraints exist. All previous
structural, frozen-fixture and negative checks remain in force.

The reconciled dispositions are in [M1_CONTRACT_FREEZE.md](M1_CONTRACT_FREEZE.md).
The original inventory remains the baseline source record. New PostgreSQL,
storage, authentication and provider tests belong to their implementation owners.

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
