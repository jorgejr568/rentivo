"""merge reminders, recipient phone, and expenses heads

Revision ID: 163e815b0479
Revises: b3f1c0a2d4e5, b7e2c4a9d1f0, ca7e47b1ebdf
Create Date: 2026-06-24 17:33:06.722326

Collapses three concurrent Alembic heads that landed on main from independent
feature branches:
  - b3f1c0a2d4e5  add reminders_enabled to billings (REN-6)
  - b7e2c4a9d1f0  add phone to billing_recipients (REN-4)
  - ca7e47b1ebdf  create expenses (REN-32)

With three heads, ``alembic upgrade head`` is ambiguous and ``initialize_db()``
crashes on a fresh migrate. This is a pure chain-join: no DDL, no data change.
Downgrade re-splits the chain back into the three original heads.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "163e815b0479"
down_revision: Union[str, Sequence[str], None] = ("b3f1c0a2d4e5", "b7e2c4a9d1f0", "ca7e47b1ebdf")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
