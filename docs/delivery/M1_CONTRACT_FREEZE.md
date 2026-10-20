# M1 contract reconciliation and proposed freeze

AR-004-B · C04 revision `m1-review-2` · **Reviewed for development/testing**.

This records implementable dispositions for the eight findings in
[BASELINE_INTERFACES.md](BASELINE_INTERFACES.md), the
[observability contract](ERROR_READINESS_TELEMETRY.md),
[capacity review](CAPACITY_AND_FUNDING.md), and the frozen
[legacy corpus](../../tests/fixtures/legacy_v0/README.md). The companion
[freeze record](../../contracts/proposals/m1.freeze.json) tracks review evidence;
[API](../../contracts/proposals/m1.openapi.json),
[data model](../../contracts/proposals/m1.data-model.json) and
[acceptance plan](../../contracts/proposals/m1.acceptance.json) carry the same
revision. Application runtime is unchanged. All 24 CT-M1 cases remain planned.

The user approved development/testing and three contributor slots. This proposal
does not request that approval again. AR-004-C must record the existing approval
and the reviewed first slice; silence does not fill a consumer review. Production
region, recurring funding, named human on-call, customer IdP, real corpus rights,
independent statistical review and release certification remain separate gates.
The $200 total validation ceiling is unchanged; recorded historical reservations
are not invoice spend or a fresh spending allocation.

## Decisions and consumer ownership

| Finding | Proposed disposition | Implementation / required consumer |
| --- | --- | --- |
| IF-01 | Keep `X-Rewind-CSRF` and exact allowed Origin on every cookie mutation, legacy and v1. | AR-007-C/011-B; BE, FE, SEC |
| IF-02 | Explicit principal legacy default project; no sole-membership or organization-wide fallback. Authorize before loading, counting or decrypting. | AR-007-A/B/C; BE, FE, SEC |
| IF-03 | Separate stable canonical client request from a persisted versioned execution envelope; retries retain original resolved configuration. | AR-008-A/B; BE, PL, RS |
| IF-04 | Close project/job/account/call/evidence ownership, generation fence and conservative opening holds. | AR-010-A/B; BE, PL, QE |
| IF-05 | Register transitive owner references; separate synthetic system sentinel; count PUT fan-out explicitly. | AR-009-A/B, AR-011-B; PL, SEC, QE |
| IF-06 | Projection records verified published progress; stale running execution becomes incomplete without rewriting history. | AR-006-A/B; BE, FE, RS |
| IF-07 | OIDC principal binds exact issuer and subject; service keys belong to one project; bootstrap cannot access customer data. | AR-007-A/C; BE, SEC |
| IF-08 | Fixed errors, strict limits, signed pagination, bounded operation error/result mapping and explicit legacy compatibility. | AR-006/008/011/012; FE, BE, QE |

These dispositions replace the inventory's unresolved recommendations for this
revision, subject to recorded consumer review. They do not replace its historical
source observations. No new v1 branch, study, artifact, timeline, key-management,
trial, report or export endpoints are introduced. AR-027–030 own later consumers.

## Identity, legacy routing and key authority

Existing `Auth.principal` uses raw OIDC `sub`, `bootstrap` or `api-key:<id>`;
[`auth.py`](../../agent_rewind/auth.py) does not retain issuer in its session.
The new principal grammar is `oidc:` plus SHA-256 of canonical
`{"issuer": verified_issuer, "subject": verified_sub}` or `api-key:<32hex>`.
The canonical function is the existing sorted compact JSON encoding. Use the
exact validated issuer and subject, with no case/slash/Unicode normalization.
Issuer allowlisting, audience, signature, nonce and expiry validation precede
identity construction. Hashing identifies a principal; it is not anonymization.
Never infer memberships from a matching `sub` at another issuer.

Version-2 sessions include issuer-bound principal, validated issuer and session
version. Reject pre-adoption sessions and require login again; do not rotate the
shared artifact encryption key to invalidate cookies. Project membership and key
revocation are checked for every request/retry; cookie role snapshots cannot grant
project access. Organization administrator mapping is installation configuration,
not a role in a client body. Organization administration alone does not grant
artifact reads: data access still needs explicit project membership.

