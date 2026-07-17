"""drop users.username

Revision ID: 47d044b7cc72
Revises: c70fabec2b76
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "47d044b7cc72"
down_revision: Union[str, Sequence[str], None] = "c70fabec2b76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique index that was created on `username` when the table was first built.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for ix in inspector.get_indexes("users"):
        if ix.get("unique") and ix.get("column_names") == ["username"]:
            op.drop_index(ix["name"], table_name="users")
    op.drop_column("users", "username")


def downgrade() -> None:
    op.add_column("users", sa.Column("username", sa.Text, nullable=False, server_default=""))
    op.create_unique_constraint("uq_users_username", "users", ["username"])
