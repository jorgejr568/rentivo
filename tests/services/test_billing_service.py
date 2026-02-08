from unittest.mock import MagicMock

from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.services.billing_service import BillingService


class TestBillingService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = BillingService(self.mock_repo)

    def test_create_billing(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        self.mock_repo.create.return_value = Billing(
            id=1, name="Apt 101", items=items
        )
        result = self.service.create_billing("Apt 101", "desc", items, pix_key="key")
        self.mock_repo.create.assert_called_once()
        assert result.name == "Apt 101"

    def test_list_billings(self):
        self.mock_repo.list_all.return_value = [Billing(name="A"), Billing(name="B")]
        result = self.service.list_billings()
        assert len(result) == 2
        self.mock_repo.list_all.assert_called_once()

    def test_get_billing(self):
        self.mock_repo.get_by_id.return_value = Billing(id=1, name="Apt 101")
        result = self.service.get_billing(1)
        assert result.name == "Apt 101"

    def test_get_billing_by_uuid(self):
        self.mock_repo.get_by_uuid.return_value = Billing(name="Apt 101", uuid="abc")
        result = self.service.get_billing_by_uuid("abc")
        assert result.uuid == "abc"

    def test_update_billing(self):
        billing = Billing(id=1, name="Updated")
        self.mock_repo.update.return_value = billing
        result = self.service.update_billing(billing)
        self.mock_repo.update.assert_called_once_with(billing)
        assert result.name == "Updated"

    def test_delete_billing(self):
        self.service.delete_billing(1)
        self.mock_repo.delete.assert_called_once_with(1)
