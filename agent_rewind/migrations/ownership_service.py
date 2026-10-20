"""Explicit ownership transition with immutable intent and atomic bounded scope batches."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from .inputs import source_digest, validate_legacy_rows, validate_mapping
from .ownership_inputs import FreshOwnership, validate_fresh
from .ownership_lineage import Closure, relational_closure
from .ownership_state import (
    MAX_CURSOR_BYTES,
    PHASE,
    OwnershipState,
    expected_members,
    inspect_ownership_state,
    resolve_intent,
)
from .schema import (
    HEAD,
    OWNERSHIP,
    MigrationRefused,
    canonical,
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


def _typed(connection: Connection, sql: str) -> str:
    if dialect(connection) == "postgresql":
        sql = sql.replace(":cursor", "CAST(:cursor AS JSON)")
        sql = sql.replace(":at", "CAST(:at AS TIMESTAMP WITH TIME ZONE)")
        sql = sql.replace(":revoked", "CAST(:revoked AS TIMESTAMP WITH TIME ZONE)")
    return sql


def _write_progress(connection: Connection, state: OwnershipState, *, insert: bool) -> None:
    parameters: dict[str, Any] = {
        "revision": OWNERSHIP,
        "phase": PHASE,
        "digest": state.source_digest,
        "cursor": canonical(state.cursor).decode(),
        "count": state.count,
        "status": state.status,
        "at": datetime.now(UTC).isoformat(),
    }
    if len(parameters["cursor"].encode()) > MAX_CURSOR_BYTES:
        raise MigrationRefused("ownership_intent_limit")
    statement = (
        "INSERT INTO migration_progress "
        "(revision,phase,source_digest,cursor,rows_verified,status,updated_at) "
        "VALUES (:revision,:phase,:digest,:cursor,:count,:status,:at)"
        if insert
        else "UPDATE migration_progress SET cursor=:cursor,rows_verified=:count,status=:status,"
        "updated_at=:at WHERE revision=:revision AND phase=:phase AND source_digest=:digest"
    )
    result = connection.execute(text(_typed(connection, statement)), parameters)
    if result.rowcount != 1:
        raise MigrationRefused("ownership_progress_invalid")


def _create_principals(connection: Connection, row: dict[str, Any], state: OwnershipState) -> None:
    at = state.cursor["initialized_at"]
    connection.execute(
        text(
            _typed(
                connection,
                "INSERT INTO organizations(id,installation_key,created_at) VALUES (:id,:key,:at)",
            )
        ),
        {"id": state.organization_id, "key": row["installation_key"], "at": at},
    )
    connection.execute(
        text(
            _typed(
                connection,
                "INSERT INTO projects(id,organization_id,name,created_at) "
                "VALUES (:id,:org,:name,:at)",
            )
        ),
        {
            "id": state.project_id,
            "org": state.organization_id,
            "name": state.project_name,
            "at": at,
        },
    )
    for project, principal, role, revoked, default in expected_members(connection, state):
        connection.execute(
            text(
                _typed(
                    connection,
                    "INSERT INTO project_memberships "
                    "(project_id,principal_id,role,revoked_at,legacy_default) "
                    "VALUES (:project,:principal,:role,:revoked,:default)",
                )
            ),
            {
                "project": project,
                "principal": principal,
                "role": role,
                "revoked": revoked.isoformat() if revoked is not None else None,
                "default": default,
            },
        )


def _verify_prefix(connection: Connection, state: OwnershipState, closure: Closure) -> None:
    if (
        state.cursor["total_resources"] != len(closure.resources)
        or state.cursor["closure_digest"] != closure.digest
        or state.cursor["last_resource"]
        != (list(closure.resources[state.count - 1]) if state.count else None)
    ):
        raise MigrationRefused("ownership_closure_changed")
    rows = connection.execute(
        text(
            "SELECT resource_kind,resource_id,project_id FROM resource_scopes "
            "ORDER BY resource_kind,resource_id LIMIT :bound"
        ).execution_options(stream_results=True, yield_per=1, max_row_buffer=1),
        {"bound": state.count + 1},
    )
    seen = 0
    for record in rows:
        if seen >= state.count or tuple(record) != (*closure.resources[seen], state.project_id):
            raise MigrationRefused("ownership_scope_conflict")
        seen += 1
    if seen != state.count:
        raise MigrationRefused("ownership_scope_conflict")


def initialize_ownership(
    engine: Engine,
    fresh: FreshOwnership | dict[str, Any] | None = None,
    *,
    batch_size: int = 1000,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise MigrationRefused("invalid_ownership_batch_size")
    parsed = (
        validate_fresh(fresh.model_dump() if isinstance(fresh, FreshOwnership) else fresh)
        if fresh is not None
        else None
    )
    with migration_transaction(engine, timeout_seconds) as connection:
        row = _installed(connection, catalog(connection))
        if row["source_kind"] == "legacy":
            if parsed is not None:
                raise MigrationRefused("legacy_ownership_input_forbidden")
            mapping = validate_mapping(row["mapping"])
            _legacy_role_inventory(connection, mapping)
            validate_legacy_rows(connection, mapping)
            original_digest = mapping.source_dataset_digest
            intent = {"source_kind": "legacy", "mapping_digest": row["mapping_digest"]}
        else:
            if parsed is None:
                raise MigrationRefused("fresh_ownership_input_required")
            if parsed.installation_key != row["installation_key"]:
                raise MigrationRefused("ownership_intent_conflict")
            original_digest = source_digest(connection)
            # Empty means every original table, including audit, not merely no runs.
            if any(
                connection.execute(text(query)).first()
                for query in (
                    "SELECT 1 FROM records LIMIT 1",
                    "SELECT 1 FROM events LIMIT 1",
                    "SELECT 1 FROM jobs LIMIT 1",
                    "SELECT 1 FROM api_keys LIMIT 1",
                    "SELECT 1 FROM audit LIMIT 1",
                )
            ):
                raise MigrationRefused("fresh_source_not_empty")
            intent = {"source_kind": "fresh", "input": parsed.model_dump()}
        closure = relational_closure(connection)
        created = row["_revision"] == HEAD
        if created:
            cursor = {
                "schema_version": 1,
                "intent": intent,
                "intent_digest": checksum(intent),
                "closure_digest": closure.digest,
                "total_resources": len(closure.resources),
                "last_resource": None,
                "initialized_at": datetime.now(UTC).isoformat(),
            }
            if len(canonical(cursor)) > MAX_CURSOR_BYTES:
                raise MigrationRefused("ownership_intent_limit")
            try:
                org, project, name, grants = resolve_intent(row, intent)
            except (ValueError, TypeError):
                raise MigrationRefused("ownership_intent_conflict") from None
            state = OwnershipState(
                cursor, original_digest, 0, "running", org, project, name, grants
            )
            _alembic(connection, "upgrade", OWNERSHIP)
            shape = catalog(connection)
            verify_installed_profile(shape, dialect(connection), OWNERSHIP)
            connection.execute(
                text("UPDATE installation_adoptions SET installed_schema_fingerprint=:fingerprint"),
                {"fingerprint": checksum(shape)},
            )
            _create_principals(connection, row, state)
        else:
            state = inspect_ownership_state(connection, row)
            if state.cursor["intent"] != intent:
                raise MigrationRefused("ownership_intent_conflict")
            if state.source_digest != original_digest:
                raise MigrationRefused("source_digest_mismatch")
        _verify_prefix(connection, state, closure)
        if state.status == "complete":
            return {
                **_public_state(row),
                "ownership_rows_verified": state.count,
                "ownership_rows_total": len(closure.resources),
            }
        end = min(state.count + batch_size, len(closure.resources))
        for kind, identifier in closure.resources[state.count : end]:
            connection.execute(
                text(
                    "INSERT INTO resource_scopes(resource_kind,resource_id,project_id) "
                    "VALUES (:kind,:id,:project)"
                ),
                {"kind": kind, "id": identifier, "project": state.project_id},
            )
        cursor = {
            **state.cursor,
            "last_resource": list(closure.resources[end - 1]) if end else None,
        }
        complete = end == len(closure.resources)
        next_state = OwnershipState(
            cursor,
            state.source_digest,
            end,
            "complete" if complete else "running",
            state.organization_id,
            state.project_id,
            state.project_name,
            state.grants,
        )
        _write_progress(connection, next_state, insert=created)
        if complete:
            connection.execute(
                text(
                    "UPDATE installation_adoptions SET state='ownership_complete', "
                    "organization_id=:org,project_id=:project"
                ),
                {"org": state.organization_id, "project": state.project_id},
            )
        final = _installed(connection, catalog(connection))
        return {
            **_public_state(final),
            "ownership_rows_verified": end,
            "ownership_rows_total": len(closure.resources),
        }
