"""Explicit empty object-schema installation after verified ownership completion."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .inputs import source_digest, validate_mapping
from .ownership_lineage import relational_closure
from .ownership_service import _verify_prefix
from .ownership_state import inspect_ownership_state
from .schema import (
    ARTIFACTS,
    OWNERSHIP,
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


def initialize_artifacts(engine: Engine, *, timeout_seconds: int = 5) -> dict[str, Any]:
    with migration_transaction(engine, timeout_seconds) as connection:
        row = _installed(connection, catalog(connection))
        if row["_revision"] not in {OWNERSHIP, ARTIFACTS} or row["state"] != "ownership_complete":
            raise MigrationRefused("completed_ownership_required")
        state = inspect_ownership_state(connection, row)
        if state.status != "complete" or source_digest(connection) != state.source_digest:
            raise MigrationRefused("source_digest_mismatch")
        if row["source_kind"] == "legacy":
            _legacy_role_inventory(connection, validate_mapping(row["mapping"]))
        _verify_prefix(connection, state, relational_closure(connection))
        if row["_revision"] == ARTIFACTS:
            return _public_state(row)
        _alembic(connection, "upgrade", ARTIFACTS)
        shape = catalog(connection)
        verify_installed_profile(shape, dialect(connection), ARTIFACTS)
        connection.execute(
            text("UPDATE installation_adoptions SET installed_schema_fingerprint=:fingerprint"),
            {"fingerprint": checksum(shape)},
        )
        return _public_state(_installed(connection, shape))
