# Scoped repository boundary

AR-007-B provides a preparatory internal read interface. It does not migrate
routes, authenticate a request, enable a second project or change the packaged
migration-only compatibility profile. Legacy Database methods remain for existing
internal callers; AR-007-C must inventory and replace route access before
customer admission. No production authorization claim follows from these tests.

## Explicit identity and current access

Every public operation on ScopedRepositories requires ProjectContext containing
organization_id, project_id and an already authenticated principal_id. The context
is not authentication evidence. Its issuer-bound OIDC identity must come from
verified issuer/subject claims; API-key identities must come from verified tokens.
Raw legacy subjects, bootstrap identities and claimed roles are not accepted.
There is no implicit default project or organization-administrator data grant.

The repository joins the named project to its organization and current,
non-revoked membership on every operation, then applies the C05 action matrix.
API-key principals additionally require the same-project key scope, current
non-revoked key, future expiry and live key-role ceiling. Viewer and operator
keys cannot exceed either their key role or membership. A retained legacy
administrator key can have at most operator authority, and only with an explicit
current project membership. Its old role never creates a grant. Keys cannot create
or revoke keys through this interface. Key metadata returned to callers excludes
token hashes.

ResourceNotFound has one fixed message for missing, foreign, unmapped, malformed
and invalid-lineage resources. Database failures produce RepositoryUnavailable
with a fixed message, without SQL, credentials or resource identifiers. The later
route boundary owns mapping these typed failures to public responses.

## Scoped SQL and lineage

Run, study, job, key, list and event-reference reads join resource_scopes before
selecting returned data. Job-to-record discovery also joins the requested project
before its limit; another project's forged incoming reference cannot contaminate
the authorized project's result. Each discovered record independently passes its
scope check before its JSON is loaded.

The lineage check verifies same-project job/parent/source/trial references,
parent acyclicity, exact request/source agreement, unique study ownership and
unique present trial claims. Failed trial runs persisted before an arm ID was
returned remain valid when a unique study job and matching source establish
their relation. Missing outcomes are never invented. Authoritative SQL record
IDs and creation times cannot be overridden by JSON fields.

This is a bounded connected-component read, not a global integrity audit.
Limits are 2 MiB per record/job/key metadata row, 2,048 connected resources,
4,096 reference edges, 64 parent edges, and 16 MiB retained encoded record/job
representation. The byte bound is not a Python RSS estimate. Lists return at
most 100 resources and 8 MiB of encoded metadata; direct event-reference reads
return at most 10,000 rows, reject any event row over 256 bytes, and do not
implicitly load inherited events.
Overflow refuses rather than returning a partial authorized result.

Legacy JSON job-reference queries may still scan scoped source records; these
limits bound returned/retained work, not database scan time or network wall time.
Indexed projections and endpoint paging belong to their later slices. The
interface assumes a trusted configured engine and a release-compatible schema
at its caller boundary; it does not replace schema inspection or add DDL.

## Artifact handoff

The structural protocols in agent_rewind/scoped_artifacts.py coordinate with
AR-009-A without requiring its unmerged migration. The resolver signature is:

    resolve_ref(connection, *, project_id, owner_kind, owner_id, role, digest)
        -> ArtifactObject | None

It performs SQL only and must join a published artifact reference, its object and
the matching resource scope. ArtifactObject is immutable metadata with id,
project_id, digest, locator, format_version, byte_count and a UTC created_at.
The loader accepts only that descriptor and validates format, locator, bounded
ciphertext/plaintext, encryption and digest. No direct hash or locator read is
provided by the repository.

read_artifact requires explicit context, owner kind/ID, role and digest each
time. It authorizes current identity and complete owner lineage before invoking
the resolver. Missing metadata or an absent adapter refuses; historical hashes
never fall back to the legacy global store. Equal hashes in two projects need
separate project/owner/role references.

The SQL connection is released before storage/decryption. After loading, another
fresh authorization and reference resolution must succeed with the same object
identity before bytes are returned. Membership/key revocation, owner scope loss
or changed references during I/O prevent return. This does not promise network
response linearizability; AR-007-C still owns request and streaming boundaries.
resolve_artifact returns an internal descriptor only. It must not be exposed as a
public locator or retained as permission for a later operation.

The fixed system sentinel has no path through these customer repositories.
Provider-call artifact access awaits its own reviewed resource implementation.

## Validation and integration limits

Synthetic SQLite tests cover the role matrix, issuer identity separation, key
role/expiry/revocation intersections, all resource kinds, forged and incomplete
lineage, bounded reads, uniform denial, hash reuse across projects and revocation
during loader I/O with zero checked-out database connections. Resolver/loader
spies prove rejected owners never reach artifact metadata or storage.

Opt-in PostgreSQL tests use the existing disposable service and a separate
SELECT-only runtime role for project isolation, incomplete/forged lineage and
post-I/O revocation. Their execution requires hosted integration evidence.
Actual AR-009-A object/ref storage integration, encrypted child reachability,
route authentication/CSRF, writes and customer admission remain separate gates.
