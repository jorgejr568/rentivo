"""add_bill_status

Revision ID: d1e0a883d14a
Revises: 268d02b96390
Create Date: 2026-02-28 09:42:44.004205

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e0a883d14a"
down_revision: Union[str, Sequence[str], None] = "268d02b96390"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("status", sa.String(20), nullable=False, server_default="draft"))
    op.add_column("bills", sa.Column("status_updated_at", sa.DateTime, nullable=True))

    # Backfill: bills with paid_at → status='paid', status_updated_at=paid_at
    op.execute("UPDATE bills SET status = 'paid', status_updated_at = paid_at WHERE paid_at IS NOT NULL")
    # Backfill: unpaid bills → status='published', status_updated_at=created_at
    op.execute("UPDATE bills SET status = 'published', status_updated_at = created_at WHERE paid_at IS NULL")

    op.drop_column("bills", "paid_at")
    op.create_index("ix_bills_status", "bills", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bills_status", table_name="bills")
    op.add_column("bills", sa.Column("paid_at", sa.DateTime, nullable=True))
    # Restore paid_at from status
    op.execute("UPDATE bills SET paid_at = status_updated_at WHERE status = 'paid'")
    op.drop_column("bills", "status_updated_at")
    op.drop_column("bills", "status")
