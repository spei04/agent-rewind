"""Required-fence composition: graph refs/root and initial run projection commit together."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .artifact_graph import decode
from .artifact_metadata import ArtifactError
from .artifact_publication import PublicationIntent, PublicationWriter
from .migrations.projection_state import inspect_projection_state
from .migrations.schema import PROJECTION, MigrationRefused
from .projection_rows import insert_projection, lock_project_sequence, matching_projection
from .run_projection import RunProjection, utc_created


def _value(intent: PublicationIntent) -> RunProjection:
    # RunPublisher has verified the complete graph and rechecked source authority.
    # These fields alone are not evidence; this adapter never loads artifact bytes.
    try:
        root = decode(intent.envelope)
        manifest = root["manifest"]
        if (
            manifest["status"] != "complete"
            or root["run_id"] != intent.run_id
            or root["project_id"] != intent.context.project_id
        ):
            raise ValueError
        return RunProjection(
            intent.run_id,
            intent.context.project_id,
            utc_created(manifest["created"]),
            "complete",
            manifest["branchable"],
            manifest["parent_id"],
            manifest["head"],
            None,
        )
    except (ValueError, KeyError, TypeError):
        raise ArtifactError("projection_publication_invalid") from None


def _completed_backfill(connection: Connection) -> None:
    if connection.execute(
        text("SELECT version_num FROM alembic_version LIMIT 2")
    ).scalars().all() != [PROJECTION]:
        raise ArtifactError("projection_revision_required")
    rows = (
        connection.execute(text("SELECT state FROM installation_adoptions LIMIT 2"))
        .mappings()
        .all()
    )
    try:
        if (
            len(rows) != 1
            or inspect_projection_state(connection, {**rows[0], "_revision": PROJECTION}).status
            != "complete"
        ):
            raise ArtifactError("projection_backfill_required")
    except MigrationRefused:
        raise ArtifactError("projection_backfill_required") from None


class ProjectionPublicationWriter:
    """No default or owner-only fence. Legacy live use remains unavailable.

    The delegate must satisfy PublicationWriter's DB-time generation/owner fence
    and source producer serialization contract. Both writers use this connection;
    neither performs storage I/O nor commits. Existing projections are immutable.
    """

    def __init__(self, delegate: PublicationWriter):
        self.delegate = delegate

    def require_available(self) -> None:
        self.delegate.require_available()

    def inspect(
        self, connection: Connection, intent: PublicationIntent
    ) -> Literal["absent", "matching", "conflict"]:
        _completed_backfill(connection)
        state = self.delegate.inspect(connection, intent)
        try:
            sequence = matching_projection(connection, _value(intent))
        except ArtifactError:
            return "conflict"
        return "conflict" if state == "matching" and sequence is None else state

    def lock_and_check(self, connection: Connection, intent: PublicationIntent) -> None:
        # Project exclusion precedes every job/run or grant/source lock.
        # A child and a replacement parent publication otherwise form a cycle.
        # Allocation still occurs only after fresh fence/source validation.
        lock_project_sequence(connection, intent.context.project_id)
        self.delegate.lock_and_check(connection, intent)
        _completed_backfill(connection)

    def publish_root(self, connection: Connection, intent: PublicationIntent) -> None:
        self.lock_and_check(connection, intent)
        self.delegate.publish_root(connection, intent)
        insert_projection(connection, _value(intent))
