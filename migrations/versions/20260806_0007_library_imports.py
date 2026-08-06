"""existing library import previews

Revision ID: 20260806_0007
Revises: 20260806_0006
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0007"
down_revision = "20260806_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("published_assets") as batch:
        batch.alter_column("candidate_asset_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("recording_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_published_assets_recording_id", "recordings", ["recording_id"], ["id"], ondelete="RESTRICT"
        )
    op.create_index("ix_published_assets_recording_id", "published_assets", ["recording_id"])
    op.execute(
        "UPDATE published_assets SET recording_id = "
        "(SELECT recording_id FROM candidate_assets WHERE candidate_assets.id = published_assets.candidate_asset_id)"
    )
    op.create_table(
        "library_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="previewed"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_library_imports_owner_id", "library_imports", ["owner_id"])
    op.create_index("ix_library_imports_status", "library_imports", ["status"])
    op.create_table(
        "library_import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "library_import_id",
            sa.Integer(),
            sa.ForeignKey("library_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(length=2048), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("container", sa.String(length=16), nullable=False),
        sa.Column("artists_json", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("descriptor", sa.String(length=1024), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("canonical_key", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "published_asset_id",
            sa.Integer(),
            sa.ForeignKey("published_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("library_import_id", "relative_path", name="uq_library_import_path"),
    )
    op.create_index("ix_library_import_rows_library_import_id", "library_import_rows", ["library_import_id"])
    op.create_index("ix_library_import_rows_canonical_key", "library_import_rows", ["canonical_key"])
    op.create_index("ix_library_import_rows_status", "library_import_rows", ["status"])


def downgrade() -> None:
    op.drop_index("ix_library_import_rows_status", table_name="library_import_rows")
    op.drop_index("ix_library_import_rows_canonical_key", table_name="library_import_rows")
    op.drop_index("ix_library_import_rows_library_import_id", table_name="library_import_rows")
    op.drop_table("library_import_rows")
    op.drop_index("ix_library_imports_status", table_name="library_imports")
    op.drop_index("ix_library_imports_owner_id", table_name="library_imports")
    op.drop_table("library_imports")
    op.drop_index("ix_published_assets_recording_id", table_name="published_assets")
    with op.batch_alter_table("published_assets") as batch:
        batch.drop_constraint("fk_published_assets_recording_id", type_="foreignkey")
        batch.drop_column("recording_id")
        batch.alter_column("candidate_asset_id", existing_type=sa.Integer(), nullable=False)
