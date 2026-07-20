"""add public UUID to billing items

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-18 23:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from ulid import ULID

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE_NAME = "uq_billing_items_uuid"


def upgrade() -> None:
    with op.batch_alter_table("billing_items") as batch_op:
        batch_op.add_column(sa.Column("uuid", sa.String(length=26), nullable=True))

    connection = op.get_bind()
    item_ids = connection.execute(sa.text("SELECT id FROM billing_items ORDER BY id")).scalars().all()
    for item_id in item_ids:
        connection.execute(
            sa.text("UPDATE billing_items SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(ULID()), "id": item_id},
        )

    with op.batch_alter_table("billing_items") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(length=26), nullable=False)
        batch_op.create_unique_constraint(_UNIQUE_NAME, ["uuid"])


def downgrade() -> None:
    with op.batch_alter_table("billing_items") as batch_op:
        batch_op.drop_constraint(_UNIQUE_NAME, type_="unique")
        batch_op.drop_column("uuid")
