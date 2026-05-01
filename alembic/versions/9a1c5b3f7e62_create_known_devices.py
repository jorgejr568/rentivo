"""create known_devices

Revision ID: 9a1c5b3f7e62
Revises: 4f9c607d1056
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "9a1c5b3f7e62"
down_revision: Union[str, Sequence[str], None] = "4f9c607d1056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "known_devices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_hash", sa.String(64), nullable=False),
        sa.Column("user_agent_snippet", sa.String(255), nullable=False, server_default=""),
        sa.Column("first_seen_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("last_seen_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "device_hash", name="uq_known_device_user_hash"),
    )
    op.create_index("ix_known_devices_user_id", "known_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_known_devices_user_id", table_name="known_devices")
    op.drop_table("known_devices")
