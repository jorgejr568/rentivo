from __future__ import annotations

from urllib.parse import urlencode

from sqlalchemy import text

from tests.web.conftest import (
    create_billing_in_db,
    create_org_in_db,
    generate_bill_in_db,
    get_audit_logs,
    get_test_user_id,
)


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


def _seed_two_recipients(auth_client, billing, csrf):
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
            "recipients-TOTAL_FORMS": "2",
            "recipients-0-name": "João",
            "recipients-0-email": "joao@example.com",
            "recipients-1-name": "Ana",
            "recipients-1-email": "ana@example.com",
        },
        follow_redirects=False,
    )


def _recipient_uuid(test_engine):
    with test_engine.connect() as c:
        return c.execute(text("SELECT uuid FROM billing_recipients LIMIT 1")).scalar()


def test_send_creates_communication_and_enqueues_job(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)

    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={
            "csrf_token": csrf_token,
            "subject": "Cobrança {{unidade}}",
            "body": "Prezado {{nome_inquilino}}",
            "recipient_uuids": ruuid,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        comm_n = c.execute(text("SELECT COUNT(*) FROM communications")).scalar()
        job_n = c.execute(text("SELECT COUNT(*) FROM jobs WHERE job_type = 'communication.send'")).scalar()
    assert comm_n == 1
    assert job_n == 1
    assert any(log.event_type == "communication.sent" for log in get_audit_logs(test_engine))


def test_send_with_empty_body_redirects_to_compose(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={"csrf_token": csrf_token, "subject": "Assunto", "body": "  ", "recipient_uuids": ruuid},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/communications/compose")
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0


def test_send_fans_out_to_multiple_recipients(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_two_recipients(auth_client, billing, csrf_token)
    with test_engine.connect() as c:
        uuids = [row[0] for row in c.execute(text("SELECT uuid FROM billing_recipients")).fetchall()]
    assert len(uuids) == 2
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        content=urlencode(
            [
                ("csrf_token", csrf_token),
                ("subject", "Cobrança {{unidade}}"),
                ("body", "Prezado {{nome_inquilino}}"),
                ("recipient_uuids", uuids[0]),
                ("recipient_uuids", uuids[1]),
            ]
        ),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with test_engine.connect() as c:
        comm_n = c.execute(text("SELECT COUNT(*) FROM communications WHERE bill_id = :b"), {"b": bill.id}).scalar()
        job_n = c.execute(text("SELECT COUNT(*) FROM jobs WHERE job_type = 'communication.send'")).scalar()
    assert comm_n == 2
    assert job_n == 2


def test_send_without_recipient_selected_redirects_to_compose(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={"csrf_token": csrf_token, "subject": "s", "body": "b"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/communications/compose")
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0


def test_send_without_pdf_redirects_with_error(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)
    # Null the pdf_path so the guard fires.
    with test_engine.connect() as c:
        c.execute(text("UPDATE bills SET pdf_path = NULL WHERE uuid = :u"), {"u": bill.uuid})
        c.commit()
    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={"csrf_token": csrf_token, "subject": "s", "body": "b", "recipient_uuids": ruuid},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith(f"/bills/{bill.uuid}")
    with test_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0


def test_send_saves_billing_template(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={
            "csrf_token": csrf_token,
            "subject": "Assunto",
            "body": "Corpo",
            "recipient_uuids": ruuid,
            "save_scope": "billing",
        },
        follow_redirects=False,
    )
    with test_engine.connect() as c:
        n = c.execute(
            text("SELECT COUNT(*) FROM communication_templates WHERE owner_type='billing' AND owner_id=:b"),
            {"b": billing.id},
        ).scalar()
    assert n == 1
    assert any(log.event_type == "communication.template_saved" for log in get_audit_logs(test_engine))


def test_send_saves_owner_template(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={
            "csrf_token": csrf_token,
            "subject": "Assunto",
            "body": "Corpo",
            "recipient_uuids": ruuid,
            "save_scope": "owner",
        },
        follow_redirects=False,
    )
    with test_engine.connect() as c:
        n = c.execute(
            text("SELECT COUNT(*) FROM communication_templates WHERE owner_type='user'"),
        ).scalar()
    assert n == 1


def test_send_owner_scope_blocked_for_manager(auth_client, test_engine, csrf_token, tmp_path):
    """A manager (can_manage_bills but not can_edit_billing) must not be able to
    overwrite the org-wide default template via save_scope='owner'."""
    from rentivo.encryption.base64 import Base64Backend
    from rentivo.models.recipient import Recipient
    from rentivo.models.user import User
    from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
    from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository

    me = get_test_user_id(test_engine)
    with test_engine.connect() as conn:
        boss = SQLAlchemyUserRepository(conn, Base64Backend()).create(User(email="boss@example.com", password_hash="h"))
    org = create_org_in_db(test_engine, "Org X", boss.id)
    with test_engine.connect() as conn:
        SQLAlchemyOrganizationRepository(conn, Base64Backend()).add_member(org.id, me, "manager")

    billing = create_billing_in_db(
        test_engine,
        owner_type="organization",
        owner_id=org.id,
        pix_key="k",
        pix_merchant_name="Merchant",
        pix_merchant_city="City",
    )
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    with test_engine.connect() as conn:
        SQLAlchemyRecipientRepository(conn, Base64Backend()).replace_for_billing(
            billing.id, [Recipient(billing_id=billing.id, name="João", email="joao@example.com")]
        )
        ruuid = conn.execute(text("SELECT uuid FROM billing_recipients LIMIT 1")).scalar()

    resp = auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={
            "csrf_token": csrf_token,
            "subject": "Assunto",
            "body": "Corpo",
            "recipient_uuids": ruuid,
            "save_scope": "owner",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/communications/compose")
    with test_engine.connect() as c:
        # Nothing was sent and no org-wide template was written.
        assert c.execute(text("SELECT COUNT(*) FROM communications")).scalar() == 0
        assert (
            c.execute(text("SELECT COUNT(*) FROM communication_templates WHERE owner_type='organization'")).scalar()
            == 0
        )


def test_bill_detail_lists_sent_communication(auth_client, test_engine, csrf_token, tmp_path):
    billing = create_billing_in_db(test_engine)
    bill = generate_bill_in_db(test_engine, billing, tmp_path)
    _seed_recipient(auth_client, billing, csrf_token)
    ruuid = _recipient_uuid(test_engine)
    auth_client.post(
        f"/billings/{billing.uuid}/bills/{bill.uuid}/communications/send",
        data={"csrf_token": csrf_token, "subject": "Cobrança Joy", "body": "Prezado João", "recipient_uuids": ruuid},
        follow_redirects=False,
    )
    page = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}")
    assert "Comunicações" in page.text
    assert "joao@example.com" in page.text
    assert "Cobrança Joy" in page.text
