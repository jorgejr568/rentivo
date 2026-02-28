from unittest.mock import patch

import pytest
from sqlalchemy import Connection

from rentivo.models.receipt import Receipt
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyBillingRepository,
    SQLAlchemyBillRepository,
    SQLAlchemyReceiptRepository,
)
from tests.conftest import _sample_bill, _sample_billing


@pytest.fixture()
def receipt_repo(db_connection: Connection) -> SQLAlchemyReceiptRepository:
    return SQLAlchemyReceiptRepository(db_connection)


@pytest.fixture()
def billing_with_bill(db_connection: Connection):
    """Create a billing and a bill for testing receipts."""
    billing_repo = SQLAlchemyBillingRepository(db_connection)
    bill_repo = SQLAlchemyBillRepository(db_connection)
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
