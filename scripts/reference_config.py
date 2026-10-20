"""Offline C14 staging configuration checks; never provisions or grants authority."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent_rewind.corpus import ManifestTimestamp

MAX_CONFIG_BYTES = 64 * 1024
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{2,39}$")]
Region = Annotated[str, Field(pattern=r"^[a-z]+-[a-z]+[1-9][0-9]?$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Money = Annotated[int, Field(ge=0, le=10**15)]
CostLine = Literal[
    "api-compute",
    "worker-compute-disks",
    "sql-compute",
    "sql-storage-backups",
    "artifact-bytes",
    "artifact-operations",
    "network",
    "keys-secrets",
    "observability",
    "state-support-contingency",
]
Capability = Literal[
    "database-dml",
    "database-ddl",
    "artifact-create-read",
    "artifact-crypt",
    "api-secrets-read",
    "provider-secret-read",
    "local-docker",
    "foundation-manage",
    "scoped-iam-manage",
    "state-read-write",
]
ROLE_CAPABILITIES = {
    "api": {"database-dml", "artifact-create-read", "artifact-crypt", "api-secrets-read"},
    "worker": {
        "database-dml",
        "artifact-create-read",
        "artifact-crypt",
        "provider-secret-read",
        "local-docker",
    },
    "migrator": {"database-ddl"},
    "provisioner": {"foundation-manage", "scoped-iam-manage", "state-read-write"},
}
COST_LINES = {
    "api-compute",
    "worker-compute-disks",
    "sql-compute",
    "sql-storage-backups",
    "artifact-bytes",
    "artifact-operations",
    "network",
    "keys-secrets",
    "observability",
    "state-support-contingency",
}
PRIVATE_RANGES = tuple(
    ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def exact_literal_types(cls, value: object) -> object:
        # Pydantic Literal considers False == 0 and True == 1; the JSON schema does not.
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                if name in value and get_origin(field.annotation) is Literal:
                    options = get_args(field.annotation)
                    if not any(type(value[name]) is type(option) for option in options):
                        raise ValueError("Literal fields require their declared JSON type.")
        return value


class Labels(Strict):
    application: Literal["agent-rewind"]
    installation: Identifier
    environment: Literal["staging"]
    owner: Identifier
    cost_center: Identifier


class Identity(Strict):
    account_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")]
    capabilities: list[Capability] = Field(min_length=1, max_length=8)


class Identities(Strict):
    api: Identity
    worker: Identity
    migrator: Identity
    provisioner: Identity

    @model_validator(mode="after")
    def least_privilege(self) -> Self:
        accounts = []
        for role, allowed in ROLE_CAPABILITIES.items():
            identity = getattr(self, role)
            accounts.append(identity.account_id)
            if set(identity.capabilities) != allowed or len(identity.capabilities) != len(allowed):
                raise ValueError("Capability set must match its separate C03 role.")
        if len(set(accounts)) != len(accounts):
            raise ValueError("Workload and maintenance identities must be distinct.")
        return self


class Network(Strict):
    network_name: Identifier
    api_subnet: str
    worker_subnet: str
    proxy_subnet: str
    sql_service_range: str
    operator_cidrs: list[str] = Field(min_length=1, max_length=8)
    ingress: Literal["internal-https"]
    private_google_access: Literal[True]
    external_egress: Literal["blocked"]
    worker_public_ip: Literal[False]
    sandbox_network: Literal["none"]
    sandbox_metadata_access: Literal[False]

    @model_validator(mode="after")
    def private_nonoverlapping_ranges(self) -> Self:
        ranges: list[ipaddress.IPv4Network] = []
        for value in (
            self.api_subnet,
            self.worker_subnet,
            self.proxy_subnet,
            self.sql_service_range,
            *self.operator_cidrs,
        ):
            network = ipaddress.IPv4Network(value, strict=True)
            if not any(network.subnet_of(r) for r in PRIVATE_RANGES):
                raise ValueError("Only explicit canonical RFC1918 IPv4 ranges are supported.")
            if any(network.overlaps(existing) for existing in ranges):
                raise ValueError("Service and operator ranges must not overlap.")
            ranges.append(network)
        if ipaddress.IPv4Network(self.sql_service_range).prefixlen > 24:
            raise ValueError("Reserve at least a /24 for this one-region SQL profile.")
        return self


class Database(Strict):
    instance_name: Identifier
    engine: Literal["POSTGRES_16"]
    availability: Literal["REGIONAL"]
    public_ip: Literal[False]
    iam_authentication: Literal[True]
    connector_enforcement: Literal["REQUIRED"]
    tls: Literal["required"]
    backup_enabled: Literal[True]
    pitr_enabled: Literal[True]
    backup_retained_count: Annotated[int, Field(ge=7, le=365)]
    pitr_days: Annotated[int, Field(ge=1, le=7)]
    deletion_protection: Literal[True]
    vcpus: Annotated[int, Field(ge=2, le=64)]
    memory_mib: Annotated[int, Field(ge=4096, le=524288)]
    disk_gib: Annotated[int, Field(ge=20, le=65536)]
    connection_capacity: Annotated[int, Field(ge=10, le=10000)]


class Storage(Strict):
    artifact_bucket: Identifier
    state_bucket: Identifier
    location: Region
    public_access_prevention: Literal["enforced"]
    uniform_bucket_access: Literal[True]
    state_versioning: Literal[True]
    automatic_artifact_deletion: Literal[False]
    retained_gib_envelope: Annotated[int, Field(ge=1, le=10**7)]


class KeysAndSecrets(Strict):
    key_ring: Identifier
    artifact_key: Identifier
    location: Region
    api_session_secret: Identifier
    oidc_client_secret: Identifier
    provider_secret: Identifier
    service_account_keys: Literal["forbidden"]
    secret_values: Literal["external-not-in-config"]


class Capacity(Strict):
    api_max_instances: Annotated[int, Field(ge=1, le=16)]
    api_vcpus: Annotated[int, Field(ge=1, le=8)]
    api_memory_mib: Annotated[int, Field(ge=512, le=32768)]
    api_processes_per_instance: Annotated[int, Field(ge=1, le=8)]
    api_pool_size: Annotated[int, Field(ge=1, le=100)]
    api_max_overflow: Annotated[int, Field(ge=0, le=100)]
    worker_max_hosts: Annotated[int, Field(ge=1, le=64)]
    worker_machine_type: Annotated[str, Field(pattern=r"^e2-standard-(?:4|8|16|32)$")]
    worker_boot_disk_gib: Annotated[int, Field(ge=20, le=1024)]
    worker_processes_per_host: Annotated[int, Field(ge=1, le=8)]
    worker_pool_size: Annotated[int, Field(ge=1, le=100)]
    worker_max_overflow: Annotated[int, Field(ge=0, le=100)]
    operator_connection_reserve: Annotated[int, Field(ge=1, le=100)]
    monthly_class_a_operations: Annotated[int, Field(ge=1, le=10**12)]
    monthly_class_b_operations: Annotated[int, Field(ge=1, le=10**12)]


class Estimate(Strict):
    line: CostLine
    monthly_microusd: Money
    basis: Literal["quote", "allowance", "synthetic"]
    evidence_id: Identifier
    owner_id: Identifier


class Budget(Strict):
    currency: Literal["USD"]
    monthly_limit_microusd: Annotated[int, Field(gt=0, le=10**15)]
    bootstrap_limit_microusd: Annotated[int, Field(gt=0, le=10**15)]
    bootstrap_estimate_microusd: Money
    owner_id: Identifier
    alert_channel_id: Identifier
    stop_owner_id: Identifier
    alert_percentages: list[int]
    lines: list[Estimate] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def bounded_estimate(self) -> Self:
        if {line.line for line in self.lines} != COST_LINES:
            raise ValueError("Every cost line must appear exactly once.")
        if self.alert_percentages != [50, 80, 100]:
            raise ValueError("The reference alerts profile is 50/80/100 percent.")
        if sum(line.monthly_microusd for line in self.lines) > self.monthly_limit_microusd:
            raise ValueError("Monthly estimate exceeds its declared approval ceiling.")
        if self.bootstrap_estimate_microusd > self.bootstrap_limit_microusd:
            raise ValueError("Bootstrap estimate exceeds its declared approval ceiling.")
        return self


class ApprovalRecord(Strict):
    gate: Literal["ENV0"]
    evidence_id: Identifier
    approved_by: Identifier
    approved_at: ManifestTimestamp
    expires_at: ManifestTimestamp
    config_sha256: Digest


class ReferenceConfig(Strict):
    schema_version: Literal[1]
    contract_id: Literal["C14"]
    purpose: Literal["staging-foundation"]
    synthetic: bool
    installation_id: Identifier
    project_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")]
    region: Region
    organization_count: Literal[1]
    operator_id: Identifier
    staging_stop_at: ManifestTimestamp
    logging_retention_days: Annotated[int, Field(ge=1, le=365)]
    labels: Labels
    identities: Identities
    network: Network
    database: Database
    storage: Storage
    keys: KeysAndSecrets
    capacity: Capacity
    budget: Budget
    approval_record: ApprovalRecord | None

    @model_validator(mode="after")
    def coherent_installation(self) -> Self:
        if (
            self.labels.installation != self.installation_id
            or self.labels.owner != self.operator_id
        ):
            raise ValueError("Resource labels must identify this installation and operator.")
        if self.storage.location != self.region or self.keys.location != self.region:
            raise ValueError("SQL, bucket and key locations must use the declared region.")
        if self.storage.artifact_bucket == self.storage.state_bucket:
            raise ValueError("Provisioning state must not share the artifact bucket.")
        secrets = (
            self.keys.api_session_secret,
            self.keys.oidc_client_secret,
            self.keys.provider_secret,
        )
        if len(set(secrets)) != 3:
            raise ValueError("API and provider secret resources must be distinct.")
        c = self.capacity
        connections = (
            c.api_max_instances
            * c.api_processes_per_instance
            * (c.api_pool_size + c.api_max_overflow)
            + c.worker_max_hosts
            * c.worker_processes_per_host
            * (c.worker_pool_size + c.worker_max_overflow)
            + c.operator_connection_reserve
        )
        if connections * 10 > self.database.connection_capacity * 7:
            raise ValueError("Connection envelope exceeds 70 percent of declared DB capacity.")
        if not self.synthetic and any(line.basis == "synthetic" for line in self.budget.lines):
            raise ValueError("A non-synthetic request requires actual quote/allowance references.")
        return self


def config_digest(config: ReferenceConfig) -> str:
    body = config.model_dump(mode="json", exclude={"approval_record"})
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def check_deployment_review(config: ReferenceConfig, now: datetime) -> None:
    """Check declared record consistency only; AR-033-B must verify its authority."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Review clock must be timezone-aware.")
    record = config.approval_record
    if config.synthetic or record is None:
        raise ValueError("Synthetic or unapproved configuration cannot enter deployment review.")
    if not record.approved_at <= now < record.expires_at <= config.staging_stop_at:
        raise ValueError("Approval record is future, expired or has no positive review window.")
    if record.config_sha256 != config_digest(config):
        raise ValueError("Approval record does not bind this exact configuration.")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration field.")
        result[key] = value
    return result


