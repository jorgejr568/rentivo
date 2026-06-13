"""create communication_templates

Revision ID: f3035fd3adb9
Revises: ec2b3ffba99f
Create Date: 2026-06-12 16:26:50.558269

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3035fd3adb9"
down_revision: Union[str, Sequence[str], None] = "ec2b3ffba99f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(26), nullable=False, unique=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("comm_type", sa.String(32), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body_markdown", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_unique_constraint(
        "uq_comm_template_owner", "communication_templates", ["owner_type", "owner_id", "comm_type"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_comm_template_owner", "communication_templates", type_="unique")
    op.drop_table("communication_templates")
