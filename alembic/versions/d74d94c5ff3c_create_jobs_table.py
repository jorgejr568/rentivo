"""create jobs

Revision ID: d74d94c5ff3c
Revises: 9a1c5b3f7e62
Create Date: 2026-05-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "d74d94c5ff3c"
down_revision: Union[str, Sequence[str], None] = "9a1c5b3f7e62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ulid", sa.String(26), nullable=False, unique=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("run_after", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("claimed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("claimed_by", sa.String(64), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("succeeded_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("failed_at", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.create_index("idx_jobs_claim", "jobs", ["status", "run_after", "id"])
    op.create_index("idx_jobs_type_status", "jobs", ["job_type", "status"])


def downgrade() -> None:
    op.drop_index("idx_jobs_type_status", table_name="jobs")
    op.drop_index("idx_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
