# Reference staging configuration

AR-033-A · C14 version 1 · proposed internal deployment contract.

This contract describes the inputs for the **AR-033-B staging foundation**, following
[C03 trust boundaries](TRUST_BOUNDARIES.md) and the
[capacity and funding record](CAPACITY_AND_FUNDING.md). It does not provision anything.
One organization owns a dedicated project, metadata database and artifact store.
There is no connection to an adopter's application database.

The [JSON schema](../../contracts/reference-config.v1.schema.json), generated from
[the offline validator](../../scripts/reference_config.py), defines the wire shape.
The [synthetic example](../../contracts/fixtures/reference-config.synthetic.json)
is deliberately marked synthetic with no approval record. Its project, region,
operators, prices and budget are invented test inputs. In particular, neither
`us-central1` nor the example dollar limits have been approved. The owner's
existing $200 model-validation ceiling is separate and unchanged.

## Validation and admission boundary

Run from a locked development environment:

```sh
python scripts/reference_config.py contracts/fixtures/reference-config.synthetic.json
python scripts/reference_config.py private-config.json --deployment-review
```

Normal validation checks the complete configuration, private network ranges,
role separation, resource relationships, the connection envelope, and cost totals.
It accepts a complete synthetic draft for review. The second command also requires
a non-synthetic request and an ENV0 record with approver, private evidence identifier,
approval/expiry timestamps and the exact configuration SHA-256. It rejects missing,
future, expired or changed records. Approval must expire no later than the declared
staging stop time. The hash covers every configuration field except the approval
record, using sorted compact JSON after typed normalization.

**Both commands always report `deployable: false`.** An evidence ID and digest in a
file do not authenticate an approver or establish authority. AR-033-B must resolve
that private record through the deployment operator's trusted approval process,
verify the actual owner/budget/region/scope and freshness, inspect the resulting
plan, and recheck the digest immediately before apply. Changing `synthetic` to
false or inventing an approval cannot grant authority. There is no apply command,
cloud client, credential lookup, provider request or IAM mutation here.

The schema rejects unknown fields; identifiers are opaque references, never
credentials or personally identifying label text. On POSIX hosts, parsing uses a nonblocking open that refuses a final-component
symlink and checks the opened descriptor is a regular file before reading. FIFOs/devices/directories are refused; both file-size
and bounded-read checks reject inputs above 64 KiB. Duplicate JSON keys are rejected. CLI errors expose bounded field/type codes and do not echo submitted values or unknown field names. Schema-only
validation does not enforce cross-field policy; consumers must also run the typed
validator. Syntax cannot prove a region/SKU exists, a bucket name is available,
an estimate is current, a referenced human has approved it, or a firewall works.

## Topology and resource contract

The reference foundation uses a dedicated GCP project and VPC, Cloud SQL PostgreSQL,
regional Cloud Storage and KMS, named Secret Manager resources, Cloud Run API
placement and dedicated Compute Engine worker placement. No worker image or
application service is deployed in AR-033-B; placement and capacity are reserved
inputs for AR-033-C. A new resource must be in the reviewed inventory and priced
before it can be added to the plan.

