"""email unique and required

Revision ID: c70fabec2b76
Revises: 71fda335fac0
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c70fabec2b76"
down_revision: Union[str, Sequence[str], None] = "71fda335fac0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Backfill any empty/NULL emails using the username so the unique index can be added.
    bind.execute(
        sa.text(
            "UPDATE users SET email = CONCAT(username, '@migrated.local') "
            "WHERE email IS NULL OR email = ''"
        )
    )
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False, server_default=None)
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False, server_default="")
