"""Bounded original SQL receipts for operation adapters, without authority.

Callers authorize the original project before these reads and reauthorize after
I/O. These primitives neither own connections nor make a disclosure decision.
Receipts retain raw SQL NULL/type identity for the later single-statement final
comparison; they are not reconstructed from a second read or storage bytes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Text, and_, case, cast, column, func, literal, select, table
from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import TableClause

from .admission_records import (
    OPERATION_LIMITS,
    OPERATIONS,
    AdmissionStorageError,
    StoredOperation,
    bounded_columns,
    hexadecimal,
    operation_value,
    principal_value,
)
from .admission_request import AdmissionPreparationError, bounded_canonical
from .artifact_metadata import ArtifactObject, _object, object_locator
from .published_reader import _bounded_columns, _objects, _refs
from .scoped_lineage import ResourceNotFound
from .scoped_repositories import ProjectContext, _byte_length, scopes

MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_IDENTITIES = 259
MAX_JOB_BYTES = 4096
JOB_LIMITS = {
    "id": 32,
    "kind": 20,
    "created": 64,
    "payload": 64,
    "status": 20,
    "owner": 64,
    "lease_until": 64,
    "cancel": 8,
    "budget": 24,
    "reserved": 24,
    "result": 64,
    "error": 1200,
    "actor": 256,
    "payload_version": 8,
    "execution_config_ref": 64,
    "execution_config_digest": 64,
}
JOBS = table("jobs", *(column(name) for name in JOB_LIMITS))
DESCRIPTOR_FIELDS = (
    "id",
    "project_id",
    "digest",
    "locator",
    "format_version",
    "byte_count",
    "created_at",
)
Domain = Literal["operation", "job", "admission_config", "result"]
Scalar = str | int | float | bool | None


def invalid() -> AdmissionStorageError:
    return AdmissionStorageError("admission_metadata_invalid")


@dataclass(frozen=True)
class RawReceipt:
    domain: Domain
    identity: str
    fields: tuple[str, ...]
    values: tuple[Scalar, ...]

    def row(self) -> dict[str, Scalar]:
        return dict(zip(self.fields, self.values, strict=True))


class ReceiptBook:
    """Request-wide retained identities and encoded bytes; no authorization."""

    def __init__(self) -> None:
        self._receipts: dict[tuple[Domain, str], RawReceipt] = {}
        self.byte_count = 2  # canonical array brackets

    @property
    def remaining(self) -> int:
        return MAX_RECEIPT_BYTES - self.byte_count

    @property
    def receipts(self) -> tuple[RawReceipt, ...]:
        return tuple(self._receipts.values())

    def remember(
        self, domain: Domain, identity: str, fields: tuple[str, ...], row: Mapping[str, Any]
    ) -> RawReceipt:
        hexadecimal(identity, 32)
        values = tuple(row[name] for name in fields)
        if any(
            type(value) not in (str, int, float, bool, type(None))
            or (type(value) is float and not math.isfinite(value))
            for value in values
        ):
            raise invalid()
        receipt = RawReceipt(domain, identity, fields, values)
        key = domain, identity
        previous = self._receipts.get(key)
        # bool/int and int/float equality must not conceal a raw SQL type change.
        if previous is not None:
            if previous != receipt or tuple(map(type, previous.values)) != tuple(map(type, values)):
                raise invalid()
            return previous
        try:
            encoded = bounded_canonical(
                [domain, identity, list(fields), list(values)],
                limit=self.remaining - bool(self._receipts),
                limit_code="admission_body_limit",
            )
        except (AdmissionPreparationError, ValueError, TypeError, UnicodeError):
            raise invalid() from None
        size = len(encoded) + bool(self._receipts)
        if len(self._receipts) >= MAX_IDENTITIES or size > self.remaining:
            raise invalid()
        self._receipts[key] = receipt
        self.byte_count += size
        return receipt


def _columns(
    connection: Connection, source: TableClause, limits: Mapping[str, int], remaining: int
) -> tuple[ColumnElement[Any], ...]:
    # Whole-row and cell limits live in the SELECT, retaining malformed rows as
    # NULL candidates. No oversized value crosses into the Python parser.
    size = sum(
        (func.coalesce(_byte_length(connection, source.c[name]), 0) for name in limits), literal(0)
    )
    return tuple(
        case((size <= remaining, value), else_=None).label(name)
        for name, value in zip(limits, bounded_columns(connection, source, limits), strict=True)
    )


def read_operation(
    connection: Connection, context: ProjectContext, operation_id: str, book: ReceiptBook
) -> tuple[StoredOperation, RawReceipt]:
    """No creator filter: named-project viewer status differs from replay."""
    rows = (
        connection.execute(
            select(*_columns(connection, OPERATIONS, OPERATION_LIMITS, book.remaining))
            .where(OPERATIONS.c.project_id == context.project_id, OPERATIONS.c.id == operation_id)
            .limit(2)
        )
        .mappings()
        .all()
    )
    if not rows:
        raise ResourceNotFound()
    if len(rows) != 1:
        raise invalid()
    value = operation_value(dict(rows[0]))
    if value.id != operation_id or value.project_id != context.project_id:
        raise invalid()
    receipt = book.remember("operation", value.id, tuple(OPERATION_LIMITS), dict(rows[0]))
    return value, receipt


def read_job(
    connection: Connection, context: ProjectContext, job_id: str, book: ReceiptBook
) -> RawReceipt:
    rows = (
        connection.execute(
            select(*_columns(connection, JOBS, JOB_LIMITS, min(MAX_JOB_BYTES, book.remaining)))
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
        raise invalid()
    row = dict(rows[0])
    if (
        row["id"] != job_id
        or row["kind"] != "run"
        or row["status"] not in {"queued", "running", "succeeded", "failed", "cancelled"}
        or type(row["budget"]) is not int
        or row["budget"] < 1
        or type(row["reserved"]) is not int
        or row["reserved"] < 0
        or type(row["payload_version"]) is not int
        or row["payload_version"] not in (1, 2)
        or not (
            type(row["cancel"]) is bool or type(row["cancel"]) is int and row["cancel"] in (0, 1)
        )
        or type(row["created"]) not in (int, float)
        or not math.isfinite(row["created"])
    ):
        raise invalid()
    for name in ("owner", "error"):
        if row[name] is not None and type(row[name]) is not str:
            raise invalid()
    lease = row["lease_until"]
    if lease is not None and (type(lease) not in (int, float) or not math.isfinite(lease)):
        raise invalid()
    hexadecimal(row["payload"], 64)
    for name in ("result", "execution_config_ref", "execution_config_digest"):
        if row[name] is not None:
            hexadecimal(row[name], 64)
    if row["actor"] is not None:
        principal_value(row["actor"])
    return book.remember("job", job_id, tuple(JOB_LIMITS), row)


def read_descriptor(
    connection: Connection,
    context: ProjectContext,
    job_id: str,
    role: Literal["admission_config", "result"],
    book: ReceiptBook,
) -> tuple[ArtifactObject, RawReceipt]:
    # Candidate-first LEFT JOIN: an invalid/missing/second descriptor is never
    # filtered into a false unique success. Scope is established by read_job.
    if role not in ("admission_config", "result"):
        raise invalid()
    columns = _bounded_columns(connection)
    size = sum(
        (
            func.coalesce(_byte_length(connection, _objects.c[name]), 0)
            for name in DESCRIPTOR_FIELDS
        ),
        literal(0),
    )
    rows = (
        connection.execute(
            select(
                *(
                    case(
                        (
                            size <= book.remaining,
                            cast(value, Text) if name == "created_at" else value,
                        ),
                        else_=None,
                    ).label(name)
                    for name, value in zip(DESCRIPTOR_FIELDS, columns, strict=True)
                ),
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
                _refs.c.project_id == context.project_id,
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
        raise invalid()
    row = dict(rows[0])
    value = _object(row)
    if (
        row["reference_id"] != value.id
        or value.project_id != context.project_id
        or value.locator != object_locator(context.project_id, value.digest)
        or value.byte_count > (65536 if role == "admission_config" else 4096)
    ):
        raise invalid()
    return value, book.remember(role, job_id, (*DESCRIPTOR_FIELDS, "reference_id"), row)
