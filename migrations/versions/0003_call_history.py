"""Add durable call history and normalized status signals."""

import sqlalchemy as sa
from alembic import op

revision = "0003_call_history"
down_revision = "0002_destination_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_records",
        sa.Column("call_id", sa.String(36), primary_key=True),
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
            nullable=True,
        ),
        sa.Column("agent_slug", sa.String(80), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(80), nullable=True),
        sa.Column("hangup_cause", sa.Integer(), nullable=True),
        sa.Column("dial_status", sa.String(32), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("talk_seconds", sa.Integer(), nullable=True),
        sa.Column("history_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_call_records_organization_id", "call_records", ["organization_id"]
    )
    op.create_index(
        "ix_call_records_partner_app_id", "call_records", ["partner_app_id"]
    )
    op.create_index("ix_call_records_terminal", "call_records", ["terminal"])
    op.create_index("ix_call_records_created_at", "call_records", ["created_at"])
    op.create_index(
        "ix_call_records_org_app_created_call",
        "call_records",
        ["organization_id", "partner_app_id", "created_at", "call_id"],
    )
    op.create_index(
        "ix_call_records_org_created_call",
        "call_records",
        ["organization_id", "created_at", "call_id"],
    )

    op.create_table(
        "call_signals",
        sa.Column(
            "call_id",
            sa.String(36),
            sa.ForeignKey("call_records.call_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(80), nullable=True),
        sa.Column("hangup_cause", sa.Integer(), nullable=True),
        sa.Column("dial_status", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", "sequence", name="uq_call_signals_call_sequence"),
    )
    op.create_index("ix_call_signals_updated_at", "call_signals", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_call_signals_updated_at", table_name="call_signals")
    op.drop_table("call_signals")
    for index_name in (
        "ix_call_records_org_created_call",
        "ix_call_records_org_app_created_call",
        "ix_call_records_created_at",
        "ix_call_records_terminal",
        "ix_call_records_partner_app_id",
        "ix_call_records_organization_id",
    ):
        op.drop_index(index_name, table_name="call_records")
    op.drop_table("call_records")
