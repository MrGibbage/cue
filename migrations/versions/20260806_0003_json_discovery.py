"""json discovery

Revision ID: 20260806_0003
Revises: 20260805_0002
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0003"
down_revision = "20260805_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "collection_version_id",
            sa.Integer(),
            sa.ForeignKey("collection_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_document_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="previewed"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_snapshots_collection_id", "source_snapshots", ["collection_id"])
    op.create_index("ix_source_snapshots_collection_version_id", "source_snapshots", ["collection_version_id"])
    op.create_index("ix_source_snapshots_status", "source_snapshots", ["status"])
    op.create_table(
        "source_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id", sa.Integer(), sa.ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_position", sa.Integer(), nullable=False),
        sa.Column("supplied_rank", sa.Integer(), nullable=True),
        sa.Column("artists_json", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("canonical_key", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_source_rows_snapshot_id", "source_rows", ["snapshot_id"])
    op.create_index("ix_source_rows_canonical_key", "source_rows", ["canonical_key"])
    op.create_index("ix_source_rows_status", "source_rows", ["status"])
    op.create_table(
        "recordings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artists_json", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("canonical_key", sa.String(length=2048), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "collection_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "collection_version_id",
            sa.Integer(),
            sa.ForeignKey("collection_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "source_row_id",
            sa.Integer(),
            sa.ForeignKey("source_rows.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unresolved"),
        sa.UniqueConstraint("collection_version_id", "ordinal", name="uq_collection_entry_ordinal"),
    )
    op.create_index("ix_collection_entries_collection_version_id", "collection_entries", ["collection_version_id"])
    op.create_index("ix_collection_entries_recording_id", "collection_entries", ["recording_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_entries_recording_id", table_name="collection_entries")
    op.drop_index("ix_collection_entries_collection_version_id", table_name="collection_entries")
    op.drop_table("collection_entries")
    op.drop_table("recordings")
    op.drop_index("ix_source_rows_status", table_name="source_rows")
    op.drop_index("ix_source_rows_canonical_key", table_name="source_rows")
    op.drop_index("ix_source_rows_snapshot_id", table_name="source_rows")
    op.drop_table("source_rows")
    op.drop_index("ix_source_snapshots_status", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_collection_version_id", table_name="source_snapshots")
    op.drop_index("ix_source_snapshots_collection_id", table_name="source_snapshots")
    op.drop_table("source_snapshots")
