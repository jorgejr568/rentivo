from datetime import datetime
from unittest.mock import patch

import pytest

from rentivo.models.bill import SP_TZ, BillLineItem
from rentivo.models.billing import ItemType


class TestBillRepoCRUD:
    def _create_billing(self, billing_repo, sample_billing):
        return billing_repo.create(sample_billing())

    def test_create_and_get(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill = sample_bill(billing_id=billing.id)
        created = bill_repo.create(bill)

        assert created.id is not None
        assert created.uuid != ""
        assert created.billing_id == billing.id
        assert len(created.line_items) == 2
        assert created.total_amount == 295000

    def test_get_by_id_not_found(self, bill_repo):
        assert bill_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        fetched = bill_repo.get_by_uuid(created.uuid)

        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, bill_repo):
        assert bill_repo.get_by_uuid("nonexistent") is None

    def test_list_by_billing(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2025-01"))
        bill_repo.create(sample_bill(billing_id=billing.id, reference_month="2025-02"))

        bills = bill_repo.list_by_billing(billing.id)
        assert len(bills) == 2

    def test_list_by_billing_empty(self, bill_repo, billing_repo, sample_billing):
        billing = self._create_billing(billing_repo, sample_billing)
        assert bill_repo.list_by_billing(billing.id) == []

    def test_update(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        created.notes = "Updated notes"
        created.line_items = [
            BillLineItem(description="New item", amount=50000, item_type=ItemType.FIXED, sort_order=0),
        ]
        created.total_amount = 50000
        updated = bill_repo.update(created)

        assert updated.notes == "Updated notes"
        assert len(updated.line_items) == 1
        assert updated.total_amount == 50000

    def test_update_pdf_path(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.update_pdf_path(created.id, "/new/path.pdf")

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.pdf_path == "/new/path.pdf"

    def test_update_paid_at(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        bill_repo.update_paid_at(created.id, now)

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.paid_at is not None

    def test_update_paid_at_to_none(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        now = datetime.now(SP_TZ)
        bill_repo.update_paid_at(created.id, now)
        bill_repo.update_paid_at(created.id, None)

        fetched = bill_repo.get_by_id(created.id)
        assert fetched.paid_at is None

    def test_soft_delete(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.delete(created.id)

        assert bill_repo.get_by_id(created.id) is None
        assert bill_repo.list_by_billing(billing.id) == []

    def test_soft_delete_hides_from_uuid(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        bill_repo.delete(created.id)
        assert bill_repo.get_by_uuid(created.uuid) is None


class TestBillRepoEdgeCases:
    def _create_billing(self, billing_repo, sample_billing):
        return billing_repo.create(sample_billing())

    def test_create_runtime_error(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        bill = sample_bill(billing_id=billing.id)
        with patch.object(bill_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve bill after create"):
                bill_repo.create(bill)

    def test_update_runtime_error(self, bill_repo, billing_repo, sample_billing, sample_bill):
        billing = self._create_billing(billing_repo, sample_billing)
        created = bill_repo.create(sample_bill(billing_id=billing.id))
        created.notes = "Updated"
        with patch.object(bill_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve bill after update"):
                bill_repo.update(created)