`project_memberships.legacy_default` is false by default; at most one active
legacy default per principal in this one-organization deployment. Adoption must
explicitly set it. Every context-free legacy route resolves this default first,
then verifies fresh membership and action rights. No default, multiple defaults,
unmapped resource, foreign ancestor or inaccessible ID gives the same safe 404.
An accessible project's insufficient action role gives 403. Do not auto-select
an only membership, use a request-supplied role, union all memberships, or choose
the first project. The v1 path names its project and does not depend on a default.

| Effective project role | Data actions | Administration |
| --- | --- | --- |
| viewer | Read/list/compare authorized scoped resources. | None. |
| operator | Viewer plus record/branch/study/investigate/cancel in that project. | None. |
| maintainer | Operator plus create/revoke project service keys at viewer/operator only. | Project key management; no organization administration. |
| organization administrator | Only explicitly granted project data actions. | Configure projects, memberships and bounded service-key issuance for explicitly selected projects. |

A service key has one immutable `resource_scopes(key,id)` project and a matching
`api-key:<id>` membership. Effective authority is the intersection of live token
role and live membership; administrator legacy keys do not retain organization
power. Adoption requires an explicit replacement viewer/operator grant or leaves
the key unusable. Preserve old token hashes, expiry and revoked flags. New raw
secrets are returned once; no secret enters mappings, logs or audit. Key issuance,
scoping, membership and audit commit atomically; no key may create stronger keys.
Deleting an unknown/foreign legacy key now returns the safe 404, an intentional
security correction with CLI/SDK tests.

Bootstrap is restricted to explicit local installation/membership administration
under operator credentials; it is rejected as a customer API credential after
adoption. `doctor` uses installation authority, not bootstrap data access. A
configuration switch cannot restore the old organization-wide API bypass.
Second-project admission remains disabled until AR-007-C and AR-009-B cross-project
legacy and nested-reference tests pass; one mapped project is the migration mode.

## Admission, retry identity and worker payload

[`api.py`](../../agent_rewind/api.py) currently stores a bare TaskSpec and
[`worker.py`](../../agent_rewind/worker.py) selects policy from current settings.
Do not put a new envelope into an old TaskSpec reader. M1 jobs receive explicit
`payload_version` metadata: 1 for existing legacy request shapes (historical or
new scoped legacy admissions), 2 for new v1 native-run admission envelopes.
Every **new** job, including legacy run/branch/study/investigate, also stores
immutable execution_config_ref and execution_config_digest in additive job
metadata, published with the same project/job artifact reference and role
admission_config. The worker verifies that common configuration before dispatch.
For version 2, envelope and job config references/digests must agree exactly;
conflict or missing association refuses before paid execution. Legacy request
bodies remain TaskSpec/BranchRequest/StudyRequest/investigation shapes read by
the existing version-1 parsers. Newly submitted legacy branches/studies must match
the source checkpoint's registered compatible policy/image; missing historical
mapping is unsupported, not permission to freeze today's unrelated defaults.
Legacy submissions have no automatic retry identity contract. Retained historical
jobs have null configuration metadata and remain readable but non-dispatchable
without explicit compatible mapping; no migration backfills guessed settings. No old worker may claim new jobs. Drain legacy writers before
adoption; nonterminal legacy jobs block adoption until explicitly drained/cancelled
using the old version. Historical jobs are not automatically redispatched.

Canonical client digest = SHA-256 of existing canonical JSON applied to SubmitRun
with all TaskDefinition defaults materialized under revision `m1-review-2`.
Reject unknown members, duplicate JSON keys, nonfinite numbers, booleans in integer
positions and ambiguous paths. Preserve source text bytes, Unicode and file modes;
never normalize content to improve deduplication. The digest includes
client_operation_id, adapter_config_id, task, seed and integer budget; it excludes
transport headers, credentials and mutable installation defaults.

