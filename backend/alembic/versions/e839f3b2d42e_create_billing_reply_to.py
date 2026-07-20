"""create billing_reply_to

Revision ID: e839f3b2d42e
Revises: 3402a10ec6e6
Create Date: 2026-06-12 20:16:30.321895

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e839f3b2d42e"
down_revision: Union[str, Sequence[str], None] = "3402a10ec6e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_reply_to",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("billing_id", sa.Integer, sa.ForeignKey("billings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_billing_reply_to_billing_id", "billing_reply_to", ["billing_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_reply_to_billing_id", table_name="billing_reply_to")
    op.drop_table("billing_reply_to")
