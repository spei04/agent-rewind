# Ownership initialization contract (C05)

AR-007-A implements one operator-only ownership revision. It does not enable
customer admission, authorization routes, a second project, artifact publication,
run projections, provider calls or a budget ledger. Both recognized revisions
remain migration-only. The release guard API stays unchanged.

## Inputs and retained provenance

`install` and `adopt` prepare revision `ar_0002_adoption`. The explicit command
`rewind migrate ownership --input <private-fresh.json> --batch-size 1000`
advances to `ar_0003_ownership` and processes at most one bounded scope batch.
Legacy initialization omits `--input`; replacement legacy intent is forbidden.

Fresh JSON has schema_version=1, installation_key, organization_id, project_id,
project_name and principal_grants. IDs are lowercase 32-character hex. Names are
1–120 printable characters. Grants explicitly name issuer-bound OIDC principals,
viewer/operator/maintainer roles and legacy_default booleans. There are 1–256
distinct grants, no inferred process user and no service keys in an empty
installation. The file must be an owner-owned regular file with no group/other
permissions and at most 64 KiB, without duplicate JSON members. Canonical fresh intent is capped
at 48 KiB to leave room for progress metadata.

Legacy uses the exact adopted mapping, including source digest, explicit principal
grants, key dispositions and retired writer inventory. Its display name is
`Legacy project`; naming is not a new ownership decision. Original mapping,
mapping digest, creation time and backup/drain evidence remain unchanged.
Fresh original empty-source mapping and null backup/drain evidence also remain
unchanged. Separate progress stores fresh initialization intent.

## Closure and resumption

The frozen closure contains each run, study, job and key once; provider_call has
no source in this revision. Events inherit their run and require an existing run.
Run parent and job IDs must resolve. Parent chains must be acyclic. Study source
and request run IDs must agree; study job IDs must resolve. Present control and
treatment run IDs in candidate and confirmation pairs must resolve, descend
directly from that source and belong to the study job. A trial run cannot occur
in two arms/pairs/studies. Missing outcomes are preserved, but ambiguous ownership
does not complete. Unknown record/job kinds and malformed identifiers refuse.
Encrypted job payloads/results and artifact content are not decoded here; later
artifact integrity and admission gates remain required.

Every invocation recomputes a bounded original-source digest and deterministic
closure under writer exclusion. At most 100,000 resources and 1,000,000 original
rows are supported by this initial profile; source byte bounds from adoption
apply. Retained identifier/edge representation is capped at 32 MiB, with at most
200,000 relational edges and 64 parent edges per chain. This is not a measured
Python RSS bound. Rows are streamed and discarded after reduction; no source
JSON bodies accumulate in the graph. Every invocation repeats a bounded full
source scan; this is an offline adoption cost, not a scalable-throughput claim.
A batch is 1–1000 resources in lexical (kind,id) order. Cursor, source and
closure digests, immutable intent and emitted prefix count are durable. An exact
already-written prefix is checked before adding rows; foreign or extra scopes
are never overwritten. Scope inserts and progress advance share one transaction.
The first transaction also creates the revision and fixed organization/project/
memberships. Completion checks full source and output before transitioning the
adoption row to ownership_complete. A crash yields either the old batch or the
new batch, never a cursor ahead of scopes. Changed source or intent refuses
resumption; recovery requires operator review, not automatic remapping.

PostgreSQL repeats existing writer/role exclusion for every batch. SQLite uses
its exclusive transaction and operator-attested process drain. Malformed or
unmappable history stays preserved and unready; no destructive quarantine or
silent omission is performed.

## Role/action decision table

| Role | Permitted project actions |
| --- | --- |
| viewer | read, list, compare |
| operator | viewer actions plus record, branch, study, investigate, cancel |
| maintainer | operator actions plus create_key, revoke_key |

Unknown roles/actions deny. Organization administration is not a project role;
it grants no data action by itself. Issuer-bound principal construction uses
the canonical exact verified issuer and subject. Authentication verification
and request authorization are later slices.

All original keys receive immutable project scope. Only explicitly mapped
matching viewer/operator key grants get membership. Disabled/unmapped keys
remain unusable; revoked or already-expired keys receive revoked memberships,
without changing token hashes, expiry, roles or revoked flags. Live-key/membership
intersection and revocation checks belong to request authorization.

## Evidence required

Independent literal SQLite/PostgreSQL catalog profiles, frozen 14-row/18-object/
245000-hold preservation, fresh null-evidence transition, invalid lineage and
foreign-scope refusal, bounded batching, exact retry, fault-before/after-commit,
competing writers and least-privilege PostgreSQL checks are required. No written
contract substitutes for hosted integration evidence. Restore compatibility must
retain the original profile identity and all prior guard/recovery regressions.
