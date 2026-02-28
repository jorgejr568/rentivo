from unittest.mock import patch

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
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    def test_dry_run(self, mock_storage, mock_receipt_repo, mock_bill_repo, mock_billing_repo, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_storage.return_value.get_url.return_value = "https://example.com/file.pdf"

        with patch("sys.argv", ["prog", "--dry-run"]):
            main()

        mock_storage.return_value.save.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.services.bill_service.BillService._get_pix_data")
    @patch("rentivo.services.bill_service.InvoicePDF")
    def test_regeneration(
        self, mock_pdf_cls, mock_pix, mock_storage, mock_receipt_repo, mock_bill_repo, mock_billing_repo, mock_init_db
    ):
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_pix.return_value = (None, "", "")
        mock_pdf_cls.return_value.generate.return_value = b"%PDF-fake"
        mock_storage.return_value.save.return_value = "/new/path.pdf"
        mock_storage.return_value.get_url.return_value = "https://example.com/new.pdf"

        with patch("sys.argv", ["prog"]):
            main()

        mock_storage.return_value.save.assert_called_once()
        mock_bill_repo.return_value.update_pdf_path.assert_called_once()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    def test_no_billings(self, mock_storage, mock_receipt_repo, mock_bill_repo, mock_billing_repo, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        mock_billing_repo.return_value.list_all.return_value = []

        with patch("sys.argv", ["prog"]):
            main()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    def test_no_bills(self, mock_storage, mock_receipt_repo, mock_bill_repo, mock_billing_repo, mock_init_db):
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = []

        with patch("sys.argv", ["prog"]):
            main()
