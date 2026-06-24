from unittest.mock import MagicMock, patch

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyUserRepository
from rentivo.storage.local import LocalStorage
from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs, get_test_user_id
from web.services_container import RequestServices


def _create_other_user_billing(test_engine):
    """Create a billing owned by a different user (not the logged-in test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn, Base64Backend())
        other = user_repo.create(User(email="bill_other@example.com", password_hash="h"))
        user_repo.update_pix(other.id, "other@pix.com", "Other Merchant", "Campinas")
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

    def test_detail_renders_policy_status_menu(self, auth_client, test_engine, tmp_path, csrf_token):
        """REN-40: the legacy <select onchange> is replaced by the policy-driven
        action bar (web/bill_transitions.py). A 'sent' bill exposes the dominant
        "Marcar como pago" primary action wired to the shared confirm dialog, plus
        an "Alterar status" menu of the rarer moves."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
                data={"csrf_token": csrf_token, "status": "sent"},
                follow_redirects=False,
            )
            html = auth_client.get(f"/billings/{billing.uuid}/bills/{bill.uuid}").text

        # Legacy flat select with silent JS submit is gone.
        assert 'onchange="this.form.submit()"' not in html
        # Dominant next step + its consequential confirm wiring (primary variant).
        assert "Marcar como pago" in html
        assert 'data-confirm-variant="primary"' in html
        assert 'data-confirm-body="Isto marca a fatura como paga' in html
        # Rarer moves live behind the status menu; cancel is a danger confirm.
        assert 'class="status-menu"' in html
        assert 'data-confirm-variant="danger"' in html
        assert 'name="status" value="cancelled"' in html


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

    def test_edit_form_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path):
        """Vuln 1: GET /edit on another user's bill must be denied."""
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            response = auth_client.get(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/edit",
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_edit_post_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 2: POST /edit on another user's bill must not mutate it."""
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            original_notes = bill.notes
            response = auth_client.post(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/edit",
                data={
                    "csrf_token": csrf_token,
                    "due_date": "15/04/2025",
                    "notes": "attacker was here",
                    "items-TOTAL_FORMS": "1",
                    "items-0-description": "hacked",
                    "items-0-amount": "0",
                    "items-0-item_type": "fixed",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        # Bill must be unchanged
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillRepository(conn, Base64Backend()).get_by_uuid(bill.uuid)
        assert reloaded.notes == original_notes


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

    def test_regenerate_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 6: can't force-regenerate another user's bill PDF."""
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            original_pdf_path = bill.pdf_path
            response = auth_client.post(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/regenerate-pdf",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillRepository(conn, Base64Backend()).get_by_uuid(bill.uuid)
        assert reloaded.pdf_path == original_pdf_path


class TestBillChangeStatus:
    def test_change_status(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
                data={"csrf_token": csrf_token, "status": "paid"},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_change_status_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/change-status",
            data={"csrf_token": csrf_token, "status": "paid"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillChangeStatusEdgeCases:
    def test_change_status_billing_not_found(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover lines 363-364: bill found but billing soft-deleted."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Soft-delete the billing
        with test_engine.connect() as conn:
            repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
            data={"csrf_token": csrf_token, "status": "paid"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_change_status_access_denied(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover lines 368-369: user lacks permission to manage bills."""
        billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
            data={"csrf_token": csrf_token, "status": "paid"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_change_status_invalid_status(self, auth_client, test_engine, tmp_path, csrf_token):
        """Cover lines 377-379: invalid status value raises ValueError."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
                data={"csrf_token": csrf_token, "status": "totally_invalid"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/bills/{bill.uuid}" in response.headers["location"]


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

    def test_delete_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 3: delete on another user's bill must be refused; bill persists."""
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            response = auth_client.post(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillRepository(conn, Base64Backend()).get_by_uuid(bill.uuid)
        assert reloaded is not None, "victim's bill must not be soft-deleted"


class TestBillInvoice:
    def test_invoice_local_file(self, auth_client, test_engine, tmp_path):
        billing = create_billing_in_db(test_engine)
        # The invoice GET now resolves the PDF through the active storage backend
        # (LocalStorage.get_ref -> _safe_path), so the request-time backend must
        # share generate_bill_in_db's base_dir. Patch where the request builds it
        # (web.services_container.get_storage), not just the web.deps re-export.
        with patch("web.services_container.get_storage", return_value=LocalStorage(str(tmp_path))):
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

    def test_invoice_rejects_unauthorized_user(self, auth_client, test_engine, tmp_path):
        """Regression: GET /invoice must check can_view_billing."""
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            response = auth_client.get(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        # Redirected to "/" with access-denied flash, not 200 FileResponse
        assert response.status_code == 302
        assert response.headers.get("location") == "/"

    def test_invoice_redirects_when_billing_missing(self, auth_client, test_engine, tmp_path):
        """Cover the 'billing not found' branch in bill_invoice."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            mock_billing_svc = MagicMock()
            mock_billing_svc.get_billing.return_value = None
            with patch.object(RequestServices, "billing", new=mock_billing_svc):
                response = auth_client.get(
                    f"/billings/{billing.uuid}/bills/{bill.uuid}/invoice",
                    follow_redirects=False,
                )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"

    def test_receipt_view_bill_uuid_mismatch(self, auth_client, test_engine, tmp_path):
        """Cover receipt_view branch where bill.uuid doesn't match the URL."""
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            with test_engine.connect() as conn:
                receipt = SQLAlchemyReceiptRepository(conn, Base64Backend()).create(
                    Receipt(
                        bill_id=bill.id,
                        filename="r.pdf",
                        storage_key="stub.pdf",
                        content_type="application/pdf",
                        file_size=4,
                    )
                )
        response = auth_client.get(
            f"/billings/{billing.uuid}/bills/wrong-bill-uuid/receipts/{receipt.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"

    def test_receipt_view_billing_uuid_mismatch(self, auth_client, test_engine, tmp_path):
        """Cover receipt_view branch where billing.uuid doesn't match the URL."""
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            with test_engine.connect() as conn:
                receipt = SQLAlchemyReceiptRepository(conn, Base64Backend()).create(
                    Receipt(
                        bill_id=bill.id,
                        filename="r.pdf",
                        storage_key="stub.pdf",
                        content_type="application/pdf",
                        file_size=4,
                    )
                )
        response = auth_client.get(
            f"/billings/wrong-billing-uuid/bills/{bill.uuid}/receipts/{receipt.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"

    def test_receipt_view_rejects_unauthorized_user(self, auth_client, test_engine, tmp_path, csrf_token):
        """Regression: GET /receipts/<uuid> must check can_view_billing."""
        # Owner uploads a receipt to their own bill
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            with test_engine.connect() as conn:
                receipt = SQLAlchemyReceiptRepository(conn, Base64Backend()).create(
                    Receipt(
                        bill_id=bill.id,
                        filename="r.pdf",
                        storage_key="stub.pdf",
                        content_type="application/pdf",
                        file_size=4,
                    )
                )

        response = auth_client.get(
            f"/billings/{other_billing.uuid}/bills/{bill.uuid}/receipts/{receipt.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"


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


class TestBillChangeStatusMultiple:
    def test_change_status_multiple_transitions(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # First change: draft → paid
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
                data={"csrf_token": csrf_token, "status": "paid"},
                follow_redirects=False,
            )
            # Second change: paid → draft
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/change-status",
                data={"csrf_token": csrf_token, "status": "draft"},
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
        assert response.headers["location"] == "/"

    def test_generate_post_access_denied(self, auth_client, test_engine, csrf_token):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/generate",
            data={"csrf_token": csrf_token, "reference_month": "2025-03", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

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
            repo = SQLAlchemyBillingRepository(conn, Base64Backend())
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
        mock_svc = MagicMock()
        mock_svc.get_bill_by_uuid.return_value = mock_bill
        with patch.object(RequestServices, "bill", new=mock_svc):
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
        mock_svc = MagicMock()
        mock_bill = Bill(
            id=bill.id,
            uuid=bill.uuid,
            billing_id=billing.id,
            reference_month="2025-03",
            total_amount=0,
            pdf_path="s3-bucket/key.pdf",
        )
        from rentivo.storage.base import FileRef

        mock_svc.get_bill_by_uuid.return_value = mock_bill
        mock_svc.get_invoice_ref.return_value = FileRef(
            kind="url", location="https://presigned-url.example.com/file.pdf"
        )
        with patch.object(RequestServices, "bill", new=mock_svc):
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "presigned-url.example.com" in response.headers.get("location", "")


class TestReceiptUpload:
    def test_upload_pdf(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": ("receipt.pdf", b"%PDF-test", "application/pdf")},
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
                files={"receipt_files": ("photo.jpg", jpeg_bytes, "image/jpeg")},
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
                files={"receipt_files": ("file.gif", b"GIF89a", "image/gif")},
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
                files={"receipt_files": ("empty.pdf", b"", "application/pdf")},
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
            files={"receipt_files": ("r.pdf", b"%PDF", "application/pdf")},
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
            repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
            data={"csrf_token": csrf_token},
            files={"receipt_files": ("r.pdf", b"%PDF", "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_upload_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 4: uploading a receipt to another user's bill must be refused."""
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
            response = auth_client.post(
                f"/billings/{other_billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": ("r.pdf", b"%PDF-malicious", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        with test_engine.connect() as conn:
            assert SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id) == []


class TestReceiptUploadMultiple:
    def test_upload_multiple_files(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files=[
                    ("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf")),
                    ("receipt_files", ("b.pdf", b"%PDF-b", "application/pdf")),
                ],
                follow_redirects=False,
            )
        assert response.status_code == 302
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) >= 2

    def test_upload_multiple_enqueues_single_pdf_render(
        self, auth_client, test_engine, tmp_path, csrf_token, monkeypatch
    ):
        """Uploading N receipts at once must enqueue exactly one pdf.render.

        Regression: attach_receipts rendered per file, so N receipts raced N
        pdf.render jobs on the same storage key. The batch must render once.
        """
        from rentivo.jobs.base import Job
        from rentivo.services.job_service import JobService

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)

            sent: list[str] = []

            def _capture(self, job_type, payload, **kwargs):
                sent.append(job_type)
                return Job(id=1, ulid="01HXYZ", job_type=job_type, payload=payload, attempts=0, max_attempts=5)

            monkeypatch.setattr(JobService, "enqueue", _capture)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files=[
                    ("receipt_files", ("a.pdf", b"%PDF-a", "application/pdf")),
                    ("receipt_files", ("b.pdf", b"%PDF-b", "application/pdf")),
                    ("receipt_files", ("c.pdf", b"%PDF-c", "application/pdf")),
                ],
                follow_redirects=False,
            )
        assert response.status_code == 302
        pdf_jobs = [j for j in sent if j == "pdf.render"]
        assert len(pdf_jobs) == 1, f"expected exactly 1 pdf.render, got {len(pdf_jobs)}"

    def test_upload_all_skipped(self, auth_client, test_engine, tmp_path, csrf_token):
        """All files are invalid type — skipped > 0, attached == 0."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files=[
                    ("receipt_files", ("a.gif", b"GIF89a", "image/gif")),
                    ("receipt_files", ("b.gif", b"GIF89a", "image/gif")),
                ],
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
                files={"receipt_files": ("receipt.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            # Get receipts to find the UUID
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipt_repo = SQLAlchemyReceiptRepository(conn, Base64Backend())
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
            repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/r-uuid/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_receipt_access_denied_for_other_users_bill(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 5: can't delete a receipt on another user's bill."""
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
        with test_engine.connect() as conn:
            receipt_repo = SQLAlchemyReceiptRepository(conn, Base64Backend())
            victim_receipt = receipt_repo.create(
                Receipt(
                    bill_id=bill.id,
                    filename="victim.pdf",
                    storage_key="k",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=0,
                )
            )
        response = auth_client.post(
            f"/billings/{other_billing.uuid}/bills/{bill.uuid}/receipts/{victim_receipt.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        with test_engine.connect() as conn:
            assert SQLAlchemyReceiptRepository(conn, Base64Backend()).get_by_uuid(victim_receipt.uuid) is not None

    def test_delete_receipt_cross_bill_rejected(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 5 amplification: supplying attacker's own bill/billing uuids but a victim receipt uuid."""
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        # Attacker's own bill (auth_client is the logged-in test user)
        attacker_billing = create_billing_in_db(test_engine)
        other_billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            attacker_bill = generate_bill_in_db(test_engine, attacker_billing, tmp_path)
            victim_bill = generate_bill_in_db(test_engine, other_billing, tmp_path)
        with test_engine.connect() as conn:
            receipt_repo = SQLAlchemyReceiptRepository(conn, Base64Backend())
            victim_receipt = receipt_repo.create(
                Receipt(
                    bill_id=victim_bill.id,
                    filename="victim.pdf",
                    storage_key="k",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=0,
                )
            )
        # Attacker passes their own bill/billing UUIDs but the victim's receipt UUID.
        response = auth_client.post(
            f"/billings/{attacker_billing.uuid}/bills/{attacker_bill.uuid}/receipts/{victim_receipt.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with test_engine.connect() as conn:
            assert SQLAlchemyReceiptRepository(conn, Base64Backend()).get_by_uuid(victim_receipt.uuid) is not None


class TestReceiptRedirectSafety:
    def test_upload_next_external_url_ignored(self, auth_client, test_engine, tmp_path, csrf_token):
        """Vuln 8: `next` form param pointing off-site must not be honoured."""
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token, "next": "https://evil.example/phish"},
                files={"receipt_files": ("r.pdf", b"%PDF", "application/pdf")},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert not response.headers["location"].startswith("https://evil.example")
        assert response.headers["location"].startswith(f"/billings/{billing.uuid}/bills/{bill.uuid}/edit")

    def test_delete_next_protocol_relative_ignored(self, auth_client, test_engine, tmp_path, csrf_token):
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        with test_engine.connect() as conn:
            receipt = SQLAlchemyReceiptRepository(conn, Base64Backend()).create(
                Receipt(
                    bill_id=bill.id,
                    filename="r.pdf",
                    storage_key="k",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=0,
                )
            )
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipt.uuid}/delete",
                data={"csrf_token": csrf_token, "next": "//evil.example/"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert not response.headers["location"].startswith("//evil.example")


class TestEditFormShowsReceipts:
    def test_edit_form_shows_receipts(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # Upload a receipt
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": ("receipt.pdf", b"%PDF-test", "application/pdf")},
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
                files={"receipt_files": ("proof.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipts = SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id)
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

    def test_generate_with_receipt_enqueues_single_pdf_render(
        self, auth_client, test_engine, tmp_path, csrf_token, monkeypatch
    ):
        """A bill created WITH a receipt must enqueue exactly one pdf.render.

        Regression: the create flow rendered once in generate_bill and again in
        add_receipt, so two pdf.render jobs raced on the same storage key (under
        the Temporal driver they run concurrently). The single surviving render
        must run after the receipt is attached so the PDF includes it.
        """
        from rentivo.jobs.base import Job
        from rentivo.services.job_service import JobService

        billing = create_billing_in_db(test_engine)

        sent: list[dict] = []

        def _capture(self, job_type, payload, **kwargs):
            sent.append({"job_type": job_type, "payload": payload, "kwargs": kwargs})
            return Job(id=1, ulid="01HXYZ", job_type=job_type, payload=payload, attempts=0, max_attempts=5)

        monkeypatch.setattr(JobService, "enqueue", _capture)

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
        pdf_jobs = [s for s in sent if s["job_type"] == "pdf.render"]
        assert len(pdf_jobs) == 1, f"expected exactly 1 pdf.render, got {len(pdf_jobs)}"

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


class TestBillGenerateSkipWarning:
    """Deliberate behavior change (Plan E): bill_generate no longer drops
    invalid receipt files silently — it flashes the same skip warning as
    receipt_upload."""

    def test_generate_flashes_skip_warning_for_invalid_receipt(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-10",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("file.gif", b"GIF89a", "image/gif")},
                follow_redirects=True,
            )
        assert response.status_code == 200
        assert "1 arquivo(s) ignorado(s)" in response.text
        assert "Fatura gerada com sucesso!" in response.text
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) == 0

    def test_generate_with_valid_receipt_has_no_skip_warning(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-11",
                    "due_date": "",
                    "notes": "",
                    "extras-TOTAL_FORMS": "0",
                },
                files={"receipt_files": ("receipt.pdf", b"%PDF-test-receipt", "application/pdf")},
                follow_redirects=True,
            )
        assert response.status_code == 200
        assert "ignorado(s)" not in response.text
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_UPLOAD)
        assert len(logs) == 1
        assert logs[0].new_state["filename"] == "receipt.pdf"
        assert logs[0].new_state["bill_uuid"] != ""
        assert logs[0].new_state["billing_uuid"] == billing.uuid


class TestReceiptViewS3Redirect:
    """Cover line 445: receipt view redirects to presigned URL for S3."""

    def test_receipt_view_s3_redirect(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": ("proof.pdf", b"%PDF-test-data", "application/pdf")},
                follow_redirects=False,
            )
            from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

            with test_engine.connect() as conn:
                receipts = SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id)
            assert len(receipts) == 1

        # Mock bill_service to return a non-local URL
        mock_svc = MagicMock()
        from rentivo.storage.base import FileRef

        mock_svc.get_receipt_by_uuid.return_value = receipts[0]
        mock_svc.get_bill_by_uuid.return_value = bill
        mock_svc.get_receipt_ref.return_value = FileRef(kind="url", location="https://s3.example.com/receipt.pdf")
        with patch.object(RequestServices, "bill", new=mock_svc):
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
                files={"receipt_files": ("big.pdf", oversized, "application/pdf")},
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
            mock_billing_svc = MagicMock()
            mock_billing_svc.get_billing_by_uuid.return_value = mock_billing
            mock_bill_svc = MagicMock()
            mock_bill_svc.generate_bill.return_value = mock_bill
            with (
                patch.object(RequestServices, "billing", new=mock_billing_svc),
                patch.object(RequestServices, "bill", new=mock_bill_svc),
            ):
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
                files={"receipt_files": ("proof.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
            response = auth_client.get(
                f"/billings/{billing.uuid}/bills/{bill.uuid}",
            )
        assert response.status_code == 200
        assert "proof.pdf" in response.text
        assert "Comprovantes" in response.text


class TestReceiptReorder:
    def _upload_receipts(self, auth_client, billing, bill, csrf_token, count=2):
        """Upload N receipts and return their UUIDs."""

        for i in range(count):
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": (f"receipt_{i}.pdf", b"%PDF-test-" + bytes([i]), "application/pdf")},
                follow_redirects=False,
            )

    def _get_receipt_uuids(self, test_engine, bill_id):
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        with test_engine.connect() as conn:
            receipts = SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill_id)
        return [r.uuid for r in receipts]

    def test_reorder_success(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            self._upload_receipts(auth_client, billing, bill, csrf_token, count=2)
            uuids = self._get_receipt_uuids(test_engine, bill.id)
            # Reverse the order
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
                json={"order": list(reversed(uuids))},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        logs = get_audit_logs(test_engine, AuditEventType.RECEIPT_REORDER)
        assert len(logs) >= 1

    def test_reorder_bill_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/x/bills/nonexistent/receipts/reorder",
            json={"order": []},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 404

    def test_reorder_billing_not_found(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        # Soft-delete billing
        with test_engine.connect() as conn:
            repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            repo.delete(billing.id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
            json={"order": []},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 404

    def test_reorder_access_denied(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = _create_other_user_billing(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
            json={"order": []},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 403

    def test_reorder_invalid_json(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
                content=b"not json",
                headers={"content-type": "application/json", "X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 400
        assert "JSON" in response.json()["error"]

    def test_reorder_order_not_a_list(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
                json={"order": "not-a-list"},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 400
        assert "lista" in response.json()["error"]

    def test_reorder_invalid_uuid(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            self._upload_receipts(auth_client, billing, bill, csrf_token, count=1)
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
                json={"order": ["nonexistent-uuid"]},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 400


def _clear_test_user_pix(test_engine):
    """Wipe PIX on the logged-in test user so billing_needs_setup returns True."""
    user_id = get_test_user_id(test_engine)
    with test_engine.connect() as conn:
        SQLAlchemyUserRepository(conn, Base64Backend()).update_pix(user_id, "", "", "")


class TestBillPixNotConfigured:
    """Every state-changing route must redirect when PIX is not configured."""

    def test_generate_form_redirects(self, auth_client, test_engine):
        _clear_test_user_pix(test_engine)
        billing = create_billing_in_db(test_engine)
        r = auth_client.get(f"/billings/{billing.uuid}/bills/generate", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == f"/billings/{billing.uuid}"

    def test_generate_post_redirects(self, auth_client, test_engine, csrf_token):
        _clear_test_user_pix(test_engine)
        billing = create_billing_in_db(test_engine)
        r = auth_client.post(
            f"/billings/{billing.uuid}/bills/generate",
            data={"csrf_token": csrf_token, "reference_month": "2025-03", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == f"/billings/{billing.uuid}"

    def test_edit_post_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        _clear_test_user_pix(test_engine)
        r = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/edit",
            data={"csrf_token": csrf_token, "items-TOTAL_FORMS": "0", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == f"/billings/{billing.uuid}"

    def test_regenerate_pdf_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        _clear_test_user_pix(test_engine)
        r = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/regenerate-pdf",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == f"/billings/{billing.uuid}"

    def test_receipt_upload_redirects(self, auth_client, test_engine, tmp_path, csrf_token):
        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        _clear_test_user_pix(test_engine)
        r = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
            data={"csrf_token": csrf_token},
            files={"receipt_files": ("r.pdf", b"%PDF-1.4", "application/pdf")},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == f"/billings/{billing.uuid}"


class TestBillDeleteCrossBilling:
    def test_delete_rejects_bill_when_billing_uuid_mismatches(self, auth_client, test_engine, tmp_path, csrf_token):
        """bill_delete must reject URLs whose billing_uuid doesn't match the bill's actual billing."""
        billing_a = create_billing_in_db(test_engine, name="A")
        billing_b = create_billing_in_db(test_engine, name="B")
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing_a, tmp_path)
        r = auth_client.post(
            f"/billings/{billing_b.uuid}/bills/{bill.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/"
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        with test_engine.connect() as conn:
            assert SQLAlchemyBillRepository(conn, Base64Backend()).get_by_uuid(bill.uuid) is not None


class TestReceiptDeleteEnqueuesS3Delete:
    def test_receipt_delete_enqueues_s3_delete_job(self, auth_client, csrf_token, monkeypatch, test_engine, tmp_path):
        """Receipt-delete must enqueue exactly one s3.delete job for the receipt's storage_key."""
        from rentivo.jobs.base import Job
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository
        from rentivo.services.job_service import JobService

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                data={"csrf_token": csrf_token},
                files={"receipt_files": ("r.pdf", b"%PDF-test", "application/pdf")},
                follow_redirects=False,
            )
            with test_engine.connect() as conn:
                receipts = SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id)
            assert len(receipts) == 1
            receipt = receipts[0]

            sent: list[dict] = []

            def _capture(self, job_type, payload, **kwargs):
                sent.append({"job_type": job_type, "payload": payload, "kwargs": kwargs})
                return Job(
                    id=1,
                    ulid="01HXYZ",
                    job_type=job_type,
                    payload=payload,
                    attempts=0,
                    max_attempts=5,
                )

            monkeypatch.setattr(JobService, "enqueue", _capture)

            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipt.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code in (200, 302)

        s3_jobs = [s for s in sent if s["job_type"] == "s3.delete"]
        assert len(s3_jobs) == 1
        assert s3_jobs[0]["payload"]["key"] == receipt.storage_key
        assert s3_jobs[0]["kwargs"]["source"] == "web"


class TestBillDeleteEnqueuesS3Delete:
    def _setup_bill_with_receipts(self, auth_client, csrf_token, test_engine, tmp_path, count):
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            for i in range(count):
                auth_client.post(
                    f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                    data={"csrf_token": csrf_token},
                    files={"receipt_files": (f"r{i}.pdf", b"%PDF-test", "application/pdf")},
                    follow_redirects=False,
                )
        with test_engine.connect() as conn:
            receipts = SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id)
        return billing, bill, receipts

    def test_bill_delete_enqueues_pdf_and_receipts(self, auth_client, csrf_token, monkeypatch, test_engine, tmp_path):
        """Bill delete enqueues one s3.delete per attached receipt + one for the PDF."""
        from rentivo.jobs.base import Job
        from rentivo.services.job_service import JobService

        billing, bill, receipts = self._setup_bill_with_receipts(
            auth_client, csrf_token, test_engine, tmp_path, count=2
        )
        assert len(receipts) == 2

        sent: list[dict] = []

        def _capture(self, job_type, payload, **kwargs):
            sent.append({"job_type": job_type, "payload": payload})
            return Job(
                id=1,
                ulid="01HXYZ",
                job_type=job_type,
                payload=payload,
                attempts=0,
                max_attempts=5,
            )

        monkeypatch.setattr(JobService, "enqueue", _capture)

        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code in (200, 302)

        s3_keys = [s["payload"]["key"] for s in sent if s["job_type"] == "s3.delete"]
        # 2 receipts + 1 bill PDF = 3 jobs
        assert len(s3_keys) == 3
        assert bill.pdf_path in s3_keys
        for receipt in receipts:
            assert receipt.storage_key in s3_keys

    def test_bill_delete_with_empty_pdf_path_skips_pdf_job(
        self, auth_client, csrf_token, monkeypatch, test_engine, tmp_path
    ):
        from sqlalchemy import text

        from rentivo.jobs.base import Job
        from rentivo.services.job_service import JobService

        billing, bill, receipts = self._setup_bill_with_receipts(
            auth_client, csrf_token, test_engine, tmp_path, count=1
        )
        assert len(receipts) == 1
        # Force pdf_path empty in the DB (simulates a render-failed bill).
        with test_engine.connect() as conn:
            conn.execute(
                text("UPDATE bills SET pdf_path = '' WHERE id = :id"),
                {"id": bill.id},
            )
            conn.commit()

        sent: list[dict] = []

        def _capture(self, job_type, payload, **kwargs):
            sent.append({"job_type": job_type, "payload": payload})
            return Job(
                id=1,
                ulid="01HXYZ",
                job_type=job_type,
                payload=payload,
                attempts=0,
                max_attempts=5,
            )

        monkeypatch.setattr(JobService, "enqueue", _capture)

        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code in (200, 302)

        s3_keys = [s["payload"]["key"] for s in sent if s["job_type"] == "s3.delete"]
        assert len(s3_keys) == 1
        assert s3_keys[0] == receipts[0].storage_key


class TestBillDetailCrossBilling:
    def test_detail_rejects_mismatched_billing_uuid(self, auth_client, test_engine, tmp_path):
        """Deliberate fix: bill_detail must reject URLs pairing the bill with an unrelated billing."""
        billing_a = create_billing_in_db(test_engine, name="A")
        billing_b = create_billing_in_db(test_engine, name="B")
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing_a, tmp_path)
        response = auth_client.get(
            f"/billings/{billing_b.uuid}/bills/{bill.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"


class TestBillChangeStatusCrossBilling:
    def test_change_status_rejects_mismatched_billing_uuid(self, auth_client, test_engine, tmp_path, csrf_token):
        """Deliberate fix: change-status must reject URLs pairing the bill with an unrelated billing."""
        billing_a = create_billing_in_db(test_engine, name="A")
        billing_b = create_billing_in_db(test_engine, name="B")
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing_a, tmp_path)
        response = auth_client.post(
            f"/billings/{billing_b.uuid}/bills/{bill.uuid}/change-status",
            data={"csrf_token": csrf_token, "status": "paid"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"
        from rentivo.repositories.sqlalchemy import SQLAlchemyBillRepository

        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillRepository(conn, Base64Backend()).get_by_uuid(bill.uuid)
        assert reloaded.status == "draft"


class TestBillInvoiceCrossBilling:
    def test_invoice_rejects_mismatched_billing_uuid(self, auth_client, test_engine, tmp_path):
        """Deliberate fix: invoice download must reject URLs pairing the bill with an unrelated billing."""
        billing_a = create_billing_in_db(test_engine, name="A")
        billing_b = create_billing_in_db(test_engine, name="B")
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing_a, tmp_path)
            response = auth_client.get(
                f"/billings/{billing_b.uuid}/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers["location"] == "/"


class TestBillInvoiceNoPdf:
    def test_invoice_redirects_when_bill_has_no_pdf(self, auth_client, test_engine, tmp_path):
        """Keeps the 'Fatura sem PDF' branch covered now that the guard owns bill-not-found."""
        from sqlalchemy import text

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        with test_engine.connect() as conn:
            conn.execute(text("UPDATE bills SET pdf_path = '' WHERE id = :id"), {"id": bill.id})
            conn.commit()
        response = auth_client.get(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/invoice",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"


class TestReceiptReorderCrossBilling:
    def test_reorder_rejects_mismatched_billing_uuid(self, auth_client, test_engine, tmp_path, csrf_token):
        """Deliberate fix: the JSON reorder endpoint must reject mismatched billing uuids with 404."""
        billing_a = create_billing_in_db(test_engine, name="A")
        billing_b = create_billing_in_db(test_engine, name="B")
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing_a, tmp_path)
        response = auth_client.post(
            f"/billings/{billing_b.uuid}/bills/{bill.uuid}/receipts/reorder",
            json={"order": []},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 404


class TestReceiptOpsWithoutPix:
    """Deliberate change: PIX setup no longer gates receipt deletion or reordering."""

    def test_receipt_delete_succeeds_without_pix(self, auth_client, test_engine, tmp_path, csrf_token):
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
        with test_engine.connect() as conn:
            receipt = SQLAlchemyReceiptRepository(conn, Base64Backend()).create(
                Receipt(
                    bill_id=bill.id,
                    filename="r.pdf",
                    storage_key="k",
                    content_type="application/pdf",
                    file_size=10,
                    sort_order=0,
                )
            )
        _clear_test_user_pix(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/{receipt.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/billings/{billing.uuid}/bills/{bill.uuid}/edit"
        with test_engine.connect() as conn:
            assert SQLAlchemyReceiptRepository(conn, Base64Backend()).get_by_uuid(receipt.uuid) is None

    def test_receipt_reorder_succeeds_without_pix(self, auth_client, test_engine, tmp_path, csrf_token):
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        billing = create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = generate_bill_in_db(test_engine, billing, tmp_path)
            # Upload two receipts while PIX is still configured.
            for i in range(2):
                auth_client.post(
                    f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/upload",
                    data={"csrf_token": csrf_token},
                    files={"receipt_files": (f"r{i}.pdf", b"%PDF-" + bytes([i]), "application/pdf")},
                    follow_redirects=False,
                )
        with test_engine.connect() as conn:
            uuids = [r.uuid for r in SQLAlchemyReceiptRepository(conn, Base64Backend()).list_by_bill(bill.id)]
        assert len(uuids) == 2
        _clear_test_user_pix(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/{bill.uuid}/receipts/reorder",
            json={"order": list(reversed(uuids))},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