Authorize and resolve both operation identities before resolving new defaults.
An existing matching operation returns its stored accepted response and binds any
new key alias transactionally; a changed canonical body conflicts. An adapter
configuration change between retries does not change or redispatch that operation.
Only a new operation resolves the current administrator-owned `native-v1` profile.
The profile contains immutable image digest/local image identity, provider endpoint
profile and model revision, adapter/prompt/tool-policy/configuration digests,
processor profile, token limits, reasoning/seed options, price version and integer
price rates. API uses the registered image/profile, not an API-side Docker call.
The client task.image must resolve through the registered allowlist to that same immutable image identity; conflicting/unmapped input is rejected, never silently replaced. The worker verifies the locally installed image and adapter/config digests before
any paid call; drift fails safely, with no provider fallback or automatic pull.
Credentials are looked up by an authorized server profile and never persisted in
the envelope. A configuration profile cannot expand corpus processor permission.

Encrypted payload version 2 is exactly:

```text
{schema: 2, kind: "native-run", project_id, client_operation_id,
 request_digest, task_ref, task_digest, seed, budget_microusd,
 execution_config_ref, execution_config_digest}
```

All IDs/digests use the existing 32/64 lowercase-hex types. `task_ref` addresses a
canonical legacy-compatible TaskSpec; new v1 task budget_usd is derived from integer
microUSD solely for that reader, with round-trip equality checked. Ledger/account
arithmetic uses the integer envelope, never that floating value. Old task bytes,
policy identity and run task digests are preserved verbatim. Configuration is a
separate bounded versioned object (64 KiB maximum canonical plaintext), and the
worker dispatches by version without heuristic field detection. Future branch or
study dispatch must explicitly resolve a compatible frozen configuration; an
unresolvable legacy policy identity is unsupported, not permission to use current
settings. Schema-1 readers remain for historical reads. No M1 envelope alone supplies the full frozen/observed study identity required by C02.

Upload/verify task, config and envelope first; one DB transaction publishes their
scoped refs, job, operation, key aliases, resolved identity and audit. Duplicate
uploads can become identified unreferenced objects; no committed job points at an
unverified payload. A lost commit acknowledgement returns outcome_uncertain;
recovery repeats only the same canonical idempotent admission identity.

## Relational closure, fences and accounting

The [logical model](../../contracts/proposals/m1.data-model.json) specifies the
constraints and their implementation owner. PostgreSQL composite FKs and CHECKs
handle direct ownership. Deferred constraint triggers handle the explicitly named
polymorphic account and evidence rules; SQLite development must run the same
transactional checks and negative tests, without claiming PostgreSQL concurrency.
Independent FK existence is never enough to prove matching project ownership.

- Every operation/provider call carries a constant `job_resource_kind=job` and a
  composite `(project_id,job_resource_kind,job_id)` FK to resource_scopes, plus an
  actual jobs FK. Account project/organization and job/scope bindings must agree.
- A call freezes exactly one organization, project and job account ID, including
  admission-period identity. Entry insertion can name only those three accounts.
  The organization account is intentionally shared across that organization;
  project and job accounts cannot cross projects. Scope-specific nullability and
  scope_id equality are enforced, not inferred from a label: project requires
  project_id IS NOT NULL and job_id IS NULL; job requires both IDs NOT NULL;
  organization requires both NULL. Explicit nullability prevents SQL UNKNOWN
  from bypassing equality or composite FKs.
- Budget evidence is a verified artifact ref owned by the same provider_call,
  project and fixed role `budget_evidence`. Calls have scoped ownership rows;
  `(project_id,call_id)` and artifact-ref composite constraints close the chain.
  An arbitrary existing artifact ID is not settlement evidence. A trusted
  reconciliation operation validates the evidence kind/source and amount; it is
  not an untrusted caller's assertion that a file is a bill.
- `jobs.lease_generation` starts at zero and increments on successful claim.
  Reservation/dispatch/publication compares job, owner, generation, running state,
  unexpired database-time lease and cancellation. Call rows retain the generation.
  An idempotent reservation lookup never returns a fresh dispatch permit after a
  call has left reserved. Transition reserved→dispatching exactly once under the
  fence immediately before network I/O; no DB transaction stays open for HTTP.
  Crash after that transition is uncertain even if no request was sent. No blind
  retry, refund or new paid call follows an ambiguous result.

