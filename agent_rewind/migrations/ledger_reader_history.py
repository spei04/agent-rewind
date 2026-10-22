"""Bounded historical provenance reads within an issued ledger transaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .ledger_check import LedgerCheck
from .ledger_history_sql import SQL
from .ledger_state import (
    ManifestCursor,
    OpeningCursor,
    validate_ledger_chain,
    validate_progress_row,
)
from .ownership_state import OwnershipState, timestamp, validate_ownership_progress
from .projection_state import ProjectionState, validate_projection_progress
from .schema import ADMISSION, LEDGER, MigrationRefused, checksum, dialect
from .service import _validate_adoption_row

_FIELDS = {
    "H10_adoption": (
        "installation_key",
        "singleton",
        "source_kind",
        "source_baseline",
        "schema_fingerprint",
        "installed_schema_fingerprint",
        "organization_id",
        "project_id",
        "mapping_digest",
        "mapping",
        "backup_evidence_digest",
        "drain_evidence_digest",
        "created_at",
        "state",
    ),
    "H20_ownership": ("source_digest", "cursor", "rows_verified", "status", "updated_at"),
    "H30_projection": ("source_digest", "cursor", "rows_verified", "status", "updated_at"),
    "H40_organization": ("created_at",),
    "H50_seed_project": ("name", "created_at"),
    "H60_ledger_progress": (
        "revision",
        "phase",
        "source_digest",
        "cursor",
        "rows_verified",
        "status",
        "updated_at",
    ),
}
_LIMITS = {
    "H10_adoption": 1114625,
    "H20_ownership": 131150,
    "H30_projection": 66560,
    "H40_organization": 65536,
    "H50_seed_project": 66016,
    "H60_ledger_progress": 16819107,
}
_CODES = {
    "H10_adoption": "adoption_metadata_drift",
    "H20_ownership": "ownership_progress_invalid",
    "H30_projection": "projection_progress_invalid",
    "H40_organization": "ownership_progress_invalid",
    "H50_seed_project": "ownership_progress_invalid",
    "H60_ledger_progress": "ledger_progress_invalid",
}


@dataclass(frozen=True)
class History:
    adoption: dict[str, Any]
    ownership: OwnershipState
    projection: ProjectionState
    manifests: tuple[ManifestCursor, ...]
    opening: OpeningCursor | None


def _query(connection: Connection, name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            text(SQL[("all", dialect(connection), name)]), parameters
        ).mappings()
    ]


def read_revision(connection: Connection) -> str:
    rows = _query(connection, "H00_revision", {})
    if (
        len(rows) != 1
        or set(rows[0]) != {"candidate_rows", "invalid_rows", "safe_revision"}
        or type(rows[0]["candidate_rows"]) is not int
        or type(rows[0]["invalid_rows"]) is not int
        or rows[0]["candidate_rows"] != 1
        or rows[0]["invalid_rows"] != 0
        or type(rows[0]["safe_revision"]) is not str
        or rows[0]["safe_revision"] not in {ADMISSION, LEDGER}
    ):
        raise MigrationRefused("schema_incompatible")
    return rows[0]["safe_revision"]


def _wire_time(value: Any) -> datetime:
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value)
        is None
    ):
        raise ValueError("timestamp projection")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    rendered = (
        f"{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}T"
        f"{parsed.hour:02d}:{parsed.minute:02d}:{parsed.second:02d}.{parsed.microsecond:06d}Z"
    )
    if rendered != value:
        raise ValueError("timestamp round trip")
    return parsed.astimezone(UTC)


def _read(
    connection: Connection,
    name: str,
    work: LedgerCheck,
    parameters: dict[str, Any] | None = None,
    *,
    absent: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    parameters = {} if parameters is None else parameters
    code = _CODES[name]
    work.check()
    rows = _query(connection, name + "_gate", parameters)
    if len(rows) != 1 or any(type(value) is not int for value in rows[0].values()):
        raise MigrationRefused(code)
    receipt = rows[0]
    fields = {
        "candidate_rows",
        "invalid_rows",
        "native_bytes",
        "utf8_bytes",
        "historical_timestamp_bytes",
    }
    if name == "H30_projection":
        fields.add("original_metadata_bytes")
    if name == "H60_ledger_progress":
        fields.update(("cursor_bytes", "metadata_bytes", "opening_rows", "manifest_rows"))
    if set(receipt) != fields:
        raise MigrationRefused(code)
    if absent:
        if any(receipt.values()):
            raise MigrationRefused(code)
        return [], 0
    ledger = name == "H60_ledger_progress"
    if (
        receipt["invalid_rows"] != 0
        or not (2 <= receipt["candidate_rows"] <= 257 if ledger else receipt["candidate_rows"] == 1)
        or not 1 <= receipt["native_bytes"] <= _LIMITS[name]
        or not 1 <= receipt["utf8_bytes"] <= _LIMITS[name] * 4
        or not 0 <= receipt["historical_timestamp_bytes"] <= 65536
        or (name == "H30_projection" and not 1 <= receipt["original_metadata_bytes"] <= 1024)
        or (
            ledger
            and (
                receipt["opening_rows"] != 1
                or not 1 <= receipt["manifest_rows"] <= 256
                or not 1 <= receipt["cursor_bytes"] <= 16777216
                or not 1 <= receipt["metadata_bytes"] <= 41891
            )
        )
    ):
        raise MigrationRefused(code)
    binds = {
        **parameters,
        "expected_rows": receipt["candidate_rows"],
        "expected_native_bytes": receipt["native_bytes"],
        "expected_utf8_bytes": receipt["utf8_bytes"],
    }
    if ledger:
        binds["expected_cursor_bytes"] = receipt["cursor_bytes"]
    bodies = _query(connection, name + "_body", binds)
    try:
        if len(bodies) != receipt["candidate_rows"]:
            raise ValueError("history changed")
        wire_bytes = 0
        for body in bodies:
            work.check()
            if set(body) != set(_FIELDS[name]):
                raise ValueError("history columns")
            for value in body.values():
                if type(value) not in (str, int, type(None)):
                    raise ValueError("history scalar")
                wire_bytes += 0 if value is None else len(str(value).encode("utf-8"))
        if wire_bytes != receipt["utf8_bytes"]:
            raise ValueError("history receipt")
        if dialect(connection) == "postgresql":
            for body in bodies:
                for column in ("created_at", "updated_at"):
                    if column in body:
                        body[column] = _wire_time(body[column])
        return bodies, receipt["historical_timestamp_bytes"]
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise MigrationRefused(code) from None


def read_history(
    connection: Connection, revision: str, shape: dict[str, Any], work: LedgerCheck
) -> History:
    for query, field in (
        ("H01_progress_addressability", "invalid_key_exists"),
        ("H02_misplaced_ledger_namespace", "misplaced_exists"),
    ):
        rows = _query(connection, query, {})
        if (
            len(rows) != 1
            or set(rows[0]) != {field}
            or type(rows[0][field]) is not int
            or rows[0][field] != 0
        ):
            raise MigrationRefused("ledger_progress_invalid")
    rows, historical_bytes = _read(connection, "H10_adoption", work)
    adoption = rows[0]
    if adoption["installed_schema_fingerprint"] != checksum(shape):
        raise MigrationRefused("schema_incompatible")
    _validate_adoption_row(connection, adoption, revision)
    adoption["_revision"] = revision
    rows, size = _read(connection, "H20_ownership", work)
    historical_bytes += size
    ownership = validate_ownership_progress(adoption, rows[0])
    if ownership.status != "complete" or adoption["state"] != "ownership_complete":
        raise MigrationRefused("ownership_progress_invalid")
    rows, _ = _read(connection, "H30_projection", work)
    projection = validate_projection_progress(rows[0])
    if projection.status != "complete":
        raise MigrationRefused("projection_progress_invalid")
    rows, size = _read(
        connection,
        "H40_organization",
        work,
        {
            "expected_organization_id": ownership.organization_id,
            "expected_installation_key": adoption["installation_key"],
        },
    )
    historical_bytes += size
    organization = rows[0]
    rows, size = _read(
        connection,
        "H50_seed_project",
        work,
        {
            "expected_project_id": ownership.project_id,
            "expected_organization_id": ownership.organization_id,
        },
    )
    historical_bytes += size
    try:
        if (
            historical_bytes > 262144
            or rows[0]["name"] != ownership.project_name
            or timestamp(organization["created_at"])
            != timestamp(ownership.cursor["initialized_at"])
            or timestamp(rows[0]["created_at"]) != timestamp(ownership.cursor["initialized_at"])
        ):
            raise ValueError("seed identity")
    except (ValueError, TypeError):
        raise MigrationRefused("ownership_progress_invalid") from None
    progress, _ = _read(connection, "H60_ledger_progress", work, absent=revision == ADMISSION)
    parsed = []
    for row in progress:
        work.check()
        parsed.append(validate_progress_row(connection, row))
    manifests = tuple(
        sorted(
            (value for value in parsed if isinstance(value, ManifestCursor)),
            key=lambda value: value.sequence,
        )
    )
    openings = [value for value in parsed if isinstance(value, OpeningCursor)]
    opening = openings[0] if len(openings) == 1 else None
    if revision == LEDGER:
        if opening is None:
            raise MigrationRefused("ledger_progress_invalid")
        head = validate_ledger_chain(manifests, opening, check=work.check)
        if head.installation_key != adoption["installation_key"]:
            raise MigrationRefused("ledger_progress_invalid")
    return History(adoption, ownership, projection, manifests, opening)
