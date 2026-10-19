# Private corpus permission and provenance contract

AR-002-A · C02 permission/provenance portion · Ready for internal review.
No customer data, customer authorization, legal approval, acquisition or model
experiment is supplied by this change. The remaining C02 failure taxonomy,
held-out split and evaluator-stability protocol belongs to AR-002-B.

The two supported [workflow IDs](WORKFLOWS.md) share this admission contract.
A private corpus records who controls each task, which source and evaluator
identities are intended, where its evidence belongs, and which specific model
processor may receive it for a declared purpose. Public fixture metadata is
entirely synthetic and must not be treated as a permitted customer corpus.

## Versioned representation

The [JSON Schema](../../contracts/corpus-manifest.v1.schema.json) specifies
version 1 syntax. The [synthetic example](../../contracts/fixtures/corpus-manifest.synthetic.json)
covers both supported workflows. Source and evaluator artifact digests in that
example match the trusted C01 examples; its zero revisions, run IDs, permission
references, policy references, storage profile and people are placeholders.
There are no corresponding approval files or approved deployment resources.

| Field | Required meaning |
| --- | --- |
| `corpus_id`, `created_at`, `schema_version` | Stable corpus identifier, timezone-aware creation instant and explicit format version. |
| `evidence_class` | Synthetic fixture or declared customer-permitted material; the latter label is not proof of permission. |
| `storage_profile_id`, `storage_owner_id` | Reference to a separately approved private storage configuration and its accountable owner. |
| `purpose` | Exactly one of debugging, intervention screening or independent confirmation. |
| `retention` | Accountable owner, future review instant and mandatory deletion deadline. |
| `publication` | Raw content forbidden, aggregates require separate review, and a versioned private redaction-policy reference. |
| `tasks[].task_id`, `workflow_id`, `run_ids` | Unique task identity, supported workflow and unique recorded run identities. A run cannot belong to two entries. |
| `source` | Source identity, full 40- or 64-hex revision and private artifact path plus SHA-256. Branch names are insufficient. |
| `evaluator` | Evaluator identity/revision, artifact digest, exact command digest and pinned image digest. |
| `permission` | Recorded approved status, rights owner, approver, approval instant, validity interval, permission-evidence reference, allowed processors and allowed purposes. |

An object reference is a normalized relative key within the approved storage
profile, paired with a lowercase SHA-256 digest. It is not a URL or host path.
Absolute paths, traversal, ambiguous separators, backslashes and control
characters are rejected. Consumers must not reinterpret percent sequences or
turn relative keys into URLs. Resolving a reference and checking the bytes
against its digest is separate from validating the reference's syntax.

A processor identifier names the reviewed vendor **and** account, region and
retention configuration. A vendor-wide name must not be reused to imply that
all accounts or regions are approved. The private profile registry must hold
those details; putting API credentials, signed URLs or private text in this
manifest is outside the contract.

The initial public-export policy is deliberately restrictive: raw task, run,
evaluator, permission and redaction-policy content is never publishable through
this contract. An aggregate report still needs a separate disclosure review;
passing a redaction rule is not publication authorization. This does not prevent
publishing the explicitly fictional examples in this repository.

## Admission boundary

`agent_rewind.corpus.validate_corpus_manifest` is a pure offline validator. It
accepts manifest JSON, a caller-owned `AdmissionPolicy`, and an authoritative
current timezone-aware time. The policy supplies the requested purpose,
requested processor ID, approved processor IDs and approved storage profiles.
These allowlists must come from trusted configuration, never from the submitted
manifest or request body.

```python
from datetime import UTC, datetime
from agent_rewind.corpus import AdmissionPolicy, validate_corpus_manifest

policy = AdmissionPolicy(
    processor_id="synthetic-model-region-a-no-retention",
    approved_processors=frozenset({"synthetic-model-region-a-no-retention"}),
    approved_storage_profiles=frozenset({"synthetic-private-storage"}),
    purpose="independent-confirmation",
)
# raw_json comes from an already authorized private metadata read.
manifest = validate_corpus_manifest(raw_json, policy=policy, now=datetime.now(UTC))
```

The example is illustrative. It does not grant those synthetic profiles access
to any resource and will stop admitting its example after the review deadline.
Tests use a fixed explicit time so they do not silently extend permissions.

Validation rejects missing/unknown fields, malformed IDs, unsupported versions,
missing permissions, non-approved status, duplicate JSON members, duplicate task
or run IDs, invalid hashes/paths, future approval or validity starts, expired
permissions, elapsed retention/review deadlines, deletion beyond permission
expiry, unapproved storage/processors and purpose/processor permission mismatch.
Expiry is exclusive: a permission with `valid_until == now` is expired. It also
rejects manifests larger than 1 MiB; lists are capped at 1,000 tasks and 100 runs
per task. Errors expose stable safe codes without private field values.

JSON Schema checks syntax only. Time comparisons, caller-owned allowlists,
normalized paths and cross-entry uniqueness require the Python admission
validator. Do not substitute schema validation alone for admission.

## Approval and lifecycle responsibilities

A structurally valid manifest is a declaration. The accountable corpus owner
must separately confirm that the referenced permission exists, covers the exact
source/evaluator and intended processor/purpose, remains valid, and has not been
revoked. An approver ID or `approved` string is not a signature or an independent
approval record. Source and evaluator object hashes must be verified when bytes
are loaded. Actual contractual interpretation and customer approval remain with
the responsible human owners.

Before any future ingestion or dispatch integration, its caller must:

1. Authorize the principal and project, obtain the current approval/revocation
   record and trusted processor/storage policy, and use the current server time.
2. Validate the manifest, resolve only approved private references and verify
   their actual content digests. Do not log the manifest or parser exception
   context, and do not use an expired earlier validation as an admission token.
3. Recheck permission and policy before new model processing and when resuming
   an experiment. A newly revoked grant must stop new use even if its stored
   expiry is in the future. No processor fallback is implicitly permitted.
4. Enforce approved storage access/encryption, retention review and deletion in
   the storage/operations layer; route any proposed aggregate publication to a
   separate review. Keep actual manifests and evidence outside this public repo.

Those integrations are prerequisites for using this contract with real data.
This change performs no network I/O, file resolution, ingestion, model calls,
revocation lookup, deletion, export or publication. It does not add an admission
check to existing run APIs. Existing run APIs therefore do not yet enforce this
private corpus contract. Do not claim a safe customer-ingestion path from these
unit tests alone.

## Verification

`tests/test_corpus_manifest.py` checks both synthetic workflows, source/evaluator
identity agreement, JSON Schema parity, missing and expired rights, duplicate
IDs, unsafe paths, malformed digests, processor/purpose/storage restrictions,
exact time boundaries, retention revalidation, duplicate JSON members, size
bounds and safe errors. No private file, cloud resource or model provider is
read or called. The examples are contract fixtures, not natural-failure or
causal-effect evidence.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider tests/test_corpus_manifest.py -q
```

Internal review should check provenance completeness, caller-owned policy,
refusal behavior and the distinction between declared and verified approvals.
Actual customer/corpus admission stays pending until the corresponding private
permission records and integration controls are available.
