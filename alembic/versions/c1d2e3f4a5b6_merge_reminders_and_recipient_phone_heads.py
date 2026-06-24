"""merge reminders + billing-recipient-phone heads

Two migration heads diverged when REN-6 (payment reminders, head
``b3f1c0a2d4e5``, branched from ``51f6a33c87b3``) merged alongside REN-4
(WhatsApp delivery, head ``b7e2c4a9d1f0``). ``alembic upgrade head`` is
ambiguous with multiple heads, which breaks every process that calls
``initialize_db()`` (web, worker, and the payment-reminders sweep) on a
fresh migrate. This is a no-op merge revision that reunites the two heads
into a single linear head; it adds no schema or data changes.

Revision ID: c1d2e3f4a5b6
Revises: b3f1c0a2d4e5, b7e2c4a9d1f0
Create Date: 2026-06-24
"""

from typing import Sequence, Union

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = ("b3f1c0a2d4e5", "b7e2c4a9d1f0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
