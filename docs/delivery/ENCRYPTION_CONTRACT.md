# C07 encryption and cloud credential contract

AR-016-A is an offline contract and synthetic fixture deliverable. Its prerequisites
AR-009-B and AR-003-B are Verified. This document does not enable ciphertext format
2, provision a resource, authorize deployment, or verify a real KMS/GCS operation.
The existing 2 [2–3] PL-day task and downstream gates remain unchanged.

The five owned files are this document,
`contracts/encryption-envelope.v1.schema.json`,
`contracts/fixtures/encryption.synthetic.json`,
`scripts/check_encryption_contract.py` and
`tests/test_encryption_contract.py`. The schema's version 1 describes a new
**ciphertext format 2**. The checker is an offline reference, never an application
storage adapter. Its wrapping provider is a local synthetic mock whose bytes are
explicitly not Cloud KMS wire bytes. All committed test keys and nonces are public,
deterministic test material and must never be used outside these vectors.

## Existing authority and compatibility

[C04](../../contracts/proposals/m1.data-model.json) and
[the baseline](BASELINE_INTERFACES.md) continue to require scoped object references,
all seven descriptor fields, complete verified graphs where applicable, fresh
authorization, and preservation of legacy data. A hash, bucket permission or
successful decrypt does not authorize disclosure. Validate the original
`id/project_id/digest/locator/format_version/byte_count/created_at` descriptor and
owner/role references before reading; revalidate their original identities and
authority after I/O. Encryption does not replace that SQL proof.

Current `ArtifactObject`, `artifact_schema.py`, scoped locators and catalog profiles
accept format 1 only. C07 does not change those contracts in place. Before format 2
is used, AR-016-B/C must deliver an explicitly reviewed additive C04 storage-format
extension, migration, supported-reader range and new exact catalog profile, with
rollback/restore and mixed-format proof. Old profiles and frozen fixtures stay
immutable. No format 2 write is allowed merely because this schema validates.

[C14](REFERENCE_CONFIGURATION.md) already requires separate artifact KMS,
API-session, OIDC-client and worker-provider secret resources and distinct workload
identities. This contract links those accepted requirements; no C14 revision or
validator change is required here. Environment-specific IDs, versions, secret
values and IAM changes remain AR-033-B/ENV0 and later implementation evidence.
C15's administrative identity work is disjoint: neither session revocation nor
last-admin recovery rotates an artifact key or grants project data access.

## Format 2 bytes and algorithms

Use the pinned `cryptography` AESGCM implementation (currently 50.0.2):
AES-256-GCM with a fresh cryptographically random 32-byte DEK and 12-byte nonce
for every **physical encryption**; a 16-byte authentication tag is mandatory.
Never reuse a DEK/nonce pair. A deduplicated cache hit reuses a verified immutable
object without generating another ciphertext. KMS wraps only the DEK; plaintext
and data encryption remain local to the trusted API/worker process.

The wire frame is exactly:

```text
52 57 45 32 00             five-byte ASCII RWE2 plus NUL
HH HH HH HH                unsigned big-endian header byte length
<header canonical ASCII JSON>
<ciphertext, exactly byte_count bytes><16-byte GCM tag>
```

The header is authenticated but not encrypted. Project IDs, plaintext digests,
sizes, nonces and key resource names are visible metadata; this format does not
claim metadata confidentiality. Never place credentials, plaintext task content
or provider error text in it.

Header fields are all required, with no additional fields:

| Field | Exact interpretation |
| --- | --- |
| format_version | Integer 2; boolean, float and string forms refuse |
| algorithm | Literal AES-256-GCM |
| wrapping | Literal gcp-kms-symmetric-v1 |
| project_id | 32 lowercase hexadecimal characters, copied from authorized SQL |
| digest | 64 lowercase hexadecimal plaintext SHA-256 characters |
| byte_count | Integer 0 through 536870912; lower caller bound also required |
| nonce | Canonical unpadded base64url of exactly 12 bytes |
| key_version | Exact Google CryptoKeyVersion resource, at most 1024 ASCII bytes |
| wrapped_dek | Canonical unpadded base64url of 1 through 1024 opaque bytes |

