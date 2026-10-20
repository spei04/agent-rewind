"""Add the scoped run index and per-project publication counter."""

from alembic import op

from agent_rewind.migrations.projection_schema import create_projection_schema

revision = "ar_0005_run_index"
down_revision = "ar_0004_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_projection_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Run projection downgrade unsupported; restore a verified backup.")
