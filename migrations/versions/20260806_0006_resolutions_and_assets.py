"""collection resolutions and published assets

Revision ID: 20260806_0006
Revises: 20260806_0005
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0006"
down_revision = "20260806_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "collection_entry_id",
            sa.Integer(),
            sa.ForeignKey("collection_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_asset_id", sa.Integer(), sa.ForeignKey("candidate_assets.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unresolved"),
        sa.Column("selected_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("collection_entry_id", name="uq_resolution_collection_entry"),
    )
    op.create_index("ix_collection_resolutions_collection_entry_id", "collection_resolutions", ["collection_entry_id"])
    op.create_index("ix_collection_resolutions_candidate_asset_id", "collection_resolutions", ["candidate_asset_id"])
    op.create_index("ix_collection_resolutions_status", "collection_resolutions", ["status"])
    op.create_table(
        "published_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "candidate_asset_id",
            sa.Integer(),
            sa.ForeignKey("candidate_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(length=2048), nullable=False),
        sa.Column("container", sa.String(length=16), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_asset_id", name="uq_published_candidate"),
        sa.UniqueConstraint("relative_path", name="uq_published_relative_path"),
    )
    op.create_index("ix_published_assets_candidate_asset_id", "published_assets", ["candidate_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_published_assets_candidate_asset_id", table_name="published_assets")
    op.drop_table("published_assets")
    op.drop_index("ix_collection_resolutions_status", table_name="collection_resolutions")
    op.drop_index("ix_collection_resolutions_candidate_asset_id", table_name="collection_resolutions")
    op.drop_index("ix_collection_resolutions_collection_entry_id", table_name="collection_resolutions")
    op.drop_table("collection_resolutions")
