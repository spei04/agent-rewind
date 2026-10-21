# Native admission foundation

AR-008-A/P1 is Verified after [accepted PR #85/main/candidate evidence](ADMISSION_EXECUTION_PLAN.md#accepted-p1-delivery--2026-10-21) and provides pure preparation for a new native-run operation. It performs
no SQL, artifact upload/read, HTTP admission, readiness probe, image discovery or
provider call. Existing routes and migration-only profiles are unchanged.
P2's additive durable schema is Implemented; verification pending after merged PR #90;
protected-main/candidate acceptance remains with lead delivery. See the
[current P2 checkpoint](ADMISSION_EXECUTION_PLAN.md#p2-merged-verification-pending--2026-10-21).
P3 remains Not started and owns authorized recovery, receipt verification and
atomic publication. This foundation does not establish either later package's verification.

## Request and task identity

`admission_request.parse_submit(raw: bytes) -> CanonicalIntent` accepts exactly
the frozen SubmitRun fields. The client must supply a 32-character lowercase-hex
client_operation_id, native-v1 adapter_config_id, TaskDefinition, integer seed
(0 through 2^31−1) and integer budget_microusd (1 through 200,000,000). Unknown or
duplicate JSON members, invalid UTF-8, noninteger JSON numbers, nonfinite values,
booleans in integer positions and malformed task/path shapes refuse with fixed
codes. Neither the JSON parser nor an error includes raw input in its public
message.

These limits have different meanings:

| Limit | Boundary |
| --- | --- |
| 9 MiB | Raw UTF-8 request bytes, checked before JSON decoding. The future HTTP adapter must also bound streaming input and reject non-identity content encoding. |
| 8 MiB | Complete canonical legacy TaskSpec, after task defaults, seed and budget_usd are materialized. |
| 2,000 | Combined source and evaluator file count. |
| 64 KiB | Canonical native configuration plaintext. |
| 4 KiB | Generated schema-2 envelope plaintext. |

The full canonical SubmitRun wrapper has no separate 8 MiB semantic limit: an
exactly 8 MiB TaskSpec remains valid when the small wrapper is included. The
canonical encoding is the existing `models.canonical` JSON encoding, including
ASCII escaping, sorted object keys and materialized TaskSpec defaults. The
implementation measures escaped output before allocating it. Source text,
Unicode representation, image alias and list order remain unchanged. Source and
evaluator file values remain strings; P1 adds no client file-mode field.

`CanonicalIntent` retains detached immutable request/task bytes and their
separate SHA256 digests. Defaults are max_steps=30, command_timeout=30 and
redact_patterns=[]. No seed or budget default is inferred. Integer microUSD is
converted to budget_usd only for the legacy TaskSpec reader; converting that
float back to rounded microUSD must recover the original integer. All future
ledger arithmetic uses the integer value, never this compatibility float.

## Explicit immutable configuration

`NativeConfiguration(canonical_bytes, expected_digest=...)` imports exactly
canonical schema-1 bytes, bounded before parsing. Pretty/noncanonical JSON,
unknown/duplicate members and unsupported versions refuse. The external digest
must equal SHA256 of the entire canonical configuration. Every field is
required; current Settings are never consulted.

| Fields | Meaning and accepted form |
| --- | --- |
| schema, kind | Integer 1 and native-v1. |
| image_identity | Immutable SHA256 image identity: sha256: followed by 64 lowercase hex characters. Tags/aliases are not executable identities. |
| endpoint_profile, endpoint_revision | Opaque identities for one immutable server-owned endpoint mapping and revision; URL/userinfo/query syntax is rejected and credentials must never be supplied. |
| model_revision, processor_profile, price_version | Opaque bounded identities. |
| adapter_digest, prompt_digest, tool_policy_digest, configuration_digest | 64-character component/input digests. configuration_digest is not a self-hash of this object. |
| max_input_tokens, max_output_tokens | Strict integers in the existing adapter ranges, 1,000–1,000,000 and 1–128,000 respectively. |
| reasoning_effort | Existing finite options: empty string, none, minimal, low, medium, high, xhigh or max. Empty means omit the option. |
| seed_supported, seed_strategy | Boolean and trial-plus-step-mod-2147483647, matching the current step seed formula. The seed is sent only when supported. |
| input_microusd_per_million_tokens, output_microusd_per_million_tokens | Positive signed-64-bit integers; rates are microUSD per million tokens, not floats or a rounded reservation. |

Opaque identities use 1–128 ASCII letters/digits/dot/underscore/hyphen characters,
beginning with a letter or digit. This grammar is not a secret detector: trusted
server composition must supply mapping identities, never credential values. The
future worker must verify the exact
endpoint profile/revision mapping, model/image identity and installed component
digests before dispatch. Reusing a mutable endpoint alias under an unchanged
revision would violate that contract. P1 neither deploys nor verifies such a
mapping.

`NativeRegistry(entry | None, image_aliases)` holds at most one immutable entry.
It copies aliases into a tuple, limits the collection to 128 distinct exact
strings of 1–300 characters, and bounds their aggregate canonical encoding at
64 KiB. Thus configuration plus aliases retain at most 128 KiB of encoded
material. Embedded NUL, invalid Unicode, mutable nested values and duplicate
aliases refuse. An absent entry requires an empty alias collection. Replacing
configuration means constructing a new explicitly supplied server snapshot;
there is no registry endpoint, reload service or Settings fallback.

`resolve_new(adapter_config_id, task_image, permitted_processor_profile=...)`
requires an exact registered alias and processor-profile equality. It preserves
the client's image alias in the task bytes. The supplied permission is trusted
internal policy data, **not evidence of SQL/corpus authority**. The later
coordinator must establish that permission and recheck it before publication;
a configuration cannot expand it.

## Envelope and prospective bindings

`ArtifactBinding` validates an intended job-owned task, admission_config or
payload association. It snapshots all seven ArtifactObject fields, checks
project/job/role, plaintext size and SHA256, and requires a project-scoped
format-1 locator. It is not an upload receipt or an existing scoped reference.
An object ID is 32 lowercase-hex characters; its content reference/digest is 64.
In particular, jobs.execution_config_ref must never become a digest-to-object-ID
foreign key.

`prepare_admission(intent, registry, ..., task_binding,
configuration_binding, permitted_processor_profile)` checks the exact task and
configuration bytes and constructs only the frozen payload:

```text
{schema: 2, kind: "native-run", project_id, client_operation_id,
 request_digest, task_ref, task_digest, seed, budget_microusd,
 execution_config_ref, execution_config_digest}
```

The content refs equal the corresponding plaintext digests, while metadata IDs
remain separate and must not collide. `PreparedAdmission.bind_payload(descriptor)`
checks the generated envelope's intended payload descriptor. No method writes
bytes, records a receipt or publishes references.

`OriginCorrelation` is a separate 32-character server-generated first-attempt
identifier. Its type validates only shape, never provenance. It does not enter
client-intent or envelope identity. HTTP composition must obtain it from its
trusted request boundary, never a client body/header; P3 persists the first
committed origin and preserves it during replay. Later HTTP requests still have
their own fresh request IDs.

## Required next integration boundary

Only a genuinely new authorized operation may invoke new configuration
resolution or `prepare_admission`. P3 must first check both authorized existing
operation identities. Matching recovery returns the original accepted
configuration/response and preserves original correlation without consulting a
new registry snapshot, redispatching or uploading again.

For new work, P3 must verify actual storage receipts, then bind the same-project
job, task/config/payload objects and roles, operation, alias and audit in one
confirmed transaction. It must freshly revalidate caller/corpus permission and
all associations. An unacknowledged commit remains uncertain; these prepared
objects cannot authorize a retry or establish whether SQL committed. Historical
NULL configurations remain readable and non-dispatchable; this slice does not
rewrite old records, ciphertext or profiles.

Focused tests cover exact raw/materialized boundaries, escaping expansion,
canonical identity changes, strict values and aliases, processor refusal, all
envelope/ref associations, metadata collisions and separate origin identity.
The installed-package smoke exercises the three modules using synthetic bytes
and checks refusal without processor permission. Actual installed-wheel/SDist
execution and the complete integrated suite remain CI evidence.
