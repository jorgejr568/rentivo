"""create api keys

Revision ID: fe0a7b31c29d
Revises: 55dc25bae00d
Create Date: 2026-07-17 10:46:18.300761

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "fe0a7b31c29d"
down_revision: Union[str, Sequence[str], None] = "55dc25bae00d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC_DATETIME = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("secret_hash", sa.BINARY(32), nullable=False),
        sa.Column("key_start", sa.String(4), nullable=False),
        sa.Column("key_end", sa.String(2), nullable=False),
        sa.Column("is_login_token", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("expires_at", UTC_DATETIME, nullable=False),
        sa.Column("last_used_at", UTC_DATETIME, nullable=True),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("revoked_at", UTC_DATETIME, nullable=True),
    )
    op.create_index("ix_api_keys_uuid", "api_keys", ["uuid"], unique=True)
    op.create_index("ix_api_keys_secret_hash", "api_keys", ["secret_hash"], unique=True)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_expires_at", "api_keys", ["expires_at"])
    op.create_index("ix_api_keys_revoked_at", "api_keys", ["revoked_at"])

    op.create_table(
        "api_key_scopes",
        sa.Column(
            "api_key_id",
            sa.Integer,
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("api_key_id", "scope"),
    )
    op.create_table(
        "api_key_resource_grants",
        sa.Column(
            "api_key_id",
            sa.Integer,
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('user', 'organization')",
            name="ck_api_key_grant_resource_type",
        ),
        sa.PrimaryKeyConstraint("api_key_id", "resource_type", "resource_id"),
    )


def downgrade() -> None:
    op.drop_table("api_key_resource_grants")
    op.drop_table("api_key_scopes")
    op.drop_table("api_keys")