This fence does not make an external provider transactional. Cancellation/expiry
can race after the final check but before HTTP; a provider may charge without a
response. Retain the hold and uncertainty. AR-017 owns process termination,
heartbeat/reclaim/cleanup and broader lease fault drills; M1 owns the minimum
ledger permit and authoritative publication checks above. No exactly-once provider
claim or automatic expired-job resume is made.

For a new call with bound R, reserve R at all three accounts atomically, locking
account IDs in sorted order. `held + accounted <= limit` and nonnegative amounts
hold for each account. Observed token usage is an estimate, not invoice proof.
Settlement evidence for charge C (0≤C≤R) moves C from held to accounted; independent
release evidence for the unused R−C removes that hold. The reserve/settle/release
entries are unique per call/account/kind and applied to all three accounts in one
transaction. Evidence must justify both operations. A fully uncharged call may
release R only with proof of non-dispatch/non-charge, never timeout alone.
Over-bound billing evidence is retained as an incident, blocks further dispatch,
and requires explicit reconciliation; do not discard it or auto-raise limits.

Legacy opening L_j is the exact original `jobs.reserved` for each mapped job.
Record it once as `legacy_reserved_microusd` and as the job account's
`opening_held_microusd`; project and organization opening holds are the corresponding
sums. No provider_calls or fake receipt entries are invented. Fixture totals remain
125000+85000+35000=245000 microUSD. Uncertain historic holds do not expire at a new
billing period: carry outstanding obligations against subsequent admission caps
until reviewed reconciliation, with explicit account transfer evidence and no
release/reset shortcut. A cap below opening exposure blocks activation; migration
must not silently increase it.

During legacy compatibility, `jobs.reserved = L_j + sum(new call reserved amounts)`
remains the gross cumulative reservation counter and may be greater than current
held+accounted after evidenced release. Preserve that meaning in legacy output and
v1 reserved_microusd; do not call it invoiced spend. Job admission also checks this
gross counter against the unchanged job budget, conservatively preventing re-use
of released job allowance. Hierarchical account totals count each call once per
level, not the sum of all three entries. Monetary values are integer microUSD;
periods use UTC and original account IDs survive reconciliation.

## Scoped object graph and capacity

[`Artifacts.get`](../../agent_rewind/artifacts.py) reads complete ciphertext before
validation. `put_workspace` rewrites every file plus a manifest at every capture;
current S3 PUTs are not deduplicated by the content address. CAP-01 therefore
remains a capacity gate: `(2D+1)*(F+1)+2D+4` approximate PUTs per continuation under
the documented assumptions. AR-009-A/B must record logical writes, actual backend
requests, cache hit/miss and byte counts separately; storage latency and request
charges are required inputs to a recurring budget. No modeled cache savings are
approved by this contract.

For new objects, project-scoped locators permit an immutable verified put-if-absent
operation. A metadata/cache hit is usable only after owner authorization and a
verified format/digest/size match. Do not infer success from an unchecked HEAD or
assume S3 conditional-write semantics without adapter tests. Legacy locators remain
readable as format 1. Equal bytes in different projects receive independent object
identities; shared retained physical legacy ciphertext grants no access.

Root references and all reachable child objects are registered for the same
scoped owner before publication: job payload/config/task/result; run task/events,
checkpoints, workspace manifests/file blobs/evaluation; study attachments; provider
call reconciliation evidence. Role vocabulary is fixed in the model. A reader
resolves `(project, owner_kind, owner_id, role, digest)`, verifies current scope and
reachable reference, then accesses the object. A naked hash or locator is never an
API capability. Branch prefixes are resolved through their actual scoped ancestor,
not rewritten with the child run ID. Study/run/job ownership must agree throughout
that graph. Corrupt/missing objects or unregistered child hashes fail explicitly;
no empty workspace substitute or branchability claim.

Adoption traverses verified schema-1 fields with bounded batches/bytes, tracks
visited objects and rejects cycles/unknown schemas/ancestry beyond the existing
64-level bound. Workspace bounds remain 10,000 entries and configured bytes.
Unreachable objects are recorded as unclassified retained inventory, inaccessible
to customer requests; no automatic deletion or guessed owner. Identified failed
uploads remain unpublished; AR-032 owns eventual retention/GC. Customer bounded
streaming beyond M1 remains AR-015; the small readiness reader below cannot be
used as evidence that all workspace reads are bounded.

