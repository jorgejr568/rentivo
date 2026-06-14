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
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    def test_dry_run(
        self,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
    ):
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_storage.return_value.get_url.return_value = "https://example.com/file.pdf"

        with patch("sys.argv", ["prog", "--dry-run"]):
            main()

        mock_job_backend.return_value.enqueue.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    @patch("rentivo.scripts.regenerate_pdfs.PixService")
    def test_enqueues_one_job_per_bill(
        self,
        mock_pix_cls,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
    ):
        from rentivo.jobs.base import Job
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_storage.return_value.get_url.return_value = "https://example.com/file.pdf"
        # PIX is configured for this billing.
        mock_pix_cls.return_value.resolve_for_billing.return_value = object()
        mock_job_backend.return_value.enqueue.return_value = Job(
            id=1,
            ulid="01HXYZ",
            job_type="pdf.render",
            payload={"bill_id": 1},
            attempts=0,
            max_attempts=5,
        )
        mock_job_repo.return_value.count_by_type_and_statuses.return_value = 1

        with patch("sys.argv", ["prog"]):
            main()

        # Exactly one enqueue, no synchronous storage write.
        assert mock_job_backend.return_value.enqueue.call_count == 1
        call_args = mock_job_backend.return_value.enqueue.call_args
        assert call_args.args[0] == "pdf.render"
        assert call_args.args[1] == {"bill_id": 1}
        mock_storage.return_value.save.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    def test_no_billings(
        self,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
    ):
        from rentivo.scripts.regenerate_pdfs import main

        mock_billing_repo.return_value.list_all.return_value = []

        with patch("sys.argv", ["prog"]):
            main()

        mock_job_backend.return_value.enqueue.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    def test_no_bills(
        self,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
    ):
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = []

        with patch("sys.argv", ["prog"]):
            main()

        mock_job_backend.return_value.enqueue.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    @patch("rentivo.scripts.regenerate_pdfs.PixService")
    def test_skips_bills_with_missing_pix(
        self,
        mock_pix_cls,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
    ):
        """Bills whose billing has no PIX must be skipped, not enqueued."""
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_storage.return_value.get_url.return_value = "https://example.com/file.pdf"
        mock_pix_cls.return_value.resolve_for_billing.return_value = None
        mock_job_repo.return_value.count_by_type_and_statuses.return_value = 0

        with patch("sys.argv", ["prog"]):
            main()

        mock_job_backend.return_value.enqueue.assert_not_called()
        mock_storage.return_value.save.assert_not_called()

    @patch("rentivo.scripts.regenerate_pdfs.initialize_db")
    @patch("rentivo.scripts.regenerate_pdfs.get_billing_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_bill_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_receipt_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_user_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_organization_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_storage")
    @patch("rentivo.scripts.regenerate_pdfs.get_audit_log_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_repository")
    @patch("rentivo.scripts.regenerate_pdfs.get_connection")
    @patch("rentivo.scripts.regenerate_pdfs.get_job_backend")
    @patch("rentivo.scripts.regenerate_pdfs.PixService")
    def test_summary_reports_pending_running_count(
        self,
        mock_pix_cls,
        mock_job_backend,
        mock_get_connection,
        mock_job_repo,
        mock_audit_repo,
        mock_storage,
        mock_org_repo,
        mock_user_repo,
        mock_receipt_repo,
        mock_bill_repo,
        mock_billing_repo,
        mock_init_db,
        capsys,
    ):
        from rentivo.jobs.base import Job
        from rentivo.scripts.regenerate_pdfs import main

        billing = self._make_billing()
        bill = self._make_bill()
        mock_billing_repo.return_value.list_all.return_value = [billing]
        mock_bill_repo.return_value.list_by_billing.return_value = [bill]
        mock_storage.return_value.get_url.return_value = "https://example.com/file.pdf"
        mock_pix_cls.return_value.resolve_for_billing.return_value = object()
        mock_job_backend.return_value.enqueue.return_value = Job(
            id=1,
            ulid="01HXYZ",
            job_type="pdf.render",
            payload={"bill_id": 1},
            attempts=0,
            max_attempts=5,
        )
        mock_job_repo.return_value.count_by_type_and_statuses.return_value = 7

        with patch("sys.argv", ["prog"]):
            main()

        mock_job_repo.return_value.count_by_type_and_statuses.assert_called_once_with(
            "pdf.render", ("pending", "running")
        )
        captured = capsys.readouterr().out
        assert "7" in captured
