from unittest.mock import MagicMock, patch

from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyUserRepository
from rentivo.storage.local import LocalStorage
from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs


def _create_other_user_billing(test_engine):
    """Create a billing owned by a different user (not the logged-in test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        other = user_repo.create(User(username="bill_other", password_hash="h"))
    return create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)


class TestBillGenerate:
    def test_generate_form(self, auth_client, test_engine):
        billing = create_billing_in_db(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}/bills/generate")
        assert response.status_code == 200

    def test_generate_form_not_found(self, auth_client):
        response = auth_client.get("/billings/nonexistent/bills/generate", follow_redirects=False)
        assert response.status_code == 302

    def test_generate_success(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-03",
                    "due_date": "10/04/2025",
                    "notes": "test",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_generate_no_reference(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/generate",
            data={
                "csrf_token": csrf_token,
                "reference_month": "",
                "extras-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_generate_billing_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/nonexistent/bills/generate",
            data={"csrf_token": csrf_token, "reference_month": "2025-03", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillDetail:
    def test_detail(self, auth_client, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}")
        assert response.status_code == 200

    def test_detail_not_found(self, auth_client):
        response = auth_client.get("/billings/x/bills/nonexistent", follow_redirects=False)
        assert response.status_code == 302


class TestBillEdit:
    def test_edit_form(self, auth_client, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}/edit")
        assert response.status_code == 200

    def test_edit_form_not_found(self, auth_client):
        response = auth_client.get("/billings/x/bills/nonexistent/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_submit(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "15/04/2025",
                    "notes": "updated",
                    "items-TOTAL_FORMS": "1",
                    "items-0-description": "Aluguel",
                    "items-0-amount": "285000",
                    "items-0-item_type": "fixed",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_edit_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/edit",
            data={"csrf_token": csrf_token, "items-TOTAL_FORMS": "0", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillRegeneratePdf:
    def test_regenerate(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/regenerate-pdf",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_regenerate_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/regenerate-pdf",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillTogglePaid:
    def test_toggle_paid(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/toggle-paid",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_toggle_paid_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/toggle-paid",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillDelete:
    def test_delete(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_delete_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillInvoice:
    def test_invoice_local_file(self, auth_client, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/pdf")

    def test_invoice_not_found(self, auth_client):
        response = auth_client.get(
            "/billings/x/bills/nonexistent/invoice",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillGenerateExtras:
    def test_generate_with_extras(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-04",
                    "due_date": "10/05/2025",
                    "notes": "",
                    "extras-TOTAL_FORMS": "1",
                    "extras-0-description": "Extra fee",
                    "extras-0-amount": "50,00",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillTogglePaidTwice:
    def test_toggle_paid_then_unpaid(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # First toggle: unpaid → paid
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/toggle-paid",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
            # Second toggle: paid → unpaid
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/toggle-paid",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillAccessDenied:
    """Test authorization denial paths for bill routes."""

    def test_generate_form_access_denied(self, auth_client, test_engine):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.get(
            f"/billings/{billing.uuid}/bills/generate",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_generate_post_access_denied(self, auth_client, test_engine, csrf_token):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/generate",
            data={"csrf_token": csrf_token, "reference_month": "2025-03", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_detail_access_denied(self, auth_client, test_engine, tmp_path):
        billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}",
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillOrphanedBilling:
    """Test cases where bill exists but parent billing was soft-deleted."""

    def _create_bill_then_delete_billing(self, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Soft-delete the billing
        with test_engine.connect() as conn:
            repo = SQLAlchemyBillingRepository(conn)
            repo.delete(billing.id)
        return billing, bill

    def test_detail_orphaned_billing(self, auth_client, test_engine, tmp_path):
        billing, bill = self._create_bill_then_delete_billing(test_engine, tmp_path)
        response = auth_client.get(
            f"/billings/{billing.uuid}/bills/{bill.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_form_orphaned_billing(self, auth_client, test_engine, tmp_path):
        billing, bill = self._create_bill_then_delete_billing(test_engine, tmp_path)
        response = auth_client.get(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_post_orphaned_billing(self, auth_client, test_engine, tmp_path, csrf_token):
        billing, bill = self._create_bill_then_delete_billing(test_engine, tmp_path)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
            data={"csrf_token": csrf_token, "items-TOTAL_FORMS": "0", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_regenerate_orphaned_billing(self, auth_client, test_engine, tmp_path, csrf_token):
        billing, bill = self._create_bill_then_delete_billing(test_engine, tmp_path)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/regenerate-pdf",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillEditEdgeCases:
    """Test bill edit form validation edge cases."""

    def test_edit_empty_description_skipped(self, auth_client, test_engine, tmp_path, csrf_token):
        """Items with empty description in formset are skipped."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "",
                    "notes": "",
                    "items-TOTAL_FORMS": "2",
                    "items-0-description": "",
                    "items-0-amount": "100",
                    "items-0-item_type": "fixed",
                    "items-1-description": "Rent",
                    "items-1-amount": "285000",
                    "items-1-item_type": "fixed",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_edit_invalid_item_type_falls_back(self, auth_client, test_engine, tmp_path, csrf_token):
        """Invalid item_type falls back to FIXED."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "",
                    "notes": "",
                    "items-TOTAL_FORMS": "1",
                    "items-0-description": "Rent",
                    "items-0-amount": "285000",
                    "items-0-item_type": "invalid_type",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_edit_with_extras(self, auth_client, test_engine, tmp_path, csrf_token):
        """Extras formset items with desc+amount get appended."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "",
                    "notes": "",
                    "items-TOTAL_FORMS": "1",
                    "items-0-description": "Rent",
                    "items-0-amount": "285000",
                    "items-0-item_type": "fixed",
                    "extras-TOTAL_FORMS": "1",
                    "extras-0-description": "Repair",
                    "extras-0-amount": "50,00",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillDeleteIdNone:
    def test_delete_bill_id_none(self, auth_client, test_engine, tmp_path, csrf_token):
        """Bill with id=None after retrieval returns error."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Mock get_bill_by_uuid to return a bill with id=None
        mock_bill = Bill(
            id=None,
            uuid=bill.uuid,
            billing_id=billing.id,
            reference_month="2025-03",
            total_amount=0,
        )
        with patch("web.routes.bill.get_bill_service") as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_bill_by_uuid.return_value = mock_bill
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillInvoiceS3Redirect:
    def test_invoice_s3_redirect(self, auth_client, test_engine, tmp_path, csrf_token):
        """When pdf_path is not a local file, redirect to presigned URL."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Set pdf_path to a non-local path (simulating S3)
        with test_engine.connect() as conn:
            from sqlalchemy import text

            conn.execute(
                text("UPDATE bills SET pdf_path = :path WHERE id = :id"),
                {"path": "s3-bucket/key.pdf", "id": bill.id},
            )
            conn.commit()
        # Mock get_invoice_url to return a URL
        with patch("web.routes.bill.get_bill_service") as mock_svc_fn:
            mock_svc = MagicMock()
            mock_bill = Bill(
                id=bill.id,
                uuid=bill.uuid,
                billing_id=billing.id,
                reference_month="2025-03",
                total_amount=0,
                pdf_path="s3-bucket/key.pdf",
            )
            mock_svc.get_bill_by_uuid.return_value = mock_bill
            mock_svc.get_invoice_url.return_value = "https://presigned-url.example.com/file.pdf"
            mock_svc_fn.return_value = mock_svc
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestReceiptUpload:
    def test_upload_pdf(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("receipt.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/bills/{bill.uuid}/edit" in response.headers.get("location", "")
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) >= 1
        assert logs[0].new_state["filename"] == "receipt.pdf"

    def test_upload_image(self, auth_client, test_engine, tmp_path, csrf_token):
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_upload_invalid_type(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("file.gif", b"GIF89a", "image/gif")},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_upload_empty_file(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("empty.pdf", b"", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_upload_no_file(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_upload_bill_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/receipts/upload",
            data={"csrf_token": csrf_token},
            files={"receipt_file": ("r.pdf", b"%PDF", "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_upload_billing_not_found(self, auth_client, test_engine, tmp_path, csrf_token):
        """When bill exists but billing is soft-deleted, should redirect."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Soft-delete billing
        with test_engine.connect() as conn:
            repo = SQLAlchemyBillingRepository(conn)
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
            data={"csrf_token": csrf_token},
            files={"receipt_file": ("r.pdf", b"%PDF", "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestReceiptDelete:
    def test_delete_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # Upload a receipt first
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("receipt.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            # Get receipts to find the UUID
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipt_repo = SQLAlchemyReceiptRepository(conn)
                receipts = receipt_repo.list_by_bill(bill.id)
            assert len(receipts) == 1
            receipt_uuid = receipts[0].uuid

            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipt_uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_DELETE)
        assert len(logs) >= 1
        assert logs[0].previous_state["filename"] == "receipt.pdf"

    def test_delete_receipt_not_found(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/nonexistent/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_delete_receipt_bill_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/receipts/r-uuid/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_receipt_billing_not_found(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Soft-delete billing
        with test_engine.connect() as conn:
            repo = SQLAlchemyBillingRepository(conn)
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/r-uuid/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestEditFormShowsReceipts:
    def test_edit_form_shows_receipts(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # Upload a receipt
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("receipt.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
            )
        assert response.status_code == 200
        assert "receipt.pdf" in response.text
        assert "Comprovantes" in response.text


class TestReceiptView:
    def test_view_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("proof.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipts = SQLAlchemyReceiptRepository(conn).list_by_bill(bill.id)
            assert len(receipts) == 1
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipts[0].uuid}",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]

    def test_view_receipt_not_found(self, auth_client, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/nonexistent",
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillGenerateWithReceipts:
    """Cover lines 105-120, 122, 136: receipt attachment during bill generation."""

    def test_generate_with_receipt_files(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-05",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("receipt.pdf", b"%PDF-test-receipt", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) >= 1

    def test_generate_skips_invalid_receipt_type(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover line 109-110: receipt with disallowed content_type is skipped."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-06",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("file.gif", b"GIF89a", "image/gif")},
                follow_redirects=False,
            )
        assert response.status_code == 302
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) == 0

    def test_generate_skips_oversized_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover lines 111-112: receipt exceeding MAX_RECEIPT_SIZE is skipped."""
        billing = create_billing_in_db(test_engine)
        from rentivo.models.receipt import MAX_RECEIPT_SIZE

        oversized = b"%PDF-" + b"x" * (MAX_RECEIPT_SIZE + 1)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-07",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("big.pdf", oversized, "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_generate_skips_empty_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover line 109: empty file_bytes is skipped."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-08",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("empty.pdf", b"", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestReceiptViewS3Redirect:
    """Cover line 445: receipt view redirects to presigned URL for S3."""

    def test_receipt_view_s3_redirect(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("proof.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipts = SQLAlchemyReceiptRepository(conn).list_by_bill(bill.id)
            assert len(receipts) == 1

        # Mock bill_service to return a non-local URL
        with patch("web.routes.bill.get_bill_service") as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_receipt_by_uuid.return_value = receipts[0]
            mock_svc.storage.get_url.return_value = "https://s3.example.com/receipt.pdf"
            mock_svc_fn.return_value = mock_svc
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipts[0].uuid}",
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "s3.example.com" in response.headers.get("location", "")


class TestReceiptUploadOversized:
    """Cover lines 488-489: file exceeding MAX_RECEIPT_SIZE."""

    def test_upload_oversized_file(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        from rentivo.models.receipt import MAX_RECEIPT_SIZE

        oversized = b"%PDF-" + b"x" * (MAX_RECEIPT_SIZE + 1)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("big.pdf", oversized, "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillGenerateExtrasValidation:
    """Cover branch 83->80: extras row that fails validation."""

    def test_generate_with_invalid_extras_skipped(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-09",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "2",
                    "extras-0-description": "",
                    "extras-0-amount": "50,00",
                    "extras-1-description": "Valid extra",
                    "extras-1-amount": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillEditExtrasValidation:
    """Cover branch 258->255: extras row with invalid amount in edit."""

    def test_edit_with_invalid_extras_skipped(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "",
                    "notes": "",
                    "items-TOTAL_FORMS": "1",
                    "items-0-description": "Rent",
                    "items-0-amount": "285000",
                    "items-0-item_type": "fixed",
                    "extras-TOTAL_FORMS": "2",
                    "extras-0-description": "",
                    "extras-0-amount": "50,00",
                    "extras-1-description": "Valid",
                    "extras-1-amount": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillGenerateVariableIdNone:
    """Cover branch 74->71: variable item with id=None is skipped."""

    def test_generate_variable_item_id_none(self, auth_client, test_engine, tmp_path, csrf_token):
        from rentivo.models.billing import Billing, BillingItem, ItemType

        billing = create_billing_in_db(test_engine)
        # Create a billing with a variable item that has id=None
        mock_billing = Billing(
            id=billing.id,
            uuid=billing.uuid,
            name=billing.name,
            owner_type=billing.owner_type,
            owner_id=billing.owner_id,
            items=[
                BillingItem(id=None, description="NoIdWater", amount=0, item_type=ItemType.VARIABLE),
                BillingItem(id=1, description="Aluguel", amount=285000, item_type=ItemType.FIXED),
            ],
        )
        mock_bill = Bill(
            id=1,
            uuid="gen-uuid",
            billing_id=billing.id,
            reference_month="2025-10",
            total_amount=285000,
        )
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            with (
                patch("web.routes.bill.get_billing_service") as mock_billing_svc,
                patch("web.routes.bill.get_bill_service") as mock_bill_svc,
            ):
                mock_billing_svc.return_value.get_billing_by_uuid.return_value = mock_billing
                mock_bill_svc.return_value.generate_bill.return_value = mock_bill
                response = auth_client.post(
                    f"/billings/{billing.uuid}/bills/generate",
                    data={
                        "csrf_token": csrf_token,
                        "reference_month": "2025-10",
                        "due_date": "",
                        "notes": "",
                        "variable_None": "50,00",
                        "extras-TOTAL_FORMS": "0",
                    },
                    follow_redirects=False,
                )
        assert response.status_code == 302


class TestBillGenerateNonFileUpload:
    """Cover line 106: receipt_files entry that is not an UploadFile."""

    def test_generate_with_non_file_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            # Send receipt_files as a regular form field (string), not a file
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-11",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                    "receipt_files": "not_a_file",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestDetailShowsReceipts:
    def test_detail_shows_receipts(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # Upload a receipt
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_file": ("proof.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}",
            )
        assert response.status_code == 200
        assert "proof.pdf" in response.text
        assert "Comprovantes" in response.text