## System sentinel and readiness sequencing

AR-011-B depends on AR-005-C. Its `check_schema_compatibility(connection,
release_profile)` is read-only and returns ready, incompatible or unavailable.
A release profile enumerates supported revisions and required completed backfills;
missing version metadata, multiple heads, unknown/future revisions or incomplete
required backfill cannot pass. `create_all` and table existence are not readiness.
AR-005-C's first release profile supports the adoption revision in migration-only
mode; it cannot enable customer admission before the later scoped revisions.

AR-011-B owns a narrow `read_system_sentinel(config, deadline)` interface with no
project or caller-supplied locator. Explicit `doctor --provision-sentinel` writes
one installation-owned, versioned synthetic object and atomically records its
expected plaintext digest and fixed locator in owner-readable installation config.
It never changes customer metadata or creates one object per probe. Installation
write checks are separate from read-only readiness.

The fixed namespace is `system/<installation_key>/readiness-v1`; a customer
`objects/` locator is rejected even if its hash matches. Payload is the canonical
`{schema:1,purpose:"readiness",installation_key:<configured installation key>}`;
verify exact payload as well as its configured digest. Only the explicit operator
command may replace the configuration; no request can supply a locator.

Sentinel plaintext is at most 4096 bytes. Fernet format 1 permits at most 5560
ciphertext bytes for that bound; read at most 5561 and reject oversize before
decryption. Local adapter opens only a regular non-symlink file at the configured
private location and enforces fstat plus bounded read. S3 adapter uses bounded
range/body reads, rejects inconsistent length/range and closes the body; it still
limits reads if a backend ignores Range. A declared small Content-Length alone
is not a bound. Verify authenticated decryption, plaintext length and digest.
No call to existing unbounded `get`, listing, customer object or model is allowed.

The complete probe has a one-second deadline, at most one in-flight check per
process and positive cache age≤5 seconds. Configure connection/read deadlines
and reject late results; a timed-out check cannot start unlimited orphan refreshes.
Unknown/stale/draining readiness fails closed; cached success never bypasses each
request's transaction/authorization checks. No sandbox/image pull or provider
call occurs. /livez means process responsive; /readyz means these bounded checks
pass; /healthz retains the old DB-check compatibility until probes migrate.
AR-009-A reuses/extends the bounded byte-read primitive for object publication,
but its project/ref API is separate and cannot bypass scope using a system flag.
This dependency split avoids waiting for customer-object migration to test safe
readiness while never treating current full-object reads as bounded.

## Run projection and pagination

AR-006-A writes `run_index` and event/ref publication coherently in the same
fenced transaction. Historical `records.data`, events.hash, ciphertext and original
floating created timestamps are never rewritten by backfill. `created_at` is a
deterministic UTC projection rounded to nearest microsecond with ties-to-even;
retain original float separately in the preserved record. `(created_at,run_id)`
breaks ties. `published_seq` is an immutable per-project commit-ordered sequence. Allocate by
locking/incrementing projects.run_sequence and inserting run_index in the same
transaction, holding the project row lock through commit. Do no object/network
I/O under this lock. Database sequence allocation alone is insufficient: an
uncommitted low sequence could appear after a higher committed watermark. Test
that reversed transaction completion and rollback cannot introduce such rows.

RunSummary and branchable describe execution/restore only, not natural-failure
eligibility, grader validity or the capture-success denominator. Historical evaluator
nonzero exits currently become success=false; preserve them without reclassifying
as verified natural failures. AR-018/024 and future attempt/study receipts own those
checks. An admission/config digest is not a study protocol/corpus/split digest;
event_head is not an artifact digest.

A complete verified manifest remains complete even when success=false. Failed
means explicit execution failure, not evaluator task failure. Running requires an
active compatible job and lease; terminal/lost/expired execution with only a
running/partial manifest projects incomplete and non-branchable. Missing/corrupt
terminal evidence also blocks branchability. A lagging running manifest may trail
a verified published event by one step; use the last verified committed event head
and do not fabricate completion. Projection repair records fixed reason, old/new
status and source identity in restricted audit, is idempotent, and never rewrites
hashed bodies. API reads may conservatively suppress branchability using current
job state while bounded reconciliation persists the repair; no list-time blob scan.

