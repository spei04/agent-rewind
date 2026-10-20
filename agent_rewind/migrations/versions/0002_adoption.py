"""Add durable origin and resumable phase metadata; no customer ownership."""

from alembic import op

from agent_rewind.migrations.metadata import create_adoption_metadata

revision = "ar_0002_adoption"
down_revision = "ar_0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_adoption_metadata(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Provenance downgrade unsupported; restore a verified backup.")
