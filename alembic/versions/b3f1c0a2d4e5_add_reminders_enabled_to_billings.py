"""add reminders_enabled to billings

Per-template landlord toggle for automated payment reminders / dunning
(REN-6). Defaults on (server_default "1") so existing templates keep
reminding late-payers after the migration; a landlord can opt a template
out without deleting its reminder copy.

Revision ID: b3f1c0a2d4e5
Revises: 51f6a33c87b3
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b3f1c0a2d4e5"
down_revision: Union[str, Sequence[str], None] = "51f6a33c87b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billings",
        sa.Column("reminders_enabled", sa.Boolean, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("billings", "reminders_enabled")
