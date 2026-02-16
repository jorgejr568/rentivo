"""create receipts

Revision ID: f5a6b7c8d9e0
Revises: f7b8c9d0e1f2
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "f7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column(
            "bill_id",
            sa.Integer,
            sa.ForeignKey("bills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text, nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_receipts_bill_id", "receipts", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_receipts_bill_id", table_name="receipts")
    op.drop_table("receipts")
