from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Connection, text

from rentivo.models.receipt import Receipt
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyReceiptRepository,
)
from tests.conftest import _sample_bill, _sample_billing


@pytest.fixture()
def billing_with_bill(db_connection: Connection, encryption):
    """Create a billing and a bill for testing receipts."""
    billing_repo = SQLAlchemyBillingRepository(db_connection, encryption)
    bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
    billing = billing_repo.create(_sample_billing())
    bill = bill_repo.create(_sample_bill(billing_id=billing.id))
    return billing, bill


class TestReceiptRepoCRUD:
    def test_create_and_get(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipt = Receipt(
            bill_id=bill.id,
            filename="receipt.pdf",
            storage_key="billing/bill/receipts/abc.pdf",
            content_type="application/pdf",
            file_size=1024,
            sort_order=0,
        )
        created = receipt_repo.create(receipt)
        assert created.id is not None
        assert created.uuid != ""
        assert created.bill_id == bill.id
        assert created.filename == "receipt.pdf"
        assert created.storage_key == "billing/bill/receipts/abc.pdf"
        assert created.content_type == "application/pdf"
        assert created.file_size == 1024
        assert created.sort_order == 0
        assert created.created_at is not None

    def test_get_by_id(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipt = Receipt(
            bill_id=bill.id,
            filename="test.jpg",
            storage_key="key.jpg",
            content_type="image/jpeg",
            file_size=500,
        )
        created = receipt_repo.create(receipt)
        fetched = receipt_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.filename == "test.jpg"

    def test_get_by_id_not_found(self, receipt_repo):
        assert receipt_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipt = Receipt(
            bill_id=bill.id,
            filename="test.png",
            storage_key="key.png",
            content_type="image/png",
            file_size=800,
        )
        created = receipt_repo.create(receipt)
        fetched = receipt_repo.get_by_uuid(created.uuid)
        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, receipt_repo):
        assert receipt_repo.get_by_uuid("nonexistent") is None

    def test_list_by_bill_ordered(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="second.pdf",
                storage_key="k2.pdf",
                content_type="application/pdf",
                file_size=100,
                sort_order=1,
            )
        )
        receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="first.pdf",
                storage_key="k1.pdf",
                content_type="application/pdf",
                file_size=200,
                sort_order=0,
            )
        )
        results = receipt_repo.list_by_bill(bill.id)
        assert len(results) == 2
        assert results[0].sort_order == 0
        assert results[0].filename == "first.pdf"
        assert results[1].sort_order == 1
        assert results[1].filename == "second.pdf"

    def test_list_by_bill_empty(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        assert receipt_repo.list_by_bill(bill.id) == []

    def test_delete(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        created = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="del.pdf",
                storage_key="k.pdf",
                content_type="application/pdf",
                file_size=50,
            )
        )
        receipt_repo.delete(created.id)
        assert receipt_repo.get_by_id(created.id) is None

    def test_delete_for_render_operation_requires_current_bill_ownership(
        self,
        receipt_repo,
        billing_with_bill,
        db_connection,
        encryption,
    ):
        _, bill = billing_with_bill
        bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
        created = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="guarded.pdf",
                storage_key="guarded.pdf",
                content_type="application/pdf",
                file_size=50,
            )
        )
        operation_a = "01JRENDEROPERATION000000001"
        operation_b = "01JRENDEROPERATION000000002"
        bill_repo.begin_pdf_render(bill.id, operation_a)
        bill_repo.begin_pdf_render(bill.id, operation_b)

        assert receipt_repo.delete_for_render_operation(created.id, bill.id, operation_a) is False
        assert receipt_repo.get_by_id(created.id) == created

        assert receipt_repo.delete_for_render_operation(created.id, bill.id, operation_b) is True
        assert receipt_repo.get_by_id(created.id) is None

    def test_delete_for_render_operation_rolls_back_when_receipt_is_missing(
        self,
        receipt_repo,
        billing_with_bill,
        db_connection,
        encryption,
    ):
        _, bill = billing_with_bill
        bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
        operation_id = "01JRENDEROPERATION000000001"
        bill_repo.begin_pdf_render(bill.id, operation_id)

        assert receipt_repo.delete_for_render_operation(9999, bill.id, operation_id) is False
        assert bill_repo.get_pdf_render_state(bill.id)[0] == operation_id

    def test_delete_for_render_operation_rolls_back_repository_error(self, encryption):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyReceiptRepository(conn, encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.delete_for_render_operation(1, 2, "operation")

        conn.rollback.assert_called_once_with()

    def test_delete_many_is_atomic_batch(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipts = [
            receipt_repo.create(
                Receipt(
                    bill_id=bill.id,
                    filename=f"{index}.pdf",
                    storage_key=f"{index}.pdf",
                    content_type="application/pdf",
                    file_size=1,
                )
            )
            for index in range(2)
        ]

        assert receipt_repo.delete_many([receipt.id for receipt in receipts]) == 2
        assert receipt_repo.list_by_bill(bill.id) == []
        assert receipt_repo.delete_many([]) == 0

    def test_restore_after_failed_render_restores_receipt_and_bill_idempotently(
        self,
        receipt_repo,
        billing_with_bill,
        db_connection,
        encryption,
    ):
        _, bill = billing_with_bill
        bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
        created = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="restore.pdf",
                storage_key="restore.pdf",
                content_type="application/pdf",
                file_size=50,
                sort_order=4,
            )
        )
        bill_repo.update_pdf_path(bill.id, "old.pdf")
        bill_repo.update_pdf_render_status(bill.id, "succeeded")
        receipt_repo.delete(created.id)
        operation_id = "01JRENDEROPERATION000000001"
        bill_repo.begin_pdf_render(bill.id, operation_id)

        assert receipt_repo.restore_after_failed_render(created, operation_id, "old.pdf", "succeeded") is True
        assert receipt_repo.restore_after_failed_render(created, operation_id, "old.pdf", "succeeded") is True

        restored = receipt_repo.get_by_id(created.id)
        assert restored == created
        assert bill_repo.get_pdf_render_state(bill.id) == (None, "succeeded", "old.pdf")

    def test_restore_after_failed_render_rejects_foreign_operation(
        self,
        receipt_repo,
        billing_with_bill,
        db_connection,
        encryption,
    ):
        _, bill = billing_with_bill
        bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
        created = receipt_repo.create(Receipt(bill_id=bill.id, filename="restore.pdf"))
        receipt_repo.delete(created.id)
        bill_repo.begin_pdf_render(bill.id, "01JRENDEROPERATION000000002")

        assert (
            receipt_repo.restore_after_failed_render(
                created,
                "01JRENDEROPERATION000000001",
                "old.pdf",
                "succeeded",
            )
            is False
        )
        assert receipt_repo.get_by_id(created.id) is None
        assert bill_repo.get_pdf_render_state(bill.id)[0] == "01JRENDEROPERATION000000002"

    def test_restore_after_failed_render_rejects_missing_receipt_id(self, receipt_repo):
        with pytest.raises(ValueError, match="without an id"):
            receipt_repo.restore_after_failed_render(
                Receipt(bill_id=1, filename="restore.pdf"),
                "operation",
                "old.pdf",
                "succeeded",
            )

    def test_restore_after_failed_render_returns_false_for_missing_bill(self, receipt_repo):
        assert (
            receipt_repo.restore_after_failed_render(
                Receipt(id=9999, bill_id=9999, filename="restore.pdf"),
                "operation",
                "old.pdf",
                "succeeded",
            )
            is False
        )

    def test_restore_after_failed_render_rejects_existing_receipt(
        self,
        receipt_repo,
        billing_with_bill,
        db_connection,
        encryption,
    ):
        _, bill = billing_with_bill
        bill_repo = SQLAlchemyBillRepository(db_connection, encryption)
        created = receipt_repo.create(Receipt(bill_id=bill.id, filename="restore.pdf"))
        bill_repo.begin_pdf_render(bill.id, "operation")

        assert (
            receipt_repo.restore_after_failed_render(
                created,
                "operation",
                "old.pdf",
                "succeeded",
            )
            is False
        )

    def test_restore_after_failed_render_rolls_back_lost_update(self, encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        selected = MagicMock()
        selected.mappings.return_value.fetchone.return_value = {
            "pdf_path": "old.pdf",
            "pdf_render_status": "pending",
            "pdf_render_operation_id": "operation",
        }
        missing_receipt = MagicMock()
        missing_receipt.mappings.return_value.fetchone.return_value = None
        conn.execute.side_effect = [
            selected,
            missing_receipt,
            MagicMock(),
            MagicMock(rowcount=0),
        ]
        repo = SQLAlchemyReceiptRepository(conn, encryption)
        receipt = Receipt(id=1, uuid="receipt", bill_id=1, filename="restore.pdf")

        assert repo.restore_after_failed_render(receipt, "operation", "old.pdf", "succeeded") is False
        conn.rollback.assert_called_once_with()

    def test_restore_after_failed_render_rolls_back_repository_error(self, encryption):
        conn = MagicMock()
        conn.dialect.name = "sqlite"
        conn.execute.side_effect = RuntimeError("database failed")
        repo = SQLAlchemyReceiptRepository(conn, encryption)

        with pytest.raises(RuntimeError, match="database failed"):
            repo.restore_after_failed_render(
                Receipt(id=1, bill_id=1, filename="restore.pdf"),
                "operation",
                "old.pdf",
                "succeeded",
            )

        conn.rollback.assert_called_once_with()

    def test_create_runtime_error(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        receipt = Receipt(
            bill_id=bill.id,
            filename="fail.pdf",
            storage_key="k.pdf",
            content_type="application/pdf",
            file_size=10,
        )
        with patch.object(receipt_repo, "get_by_uuid", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve receipt after create"):
                receipt_repo.create(receipt)

    def test_create_rolls_back_insert_when_hydration_fails(
        self,
        db_connection,
        encryption,
        billing_with_bill,
    ):
        _, bill = billing_with_bill
        failing_encryption = MagicMock(wraps=encryption)
        failing_encryption.decrypt_many.side_effect = RuntimeError("decrypt failed")
        repo = SQLAlchemyReceiptRepository(db_connection, failing_encryption)

        with pytest.raises(RuntimeError, match="decrypt failed"):
            repo.create(
                Receipt(
                    bill_id=bill.id,
                    filename="fail.pdf",
                    storage_key="k.pdf",
                    content_type="application/pdf",
                    file_size=10,
                )
            )

        assert db_connection.execute(text("SELECT COUNT(*) FROM receipts")).scalar_one() == 0

    def test_update_sort_orders(self, receipt_repo, billing_with_bill):
        _, bill = billing_with_bill
        r1 = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="a.pdf",
                storage_key="a",
                content_type="application/pdf",
                file_size=1,
                sort_order=0,
            )
        )
        r2 = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="b.pdf",
                storage_key="b",
                content_type="application/pdf",
                file_size=1,
                sort_order=1,
            )
        )
        r3 = receipt_repo.create(
            Receipt(
                bill_id=bill.id,
                filename="c.pdf",
                storage_key="c",
                content_type="application/pdf",
                file_size=1,
                sort_order=2,
            )
        )
        # Reverse order: c, b, a
        receipt_repo.update_sort_orders([(r3.id, 0), (r2.id, 1), (r1.id, 2)])

        results = receipt_repo.list_by_bill(bill.id)
        assert results[0].filename == "c.pdf"
        assert results[1].filename == "b.pdf"
        assert results[2].filename == "a.pdf"


