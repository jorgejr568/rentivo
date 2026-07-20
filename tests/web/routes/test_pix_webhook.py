"""Public Asaas PIX webhook route tests (REN-26).

Drives the real route + reconciliation service + repos against the in-memory
SQLite app; only the network (charge creation) is never touched — the webhook
path is pure parse/verify/DB. Asaas is enabled by patching settings.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from ulid import ULID

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import BillStatus
from tests.web.conftest import create_billing_in_db, get_audit_logs

WEBHOOK_URL = "/webhooks/pix/asaas"
TOKEN = "sandbox-webhook-secret"
HEADERS = {"asaas-access-token": TOKEN}


@pytest.fixture()
def asaas_enabled(monkeypatch):
    """Enable the Asaas integration by patching the shared settings object."""
    from web import services_container

    monkeypatch.setattr(services_container.settings, "asaas_api_key", "sandbox-key")
    monkeypatch.setattr(services_container.settings, "asaas_webhook_token", TOKEN)
    yield


def _seed_bill(test_engine, tmp_path=None, *, total_amount: int = 285000, status: str = "sent"):
    """Insert a bill directly (raw SQL) so the webhook path is exercised without
    the unrelated PIX-config requirement of the bill-generation service."""
    billing = create_billing_in_db(test_engine)
    bill_uuid = str(ULID())
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO bills (billing_id, reference_month, total_amount, uuid, "
                "status, status_updated_at, created_at) "
                "VALUES (:billing_id, '2025-03', :total, :uuid, :status, :now, :now)"
            ),
            {
                "billing_id": billing.id,
                "total": total_amount,
                "uuid": bill_uuid,
                "status": status,
                "now": datetime(2025, 3, 1, 12, 0, 0),
            },
        )
        conn.commit()

    class _B:
        uuid = bill_uuid

    _B.status = status
    return _B


def _paid_body(bill_uuid: str, *, value: float = 2850.00, event: str = "PAYMENT_RECEIVED", event_id="evt_1"):
    return {
        "id": event_id,
        "event": event,
        "payment": {
            "id": "pay_123",
            "externalReference": bill_uuid,
            "value": value,
            "status": "RECEIVED",
            "pixTransaction": {"endToEndIdentifier": "E2E-ABC"},
        },
    }


def _bill_status(test_engine, bill_uuid: str) -> str:
    with test_engine.connect() as conn:
        return conn.execute(text("SELECT status FROM bills WHERE uuid = :u"), {"u": bill_uuid}).scalar_one()


def test_webhook_disabled_returns_503(client):
    # No settings patch → integration off → fail closed (no live public endpoint).
    resp = client.post(WEBHOOK_URL, json=_paid_body("nope"), headers=HEADERS)
    assert resp.status_code == 503


def test_webhook_rejects_missing_token(client, asaas_enabled):
    resp = client.post(WEBHOOK_URL, json=_paid_body("nope"))
    assert resp.status_code == 401


def test_webhook_rejects_bad_token(client, asaas_enabled):
    resp = client.post(WEBHOOK_URL, json=_paid_body("nope"), headers={"asaas-access-token": "wrong"})
    assert resp.status_code == 401


def test_webhook_bad_json_returns_400(client, asaas_enabled):
    resp = client.post(WEBHOOK_URL, content=b"not-json", headers=HEADERS)
    assert resp.status_code == 400


def test_webhook_paid_confirms_bill(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    assert bill.status != BillStatus.PAID.value

    resp = client.post(WEBHOOK_URL, json=_paid_body(bill.uuid), headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert _bill_status(test_engine, bill.uuid) == BillStatus.PAID.value


def test_webhook_audits_as_system_actor(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    client.post(WEBHOOK_URL, json=_paid_body(bill.uuid), headers=HEADERS)

    logs = get_audit_logs(test_engine, AuditEventType.BILL_STATUS_CHANGE)
    assert len(logs) == 1
    log = logs[0]
    # `source` is the reliable, unredacted webhook-actor signal; `actor_username`
    # is partial-mask redacted by the audit PII guard like every other username.
    assert log.source == "psp-webhook"
    assert log.actor_username.startswith("sys")
    assert log.actor_id is None
    assert log.new_state.get("status") == BillStatus.PAID.value
    assert log.metadata.get("charge_id") == "pay_123"


def test_webhook_persists_pix_linkage(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    client.post(WEBHOOK_URL, json=_paid_body(bill.uuid), headers=HEADERS)

    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT pix_provider, pix_charge_id, pix_e2eid FROM bills WHERE uuid = :u"),
            {"u": bill.uuid},
        ).fetchone()
    assert row[0] == "asaas"
    assert row[1] == "pay_123"
    assert row[2] == "E2E-ABC"


def test_webhook_replay_is_idempotent(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    body = _paid_body(bill.uuid)

    first = client.post(WEBHOOK_URL, json=body, headers=HEADERS)
    second = client.post(WEBHOOK_URL, json=body, headers=HEADERS)

    assert first.json()["status"] == "confirmed"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    # Exactly one transition audited despite two deliveries.
    assert len(get_audit_logs(test_engine, AuditEventType.BILL_STATUS_CHANGE)) == 1


def test_webhook_unknown_bill_acked_not_confirmed(client, asaas_enabled, test_engine, tmp_path):
    resp = client.post(WEBHOOK_URL, json=_paid_body("00000000000000000000000000"), headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "bill_not_found"


def test_webhook_amount_mismatch_does_not_confirm(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    # Bill total is R$2850.00; report a different settled amount.
    resp = client.post(WEBHOOK_URL, json=_paid_body(bill.uuid, value=10.00), headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["status"] == "amount_mismatch"
    assert _bill_status(test_engine, bill.uuid) != BillStatus.PAID.value


def test_webhook_non_paid_event_ignored(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    body = _paid_body(bill.uuid, event="PAYMENT_OVERDUE")

    resp = client.post(WEBHOOK_URL, json=body, headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored_not_paid"
    assert _bill_status(test_engine, bill.uuid) != BillStatus.PAID.value


def test_webhook_already_paid_is_noop_success(client, asaas_enabled, test_engine, tmp_path):
    bill = _seed_bill(test_engine, tmp_path)
    # First settle it, then a *new* event id for the same bill arrives.
    client.post(WEBHOOK_URL, json=_paid_body(bill.uuid, event_id="evt_a"), headers=HEADERS)
    resp = client.post(WEBHOOK_URL, json=_paid_body(bill.uuid, event_id="evt_b"), headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json()["status"] == "already_paid"
    assert _bill_status(test_engine, bill.uuid) == BillStatus.PAID.value
