"""initial schema

Revision ID: e0a39c4eb167
Revises:
Create Date: 2026-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e0a39c4eb167"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "billing_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("billing_id", sa.Integer, sa.ForeignKey("billings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("item_type", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "bills",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("billing_id", sa.Integer, sa.ForeignKey("billings.id"), nullable=False),
        sa.Column("reference_month", sa.Text, nullable=False),
        sa.Column("total_amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pdf_path", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bill_line_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("item_type", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("bill_line_items")
    op.drop_table("bills")
    op.drop_table("billing_items")
    op.drop_table("billings")
