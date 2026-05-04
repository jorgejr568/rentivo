from unittest.mock import patch

import pytest
from sqlalchemy import Connection

from rentivo.models.receipt import Receipt
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
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