class TestReceiptRepoEncryptionWiring:
    def test_constructor_accepts_encryption_backend(self, db_connection, fake_encryption):
        from rentivo.repositories.sqlalchemy import SQLAlchemyReceiptRepository

        repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
        assert repo.encryption is fake_encryption

    def test_factory_passes_encryption_backend(self, monkeypatch):
        from unittest.mock import MagicMock

        from rentivo.repositories.factory import get_receipt_repository

        called = {}

        class FakeRepo:
            def __init__(self, conn, encryption):
                called["conn"] = conn
                called["encryption"] = encryption

        monkeypatch.setattr("rentivo.db.get_connection", lambda: MagicMock())
        monkeypatch.setattr(
            "rentivo.repositories.sqlalchemy.SQLAlchemyReceiptRepository",
            FakeRepo,
        )
        repo = get_receipt_repository()
        assert repo is not None
        assert called["encryption"] is not None


class TestReceiptRepoEncryption:
    def test_create_encrypts_filename(self, db_connection, fake_encryption, sample_billing, sample_bill):
        from sqlalchemy import text

        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import (
            SQLAlchemyBillingRepository,
            SQLAlchemyBillRepository,
            SQLAlchemyReceiptRepository,
        )

        billing = SQLAlchemyBillingRepository(db_connection, fake_encryption).create(sample_billing())
        bill = SQLAlchemyBillRepository(db_connection, fake_encryption).create(sample_bill(billing_id=billing.id))

        repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
        created = repo.create(
            Receipt(
                bill_id=bill.id,
                filename="comprovante_joao_silva.pdf",
                storage_key="some/key.pdf",
                content_type="application/pdf",
                file_size=1234,
                sort_order=0,
            )
        )

        row = (
            db_connection.execute(
                text("SELECT filename FROM receipts WHERE id = :id"),
                {"id": created.id},
            )
            .mappings()
            .fetchone()
        )
        assert row["filename"] == "fake:comprovante_joao_silva.pdf"

    def test_get_and_list_decrypt_filename(self, db_connection, fake_encryption, sample_billing, sample_bill):
        from rentivo.models.receipt import Receipt
        from rentivo.repositories.sqlalchemy import (
            SQLAlchemyBillingRepository,
            SQLAlchemyBillRepository,
            SQLAlchemyReceiptRepository,
        )

        billing = SQLAlchemyBillingRepository(db_connection, fake_encryption).create(sample_billing())
        bill = SQLAlchemyBillRepository(db_connection, fake_encryption).create(sample_bill(billing_id=billing.id))

        repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
        created = repo.create(
            Receipt(
                bill_id=bill.id,
                filename="comprovante.pdf",
                storage_key="key.pdf",
                content_type="application/pdf",
                file_size=10,
                sort_order=0,
            )
        )

        fetched_by_id = repo.get_by_id(created.id)
        assert fetched_by_id is not None
        assert fetched_by_id.filename == "comprovante.pdf"

        fetched_by_uuid = repo.get_by_uuid(created.uuid)
        assert fetched_by_uuid is not None
        assert fetched_by_uuid.filename == "comprovante.pdf"

        listed = repo.list_by_bill(bill.id)
        assert [r.filename for r in listed] == ["comprovante.pdf"]

    def test_get_handles_legacy_plaintext_filename(self, db_connection, fake_encryption, sample_billing, sample_bill):
        from sqlalchemy import text

        from rentivo.repositories.sqlalchemy import (
            SQLAlchemyBillingRepository,
            SQLAlchemyBillRepository,
            SQLAlchemyReceiptRepository,
        )

        billing = SQLAlchemyBillingRepository(db_connection, fake_encryption).create(sample_billing())
        bill = SQLAlchemyBillRepository(db_connection, fake_encryption).create(sample_bill(billing_id=billing.id))

        db_connection.execute(
            text(
                "INSERT INTO receipts (uuid, bill_id, filename, storage_key, content_type, "
                "file_size, sort_order, created_at) "
                "VALUES ('01HXLEGACYRECEIPT00000000000', :bid, 'legacy.pdf', 'k.pdf', "
                "'application/pdf', 1, 0, '2026-04-01 00:00:00')"
            ),
            {"bid": bill.id},
        )
        db_connection.commit()

        repo = SQLAlchemyReceiptRepository(db_connection, fake_encryption)
        fetched = repo.get_by_uuid("01HXLEGACYRECEIPT00000000000")
        assert fetched is not None
        assert fetched.filename == "legacy.pdf"