Canonical JSON uses sorted keys, ASCII escapes, no whitespace, no duplicate names,
no NaN/infinity, and exact declared types. Base64url has no padding, alternate
alphabet or nonzero unused bits. The key resource grammar and header structural
schema are in the new JSON schema; canonical encoding, decoded lengths, complete
frame lengths and trusted-key membership are additional mandatory checks.

| Limit | Value and source |
| --- | --- |
| Plaintext | Existing global `bounded_bytes.MAX_OBJECT_PLAINTEXT`: 512 MiB; caller limits remain mandatory |
| Header | 4096 bytes; new supported framing ceiling |
| Key version | 1024 ASCII bytes; bounded resource identifier, never a URL |
| Wrapped DEK | 1024 decoded bytes; new application support ceiling, **not** a claimed KMS output limit |
| Frame | At most 536875033 bytes: 9 + 4096 + 536870912 + 16 |
| Synthetic input | 128 KiB regular file; 1–8 vectors, each frame at most 64 KiB |

A runtime reader must bound transport before materialization: read the 9-byte
prefix, cap header length before reading it, validate header and authorized size,
then read exactly the declared ciphertext plus tag with a bounded overflow probe.
Refuse premature EOF, extra bytes, oversized headers, compression/alternate
encodings and unsupported algorithms/versions. Never use an attacker-specified
length directly as an unbounded allocation or network read. The offline bytes
parser proves format rules, not transport, deadline or memory behavior. The
512 MiB global ceiling is not a per-call buffering guarantee: one-shot AESGCM
and legacy Fernet retain whole messages and can amplify memory through copies.
Require a lower operational caller limit and AR-015-A capacity/streaming evidence
before claiming runtime support for any large object, including the full ceiling.

## Authentication and wrapping context

KMS additional authenticated data is the canonical JSON object containing exactly
`purpose="agent-rewind-artifact-dek"`, `format_version=2`, `project_id`,
`digest`, and `byte_count`. Reconstruct it from already matched scoped content;
never derive authorization from a KMS response. This avoids a circular dependency
on the wrapped DEK itself. KMS decrypt must use identical AAD.

Data AESGCM AAD is the ASCII domain `agent-rewind:artifact-data:v2`, one NUL,
then the entire prefix and canonical header. Thus the key version, wrapping
algorithm, wrapped DEK, nonce, content identity and lengths are authenticated.
After decrypt, independently check exact plaintext length and SHA-256 before
returning any bytes. No plaintext prefix may escape before tag verification.

Do not include mutable reference owners, roles, job IDs, object IDs or timestamps
in the content AAD: one scoped object may have multiple references, and a collision
winner must retain all seven original descriptor fields. Cross-project identical
plaintext has a different wrapping/data context; ciphertext cannot be adopted
under another project. Future retries preserve the publication receipt's exact
physical ciphertext/descriptor identity, not merely equivalent plaintext.

An accepted KMS configuration is server-owned, installation-scoped and finite.
The offline reference accepts at most 32 explicitly allowed versions. This is a
finite design support ceiling, not an assertion about a deployed key inventory.
If retention would exceed it, refuse new rotation/adoption until a reviewed
capacity extension; never silently evict an old required key.
The supplied header cannot select an endpoint, credential source or new key.
An unknown key version refuses before a provider request. The future adapter
must bind allowed key versions to the already authorized installation/project
context, cap configuration and refresh work, and perform one selected unwrap;
it must not try arbitrary keys until a tag succeeds.

