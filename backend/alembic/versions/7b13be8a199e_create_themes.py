"""create_themes

Revision ID: 7b13be8a199e
Revises: d1e0a883d14a
Create Date: 2026-02-28 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b13be8a199e"
down_revision: Union[str, Sequence[str], None] = "d1e0a883d14a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "themes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, server_default=""),
        sa.Column("header_font", sa.String(50), nullable=False, server_default="Montserrat"),
        sa.Column("text_font", sa.String(50), nullable=False, server_default="Montserrat"),
        sa.Column("primary_color", sa.String(7), nullable=False, server_default="#8A4C94"),
        sa.Column("primary_light", sa.String(7), nullable=False, server_default="#EEE4F1"),
        sa.Column("secondary", sa.String(7), nullable=False, server_default="#6EAFAE"),
        sa.Column("secondary_dark", sa.String(7), nullable=False, server_default="#357B7C"),
        sa.Column("text_color", sa.String(7), nullable=False, server_default="#282830"),
        sa.Column("text_contrast", sa.String(7), nullable=False, server_default="#FFFFFF"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_themes_owner", "themes", ["owner_type", "owner_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_themes_owner", table_name="themes")
    op.drop_table("themes")
