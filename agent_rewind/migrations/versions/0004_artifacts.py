"""Create empty scoped object metadata; later publication must verify all bytes."""

from alembic import op

from agent_rewind.migrations.artifact_schema import create_artifact_schema

revision = "ar_0004_artifacts"
down_revision = "ar_0003_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_artifact_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Artifact metadata downgrade unsupported; restore a verified backup.")
