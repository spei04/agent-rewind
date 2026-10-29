# Public candidate declaration contract v2

PCA1 · C02 supplement · offline metadata only

This format describes private pre-recording candidates. It does not establish rights,
qualify source/evaluator content, acquire data, dispatch a model, record a run or make
a checkpoint branchable. The [synthetic example](../../contracts/fixtures/public-corpus.synthetic.v2.json)
is fictional. Its approval, dataset, row and policy references are not real approvals
or acquired records.

## Separate versions and identities

[Corpus v1](CORPUS_PERMISSIONS.md) retains its exact API, schema and synthetic/customer-permitted
recorded declarations. Public candidates use a separate
[closed v2 schema](../../contracts/public-corpus.v2.schema.json) and
[validator](../../agent_rewind/public_corpus.py). Neither validator upgrades or routes
the other version. Version 2 admits only pre-recording-candidates in offline-preparation.
A public recorded format remains unsupported until a separately reviewed native producer
and receipt contract define a **new version**. There is no candidate-to-recorded converter
or native-ID generator.

All fields are required, objects reject extra fields, and no value is nullable.

| Object | Fields |
| --- | --- |
| Manifest | schema_version=2, record_kind=pre-recording-candidates, phase=offline-preparation, corpus_id, created_at, evidence_class, storage_profile_id, storage_owner_id, purpose, retention, publication, candidates. |
| Candidate | candidate_id, workflow_id, dataset, row, source, evaluator, source_policy, permission. |
| Dataset/source | source_id, immutable revision, artifact (private relative path and SHA-256). Dataset artifact means pinned card/declaration bytes; source artifact means declared complete base bytes. |
| Evaluator | evaluator_id, revision, artifact, command_sha256, image_digest. Digests are identities, not executable commands or qualification. |
| Row/source policy | Private path/digest references to exact supplied row bytes and independently reviewed field/provenance interpretation. No row contents are loaded. |
| Permission/retention/publication | The existing C02 types and lifecycle duties, unchanged. Declared approved is not authority. Raw publication is forbidden; aggregates require separate review. |

evidence_class is synthetic or public-derived-declaration. Neither label proves permission.
The two workflow IDs and three purposes remain those in C02. An opaque candidate_id is
private operational metadata; it is not inference context, a native ID or a cache key.
PCA1 does not establish its independent assignment or transitive-content safety. Later PCA2
must prove the required separation/noninterference using independently qualified inputs.

The 1 MiB UTF-8 manifest limit and 1–1000 candidate structural limit both apply; a structurally
valid count can still exceed the byte limit. IDs use the existing ASCII 1–80-character profile;
revisions are 40/64 lowercase hex, SHA-256 is 64 lowercase hex. Private relative paths retain
the existing 1–512-character, normalized-path rules. Do not resolve them as URLs or
percent-decode them. Duplicate candidate IDs and duplicate
(dataset source ID, dataset revision, card digest, row digest) identities refuse, including
row-path aliases. Duplicate JSON members at every depth and nonfinite JSON constants refuse.

Timestamps retain the v1 RFC3339 seconds, explicit offset and optional 1–6 fractional-digit
profile. Invalid calendars, naive/epoch times, leap seconds and UTC conversion overflow
refuse. All policy/time comparisons use UTC instants, including DST folds. Permission
expiry is exclusive; exact expiry refuses. Review/deletion deadlines and deletion no later
than each permission end remain mandatory.

No real upstream requiredness, nullability or timestamp interpretation is inferred here.
Unknown source semantics, missing qualification and unavailable native receipts are not
converted into positive eligibility. The result is declaration metadata only.

## Trusted caller boundary

validate_public_candidate_manifest(raw, *, policy, now) accepts bytes or a UTF-8 string,
a caller-owned PublicDeclarationPolicy and an authoritative aware current time. It returns
PublicCandidateManifest or PublicDeclarationError with a fixed safe code. Direct model
construction does not perform the current policy/rights checks and is not this boundary.

PublicDeclarationPolicy contains:
- admission: existing AdmissionPolicy with requested processor/purpose and approved processor
  and storage IDs; both allowlists are actual frozensets of 1–32 valid IDs.
- reviewed_manifest_sha256: exact raw UTF-8 declaration digest.
- approval_reference: private reference to an independent whole-declaration decision covering
  every rights/source/evaluator/field-policy association.
- rights_status: current, revoked or missing; only current proceeds.
- checked_at: authoritative approval/revocation snapshot instant, equal to now as a UTC instant.

Every current policy field is revalidated, including mutated or model_construct-created
PrivateObject values. The caller obtains actual approval and revocation evidence independently;
a hash, reference shape, model instance or approved flag does not authenticate it. The caller
also owns principal/project authorization and processor account/region/storage configuration.
No registry, resolver, signing service, policy callback or rights lookup is implemented.

A stale checked_at refuses, but matching timestamps do not prove the caller told the truth
or that a live revocation service exists. Changing any declaration byte, including whitespace,
requires a refreshed independent binding. Recomputing an untrusted hash cannot approve it.
Recheck authoritative time and policy on later use; a returned model is not a bearer token.
The current run APIs are not wired to this validator.

## Safe refusal and qualification

Invalid now yields invalid-validation-time; malformed current policy yields invalid-policy.
Invalid raw type/UTF-8/JSON/shape, duplicate/nonfinite members and missing/wrong-type
discriminators yield invalid-manifest, subject to the byte bound. A well-typed unsupported
integer version yields unsupported-version before kind validation; a well-typed unsupported
string kind yields unsupported-record-kind. Bool/string/float versions are not integer aliases.

Other fixed codes are manifest-too-large, duplicate-candidate-id, duplicate-row-identity,
declaration-not-reviewed, policy-not-current, rights-missing, rights-revoked,
manifest-from-future, processor-not-approved, storage-not-approved, purpose-mismatch,
retention-expired, retention-review-overdue, permission-not-active, permission-expired,
retention-exceeds-permission, processor-not-permitted and purpose-not-permitted.

The public validator suppresses private parser/model/calendar diagnostics and exception
chaining. Errors do not contain field locations, IDs, values, hashes or reference paths.
Process-control interruptions retain their original identity. No logging or partial admitted
subset is produced.

Schema parity tests compare the published structural schema to the runtime model. JSON Schema
alone does not enforce duplicate JSON text, current policy, real-calendar/UTC checks,
normalized paths or cross-entry uniqueness. The validator remains mandatory. Focused controls
cover those boundaries, unchanged v1 behavior, safe diagnostics, stale/revoked policy and
blocked I/O/dispatch; synthetic records demonstrate no actual rights or native qualification.

The implementation adds no file acquisition, network call, image pull, dynamic import,
command/build/evaluator execution, model call or Engine integration. PCA2 requires accepted
PCA1 source/merge/review/schema identity. Remaining AR-002-C operating duties, PUBCAP-A native
integration, PUBLICDATA0/G2, capture, funding, held-out and study gates are unchanged.
