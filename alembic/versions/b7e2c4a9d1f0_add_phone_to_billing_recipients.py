"""add phone to billing_recipients

Revision ID: b7e2c4a9d1f0
Revises: 51f6a33c87b3
Create Date: 2026-06-24 19:30:00.000000

Adds an optional, encrypted ``phone`` column to ``billing_recipients`` so a
landlord can send an invoice over WhatsApp via a ``wa.me`` deep link (REN-4).
Nullable because phone is optional — name + email remain the only required
recipient fields. Stored as Text (like ``name``/``email``) to hold the
ciphertext from the field-level PII encryption backend.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2c4a9d1f0"
down_revision: Union[str, Sequence[str], None] = "51f6a33c87b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("billing_recipients", sa.Column("phone", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("billing_recipients", "phone")
