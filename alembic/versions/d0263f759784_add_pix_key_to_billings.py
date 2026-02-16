"""add pix_key to billings

Revision ID: d0263f759784
Revises: e0a39c4eb167
Create Date: 2026-02-07
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d0263f759784"
down_revision: Union[str, Sequence[str], None] = "e0a39c4eb167"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("billings", sa.Column("pix_key", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("billings", "pix_key")
