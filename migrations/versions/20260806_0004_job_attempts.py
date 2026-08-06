"""job attempts

Revision ID: 20260806_0004
Revises: 20260806_0003
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_0004"
down_revision = "20260806_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
        batch.add_column(sa.Column("claimed_by", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_job_attempt_number"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_attempts_job_id", table_name="job_attempts")
    op.drop_table("job_attempts")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("last_error")
        batch.drop_column("claimed_at")
        batch.drop_column("claimed_by")
        batch.drop_column("max_attempts")
        batch.drop_column("attempt_count")
