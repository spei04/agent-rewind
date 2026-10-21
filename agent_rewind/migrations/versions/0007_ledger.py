"""Ledger tables; reachable only inside the explicit manifest operator."""

from alembic import op

from agent_rewind.migrations.ledger_inputs import LedgerManifest, validate_ledger_manifest
from agent_rewind.migrations.ledger_schema import create_ledger_schema
from agent_rewind.migrations.schema import MigrationRefused

revision = "ar_0007_ledger"
down_revision = "ar_0006_admission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Generic upgrade has no intent and cannot publish a partial ledger installation.
    config = op.get_context().config
    manifest = None if config is None else config.attributes.get("ledger_manifest")
    if not isinstance(manifest, LedgerManifest):
        raise MigrationRefused("invalid_ledger_manifest")
    checked = validate_ledger_manifest(manifest.model_dump(mode="json"))
    if checked.operation != "initialize":
        raise MigrationRefused("invalid_ledger_manifest")
    create_ledger_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Ledger downgrade requires a verified restore")