Signed cursors (server-held HMAC key distinct from artifact encryption) contain
version, project, principal, fixed empty filter set, limit, initial maximum
published_seq, last `(created_at,id)` and expiry. TTL is 15 minutes, encoded size
≤2048 bytes. Verify size/signature/shape before using data; authorize the project
first. Query only scoped rows with published_seq≤watermark and descending tuple
below the previous position; this also excludes later backfills with older creation
times. No snapshot of mutable run status is promised. No duplicates; deletions or
revocation can shorten pages. Foreign/tampered/expired cursors give invalid_cursor
only for an accessible project, otherwise 404. Key rotation invalidates old
cursors; restarting pagination is safe. No event/workspace loads for summaries.

## Errors, limits and consumer compatibility

The API retains five v1 operations and the existing bounded RunSummary. The
workbench, SDK and CLI stay on scoped legacy shapes through M1; AR-027-A owns richer
history/UI contracts. Every application response gets a generated request ID and
no-store header. Fixed v1 errors use exactly code/message/request_id/retryable,
including outcome_uncertain; generic ValueError is not automatically user error.
All operations declare 500 and 413; quota Retry-After is 1–60 seconds.

BodyLimit remains 9 MiB of received bytes, including chunked bodies. Only identity
content encoding is accepted in M1; compressed bodies are rejected safely rather
than expanded outside the limit. Task limit is 8 MiB of canonical materialized
legacy-compatible TaskSpec, independently of transport size. Apply the same source,
evaluator path, file-count and redaction rules to v1 and legacy admissions. No
private dynamic file key or validation value appears in an error. Legacy errors
retain `{detail: fixed_safe_message}` plus headers until FE/SDK migration; unsafe
exception text is never preserved for compatibility.

A successful Operation read is 200 even if its stored safe error is
outcome_uncertain. The nested error's request_id is the originating generated
request/worker correlation ID; the GET has a separate header ID. Historical rows
with no correlation receive a persisted migration correlation marker, not a fake
original request ID. `result_run_id` is returned only after same-project result
reference validation; never expose storage locators. Cancellation is repeated
intent: queued→cancelled, running remains running with cancel_requested=true,
terminal status unchanged, absent/inaccessible resource 404. Ambiguous admission
uses the original identity for recovery; legacy POSTs still have no automatic
retry guarantee. Switching a service key changes principal and is not safe recovery
of the same operation identity; revoked access still denies replay. Identity aliases
remain for the operation lifetime plus at least 90 days; M1 has no deletion API.
Observability label vocabularies remain unchanged.

## First migration slice and revision ownership

Use one linear Alembic history; feature authors rebase their unmerged revision on
the latest accepted predecessor. No independently guessed head or runtime stamping.
Logical revision names below reserve ownership; concrete Alembic identifiers are
chosen once by the owning PR and recorded in the compatibility manifest.

| Revision / owner | Exact boundary |
| --- | --- |
| baseline-v0 / AR-005-B | Frozen explicit five-table DDL for empty install; known existing schema is fingerprinted, then explicitly stamped. No current metadata.create_all. |
| adoption-v1 / AR-005-B | Add installation_adoptions and migration_progress metadata only; persist explicit mapping intent and backup/drain evidence. No organization/project/membership/resource rows. |
| ownership-v1 / AR-007-A | Own all organization/project/membership/resource_scopes DDL, explicit principal grants/defaults and resumable ownership backfill from adoption intent. |
| run-index-v1 / AR-006-A | Own run_index DDL/backfill/publication sequence after scoped ownership exists. |
| artifacts-v1 / AR-009-A | Own object/ref DDL and reachability backfill metadata; AR-009-B wires publication. |
| admission-v1 / AR-008-A | Own operation/key-alias DDL and versioned payload/job metadata; depends on artifact schema contract, publication integration in AR-008-B. |
| ledger-v1 / AR-010-A | Own accounts/calls/entries and lease_generation DDL, opening holds and constraints; AR-010-B wire permit/call paths. |

