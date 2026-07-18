from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from rentivo.constants import SP_TZ
from rentivo.encryption.base64 import Base64Backend
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.receipt import Receipt
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyOrganizationRepository,
    SQLAlchemyReceiptRepository,
    SQLAlchemyUserRepository,
)
from rentivo.services.bill_service import BillService, _receipt_storage_key, _recibo_storage_key, _storage_key
from rentivo.services.pix_service import PixConfig, PixService
from rentivo.storage.local import LocalStorage
from tests.web.conftest import test_engine, web_test_db  # noqa: F401


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
        # sent → paid is the canonical "mark as paid" transition.
        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
            status="sent",
        )
        result = self.service.change_status(bill, "paid")
        status_call = self.mock_repo.update_status.call_args
        assert status_call.args[:3] == (1, "sent", "paid")
        assert result.status == "paid"
        assert result.status_updated_at is not None

    def test_change_status_rejects_lost_compare_and_swap_without_mutating_bill(self):
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03", status="sent")
        self.mock_repo.update_status.return_value = False

        with pytest.raises(RuntimeError) as exc_info:
            self.service.change_status(bill, "paid")

        assert type(exc_info.value).__name__ == "StaleBillStatusError"
        assert bill.status == "sent"
        assert bill.status_updated_at is None

    def test_change_status_to_draft(self):
        # published → draft (back to rascunho) is an allowed backward transition.
        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
            status="published",
            status_updated_at=datetime.now(SP_TZ),
        )
        result = self.service.change_status(bill, "draft")
        self.mock_repo.update_status.assert_called_once()
        assert result.status == "draft"
        assert result.status_updated_at is not None

    def test_change_status_rejects_disallowed_transition(self):
        # paid → draft is not in the lifecycle; the service must reject it
        # (defense-in-depth, REN-21) without touching the repo.
        import pytest

        from rentivo.models.bill import InvalidStatusTransition

        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
            status="paid",
        )
        with pytest.raises(InvalidStatusTransition):
            self.service.change_status(bill, "draft")
        self.mock_repo.update_status.assert_not_called()
        # Bill state is left untouched.
        assert bill.status == "paid"

    def test_change_status_noop_same_status_allowed(self):
        # A no-op (same status) is idempotent and allowed.
        bill = Bill(
            id=1,
            uuid="u",
            billing_id=1,
            reference_month="2025-03",
            status="sent",
        )
        result = self.service.change_status(bill, "sent")
        self.mock_repo.update_status.assert_called_once()
        assert result.status == "sent"

    def test_get_invoice_url(self):
        self.mock_storage.get_url.return_value = "https://example.com/file.pdf"
        result = self.service.get_invoice_url("/path/file.pdf")
        assert result == "https://example.com/file.pdf"

    def test_get_invoice_url_empty(self):
        assert self.service.get_invoice_url(None) == ""
        assert self.service.get_invoice_url("") == ""

    def test_get_invoice_ref_delegates_to_storage(self):
        from rentivo.storage.base import FileRef

        self.mock_storage.get_ref.return_value = FileRef(kind="url", location="https://x/file.pdf")
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2025-03", pdf_path="key/file.pdf")

        ref = self.service.get_invoice_ref(bill)

        self.mock_storage.get_ref.assert_called_once_with("key/file.pdf")
        assert ref == FileRef(kind="url", location="https://x/file.pdf")

    def test_get_receipt_ref_delegates_to_storage(self):
        from rentivo.storage.base import FileRef

        self.mock_storage.get_ref.return_value = FileRef(kind="local", location="/abs/r.pdf")
        receipt = Receipt(id=1, bill_id=1, filename="r.pdf", storage_key="b/bill/receipts/r.pdf")

        ref = self.service.get_receipt_ref(receipt)

        self.mock_storage.get_ref.assert_called_once_with("b/bill/receipts/r.pdf")
        assert ref == FileRef(kind="local", location="/abs/r.pdf")

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
        self.mock_repo.delete.return_value = True
        self.service.delete_bill(1)
        self.mock_repo.delete.assert_called_once_with(1)

    def test_delete_bill_rejects_already_deleted_row(self):
        self.mock_repo.delete.return_value = False

        with pytest.raises(RuntimeError) as exc_info:
            self.service.delete_bill(1)

        assert type(exc_info.value).__name__ == "StaleBillDeleteError"


