"""Bounded nonsecret operator intent and deterministic source identity."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .schema import COLUMNS, TABLES, MigrationRefused, canonical

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
InstallationKey = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
Principal = Annotated[str, Field(pattern=r"^(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})$")]
MAX_MAPPING_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_ROW_BYTES = 16 * 1024 * 1024
SOURCE_QUERIES = {
    "api_keys": "SELECT * FROM api_keys ORDER BY id",
    "audit": "SELECT * FROM audit ORDER BY id",
    "events": "SELECT * FROM events ORDER BY run_id,step",
    "jobs": "SELECT * FROM jobs ORDER BY id",
    "records": "SELECT * FROM records ORDER BY id",
}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Grant(StrictInput):
    principal_id: Principal
    role: Literal["viewer", "operator", "maintainer"]
    legacy_default: bool


class KeyDisposition(StrictInput):
    key_id: Identifier
    role: Literal["viewer", "operator", "disabled"]


class AdoptionMapping(StrictInput):
    schema_version: Literal[1]
    installation_key: InstallationKey
    source_dataset_digest: Digest
    organization_id: Identifier
    project_id: Identifier
    selector: Literal["all-verified-legacy-resources"]
    principal_grants: Annotated[list[Grant], Field(min_length=1, max_length=256)]
    key_dispositions: Annotated[list[KeyDisposition], Field(max_length=1024)]
    legacy_writer_roles: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")]],
        Field(max_length=64),
    ] = Field(default_factory=list)


def validate_mapping(value: Any) -> AdoptionMapping:
    try:
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
            raise ValueError("invalid version")
        mapping = AdoptionMapping.model_validate(value)
        grants = [g.principal_id for g in mapping.principal_grants]
        keys = [k.key_id for k in mapping.key_dispositions]
        if (
            len(set(grants)) != len(grants)
            or len(set(keys)) != len(keys)
            or len(set(mapping.legacy_writer_roles)) != len(mapping.legacy_writer_roles)
        ):
            raise ValueError("duplicate identity")
        if len(canonical(mapping.model_dump())) > MAX_MAPPING_BYTES:
            raise ValueError("oversize mapping")
        return mapping
    except (ValueError, TypeError, ValidationError):
        raise MigrationRefused("invalid_mapping") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate member")
        result[key] = value
    return result


def read_mapping(path: Path) -> AdoptionMapping:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > MAX_MAPPING_BYTES
            ):
                raise ValueError("unsafe file")
            raw = handle.read(MAX_MAPPING_BYTES + 1)
        if len(raw) > MAX_MAPPING_BYTES:
            raise ValueError("oversize mapping")
        return validate_mapping(json.loads(raw, object_pairs_hook=_unique_object))
    except (OSError, ValueError, RecursionError):
        raise MigrationRefused("invalid_mapping_file") from None


def source_digest(connection: Connection) -> str:
    """Hash all original values in stable row order, streaming with hard work bounds."""
    digest = hashlib.sha256()
    total = 0
    count = 0
    for table in TABLES:
        digest.update(canonical([table, [c[0] for c in COLUMNS[table]]]) + b"\n")
        rows = connection.execute(
            text(SOURCE_QUERIES[table]).execution_options(stream_results=True)
        )
        for row in rows:
            values = list(row)
            try:
                if table == "records" and isinstance(values[3], str):
                    values[3] = json.loads(values[3], object_pairs_hook=_unique_object)
                values = [int(v) if isinstance(v, bool) else v for v in values]
                encoded = canonical(values)
            except (ValueError, TypeError, RecursionError):
                raise MigrationRefused("invalid_source_data") from None
            total += len(encoded)
            count += 1
            if len(encoded) > MAX_ROW_BYTES or total > MAX_SOURCE_BYTES or count > 1000000:
                raise MigrationRefused("source_limit_exceeded")
            digest.update(encoded + b"\n")
    return digest.hexdigest()


def validate_legacy_rows(connection: Connection, mapping: AdoptionMapping) -> None:
    if connection.execute(
        text("SELECT 1 FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled') LIMIT 1")
    ).first():
        raise MigrationRefused("legacy_jobs_not_terminal")
    if connection.execute(
        text("SELECT 1 FROM records WHERE kind NOT IN ('run','study') LIMIT 1")
    ).first():
        raise MigrationRefused("unknown_resource_kind")
    if connection.execute(
        text("SELECT 1 FROM jobs WHERE reserved < 0 OR budget < reserved LIMIT 1")
    ).first():
        raise MigrationRefused("invalid_legacy_reservation")
    keys: set[str] = set(connection.execute(text("SELECT id FROM api_keys")).scalars())
    if any(k.key_id not in keys for k in mapping.key_dispositions):
        raise MigrationRefused("unknown_key_disposition")
    dispositions = {k.key_id: k.role for k in mapping.key_dispositions}
    for grant in mapping.principal_grants:
        if (
            grant.principal_id.startswith("api-key:")
            and dispositions.get(grant.principal_id[8:]) != grant.role
        ):
            raise MigrationRefused("invalid_key_grant")
    if source_digest(connection) != mapping.source_dataset_digest:
        raise MigrationRefused("source_digest_mismatch")
