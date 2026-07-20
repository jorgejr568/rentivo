"""create billing_recipients

Revision ID: ec2b3ffba99f
Revises: ed5a99b2fe74
Create Date: 2026-06-12 16:15:23.067830

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec2b3ffba99f"
down_revision: Union[str, Sequence[str], None] = "ed5a99b2fe74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_recipients",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("billing_id", sa.Integer, sa.ForeignKey("billings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_billing_recipients_billing_id", "billing_recipients", ["billing_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_recipients_billing_id", table_name="billing_recipients")
    op.drop_table("billing_recipients")
