"""create auth rate limits

Revision ID: b7c8d9e0f1a2
Revises: a15a69fdc2d5
Create Date: 2026-07-17 17:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a15a69fdc2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("identity_hash", sa.BINARY(32), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("window_started_at", UTC_DATETIME, nullable=False),
        sa.Column("expires_at", UTC_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("action", "identity_hash"),
    )
    op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
