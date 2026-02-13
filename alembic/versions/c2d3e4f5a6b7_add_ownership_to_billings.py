"""add ownership to billings

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-02-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billings",
        sa.Column("owner_type", sa.String(12), nullable=False, server_default="user"),
    )
    op.add_column(
        "billings",
        sa.Column("owner_id", sa.Integer, nullable=False, server_default="0"),
    )

    # Backfill: assign all existing billings to the first user
    conn = op.get_bind()
    first_user = conn.execute(
        sa.text("SELECT id FROM users ORDER BY id LIMIT 1")
    ).fetchone()
    if first_user:
        conn.execute(
            sa.text("UPDATE billings SET owner_id = :uid WHERE owner_id = 0"),
            {"uid": first_user[0]},
        )

    # Remove server defaults (they were only for migration backfill)
    op.alter_column("billings", "owner_type", server_default=None)
    op.alter_column("billings", "owner_id", server_default=None)

    op.create_index("ix_billings_owner", "billings", ["owner_type", "owner_id"])


def downgrade() -> None:
    op.drop_index("ix_billings_owner", table_name="billings")
    op.drop_column("billings", "owner_id")
    op.drop_column("billings", "owner_type")
