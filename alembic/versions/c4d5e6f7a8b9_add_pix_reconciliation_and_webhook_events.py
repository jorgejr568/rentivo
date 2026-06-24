"""add dynamic-PIX reconciliation columns to bills + pix_webhook_events table

Supports the Asaas dynamic-PIX webhook auto-confirmation pilot (REN-15 / REN-25).

- ``bills`` gains four nullable PSP linkage columns. They carry non-PII
  operational identifiers (provider charge / txid / e2eid), so no KMS
  encryption is applied — unlike the PIX *key* on ``billings``.
- ``pix_webhook_events`` is an idempotency / replay-protection ledger for
  inbound webhook deliveries. The webhook handler inserts with
  ``ON CONFLICT DO NOTHING`` (MySQL: ``INSERT IGNORE`` / ``ON DUPLICATE KEY``)
  on ``(provider, event_id)``; first insert wins and drives the
  ``Bill -> PAID`` transition, duplicate deliveries are dropped.

Portable across MySQL (prod, ``mysql+pymysql``) and SQLite (tests): indexed /
constrained string columns use explicit ``String`` lengths as MySQL requires.

Revision ID: c4d5e6f7a8b9
Revises: 51f6a33c87b3
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "51f6a33c87b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. bills — PSP linkage columns (all nullable; no backfill).
    op.add_column("bills", sa.Column("pix_provider", sa.String(32), nullable=True))
    op.add_column("bills", sa.Column("pix_charge_id", sa.String(64), nullable=True))
    op.add_column("bills", sa.Column("pix_txid", sa.String(64), nullable=True))
    op.add_column("bills", sa.Column("pix_e2eid", sa.String(64), nullable=True))
    # Reconciliation looks up the bill by provider charge id; index it.
    op.create_index("ix_bills_pix_charge_id", "bills", ["pix_charge_id"])

    # 2. pix_webhook_events — idempotency / replay ledger.
    op.create_table(
        "pix_webhook_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(191), nullable=False),
        sa.Column("charge_id", sa.String(64), nullable=True),
        sa.Column("external_reference", sa.String(191), nullable=True),
        sa.Column("e2eid", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "bill_id",
            sa.Integer,
            sa.ForeignKey("bills.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Replayed delivery -> no-op insert (handler uses INSERT ... ON CONFLICT
        # DO NOTHING on this pair).
        sa.UniqueConstraint(
            "provider", "event_id", name="uq_pix_webhook_events_provider_event"
        ),
    )
    # Reconciliation / lookup access paths.
    op.create_index(
        "ix_pix_webhook_events_charge_id", "pix_webhook_events", ["charge_id"]
    )
    op.create_index("ix_pix_webhook_events_bill_id", "pix_webhook_events", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_pix_webhook_events_bill_id", table_name="pix_webhook_events")
    op.drop_index("ix_pix_webhook_events_charge_id", table_name="pix_webhook_events")
    op.drop_table("pix_webhook_events")

    op.drop_index("ix_bills_pix_charge_id", table_name="bills")
    op.drop_column("bills", "pix_e2eid")
    op.drop_column("bills", "pix_txid")
    op.drop_column("bills", "pix_charge_id")
    op.drop_column("bills", "pix_provider")
