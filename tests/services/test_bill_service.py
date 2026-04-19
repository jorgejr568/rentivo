from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from rentivo.constants import SP_TZ
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.receipt import Receipt
from rentivo.services.bill_service import BillService, _receipt_storage_key, _storage_key
from rentivo.services.pix_service import PixConfig


class TestStorageKey:
    def test_with_prefix(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = "bills"
            assert _storage_key("billing-uuid", "bill-uuid") == "bills/billing-uuid/bill-uuid.pdf"

    def test_without_prefix(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = ""
            assert _storage_key("billing-uuid", "bill-uuid") == "billing-uuid/bill-uuid.pdf"


def _pix_service_with(config: PixConfig | None = None):
    """Shared stub PixService that returns a fixed config for all billings."""

    class _Stub:
        def resolve_for_billing(self, billing):
            return config or PixConfig(pix_key="test@pix.com", merchant_name="Rentivo", merchant_city="Sao Paulo")

    return _Stub()


class TestBillService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.service = BillService(self.mock_repo, self.mock_storage, pix_service=_pix_service_with())

    def test_generate_bill(self):
        billing = Billing(
            id=1,
            uuid="billing-uuid",
            name="Apt 101",
            items=[
                BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
                BillingItem(id=2, description="Water", amount=0, item_type=ItemType.VARIABLE),
            ],
        )
        self.mock_repo.create.return_value = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=110000,
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
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")
        line_items = [
            BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
        ]
        self.mock_repo.update.return_value = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
            line_items=line_items,
        )
        self.mock_storage.save.return_value = "/new/path.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            self.service.update_bill(bill, billing, line_items, "notes", "10/04/2025")

        self.mock_repo.update.assert_called_once()
        self.mock_storage.save.assert_called_once()

    def test_regenerate_pdf(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")
        self.mock_storage.save.return_value = "/regen/path.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            result = self.service.regenerate_pdf(bill, billing)

        self.mock_repo.update_pdf_path.assert_called_once()
        assert result.pdf_path == "/regen/path.pdf"

    def test_change_status_to_paid(self):
        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
        )
        result = self.service.change_status(bill, "paid")
        self.mock_repo.update_status.assert_called_once()
        assert result.status == "paid"
        assert result.status_updated_at is not None

    def test_change_status_to_draft(self):
        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
            status="paid",
            status_updated_at=datetime.now(SP_TZ),
        )
        result = self.service.change_status(bill, "draft")
        self.mock_repo.update_status.assert_called_once()
        assert result.status == "draft"
        assert result.status_updated_at is not None

    def test_get_invoice_url(self):
        self.mock_storage.get_url.return_value = "https://example.com/file.pdf"
        result = self.service.get_invoice_url("/path/file.pdf")
        assert result == "https://example.com/file.pdf"

    def test_get_invoice_url_empty(self):
        assert self.service.get_invoice_url(None) == ""
        assert self.service.get_invoice_url("") == ""

    def test_list_bills(self):
        self.mock_repo.list_by_billing.return_value = []
        self.service.list_bills(1)
        self.mock_repo.list_by_billing.assert_called_once_with(1)

    def test_get_bill(self):
        self.mock_repo.get_by_id.return_value = None
        self.service.get_bill(1)
        self.mock_repo.get_by_id.assert_called_once_with(1)

    def test_get_bill_by_uuid(self):
        self.mock_repo.get_by_uuid.return_value = None
        self.service.get_bill_by_uuid("uuid")
        self.mock_repo.get_by_uuid.assert_called_once_with("uuid")

    def test_delete_bill(self):
        self.service.delete_bill(1)
        self.mock_repo.delete.assert_called_once_with(1)


class _StaticPixService:
    """Minimal stand-in for PixService used by BillService tests."""

    def __init__(self, config):
        self._config = config

    def resolve_for_billing(self, billing):
        return self._config


