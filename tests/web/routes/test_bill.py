from unittest.mock import patch

from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
)
from landlord.services.bill_service import BillService
from landlord.storage.local import LocalStorage


def _create_billing_in_db(engine):
    with engine.connect() as conn:
        repo = SQLAlchemyBillingRepository(conn)
        billing = repo.create(
            Billing(
                name="Apt 101",
                description="",
                pix_key="",
                items=[
                    BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED),
                    BillingItem(description="Água", amount=0, item_type=ItemType.VARIABLE),
                ],
            )
        )
    return billing


def _generate_bill_in_db(engine, billing, tmp_path):
    with engine.connect() as conn:
        bill_repo = SQLAlchemyBillRepository(conn)
        storage = LocalStorage(str(tmp_path))
        service = BillService(bill_repo, storage)
        bill = service.generate_bill(
            billing=billing,
            reference_month="2025-03",
            variable_amounts={},
            extras=[],
            notes="note",
            due_date="10/04/2025",
        )
    return bill


class TestBillGenerate:
    def test_generate_form(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.get(f"/bills/{billing.uuid}/generate")
        assert response.status_code == 200

    def test_generate_form_not_found(self, auth_client):
        response = auth_client.get("/bills/nonexistent/generate", follow_redirects=False)
        assert response.status_code == 302

    def test_generate_success(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            response = auth_client.post(
                f"/bills/{billing.uuid}/generate",
                data={
                    "reference_month": "2025-03",
                    "due_date": "10/04/2025",
                    "notes": "test",
                    "extras-TOTAL_FORMS": "0",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_generate_no_reference(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/bills/{billing.uuid}/generate",
            data={
                "reference_month": "",
                "extras-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_generate_billing_not_found(self, auth_client):
        response = auth_client.post(
            "/bills/nonexistent/generate",
            data={"reference_month": "2025-03", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillDetail:
    def test_detail(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(f"/bills/{bill.uuid}")
        assert response.status_code == 200

    def test_detail_not_found(self, auth_client):
        response = auth_client.get("/bills/nonexistent", follow_redirects=False)
        assert response.status_code == 302


class TestBillEdit:
    def test_edit_form(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(f"/bills/{bill.uuid}/edit")
        assert response.status_code == 200

    def test_edit_form_not_found(self, auth_client):
        response = auth_client.get("/bills/nonexistent/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_submit(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/bills/{bill.uuid}/edit",
                data={
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

    def test_edit_not_found(self, auth_client):
        response = auth_client.post(
            "/bills/nonexistent/edit",
            data={"items-TOTAL_FORMS": "0", "extras-TOTAL_FORMS": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillRegeneratePdf:
    def test_regenerate(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/bills/{bill.uuid}/regenerate-pdf",
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_regenerate_not_found(self, auth_client):
        response = auth_client.post(
            "/bills/nonexistent/regenerate-pdf",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillTogglePaid:
    def test_toggle_paid(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/bills/{bill.uuid}/toggle-paid",
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_toggle_paid_not_found(self, auth_client):
        response = auth_client.post(
            "/bills/nonexistent/toggle-paid",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillDelete:
    def test_delete(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.post(
                f"/bills/{bill.uuid}/delete",
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_delete_not_found(self, auth_client):
        response = auth_client.post(
            "/bills/nonexistent/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillInvoice:
    def test_invoice_local_file(self, auth_client, test_engine, tmp_path):
        billing = _create_billing_in_db(test_engine)
        with patch("web.deps.get_storage", return_value=LocalStorage(str(tmp_path))):
            bill = _generate_bill_in_db(test_engine, billing, tmp_path)
            response = auth_client.get(
                f"/bills/{bill.uuid}/invoice",
                follow_redirects=False,
            )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/pdf")

    def test_invoice_not_found(self, auth_client):
        response = auth_client.get(
            "/bills/nonexistent/invoice",
            follow_redirects=False,
        )
        assert response.status_code == 302
