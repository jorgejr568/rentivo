from __future__ import annotations

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.audit_log import AuditEventType
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs


def _add_recipient(engine, billing_id, phone):
    with engine.connect() as conn:
        repo = SQLAlchemyRecipientRepository(conn, Base64Backend())
        repo.replace_for_billing(
            billing_id, [Recipient(billing_id=billing_id, name="João", email="joao@example.com", phone=phone)]
        )
        return repo.list_by_billing(billing_id)[0].uuid


def test_whatsapp_click_redirects_to_wa_me_and_audits(auth_client, test_engine, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    uuid = _add_recipient(test_engine, billing.id, "+5511999998888")

    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/whatsapp?recipient={uuid}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://wa.me/5511999998888?text=")

    logs = get_audit_logs(test_engine, AuditEventType.WHATSAPP_INVOICE_CLICKED)
    assert len(logs) == 1


def test_detail_page_shows_whatsapp_button_for_recipient_with_phone(auth_client, test_engine, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _add_recipient(test_engine, billing.id, "+5511999998888")

    resp = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}")
    assert resp.status_code == 200
    assert "Enviar pelo WhatsApp" in resp.text
    assert f"/billings/{billing.uuid}/bills/{bill.uuid}/whatsapp?recipient=" in resp.text


def test_unknown_recipient_flashes_and_redirects_back(auth_client, test_engine, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)

    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/whatsapp?recipient=does-not-exist",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/billings/{billing.uuid}/bills/{bill.uuid}"


def test_invalid_phone_number_flashes_and_redirects_back(auth_client, test_engine, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    uuid = _add_recipient(test_engine, billing.id, "123")  # truthy but un-normalizable

    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/whatsapp?recipient={uuid}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/billings/{billing.uuid}/bills/{bill.uuid}"


def test_pix_not_configured_flashes_and_redirects_back(auth_client, test_engine, tmp_path, monkeypatch):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    uuid = _add_recipient(test_engine, billing.id, "+5511999998888")

    def _raise(self, *args, **kwargs):
        raise ValueError("Configure a chave PIX antes de enviar.")

    monkeypatch.setattr("rentivo.services.bill_service.BillService.build_whatsapp_link", _raise)

    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/whatsapp?recipient={uuid}",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/billings/{billing.uuid}/bills/{bill.uuid}"