`installation_adoptions` has singleton installation_key (PK varchar64),
source_kind `fresh|legacy`, source_baseline char40, schema_fingerprint char64, organization_id/project_id
nullable char32 **intent values without premature FK**, mapping_digest char64,
mapping JSON (bounded 1 MiB), backup_evidence_digest char64,
drain_evidence_digest char64, created_at timestamptz and state
`prepared|ownership_complete`. IDs/digests have format CHECKs. Store nonsecret
operator-supplied mapping data only; raw tokens, private backup paths and contents
stay outside this table. Mapping schema 1 names the source dataset digest, exactly one target organization
and project, the explicit selector `all-verified-legacy-resources`, canonical
principal grants/legacy defaults and explicit legacy-key dispositions (unlisted
keys disabled). This assigns the verified frozen dataset as a unit without an
unbounded list of every resource ID or inference from actors/key names. Reject
unknown record kinds, conflicting targets and missing principal/key authority;
resource closure verification is still required. AR-007-A verifies the intent against current
rows under writer exclusion before setting ownership_complete.

`migration_progress` has `(revision,phase)` PK, source_digest char64, bounded cursor
JSON, rows_verified bigint≥0, status `pending|running|complete|blocked` and
updated_at timestamptz. Completed batches and cursor advance in one transaction;
source digest drift blocks resumption. AR-005-B provides this mechanism; each
feature owns its own phases/data verification. No AR-005-B placeholder backfill
writes the future ownership schema. Re-entering identical intent/evidence is
idempotent; changed mapping/source/evidence is a conflict requiring reviewed
recovery. A schema-only adoption may reach prepared, but corruption or unmappable
history keeps activation blocked; prepared never reports healthy customer service.

Fresh installation has an explicit path: `install` creates an adoption row with
source_kind=fresh, the verified empty-source fingerprint, null organization/project
intent, mapping `{schema:1,source_kind:"fresh"}` and null backup/drain evidence.
CHECKs permit null target organization/project IDs only while source_kind=fresh
and state=prepared; both targets are required for ownership_complete. Legacy
backup/drain evidence is always required for source_kind=legacy. Fresh backup/drain
evidence remains NULL (explicitly inapplicable) through ownership_complete;
initialization must not fabricate legacy evidence to satisfy a state transition. AR-007-A owns an explicit
operator initialization command accepting installation/project IDs and canonical
principal grants; it verifies the recorded fresh installation and empty legacy
dataset, creates real ownership rows and records ownership_complete atomically.
It never invokes legacy `adopt`, fabricates legacy mappings or infers a user from
the process login. A legacy prepared row requires non-null mapping targets and
backup/drain evidence. Fresh and legacy transitions cannot be switched by a retry. Test the complete fresh prepared→ownership_complete transition with null inapplicable evidence, not only fresh row insertion.

CLI contract: `rewind migrate status` reads state; `rewind migrate install --installation-key <key>` accepts
only an empty recognized database for first installation. Repeating it with the
same installation key at exactly its known installed revision and unchanged fresh
provenance returns the original installed state with no writes. Different key,
changed provenance or unknown/nonempty unversioned schema refuses; later revision
work uses upgrade/status, not reinstall; `rewind migrate adopt --mapping <file>
--backup-evidence <digest> --drain-evidence <digest>` accepts only known exact
unversioned schema and terminal legacy jobs; `rewind migrate upgrade --target
<revision>` requires the migration credential and reviewed target. Existing
`rewind migrate` remains an explicit operator command equivalent to upgrade to the
release's declared target, never unknown-schema auto-adoption. `init` retains .env
secret-preservation but cannot silently adopt an existing unknown DB. CLI mapping
files must be owner-readable and never printed. Confirmation flags alone are not
proof of backup/drain: verify DB role/writer exclusion, no active job leases and
operator evidence identity; rehearse restoration on the frozen fixture.

