"""create communications

Revision ID: 3402a10ec6e6
Revises: f3035fd3adb9
Create Date: 2026-06-12 16:26:54.269849

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3402a10ec6e6"
down_revision: Union[str, Sequence[str], None] = "f3035fd3adb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comm_type", sa.String(32), nullable=False),
        sa.Column("recipient_name", sa.Text, nullable=False),
        sa.Column("recipient_email", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body_markdown", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("job_ulid", sa.String(26), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("sent_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_communications_bill_id", "communications", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_communications_bill_id", table_name="communications")
    op.drop_table("communications")
