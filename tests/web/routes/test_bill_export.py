"""Integration tests for the bill export route (async, emailed to recipients)."""

from __future__ import annotations

from sqlalchemy import text

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.audit_log import AuditEventType
from rentivo.models.recipient import Recipient
from rentivo.repositories.sqlalchemy.recipient import SQLAlchemyRecipientRepository
from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs


def _add_recipient(engine, billing, email="dest@example.com", name="Destinatário"):
    with engine.connect() as conn:
        SQLAlchemyRecipientRepository(conn, Base64Backend()).replace_for_billing(
            billing.id, [Recipient(billing_id=billing.id, name=name, email=email)]
        )


def _enqueued_export_jobs(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT payload FROM jobs WHERE job_type = 'export.generate'")).fetchall()
    return [r[0] for r in rows]


class TestBillExport:
    def test_export_enqueues_job_and_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        generate_bill_in_db(test_engine, billing, tmp_path)
        _add_recipient(test_engine, billing)

        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "csv"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == f"/billings/{billing.uuid}"
        jobs = _enqueued_export_jobs(test_engine)
        assert len(jobs) == 1
        assert '"format": "csv"' in jobs[0]
        assert f'"billing_id": {billing.id}' in jobs[0]

    def test_export_xlsx_format_recorded(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        generate_bill_in_db(test_engine, billing, tmp_path)
        _add_recipient(test_engine, billing)

        auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "xlsx"},
            follow_redirects=False,
        )
        jobs = _enqueued_export_jobs(test_engine)
        assert len(jobs) == 1
        assert '"format": "xlsx"' in jobs[0]

    def test_export_unknown_format_falls_back_to_csv(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        generate_bill_in_db(test_engine, billing, tmp_path)
        _add_recipient(test_engine, billing)

        auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "pdf"},
            follow_redirects=False,
        )
        jobs = _enqueued_export_jobs(test_engine)
        assert '"format": "csv"' in jobs[0]

    def test_export_without_recipients_is_rejected(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        generate_bill_in_db(test_engine, billing, tmp_path)

        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "csv"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/billings/{billing.uuid}/edit"
        assert _enqueued_export_jobs(test_engine) == []

    def test_export_records_audit_event(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        generate_bill_in_db(test_engine, billing, tmp_path)
        _add_recipient(test_engine, billing)

        auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "xlsx"},
            follow_redirects=False,
        )
        logs = get_audit_logs(test_engine, event_type=AuditEventType.BILLING_EXPORT)
        assert len(logs) == 1
        assert logs[0].new_state == {"format": "xlsx", "recipient_count": 1}

    def test_export_billing_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/nonexistent/bills/export",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_export_other_users_billing_denied(self, auth_client, test_engine, csrf_token):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        with test_engine.connect() as conn:
            other = SQLAlchemyUserRepository(conn, Base64Backend()).create(
                User(email="exp_other@example.com", password_hash="h")
            )
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)
        _add_recipient(test_engine, billing)

        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/export",
            data={"csrf_token": csrf_token, "format": "csv"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert _enqueued_export_jobs(test_engine) == []
