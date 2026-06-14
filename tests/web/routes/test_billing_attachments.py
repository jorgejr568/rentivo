from unittest.mock import patch

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing_attachment import BillingAttachment
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingAttachmentRepository
from rentivo.storage.local import LocalStorage
from tests.web.conftest import create_billing_in_db, get_audit_logs
from tests.web.routes.test_bill import _create_other_user_billing


def _patched_storage(tmp_path):
    return patch("web.services_container.get_storage", return_value=LocalStorage(str(tmp_path)))


def _attachments(test_engine, billing):
    with test_engine.connect() as conn:
        return SQLAlchemyBillingAttachmentRepository(conn, Base64Backend()).list_by_billing(billing.id)


class TestAttachmentUpload:
    def test_upload_pdf(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "Contrato"},
                files={"attachment_file": ("contrato.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert f"/billings/{billing.uuid}/edit" in resp.headers.get("location", "")
        logs = get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD)
        assert len(logs) == 1
        assert logs[0].new_state["name"] == "Contrato"
        assert logs[0].new_state["filename"] == "contrato.pdf"

    def test_upload_image(self, auth_client, test_engine, tmp_path, csrf_token):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (10, 10), color="red").save(buf, format="JPEG")
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "Foto"},
                files={"attachment_file": ("a.jpg", buf.getvalue(), "image/jpeg")},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert len(get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD)) == 1

    def test_upload_blank_name_defaults_to_filename(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": ""},
                files={"attachment_file": ("lease.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        logs = get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD)
        assert logs[0].new_state["name"] == "lease.pdf"

    def test_upload_no_file_flashes(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "x"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD) == []

    def test_upload_invalid_type_flashes(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "x"},
                files={"attachment_file": ("a.gif", b"GIF89a", "image/gif")},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD) == []

    def test_upload_service_value_error_flashes(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with (
            _patched_storage(tmp_path),
            patch(
                "rentivo.services.billing_attachment_service.BillingAttachmentService.add_attachment",
                side_effect=ValueError("boom"),
            ),
        ):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "x"},
                files={"attachment_file": ("a.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert f"/billings/{billing.uuid}/edit" in resp.headers["location"]
        assert get_audit_logs(test_engine, AuditEventType.ATTACHMENT_UPLOAD) == []

    def test_upload_denied_for_other_users_billing(self, auth_client, test_engine, tmp_path, csrf_token):
        other = _create_other_user_billing(test_engine)
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{other.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "x"},
                files={"attachment_file": ("a.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"
        assert _attachments(test_engine, other) == []


class TestAttachmentDownloadDelete:
    def _upload(self, auth_client, billing, tmp_path, csrf_token, name="Contrato"):
        with _patched_storage(tmp_path):
            auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": name},
                files={"attachment_file": ("c.pdf", b"%PDF-data", "application/pdf")},
                follow_redirects=False,
            )

    def test_download_returns_file(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        self._upload(auth_client, billing, tmp_path, csrf_token)
        uuid = _attachments(test_engine, billing)[0].uuid
        with _patched_storage(tmp_path):
            resp = auth_client.get(f"/billings/{billing.uuid}/attachments/{uuid}", follow_redirects=False)
        assert resp.status_code == 200
        assert resp.content == b"%PDF-data"

    def test_download_missing_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        resp = auth_client.get(f"/billings/{billing.uuid}/attachments/nope", follow_redirects=False)
        assert resp.status_code == 302

    def test_download_denied_for_other_users_billing(self, auth_client, test_engine, tmp_path, csrf_token):
        other = _create_other_user_billing(test_engine)
        with test_engine.connect() as conn:
            a = SQLAlchemyBillingAttachmentRepository(conn, Base64Backend()).create(
                BillingAttachment(
                    billing_id=other.id,
                    name="x",
                    filename="x.pdf",
                    storage_key="k.pdf",
                    content_type="application/pdf",
                    file_size=1,
                )
            )
        resp = auth_client.get(f"/billings/{other.uuid}/attachments/{a.uuid}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_delete_removes_and_audits(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        self._upload(auth_client, billing, tmp_path, csrf_token)
        uuid = _attachments(test_engine, billing)[0].uuid
        with _patched_storage(tmp_path):
            resp = auth_client.post(
                f"/billings/{billing.uuid}/attachments/{uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert _attachments(test_engine, billing) == []
        assert len(get_audit_logs(test_engine, AuditEventType.ATTACHMENT_DELETE)) == 1

    def test_download_url_backend_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        from rentivo.storage.base import FileRef

        billing = create_billing_in_db(test_engine)
        with test_engine.connect() as conn:
            a = SQLAlchemyBillingAttachmentRepository(conn, Base64Backend()).create(
                BillingAttachment(
                    billing_id=billing.id,
                    name="x",
                    filename="x.pdf",
                    storage_key="k.pdf",
                    content_type="application/pdf",
                    file_size=1,
                )
            )
        with patch(
            "rentivo.services.billing_attachment_service.BillingAttachmentService.get_attachment_ref",
            return_value=FileRef(kind="url", location="https://example.test/x.pdf"),
        ):
            resp = auth_client.get(f"/billings/{billing.uuid}/attachments/{a.uuid}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.test/x.pdf"

    def test_delete_missing_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/attachments/nope/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestAttachmentRendering:
    def test_edit_page_shows_upload_form(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        resp = auth_client.get(f"/billings/{billing.uuid}/edit")
        assert resp.status_code == 200
        assert "attachments/upload" in resp.text
        assert "Documentos" in resp.text

    def test_edit_page_lists_uploaded_attachment(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "Contrato de locação"},
                files={"attachment_file": ("c.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        resp = auth_client.get(f"/billings/{billing.uuid}/edit")
        assert "Contrato de locação" in resp.text

    def test_detail_page_lists_attachment_download_link(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with _patched_storage(tmp_path):
            auth_client.post(
                f"/billings/{billing.uuid}/attachments/upload",
                data={"csrf_token": csrf_token, "name": "Contrato"},
                files={"attachment_file": ("c.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        resp = auth_client.get(f"/billings/{billing.uuid}")
        assert "Contrato" in resp.text
        assert f"/billings/{billing.uuid}/attachments/" in resp.text