| Input | AR-033-B materialization / denial constraint | Cost line |
| --- | --- | --- |
| `region`, `project_id`, labels | One approved region; installation/environment/owner/cost-center labels on supported resources, inventory mapping where labels are unsupported. Never reuse shared/live resources by matching a name alone. | All lines |
| Four network ranges, operator CIDRs | Distinct canonical RFC1918 API, worker, internal proxy and SQL private-services ranges; at least /24 for the SQL region. Private operator access through an already approved VPN/Interconnect path. No default Internet allow rule. | network |
| `network.ingress` | Internal HTTPS load-balancing/private application route only; API ingress internal, VPC routing explicit. User authentication remains required. Certificate/private DNS, approved operator connectivity and firewall ownership must appear in the plan. | network, api-compute |
| `network.private_google_access` | Private DNS and Google API routing for Storage/KMS/Secret Manager/control APIs; restrict destinations and IAM. Private routing alone is not authorization or a VPC Service Controls perimeter. | network |
| `database` | Dedicated regional HA PostgreSQL 16, private IP only, IAM authentication and connector enforcement, encrypted connector traffic, backup/PITR retention, deletion protection. Instance/location derive from this project/region. | sql-compute, sql-storage-backups |
| `storage` | Distinct artifact and provisioning-state buckets, same region, enforced public-access prevention and uniform bucket IAM; state versioning. No automatic artifact lifecycle deletion before AR-032 reachability/retention. | artifact-bytes, artifact-operations, state-support-contingency |
| `keys` | Regional artifact encryption key and separate API session, OIDC client and worker provider secret resources. No secret versions/values or downloaded service-account keys in configuration or IaC state. Native GCS/KMS artifact integration remains AR-016. | keys-secrets |
| `capacity` | Explicit API CPU/memory/instance and worker machine/disk/host/process limits, API/worker process counts, explicit per-process pool sizes and maximum overflow, operator reserve and object-operation envelopes. No autoscaling beyond these maxima. | api-compute, worker-compute-disks, artifact-operations |
| `logging_retention_days` | Bounded service/control-plane telemetry retention; no task source, tool payload, tokens or credential material. Private evidence retention follows its own approved policy. | observability |
| `staging_stop_at`, budget owners | Scheduled operator review/stop deadline; no claim the validator stops running resources. Teardown requires the labeled inventory and explicit retention disposition. | state-support-contingency |

No public worker IP, public database, remote Docker listener, arbitrary Internet
egress or guest metadata route is allowed. Both agent and evaluator containers
retain `runsc`, network-none and the complete C03 mount/credential/resource profile.
A trusted worker may use its platform identity endpoint; the sandbox must not.
A dedicated worker compromise remains a deployment incident, not a gVisor guarantee.

The foundation starts with **external application egress blocked**. Model/IdP
endpoints and approved data processing are integration inputs for AR-033-C and
IDP0/PAID0, not implied permission from this foundation. Bootstrapping signed images,
host patches and cloud control APIs requires a separately reviewed operator path;
do not turn a general NAT gateway into an application egress allowlist. Enabling
external destinations requires a versioned C14 extension and renewed digest-bound
approval before composition. This restriction preserves C03's intended external
flows while denying them until their real destination/processor policy exists.

## Flow and IAM review map

These rows account for all 15 allowed direct connections in the C03 fixture.
A target permitted by C03 is an upper bound; foundation-only restrictions may
keep it disabled. Every untrusted-sandbox outgoing edge and the other 40 explicit
C03 denials remains denied. DNS/platform plumbing does not introduce guest access.

| C03 source → target | Enforced interface / authority | Cost line |
| --- | --- | --- |
| browser → ingress | Private operator connectivity, HTTPS and authenticated app; activation waits for composition/identity. | network, api-compute |
| ingress → api | Internal application route; no direct public service path. | network, api-compute |
| api → metadata_db | Private connector plus runtime SQL DML grants. | sql-compute |
| api → artifact_store | Bucket-scoped create/read of encrypted objects, no delete/list-all-project access. | artifact-bytes, artifact-operations |
| api → identity_provider | Disabled in foundation; approved OIDC discovery/token/JWKS destinations at composition. | network |
| browser → identity_provider | Interactive login at configured IdP; no cloud resource authority. | network |
| api → key_service | Artifact cryptographic operations and API-only secret resource reads. | keys-secrets |
| worker → metadata_db | Private connector plus runtime SQL DML grants. | sql-compute |
| worker → artifact_store | Same scoped encrypted-object create/read boundary. | artifact-bytes, artifact-operations |
| worker → model_provider | Disabled in foundation; approved endpoint, worker-only secret and funded application ledger at composition. | network; model inference separately funded |
| worker → key_service | Artifact cryptographic operations and provider-only secret read. | keys-secrets |
| worker → docker_daemon | Local Unix socket on dedicated worker; no TCP daemon listener. | worker-compute-disks |
| migration_operator → metadata_db | Separate temporary maintenance identity and SQL DDL grants, writer exclusion and verified backup. | sql-compute, sql-storage-backups |
| api → cloud_metadata | Platform workload identity bootstrap only; no service-account key file. | api-compute |
| worker → cloud_metadata | Host workload identity bootstrap only; no endpoint inside guests. | worker-compute-disks |