def load_config(path: Path) -> ReferenceConfig:
    # Nonblocking open prevents a FIFO from hanging before its file type can be checked.
    # Check the opened descriptor, not a pathname stat that could race a replacement.
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Configuration must be a regular file.")
        if metadata.st_size > MAX_CONFIG_BYTES:
            raise ValueError("Configuration exceeds the 64 KiB limit.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            body = stream.read(MAX_CONFIG_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(body) > MAX_CONFIG_BYTES:
        raise ValueError("Configuration exceeds the 64 KiB limit.")
    value = json.loads(body, object_pairs_hook=_unique_object)
    return ReferenceConfig.model_validate(value)


def safe_validation_errors(error: ValidationError) -> list[dict[str, object]]:
    schema = ReferenceConfig.model_json_schema()
    known_fields = set(schema["properties"])
    for definition in schema["$defs"].values():
        known_fields.update(definition.get("properties", {}))
    issues: list[dict[str, object]] = []
    for issue in error.errors(include_input=False, include_context=False, include_url=False)[:16]:
        path = [
            part if isinstance(part, int) or part in known_fields else "<unknown-field>"
            for part in issue["loc"]
        ]
        issues.append({"path": path, "code": issue["type"]})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--deployment-review", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.deployment_review:
            check_deployment_review(config, datetime.now(UTC))
    except ValidationError as error:
        print(
            json.dumps(
                {
                    "valid": False,
                    "deployable": False,
                    "error": "invalid-reference-config",
                    "issues": safe_validation_errors(error),
                }
            )
        )
        return 2
    except (OSError, ValueError, RecursionError):
        # Configuration values may contain accidentally pasted credentials; never echo them.
        print(
            json.dumps({"valid": False, "deployable": False, "error": "invalid-reference-config"})
        )
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "deployable": False,
                "config_sha256": config_digest(config),
                "record_consistency_checked": args.deployment_review,
                "required_next_step": "AR-033-B: verify ENV0 authority and inspect the IaC plan",
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
