"""Add durable admission identities and common job configuration metadata."""

from alembic import op

from agent_rewind.migrations.admission_schema import create_admission_schema

revision = "ar_0006_admission"
down_revision = "ar_0005_run_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_admission_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Admission downgrade unsupported; restore a verified backup.")
