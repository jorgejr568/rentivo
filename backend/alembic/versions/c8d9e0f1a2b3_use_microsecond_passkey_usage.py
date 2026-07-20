"""use microsecond passkey usage timestamps

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-17 22:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SECOND_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=0), "mysql")
MICROSECOND_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def _uses_native_fractional_datetime() -> bool:
    return op.get_bind().dialect.name != "sqlite"


def upgrade() -> None:
    if not _uses_native_fractional_datetime():
        return
    op.alter_column(
        "user_passkeys",
        "last_used_at",
        existing_type=SECOND_DATETIME,
        type_=MICROSECOND_DATETIME,
        existing_nullable=True,
    )


def downgrade() -> None:
    if not _uses_native_fractional_datetime():
        return
    op.alter_column(
        "user_passkeys",
        "last_used_at",
        existing_type=MICROSECOND_DATETIME,
        type_=SECOND_DATETIME,
        existing_nullable=True,
    )
