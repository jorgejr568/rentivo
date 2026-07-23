"""relax user fks for account deletion

Revision ID: 6f876ec79535
Revises: e0f1a2b3c4d5
Create Date: 2026-07-23 20:13:38.466645

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f876ec79535"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# InnoDB auto-generated foreign-key names on MariaDB (verified against
# information_schema): the original CREATE TABLE statements defined these
# constraints inline without an explicit name.
FK_ORG_CREATED_BY = "organizations_ibfk_1"
FK_INVITES_INVITED_BY = "invites_ibfk_3"


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint(FK_ORG_CREATED_BY, type_="foreignkey")
        batch.alter_column("created_by", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key(FK_ORG_CREATED_BY, "users", ["created_by"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("invites") as batch:
        batch.drop_constraint(FK_INVITES_INVITED_BY, type_="foreignkey")
        batch.create_foreign_key(
            FK_INVITES_INVITED_BY,
            "users",
            ["invited_by_user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("invites") as batch:
        batch.drop_constraint(FK_INVITES_INVITED_BY, type_="foreignkey")
        batch.create_foreign_key(FK_INVITES_INVITED_BY, "users", ["invited_by_user_id"], ["id"])
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint(FK_ORG_CREATED_BY, type_="foreignkey")
        batch.alter_column("created_by", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(FK_ORG_CREATED_BY, "users", ["created_by"], ["id"])
