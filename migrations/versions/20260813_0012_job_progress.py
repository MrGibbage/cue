"""durable job progress

Revision ID: 20260813_0012
Revises: 20260812_0011
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0012"
down_revision = "20260812_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("progress_total", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("progress_message", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("progress_message")
        batch.drop_column("progress_total")
        batch.drop_column("progress_current")
