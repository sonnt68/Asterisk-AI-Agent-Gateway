"""Add shared outbound caller-number assignments."""

import sqlalchemy as sa
from alembic import op

revision = "0006_outbound_phone_apps"
down_revision = "0005_phone_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_number_outbound_apps",
        sa.Column(
            "phone_number_id",
            sa.String(36),
            sa.ForeignKey("phone_numbers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "partner_app_id",
            sa.String(36),
            sa.ForeignKey("partner_apps.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_phone_number_outbound_apps_partner_app_id",
        "phone_number_outbound_apps",
        ["partner_app_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phone_number_outbound_apps_partner_app_id",
        table_name="phone_number_outbound_apps",
    )
    op.drop_table("phone_number_outbound_apps")
