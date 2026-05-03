"""widen pix columns for encryption

Revision ID: 2f30089b2082
Revises: 218ffaa712e2
Create Date: 2026-05-03 16:39:45.331870

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "2f30089b2082"
down_revision: Union[str, Sequence[str], None] = "218ffaa712e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES_AND_COLUMNS = (
    ("users", "pix_merchant_name", 25),
    ("users", "pix_merchant_city", 15),
    ("organizations", "pix_merchant_name", 25),
    ("organizations", "pix_merchant_city", 15),
    ("billings", "pix_merchant_name", 25),
    ("billings", "pix_merchant_city", 15),
)


def upgrade() -> None:
    for table, column, length in _TABLES_AND_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length),
            type_=sa.Text,
            existing_nullable=False,
            existing_server_default="",
        )


def downgrade() -> None:
    for table, column, length in _TABLES_AND_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text,
            type_=sa.String(length),
            existing_nullable=False,
            existing_server_default="",
        )
