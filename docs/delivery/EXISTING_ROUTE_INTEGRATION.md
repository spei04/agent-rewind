# Existing route integration (AR-007-C/P2)

This slice wires the existing HTTP routes to current project authority. Every real
release profile remains migration-only. Tests that reach routes use the named
synthetic behavior fixture; no production profile or admission bypass is added.
Named-project authority remains a server dependency for future paths, not a new
legacy header/query selector. AR-006-B and later debugger/export routes are outside
this slice.

## Identity and action boundaries

OIDC validates signature, exact issuer/audience, nonce and expiry before issuing a
strict issuer-bound version-2 session. Cookie role claims and legacy bootstrap
secrets are not HTTP authority. Explicit Authorization headers take precedence on
normal routes; invalid headers never fall back to cookies. Logout always uses the
cookie itself, its CSRF token and exact Origin, regardless of a bearer header.

`/api/me` returns the caller's issuer-bound identity and own CSRF, with an optional
current explicit-default effective role. Missing/revoked/ambiguous default yields
null; genuine database failure remains 503. This lets a revoked member reload and
log out. `/api/schema` remains default-scoped. The UI treats only operator and
maintainer as action-capable. Manual refresh and polling re-read the current role;
null/unknown roles or a failed data refresh clear earlier protected state, close
privileged dialogs and disable actions while preserving own CSRF/logout. Submission
handlers recheck the role hint, and a later successful operator refresh restores
actions. Switching credentials advances an in-memory identity generation: obsolete
refresh/selection responses, failures and completion handlers cannot restore old
identity/data, clear new credentials or release the new lookup's busy state. No
token persistence is added. Clearing protected state also advances a separate view
generation, so a previously requested detail/file/comparison cannot repopulate
cleared data after same-credential authority loss or data failure. Own identity,
CSRF, logout and subsequent authorized recovery remain independent. The server
remains the authority for every request.

All resources are scoped before action decisions: inaccessible/missing/invalid
resources return fixed 404; an accessible resource with a denied action returns
403; invalid credentials return 401. Service-key rights intersect current finite
expiry, revocation, token role and current membership. Human maintainers alone
issue viewer/operator keys. Issuance writes an explicit default for the authorized
project atomically with key, scope, matching membership and fixed audit; authentication
never substitutes a sole-membership guess.

`ScopedActions` owns each short cancellation/key/audit transaction. Routes pass the
original context and verified principal, not a cached role. Successful verified
run detail calls `record_run_read` before responding; revoked/failed/unsupported
reads produce no success audit. The reader remains SELECT-only. No bytes or network
work occurs under action locks, and uncertain commit acknowledgment never returns
a new token or retries automatically.

## Read representations and bounds

Run/study lists and study detail are scoped SQL metadata views. They do not certify
capture completion or artifact availability. SQL identity and creation time override
historical JSON fields. Invalid selected rows refuse rather than silently disappear.
Run detail, files and comparison require complete, uniquely rooted published graphs;
complete runs with unsuccessful evaluations remain complete with success=false.
Missing, ambiguous, incomplete or unpublished graphs have no raw legacy fallback.

Pure presentation validates the opaque containers it consumes, including exact
workspace change entries (normalized path plus added/removed/modified), while the
shared graph verifier retains its intentional policy-payload opacity. Missing
step/path is 404; invalid path is the existing 422. Workspace file bytes/mode/kind/mtime
and ancestor owner bindings come from verified graph objects. Displayed file content
is capped at 100,000 bytes; compare uses that input ceiling per side/file and a
12,000-character displayed diff. The existing two-graph, 16,000-ref, 64-MiB combined
loaded-byte limit is unchanged.

SQL lists select at most 100 rows. A request-wide work budget includes repeated
lineage checks, including both artifact-loader authorization passes: 2,048 nodes,
4,096 edges and 16 MiB canonical row representations. Each source row has the
existing 2-MiB SQL prefetch bound. Responses cap at 8 MiB. Original raw source
receipts have a separate 4-MiB/2,048-identity ceiling (plus at most one 4-MiB encoded
rowset); these representation bounds are not measured Python RSS. SQL field sizes
are checked before driver materialization, including SQLite NUL/dynamic cells.

After sequential closure checks, one materialized bounded JSON rowset compares all
original source fields and scopes and detects new by-job members. It returns only
bounded input kind/id identities, with constant bind count; no source bodies cross
the driver in this final statement. It uses the P1 SQLite 3.35+/JSON or PostgreSQL16
JSONB assumptions. A final fresh authority check follows. This is optimistic READ
COMMITTED revalidation, not response linearizability or a future grant.

Job result bytes require their own scoped job/result descriptor and a supported
exact run_id or study_id object (at most 1 KiB). Every requested result ref is scoped
before I/O. Original seven-field descriptors survive all reads; one final ref check
and source/target closure check reject a changed earlier result or target while a
later item loads. No database connection is held across storage. Unsupported result
shapes and missing refs refuse; hashes in arbitrary payloads are never crawled.

HTTP uses the local scoped verified storage adapter. A configured S3 backend refuses
after authorization without initializing a raw S3 client or falling back to local
files. The future scoped remote-storage integration owns that limitation. Historical
ownership/projection backfill does not register artifact refs. Existing non-HTTP
legacy artifact consumers are retained.

## Admission and remaining evidence

All four existing work-creation routes authenticate and establish current resource
visibility/action rights, then call a required unavailable admission interface
before readiness probes, storage, enqueue, audit or provider work. AR-008-A/B and
AR-010-B must supply the reviewed scoped configuration/idempotency/dispatch adapter;
there is no raw Database.enqueue fallback. Generation-fenced live publication is
still unavailable and remains owned by its existing later integration slices.

Local fixture tests establish only the synthetic behavior they execute. Actual
PostgreSQL source-receipt/concurrent-change and atomic-action cases, installed-wheel
smoke, and exact full route guard checks remain required hosted delivery evidence.