The four configurable service accounts must be distinct and have exactly their
declared capability sets. C14 capabilities describe required grants, not executable
cloud IAM role strings. AR-033-B must translate them into a reviewed concrete policy:

| Capability / holder | Concrete grant boundary and required negative check |
| --- | --- |
| database-dml / API, worker | Cloud SQL connector access and IAM login plus PostgreSQL DML on the owned application schema. IAM login does not grant SQL table access. Deny DDL, other databases and migration impersonation. |
| database-ddl / migrator | Cloud SQL connection/login with distinct SQL migration grants. No artifact, model-secret or worker-host authority. Availability alone does not bypass AR-005 maintenance locks. |
| artifact-create-read / API, worker | Custom role limited to `storage.objects.create` and `storage.objects.get` on the artifact bucket. No bucket administration, state reads, object deletion or implicit per-product-project IAM guarantee. AR-009/016 enforce application scope and immutable publication. |
| artifact-crypt / API, worker | `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the artifact key, never key administration or destroy authority. |
| api-secrets-read / API | `roles/secretmanager.secretAccessor` on session/OIDC resources only; provider secret denied. |
| provider-secret-read / worker | Secret accessor on provider resource only; API secrets denied. No paid call is authorized by possession of a key. |
| local-docker / worker | Host-local Docker group/socket only; not a cloud IAM grant. API and all sandboxes denied. |
| foundation-manage, scoped-iam-manage / provisioner | Trusted, short-lived deployment identity for this dedicated project, reviewed resource types and allowed role bindings; never a runtime identity or project Owner/Editor shortcut. Exact creation permissions must be derived from the actual 033B plan. |
| state-read-write / provisioner | State-bucket-only role with required version/object and lock operations; runtime identities denied. Protected remote state and versioned recovery are required before apply. |

Cloud SQL connector/login normally needs `roles/cloudsql.client` and
`roles/cloudsql.instanceUser`. Some control permissions are project-scoped, so
document their real scope rather than claiming per-instance IAM isolation.
The dedicated project, SQL users/grants and live deny tests jointly enforce the
boundary. Google-managed SQL/Storage/KMS service agents and bootstrap operators
are additional infrastructure principals: 033B must enumerate their actual grants
and impersonation edges in the plan. This validator cannot certify them.

## Funding and downstream handoff

Ten cost lines are mandatory, unique and included in the monthly sum; bootstrap
estimate has a separate bound. Amounts are integer micro-USD. A non-synthetic
request needs quote or explicit allowance references with owners; references
remain private and require verification. The state/support/contingency line must
price or reserve remaining staging costs, including control-plane state,
support/taxes and bounded teardown. Cross-region recovery, customer rollout,
paid inference and human staffing remain separate gates.

The example prices are deliberately synthetic, not copied vendor quotes.
CAP-01 remains material: byte retention and Class A/B operation counts are separate
inputs, and file fanout must be measured before recurring funding. The peak connection check uses:

```text
API max instances × API processes per instance × (API pool_size + API max_overflow + 1 readiness connection)
+ worker max hosts × worker processes per host × (worker pool_size + worker max_overflow)
+ operator connection reserve
≤ 70% of declared database connection capacity
```

Both overflow allowances are explicit nonnegative bounded inputs; unlimited
overflow is rejected. The example declares one API process per instance and
overflow 10 for each API/worker pool, giving 138 possible connections against
a synthetic capacity of 200. Multiple API processes multiply independent pools and supervised readiness connections.
The readiness child has a fixed pool size of one and zero overflow; there is no
configuration knob that can exclude it from this bound. This corrects the
pre-readiness envelope without changing the version 1 input shape or fixture identities.
The current Database engine leaves [SQLAlchemy's default overflow](https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.QueuePool.__init__) at 10; this
contract changes no runtime pool behavior. AR-033-C must set and verify both
`pool_size` and `max_overflow` for every process and verify the declared process
counts before service activation. Additional coordinators or pools require a
revised envelope, not an uncounted connection source. The DB capacity is not
inferred from a machine size; 033B must verify the actual server limit.

This profile specifies alerts at 50/80/100 percent, an alert channel, a budget
owner and a stop owner. It uses **alerts-only** budgets, which do not cap spending;
resource limits, reviewed funded duration and operator action are still needed.
No automatic billing-disable action is proposed because it can destroy recovery
availability. Use a current, region-specific estimate before ENV0 approval.

AR-033-B consumes validated config version 1, its digest, privately verified ENV0,
reviewed IaC/provider pins and an exact proposed resource/IAM/network/cost inventory.
The consumer must preserve the peak connection settings through composition;
a plan or manifest that drops process counts or overflow allowances is incomplete.
Its output contract is an immutable installation manifest with:

- config digest, source/plan/provider identities and authorized change record;
- project/region, all resource IDs and labels, account identities and grant scopes;
- SQL private connection name and separately provisioned SQL users, bucket names,
  KMS key resource/version and secret resource references **without secret values**;
- private ingress/DNS/network bindings, operator access path, egress-denial policy,
  budget/alert IDs, stop deadline and teardown/retention inventory;
- live allowed/denied connectivity/IAM evidence and unresolved blockers.

The manifest and private evidence must be retained outside disposable checkouts.
AR-033-C consumes this foundation plus AR-013-C, AR-016-D and AR-011-C; no current
settings file is silently redirected to these draft fields. AR-033-D requires
a different operator to repeat install/teardown. This task supplies inputs and
offline checks only; it cannot close ENV0, those tasks, production acceptance,
or independent security review.

## Primary references and verification limits

Cloud behavior was checked against official documentation on 2026-10-20:
[Cloud Run private networking](https://docs.cloud.google.com/run/docs/securing/private-networking),
[Cloud SQL private services access](https://docs.cloud.google.com/sql/docs/postgres/configure-private-services-access),
[IAM database login](https://docs.cloud.google.com/sql/docs/postgres/iam-logins),
[Secret Manager resource access](https://docs.cloud.google.com/run/docs/configuring/services/secrets),
[KMS key-scoped roles](https://docs.cloud.google.com/kms/docs/reference/permissions-and-roles),
[Storage IAM permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-roles),
[Cloud SQL connector enforcement](https://docs.cloud.google.com/sql/docs/postgres/connect-connectors),
and [alerts-only budget limits](https://docs.cloud.google.com/billing/docs/how-to/budgets).
These references support the proposed mapping, not a deployed configuration.
Cloud compatibility, effective IAM, provider endpoint rules, region capacity,
current price quotes and operator evidence remain 033B/C checks.

Offline tests cover real acceptance/refusal decisions, malformed/missing fields,
public/metadata/overlapping routes, privilege mixing, mismatched regions/resources,
budget and connection arithmetic, digest drift, approval timing and safe CLI output.
Synthetic test records are fabricated to test consistency and establish no sign-off.

Local checks: 70 scoped tests, Ruff lint/format/security rules and strict mypy on the
validator passed using the existing owned environment. No dependencies were installed.
All local document links and 15/15 C03 allowed-flow mappings were checked. Final
locked-environment evidence requires hosted CI; live IAM/network, actual approvals
and provisioning remain unperformed. Independent reviewer disposition is pending.
