"""dashboard settings

Revision ID: 20260806_0009
Revises: 20260806_0008
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0009"
down_revision = "20260806_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("application_settings")
