"""Add Partner App logical deletion tombstones."""

import sqlalchemy as sa
from alembic import op

revision = "0007_partner_app_logical_delete"
down_revision = "0006_outbound_phone_apps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_apps",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "encrypted_secret")
    op.drop_column("partner_apps", "deleted_at")
