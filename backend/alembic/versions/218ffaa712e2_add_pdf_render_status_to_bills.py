"""add pdf_render_status to bills

Revision ID: 218ffaa712e2
Revises: d74d94c5ff3c
Create Date: 2026-05-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "218ffaa712e2"
down_revision: Union[str, Sequence[str], None] = "d74d94c5ff3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("pdf_render_status", sa.String(16), nullable=True),
    )
    op.create_index(
        "idx_bills_pdf_render_status",
        "bills",
        ["billing_id", "pdf_render_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_bills_pdf_render_status", table_name="bills")
    op.drop_column("bills", "pdf_render_status")
