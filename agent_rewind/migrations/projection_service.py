"""Explicit initial run-index installation and evidence-bound offline batch projection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..artifact_metadata import ArtifactError
from ..models import canonical, digest
from ..projection_evidence import (
    OperatorReader,
    PreparedCohort,
    prepare_evidence,
    projection_identity,
)
from ..projection_rows import insert_projection, read_index
from ..projection_source import CohortIdentity, QueryBudget, read_cohort, readonly_source
from ..run_projection import MAX_COHORT_BYTES
from .inputs import validate_mapping
from .ownership_state import MAX_CURSOR_BYTES
from .projection_state import PHASE, ProjectionState, inspect_projection_state
from .schema import (
    ARTIFACTS,
    PROJECTION,
    MigrationRefused,
    catalog,
    checksum,
    dialect,
    verify_installed_profile,
)
from .service import (
    _alembic,
    _installed,
    _legacy_role_inventory,
    _public_state,
    migration_transaction,
)


def _write_progress(connection: Connection, state: ProjectionState, *, insert: bool) -> None:
    encoded = canonical(state.cursor)
    if len(encoded) > MAX_CURSOR_BYTES:
        raise MigrationRefused("projection_progress_limit")
    values = {
        "revision": PROJECTION,
        "phase": PHASE,
        "digest": state.source_digest,
        "cursor": encoded.decode(),
        "count": state.count,
        "status": state.status,
        "at": datetime.now(UTC).isoformat(),
    }
    sql = (
        "INSERT INTO migration_progress "
        "(revision,phase,source_digest,cursor,rows_verified,status,updated_at) "
        "VALUES(:revision,:phase,:digest,:cursor,:count,:status,:at)"
        if insert
        else "UPDATE migration_progress SET cursor=:cursor,rows_verified=:count,"
        "status=:status,updated_at=:at "
        "WHERE revision=:revision AND phase=:phase AND source_digest=:digest"
    )
    if dialect(connection) == "postgresql":
        sql = sql.replace(":cursor", "CAST(:cursor AS JSON)").replace(
            ":at", "CAST(:at AS TIMESTAMP WITH TIME ZONE)"
        )
    if connection.execute(text(sql), values).rowcount != 1:
        raise MigrationRefused("projection_progress_invalid")


def _result(row: dict[str, Any], state: ProjectionState) -> dict[str, Any]:
    return {
        **_public_state(row),
        "projection_rows_verified": state.count,
        "projection_rows_total": state.cursor["total_runs"],
        "projection_status": state.status,
    }


def _bind(state: ProjectionState, identity: CohortIdentity) -> None:
    expected = {
        "source_digest": state.source_digest,
        **{
            key: state.cursor[key]
            for key in ("scope_digest", "order_digest", "cohort_digest", "total_runs")
        },
    }
    if asdict(identity) != expected:
        raise MigrationRefused("projection_cohort_changed")


def initialize_projection(engine: Engine, *, timeout_seconds: int = 5) -> dict[str, Any]:
    """Schema/cohort metadata only. No artifact key, bytes or completion inference."""
    try:
        with migration_transaction(engine, timeout_seconds) as connection:
            row = _installed(connection, catalog(connection))
            if row["_revision"] == PROJECTION:
                return _result(row, inspect_projection_state(connection, row))
            if row["_revision"] != ARTIFACTS or row["state"] != "ownership_complete":
                raise MigrationRefused("artifact_schema_required")
            if row["source_kind"] == "legacy":
                _legacy_role_inventory(connection, validate_mapping(row["mapping"]))
            with QueryBudget().observe(connection):
                cohort = read_cohort(connection)
            cursor = {
                "schema_version": 1,
                "initialized_at": datetime.now(UTC).isoformat(),
                "cohort_digest": cohort.identity.cohort_digest,
                "scope_digest": cohort.identity.scope_digest,
                "order_digest": cohort.identity.order_digest,
                "total_runs": cohort.identity.total_runs,
                "last_run_id": None,
                "evidence_digest": None if cohort.order else digest([]),
                "projects": list(cohort.project_ids),
            }
            state = ProjectionState(
                cursor, cohort.identity.source_digest, 0, "running" if cohort.order else "complete"
            )
            del cohort
            _alembic(connection, "upgrade", PROJECTION)
            shape = catalog(connection)
            verify_installed_profile(shape, dialect(connection), PROJECTION)
            connection.execute(
                text("UPDATE installation_adoptions SET installed_schema_fingerprint=:fingerprint"),
                {"fingerprint": checksum(shape)},
            )
            _write_progress(connection, state, insert=True)
            return _result(_installed(connection, shape), state)
    except ArtifactError as error:
        raise MigrationRefused(str(error)) from None


def _verify_prefix(
    connection: Connection, state: ProjectionState, prepared: PreparedCohort
) -> None:
    _bind(state, prepared.identity)
    if state.cursor["last_run_id"] != (
        prepared.rows[state.count - 1].run_id if state.count else None
    ):
        raise MigrationRefused("projection_prefix_invalid")
    frozen_evidence = state.cursor["evidence_digest"]
    if frozen_evidence is not None and frozen_evidence != prepared.evidence_digest:
        raise MigrationRefused("projection_evidence_changed")
    counters = {project: 0 for project in state.cursor["projects"]}
    expected: list[dict[str, Any]] = []
    for row in prepared.rows[: state.count]:
        if row.project_id not in counters:
            raise MigrationRefused("projection_prefix_invalid")
        counters[row.project_id] += 1
        expected.append(
            {
                **projection_identity(row),
                "resource_kind": "run",
                "published_seq": counters[row.project_id],
            }
        )
    actual = read_index(connection, limit=state.count + 1)
    if actual != sorted(expected, key=lambda row: row["run_id"]):
        raise MigrationRefused("projection_prefix_invalid")
    current = connection.execute(
        text("SELECT id,run_sequence FROM projects ORDER BY id LIMIT 129")
    ).all()
    if [tuple(row) for row in current] != sorted(counters.items()):
        raise MigrationRefused("projection_sequence_invalid")


def backfill_run_index(
    engine: Engine, source: OperatorReader, *, batch_size: int = 1000, timeout_seconds: int = 5
) -> dict[str, Any]:
    """One bounded initial batch, with all operator artifact I/O outside SQL transactions.

    Every retry checks the whole capped frozen cohort. New/changed history requires
    an explicitly reviewed later projection path, never cursor skipping or repair.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise MigrationRefused("invalid_projection_batch_size")
    budget = QueryBudget()
    try:
        with readonly_source(engine, budget) as connection:
            row = _installed(connection, catalog(connection))
            state = inspect_projection_state(connection, row)
            cohort = read_cohort(connection)
            _bind(state, cohort.identity)
        # No connection/lock spans the reader. Its source is an operator-frozen
        # immutable byte view; SQL cannot guarantee later filesystem availability.
        prepared = prepare_evidence(cohort, source)
        del cohort
        with (
            migration_transaction(engine, timeout_seconds) as connection,
            budget.observe(connection),
        ):
            row = _installed(connection, catalog(connection))
            state = inspect_projection_state(connection, row)
            if row["source_kind"] == "legacy":
                _legacy_role_inventory(connection, validate_mapping(row["mapping"]))
            current = read_cohort(connection, byte_limit=MAX_COHORT_BYTES - prepared.retained_bytes)
            if current.identity != prepared.identity:
                raise MigrationRefused("projection_cohort_changed")
            del current
            _verify_prefix(connection, state, prepared)
            if state.status == "complete":
                return _result(row, state)
            end = min(state.count + batch_size, len(prepared.rows))
            for projection in prepared.rows[state.count : end]:
                insert_projection(connection, projection)
            next_state = ProjectionState(
                {
                    **state.cursor,
                    "last_run_id": prepared.rows[end - 1].run_id if end else None,
                    "evidence_digest": prepared.evidence_digest,
                },
                state.source_digest,
                end,
                "complete" if end == len(prepared.rows) else "running",
            )
            _write_progress(connection, next_state, insert=False)
            _verify_prefix(connection, next_state, prepared)
            return _result(_installed(connection, catalog(connection)), next_state)
    except ArtifactError as error:
        raise MigrationRefused(str(error)) from None
