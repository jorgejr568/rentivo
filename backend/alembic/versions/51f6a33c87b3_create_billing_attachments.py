"""create billing_attachments

Revision ID: 51f6a33c87b3
Revises: e839f3b2d42e
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "51f6a33c87b3"
down_revision: Union[str, Sequence[str], None] = "e839f3b2d42e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_attachments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column(
            "billing_id",
            sa.Integer,
            sa.ForeignKey("billings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
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
    op.create_index("ix_billing_attachments_billing_id", "billing_attachments", ["billing_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_attachments_billing_id", table_name="billing_attachments")
    op.drop_table("billing_attachments")
