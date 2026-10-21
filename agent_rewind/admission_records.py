"""Bounded admission SQL values; no connection ownership or committed authority.

These readers require their caller's fresh scoped authorization. Configuration
metadata proves a persisted association, never a storage receipt. SQL datatypes
alone do not establish finite UTC timestamps or retention policy.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Text, and_, case, cast, column, func, or_, select, table
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import TableClause

from .admission_envelope import ArtifactBinding
from .artifact_metadata import ArtifactError, ArtifactObject, _object, object_locator
from .models import canonical
from .published_reader import _bounded_columns, _objects, _refs
from .request_identity import IdentityInvalid
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import ProjectContext, _byte_length, scopes

StorageCode = Literal[
    "admission_input_invalid",
    "admission_metadata_invalid",
    "admission_conflict",
    "admission_transaction_required",
    "admission_storage_unavailable",
]


class AdmissionStorageError(RuntimeError):
    """Fixed code only; never driver text, submitted configuration or credentials."""

    def __init__(self, code: StorageCode):
        self.code = code
        super().__init__(code)


OPERATION_LIMITS = {
    "id": 32,
    "project_id": 32,
    "principal_id": 256,
    "kind": 20,
    "client_operation_id": 32,
    "request_digest": 64,
    "job_id": 32,
    "accepted_response": 128,
    "created_at": 64,
    "retain_until": 64,
    "job_resource_kind": 20,
    "execution_config_digest": 64,
    "payload_version": 8,
    "failure_correlation_id": 32,
}
ALIAS_LIMITS = {
    "project_id": 32,
    "principal_id": 256,
    "kind": 20,
    "key_hash": 64,
    "operation_id": 32,
    "request_digest": 64,
}
JOB_LIMITS = {
    "id": 32,
    "kind": 20,
    "payload": 64,
    "budget": 24,
    "actor": 256,
    "payload_version": 8,
    "execution_config_ref": 64,
    "execution_config_digest": 64,
}
OPERATIONS = table("operations", *(column(name) for name in OPERATION_LIMITS))
ALIASES = table("operation_keys", *(column(name) for name in ALIAS_LIMITS))
JOBS = table("jobs", *(column(name) for name in JOB_LIMITS))


@contextmanager
def storage_errors() -> Iterator[None]:
    try:
        yield
    except IdentityInvalid:
        raise
    except IntegrityError:
        raise AdmissionStorageError("admission_conflict") from None
    except (SQLAlchemyError, sqlite3.Error):
        raise AdmissionStorageError("admission_storage_unavailable") from None
    except (ArtifactError, ValueError, TypeError, OverflowError, KeyError):
        raise AdmissionStorageError("admission_metadata_invalid") from None


def hexadecimal(value: Any, length: int, *, input_value: bool = False) -> str:
    if type(value) is not str or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        raise AdmissionStorageError(
            "admission_input_invalid" if input_value else "admission_metadata_invalid"
        )
    return value


def principal_value(value: Any) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})", value) is None
    ):
        raise AdmissionStorageError("admission_metadata_invalid")
    return value


def timestamp(value: Any, *, input_value: bool = False) -> datetime:
    try:
        if not input_value and type(value) is str:
            value = datetime.fromisoformat(value)
        if type(value) is not datetime or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        raise AdmissionStorageError(
            "admission_input_invalid" if input_value else "admission_metadata_invalid"
        ) from None


def retention(created: Any, until: Any, *, input_value: bool = False) -> tuple[datetime, datetime]:
    created_at = timestamp(created, input_value=input_value)
    retain_until = timestamp(until, input_value=input_value)
    try:
        if retain_until < created_at + timedelta(days=90):
            raise ValueError
    except (ValueError, OverflowError):
        raise AdmissionStorageError(
            "admission_input_invalid" if input_value else "admission_metadata_invalid"
        ) from None
    # No comparison with now: passing the initial floor never makes replay expire.
    return created_at, retain_until


def bounded_columns(
    connection: Connection, source: TableClause, limits: Mapping[str, int]
) -> tuple[ColumnElement[Any], ...]:
    safe = and_(
        *(
            or_(source.c[name].is_(None), _byte_length(connection, source.c[name]) <= limit)
            for name, limit in limits.items()
        )
    )
    dates = {"created_at", "retain_until"} & limits.keys()
    if connection.dialect.name == "sqlite":
        safe = and_(safe, *(func.typeof(source.c[name]) == "text" for name in dates))
    # Text conversion avoids psycopg materializing +/-infinity as a datetime
    # before our finite parser. CASE keeps malformed candidates instead of
    # filtering them into a false absent/unique identity.
    return tuple(
        case(
            (safe, cast(source.c[name], Text) if name in dates else source.c[name]), else_=None
        ).label(name)
        for name in limits
    )


def write_transaction(connection: Connection) -> None:
    raw = connection.connection.driver_connection
    name = connection.dialect.name
    if not connection.in_transaction() or not (
        (name == "postgresql" and getattr(raw, "autocommit", None) is False)
        or (
            name == "sqlite"
            and getattr(raw, "isolation_level", None) is not None
            and getattr(raw, "autocommit", -1) == -1
            and getattr(raw, "in_transaction", False) is True
        )
    ):
        raise AdmissionStorageError("admission_transaction_required")
    if name == "sqlite" and connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
        raise AdmissionStorageError("admission_transaction_required")


@dataclass(frozen=True)
class StoredOperation:
    id: str
    project_id: str
    principal_id: str
    client_operation_id: str
    request_digest: str
    job_id: str
    created_at: datetime
    retain_until: datetime
    execution_config_digest: str
    failure_correlation_id: str | None

    @property
    def accepted_response(self) -> dict[str, str]:
        return {"job_id": self.job_id, "operation_id": self.id}


def operation_value(row: Mapping[str, Any]) -> StoredOperation:
    for name in ("id", "project_id", "client_operation_id", "job_id"):
        hexadecimal(row[name], 32)
    principal_value(row["principal_id"])
    for name in ("request_digest", "execution_config_digest"):
        hexadecimal(row[name], 64)
    if row["failure_correlation_id"] is not None:
        hexadecimal(row["failure_correlation_id"], 32)
    if (
        row["kind"] != "run"
        or row["job_resource_kind"] != "job"
        or type(row["payload_version"]) is not int
        or row["payload_version"] != 2
        or row["accepted_response"]
        != canonical({"job_id": row["job_id"], "operation_id": row["id"]}).decode()
    ):
        raise AdmissionStorageError("admission_metadata_invalid")
    created, until = retention(row["created_at"], row["retain_until"])
    return StoredOperation(
        row["id"],
        row["project_id"],
        row["principal_id"],
        row["client_operation_id"],
        row["request_digest"],
        row["job_id"],
        created,
        until,
        row["execution_config_digest"],
        row["failure_correlation_id"],
    )


@dataclass(frozen=True)
class JobConfiguration:
    job_id: str
    project_id: str
    kind: str
    payload_version: int
    reference: str
    digest: str
    descriptor: ArtifactObject
    payload: str
    budget_microusd: int
    actor: str | None


def scoped_descriptor(
    connection: Connection,
    *,
    project_id: str,
    job_id: str,
    role: str,
    expected: ArtifactObject | None = None,
) -> ArtifactObject:
    # Enumerate the exact owner/role BEFORE digest/format checks. An unmatched
    # or malformed second candidate must refuse, not disappear behind a filter.
    rows = (
        connection.execute(
            select(
                *_bounded_columns(connection),
                case(
                    (_byte_length(connection, _refs.c.artifact_id) == 32, _refs.c.artifact_id),
                    else_=None,
                ).label("reference_id"),
            )
            .select_from(
                _refs.outerjoin(
                    _objects,
                    and_(
                        _objects.c.project_id == _refs.c.project_id,
                        _objects.c.id == _refs.c.artifact_id,
                    ),
                )
            )
            .where(
                _refs.c.project_id == project_id,
                _refs.c.owner_kind == "job",
                _refs.c.owner_id == job_id,
                _refs.c.role == role,
            )
            .limit(2)
        )
        .mappings()
        .all()
    )
    if len(rows) != 1:
        raise AdmissionStorageError("admission_metadata_invalid")
    value = _object(rows[0])
    if (
        rows[0]["reference_id"] != value.id
        or value.project_id != project_id
        or value.locator != object_locator(project_id, value.digest)
        or (expected is not None and value != expected)
    ):
        raise AdmissionStorageError("admission_metadata_invalid")
    return value


def verify_job_configuration(
    connection: Connection,
    *,
    context: ProjectContext,
    job_id: str,
    payload_version: int,
    expected_descriptor: ArtifactObject | None = None,
) -> JobConfiguration:
    """After authorization, verify common config even without an operations row.

    NULL historical config is never usable here. This method does not read
    plaintext, verify a storage receipt, acquire authority locks or commit.
    """
    hexadecimal(job_id, 32, input_value=True)
    if type(payload_version) is not int or payload_version not in (1, 2):
        raise AdmissionStorageError("admission_input_invalid")
    with storage_errors():
        rows = (
            connection.execute(
                select(*bounded_columns(connection, JOBS, JOB_LIMITS))
                .select_from(
                    JOBS.join(
                        scopes,
                        and_(
                            scopes.c.project_id == context.project_id,
                            scopes.c.resource_kind == "job",
                            scopes.c.resource_id == JOBS.c.id,
                        ),
                    )
                )
                .where(JOBS.c.id == job_id)
                .limit(2)
            )
            .mappings()
            .all()
        )
        if not rows:
            raise ResourceNotFound()
        if len(rows) != 1:
            raise AdmissionStorageError("admission_metadata_invalid")
        row = rows[0]
        reference = hexadecimal(row["execution_config_ref"], 64)
        config_digest = hexadecimal(row["execution_config_digest"], 64)
        if (
            row["id"] != job_id
            or row["kind"] not in {"run", "branch", "study", "investigate"}
            or type(row["payload_version"]) is not int
            or row["payload_version"] != payload_version
            or reference != config_digest
            or type(row["budget"]) is not int
            or not 1 <= row["budget"] <= 200_000_000
        ):
            raise AdmissionStorageError("admission_metadata_invalid")
        payload = hexadecimal(row["payload"], 64)
        actor = principal_value(row["actor"]) if row["actor"] is not None else None
        descriptor = scoped_descriptor(
            connection,
            project_id=context.project_id,
            job_id=job_id,
            role="admission_config",
            expected=expected_descriptor,
        )
        if descriptor.digest != config_digest or descriptor.byte_count > 65536:
            raise AdmissionStorageError("admission_metadata_invalid")
        return JobConfiguration(
            job_id,
            context.project_id,
            row["kind"],
            payload_version,
            reference,
            config_digest,
            descriptor,
            payload,
            row["budget"],
            actor,
        )


def verify_binding(
    connection: Connection, context: ProjectContext, binding: ArtifactBinding
) -> None:
    if type(binding) is not ArtifactBinding or binding.project_id != context.project_id:
        raise AdmissionStorageError("admission_input_invalid")
    scoped_descriptor(
        connection,
        project_id=context.project_id,
        job_id=binding.job_id,
        role=binding.role,
        expected=binding.descriptor,
    )
