# Disconnected synthetic SWE-rebench preparation

PCA2 translates only supplied fictional fixtures. It does not implement an upstream
SWE-rebench row schema, prove real-source compatibility, acquire or execute data,
grant rights, or produce a recording. PCA1's declaration contract and corpus v1
remain unchanged. No normalizer is connected to the engine, runner or API.

## Interface

`normalize_swe_rebench(declaration, rows, *, policy, qualifications, now)`
accepts the raw PCA1 declaration, a tuple of `SuppliedRow(candidate_id, raw)`,
a caller-owned `NormalizationPolicy`, and separately supplied
`QualificationReceipt` objects. The declaration is validated by the existing
PCA1 entry point against the caller's current rights/processor/storage/purpose
policy. Only `evidence_class=synthetic` is supported here.

A `NormalizationBatch` contains one `CandidateDecision` for every declared
candidate, in declaration order. Missing or invalid rows and absent, stale or
failed qualification are quarantined. Well-formed unsupported language/state or
size is unsupported. Only a qualified synthetic fixture yields `next-gate`
with separate `InferenceManifest` and `EvaluatorManifest` values. This is
eligibility for later review, never permission to execute. Counts include all
three outcomes. Invalid batch envelopes, duplicate/undeclared associations or
invalid caller policy refuse the entire batch without partial output.

## Explicit synthetic input profile

The closed profile is `swe-rebench-python-synthetic-v1`. Its fields are
`profile`, `language`, `synthetic_created_at`, `state_kind`,
`base_revision`, `instruction`, `base_files`, `evaluator` and
`private_metadata`. The timestamp is fictional fixture creation time in C02's
aware date-time profile, not an interpretation of an upstream `created_at`.
Unknown aliases, omitted values and nulls refuse; no coercion is performed.

The evaluator has exactly `reference_patch`, `test_files`, `command` and
`image_digest`. Private metadata has exactly `repository`, `instance`,
`pull_request_text`, `labels`, `logs` and `image_name`. These fields
exercise routing and contamination controls; they assert no upstream
requiredness, nullability, source rights or actual image contents.

Only Python and file-tree state can reach the next gate. Paths must be normalized
relative paths without controls; source and evaluator paths cannot overlap.
The existing 2,000 combined-file and 8 MiB manifest ceilings are retained as
preparation ceilings. Raw supplied row bytes and their aggregate are each bounded
by 8 MiB; there are at most 1,000 supplied rows/receipts. Instruction and command
limits remain 20,000 and 4,000 characters. Byte limits apply before JSON parsing.
No files are truncated or silently omitted.

## Qualification and current authority

There is no production qualification builder. The caller supplies independently
reviewed receipt digests in `NormalizationPolicy`, the actual normalizer
implementation digest, and current PCA1 policy. The normalizer validates the
receipt's current fields each time, including constructed or mutated instances.
A receipt's syntax and hash alone do not establish review authority; the caller
must independently bind the policy to the installed implementation and its
reviewed receipts.

Each receipt binds the candidate, exact declaration and raw row bytes, pinned
dataset/card, base source/revision, field policy, explicit synthetic schema,
normalizer profile/implementation, processor/purpose, inference payload,
evaluator payload/revision/command/image, and private evidence reference.
Issued/expiry instants must be coherent and current; the caller policy snapshot
must equal `now`. Source bytes are the canonical `{"files": base_files}`
object. Evaluator bytes are the exact canonical private evaluator manifest.
PCA1 source/evaluator/row declarations must agree with these supplied bytes.

Qualification retains at least three outcomes each for original, reference,
invalid and tamper controls. Every original must fail, every reference pass, and
every invalid/tamper control must fail or be rejected. Missing, erroneous,
unknown or contradictory outcomes quarantine the candidate. Answer-blind
context and supported-state reviews must independently be affirmative.
These supplied synthetic receipts demonstrate validation behavior only; the
normalizer does not run a grader or certify those observations.

## Separation and identity

The inference payload contains only a fixed format marker, instruction and
sorted admitted base files. Its cache identity is SHA-256 of those exact bytes.
It excludes candidate IDs, raw-row/declaration hashes, source/evaluator revisions,
image names/digests, hidden patches/tests, PR text, labels, logs and receipt
lineage. Private lineage and the evaluator view remain separate. A caller must
never substitute the entire decision/evaluator serialization for inference.

Separately qualified hidden-field variants with identical admitted instruction
and context produce identical inference bytes/cache identity. Their private
row/evaluator/receipt hashes may differ. A row mutation with its old receipt
quarantines independently. Binding alone does not prove absence of hidden
content in context: that remains an explicit independent qualification duty.

## Validation and limits of delivery

Synthetic controls cover independent golden receipt bindings, all four control
families, stale/tamper/revoked policy, qualified hidden variants, canaries, strict
shapes/duplicates/UTF-8/nonfinite/timestamps, file/path/byte boundaries, complete
ordered denominators and blocked I/O/dispatch. Existing PCA1 and corpus-v1 checks
remain applicable. The new runtime module is explicitly listed in distribution
policy; no baseline or shared planning changes belong to this implementation.

Real rows, source/image qualification, native consumers, rights acquisition,
capture, held-out access, provider calls and production remain separately gated.
