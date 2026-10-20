"""Frozen unversioned five-table baseline."""

from alembic import op

from agent_rewind.migrations.schema import create_baseline

revision = "ar_0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_baseline(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade unsupported; restore a verified backup.")
