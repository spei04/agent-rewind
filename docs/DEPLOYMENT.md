# Deployment and operations

Self-hosted means the adopting organization operates the service in its own
infrastructure. It does not mean Agent Rewind connects to that organization's
production application database. Provision a dedicated metadata database,
artifact bucket, and worker machines.

## Control plane

Run the API behind an HTTPS reverse proxy. Set `REWIND_MODE=production`, a
PostgreSQL DSN, encryption key, public URL, identity settings, and S3 storage.
Use the same encryption key and bucket on the API and workers. Give the API no
Docker socket and no model provider key.

`compose.yaml` provides a local control-plane layout. It intentionally does not
expose PostgreSQL or include a privileged worker service. For this local layout:

```sh
# Supply REWIND_POSTGRES_PASSWORD in the local environment or .env.
docker compose up -d database
docker compose --profile setup run --rm migrate
docker compose up -d api
```

Use a URL-safe generated database password in this Compose example. For a
production deployment, supply a correctly encoded DSN through your secret
manager, use a managed or independently operated PostgreSQL database, and place
workers on dedicated Linux hosts with private access to that database.

The initial schema is created with `rewind migrate`. It is idempotent; this
release has no later schema revisions. Back up before upgrading to a future
revision. Runtime roles need no schema modification rights after initialization.

## Identity

Register a web client with your identity provider:

- Callback: `https://YOUR_HOST/auth/callback`.
- Authorization code flow with PKCE.
- ID token containing a dedicated `rewind_role` claim.
- Allowed claim values: `viewer`, `operator`, `administrator`.

Configure issuer, client ID, optional client secret, and expected audience. The
issuer discovery document must match the configured issuer and advertise HTTPS
endpoints. Scope API keys through the administrator-only `/api/keys` endpoint.
The authentication implementation is tested with signed local fixtures;
your organization's actual identity-provider configuration needs a deployment
smoke test.

## Workers

Install the signed gVisor package on a dedicated Linux host using the
[official installation guide](https://gvisor.dev/docs/user_guide/install/).
Register `runsc` with Docker, then test a known container. Preserve all package
sidecar binaries; a standalone copied binary is not a complete current install.

Install this repository from its lockfile, pre-pull allowed task images by digest,
and configure a worker-only environment file. Run `rewind doctor`, then
`rewind worker`. `deploy/rewind-worker.service` is a systemd example. Docker group
membership is powerful; this service account belongs only on the dedicated
worker host.

The worker uses its model API key outside sandboxes. Set the selected model's
input and output rates in USD per million tokens. In-flight calls reserve a
conservative amount before dispatch. Reservations are not released on uncertain
failures, and the application does not automatically retry provider calls.
Pricing correctness is an administrator responsibility; software reservations
cannot override the provider's billing rules.

Use multiple worker processes to handle concurrent jobs. They share PostgreSQL
and encrypted object storage. PostgreSQL row locks coordinate claims. A study
runs sequential pairs in its current worker; distributed within-study fanout is
a future extension.

## Storage and retention

An S3 bucket must already exist. Grant only object read/write and the minimum
bucket permissions your setup requires; public access is unnecessary. Standard
cloud credential mechanisms configure the S3 client. The application also
encrypts object contents before upload.

Objects are content-addressed at file granularity. Identical unchanged files are
shared between checkpoints. Temporary shell workspaces live on tmpfs and are
removed after each command. Neither traces nor secrets are included in the Git
repository.

Back up PostgreSQL, the bucket, and encryption keys as a consistent operational
set. Do not apply independent object lifecycle deletion to referenced blobs.
This release does not include automatic trace retention or garbage collection.
Retention and key rotation require an explicit operator procedure.

## Failure recovery

- Inspect `/api/jobs` for terminal status and conservative budget reservations.
- Cancel queued/running jobs through the authenticated API.
- Wait for an outstanding provider call to return or time out; cancellation
  cannot guarantee a provider did not already bill that call.
- Expired worker leases become failed. Do not blindly replay a failed paid job.
- Partial runs and studies are retained for diagnosis.
- Worker startup reaps only labeled abandoned resources older than the maximum
  job lifetime plus a margin. Active tool containers have a 600-second lifetime.

Deploy ingress request-rate/concurrency limits and monitor worker memory,
PostgreSQL connections, object storage growth, and provider spend. The service
reports readiness at `/healthz` and provides its authenticated API schema at
`/api/schema`.
