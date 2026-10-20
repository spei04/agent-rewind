"""SQL-only initial projection inserts; callers own fresh fence/source authority."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import column, func, literal, select, table, text
from sqlalchemy.engine import Connection

from .artifact_metadata import ArtifactError, digest_value, identifier
from .projection_evidence import projection_identity
from .run_projection import RunProjection
from .scoped_repositories import _byte_length

FIELDS = (
    "run_id",
    "project_id",
    "resource_kind",
    "created_at",
    "status",
    "branchable",
    "parent_id",
    "event_head",
    "published_seq",
    "projection_reason",
)
INDEX = table("run_index", *(column(name) for name in FIELDS))
MAX_SEQUENCE = 2**63 - 1


def validate_projection(value: RunProjection) -> None:
    identifier(value.run_id)
    identifier(value.project_id)
    if value.parent_id is not None:
        identifier(value.parent_id)
    if value.event_head is not None:
        digest_value(value.event_head)
    if (
        not isinstance(value.created_at, datetime)
        or value.created_at.utcoffset() is None
        or value.status not in {"running", "complete", "failed", "incomplete"}
        or type(value.branchable) is not bool
        or (value.branchable and value.status != "complete")
        or value.projection_reason not in {None, "unfenced_execution"}
    ):
        raise ArtifactError("projection_row_invalid")


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    try:
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        value = RunProjection(
            row["run_id"],
            row["project_id"],
            created,
            row["status"],
            bool(row["branchable"]),
            row["parent_id"],
            row["event_head"],
            row["projection_reason"],
        )
        if row["resource_kind"] != "run" or row["branchable"] not in (0, 1, False, True):
            raise ValueError
        sequence = row["published_seq"]
        if type(sequence) is not int or not 1 <= sequence <= MAX_SEQUENCE:
            raise ValueError
        validate_projection(value)
        return {
            **projection_identity(value),
            "created_at": value.created_at.astimezone(UTC).isoformat(),
            "resource_kind": "run",
            "published_seq": sequence,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ArtifactError("projection_row_invalid") from None


def read_index(
    connection: Connection, *, limit: int, run_id: str | None = None
) -> list[dict[str, Any]]:
    size = sum((func.coalesce(_byte_length(connection, field), 0) for field in INDEX.c), literal(0))
    predicate = INDEX.c.run_id == run_id if run_id is not None else literal(True)
    if connection.execute(
        select(literal(1)).select_from(INDEX).where(predicate, size > 1024).limit(1)
    ).first():
        raise ArtifactError("projection_row_invalid")
    rows = connection.execute(
        select(INDEX).where(predicate, size <= 1024).order_by(INDEX.c.run_id).limit(limit)
    ).mappings()
    return [_normalize(dict(row)) for row in rows]


def matching_projection(connection: Connection, value: RunProjection) -> int | None:
    rows = read_index(connection, limit=2, run_id=value.run_id)
    if not rows:
        return None
    expected = {
        **projection_identity(value),
        "created_at": value.created_at.astimezone(UTC).isoformat(),
        "resource_kind": "run",
    }
    if len(rows) != 1 or {k: v for k, v in rows[0].items() if k != "published_seq"} != expected:
        raise ArtifactError("projection_conflict")
    return int(rows[0]["published_seq"])


def insert_projection(connection: Connection, value: RunProjection) -> int:
    """Allocate under the project lock held through caller commit; never update existing rows.

    This primitive neither verifies artifact bytes nor grants publication authority.
    The offline migrator or required same-connection live fence must establish that.
    """
    validate_projection(value)
    raw, dialect = connection.connection.driver_connection, connection.dialect.name
    if not connection.in_transaction() or not (
        (dialect == "postgresql" and getattr(raw, "autocommit", None) is False)
        or (
            dialect == "sqlite"
            and getattr(raw, "isolation_level", None) is not None
            and getattr(raw, "autocommit", False) is not True
        )
    ):
        raise ArtifactError("projection_transaction_required")
    if dialect == "sqlite":
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            raise ArtifactError("projection_constraints_required")
        connection.execute(
            text("UPDATE projects SET run_sequence=run_sequence WHERE id=:id"),
            {"id": value.project_id},
        )
    query = "SELECT run_sequence FROM projects WHERE id=:id"
    if dialect == "postgresql":
        query += " FOR UPDATE"
    counter: Any = connection.execute(text(query), {"id": value.project_id}).scalar_one_or_none()
    if type(counter) is not int or not 0 <= counter <= MAX_SEQUENCE:
        raise ArtifactError("projection_sequence_invalid")
    if not connection.execute(
        text(
            "SELECT 1 FROM records r JOIN resource_scopes s "
            "ON s.resource_kind='run' AND s.resource_id=r.id "
            "WHERE r.kind='run' AND r.id=:run AND s.project_id=:project"
        ),
        {"run": value.run_id, "project": value.project_id},
    ).first():
        raise ArtifactError("projection_scope_invalid")
    existing = matching_projection(connection, value)
    if existing is not None:
        if existing > counter:
            raise ArtifactError("projection_sequence_invalid")
        return existing
    if (
        value.parent_id is not None
        and not connection.execute(
            text("SELECT 1 FROM run_index WHERE run_id=:run AND project_id=:project"),
            {"run": value.parent_id, "project": value.project_id},
        ).first()
    ):
        raise ArtifactError("projection_parent_required")
    if counter == MAX_SEQUENCE:
        raise ArtifactError("projection_sequence_invalid")
    sequence = counter + 1
    parameters = {**projection_identity(value), "sequence": sequence}
    statement = (
        "INSERT INTO run_index "
        "(run_id,project_id,resource_kind,created_at,status,branchable,parent_id,"
        "event_head,published_seq,projection_reason) VALUES "
        "(:run_id,:project_id,'run',:created_at,:status,:branchable,:parent_id,"
        ":event_head,:sequence,:projection_reason)"
    )
    if dialect == "postgresql":
        statement = statement.replace(
            ":created_at", "CAST(:created_at AS TIMESTAMP WITH TIME ZONE)"
        )
    connection.execute(text(statement), parameters)
    result = connection.execute(
        text(
            "UPDATE projects SET run_sequence=:sequence "
            "WHERE id=:project_id AND run_sequence=:previous"
        ),
        {"sequence": sequence, "project_id": value.project_id, "previous": counter},
    )
    if result.rowcount != 1:
        raise ArtifactError("projection_sequence_invalid")
    return sequence
