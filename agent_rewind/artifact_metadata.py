"""Insert-only scoped object metadata; locators are never authorization tokens."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from sqlalchemy import (
    LargeBinary,
    Text,
    and_,
    case,
    cast,
    column,
    event,
    func,
    or_,
    select,
    table,
    text,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.sql.elements import ColumnElement

ROLES = frozenset(
    {
        "payload",
        "admission_config",
        "task",
        "event",
        "checkpoint",
        "workspace",
        "file_blob",
        "evaluation",
        "result",
        "study_attachment",
        "budget_evidence",
    }
)
OWNER_KINDS = frozenset({"run", "study", "job", "provider_call"})


class ArtifactError(ValueError):
    """Fixed artifact failure code only, never storage/database exception text."""


def identifier(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ArtifactError("artifact_identity_invalid")


def digest_value(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ArtifactError("artifact_digest_invalid")


def object_locator(project_id: str, digest: str) -> str:
    identifier(project_id)
    digest_value(digest)
    return f"objects/{project_id}/v1/{digest}"


class ArtifactDescriptor(Protocol):
    """Readonly metadata shape shared with independently scoped repositories."""

    @property
    def id(self) -> str: ...
    @property
    def project_id(self) -> str: ...
    @property
    def digest(self) -> str: ...
    @property
    def locator(self) -> str: ...
    @property
    def format_version(self) -> int: ...
    @property
    def byte_count(self) -> int: ...
    @property
    def created_at(self) -> datetime: ...


@dataclass(frozen=True)
class ArtifactObject:
    id: str
    project_id: str
    digest: str
    locator: str
    format_version: Literal[1]
    byte_count: int
    created_at: datetime

    def __post_init__(self) -> None:
        identifier(self.id)
        identifier(self.project_id)
        digest_value(self.digest)
        if type(self.format_version) is not int or self.format_version != 1:
            raise ArtifactError("artifact_format_unsupported")
        if type(self.byte_count) is not int or not 0 <= self.byte_count <= 2**63 - 1:
            raise ArtifactError("artifact_size_invalid")
        if self.locator not in {
            object_locator(self.project_id, self.digest),
            f"objects/{self.digest}",
        }:
            raise ArtifactError("artifact_locator_invalid")
        if not isinstance(self.created_at, datetime) or self.created_at.utcoffset() is None:
            raise ArtifactError("artifact_timestamp_invalid")


def _object(row: object) -> ArtifactObject:
    if not isinstance(row, Mapping):
        raise ArtifactError("artifact_metadata_invalid")
    try:
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return ArtifactObject(
            id=row["id"],
            project_id=row["project_id"],
            digest=row["digest"],
            locator=row["locator"],
            format_version=row["format_version"],
            byte_count=row["byte_count"],
            created_at=created,
        )
    except (KeyError, TypeError, ValueError):
        raise ArtifactError("artifact_metadata_invalid") from None


def _owner(project_id: str, owner_kind: str, owner_id: str, role: str) -> None:
    identifier(project_id)
    identifier(owner_id)
    if owner_kind not in OWNER_KINDS or role not in ROLES:
        raise ArtifactError("artifact_reference_invalid")
    if role == "budget_evidence" and owner_kind != "provider_call":
        raise ArtifactError("artifact_reference_invalid")


def resolve_ref(
    connection: Connection,
    *,
    project_id: str,
    owner_kind: str,
    owner_id: str,
    role: str,
    digest: str,
) -> ArtifactObject | None:
    """SQL only, after caller's fresh principal/action/ancestry authorization."""
    _owner(project_id, owner_kind, owner_id, role)
    digest_value(digest)
    rows = (
        connection.execute(
            text("""
        SELECT o.id,o.project_id,o.digest,o.locator,o.format_version,o.byte_count,o.created_at
        FROM artifact_refs r
        JOIN artifact_objects o ON o.project_id=r.project_id AND o.id=r.artifact_id
        JOIN resource_scopes s ON s.project_id=r.project_id
          AND s.resource_kind=r.owner_kind AND s.resource_id=r.owner_id
        WHERE r.project_id=:project AND r.owner_kind=:kind AND r.owner_id=:owner
          AND r.role=:role AND o.digest=:digest AND o.format_version=1
        LIMIT 2
    """),
            {
                "project": project_id,
                "kind": owner_kind,
                "owner": owner_id,
                "role": role,
                "digest": digest,
            },
        )
        .mappings()
        .all()
    )
    if len(rows) > 1:
        raise ArtifactError("artifact_metadata_conflict")
    return _object(rows[0]) if rows else None