Only a configured symmetric ENCRYPT_DECRYPT key is supported; no asymmetric
wrapping or key-purpose inference is permitted. Cloud KMS Encrypt may target a
CryptoKey primary or explicit CryptoKeyVersion.
Record its returned `name`, verify its expected parent/exact requested version,
and verify request/response CRC32C fields and verified flags as applicable.
Plaintext-DEK CRC32C values are transient integrity inputs, never durable metadata
or log fields. Discard any failed-integrity response; no envelope may use it.
The default contract makes one provider attempt. An explicitly enabled adapter
may make at most one additional attempt within the existing remaining operation
deadline and request budget, before object publication. Exhaustion refuses; no
background retry, new admission, or failed-integrity wrap publication is permitted.
Cloud KMS Decrypt addresses the CryptoKey, and selects the embedded ciphertext
version; its response does **not** establish an explicit key-version name.
Do not claim version-pinned decrypt or a returned version check. The local
authenticated header, trusted key allowlist, expected CryptoKey and original
Encrypt receipt are the binding. A provider response exceeding the supported
wrapped-DEK limit refuses without truncation. AR-016-B must prove that real
supported KMS responses fit this format before enabling it.

## Key lifecycle, credentials and errors

| State | Allowed behavior |
| --- | --- |
| Active primary | New physical encryptions may wrap a fresh DEK; retained decrypt remains possible |
| Retained decrypt-only | Never selected for new encryption; authorized old objects and backups remain readable |
| Disabled | Decrypt refuses with fixed unavailable error; explicit operator re-enable may recover reads |
| Destroy scheduled/destroyed | No automatic transition; block while any retained object, backup or recovery journal requires it |

Application lifecycle labels do not claim to mirror every Google key-state enum.
A normal KMS primary rotation affects future writes, not existing ciphertext.
Immutable cache hits may retain an older allowed key version. Full-header AAD
means replacing only the wrapped-DEK/key-version header invalidates the data tag.
**In-place rewrap is unsupported.** AR-016-D must design a bounded operator
rotation/restore procedure with a new immutable object representation, metadata
and reader/profile handoff before rewriting content; C07 alone does not provide
that migration. AR-032-A supplies retention policy; key deletion remains blocked
until retained objects/backups are proven independent and the existing explicit
operator/destructive-action approval applies.

Format 1 remains raw Fernet, selected only by trusted descriptor format 1 and an
explicit legacy key configuration. Existing registered legacy locators remain
readable; do not rewrite bytes, change plaintext digests or invent new refs on
read. A missing legacy key refuses. Failed format 2 parse/authentication must
never fall back to Fernet or a different format. No heuristic trial of current,
old, cookie and provider keys is allowed. An existing legacy cohort uses its one explicitly configured Fernet key. Multiple
legacy keys require an explicit object/cohort-to-key association and reviewed
metadata migration, never blind trial decryption. Legacy rotation requires that
bounded mapping and retained-key review; there is no key ID hidden in old tokens.

The offline reference collapses malformed, tampered, wrong-scope, unknown,
disabled, denied and unavailable unwrap cases to `envelope_unavailable`.
Runtime consumers retain their existing fixed `ArtifactError`/dependency boundary;
do not expose provider messages, resource IDs, key material, plaintext or
ciphertext in customer errors/logs. Preserve typed authorization failures before
storage and after I/O. A KMS timeout during a read never causes a new publication,
fallback key, retry loop or admission. Future adapters must account bounded
provider attempts and uncertainty using the existing publication protocol.

No plaintext KEK is delivered to the application. Plaintext DEKs exist only in
trusted process memory for the operation; never persist them in SQL, journals,
logs, fixtures other than declared public test vectors, or sandboxes. Python
objects do not establish guaranteed zeroization; runtime review must minimize
lifetimes/copies without claiming a memory-erasure guarantee.

Use C14's workload identity and resource-scoped grants: API/worker artifact crypt
on the designated key only, independent API-session/OIDC and worker-provider
secret access, no key-admin/destroy permissions for runtime, no downloaded
service-account keys, no sandbox metadata/credential access. Application project
authorization still precedes crypt operations; IAM is not per-object SQL authority.
No ambient credential discovery, SDK installation or real credential read occurs
in this deliverable.