class TestGetPixData:
    def _service(self, config):
        svc = BillService(MagicMock(), MagicMock(), pix_service=_StaticPixService(config))
        return svc

    def test_with_billing_pix_config(self):
        from rentivo.services.pix_service import PixConfig

        billing = Billing(
            name="Apt",
            pix_key="billing@pix.com",
            pix_merchant_name="Billing Co",
            pix_merchant_city="Campinas",
        )
        service = self._service(
            PixConfig(pix_key="billing@pix.com", merchant_name="Billing Co", merchant_city="Campinas")
        )
        png, key, payload = service._get_pix_data(billing, 10000)

        assert png is not None
        assert key == "billing@pix.com"
        assert len(payload) > 0

    def test_falls_back_to_owner_pix(self):
        from rentivo.services.pix_service import PixConfig

        billing = Billing(name="Apt")
        service = self._service(PixConfig(pix_key="owner@pix.com", merchant_name="Owner", merchant_city="Sao Paulo"))
        png, key, _ = service._get_pix_data(billing, 10000)

        assert png is not None
        assert key == "owner@pix.com"

    def test_no_pix_config_raises(self):
        billing = Billing(name="Apt")
        service = self._service(None)
        with pytest.raises(ValueError, match="Configure a chave PIX"):
            service._get_pix_data(billing, 10000)

    def test_missing_pix_service_raises(self):
        billing = Billing(name="Apt")
        service = BillService(MagicMock(), MagicMock())
        with pytest.raises(ValueError, match="Configure a chave PIX"):
            service._get_pix_data(billing, 10000)


class TestBillServiceValueErrors:
    """Test ValueError checks for id=None on various methods."""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.service = BillService(self.mock_repo, self.mock_storage, pix_service=_pix_service_with())

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

        billing = Billing(
            id=1,
            uuid="bu",
            name="Apt",
            items=[
                BillingItem(id=None, description="Water", amount=0, item_type=ItemType.VARIABLE),
            ],
        )
        with pytest.raises(ValueError, match="Variable billing item must have an id"):
            self.service.generate_bill(billing, "2025-03", {}, [])

    def test_change_status_bill_id_none(self):
        import pytest

        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03")
        with pytest.raises(ValueError, match="Cannot change status"):
            self.service.change_status(bill, "paid")


