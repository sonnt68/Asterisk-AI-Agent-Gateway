"""Add destination metadata to durable call records."""

import sqlalchemy as sa
from alembic import op

revision = "0004_call_destination"
down_revision = "0003_call_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "call_records", sa.Column("called_number", sa.String(80), nullable=True)
    )
    op.add_column(
        "call_records", sa.Column("routing_context", sa.String(80), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("call_records", "routing_context")
    op.drop_column("call_records", "called_number")
