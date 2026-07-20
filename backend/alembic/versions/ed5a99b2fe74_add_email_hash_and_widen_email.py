"""add email hash and widen email

Revision ID: ed5a99b2fe74
Revises: 2f30089b2082
Create Date: 2026-05-12 05:22:31.972804

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ed5a99b2fe74"
down_revision: Union[str, Sequence[str], None] = "2f30089b2082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the plaintext UNIQUE on email — the column is about to hold
    #    non-deterministic ciphertext, so uniqueness moves to email_hash. We
    #    also need it dropped *before* the normalization in step 2, otherwise
    #    rows like ('Alice@x.com', ...) and ('alice@x.com', ...) collide when
    #    we lowercase them. Letting the collision surface at backfill time via
    #    the new UNIQUE(email_hash) is the right place to catch it.
    op.drop_constraint("uq_users_email", "users", type_="unique")

    # 2. Normalize existing plaintext: TRIM + LOWER. Matches the
    #    normalization rentivo.blind_index.compute_email_hash applies, so the
    #    legacy-plaintext fallback that the repository will gain in a later
    #    commit can compare a single normalized form. Operationally cheap — a
    #    single full-table UPDATE on a column that's about to be re-written
    #    anyway by the encryption backfill.
    op.execute("UPDATE users SET email = LOWER(TRIM(email))")

    # 3. Widen email so KMS ciphertext (~200-500 chars base64) fits.
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )

    # 4. Add the blind-index column. Nullable for the rollout window — the
    #    backfill populates it. Once the backfill is complete the operator can
    #    follow up with a tighten-to-NOT-NULL migration if desired.
    op.add_column(
        "users",
        sa.Column("email_hash", sa.String(length=64), nullable=True),
    )
    # UNIQUE applies only to non-NULL values in MariaDB/MySQL, so adding it now
    # is safe — legacy rows are NULL until the backfill runs. If two rows
    # collided after the LOWER(TRIM) in step 2, the operator finds out here
    # (backfill INSERT fails on the second row).
    op.create_unique_constraint(
        "uq_users_email_hash",
        "users",
        ["email_hash"],
    )


def downgrade() -> None:
    # NOTE: the LOWER(TRIM(email)) normalization in upgrade() is intentionally
    # not reversed — there is no record of the original case/whitespace. Users
    # who entered "Alice@Example.com" at signup will read back
    # "alice@example.com" after a downgrade. That's an acceptable trade-off for
    # a downgrade path that exists mainly for emergency rollback before any
    # production data migration runs.
    #
    # WARNING: narrowing `email` back to VARCHAR(255) will silently truncate
    # any row that has already been encrypted (KMS ciphertext can run to ~500
    # chars) under default MariaDB sql_mode — corrupting data unrecoverably.
    # Only run this downgrade BEFORE any production encryption backfill.
    op.drop_constraint("uq_users_email_hash", "users", type_="unique")
    op.drop_column("users", "email_hash")
    op.alter_column(
        "users",
        "email",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
