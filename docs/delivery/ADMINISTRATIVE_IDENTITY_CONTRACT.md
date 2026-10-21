# C15 administrative identity contract

Status: independently accepted offline contract for development consumption;
peer review is not independent human certification.
AR-034-A [#100](https://github.com/spei04/agent-rewind/issues/100) produces only
this document, the [OpenAPI proposal](../../contracts/proposals/administrative-identity.openapi.json),
[synthetic vectors](../../contracts/fixtures/administrative-identity.json) and
offline contract tests. No route, grant, session-revocation producer, operator
tool, database migration, IdP integration or production authority is implemented.
The register is available after the recorded review/delivery gate below.
Runtime and live exercise belong to AR-034-B and AR-034-C respectively.

## Existing producers and compatibility

The source baseline is 0b8f99c70f0b203adfc7eed062704b2c43ecdcf1. Links below name
current interfaces, not proof that proposed C15 behavior exists.

| Source | Reusable behavior and limit |
| --- | --- |
| [C04 identity section](M1_CONTRACT_FREEZE.md#identity-legacy-routing-and-key-authority) | Exact issuer/subject principal; installation-configured organization administration; explicit project data membership; viewer/operator/maintainer; scoped keys; operator recovery. Its historical baseline prose is not the current Auth implementation. |
| [Auth](../../agent_rewind/auth.py), [v2 codec](../../agent_rewind/request_identity.py) | Verified issuer/audience/signature/nonce/expiry before identity; role-free v2 session, 900-second TTL, cookie CSRF and exact Origin. Current role/group claims do not grant authority. |
| [RequestAuthority](../../agent_rewind/request_authority.py), [effective_role](../../agent_rewind/scoped_repositories.py) | Fresh original-project membership and live key ceiling; typed visibility/action decisions. No organization-administrator decision. |
| [ScopedActions](../../agent_rewind/scoped_actions.py) | Human maintainer's existing project-key creation/revocation: key, immutable scope, matching membership and fixed audit in one transaction; secret only after acknowledged commit. No membership/project administration. |
| [ownership schema](../../agent_rewind/migrations/ownership_schema.py) | Projects and viewer/operator/maintainer memberships, explicit active legacy default; no admin role, group-provenance or session-revocation store. |
| [browser](../../agent_rewind/web/app.js) and test_route_ui*.py | Refresh current role; clear protected state on authority loss; preserve own CSRF/logout; fence obsolete identity/view responses. |
| [C14](REFERENCE_CONFIGURATION.md) | Separate operator/runtime identities, opaque OIDC secret reference, gated identity-provider network composition. No deployed mapping or credential authority. |

C04, C14, existing frozen fixtures and profiles are unchanged. Existing
maintainer key routes remain separate from these future cookie-only
organization-admin routes. Service keys never manage membership, grant admin,
or issue/revoke keys through C15. Organization administration does not grant run,
artifact, job, study or corpus reads; explicit project membership is still
required. An administrator may intentionally grant their own project membership
through the audited membership action, but receives no implicit grant.

C15 does not change the shared artifact encryption key or rotate it to revoke
cookies. AR-016's C07 key-separation handoff must preserve that requirement;
a cryptographic key grant is not application administration or artifact scope.

## Proposed wire surface

The nine operations in the OpenAPI file are:

| Path under /api/v1/admin | Methods | Result |
| --- | --- | --- |
| /projects | GET, POST | Bounded project page or newly created project, with no automatic membership. |
| /projects/{project_id} | PATCH | Rename only. No delete/archive/retention semantics. |
| /projects/{project_id}/memberships | GET | Bounded metadata including revoked grants. |
| /projects/{project_id}/memberships/{principal_id} | PUT, DELETE | Set or soft-revoke an explicit human project grant. |
| /projects/{project_id}/keys | GET, POST | Bounded key metadata or a one-time viewer/operator secret. |
| /projects/{project_id}/keys/{key_id} | DELETE | Soft-revoke a scoped key and its membership. |

Membership mutation accepts only oidc:<64hex>; api-key membership changes
belong to the key transaction, so it cannot create a mismatched token ceiling.
Membership lists can include either principal kind. PUT specifies role and
legacy_default explicitly. Moving an active legacy default requires locks on
all affected projects in sorted order and atomic removal of the old default;
there is no sole-membership fallback. Group reconciliation never chooses a
legacy default. Unknown or foreign targets are not synthesized by DELETE.
Known revoked membership/key DELETE is idempotent and preserves history.
Key issuance intentionally sets legacy_default=true for the newly scoped key,
matching existing C04 behavior. Key listings never return token hashes or secrets.

These routes require a verified v2 human cookie and reject any Authorization
header, including a bearer paired with a valid cookie. Mutations additionally
require X-Rewind-CSRF and exact configured Origin. No prefix exemption is
introduced. The existing /auth/logout retains its cookie-only validation even
when a bearer is present; existing non-admin routes retain their own credential
precedence. The real schema guard still runs before customer/admin activity.
No project ID is accepted from an untrusted header or inferred from a default.

Each response uses Cache-Control:no-store and a fresh server-generated
X-Request-ID. Fault is {"error": Error}; the nested Error schema is exactly C04's
four fields/vocabulary. 401 is credential/CSRF/Origin failure; an authenticated
human lacking installation administration gets the same 403 before target
enumeration; an authorized administrator's missing/foreign target gets 404.
The project-data boundary retains its existing visibility-before-action rules.
413 is the raw byte cap, 422 bounded invalid input/cursor, 503 unavailable or
uncertain, and 500 fixed internal_error outside classified transaction failure.
No raw SQL, IdP response, group list, token or configuration is an error message.

There is no HTTP endpoint to promote an administrator, change installation
mapping, run recovery, revoke all sessions, provision an IdP or purchase anything.
Creation has no invented idempotency guarantee: after uncertain ACK, return
outcome_uncertain, never automatically create again or disclose a key secret.
AR-034-B must freeze its bounded reconciliation/operator handling before wiring
these actions. Error messages and outcome classification must agree with the
existing safe-error and transaction boundaries; no generic exception becomes
proof of a committed or rolled-back effect.

## Finite bounds and work ownership

| Input/work | Contract maximum |
| --- | --- |
| Raw HTTP JSON body | 16,384 bytes before parsing; strict UTF-8, no duplicate/unknown fields, nonfinite numbers, invalid surrogate or NUL. JSON depth 8 and 512 total values. GET/DELETE reject bodies. |
| Response | 131,072 encoded UTF-8 bytes, including one-time key response; no partial/truncated success. |
| Page | limit 1–50, default 50; fetch at most 51 candidates. IDs ascending, bounded authenticated cursor <=1,024 base64url characters, bound to caller, installation, selected project, query and mapping revision. No offset/unbounded scan. |
| Identifiers/names | Existing 32hex object IDs, issuer-bound human IDs; names 1–120 characters and <=480 UTF-8 bytes, no control characters. Key days strict integer 1–90; booleans are not integers. |
| Operator mapping | <=65,536 raw and canonical bytes; 1–32 unique human administrators and 0–64 unique (group, project) rules. Single exact HTTPS issuer, no userinfo/query/fragment or credentials; no URL normalization. |
| Group snapshot | <=16,384 raw and canonical bytes; <=128 unique group values, each 1–128 characters and <=512 UTF-8 bytes, no control characters. Exact case/Unicode/whitespace; no normalization or wildcards. |
| Metadata work per request | <=128 SQL statements, cumulative <=5 seconds of SQL work and <=5,000,000 SQLite VM instructions; all reads, lock/setup/rechecks, effects and fresh disclosure share the budget. |
| Operator recovery request | <=16,384 raw and canonical bytes, depth/value caps as HTTP; at most 32 replacement humans. No HTTP transport. |

OpenAPI carries the finite wire shapes and byte extensions; the document adds
semantic/work constraints that JSON Schema alone cannot enforce. Aggregate
bounds apply even when each field individually fits. Encoded sizes use existing
sorted compact ensure_ascii canonical JSON. The fixture token and names are
fabricated, not reusable credentials. New complete-string patterns use the
ECMAScript-compatible `(?![\s\S])` end assertion rather than `$`, which may match
before a terminal LF. Control exclusions therefore apply at every position,
including the final character, under JSON Schema search semantics. The offline
oracle uses search too; it does not conceal schema gaps with Python fullmatch.
The copied frozen C04 Error schema remains unchanged. AR-034-B must preserve
these checks with a compatible schema validator or equivalent explicit checks;
this proposal does not add lookaround to an existing runtime regex engine.

AR-034-B owns pre-materialization SQL type/byte CASE checks and bounded
candidate-first reads. Malformed selected rows remain candidates and refuse;
they must not disappear through filters. Bound all dynamic cells, including
names, IDs, timestamps, role text and cursor/mapping metadata, before DBAPI
materialization; validate dates as finite UTC. One extra candidate detects
overflow, not permission to return 51 rows. Listings recheck exact original
ownership/selection receipts and fresh authority after the full read. Cursor
failure is invalid_cursor without disclosing a foreign cursor's contents.
Index/work and actual maximum matching-set tests must prove these ceilings.

Budgets are an implementation contract, not a new global engine hook. Attach
connection-local accounting before setup; all transaction/native control
attempts need explicit accounting. Use positive remaining-time native limits,
never exhausted/sub-millisecond values that become unlimited. Check before
commit_attempted; cleanup runs even after exhaustion or partial attach failure,
preserves typed denial, and discards connections if detach is unconfirmed.
Fresh disclosure uses the same request budget on a new short SQL phase.
No SQL connection is held while contacting an IdP/config service, and ordinary
C15 HTTP requests require no such external call. AR-034-B must prove its
chosen bounded mapping snapshot/refresh mechanism and fail closed if unavailable.

## Separate administrative authority

The proposed consumer interface is:

    AdministrativeAuthority.check(
        connection, verified_principal, installation_key,
        action, target_project_id=None,
    ) -> AdministrativeDecision

Actions are project_list/create/rename, membership_list/set/revoke and
key_list/issue/revoke. A decision is evidence for that check, never a durable
capability. The default implementation is unavailable until AR-034-B provides
an authenticated, bounded, versioned installation mapping and same-Connection
validation seam. Neither a schema-valid dict, arbitrary processor/role string,
ProjectDecision nor a caller boolean can supply administrative trust.
Conversely, an AdministrativeDecision must never be converted to ProjectDecision,
a maintainer role or a bypass of ScopedActions' existing project authority check.
New admin mutations use separate fresh administrative authority and its own
transaction; only reviewed lower-level effects may be shared. An explicit audited
self-membership grant remains legitimate and must subsequently pass the normal
project authority checks.

The mapping contains exactly one issuer, organization and installation; its
administrators are exact human subject/principal pairs. Recompute each principal
using C04 canonical issuer/subject hashing; reject wrong pairs, duplicates,
unknown roles or an empty set. Do not use service keys or project maintainers as
administrators. The mapping digest identifies immutable bytes, not an approval.
The trusted installation/operator composition authenticates its source and
version. Request mapping-version rechecks and configuration mutation must share
a serialization protocol; a detached file read cannot claim SQL atomicity.

For HTTP mutations, after fresh administrative visibility, the consumer owns a
short transaction. Lock all affected projects in sorted order before
organization/grant/key/target rows, conforming to the established producer
hierarchy. Revalidate mapping version and caller/target ownership after waits
and immediately before effects. Preserve each action's original target and
principal. A direct administrative DML revoker must conflict with held grant
rows; project locks alone are insufficient proof. Project creation needs an
explicit organization/installation-first creation exception that attempts only
a new project ID and never later explicitly locks an existing project. A pre-insert
absence observation is not proof of uniqueness: PostgreSQL INSERT can wait on
implicit foreign-key or uniqueness locks, including an uncommitted colliding ID.
The AR-034-B transaction review and actual PostgreSQL tests must account for those
waits within the same remaining native timeout/work budget, prove bounded rollback
on collision/timeout, and show no existing-project fallback or mutation. Include
both committed and concurrent uncommitted ID collisions and foreign-key waits.
No fictitious absent-project or job lock substitutes for that boundary. Operator
mapping/recovery transactions are installation-only: they do not later acquire project locks.
Selected-project actions acquire all existing projects first, then organization,
current mapping/version, grants/keys and targets. Mapping CAS may serialize on
installation state because it never waits for existing projects while holding it.
The concrete AR-034-B transaction review must prove this order and its creation
exception against the existing scoped_locks.lock_authority implementation.
Audit and every metadata effect commit together.
Return success only after ACK and fresh authority disclosure; post-attempt
uncertainty/cleanup failure must not disclose a secret or invite automatic retry.
This defines requirements, not permission to refactor existing ScopedActions
callers or to implement schema in AR-034-A.

## Group mapping and revocation truth

Group rules may produce viewer/operator/maintainer grants only in explicitly
named projects. Proposed internal input VerifiedGroupSnapshot is trusted only
after the actual OIDC verifier checks signed token issuer/audience/nonce/time.
It is not an accepted HTTP body and a matching hash is not authentication.
AR-034-B must name the complete authoritative group-claim source and its
configuration revision. Current Auth requests openid profile, ignores roles,
and does not obtain an authoritative group inventory; do not fabricate it from
a role claim or local cookie.

A complete snapshot with no groups can remove only previously mapping-owned
grants. Missing/truncated/malformed/non-authoritative claims are not an empty
snapshot and cannot silently delete explicit manual grants. Reject duplicate
values, issuer/revision mismatch, unknown project or conflicting roles for the
same project. Unknown groups grant nothing. Provenance must distinguish manual,
group-managed and key-created memberships; never overwrite an explicit grant
or union conflicting roles to choose the stronger one. AR-034-B must decide
the durable provenance/refresh representation and compatible migration, if any,
before implementation, with preservation and reforecast review if broader than
its card. No representation is invented in existing ownership tables here.

| Event | Current truth / C15 requirement |
| --- | --- |
| Membership revoke committed | Subsequent project checks deny; an existing v2 cookie can still obtain own /me CSRF with role:null and logout. Final rechecks/transaction serialization govern in-flight requests. |
| Key revoked/expired | New Auth bearer lookup denies 401; a previously constructed principal must still fail fresh scoped authority. Matching membership and key revoke atomically. No stronger issuer rights. |
| Admin mapping removal | Proposed next admin check must consult the current trusted version; data grants are independent. This producer does not yet exist. |
| Browser logout | Clears this browser cookie. It does not revoke copied cookies or an IdP session. |
| Cookie aging | Current local validity is at most 900 seconds from issuance. This is not an IdP deprovisioning guarantee if the IdP still issues new credentials. |
| IdP user/group removal | Not observed by current data requests. No immediate revocation claim. AR-034-B must freeze refresh/freshness and unavailable behavior; AR-034-C proves the bound with actual IDP0 accounts. |
| Individual/all-session server revoke | No current session ID/epoch store or endpoint. Unsupported by this proposal's wire surface; stronger support requires an explicit AR-034-B design/reforecast decision. Never rotate the artifact key as a workaround. |

Browser states are signed out, authenticated-without-project-access, accessible
viewer, actionable operator/maintainer, administrator-with-separate-project-role,
and dependency unavailable. A null/unknown role disables protected actions and
clears protected data/dialogs; it does not hide own logout. A later successful
refresh restores actions. Credential and protected-view generations fence old
success, error and finally callbacks. Authentication failure requires login;
dependency failure does not invent grant revocation or destroy valid own CSRF.
An admin role hint is never server authority.

## Last administrator and explicit operator recovery

Only the configured human administrator set participates in last-admin policy.
Removing a project maintainer, revoking a project membership or revoking a key
does not remove an organization administrator. Normal operator configuration
changes require the expected current mapping digest, a nonempty next human set
and serialized compare-and-replace with protected audit. Two simultaneous
removals must not leave zero administrators. A nonempty mapping does not prove
that any external account can still authenticate.

Total IdP-side lockout requires an installation operator authenticated by the
approved separate control plane/local procedure. RecoveryRequest is a bounded
offline request, not a credential. Bind the real installation, exact expected
mapping digest, immutable operation ID and replacement exact human identities;
verify authority independently of the inaccessible browser account. Preserve
all project grants, data, histories, token hashes, ciphertexts and audit heads.
No public bootstrap exception, silent admin role assignment or shared key
rotation is allowed. Protect subjects/groups as identity data, not anonymized
hashes. Audit only fixed action, authenticated operator, installation/target,
operation ID and old/new mapping identity; no secret, raw group list or token.

Mapping change, durable idempotent recovery result and protected audit must be
acknowledged together under the chosen storage protocol. If audit cannot persist,
do not apply a new mapping. Same operation ID and exact body recover the original
result; changed body/stale digest refuses without mutation; unknown ACK requires
read-only reconciliation, never blind reapplication. Audit/storage corruption or
missing expected mapping does not authorize reset or force mode. Initial
mapping bootstrap is a separate approved installation procedure, not an invented
zero digest in this recovery API. AR-034-B must choose and review durable storage,
ACK, restart and serialization mechanics before implementing the procedure.

### AR-034-B durable-store entry decision

Preferred candidate: an operator-controlled, versioned installation configuration
record and recovery-result record in the metadata database, with the protected
audit in the same SQL transaction. This keeps CAS, nonempty-admin checking,
idempotent operation identity and ACK/unknown-commit reconciliation at one
durable boundary. It requires an explicitly owned additive migration, privilege
design, literal catalog review and backup/restore/history proof before code;
this proposal defines no columns, revision or implemented store.

Alternative: a protected operator journal is the sole authoritative commit and
audit record, with any SQL projection acknowledged only as derived state. That
would need its own durable replay, corruption, compaction and cross-store
reconciliation design, and is likely broader than the current implementation
card. Existing PublicationJournal is not automatically that protected operator
audit producer. Ordinary file rename followed by a separate SQL audit is
explicitly rejected: neither ordering makes two independent stores atomic.

SEC/TL must accept one boundary before AR-034-B runtime entry. Review must cover
operator credential provenance, runtime read/administration privilege separation,
mapping-version serialization with in-flight requests, concurrent last-admin
changes, audit failure, ACK loss/restart, repeated/changed recovery requests,
revocation after restore and preservation of old rows/ciphertexts/audit history.
The required new administrative authority, group-grant provenance/refresh,
durable recovery store and accessible UI are more work than merely adapting
existing key routes. AR-034-B's current 4 [4–6] days needs a concrete reforecast
at that entry decision if all of these producers require implementation; this
design task does not silently fund them or alter its estimate/status/dependencies.

## Review and evidence boundaries

AR-007-C and AR-003-B are the verified design prerequisites. AR-003-B is not
funding, IdP credential or operator approval. IDP0 depends on AR-034-A and remains
an external customer-identity-administrator gate; reversing that edge would
prevent this offline contract. AR-034-B also waits for AR-033-C composition.
AR-034-C owns actual disposable-user/group/logout/revocation proof after IDP0.
No SCIM, multiple IdPs, customer credentials or production changes are included.

The four-file offline scope fits the existing 2 [2–3] FE-day design package.
SEC/TL/QE peer review must resolve authority, mapping provenance/freshness and
recovery decisions; tests cannot certify those people or their approval.
Future storage/session producers, migration and live account work do not fit
silently inside this estimate. C04/C14 changes would need their own reviewed
contract reconciliation, not an unnoticed edit in C15.

Offline tests validate strict proposal shape, examples and negative/boundary
vectors; they exercise no new routes, databases, browser, IdP or operator action.
Required later proof includes two projects, non-admin non-enumeration,
admin-without-data-grant denial, live cookie/key revocation, malformed group and
manual-grant preservation, key/audit ACK failure, real concurrent last-admin
changes, recovery restart/uncertainty, maximum SQL/cursor work, and the existing
revoked-member /me-to-logout and stale UI response regressions. Synthetic vector
behavior_status remains planned-not-executed. No task or production gate becomes
Verified merely because the OpenAPI model and these tests pass.

## Accepted offline delivery — 2026-10-21

AR-034-A offline C15 is Verified after reviewed source 881096a73224f2ca307d31ebfe26d66c86f8229a merged in PR #103 as 9ee75e785224fc2856e4666e32ef62631ef93454 with an identical tree. PR run 39586855528 and protected-main run 39589239743 passed 3040/3050 tests on Python 3.11/3.12 with 13/3 expected skips and one existing warning each; all 33 publication and 26 recovery PostgreSQL cases ran on both versions. Package/security/CI gate, three gVisor cases and main delivery passed. C authored the contract, A independently accepted the corrected contract and schema, and B accepted composition and both CI runs. Lead verified candidate 12342151758 (585143 bytes), exact four files, source/parent/tree, pinned manifests and package/archive hashes; indexed private release record reviewed-delivery-20261021-pr103-9ee75e7.json is retained outside checkouts. C15 is available for development contract consumption. Administrative services/UI, durable mapping/recovery storage, real IdP and production acceptance remain gated; AR-034-B still waits for AR-033-C and its concrete storage/effort entry decision.
