# Security boundaries

## Trust model

Organization administrators, worker hosts, the Docker daemon, base images,
installed policy adapters, and evaluator definitions are trusted. Agent-produced
commands, source files, observations, and model responses are untrusted.
Operators can submit arbitrary code for isolated execution; viewers can read
organization traces. This is a single-organization deployment, not hostile
multi-tenant SaaS isolation.

Production configuration refuses standard `runc`, missing identity settings,
non-HTTPS public URLs, and non-PostgreSQL metadata. Workers require `runsc` and
allowlisted, preinstalled image digests. There is no fallback when the runtime is
unavailable. Standard Docker is available only through explicit development
configuration.

Agent sandboxes have no network, host mounts, Docker socket, model credentials,
service credentials, or elevated capabilities. They run as UID 1000 with a
read-only root, process/CPU/memory limits, bounded temporary storage, and a host
wall-clock deadline. Evaluator files are mounted read-only in a separate
container and are absent from agent steps.

The trusted worker needs Docker access, which is powerful host access. Keep it
on dedicated hosts, separate from the API and sensitive application services.
gVisor reduces kernel attack exposure; it does not replace host maintenance,
network policy, image review, or a careful evaluator.

## Authentication

OIDC uses authorization code flow with PKCE, signed token validation against the
issuer's JWKS, issuer/audience/expiry checks, a nonce, and a short encrypted login
state cookie. Sessions last 15 minutes. Cookie-authenticated writes require an
exact origin match and a CSRF token. Version-2 sessions bind the subject to the
configured exact issuer; roles in cookies or OIDC claims confer no project
rights. Every data request checks current explicit project membership. Existing
routes require an active `legacy_default` grant; a sole membership is not an
implicit default. Revocation and role changes apply on the next authority check.
The retained `REWIND_OIDC_ROLE_CLAIM` option is ignored for HTTP authorization.

API keys contain random entropy, are stored as hashes, expire within 90 days,
and can be revoked. Only a human project maintainer can issue viewer/operator
keys. Issuance atomically records the key, project scope, matching explicit
default membership and audit; service keys cannot manage keys. Effective key
rights intersect current key validity, token role and current membership.
Bootstrap secrets are not customer HTTP credentials, including during setup.

Authenticated `/api/me` returns only the caller's identity, CSRF token and an
optional current default-project role. Missing or revoked membership yields a
null role so a freshly loaded browser can still log out. Logout always checks
the version-2 cookie, its CSRF token and exact origin, even when a bearer header
is also present. Other routes give an explicit Authorization header precedence
over cookies; an invalid header cannot fall back to a valid session. These
identity exceptions do not bypass the schema compatibility guard.

Put the API behind TLS and a rate-limiting ingress. A company VPN limits network
reachability; it does not replace authentication or audit trails.

## Data

File contents, checkpoint state, event payloads, job payloads, evaluator output,
and model responses use authenticated application-level encryption before local
or S3 storage. Metadata and audit records live in PostgreSQL; deploy database
storage encryption and TLS separately. Object hashes support deduplication and
integrity, and reveal equality within a deployment.

Existing HTTP artifact views use only registered project/owner/role references
and verified complete run graphs. Unregistered historical objects remain
unavailable; projection backfill does not register their bytes. The current
scoped HTTP adapter supports local storage. Configured S3 reads fail safely
after authorization until the scoped remote adapter is delivered; HTTP routes
do not fall back to raw hashes, unscoped S3 access or local files. Non-HTTP legacy
storage consumers retain their existing compatibility behavior.

Literal redaction rules apply to captured tool observations, policy state, and
workspace snapshots. They make affected runs non-branchable. Submitted task
manifests are encrypted configuration records and remain available to workers;
do not put credentials in task manifests or redaction rules. Prefer worker-side
secret configuration. Redaction is not an automatic secret-discovery system.

Keep the encryption key in a secret manager. Back it up separately from the
artifacts. Losing it loses the ability to read every encrypted object. This
release requires an offline re-encryption procedure for key rotation; there is
no built-in multi-key rotation manager.

Hash chains detect corruption and inconsistent history. They are not signatures
against an administrator who can rewrite both the database and artifact store.

The browser renders untrusted content as text, uses a restrictive content
security policy, and keeps service API keys in memory only. Model keys are never
browser credentials.
