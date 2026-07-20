"""create audit_logs

Revision ID: f7b8c9d0e1f2
Revises: e4f5a6b7c8d9
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.Integer, nullable=True),
        sa.Column(
            "actor_username",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column(
            "entity_type",
            sa.String(50),
            nullable=False,
            server_default="",
        ),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column(
            "entity_uuid",
            sa.String(26),
            nullable=False,
            server_default="",
        ),
        sa.Column("previous_state", sa.Text, nullable=True),
        sa.Column("new_state", sa.Text, nullable=True),
        sa.Column(
            "metadata",
            sa.Text,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_table("audit_logs")
