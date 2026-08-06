"""playlist export manifests

Revision ID: 20260806_0008
Revises: 20260806_0007
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0008"
down_revision = "20260806_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playlist_exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="previewed"),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("m3u8_relative_path", sa.String(length=2048), nullable=True),
        sa.Column("report_relative_path", sa.String(length=2048), nullable=True),
        sa.Column("digest", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_playlist_exports_owner_id", "playlist_exports", ["owner_id"])
    op.create_index("ix_playlist_exports_collection_id", "playlist_exports", ["collection_id"])
    op.create_index("ix_playlist_exports_status", "playlist_exports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_playlist_exports_status", table_name="playlist_exports")
    op.drop_index("ix_playlist_exports_collection_id", table_name="playlist_exports")
    op.drop_index("ix_playlist_exports_owner_id", table_name="playlist_exports")
    op.drop_table("playlist_exports")
