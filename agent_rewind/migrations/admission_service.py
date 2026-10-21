"""Explicit additive admission storage installation; no coordinator or dispatch."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..projection_source import QueryBudget, read_cohort
from .inputs import source_digest, validate_mapping
from .ownership_state import inspect_ownership_state
from .projection_service import _bind
from .projection_state import inspect_projection_state
from .schema import (
    ADMISSION,
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


def initialize_admission(engine: Engine, *, timeout_seconds: int = 5) -> dict[str, Any]:
    """Install empty identities, preserving original history and completed progress.

    The literal catalog must already be independently reviewed and packaged.
    This verifies SQL preservation, not artifact availability or new-job authority.
    """
    with migration_transaction(engine, timeout_seconds) as connection:
        row = _installed(connection, catalog(connection))
        if row["_revision"] not in {PROJECTION, ADMISSION} or row["state"] != "ownership_complete":
            raise MigrationRefused("completed_projection_required")
        ownership = inspect_ownership_state(connection, row)
        projection = inspect_projection_state(connection, row)
        if ownership.status != "complete" or projection.status != "complete":
            raise MigrationRefused("completed_projection_required")
        if row["source_kind"] == "legacy":
            _legacy_role_inventory(connection, validate_mapping(row["mapping"]))
        if row["_revision"] == ADMISSION:
            return _public_state(row)
        with QueryBudget().observe(connection):
            cohort = read_cohort(connection)
            _bind(projection, cohort.identity)
        original = cohort.identity.source_digest
        del cohort
        _alembic(connection, "upgrade", ADMISSION)
        shape = catalog(connection)
        verify_installed_profile(shape, dialect(connection), ADMISSION)
        if source_digest(connection) != original:
            raise MigrationRefused("source_digest_mismatch")
        connection.execute(
            text("UPDATE installation_adoptions SET installed_schema_fingerprint=:fingerprint"),
            {"fingerprint": checksum(shape)},
        )
        return _public_state(_installed(connection, shape))
