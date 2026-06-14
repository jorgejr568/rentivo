"""add readjustment to billings

Revision ID: 0aad121e50b3
Revises: e839f3b2d42e
Create Date: 2026-06-14 20:35:27.444325

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0aad121e50b3"
down_revision: Union[str, Sequence[str], None] = "e839f3b2d42e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("billings", sa.Column("readjustment_index", sa.Text, nullable=True))
    op.add_column("billings", sa.Column("readjustment_month", sa.Integer, nullable=True))
    op.add_column("billings", sa.Column("last_readjustment_date", sa.Text, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("billings", "last_readjustment_date")
    op.drop_column("billings", "readjustment_month")
    op.drop_column("billings", "readjustment_index")
