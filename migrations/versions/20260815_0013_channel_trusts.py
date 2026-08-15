"""owner-confirmed candidate channel authority

Revision ID: 20260815_0013
Revises: 20260813_0012
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op


revision = "20260815_0013"
down_revision = "20260813_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_trusts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="youtube"),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("channel_name", sa.String(length=512), nullable=True),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "provider", "channel_id", name="uq_channel_trust_owner_provider_channel"),
    )
    op.create_index("ix_channel_trusts_owner_id", "channel_trusts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_trusts_owner_id", table_name="channel_trusts")
    op.drop_table("channel_trusts")
