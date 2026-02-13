from datetime import datetime
from unittest.mock import MagicMock, patch

from landlord.models.bill import SP_TZ, Bill, BillLineItem
from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.services.bill_service import BillService, _storage_key


class TestStorageKey:
    def test_with_prefix(self):
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = "bills"
            assert _storage_key("billing-uuid", "bill-uuid") == "bills/billing-uuid/bill-uuid.pdf"

    def test_without_prefix(self):
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = ""
            assert _storage_key("billing-uuid", "bill-uuid") == "billing-uuid/bill-uuid.pdf"


class TestBillService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.service = BillService(self.mock_repo, self.mock_storage)

    def test_generate_bill(self):
        billing = Billing(
            id=1, uuid="billing-uuid", name="Apt 101",
            items=[
                BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
                BillingItem(id=2, description="Water", amount=0, item_type=ItemType.VARIABLE),
            ],
        )
        self.mock_repo.create.return_value = Bill(
            id=1, uuid="bill-uuid", billing_id=1,
            reference_month="2025-03", total_amount=110000,
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
                BillLineItem(description="Water", amount=10000, item_type=ItemType.VARIABLE, sort_order=1),
            ],
        )
        self.mock_storage.save.return_value = "/path/to/file.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            result = self.service.generate_bill(
                billing=billing,
                reference_month="2025-03",
                variable_amounts={2: 10000},
                extras=[("Extra", 5000)],
                notes="note",
                due_date="10/04/2025",
            )

        self.mock_repo.create.assert_called_once()
        self.mock_repo.update_pdf_path.assert_called_once()
        assert result.pdf_path == "/path/to/file.pdf"

    def test_update_bill(self):
        bill = Bill(
            id=1, uuid="bill-uuid", billing_id=1,
            reference_month="2025-03", total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")
        line_items = [
            BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
        ]
        self.mock_repo.update.return_value = Bill(
            id=1, uuid="bill-uuid", billing_id=1,
            reference_month="2025-03", total_amount=100000,
            line_items=line_items,
        )
        self.mock_storage.save.return_value = "/new/path.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            result = self.service.update_bill(bill, billing, line_items, "notes", "10/04/2025")

        self.mock_repo.update.assert_called_once()
        self.mock_storage.save.assert_called_once()

    def test_regenerate_pdf(self):
        bill = Bill(
            id=1, uuid="bill-uuid", billing_id=1,
            reference_month="2025-03", total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")
        self.mock_storage.save.return_value = "/regen/path.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            result = self.service.regenerate_pdf(bill, billing)

        self.mock_repo.update_pdf_path.assert_called_once()
        assert result.pdf_path == "/regen/path.pdf"

    def test_toggle_paid_marks_as_paid(self):
        bill = Bill(
            id=1, uuid="u", billing_id=1,
            reference_month="2025-03", paid_at=None,
        )
        result = self.service.toggle_paid(bill)
        self.mock_repo.update_paid_at.assert_called_once()
        assert result.paid_at is not None

    def test_toggle_paid_unmarks(self):
        bill = Bill(
            id=1, uuid="u", billing_id=1,
            reference_month="2025-03",
            paid_at=datetime.now(SP_TZ),
        )
        result = self.service.toggle_paid(bill)
        call_args = self.mock_repo.update_paid_at.call_args[0]
        assert call_args[1] is None
        assert result.paid_at is None

    def test_get_invoice_url(self):
        self.mock_storage.get_url.return_value = "https://example.com/file.pdf"
        result = self.service.get_invoice_url("/path/file.pdf")
        assert result == "https://example.com/file.pdf"

    def test_get_invoice_url_empty(self):
        assert self.service.get_invoice_url(None) == ""
        assert self.service.get_invoice_url("") == ""

    def test_list_bills(self):
        self.mock_repo.list_by_billing.return_value = []
        result = self.service.list_bills(1)
        self.mock_repo.list_by_billing.assert_called_once_with(1)

    def test_get_bill(self):
        self.mock_repo.get_by_id.return_value = None
        result = self.service.get_bill(1)
        self.mock_repo.get_by_id.assert_called_once_with(1)

    def test_get_bill_by_uuid(self):
        self.mock_repo.get_by_uuid.return_value = None
        result = self.service.get_bill_by_uuid("uuid")
        self.mock_repo.get_by_uuid.assert_called_once_with("uuid")

    def test_delete_bill(self):
        self.service.delete_bill(1)
        self.mock_repo.delete.assert_called_once_with(1)


class TestGetPixData:
    def test_with_billing_pix_key(self):
        billing = Billing(name="Apt", pix_key="billing@pix.com")
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.pix_key = "global@pix.com"
            mock_settings.pix_merchant_name = "Landlord"
            mock_settings.pix_merchant_city = "Sao Paulo"
            png, key, payload = BillService._get_pix_data(billing, 10000)

        assert png is not None
        assert key == "billing@pix.com"
        assert len(payload) > 0

    def test_falls_back_to_global_pix_key(self):
        billing = Billing(name="Apt", pix_key="")
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.pix_key = "global@pix.com"
            mock_settings.pix_merchant_name = "Landlord"
            mock_settings.pix_merchant_city = "Sao Paulo"
            png, key, payload = BillService._get_pix_data(billing, 10000)

        assert png is not None
        assert key == "global@pix.com"

    def test_no_pix_key(self):
        billing = Billing(name="Apt", pix_key="")
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.pix_key = ""
            png, key, payload = BillService._get_pix_data(billing, 10000)

        assert png is None
        assert key == ""
        assert payload == ""

    def test_no_merchant_name(self):
        billing = Billing(name="Apt", pix_key="key@pix")
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.pix_key = ""
            mock_settings.pix_merchant_name = ""
            mock_settings.pix_merchant_city = "City"
            png, key, payload = BillService._get_pix_data(billing, 10000)

        assert png is None

    def test_no_merchant_city(self):
        billing = Billing(name="Apt", pix_key="key@pix")
        with patch("landlord.services.bill_service.settings") as mock_settings:
            mock_settings.pix_key = ""
            mock_settings.pix_merchant_name = "Name"
            mock_settings.pix_merchant_city = ""
            png, key, payload = BillService._get_pix_data(billing, 10000)

        assert png is None


class TestBillServiceValueErrors:
    """Test ValueError checks for id=None on various methods."""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.service = BillService(self.mock_repo, self.mock_storage)

    def test_generate_and_store_pdf_bill_id_none(self):
        import pytest
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03", total_amount=100)
        billing = Billing(id=1, uuid="bu", name="Apt")
        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            self.mock_storage.save.return_value = "/path.pdf"
            with pytest.raises(ValueError, match="Cannot update pdf_path"):
                self.service._generate_and_store_pdf(bill, billing)

    def test_generate_bill_billing_id_none(self):
        import pytest
        billing = Billing(id=None, uuid="bu", name="Apt", items=[])
        with pytest.raises(ValueError, match="Cannot generate bill for billing without an id"):
            self.service.generate_bill(billing, "2025-03", {}, [])

    def test_generate_bill_variable_item_id_none(self):
        import pytest
        billing = Billing(id=1, uuid="bu", name="Apt", items=[
            BillingItem(id=None, description="Water", amount=0, item_type=ItemType.VARIABLE),
        ])
        with pytest.raises(ValueError, match="Variable billing item must have an id"):
            self.service.generate_bill(billing, "2025-03", {}, [])

    def test_toggle_paid_bill_id_none(self):
        import pytest
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03", paid_at=None)
        with pytest.raises(ValueError, match="Cannot toggle paid"):
            self.service.toggle_paid(bill)