def test_competing_status_transitions_use_real_service_repository_compare_and_swap(
    db_connection,
    fake_encryption,
    sample_billing,
    sample_bill,
):
    billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
    bill_repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
    billing = billing_repo.create(sample_billing())
    stored = bill_repo.create(sample_bill(billing_id=billing.id, status="draft"))
    first_reader = stored.model_copy(deep=True)
    competing_reader = stored.model_copy(deep=True)
    service = BillService(bill_repo, MagicMock())

    service.change_status(first_reader, "published")
    with pytest.raises(RuntimeError) as exc_info:
        service.change_status(competing_reader, "sent")

    assert type(exc_info.value).__name__ == "StaleBillStatusError"
    assert competing_reader.status == "draft"
    assert bill_repo.get_by_id(stored.id).status == "published"


def test_rollback_bill_creation_removes_real_bill_receipts_and_storage(
    db_connection,
    fake_encryption,
    sample_billing,
    tmp_path,
):
    billing_repo = SQLAlchemyBillingRepository(db_connection, fake_encryption)
    bill_repo = SQLAlchemyBillRepository(db_connection, fake_encryption)
    receipt_repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
    storage = LocalStorage(str(tmp_path))
    service = BillService(bill_repo, storage, receipt_repo)
    billing = billing_repo.create(sample_billing())
    bill = service.generate_bill(billing, "2026-08", {}, [], render=False)
    receipt, _ = service.add_receipt(
        bill,
        billing,
        "receipt.pdf",
        b"receipt",
        "application/pdf",
        render=False,
    )
    invoice_key = _storage_key(billing.uuid, bill.uuid)
    storage.save(invoice_key, b"%PDF")

    service.rollback_bill_creation(bill, billing)

    assert bill_repo.get_by_id(bill.id) is None
    assert receipt_repo.get_by_uuid(receipt.uuid) is None
    with pytest.raises(FileNotFoundError):
        storage.get(receipt.storage_key)
    with pytest.raises(FileNotFoundError):
        storage.get(invoice_key)


def test_rollback_receipt_batch_requires_atomic_delete_before_storage_cleanup():
    receipt_repo = MagicMock()
    receipt_repo.delete_many.return_value = 2
    storage = MagicMock()
    events: list[str] = []
    receipt_repo.delete_many.side_effect = lambda _ids: events.append("db") or 2
    storage.delete.side_effect = lambda _key: events.append("storage")
    service = BillService(MagicMock(), storage, receipt_repo)
    receipts = (
        Receipt(id=1, bill_id=1, filename="a.pdf", storage_key="a"),
        Receipt(id=2, bill_id=1, filename="b.pdf", storage_key="b"),
    )

    service.rollback_receipt_batch(receipts)

    assert events == ["db", "storage", "storage"]
    receipt_repo.delete_many.assert_called_once_with([1, 2])


def test_rollback_receipt_batch_empty_is_noop():
    service = BillService(MagicMock(), MagicMock())

    service.rollback_receipt_batch(())

    service.storage.delete.assert_not_called()


def test_rollback_receipt_batch_requires_repository():
    service = BillService(MagicMock(), MagicMock())
    receipt = Receipt(id=1, bill_id=1, filename="a.pdf", storage_key="a")

    with pytest.raises(RuntimeError, match="Receipt repository not configured"):
        service.rollback_receipt_batch((receipt,))


