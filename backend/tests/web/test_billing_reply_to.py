from __future__ import annotations

from sqlalchemy import text

from tests.web.conftest import create_billing_in_db


def _form(csrf, **extra):
    base = {
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
    }
    base.update(extra)
    return base


def test_create_persists_reply_to(auth_client, test_engine, csrf_token):
    resp = auth_client.post(
        "/billings/create",
        data=_form(
            csrf_token,
            name="Com Reply-To",
            **{
                "reply_to-TOTAL_FORMS": "2",
                "reply_to-0-name": "Ana",
                "reply_to-0-email": "ana@example.com",
                "reply_to-1-name": "Bruno",
                "reply_to-1-email": "bruno@example.com",
            },
        ),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM billing_reply_to")).scalar() == 2


def test_create_without_reply_to_persists_none(auth_client, test_engine, csrf_token):
    resp = auth_client.post(
        "/billings/create",
        data=_form(csrf_token, name="Sem Reply-To", **{"reply_to-TOTAL_FORMS": "0"}),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM billing_reply_to")).scalar() == 0


def test_edit_persists_and_renders_reply_to(auth_client, test_engine, csrf_token):
    billing = create_billing_in_db(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(
            csrf_token,
            **{"reply_to-TOTAL_FORMS": "1", "reply_to-0-name": "Ana", "reply_to-0-email": "ana@example.com"},
        ),
        follow_redirects=False,
    )
    with test_engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM billing_reply_to WHERE billing_id = :b"), {"b": billing.id}).scalar()
    assert n == 1
    page = auth_client.get(f"/billings/{billing.uuid}/edit")
    assert "ana@example.com" in page.text


def test_edit_clearing_reply_to_deletes(auth_client, test_engine, csrf_token):
    billing = create_billing_in_db(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(
            csrf_token,
            **{"reply_to-TOTAL_FORMS": "1", "reply_to-0-name": "Ana", "reply_to-0-email": "ana@example.com"},
        ),
        follow_redirects=False,
    )
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(csrf_token, **{"reply_to-TOTAL_FORMS": "0"}),
        follow_redirects=False,
    )
    with test_engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM billing_reply_to WHERE billing_id = :b"), {"b": billing.id}).scalar()
    assert n == 0
