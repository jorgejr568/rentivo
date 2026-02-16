"""add deleted_at to bills and fix uuid column type

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-08
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("deleted_at", sa.DateTime, nullable=True))
    op.alter_column("billings", "uuid", existing_type=sa.Text, type_=sa.String(36))
    op.alter_column("bills", "uuid", existing_type=sa.Text, type_=sa.String(36))


def downgrade() -> None:
    op.drop_column("bills", "deleted_at")
    op.alter_column("bills", "uuid", existing_type=sa.String(36), type_=sa.Text)
    op.alter_column("billings", "uuid", existing_type=sa.String(36), type_=sa.Text)