def test_rollback_receipt_batch_rejects_partial_database_cleanup():
    receipt_repo = MagicMock()
    receipt_repo.delete_many.return_value = 1
    storage = MagicMock()
    service = BillService(MagicMock(), storage, receipt_repo)
    receipts = (
        Receipt(id=1, bill_id=1, filename="a.pdf", storage_key="a"),
        Receipt(id=2, bill_id=1, filename="b.pdf", storage_key="b"),
    )

    with pytest.raises(RuntimeError, match="complete receipt batch"):
        service.rollback_receipt_batch(receipts)

    storage.delete.assert_not_called()


def test_rollback_bill_creation_without_receipt_repository_uses_predictable_keys():
    bill_repo = MagicMock()
    bill_repo.delete_created.return_value = True
    storage = MagicMock()
    service = BillService(bill_repo, storage)
    bill = Bill(id=1, uuid="bill-uuid", billing_id=1, reference_month="2026-08")
    billing = Billing(id=1, uuid="billing-uuid", name="Apt")

    service.rollback_bill_creation(bill, billing)

    assert [call.args[0] for call in storage.delete.call_args_list] == [
        _storage_key(billing.uuid, bill.uuid),
        _recibo_storage_key(billing.uuid, bill.uuid),
    ]


def test_rollback_bill_creation_requires_confirmed_hard_delete():
    bill_repo = MagicMock()
    bill_repo.delete_created.return_value = False
    storage = MagicMock()
    service = BillService(bill_repo, storage)

    with pytest.raises(RuntimeError, match="created bill"):
        service.rollback_bill_creation(
            Bill(id=1, uuid="bill-uuid", billing_id=1, reference_month="2026-08"),
            Billing(id=1, uuid="billing-uuid", name="Apt"),
        )

    storage.delete.assert_not_called()


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

    def test_render_pdf_sync_bill_id_none(self):
        import pytest

        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2025-03", total_amount=100)
        billing = Billing(id=1, uuid="bu", name="Apt")
        with patch.object(self.service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            self.mock_storage.save.return_value = "/path.pdf"
            with pytest.raises(ValueError, match="Cannot update pdf_path"):
                self.service._render_pdf_sync(bill, billing)

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
    """Test that _render_pdf_sync merges receipts."""

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
                self.service._render_pdf_sync(bill, billing)

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
                self.service._render_pdf_sync(bill, billing)

        mock_merge.assert_not_called()

    def test_pdf_generation_resolves_theme_when_theme_service_configured(self):
        """When a ThemeService is configured, _render_pdf_sync must resolve and pass the theme."""
        bill = Bill(
            id=1,
            uuid="bill-uuid",
            billing_id=1,
            reference_month="2025-03",
            total_amount=100000,
        )
        billing = Billing(id=1, uuid="billing-uuid", name="Apt 101")

        mock_theme = MagicMock()
        mock_theme_service = MagicMock()
        mock_theme_service.resolve_theme_for_billing.return_value = mock_theme

        service = BillService(
            self.mock_repo,
            self.mock_storage,
            self.mock_receipt_repo,
            theme_service=mock_theme_service,
            pix_service=_pix_service_with(),
        )
        self.mock_receipt_repo.list_by_bill.return_value = []
        self.mock_storage.save.return_value = "/out.pdf"

        with patch.object(service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            service._render_pdf_sync(bill, billing)

        mock_theme_service.resolve_theme_for_billing.assert_called_once_with(billing)
        # The resolved theme is threaded through to the PDF generator.
        assert mock_pdf.generate.call_args.kwargs.get("theme") is mock_theme

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


class TestRenderOrEnqueue:
    def setup_method(self):
        self.bill_repo = MagicMock()
        self.storage = MagicMock()
        self.receipt_repo = MagicMock()
        self.receipt_repo.list_by_bill.return_value = []
        self.storage.save.return_value = "/path.pdf"
        self.pix = _pix_service_with()
        self.job_service = MagicMock()

    def _bill(self):
        return Bill(id=42, uuid="b-uuid", billing_id=1, reference_month="2026-05", total_amount=10000)

    def _billing(self):
        return Billing(id=1, uuid="bg-uuid", name="Apt 101")

    def test_no_job_service_renders_synchronously(self):
        service = BillService(self.bill_repo, self.storage, self.receipt_repo, pix_service=self.pix)
        with patch.object(service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            path, failed = service._render_or_enqueue(self._bill(), self._billing())

        assert path == "/path.pdf"
        assert failed == []
        # Sync path: pdf_render_status set to "succeeded" (inside _render_pdf_sync)
        self.bill_repo.update_pdf_render_status.assert_called_once_with(42, "succeeded")

    def test_job_service_enqueues_and_marks_pending(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="alice@example.com")
        with patch.object(service, "pdf_generator") as mock_pdf:
            path, failed = service._render_or_enqueue(self._bill(), self._billing(), actor=actor)

        # Async path: no actual render
        mock_pdf.generate.assert_not_called()
        # Bill marked pending and job enqueued via enqueue_for
        self.bill_repo.update_pdf_render_status.assert_called_once_with(42, "pending")
        self.job_service.enqueue_for.assert_called_once_with(
            actor,
            "pdf.render",
            {"bill_id": 42},
            max_attempts=3,
        )
        self.job_service.enqueue.assert_not_called()
        assert path is None
        assert failed == []

    def test_enqueue_falls_back_to_anonymous_when_no_actor(self):
        """When actor=None, the job is enqueued via plain enqueue with
        empty source/id/username — matches CLI behaviour pre-refactor."""
        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        with patch.object(service, "pdf_generator") as mock_pdf:
            path, failed = service._render_or_enqueue(self._bill(), self._billing())

        mock_pdf.generate.assert_not_called()
        self.bill_repo.update_pdf_render_status.assert_called_once_with(42, "pending")
        self.job_service.enqueue_for.assert_not_called()
        self.job_service.enqueue.assert_called_once_with(
            "pdf.render",
            {"bill_id": 42},
            source="",
            actor_id=None,
            actor_username="",
            max_attempts=3,
        )
        assert path is None
        assert failed == []

    def test_render_or_enqueue_raises_when_bill_id_missing(self):
        service = BillService(self.bill_repo, self.storage, pix_service=self.pix)
        bill = Bill(id=None, uuid="u", billing_id=1, reference_month="2026-05", total_amount=10000)
        with pytest.raises(ValueError, match="render or enqueue"):
            service._render_or_enqueue(bill, self._billing())

    def test_update_bill_uses_render_or_enqueue(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        self.bill_repo.update.return_value = self._bill()
        with patch.object(service, "pdf_generator") as mock_pdf:
            service.update_bill(self._bill(), self._billing(), [], "notes", "", actor=actor)

        mock_pdf.generate.assert_not_called()
        self.job_service.enqueue_for.assert_called_once()
        assert self.job_service.enqueue_for.call_args.args[0] is actor

    def test_regenerate_pdf_uses_render_or_enqueue(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        with patch.object(service, "pdf_generator") as mock_pdf:
            service.regenerate_pdf(self._bill(), self._billing(), actor=actor)

        mock_pdf.generate.assert_not_called()
        self.job_service.enqueue_for.assert_called_once()
        assert self.job_service.enqueue_for.call_args.args[0] is actor

    def test_regenerate_pdf_paid_also_enqueues_recibo(self):
        """A PAID bill regenerates both the invoice and the recibo, in that order."""
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        paid_bill = Bill(
            id=42, uuid="b-uuid", billing_id=1, reference_month="2026-05", total_amount=10000, status="paid"
        )
        with patch.object(service, "pdf_generator"):
            service.regenerate_pdf(paid_bill, self._billing(), actor=actor)

        calls = self.job_service.enqueue_for.call_args_list
        assert [c.args[1] for c in calls] == ["pdf.render", "recibo.render"]
        assert all(c.args[0] is actor for c in calls)
        assert all(c.args[2] == {"bill_id": 42} for c in calls)

    def test_regenerate_pdf_not_paid_skips_recibo(self):
        """A non-PAID bill regenerates only the invoice — no recibo job."""
        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        draft_bill = Bill(
            id=42, uuid="b-uuid", billing_id=1, reference_month="2026-05", total_amount=10000, status="draft"
        )
        with patch.object(service, "pdf_generator"):
            service.regenerate_pdf(draft_bill, self._billing())

        # Only the invoice is enqueued (anonymous, since no actor); no recibo.render.
        job_types = [c.args[0] for c in self.job_service.enqueue.call_args_list]
        assert job_types == ["pdf.render"]

    def test_add_receipt_uses_render_or_enqueue_in_async_mode(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        bill = self._bill()
        self.receipt_repo.create.return_value = Receipt(
            id=11,
            uuid="r-uuid",
            bill_id=42,
            filename="r.pdf",
            storage_key="key",
            content_type="application/pdf",
            file_size=10,
        )
        receipt, failed = service.add_receipt(bill, self._billing(), "r.pdf", b"data", "application/pdf", actor=actor)

        assert receipt.filename == "r.pdf"
        assert failed == []
        # In async mode the worker will report receipt-merge failures separately.
        self.job_service.enqueue_for.assert_called_once()
        assert self.job_service.enqueue_for.call_args.args[0] is actor

    def test_delete_receipt_uses_render_or_enqueue_in_async_mode(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        bill = self._bill()
        receipt = Receipt(id=5, bill_id=42, filename="r.pdf", uuid="r-uuid")
        service.delete_receipt(receipt, bill, self._billing(), actor=actor)

        self.receipt_repo.delete.assert_called_once_with(5)
        self.job_service.enqueue_for.assert_called_once()
        assert self.job_service.enqueue_for.call_args.args[0] is actor

    def test_reorder_receipts_uses_render_or_enqueue_in_async_mode(self):
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        bill = self._bill()
        existing = [
            Receipt(id=1, uuid="a", bill_id=42, filename="x.pdf", sort_order=0),
            Receipt(id=2, uuid="b", bill_id=42, filename="y.pdf", sort_order=1),
        ]
        self.receipt_repo.list_by_bill.return_value = existing
        service.reorder_receipts(bill, self._billing(), ["b", "a"], actor=actor)

        self.receipt_repo.update_sort_orders.assert_called_once()
        self.job_service.enqueue_for.assert_called_once()
        assert self.job_service.enqueue_for.call_args.args[0] is actor

    def test_generate_bill_enqueues_pdf_render_when_job_service_is_configured(self):
        """First-render path must enqueue when a JobService is configured (web).

        Bill creation through the web UI used to render the PDF inline,
        blocking the HTTP request for hundreds of milliseconds. The
        ``pdf.render`` worker + ``Renderizando`` UI badge make async render
        the right default; the bill is returned with
        ``pdf_render_status='pending'`` and the worker drains the job.
        """
        billing = Billing(
            id=1,
            uuid="bg-uuid",
            name="Apt 101",
            items=[BillingItem(id=1, description="Rent", amount=10000, item_type=ItemType.FIXED)],
        )
        self.bill_repo.create.return_value = Bill(
            id=42,
            uuid="b-uuid",
            billing_id=1,
            reference_month="2026-05",
            total_amount=10000,
            line_items=[BillLineItem(description="Rent", amount=10000, item_type=ItemType.FIXED, sort_order=0)],
        )
        from legacy_web.context import WebActor

        service = BillService(
            self.bill_repo,
            self.storage,
            self.receipt_repo,
            pix_service=self.pix,
            job_service=self.job_service,
        )
        actor = WebActor(user_id=7, email="a@x")
        with patch.object(service, "pdf_generator") as mock_pdf:
            mock_pdf.generate.return_value = b"%PDF"
            service.generate_bill(billing, "2026-05", {}, [], actor=actor)

        # generate_bill must NOT render the PDF inline...
        mock_pdf.generate.assert_not_called()
        self.storage.save.assert_not_called()
        self.bill_repo.update_pdf_path.assert_not_called()

        # ...and must enqueue a pdf.render job for the new bill via enqueue_for.
        self.job_service.enqueue_for.assert_called_once()
        call = self.job_service.enqueue_for.call_args
        assert call.args[0] is actor
        assert call.args[1] == "pdf.render"
        assert call.args[2] == {"bill_id": 42}
        assert call.kwargs.get("max_attempts") == 3

        # The row is marked "pending" (not "succeeded") on the enqueue path.
        self.bill_repo.update_pdf_render_status.assert_called_once_with(42, "pending")


class TestRenderRecibo:
    def _service(self, conn, tmp_path):
        return BillService(
            SQLAlchemyBillRepository(conn, Base64Backend()),
            LocalStorage(str(tmp_path)),
            pix_service=PixService(
                SQLAlchemyUserRepository(conn, Base64Backend()),
                SQLAlchemyOrganizationRepository(conn, Base64Backend()),
            ),
        )

    def test_render_recibo_returns_pdf_bytes(self, test_engine, tmp_path):  # noqa: F811
        with test_engine.connect() as conn:
            billing_repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            billing = billing_repo.create(
                Billing(
                    name="Apt 101",
                    pix_key="maria@pix.com",
                    pix_merchant_name="Maria Recebedora",
                    pix_merchant_city="Sao Paulo",
                    owner_type="user",
                    owner_id=1,
                    items=[BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED)],
                )
            )
            service = self._service(conn, tmp_path)
            bill = service.generate_bill(
                billing=billing,
                reference_month="2025-03",
                variable_amounts={},
                extras=[],
                notes="",
                due_date="10/04/2025",
            )
            pdf_bytes = service.render_recibo(bill, billing)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_render_recibo_user_owned_smoke(
        self,
        test_engine,  # noqa: F811
        tmp_path,
    ):
        with test_engine.connect() as conn:
            # User-owned billing: render_recibo resolves the issuer to the owner's
            # account email and still produces a valid PDF.
            user_repo = SQLAlchemyUserRepository(conn, Base64Backend())
            owner = user_repo.create(User(email="owner202@example.com", password_hash="h"))
            user_repo.update_pix(owner.id, "owner202@pix.com", "Owner Recebedor", "Campinas")
            billing_repo = SQLAlchemyBillingRepository(conn, Base64Backend())
            billing = billing_repo.create(
                Billing(
                    name="Apt 202",
                    pix_key="apt202@pix.com",
                    pix_merchant_name="",
                    pix_merchant_city="Campinas",
                    owner_type="user",
                    owner_id=owner.id,
                    items=[BillingItem(description="Aluguel", amount=120000, item_type=ItemType.FIXED)],
                )
            )
            service = self._service(conn, tmp_path)
            bill = service.generate_bill(
                billing=billing,
                reference_month="2025-04",
                variable_amounts={},
                extras=[],
                notes="",
                due_date="10/05/2025",
            )
            pdf_bytes = service.render_recibo(bill, billing)
        assert pdf_bytes[:5] == b"%PDF-"


class TestResolveReciboIssuer:
    class _Repo:
        def __init__(self, obj):
            self._obj = obj

        def get_by_id(self, _id):
            return self._obj

    class _Pix:
        def __init__(self, user=None, org=None):
            self.user_repo = TestResolveReciboIssuer._Repo(user)
            self.org_repo = TestResolveReciboIssuer._Repo(org)

    def _service(self, pix):
        return BillService(MagicMock(), MagicMock(), pix_service=pix)

    def test_org_owned_uses_org_name(self):
        from rentivo.models.organization import Organization

        svc = self._service(self._Pix(org=Organization(id=5, name="Imobiliária Central")))
        billing = Billing(id=1, name="Apt 101", owner_type="organization", owner_id=5)
        assert svc._resolve_recibo_issuer(billing) == "Imobiliária Central"

    def test_user_owned_uses_account_email(self):
        svc = self._service(self._Pix(user=User(id=7, email="dono@example.com", password_hash="h")))
        billing = Billing(id=1, name="Apt 101", owner_type="user", owner_id=7)
        assert svc._resolve_recibo_issuer(billing) == "dono@example.com"

    def test_falls_back_to_billing_name_when_owner_missing(self):
        svc = self._service(self._Pix(user=None))
        billing = Billing(id=1, name="Apt 101", owner_type="user", owner_id=7)
        assert svc._resolve_recibo_issuer(billing) == "Apt 101"

    def test_falls_back_to_billing_name_when_organization_missing(self):
        svc = self._service(self._Pix(org=None))
        billing = Billing(id=1, name="Apt 101", owner_type="organization", owner_id=7)
        assert svc._resolve_recibo_issuer(billing) == "Apt 101"

    def test_falls_back_to_billing_name_without_pix_service(self):
        svc = BillService(MagicMock(), MagicMock())  # pix_service=None
        billing = Billing(id=1, name="Apt 101", owner_type="organization", owner_id=5)
        assert svc._resolve_recibo_issuer(billing) == "Apt 101"

    def test_render_recibo_without_status_timestamp_uses_empty_payment_date(self):
        svc = BillService(MagicMock(), MagicMock())
        bill = Bill(id=1, uuid="u", billing_id=1, reference_month="2026-08", status_updated_at=None)
        billing = Billing(id=1, name="Apt 101")
        with patch.object(svc, "recibo_generator") as generator:
            generator.generate.return_value = b"%PDF"

            svc.render_recibo(bill, billing)

        assert generator.generate.call_args.kwargs["payment_date"] == ""


class TestReciboLifecycle:
    """change_status drives the recibo: generate on entering PAID, remove on leaving."""

    def _bill(self, status="sent", recibo_pdf_path=None):
        return Bill(
            id=42,
            uuid="b-uuid",
            billing_id=1,
            reference_month="2026-05",
            total_amount=10000,
            status=status,
            recibo_pdf_path=recibo_pdf_path,
        )

    def _billing(self):
        return Billing(id=1, uuid="bg-uuid", name="Apt 101", pix_merchant_name="Maria")

    def test_store_recibo_persists_and_records_key(self, tmp_path):
        repo = MagicMock()
        service = BillService(repo, LocalStorage(str(tmp_path)))
        bill = self._bill(status="paid")
        bill.status_updated_at = datetime.now(SP_TZ)

        path = service.store_recibo(bill, self._billing())

        assert path.endswith("bg-uuid/b-uuid.recibo.pdf")
        assert service.storage.get(path)[:5] == b"%PDF-"
        repo.update_recibo_pdf_path.assert_called_once_with(42, path)
        assert bill.recibo_pdf_path == path

    def test_store_recibo_requires_bill_id(self, tmp_path):
        service = BillService(MagicMock(), LocalStorage(str(tmp_path)))
        bill = self._bill(status="paid")
        bill.id = None
        with pytest.raises(ValueError, match="without an id"):
            service.store_recibo(bill, self._billing())

    def test_change_status_to_paid_renders_recibo_sync_without_job_service(self, tmp_path):
        repo = MagicMock()
        service = BillService(repo, LocalStorage(str(tmp_path)))
        bill = self._bill(status="sent")

        service.change_status(bill, "paid", billing=self._billing())

        assert bill.recibo_pdf_path is not None
        repo.update_recibo_pdf_path.assert_called_once()
        assert service.storage.get(bill.recibo_pdf_path)[:5] == b"%PDF-"

    def test_change_status_to_paid_without_billing_skips_render(self, tmp_path):
        """No billing available (e.g. a non-web caller) → nothing rendered."""
        repo = MagicMock()
        service = BillService(repo, LocalStorage(str(tmp_path)))
        bill = self._bill(status="sent")

        service.change_status(bill, "paid")

        assert bill.recibo_pdf_path is None
        repo.update_recibo_pdf_path.assert_not_called()

    def test_change_status_to_paid_enqueues_job_with_actor(self):
        from legacy_web.context import WebActor

        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)
        actor = WebActor(user_id=7, email="alice@example.com")

        service.change_status(self._bill(status="sent"), "paid", billing=self._billing(), actor=actor)

        job_service.enqueue_for.assert_called_once_with(actor, "recibo.render", {"bill_id": 42}, max_attempts=3)
        job_service.enqueue.assert_not_called()

    def test_change_status_to_paid_enqueues_job_without_actor(self):
        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)

        service.change_status(self._bill(status="sent"), "paid", billing=self._billing())

        job_service.enqueue_for.assert_not_called()
        job_service.enqueue.assert_called_once_with(
            "recibo.render", {"bill_id": 42}, source="", actor_id=None, actor_username="", max_attempts=3
        )

    def test_re_marking_paid_does_not_regenerate(self):
        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)

        service.change_status(self._bill(status="paid"), "paid", billing=self._billing())

        job_service.enqueue_for.assert_not_called()
        job_service.enqueue.assert_not_called()

    def test_change_status_leaving_paid_enqueues_s3_delete_with_actor(self):
        from legacy_web.context import WebActor

        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)
        actor = WebActor(user_id=7, email="alice@example.com")
        bill = self._bill(status="paid", recibo_pdf_path="bg-uuid/b-uuid.recibo.pdf")

        service.change_status(bill, "cancelled", billing=self._billing(), actor=actor)

        job_service.enqueue_for.assert_called_once_with(actor, "s3.delete", {"key": "bg-uuid/b-uuid.recibo.pdf"})
        repo.update_recibo_pdf_path.assert_called_once_with(42, None)
        assert bill.recibo_pdf_path is None

    def test_change_status_leaving_paid_enqueues_s3_delete_without_actor(self):
        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)
        bill = self._bill(status="paid", recibo_pdf_path="k/recibo.pdf")

        service.change_status(bill, "sent", billing=self._billing())

        job_service.enqueue.assert_called_once_with(
            "s3.delete", {"key": "k/recibo.pdf"}, source="", actor_id=None, actor_username=""
        )
        assert bill.recibo_pdf_path is None

    def test_change_status_leaving_paid_deletes_sync_without_job_service(self):
        repo = MagicMock()
        storage = MagicMock()
        service = BillService(repo, storage)
        bill = self._bill(status="paid", recibo_pdf_path="k/recibo.pdf")

        service.change_status(bill, "cancelled", billing=self._billing())

        storage.delete.assert_called_once_with("k/recibo.pdf")
        repo.update_recibo_pdf_path.assert_called_once_with(42, None)
        assert bill.recibo_pdf_path is None

    def test_change_status_leaving_paid_swallows_delete_error(self):
        repo = MagicMock()
        storage = MagicMock()
        storage.delete.side_effect = RuntimeError("boom")
        service = BillService(repo, storage)
        bill = self._bill(status="paid", recibo_pdf_path="k/recibo.pdf")

        service.change_status(bill, "cancelled", billing=self._billing())

        # The column is still cleared even though the file delete failed.
        repo.update_recibo_pdf_path.assert_called_once_with(42, None)
        assert bill.recibo_pdf_path is None

    def test_change_status_leaving_paid_without_recibo_is_noop(self):
        repo = MagicMock()
        job_service = MagicMock()
        service = BillService(repo, MagicMock(), job_service=job_service)
        bill = self._bill(status="paid", recibo_pdf_path=None)

        service.change_status(bill, "cancelled", billing=self._billing())

        job_service.enqueue.assert_not_called()
        job_service.enqueue_for.assert_not_called()
        repo.update_recibo_pdf_path.assert_not_called()

    def test_get_recibo_ref(self):
        storage = MagicMock()
        storage.get_ref.return_value = "REF"
        service = BillService(MagicMock(), storage)
        bill = self._bill(recibo_pdf_path="k/recibo.pdf")
        assert service.get_recibo_ref(bill) == "REF"
        storage.get_ref.assert_called_once_with("k/recibo.pdf")
