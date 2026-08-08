"""add jobs retention index

Revision ID: 69034275ea88
Revises: 6f876ec79535
Create Date: 2026-07-31 22:37:35.912273

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "69034275ea88"
down_revision: Union[str, Sequence[str], None] = "6f876ec79535"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supports the retention purge's `status IN (...) AND updated_at <= :cutoff`
    # scan. `updated_at` is set by both mark_succeeded and mark_failed, so one
    # index covers both terminal states without needing succeeded_at/failed_at.
    op.create_index("idx_jobs_retention", "jobs", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_jobs_retention", table_name="jobs")
