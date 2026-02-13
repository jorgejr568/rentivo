from unittest.mock import MagicMock

from landlord.models.billing import Billing
from landlord.models.organization import OrganizationMember
from landlord.services.authorization_service import AuthorizationService


class TestAuthorizationService:
    def setup_method(self):
        self.mock_org_repo = MagicMock()
        self.service = AuthorizationService(self.mock_org_repo)

    def test_owner_can_view(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_view_billing(1, billing) is True

    def test_non_owner_cannot_view(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        self.mock_org_repo.get_member.return_value = None
        assert self.service.can_view_billing(2, billing) is False

    def test_org_member_can_view(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="viewer"
        )
        assert self.service.can_view_billing(2, billing) is True

    def test_owner_can_edit(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_edit_billing(1, billing) is True

    def test_org_admin_can_edit(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="admin"
        )
        assert self.service.can_edit_billing(2, billing) is True

    def test_org_viewer_cannot_edit(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="viewer"
        )
        assert self.service.can_edit_billing(2, billing) is False

    def test_org_manager_cannot_edit(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="manager"
        )
        assert self.service.can_edit_billing(2, billing) is False

    def test_owner_can_delete(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_delete_billing(1, billing) is True

    def test_owner_can_manage_bills(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_manage_bills(1, billing) is True

    def test_org_manager_can_manage_bills(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="manager"
        )
        assert self.service.can_manage_bills(2, billing) is True

    def test_org_viewer_cannot_manage_bills(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="viewer"
        )
        assert self.service.can_manage_bills(2, billing) is False

    def test_owner_can_transfer(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_transfer_billing(1, billing) is True

    def test_non_owner_cannot_transfer(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.can_transfer_billing(2, billing) is False

    def test_org_billing_cannot_transfer(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        assert self.service.can_transfer_billing(1, billing) is False

    def test_get_role_owner(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.get_role_for_billing(1, billing) == "owner"

    def test_get_role_org_member(self):
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        self.mock_org_repo.get_member.return_value = OrganizationMember(
            organization_id=10, user_id=2, role="manager"
        )
        assert self.service.get_role_for_billing(2, billing) == "manager"

    def test_get_role_none(self):
        billing = Billing(name="Test", owner_type="user", owner_id=1)
        assert self.service.get_role_for_billing(2, billing) is None

    def test_no_org_repo(self):
        service = AuthorizationService(None)
        billing = Billing(name="Test", owner_type="organization", owner_id=10)
        assert service.can_view_billing(2, billing) is False
