"""add bill concurrency tokens

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-18 19:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SECOND_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=0), "mysql", "mariadb")
MICROSECOND_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql", "mariadb")


def _uses_native_fractional_datetime() -> bool:
    return op.get_bind().dialect.name != "sqlite"


def upgrade() -> None:
    op.add_column("bills", sa.Column("pdf_render_operation_id", sa.String(26), nullable=True))
    op.add_column(
        "bills",
        sa.Column("mutation_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    if _uses_native_fractional_datetime():
        op.alter_column(
            "bills",
            "status_updated_at",
            existing_type=SECOND_DATETIME,
            type_=MICROSECOND_DATETIME,
            existing_nullable=True,
        )


def downgrade() -> None:
    if _uses_native_fractional_datetime():
        op.alter_column(
            "bills",
            "status_updated_at",
            existing_type=MICROSECOND_DATETIME,
            type_=SECOND_DATETIME,
            existing_nullable=True,
        )
    op.drop_column("bills", "mutation_revision")
    op.drop_column("bills", "pdf_render_operation_id")
