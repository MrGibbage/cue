"""collection candidate policies and stable uploader identifiers

Revision ID: 20260812_0011
Revises: 20260809_0010
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260812_0011"
down_revision = "20260809_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collections") as batch:
        batch.add_column(sa.Column("candidate_policy_json", sa.Text(), nullable=False, server_default="{}"))
    with op.batch_alter_table("candidate_assets") as batch:
        batch.add_column(sa.Column("uploader_id", sa.String(length=255), nullable=True))
        batch.create_index("ix_candidate_assets_uploader_id", ["uploader_id"])


def downgrade() -> None:
    with op.batch_alter_table("candidate_assets") as batch:
        batch.drop_index("ix_candidate_assets_uploader_id")
        batch.drop_column("uploader_id")
    with op.batch_alter_table("collections") as batch:
        batch.drop_column("candidate_policy_json")
