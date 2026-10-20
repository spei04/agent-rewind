"""Create ownership storage; explicit operator input and backfill remain required."""

from alembic import op

from agent_rewind.migrations.ownership_schema import create_ownership_schema

revision = "ar_0003_ownership"
down_revision = "ar_0002_adoption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_ownership_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Ownership downgrade unsupported; restore a verified backup.")