PostgreSQL uses a migration advisory lock plus bounded lock/statement timeouts;
SQLite development uses exclusive writer exclusion with finite busy timeout.
Fingerprint schema-qualified tables/columns/types and PostgreSQL typmods,
nullability, server defaults, ordered PK/unique/FK/index constraints and unexpected
write-changing triggers/rules under dialect-specific reviewed profiles, not fixture
checksum or table names alone. Preserve nullable api_keys.hash/revoked, non-null
jobs.cancel and Python-side defaults without inventing server defaults. Original
created/expires/lease values remain FLOAT. Advisory migrator locking alone cannot
exclude old writers: a bounded DB lock and operator-enforced writer exclusion must
span fingerprint through stamp, with active/expired running jobs and queued work
blocking adoption. Test an active old writer as well as competing migrators. Unknown/partial/future schemas fail before DDL. Current create_all is invoked by CLI init/migrate; API/worker lack revision guards. AR-005-C removes create_all from supported runtime/CLI initialization paths,
uses a declared compatibility manifest and read-only revision checks before API admission/worker claim, and documents
compatible application rollback versus required restore. First-slice acceptance includes real PostgreSQL catalog/lock/rollback tests and a non-owner runtime role denied CREATE/ALTER/stamp on empty/partial/future schemas, plus empty install, known adoption, refusal, interruption and competing migrator tests;
it is not full M1 backfill or production-ready status.

## Exact dependency and scheduling changes for the lead

These are proposed card/DAG changes; global trackers are not edited here.

1. Add AR-005-C → AR-011-B. Keep G0 and AR-011-A prerequisites. AR-011-B owns the
   bounded system sentinel primitive and provisioning command; AR-009-A consumes
   its interface. Add AR-011-B → AR-009-A for that reuse, without an inverse edge.
2. Preserve the existing AR-007-A → AR-006-A edge: projection owns a real scoped
   FK/backfill. AR-006-A and AR-007-B may run in parallel once ownership is available.
3. Existing AR-008-A depends on AR-009-B (therefore AR-009-A), and AR-008-B depends
   on AR-008-A; those already enforce artifact schema/publication availability.
   No redundant edge is needed. Keep AR-008-A operations/key schema and canonical
   envelope scope distinct from artifact DDL.
4. Keep AR-005-B infrastructure-only and AR-005-C revision guard before
   AR-007-A ownership schema/backfill. Add the adoption tables/CLI and release
   profile detail above to their cards; AR-007-A consumes their durable mapping.
5. AR-010-A owns generation schema and minimum permit fence; AR-017 consumes it
   for full execution lifecycle fencing. Require AR-010-A/B integration before
   any production paid execution, including legacy discovery/continuation.

With three contributors, first start AR-005-B plus independent fixture/test design
and consumer contract work; do not claim three parallel schema implementations.
Then AR-005-C unlocks AR-007-A and AR-011-B in parallel. After both, ownership
repositories, run projection and artifact schema can proceed independently using
one serialized migration chain. First-slice estimates remain those in the approved
backlog (3 days AR-005-B, 1.5 days AR-005-C); integration and review consume capacity.
No calendar date is promised until these new edges are applied and actual migration
results reduce uncertainty. Schema/profile surprises use the existing estimate
contingency and block adoption, rather than relaxing preservation.

## Review evidence and validation limits

BE proposal author: Engineer B, revision m1-review-2. FE/RS review: Engineer A,
accepted at source 22c4376. PL/SEC/QE review: Engineer C, accepted at the same source.
Lead acceptance and AR-004-C are recorded in [G0_DECISION.md](G0_DECISION.md). These are internal
contributor roles, not external human security/statistical certification. The
machine record must contain actual dated dispositions and scope/evidence before
approval metadata becomes reviewed; a passing structural checker cannot fill them.

Structural checks cover cross-file revision/CSRF/error/limit/closure declarations,
review-state consistency and preserved fixtures. They do not execute migrations,
prove SQL triggers, bound live S3 traffic, or pass the planned runtime acceptance
cases. PostgreSQL concurrency, rollout/rollback, legacy client behavior and fault
injection remain implementation gates with commit-addressed evidence.

Validation of this proposal: the stdlib checker and installed FastAPI model check
pass (5 operations, 50 local references, 12 logical entities, 24 planned cases,
14 frozen rows, 18 ciphertext objects, five legacy variants). The targeted
review/harness/inventory/legacy/observability suite passes 147 tests with bytecode
and pytest cache disabled. Ruff lint/format and local document links pass. These
checks leave application code and frozen history bytes unchanged; no database,
provider, sandbox or cloud resource was provisioned or called.
