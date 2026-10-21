"""Add exact managed DID mappings."""

import sqlalchemy as sa
from alembic import op

revision = "0005_phone_numbers"
down_revision = "0004_call_destination"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_numbers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "partner_app_id",
            sa.String(36),
            sa.ForeignKey("partner_apps.id"),
            nullable=False,
        ),
        sa.Column("number", sa.String(33), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pbx_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("number", name="uq_phone_numbers_number"),
    )
    op.create_index(
        "ix_phone_numbers_organization_id", "phone_numbers", ["organization_id"]
    )
    op.create_index(
        "ix_phone_numbers_partner_app_id", "phone_numbers", ["partner_app_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_phone_numbers_partner_app_id", table_name="phone_numbers")
    op.drop_index("ix_phone_numbers_organization_id", table_name="phone_numbers")
    op.drop_table("phone_numbers")
