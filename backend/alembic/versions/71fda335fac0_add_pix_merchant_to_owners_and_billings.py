"""add pix merchant fields to users, organizations, and billings

Revision ID: 71fda335fac0
Revises: 7b13be8a199e
Create Date: 2026-04-19
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "71fda335fac0"
down_revision: Union[str, Sequence[str], None] = "7b13be8a199e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pix_key", sa.Text, nullable=False, server_default=""))
    op.add_column("users", sa.Column("pix_merchant_name", sa.String(25), nullable=False, server_default=""))
    op.add_column("users", sa.Column("pix_merchant_city", sa.String(15), nullable=False, server_default=""))

    op.add_column("organizations", sa.Column("pix_key", sa.Text, nullable=False, server_default=""))
    op.add_column("organizations", sa.Column("pix_merchant_name", sa.String(25), nullable=False, server_default=""))
    op.add_column("organizations", sa.Column("pix_merchant_city", sa.String(15), nullable=False, server_default=""))

    op.add_column("billings", sa.Column("pix_merchant_name", sa.String(25), nullable=False, server_default=""))
    op.add_column("billings", sa.Column("pix_merchant_city", sa.String(15), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("billings", "pix_merchant_city")
    op.drop_column("billings", "pix_merchant_name")

    op.drop_column("organizations", "pix_merchant_city")
    op.drop_column("organizations", "pix_merchant_name")
    op.drop_column("organizations", "pix_key")

    op.drop_column("users", "pix_merchant_city")
    op.drop_column("users", "pix_merchant_name")
    op.drop_column("users", "pix_key")
