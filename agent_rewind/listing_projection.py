"""Bounded projection cells, keyset candidates and conservative summary rules."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

from sqlalchemy import Text, and_, case, column, func, literal, or_, select, table, text, tuple_
from sqlalchemy.engine import Connection

from .artifact_metadata import ArtifactError, digest_value
from .errors import Fault
from .projection_rows import INDEX, MAX_SEQUENCE, validate_projection
from .run_cursor import CursorPosition
from .run_projection import RunProjection, utc_created
from .scoped_lineage import ResourceNotFound, identifier
from .scoped_repositories import _byte_length

COUNTERS = table("projects", column("id"), column("run_sequence"))


def fail() -> NoReturn:
    raise Fault("dependency_unavailable")


def bounded(connection: Connection) -> Any:
    total = sum((func.coalesce(_byte_length(connection, c), 0) for c in INDEX.c), literal(0))
    return total <= 1024


@dataclass(frozen=True)
class IndexEntry:
    value: RunProjection
    sequence: int

    def receipt(self) -> dict[str, Any]:
        v = self.value
        return {
            "run_id": v.run_id,
            "project_id": v.project_id,
            "resource_kind": "run",
            "created_at": v.created_at.astimezone(UTC).isoformat(),
            "status": v.status,
            "branchable": v.branchable,
            "parent_id": v.parent_id,
            "event_head": v.event_head,
            "published_seq": self.sequence,
            "projection_reason": v.projection_reason,
        }


def entry(row: Any, project_id: str) -> IndexEntry:
    try:
        created = row["created_at"]
        if type(created) is str:
            parsed = datetime.fromisoformat(created)
            if parsed.utcoffset() is None or parsed.astimezone(UTC).isoformat() != created:
                fail()
            created = parsed
        flag = row["branchable"]
        if type(flag) not in {bool, int} or flag not in (0, 1):
            fail()
        sequence = row["published_seq"]
        if type(sequence) is not int or not 1 <= sequence <= MAX_SEQUENCE:
            fail()
        value = RunProjection(
            row["run_id"],
            row["project_id"],
            created,
            row["status"],
            bool(flag),
            row["parent_id"],
            row["event_head"],
            row["projection_reason"],
        )
        if row["resource_kind"] != "run" or value.project_id != project_id:
            fail()
        validate_projection(value)
        return IndexEntry(value, sequence)
    except (ArtifactError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise Fault("dependency_unavailable") from None


def safe_columns(connection: Connection) -> list[Any]:
    safe = bounded(connection)
    return [case((safe, c), else_=None).label(c.name) for c in INDEX.c]


def safe_created(connection: Connection) -> Any:
    """Reject invalid ordering cells before keyset filtering can hide them."""
    created = INDEX.c.created_at
    if connection.dialect.name == "postgresql":
        # Native TIMESTAMPTZ also permits infinity and dates the Python driver
        # cannot represent. Compare in SQL without materializing those values.
        return and_(
            created >= datetime.min.replace(tzinfo=UTC),
            created <= datetime.max.replace(tzinfo=UTC),
        )
    size = _byte_length(connection, created)
    digits = "[0-9]"
    seconds = f"{digits * 4}-{digits * 2}-{digits * 2}T{digits * 2}:{digits * 2}:{digits * 2}"
    prefix = func.substr(created, 1, 19)
    canonical = and_(
        or_(
            and_(size == 25, created.op("GLOB")(seconds + "+00:00")),
            and_(
                size == 32,
                created.op("GLOB")(seconds + "." + digits * 6 + "+00:00"),
                func.substr(created, 21, 6) != "000000",
            ),
        ),
        func.substr(created, 1, 4) != "0000",
        # The explicit modifier normalizes impossible calendar dates and
        # 24:00; bare strftime can merely echo those inputs.
        func.strftime("%Y-%m-%dT%H:%M:%S", prefix, "+0 seconds") == prefix,
    )
    # CASE bounds native parser work as well as returned bytes, including NUL
    # suffixes. Invalid/NULL cells become a zero marker in the aggregate.
    return case(
        (and_(func.typeof(created) == "text", size.in_((25, 32))), canonical),
        else_=False,
    )


def candidates(
    connection: Connection, project: str, limit: int, cursor: CursorPosition | None
) -> tuple[int, list[IndexEntry]]:
    """Counter and candidate rows share one statement, including an empty page."""
    safe_sequence = and_(INDEX.c.published_seq >= 1, INDEX.c.published_seq <= MAX_SEQUENCE)
    safe_counter = and_(COUNTERS.c.run_sequence >= 0, COUNTERS.c.run_sequence <= MAX_SEQUENCE)
    if connection.dialect.name == "sqlite":
        safe_sequence = and_(safe_sequence, func.typeof(INDEX.c.published_seq) == "integer")
        safe_counter = and_(safe_counter, func.typeof(COUNTERS.c.run_sequence) == "integer")
    # Watermark/keyset filters must not hide malformed ordering cells or a
    # counter behind committed rows. This project-scoped scan shares the native
    # work ceiling; LIMIT is not used as an execution-work guarantee.
    guard = (
        select(
            func.coalesce(
                func.min(case((and_(safe_sequence, safe_created(connection)), 1), else_=0)), 1
            ).label("valid"),
            func.coalesce(func.max(case((safe_sequence, INDEX.c.published_seq), else_=0)), 0).label(
                "maximum"
            ),
        )
        .where(INDEX.c.project_id == project)
        .cte("list_order_guard")
        .prefix_with("MATERIALIZED")
    )
    counter = (
        select(
            case((safe_counter, COUNTERS.c.run_sequence), else_=None).label("current"),
            case(
                (and_(guard.c.valid == 1, guard.c.maximum <= COUNTERS.c.run_sequence), 1), else_=0
            ).label("consistent"),
        )
        .select_from(COUNTERS.join(guard, literal(True)))
        .where(COUNTERS.c.id == project)
        .cte("list_counter")
        .prefix_with("MATERIALIZED")
    )
    watermark = counter.c.current if cursor is None else literal(cursor.watermark)
    query = (
        select(*safe_columns(connection), literal(1).label("present"))
        .select_from(INDEX.join(counter, literal(True)))
        .where(
            INDEX.c.project_id == project,
            INDEX.c.published_seq <= watermark,
            counter.c.consistent == 1,
        )
    )
    if cursor is not None:
        query = query.where(
            tuple_(INDEX.c.created_at, INDEX.c.run_id)
            < tuple_(
                cursor.last_created_at
                if connection.dialect.name == "postgresql"
                else cursor.last_created_at.astimezone(UTC).isoformat(),
                cursor.last_id,
            )
        )
    page = (
        query.order_by(INDEX.c.created_at.desc(), INDEX.c.run_id.desc())
        .limit(limit + 1)
        .cte("page")
    )
    rows = connection.execute(
        select(counter.c.current, counter.c.consistent, *page.c)
        .select_from(counter.outerjoin(page, literal(True)))
        .order_by(page.c.created_at.desc(), page.c.run_id.desc())
    ).mappings()
    current: int | None = None
    result = []
    for row in rows:
        observed = row["current"]
        if type(observed) is not int or not 0 <= observed <= MAX_SEQUENCE or row["consistent"] != 1:
            fail()
        current = observed
        if cursor is not None and current < cursor.watermark:
            fail()
        if row["present"] is not None:
            result.append(entry(row, project))
    if current is None:
        raise ResourceNotFound()
    return (current if cursor is None else cursor.watermark), result


def by_ids(connection: Connection, project: str, ids: set[str]) -> dict[str, IndexEntry]:
    if not ids:
        return {}
    # The caller's request-wide node limit bounds this set. One set-oriented query.
    result = {}
    for row in connection.execute(
        select(*safe_columns(connection)).where(
            INDEX.c.project_id == project, INDEX.c.run_id.in_(sorted(ids))
        )
    ).mappings():
        value = entry(row, project)
        result[value.value.run_id] = value
    if set(result) != ids:
        raise ResourceNotFound()
    return result


def matching_query(connection: Connection, values: list[IndexEntry]) -> Any:
    """Projection receipt query composes with source receipts in ONE final SELECT."""
    if connection.dialect.name == "sqlite":
        raw = """SELECT
          CAST(json_extract(value,'$.run_id') AS TEXT) AS run_id,
          CAST(json_extract(value,'$.project_id') AS TEXT) AS project_id,
          json_extract(value,'$.resource_kind') AS resource_kind,
          json_extract(value,'$.created_at') AS created_at,
          json_extract(value,'$.status') AS status,
          json_extract(value,'$.branchable') AS branchable,
          json_extract(value,'$.parent_id') AS parent_id,
          json_extract(value,'$.event_head') AS event_head,
          json_extract(value,'$.published_seq') AS published_seq,
          json_extract(value,'$.projection_reason') AS projection_reason
          FROM json_each(:projection_receipts)"""
    else:
        raw = """SELECT * FROM jsonb_to_recordset(CAST(:projection_receipts AS jsonb)) AS p(
          run_id TEXT,project_id TEXT,resource_kind TEXT,created_at TIMESTAMPTZ,
          status TEXT,branchable BOOLEAN,parent_id TEXT,event_head TEXT,published_seq BIGINT,
          projection_reason TEXT)"""
    wanted = (
        text(raw)
        .columns(**{c.name: Text() for c in INDEX.c})
        .cte("projection_receipts")
        .prefix_with("MATERIALIZED")
    )
    return (
        select(literal("projection").label("kind"), wanted.c.run_id.label("id"))
        .select_from(
            wanted.join(
                INDEX,
                and_(INDEX.c.run_id == wanted.c.run_id, INDEX.c.project_id == wanted.c.project_id),
            )
        )
        .where(
            bounded(connection),
            *(c.is_not_distinct_from(wanted.c[c.name]) for c in INDEX.c),
        )
        .limit(len(values) + 1)
    )


def summary(value: IndexEntry, source: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Stored verification remains provenance; no artifact/event reads or repair."""
    v = value.value
    try:
        if (
            identifier(source["id"]) != v.run_id
            or utc_created(source["created"]) != v.created_at
            or source["parent_id"] != v.parent_id
            or identifier(source["job_id"]) != identifier(job["id"])
            or source["status"] not in {"running", "complete", "failed"}
            or type(source["branchable"]) is not bool
            or (source.get("success") is not None and type(source["success"]) is not bool)
            or (source["status"] == "complete" and type(source.get("success")) is not bool)
            or job["status"] not in {"queued", "running", "succeeded", "failed", "cancelled"}
            or type(job["cancel"]) is not bool
        ):
            fail()
        head = source["head"]
        if head is not None:
            digest_value(head)
        owner, lease = job["owner"], job["lease_until"]
        if owner is not None and (
            type(owner) is not str or not 1 <= len(owner) <= 64 or "\0" in owner
        ):
            fail()
        if lease is not None and (
            type(lease) not in {int, float} or not math.isfinite(lease) or lease < 0
        ):
            fail()
        if v.status == "complete" and (source["status"] != "complete" or head != v.event_head):
            fail()
        status = "incomplete" if v.status == "running" else v.status
        return {
            "id": v.run_id,
            "project_id": v.project_id,
            "created_at": v.created_at.astimezone(UTC).isoformat(timespec="microseconds"),
            "status": status,
            "branchable": (
                status == "complete"
                and v.branchable
                and source["branchable"]
                and job["status"] == "succeeded"
                and not job["cancel"]
            ),
            "parent_id": v.parent_id,
            "event_head": v.event_head,
        }
    except (ArtifactError, ResourceNotFound, KeyError, ValueError, TypeError, OverflowError):
        raise Fault("dependency_unavailable") from None
