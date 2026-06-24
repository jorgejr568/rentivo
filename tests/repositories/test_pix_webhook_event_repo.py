"""Idempotency / replay-ledger repo tests (REN-26)."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text

from rentivo.repositories.sqlalchemy import SQLAlchemyPixWebhookEventRepository


@pytest.fixture()
def event_repo(db_connection: Connection) -> SQLAlchemyPixWebhookEventRepository:
    return SQLAlchemyPixWebhookEventRepository(db_connection)


def _count(conn: Connection) -> int:
    return conn.execute(text("SELECT COUNT(*) FROM pix_webhook_events")).scalar_one()


def test_record_if_new_first_delivery_inserts(event_repo, db_connection):
    inserted = event_repo.record_if_new(
        provider="asaas",
        event_id="evt_1",
        event_type="PAYMENT_RECEIVED",
        status="RECEIVED",
        charge_id="pay_1",
        external_reference="bill-uuid-1",
        e2eid="E2E1",
    )
    assert inserted is True
    assert _count(db_connection) == 1


def test_record_if_new_duplicate_dropped(event_repo, db_connection):
    common = dict(
        provider="asaas",
        event_id="evt_dup",
        event_type="PAYMENT_RECEIVED",
        status="RECEIVED",
        charge_id="pay_1",
    )
    assert event_repo.record_if_new(**common) is True
    # Same (provider, event_id) — replayed delivery loses the unique-key race.
    assert event_repo.record_if_new(**common) is False
    assert _count(db_connection) == 1


def test_record_if_new_distinct_providers_not_deduped(event_repo, db_connection):
    assert (
        event_repo.record_if_new(provider="asaas", event_id="evt_x", event_type="PAYMENT_RECEIVED", status="RECEIVED")
        is True
    )
    # Same event_id but a different provider is a different ledger row.
    assert (
        event_repo.record_if_new(provider="efi", event_id="evt_x", event_type="PAYMENT_RECEIVED", status="RECEIVED")
        is True
    )
    assert _count(db_connection) == 2


def _seed_bill(conn) -> int:
    """Insert a minimal billing + bill so the FK on pix_webhook_events.bill_id holds."""
    from datetime import datetime

    now = datetime(2025, 3, 1)
    conn.execute(
        text(
            "INSERT INTO billings (name, uuid, created_at, updated_at) "
            "VALUES ('Apt', 'BILLINGUUID00000000000001', :now, :now)"
        ),
        {"now": now},
    )
    bid = conn.execute(text("SELECT id FROM billings LIMIT 1")).scalar_one()
    conn.execute(
        text(
            "INSERT INTO bills (billing_id, reference_month, total_amount, uuid, status, created_at) "
            "VALUES (:bid, '2025-03', 1000, 'BILLUUID0000000000000001', 'sent', :now)"
        ),
        {"bid": bid, "now": now},
    )
    conn.commit()
    return conn.execute(text("SELECT id FROM bills LIMIT 1")).scalar_one()


def test_set_bill_id_backfills(event_repo, db_connection):
    bill_id = _seed_bill(db_connection)
    event_repo.record_if_new(provider="asaas", event_id="evt_b", event_type="PAYMENT_RECEIVED", status="RECEIVED")
    event_repo.set_bill_id(provider="asaas", event_id="evt_b", bill_id=bill_id)
    row = db_connection.execute(text("SELECT bill_id FROM pix_webhook_events WHERE event_id = 'evt_b'")).fetchone()
    assert row[0] == bill_id
