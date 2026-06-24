from __future__ import annotations

from sqlalchemy import text

from tests.web.conftest import create_billing_in_db, generate_bill_in_db


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


def test_compose_shows_default_template_and_recipients(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)

    page = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=bill_ready")
    assert page.status_code == 200
    assert "Prezado" in page.text  # default body shown
    assert "joao@example.com" in page.text  # recipient checkbox


def test_compose_with_no_recipients_shows_prompt(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    page = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=bill_ready")
    assert page.status_code == 200
    # No recipients → a prompt linking to the billing edit page (no send form).
    assert f"/billings/{billing.uuid}/edit" in page.text


def test_preview_renders_markdown(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/preview",
        json={"body": "Prezado **João**"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    assert "<strong>João</strong>" in resp.json()["html"]
    assert "<script>" not in resp.json()["html"]


def _mark_paid_with_recibo(test_engine, bill, recibo_key="bg/recibo.pdf"):
    with test_engine.connect() as c:
        c.execute(
            text("UPDATE bills SET status = 'paid', recibo_pdf_path = :r WHERE id = :id"),
            {"r": recibo_key, "id": bill.id},
        )
        c.commit()


def test_compose_rejects_invalid_type(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=bogus",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith(f"/bills/{bill.uuid}")


def test_compose_payment_receipt_requires_available_recibo(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)  # not paid, no recibo
    resp = auth_client.get(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=payment_receipt",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith(f"/bills/{bill.uuid}")


def test_compose_payment_receipt_shows_recibo_template(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    _mark_paid_with_recibo(test_engine, bill)
    page = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=payment_receipt")
    assert page.status_code == 200
    assert "recibo de pagamento" in page.text
    assert 'name="comm_type" value="payment_receipt"' in page.text


def test_compose_has_moderation_panel_and_ack(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    page = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/compose?type=bill_ready")
    assert 'id="moderation-panel"' in page.text
    assert 'name="acknowledge_warning"' in page.text
