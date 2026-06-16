"""add recibo_pdf_path to bills

Revision ID: 08c21e96caa6
Revises: 51f6a33c87b3
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "08c21e96caa6"
down_revision: Union[str, Sequence[str], None] = "51f6a33c87b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("recibo_pdf_path", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "recibo_pdf_path")
