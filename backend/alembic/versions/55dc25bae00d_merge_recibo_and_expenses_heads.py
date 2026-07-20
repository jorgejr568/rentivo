"""merge recibo and expenses heads

Revision ID: 55dc25bae00d
Revises: 08c21e96caa6, ca7e47b1ebdf
Create Date: 2026-06-24 18:36:17.212434

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "55dc25bae00d"
down_revision: Union[str, Sequence[str], None] = ("08c21e96caa6", "ca7e47b1ebdf")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
