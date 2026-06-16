from __future__ import annotations

from sqlalchemy import text

from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs


def _seed_recipient(auth_client, billing, csrf):
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data={
            "csrf_token": csrf,
            "name": "Apt 101",
            "description": "",
            "pix_key": "",
            "pix_merchant_name": "",
            "pix_merchant_city": "",
            "items-TOTAL_FORMS": "1",
            "items-0-description": "Aluguel",
            "items-0-item_type": "fixed",
            "items-0-amount": "2850,00",
            "recipients-TOTAL_FORMS": "1",
            "recipients-0-name": "João",
            "recipients-0-email": "joao@example.com",
        },
        follow_redirects=False,
    )


def _ruuid(test_engine):
    with test_engine.connect() as c:
        return c.execute(text("SELECT uuid FROM billing_recipients LIMIT 1")).scalar()


def _send(auth_client, billing, bill, csrf, body, ruuid, ack=False):
    data = {
        "csrf_token": csrf,
        "comm_type": "bill_ready",
        "subject": "Cobrança",
        "body": body,
        "recipient_uuids": ruuid,
    }
    if ack:
        data["acknowledge_warning"] = "1"
    return auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send", data=data, follow_redirects=False
    )


def test_severe_content_is_blocked(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    resp = _send(auth_client, billing, bill, csrf_token, "Se não pagar vou te matar.", _ruuid(test_engine))
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/communications/compose?type=bill_ready")
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM jobs WHERE job_type='communication.send'")).scalar() == 0
    assert any(log.event_type == "communication.blocked" for log in get_audit_logs(test_engine))


def test_mild_content_requires_acknowledgment(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    resp = _send(auth_client, billing, bill, csrf_token, "Que merda, paga logo.", _ruuid(test_engine), ack=False)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/communications/compose?type=bill_ready")
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM jobs WHERE job_type='communication.send'")).scalar() == 0


def test_mild_content_sends_with_acknowledgment(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    resp = _send(auth_client, billing, bill, csrf_token, "Que merda, paga logo.", _ruuid(test_engine), ack=True)
    assert resp.status_code == 302
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 1
    assert any(log.event_type == "communication.flagged_override" for log in get_audit_logs(test_engine))


def test_clean_send_emits_no_moderation_audit(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    resp = _send(auth_client, billing, bill, csrf_token, "Prezado, segue a cobrança.", _ruuid(test_engine))
    assert resp.status_code == 302
    events = {log.event_type for log in get_audit_logs(test_engine)}
    assert "communication.blocked" not in events
    assert "communication.flagged_override" not in events


def test_preview_returns_moderation(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/preview",
        json={"subject": "Aviso", "body": "Que merda"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    assert resp.json()["mild"] == ["merda"]
    assert resp.json()["severe"] == []
