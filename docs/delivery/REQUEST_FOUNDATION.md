# Existing-route request foundation (AR-007-C/P1)

This package is preparatory. HTTP authentication, session issuance, routes, UI,
cancel/key mutations and admission are unchanged. P2 must integrate the complete
route matrix after this package is independently accepted and merged. All release
profiles remain migration-only; no helper is an admission or publication bypass.

## Identity and current project authority

`request_identity` supplies a bounded strict v2 Fernet codec and issuer-bound
principal values. Its factory is called only after a trusted authenticator has
validated exact issuer, audience, signature, nonce and expiry, or the supplied API
token. Constructing a principal does not authenticate credentials or grant access.
Sessions contain exact version/principal/issuer/subject/CSRF fields and no role.
Version 1, duplicates, extra fields, malformed/expired tokens and issuer changes
refuse with a fixed identity failure.

`RequestAuthority.legacy` resolves exactly one active explicit legacy-default
membership, with a two-row ambiguity bound. `named` is the future server path
dependency, not a new legacy header/query selector. Both join organization/project
ownership, enforce current membership and the live key ceiling, and return a frozen
context for that operation. A changed default does not redirect a bound operation.
`check(connection, ...)` rechecks the same context on its supplied connection; it
takes no locks and is not a later-write capability. P2 mutations must own exclusion
and reauthorize in their transaction.

Identity failure, inaccessible project/resource, accessible denied action and SQL
unavailability remain distinct typed decisions. Resource visibility is checked
before the action decision. API keys retain SQL unrevoked filtering, finite future
expiry and viewer/operator ceilings; a mapped historical administrator key has only
an operator ceiling with an explicit current grant. Keys cannot manage keys.
`legacy_role` returns null only for missing/inaccessible/ambiguous scope, not a
database failure. The later identity-only me/logout policy is not wired here.

## Published graphs and compound reads

`PublishedRunReader(engine, storage)` has no journal or writer.
`read(context, run_id, root_digest)` preserves explicit-root behavior;
`RunPublisher.read` delegates to it. `read_current` first authorizes the actual
run/lineage, then requires exactly one registered project/run/result/format-1 root.
Zero or multiple roots refuse; neither legacy JSON nor first/latest-hash selection
is a fallback. Earlier valid explicit roots remain explicitly readable.

`read_many(context, requests)` verifies up to two run graphs for the existing
comparison use case. Every requested run/root is scoped before the first storage
read. It preserves real ancestor owners and all seven immutable
descriptor fields, and caps the combined operation at 16,000 distinct owner/ref
identities and 64 MiB of loaded bytes. Repeated bytes still consume the combined
budget. Shared SQL CASE descriptor bounds apply to initial, post-I/O and final lookups;
per-object content limits are checked before backend reads. Explicit root digests
also require their owner-scoped result ref during compound preflight. No SQL
connection is held across storage/decryption.

After all I/O, a SQL-only pass validates every graph owner and any unique-root
selection, then reads the entire expected ref set in one statement. The JSON rowset
is capped at 4 MiB; one JSON bind carries all refs, with a fixed number of additional predicate/limit
binds (at most 64 SQLite positional slots), regardless of graph size. This uses SQLite's already-required JSON functions or
PostgreSQL 16 builtin JSONB, without an extension. The result has a maximum of expected refs plus one row;
SQL CASE bounds each descriptor's text representation (384 bytes across its seven
fields) before driver materialization. Fixed-width expected owner/role/digest
fields add at most 106 bytes per row. Fresh authority is checked again at the end,
so revocation while earlier refs are being checked refuses returned bytes.

This is optimistic READ COMMITTED revalidation. Each statement has its own snapshot;
it does not promise response linearizability or grant future access. There are no
reader locks, UPDATE privilege requirements, counter/ref mutations or filesystem/SQL
atomicity claims. The underlying graph verifier, scoped loader and complete graph
format remain shared with the accepted publication coordinator.

Historical adoption/backfill does not publish artifact refs. Such unregistered
evidence remains inaccessible. The live generation/DB-time publication adapter is
still unavailable; this reader does not supply one. Actual PostgreSQL revocation
and installed-distribution evidence are required in hosted CI before P1 acceptance.
