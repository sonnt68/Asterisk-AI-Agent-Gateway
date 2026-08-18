"""Add destination policy and globally unambiguous Asterisk route slug."""

import sqlalchemy as sa
from alembic import op

revision = "0002_destination_policy"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_apps",
        sa.Column("allowed_destinations", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_partner_apps_agent_slug", "partner_apps", ["agent_slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_partner_apps_agent_slug", table_name="partner_apps")
    op.drop_column("partner_apps", "allowed_destinations")
