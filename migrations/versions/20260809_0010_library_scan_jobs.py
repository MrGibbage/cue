"""durable bounded library import scans

Revision ID: 20260809_0010
Revises: 20260806_0009
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260809_0010"
down_revision = "20260806_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("library_imports") as batch:
        batch.add_column(sa.Column("scanned_files", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("scanned_directories", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("current_path", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("library_imports") as batch:
        batch.drop_column("cancelled_at")
        batch.drop_column("completed_at")
        batch.drop_column("error")
        batch.drop_column("current_path")
        batch.drop_column("scanned_directories")
        batch.drop_column("scanned_files")
