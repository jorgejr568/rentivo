from unittest.mock import patch

import pytest

from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.repositories.sqlalchemy import SQLAlchemyBillingRepository


class TestBillingRepoCRUD:
    def test_create_and_get(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing = sample_billing()
        created = billing_repo.create(billing)

        assert created.id is not None
        assert created.uuid != ""
        assert created.name == "Apt 101"
        assert len(created.items) == 2
        assert created.created_at is not None

    def test_get_by_id(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        fetched = billing_repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == created.name

    def test_get_by_id_not_found(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        fetched = billing_repo.get_by_uuid(created.uuid)

        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.get_by_uuid("nonexistent") is None

    def test_list_all(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing_repo.create(sample_billing(name="Apt 101"))
        billing_repo.create(sample_billing(name="Apt 102"))

        billings = billing_repo.list_all()
        assert len(billings) == 2

    def test_list_all_empty(self, billing_repo: SQLAlchemyBillingRepository):
        assert billing_repo.list_all() == []

    def test_list_all_returns_items(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        billing_repo.create(sample_billing())
        billings = billing_repo.list_all()
        assert len(billings[0].items) == 2

    def test_update(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        created.name = "Apt 102 Updated"
        created.items = [
            BillingItem(description="New item", amount=50000, item_type=ItemType.FIXED),
        ]
        updated = billing_repo.update(created)

        assert updated.name == "Apt 102 Updated"
        assert len(updated.items) == 1
        assert updated.items[0].description == "New item"

    def test_soft_delete(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        billing_repo.delete(created.id)

        assert billing_repo.get_by_id(created.id) is None
        assert billing_repo.list_all() == []

    def test_soft_delete_hides_from_uuid_lookup(
        self, billing_repo: SQLAlchemyBillingRepository, sample_billing
    ):
        created = billing_repo.create(sample_billing())
        billing_repo.delete(created.id)
        assert billing_repo.get_by_uuid(created.uuid) is None


class TestBillingRepoEdgeCases:
    def test_create_runtime_error(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        with patch.object(billing_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve billing after create"):
                billing_repo.create(sample_billing())

    def test_update_runtime_error(self, billing_repo: SQLAlchemyBillingRepository, sample_billing):
        created = billing_repo.create(sample_billing())
        created.name = "Updated"
        with patch.object(billing_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve billing after update"):
                billing_repo.update(created)
