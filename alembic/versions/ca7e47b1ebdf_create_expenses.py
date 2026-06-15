"""create expenses

Revision ID: ca7e47b1ebdf
Revises: e839f3b2d42e
Create Date: 2026-06-15 10:20:02.502060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca7e47b1ebdf'
down_revision: Union[str, Sequence[str], None] = 'e839f3b2d42e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column(
            "billing_id",
            sa.Integer,
            sa.ForeignKey("billings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("category", sa.String(32), nullable=False, server_default="outros"),
        sa.Column("incurred_on", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_expenses_billing_id", "expenses", ["billing_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_expenses_billing_id", table_name="expenses")
    op.drop_table("expenses")