class TestReceiptStorageKey:
    def test_receipt_key_with_prefix(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = "bills"
            key = _receipt_storage_key("billing-uuid", "bill-uuid", "receipt-uuid", "application/pdf")
        assert key == "bills/billing-uuid/bill-uuid/receipts/receipt-uuid.pdf"

    def test_receipt_key_without_prefix(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = ""
            key = _receipt_storage_key("billing-uuid", "bill-uuid", "receipt-uuid", "image/jpeg")
        assert key == "billing-uuid/bill-uuid/receipts/receipt-uuid.jpg"

    def test_receipt_key_png(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = ""
            key = _receipt_storage_key("bu", "bi", "ru", "image/png")
        assert key == "bu/bi/receipts/ru.png"

    def test_receipt_key_unknown_type(self):
        with patch("rentivo.services.bill_service.settings") as mock_settings:
            mock_settings.storage_prefix = ""
            key = _receipt_storage_key("bu", "bi", "ru", "text/plain")
        assert key == "bu/bi/receipts/ru"


class TestReceiptMethods:
    """Test receipt-related methods on BillService."""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.mock_receipt_repo = MagicMock()
        self.service = BillService(
            self.mock_repo,
            self.mock_storage,
            self.mock_receipt_repo,
            pix_service=_pix_service_with(),
        )

    def test_add_receipt(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        self.mock_receipt_repo.list_by_bill.return_value = []
        self.mock_receipt_repo.create.return_value = Receipt(
            id=1,
            uuid="receipt-uuid",
            bill_id=1,
            filename="receipt.pdf",
            storage_key="key.pdf",
            content_type="application/pdf",
            file_size=1024,
        )
        self.mock_storage.save.return_value = "/path/receipt.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-fake"
            receipt, failed = self.service.add_receipt(bill, billing, "receipt.pdf", b"pdf-data", "application/pdf")

        assert receipt.filename == "receipt.pdf"
        assert failed == []
        # Storage save called twice: once for receipt file, once for regenerated PDF
        assert self.mock_storage.save.call_count == 2
        self.mock_receipt_repo.create.assert_called_once()

    def test_add_receipt_sort_order_increments(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        existing = [
            Receipt(id=1, bill_id=1, filename="a.pdf", sort_order=0, storage_key="k", content_type="application/pdf"),
            Receipt(id=2, bill_id=1, filename="b.pdf", sort_order=1, storage_key="k", content_type="application/pdf"),
        ]
        self.mock_receipt_repo.list_by_bill.return_value = existing
        self.mock_receipt_repo.create.return_value = Receipt(
            id=3,
            uuid="r3",
            bill_id=1,
            filename="c.pdf",
            storage_key="k3",
            content_type="application/pdf",
            file_size=100,
            sort_order=2,
        )
        self.mock_storage.save.return_value = "/p"
        self.mock_storage.get.return_value = b"data"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            self.service.add_receipt(bill, billing, "c.pdf", b"data", "application/pdf")

        # Check that sort_order=2 was set in the created receipt
        create_call = self.mock_receipt_repo.create.call_args[0][0]
        assert create_call.sort_order == 2

    def test_add_receipt_no_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)  # no receipt_repo
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(RuntimeError, match="Receipt repository not configured"):
            service.add_receipt(bill, billing, "f.pdf", b"data", "application/pdf")

    def test_add_receipt_bill_id_none(self):
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(ValueError, match="Cannot add receipt to bill without an id"):
            self.service.add_receipt(bill, billing, "f.pdf", b"data", "application/pdf")

    def test_add_receipt_invalid_type(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(ValueError, match="Unsupported file type"):
            self.service.add_receipt(bill, billing, "f.gif", b"data", "image/gif")

    def test_add_receipt_too_large(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        big_data = b"x" * (10 * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="File too large"):
            self.service.add_receipt(bill, billing, "f.pdf", big_data, "application/pdf")

    def test_add_receipt_empty_file(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(ValueError, match="Empty file"):
            self.service.add_receipt(bill, billing, "f.pdf", b"", "application/pdf")

    def test_add_receipt_rolls_back_storage_on_repo_failure(self):
        """Regression: if receipt_repo.create fails, storage.delete is called to clean up."""
        bill = Bill(id=1, uuid="bill-uuid", billing_id=1, reference_month="2025-03", total_amount=100)
        billing = Billing(id=1, uuid="billing-uuid", name="A")

        self.mock_receipt_repo.list_by_bill.return_value = []
        self.mock_receipt_repo.create.side_effect = RuntimeError("DB down")

        with pytest.raises(RuntimeError, match="DB down"):
            self.service.add_receipt(bill, billing, "f.pdf", b"data", "application/pdf")

        # storage.delete should have been called with the same key that was saved
        assert self.mock_storage.delete.call_count == 1
        saved_key = self.mock_storage.save.call_args_list[0][0][0]
        deleted_key = self.mock_storage.delete.call_args[0][0]
        assert deleted_key == saved_key

    def test_delete_receipt(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")
        receipt = Receipt(
            id=5,
            uuid="receipt-uuid",
            bill_id=1,
            filename="r.pdf",
            storage_key="k.pdf",
            content_type="application/pdf",
            file_size=100,
        )
        self.mock_storage.save.return_value = "/p"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            self.service.delete_receipt(receipt, bill, billing)

        self.mock_receipt_repo.delete.assert_called_once_with(5)

    def test_delete_receipt_no_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)
        receipt = Receipt(id=1, bill_id=1, filename="r.pdf")
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(RuntimeError, match="Receipt repository not configured"):
            service.delete_receipt(receipt, bill, billing)

    def test_delete_receipt_id_none(self):
        receipt = Receipt(id=None, bill_id=1, filename="r.pdf")
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(ValueError, match="Cannot delete receipt without an id"):
            self.service.delete_receipt(receipt, bill, billing)

    def test_list_receipts(self):
        self.mock_receipt_repo.list_by_bill.return_value = [
            Receipt(id=1, bill_id=1, filename="a.pdf"),
        ]
        result = self.service.list_receipts(1)
        assert len(result) == 1
        self.mock_receipt_repo.list_by_bill.assert_called_once_with(1)

    def test_list_receipts_no_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)
        result = service.list_receipts(1)
        assert result == []

    def test_get_receipt_by_uuid(self):
        self.mock_receipt_repo.get_by_uuid.return_value = Receipt(id=1, bill_id=1, filename="r.pdf")
        result = self.service.get_receipt_by_uuid("uuid")
        assert result is not None
        self.mock_receipt_repo.get_by_uuid.assert_called_once_with("uuid")

    def test_get_receipt_by_uuid_no_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)
        result = service.get_receipt_by_uuid("uuid")
        assert result is None

    def test_reorder_receipts(self):
        bill = Bill(id=1, uuid="bill-uuid", billing_id=1, reference_month="2025-03", total_amount=100000)
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        r1 = Receipt(
            id=1, uuid="r1", bill_id=1, filename="a.pdf", sort_order=0, storage_key="k", content_type="application/pdf"
        )
        r2 = Receipt(
            id=2, uuid="r2", bill_id=1, filename="b.pdf", sort_order=1, storage_key="k", content_type="application/pdf"
        )
        r3 = Receipt(
            id=3, uuid="r3", bill_id=1, filename="c.pdf", sort_order=2, storage_key="k", content_type="application/pdf"
        )
        self.mock_receipt_repo.list_by_bill.return_value = [r1, r2, r3]
        self.mock_storage.save.return_value = "/p"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            self.service.reorder_receipts(bill, billing, ["r3", "r1", "r2"])

        self.mock_receipt_repo.update_sort_orders.assert_called_once_with([(3, 0), (1, 1), (2, 2)])

    def test_reorder_receipts_no_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(RuntimeError, match="Receipt repository not configured"):
            service.reorder_receipts(bill, billing, [])

    def test_reorder_receipts_bill_id_none(self):
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        with pytest.raises(ValueError, match="Cannot reorder receipts for bill without an id"):
            self.service.reorder_receipts(bill, billing, [])

    def test_reorder_receipts_invalid_uuid(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        r1 = Receipt(
            id=1, uuid="r1", bill_id=1, filename="a.pdf", sort_order=0, storage_key="k", content_type="application/pdf"
        )
        self.mock_receipt_repo.list_by_bill.return_value = [r1]
        with pytest.raises(ValueError, match="does not belong to this bill"):
            self.service.reorder_receipts(bill, billing, ["nonexistent"])

    def test_reorder_receipts_missing_uuid(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        billing = Billing(id=1, uuid="bu", name="A")
        r1 = Receipt(
            id=1, uuid="r1", bill_id=1, filename="a.pdf", sort_order=0, storage_key="k", content_type="application/pdf"
        )
        r2 = Receipt(
            id=2, uuid="r2", bill_id=1, filename="b.pdf", sort_order=1, storage_key="k", content_type="application/pdf"
        )
        self.mock_receipt_repo.list_by_bill.return_value = [r1, r2]
        with pytest.raises(ValueError, match="Must include all receipts"):
            self.service.reorder_receipts(bill, billing, ["r1"])


class TestPdfGenerationWithReceipts:
    """Test that _generate_and_store_pdf merges receipts."""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_storage = MagicMock()
        self.mock_receipt_repo = MagicMock()
        self.service = BillService(
            self.mock_repo,
            self.mock_storage,
            self.mock_receipt_repo,
            pix_service=_pix_service_with(),
        )

    def test_pdf_generation_fetches_and_merges_receipts(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        self.mock_receipt_repo.list_by_bill.return_value = [
            Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="key/r.pdf", content_type="application/pdf"),
        ]
        self.mock_storage.get.return_value = b"%PDF-receipt"
        self.mock_storage.save.return_value = "/out.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-invoice"
            with patch("rentivo.services.bill_service.merge_receipts") as mock_merge:
                mock_merge.return_value = (b"%PDF-merged", [])
                self.service._generate_and_store_pdf(bill, billing)

        mock_merge.assert_called_once()
        self.mock_storage.get.assert_called_once_with("key/r.pdf")

    def test_pdf_generation_no_receipts_skips_merge(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        self.mock_receipt_repo.list_by_bill.return_value = []
        self.mock_storage.save.return_value = "/out.pdf"

        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF-invoice"
            with patch("rentivo.services.bill_service.merge_receipts") as mock_merge:
                self.service._generate_and_store_pdf(bill, billing)

        mock_merge.assert_not_called()

    def test_fetch_receipt_data_handles_storage_error(self):
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        self.mock_receipt_repo.list_by_bill.return_value = [
            Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="key/r.pdf", content_type="application/pdf"),
        ]
        self.mock_storage.get.side_effect = Exception("download failed")

        data, ordered = self.service._fetch_receipt_data(bill)
        assert data == []  # Error is caught and skipped
        assert ordered == []

    def test_fetch_receipt_data_no_receipt_repo(self):
        service = BillService(self.mock_repo, self.mock_storage)
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03")
        data, ordered = service._fetch_receipt_data(bill)
        assert data == []
        assert ordered == []

    def test_fetch_receipt_data_bill_id_none(self):
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03")
        data, ordered = self.service._fetch_receipt_data(bill)
        assert data == []
        assert ordered == []
