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


def test_edit_persists_recipients(auth_client, test_engine, csrf_token):
    billing = create_billing_in_db(test_engine)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(
            csrf_token,
            **{
                "recipients-TOTAL_FORMS": "2",
                "recipients-0-name": "Rodrigo",
                "recipients-0-email": "rodrigo@example.com",
                "recipients-1-name": "Ana",
                "recipients-1-email": "ana@example.com",
            },
        ),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM billing_recipients WHERE billing_id = :b"), {"b": billing.id}).scalar()
    assert n == 2


def test_edit_clearing_recipients_deletes_and_audits(auth_client, test_engine, csrf_token):
    from tests.web.conftest import get_audit_logs

    billing = create_billing_in_db(test_engine)
    # First add a recipient.
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(
            csrf_token,
            **{
                "recipients-TOTAL_FORMS": "1",
                "recipients-0-name": "Rodrigo",
                "recipients-0-email": "rodrigo@example.com",
            },
        ),
        follow_redirects=False,
    )
    # Then submit the edit with an empty recipients formset (cleared).
    resp = auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(csrf_token, **{"recipients-TOTAL_FORMS": "0"}),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM billing_recipients WHERE billing_id = :b"), {"b": billing.id}).scalar()
    assert n == 0
    logs = get_audit_logs(test_engine, event_type="billing.recipients_updated")
    # The clear is audited: a recipients_updated log records new count 0 (and the previous count 1).
    cleared = [log for log in logs if log.new_state == {"recipient_count": 0}]
    assert cleared
    assert cleared[0].previous_state == {"recipient_count": 1}


def test_edit_renders_existing_recipients(auth_client, test_engine, csrf_token):
    billing = create_billing_in_db(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/edit",
        data=_form(
            csrf_token,
            **{
                "recipients-TOTAL_FORMS": "1",
                "recipients-0-name": "Rodrigo",
                "recipients-0-email": "rodrigo@example.com",
            },
        ),
        follow_redirects=False,
    )
    page = auth_client.get(f"/billings/{billing.uuid}/edit")
    assert "rodrigo@example.com" in page.text
    assert "Rodrigo" in page.text