## Consumer and implementation handoffs

| Consumer/owner | Required boundary before activation |
| --- | --- |
| AR-016-B KMS/secrets | Actual allowlisted KMS wrap/unwrap, integrity checks, bounded failures, workload identity and ENV0/AR-033-B proof; independent session/provider secrets |
| AR-016-C storage | Reviewed format-2 C04 extension, additive migration/new catalog, scoped locator/version, exact descriptor reuse, immutable conditional writes, mixed readers, actual GCS conformance |
| AR-015-A streaming | Encrypted streaming/private quarantine, tag/digest verification before disclosure, actual aggregate byte/cancel/cleanup proof; this one-shot reference does not prove bounded-memory runtime |
| AR-016-D rotation | Retained-key inventory and backup restore, explicit version migration/rollback and no unsupported in-place rewrap |
| AR-032-A retention | Retained object/backup/key linkage and deletion approval; no cleanup/GC is implemented here |
| API Auth / C15 | Existing v2/Fernet sessions preserved now; separate cookie key before artifact rotation, explicit bounded session-key lifecycle; never revoke users by rotating the artifact key |
| Cursor configuration | Existing independent LIST HMAC key and key-reuse checks remain; no artifact/session/provider key reuse |
| Sentinel/readiness | Existing system Fernet configuration needs an explicit separate-purpose key/delivery and old-reader handoff; never treat a system sentinel as a customer artifact |
| Legacy worker, CLI/FrozenLegacySource | Explicit old-format/key access remains; do not silently switch raw `Artifacts` or backfill readers to a cloud adapter |
| Admission/publication | Preserve verified receipts, deduplication, unknown-commit recovery and no KMS/storage I/O under SQL locks; new format never relabels an old receipt |

There is no new task edge or implementation package in AR-016-A. AR-015-A and
AR-016-C must reconcile their framing/streaming handoff before accepting either
affected runtime interface. If chunk-authenticated streaming is required, it is
a distinct reviewed format with its own framing/nonces/order/truncation proof,
not an implicit reinterpretation of format 2. Current C04 and C14 bytes remain
unchanged. No customer-ready or runtime profile is introduced.

## Evidence and review gates

The offline checker compares committed deterministic frame bytes, wrapping AAD
and data-AAD digest, AESGCM ciphertext/tag and decrypted plaintext. Tests must
exercise malformed/canonical framing, both bound endpoints, tampered header/tag,
wrong project/size/digest, unknown/denied/disabled keys, exact legacy fixture reads
without changes, and schema/reference parity. Existing schema/profile/manifest
and frozen fixture files must remain byte-identical.

This evidence proves only reference framing, local cryptographic composition and
offline compatibility expectations. Real KMS IAM/integrity/availability/rotation,
real GCS immutable storage, end-to-end constant memory, DB migrations, workload
credential denial and retained-backup recovery are downstream acceptance gates.
PL/SEC design review is still required; a green synthetic checker is not production
approval.

Primary references checked for this design:
[Google envelope encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption),
[KMS AAD](https://docs.cloud.google.com/kms/docs/additional-authenticated-data),
[KMS integrity](https://docs.cloud.google.com/kms/docs/data-integrity-guidelines),
[Encrypt API](https://docs.cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys/encrypt),
[Decrypt API](https://docs.cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys/decrypt),
[key rotation](https://docs.cloud.google.com/kms/docs/key-rotation),
[scoped KMS IAM](https://docs.cloud.google.com/kms/docs/iam),
[service-account guidance](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts),
[pinned AESGCM](https://cryptography.io/en/50.0.2/hazmat/primitives/aead/),
and [Fernet memory/compatibility](https://cryptography.io/en/50.0.2/fernet/).
