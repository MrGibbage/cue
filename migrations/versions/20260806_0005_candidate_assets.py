"""candidate assets

Revision ID: 20260806_0005
Revises: 20260806_0004
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0005"
down_revision = "20260806_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("uploader", sa.String(length=512), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("classifications_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_id", name="uq_candidate_provider_asset"),
    )
    op.create_index("ix_candidate_assets_recording_id", "candidate_assets", ["recording_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_assets_recording_id", table_name="candidate_assets")
    op.drop_table("candidate_assets")
