"""Dormant failure evidence; only the explicit owned installation may advance."""

from alembic import op

from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.failure_service import _require_failure_upgrade

revision = "ar_0008_failure_evidence"
down_revision = "ar_0007_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    work = _require_failure_upgrade(connection)
    create_failure_schema(connection)
    if _require_failure_upgrade(connection) is not work:
        raise RuntimeError("Failure migration scope changed")


def downgrade() -> None:
    raise RuntimeError("Failure evidence downgrade requires a verified restore")
