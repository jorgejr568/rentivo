"""widen pix columns for encryption

Revision ID: 2f30089b2082
Revises: 218ffaa712e2
Create Date: 2026-05-03 16:39:45.331870

Widens users/organizations/billings.pix_merchant_name (was VARCHAR(25)) and
.pix_merchant_city (was VARCHAR(15)) to TEXT to fit ciphertext written by the
encryption backend: KMSBackend produces ~340-char "enc:v1:..." values and
Base64Backend produces ~50-char "b64:v1:..." values. See the plan in
docs/superpowers/plans/2026-05-03-kms-encryption.md for context.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "2f30089b2082"
down_revision: Union[str, Sequence[str], None] = "218ffaa712e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES_AND_COLUMNS = (
    ("users", "pix_merchant_name", 25),
    ("users", "pix_merchant_city", 15),
    ("organizations", "pix_merchant_name", 25),
    ("organizations", "pix_merchant_city", 15),
    ("billings", "pix_merchant_name", 25),
    ("billings", "pix_merchant_city", 15),
)


def upgrade() -> None:
    for table, column, length in _TABLES_AND_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length),
            type_=sa.Text,
            existing_nullable=False,
            existing_server_default="",
        )


def downgrade() -> None:
    # WARNING: Narrows TEXT back to VARCHAR(25)/VARCHAR(15). If any row
    # contains ciphertext written by the encryption backend (KMSBackend
    # produces ~340-char "enc:v1:..." rows; Base64Backend produces ~50-char
    # "b64:v1:..." rows), MariaDB will silently truncate it under default
    # sql_mode, corrupting data unrecoverably. Only run this downgrade after
    # verifying no row exceeds the target widths — for example, a fresh
    # schema with no production data, or after running the encryption
    # backfill in reverse to restore plaintext. See the rollback note in
    # docs/superpowers/plans/2026-05-03-kms-encryption.md.
    for table, column, length in _TABLES_AND_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text,
            type_=sa.String(length),
            existing_nullable=False,
            existing_server_default="",
        )
