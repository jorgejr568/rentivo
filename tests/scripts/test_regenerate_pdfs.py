from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType


class TestRegeneratePdfs:
    def _make_billing(self):
        return Billing(
            id=1,
            uuid="billing-uuid",
            name="Apt 101",
            items=[BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)],
        )

    def _make_bill(self):
        return Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
            pdf_path="bills/billing-uuid/bill-uuid.pdf",
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
            ],
        )

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.ConnectionServices.open")
    def test_dry_run(self, mock_open_services, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        mock_services = MagicMock()
        mock_open_services.return_value = nullcontext(mock_services)
        billing = self._make_billing()
        bill = self._make_bill()
        mock_services.billing_repo.list_all.return_value = [billing]
        mock_services.bill_repo.list_by_billing.return_value = [bill]
        mock_services.storage.get_url.return_value = "https://example.com/file.pdf"

        with patch("sys.argv", ["prog", "--dry-run"]):
            main()

        mock_services.bill_service.regenerate_pdf.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.ConnectionServices.open")
    def test_regeneration(self, mock_open_services, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        mock_services = MagicMock()
        mock_open_services.return_value = nullcontext(mock_services)
        billing = self._make_billing()
        bill = self._make_bill()
        mock_services.billing_repo.list_all.return_value = [billing]
        mock_services.bill_repo.list_by_billing.return_value = [bill]
        mock_services.storage.get_url.return_value = "https://example.com/new.pdf"

        with patch("sys.argv", ["prog"]):
            main()

        mock_services.bill_service.regenerate_pdf.assert_called_once_with(bill, billing)

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.ConnectionServices.open")
    def test_no_billings(self, mock_open_services, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        mock_services = MagicMock()
        mock_open_services.return_value = nullcontext(mock_services)
        mock_services.billing_repo.list_all.return_value = []

        with patch("sys.argv", ["prog"]):
            main()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.ConnectionServices.open")
    def test_no_bills(self, mock_open_services, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        mock_services = MagicMock()
        mock_open_services.return_value = nullcontext(mock_services)
        billing = self._make_billing()
        mock_services.billing_repo.list_all.return_value = [billing]
        mock_services.bill_repo.list_by_billing.return_value = []

        with patch("sys.argv", ["prog"]):
            main()
