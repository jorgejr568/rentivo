"""add paid_at to bills

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-08
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("paid_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "paid_at")
