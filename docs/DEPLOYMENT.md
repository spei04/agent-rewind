# Deployment and operations

This release supports metadata preparation and inspection. Its packaged
compatibility profile is migration-only: customer API/authentication routes return
HTTP 503 and workers exit with `worker_schema_refused:<code>`, even after successful
installation or adoption. The static workbench remains available. No command in
this guide enables customer admission; later reviewed ownership, authorization,
readiness and integration work is required. Production spending and partner data
remain separately gated.

Self-hosted means the adopting organization operates the service in its own
infrastructure, using a dedicated metadata database and artifact storage. It does
not connect to that organization's production application database.

## Local development preparation

`compose.yaml` is a local development convenience, not a production deployment.
It forces development mode and uses the same PostgreSQL initdb superuser for its
API and explicit setup commands. That shared privileged role must never be copied
into a production API/worker configuration. PostgreSQL is not exposed to the host;
the API binds only to loopback. No worker or Docker socket is included.

After creating a private local `.env` (see the repository quickstart), supply a
URL-safe generated `REWIND_POSTGRES_PASSWORD` in the shell or local `.env`:

```sh
docker compose up -d database
# The setup service defaults to read-only status; this does not initialize metadata.
docker compose --profile setup run --rm migrate
```

For a new empty development database, explicitly supply the operator migration
DSN in the shell. This variable is passed only to the setup container; do not add a
production migration credential to an API/worker environment file.

```sh
# Development-only shared role; the hostname resolves inside the Compose network.
export REWIND_MIGRATION_DATABASE_URL="postgresql+psycopg://rewind:${REWIND_POSTGRES_PASSWORD}@database/rewind"
docker compose --profile setup run --rm -e REWIND_MIGRATION_DATABASE_URL migrate \
  rewind migrate install --installation-key local-development
# Inspect the prepared revision and origin.
docker compose --profile setup run --rm migrate rewind migrate status
# Explicit upgrade/re-entry is only for a supported, already-versioned database.
docker compose --profile setup run --rm -e REWIND_MIGRATION_DATABASE_URL migrate \
  rewind migrate upgrade
unset REWIND_MIGRATION_DATABASE_URL
docker compose up -d api
```

If the password is stored only in `.env`, export it privately into the shell before
constructing that DSN; Compose interpolation does not export variables to a parent
shell. Use a correctly encoded DSN for arbitrary passwords. Do not print credentials
or copy them into a command transcript. PostgreSQL mutation commands require
`REWIND_MIGRATION_DATABASE_URL`; `REWIND_DATABASE_URL` alone is insufficient.

`rewind init` creates local secret placeholders only. `init --installation-key`
delegates to explicit installation. Bare `rewind migrate` means upgrade, not fresh
installation, and never adopts unversioned history. The supported baseline has a
linear Alembic baseline/adoption chain; unknown, partial and future states refuse.
Legacy adoption requires backup/drain evidence and explicit mapping/retired-writer
inventory under the [migration procedure](MIGRATIONS.md). Do not run install over
existing history or assume a successful preparation means customer readiness.

## Production design requirements

The accepted reference configuration and deployment review are separate from this
local layout. When a later release is approved, run the API behind HTTPS and use
separate runtime and migration identities. Runtime roles must have no CREATE,
ALTER or stamp authority; the migration credential belongs only to explicit
operator commands. Give the API no Docker socket or model provider key. Worker
machines are dedicated Linux hosts with private access to metadata and object
storage. Provisioning these resources is outside this guide's preparation scope.

Production runtime settings require `REWIND_MODE=production`, an encryption key,
HTTPS public URL, identity configuration and a PostgreSQL psycopg DSN. The runtime
connection profile requires **one numeric TCP host/hostaddr or explicit Unix socket**.
A logical hostname may accompany a numeric hostaddr for TLS hostname verification;
for example, the DSN can retain a managed database hostname and `sslmode=verify-full`
while supplying its approved numeric `hostaddr`. A local database proxy/socket can
also satisfy this boundary. DNS-only or multi-host production DSNs, hidden libpq
service configuration and inherited routing overrides refuse before network use.
This is not a recommendation to disable TLS verification or bypass private networking.

The guard sets pool, connection and server SQL timeouts and limits concurrent API
probes. Synchronous stalled network reads are not proven to meet an end-to-end
wall-clock deadline. The later readiness slice must provide its required bounded
transport behavior; this release makes no HA or rolling-upgrade claim.

## Identity and workers

Customer login, scoped key issuance, histories and submissions remain blocked by
the current compatibility profile. The retained authentication and worker handlers
have unit coverage, but that is not evidence of production authorization readiness.
Production IdP issuer, audience, signed-token validation and project membership
integration require the later scoped authorization work and a deployment smoke test.

For future approved workers, install the signed gVisor package on a dedicated Linux
host using the [official guide](https://gvisor.dev/docs/user_guide/install/), including
its sidecar binaries, register `runsc` with Docker and pre-pull allowed images by
digest. `deploy/rewind-worker.service` is an example, not an active deployment.
The current `rewind worker` fails before claiming jobs or accessing artifacts/models
when compatibility refuses; starting more processes cannot enable it.

Model credentials stay outside sandboxes. Price configuration and conservative
reservations are not provider invoices. Do not automatically replay paid jobs or
release uncertain reservations. The preserved fixture's 245000 microUSD holds are
historical validation data, not permission to spend that amount.

## Storage, recovery and probes

Keep metadata, encrypted objects and encryption keys as a consistent backup set.
Never independently delete referenced objects. Retention, key rotation and cleanup
require explicit operator procedures; this release does not provide automatic
trace retention or garbage collection. S3 provisioning and real customer storage
validation are not performed by metadata installation.

Follow [the recovery guide](RECOVERY.md) for synthetic PostgreSQL backup/restore
coverage, compatible-reader rollback decisions and limitations. The current API
cannot be used to inspect or cancel legacy customer jobs; drain/cancel them with
the old version under the explicit adoption procedure before migration. An older
unguarded binary is not an approved rollback that restores customer access.

`GET /livez` returns 200 `{"status":"live"}` for process responsiveness without a
database or object-store probe. `GET /healthz` retains legacy database-connectivity
semantics: 200 `{"status":"ok"}` when its read-only check succeeds, otherwise a safe
503. It does not certify schema compatibility, object integrity or customer
readiness. The static workbench is inspectable; `/api/schema` remains behind the
customer compatibility guard. Full `/readyz`, sentinel checks and migration of
operator probe consumers belong to AR-011-B and are not implemented here.
