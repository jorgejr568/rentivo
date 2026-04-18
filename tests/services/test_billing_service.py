from unittest.mock import MagicMock

import pytest

from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.organization import Organization, OrganizationMember
from rentivo.services.billing_service import BillingService


class TestBillingService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = BillingService(self.mock_repo)

    def test_create_billing(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        self.mock_repo.create.return_value = Billing(id=1, name="Apt 101", items=items)
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

    def test_create_billing_with_ownership(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        self.mock_repo.create.return_value = Billing(
            id=1,
            name="Apt 101",
            items=items,
            owner_type="organization",
            owner_id=5,
        )
        result = self.service.create_billing(
            "Apt 101",
            "desc",
            items,
            owner_type="organization",
            owner_id=5,
        )
        assert result.owner_type == "organization"
        assert result.owner_id == 5

    def test_list_billings_for_user(self):
        self.mock_repo.list_for_user.return_value = [Billing(name="A")]
        result = self.service.list_billings_for_user(1)
        assert len(result) == 1
        self.mock_repo.list_for_user.assert_called_once_with(1)

    def test_transfer_to_organization(self):
        self.mock_repo.get_by_id.return_value = Billing(id=1, name="A", owner_type="user", owner_id=1)
        self.service.transfer_to_organization(1, 5)
        self.mock_repo.transfer_owner.assert_called_once_with(1, "organization", 5)

    def test_transfer_not_found(self):
        self.mock_repo.get_by_id.return_value = None
        import pytest

        with pytest.raises(ValueError, match="Billing not found"):
            self.service.transfer_to_organization(1, 5)

    def test_transfer_already_org_owned(self):
        self.mock_repo.get_by_id.return_value = Billing(id=1, name="A", owner_type="organization", owner_id=3)

        with pytest.raises(ValueError, match="personal billings"):
            self.service.transfer_to_organization(1, 5)

    def test_create_billing_for_other_user_rejected(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]

        with pytest.raises(ValueError, match="another user"):
            self.service.create_billing(
                "Apt 101",
                "desc",
                items,
                owner_type="user",
                owner_id=2,
                actor_user_id=1,
            )

    def test_create_billing_for_org_requires_manage_role(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        mock_org_repo = MagicMock()
        mock_org_repo.get_by_id.return_value = Organization(id=5, name="Org")
        mock_org_repo.get_member.return_value = OrganizationMember(organization_id=5, user_id=1, role="viewer")
        service = BillingService(self.mock_repo, mock_org_repo)

        with pytest.raises(ValueError, match="permission to manage billings"):
            service.create_billing(
                "Apt 101",
                "desc",
                items,
                owner_type="organization",
                owner_id=5,
                actor_user_id=1,
            )

    def test_create_billing_for_org_manager_allowed(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        mock_org_repo = MagicMock()
        mock_org_repo.get_by_id.return_value = Organization(id=5, name="Org")
        mock_org_repo.get_member.return_value = OrganizationMember(organization_id=5, user_id=1, role="manager")
        mock_repo = MagicMock()
        mock_repo.create.return_value = Billing(
            id=1,
            name="Apt 101",
            items=items,
            owner_type="organization",
            owner_id=5,
        )
        service = BillingService(mock_repo, mock_org_repo)

        result = service.create_billing(
            "Apt 101",
            "desc",
            items,
            owner_type="organization",
            owner_id=5,
            actor_user_id=1,
        )

        mock_repo.create.assert_called_once()
        assert result.owner_type == "organization"

    def test_transfer_to_organization_requires_manage_role(self):
        mock_org_repo = MagicMock()
        mock_org_repo.get_by_id.return_value = Organization(id=5, name="Org")
        mock_org_repo.get_member.return_value = None
        service = BillingService(self.mock_repo, mock_org_repo)
        self.mock_repo.get_by_id.return_value = Billing(id=1, name="A", owner_type="user", owner_id=1)

        with pytest.raises(ValueError, match="permission to manage billings"):
            service.transfer_to_organization(1, 5, actor_user_id=1)


class TestTransactionalBillingService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.mock_conn = MagicMock()
        self.service = BillingService(self.mock_repo, db_conn=self.mock_conn)

    def test_create_billing_commits_once(self):
        items = [BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED)]
        self.mock_repo.create.return_value = Billing(id=1, name="Apt 101", items=items)

        result = self.service.create_billing("Apt 101", "desc", items, pix_key="key")

        assert result.name == "Apt 101"
        self.mock_conn.commit.assert_called_once()
        self.mock_conn.rollback.assert_not_called()

    def test_transfer_rolls_back_when_repo_fails(self):
        self.mock_repo.get_by_id.return_value = Billing(id=1, name="A", owner_type="user", owner_id=1)
        self.mock_repo.transfer_owner.side_effect = RuntimeError("transfer failed")

        with pytest.raises(RuntimeError, match="transfer failed"):
            self.service.transfer_to_organization(1, 5)

        self.mock_conn.rollback.assert_called_once()
        self.mock_conn.commit.assert_not_called()
