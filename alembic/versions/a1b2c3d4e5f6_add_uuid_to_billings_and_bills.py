"""add uuid to billings and bills

Revision ID: a1b2c3d4e5f6
Revises: d0263f759784
Create Date: 2026-02-07
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d0263f759784"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add nullable uuid columns
    op.add_column("billings", sa.Column("uuid", sa.Text, nullable=True))
    op.add_column("bills", sa.Column("uuid", sa.Text, nullable=True))

    # Step 2: Backfill existing rows with generated UUIDs
    conn = op.get_bind()
    for row in conn.execute(sa.text("SELECT id FROM billings")):
        conn.execute(
            sa.text("UPDATE billings SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(uuid4()), "id": row[0]},
        )
    for row in conn.execute(sa.text("SELECT id FROM bills")):
        conn.execute(
            sa.text("UPDATE bills SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(uuid4()), "id": row[0]},
        )

    # Step 3: Make NOT NULL + UNIQUE
    op.alter_column("billings", "uuid", existing_type=sa.Text, nullable=False)
    op.create_unique_constraint("uq_billings_uuid", "billings", ["uuid"])
    op.alter_column("bills", "uuid", existing_type=sa.Text, nullable=False)
    op.create_unique_constraint("uq_bills_uuid", "bills", ["uuid"])


def downgrade() -> None:
    op.drop_constraint("uq_bills_uuid", "bills", type_="unique")
    op.drop_column("bills", "uuid")
    op.drop_constraint("uq_billings_uuid", "billings", type_="unique")
    op.drop_column("billings", "uuid")