def _sqlite_connect(dbapi: Any, record: ConnectionPoolEntry) -> None:
    cursor = dbapi.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA foreign_keys")
        if cursor.fetchone() != (1,):
            raise ArtifactError("artifact_constraints_required")
    finally:
        cursor.close()


def configure_artifact_engine(engine: Engine) -> None:
    """Configure before first use; existing pooled connections still must pass checks."""
    if engine.dialect.name == "sqlite" and not event.contains(engine, "connect", _sqlite_connect):
        event.listen(engine, "connect", _sqlite_connect)


def _write_constraints(connection: Connection) -> None:
    if connection.dialect.name not in {"sqlite", "postgresql"}:
        raise ArtifactError("artifact_database_unsupported")
    if (
        connection.dialect.name == "sqlite"
        and connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1
    ):
        raise ArtifactError("artifact_constraints_required")


_OBJECT_BOUNDS = {
    "id": 32,
    "project_id": 32,
    "digest": 64,
    "locator": 160,
    "format_version": 8,
    "byte_count": 24,
    "created_at": 64,
}
_objects = table("artifact_objects", *(column(name) for name in _OBJECT_BOUNDS))


def _verified_columns(connection: Connection) -> tuple[ColumnElement[Any], ...]:
    # Keep malformed candidates in the OR query, but never transfer oversized
    # cells. Byte lengths catch SQLite BLOBs, multibyte text and NUL suffixes.
    sizes = (
        func.octet_length(cast(field, Text))
        if connection.dialect.name == "postgresql"
        else func.length(cast(field, LargeBinary))
        for field in _objects.c
    )
    bounded = and_(*(size <= cap for size, cap in zip(sizes, _OBJECT_BOUNDS.values(), strict=True)))
    return tuple(case((bounded, field), else_=None).label(field.name) for field in _objects.c)


def record_verified(connection: Connection, value: ArtifactObject) -> ArtifactObject:
    """Preparatory primitive; caller must hold a verified storage receipt.

    Does not upload, authorize a principal, commit or publish a root graph.
    AR-009-B owns the coordinator. There is no update/delete operation.
    """
    _write_constraints(connection)
    value.__post_init__()
    at = value.created_at.astimezone(UTC).isoformat()
    statement = """
        INSERT INTO artifact_objects
          (id,project_id,digest,locator,format_version,byte_count,created_at)
        VALUES (:id,:project,:digest,:locator,:version,:size,:at)
        ON CONFLICT DO NOTHING
    """
    if connection.dialect.name == "postgresql":
        statement = statement.replace(":at", "CAST(:at AS TIMESTAMP WITH TIME ZONE)")
    connection.execute(
        text(statement),
        {
            "id": value.id,
            "project": value.project_id,
            "digest": value.digest,
            "locator": value.locator,
            "version": value.format_version,
            "size": value.byte_count,
            "at": at,
        },
    )
    rows = (
        connection.execute(
            select(*_verified_columns(connection))
            .where(
                or_(
                    _objects.c.id == value.id,
                    and_(
                        _objects.c.project_id == value.project_id,
                        _objects.c.digest == value.digest,
                        _objects.c.format_version == value.format_version,
                    ),
                )
            )
            .limit(2)
        )
        .mappings()
        .all()
    )
    if len(rows) != 1 or _object(rows[0]) != value:
        raise ArtifactError("artifact_metadata_conflict")
    return _object(rows[0])


def register_ref(
    connection: Connection,
    *,
    project_id: str,
    owner_kind: str,
    owner_id: str,
    role: str,
    artifact_id: str,
) -> bool:
    """Insert one exact association; duplicate is idempotent, never a new grant."""
    _owner(project_id, owner_kind, owner_id, role)
    identifier(artifact_id)
    _write_constraints(connection)
    result = connection.execute(
        text("""
        INSERT INTO artifact_refs(project_id,owner_kind,owner_id,artifact_id,role)
        VALUES (:project,:kind,:owner,:artifact,:role)
        ON CONFLICT DO NOTHING
    """),
        {
            "project": project_id,
            "kind": owner_kind,
            "owner": owner_id,
            "artifact": artifact_id,
            "role": role,
        },
    )
    return result.rowcount == 1
