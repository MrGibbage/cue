"""foundation metadata

Revision ID: 20260805_0001
Revises:
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "20260805_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_metadata",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.String(length=1024), nullable=False),
    )
    op.execute("INSERT INTO application_metadata (key, value) VALUES ('schema_version', '1')")


def downgrade() -> None:
    op.drop_table("application_metadata")
