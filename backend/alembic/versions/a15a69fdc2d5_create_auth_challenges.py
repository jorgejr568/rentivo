"""create auth challenges

Revision ID: a15a69fdc2d5
Revises: fe0a7b31c29d
Create Date: 2026-07-17 13:34:37.535015

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a15a69fdc2d5"
down_revision: Union[str, Sequence[str], None] = "fe0a7b31c29d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UTC_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("nonce_hash", sa.BINARY(32), nullable=False),
        sa.Column("allowed_methods", sa.JSON, nullable=False),
        sa.Column("webauthn_challenge", sa.LargeBinary, nullable=True),
        sa.Column("failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("expires_at", UTC_DATETIME, nullable=False),
        sa.Column("consumed_at", UTC_DATETIME, nullable=True),
    )
    op.create_index("ix_auth_challenges_uuid", "auth_challenges", ["uuid"], unique=True)
    op.create_index("ix_auth_challenges_user_id", "auth_challenges", ["user_id"])
    op.create_index("ix_auth_challenges_expires_at", "auth_challenges", ["expires_at"])
    op.create_index("ix_auth_challenges_consumed_at", "auth_challenges", ["consumed_at"])


def downgrade() -> None:
    op.drop_table("auth_challenges")
