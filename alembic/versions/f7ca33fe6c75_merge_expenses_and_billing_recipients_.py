"""merge recibo-pdf-path and expenses heads

Revision ID: f7ca33fe6c75
Revises: 08c21e96caa6, ca7e47b1ebdf
Create Date: 2026-06-24 17:43:42.650516

Merge-only migration (REN-51): collapses the two divergent Alembic heads on
main into one so the host's `alembic upgrade head` is unambiguous and
`initialize_db()` does not crash on a fresh migrate.

  - 08c21e96caa6  add recibo_pdf_path to bills
  - ca7e47b1ebdf  create expenses (#108)

Both descend from e839f3b2d42e. There is intentionally NO DDL here: a merge
node only joins lineage. Rollback is `alembic downgrade`, which simply removes
this merge node and restores the two heads (also no DDL).

History note: REN-51 was originally written against THREE heads
(b3f1c0a2d4e5 reminders, b7e2c4a9d1f0 billing-recipient phone, ca7e47b1ebdf
expenses). Both feature branches were then reverted on main — reminders in
#123 and the WhatsApp/billing-recipient-phone work in #124 — which deleted
the b3f1c0a2d4e5 and b7e2c4a9d1f0 migrations. Reverting b7e2c4a9d1f0 re-exposed
its parent 08c21e96caa6 as a head. The real divergence on current main is
therefore the 2-way (08c21e96caa6, ca7e47b1ebdf), reconciled here.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f7ca33fe6c75"
down_revision: Union[str, Sequence[str], None] = ("08c21e96caa6", "ca7e47b1ebdf")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
