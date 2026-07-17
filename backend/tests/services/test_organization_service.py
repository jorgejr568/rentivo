from unittest.mock import MagicMock

import pytest

from rentivo.models.organization import Organization, OrganizationMember
from rentivo.services.organization_service import OrganizationService


class TestOrganizationService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = OrganizationService(self.mock_repo)

    def test_create_organization(self):
        self.mock_repo.create.return_value = Organization(id=1, name="Test Org", created_by=5)
        org = self.service.create_organization("Test Org", 5)
        self.mock_repo.create.assert_called_once()
        self.mock_repo.add_member.assert_called_once_with(1, 5, "admin")
        assert org.name == "Test Org"

    def test_get_by_id(self):
        self.mock_repo.get_by_id.return_value = Organization(id=1, name="Test Org")
        result = self.service.get_by_id(1)
        assert result.name == "Test Org"

    def test_get_by_uuid(self):
        self.mock_repo.get_by_uuid.return_value = Organization(id=1, name="Test Org", uuid="abc")
        result = self.service.get_by_uuid("abc")
        assert result.uuid == "abc"

    def test_list_user_organizations(self):
        self.mock_repo.list_by_user.return_value = [Organization(name="A"), Organization(name="B")]
        result = self.service.list_user_organizations(1)
        assert len(result) == 2

    def test_update_organization(self):
        org = Organization(id=1, name="Updated")
        self.mock_repo.update.return_value = org
        result = self.service.update_organization(org)
        assert result.name == "Updated"

    def test_delete_organization(self):
        self.service.delete_organization(1)
        self.mock_repo.delete.assert_called_once_with(1)

    def test_get_member(self):
        self.mock_repo.get_member.return_value = OrganizationMember(user_id=1, role="admin")
        result = self.service.get_member(1, 1)
        assert result.role == "admin"

    def test_list_members(self):
        self.mock_repo.list_members.return_value = [OrganizationMember(user_id=1)]
        result = self.service.list_members(1)
        assert len(result) == 1

    def test_add_member(self):
        self.mock_repo.add_member.return_value = OrganizationMember(user_id=2, role="viewer")
        result = self.service.add_member(1, 2, "viewer")
        assert result.role == "viewer"

    def test_remove_member(self):
        self.service.remove_member(1, 2)
        self.mock_repo.remove_member.assert_called_once_with(1, 2)

    def test_update_member_role(self):
        self.service.update_member_role(1, 2, "manager")
        self.mock_repo.update_member_role.assert_called_once_with(1, 2, "manager")

    def test_set_enforce_mfa_success(self):
        org = Organization(id=1, name="Test")
        self.mock_repo.get_by_id.return_value = org
        self.mock_repo.update.return_value = Organization(id=1, name="Test", enforce_mfa=True)
        result = self.service.set_enforce_mfa(1, True)
        assert result.enforce_mfa is True
        self.mock_repo.update.assert_called_once()

    def test_set_enforce_mfa_not_found(self):
        self.mock_repo.get_by_id.return_value = None
        with pytest.raises(ValueError, match="Organização não encontrada"):
            self.service.set_enforce_mfa(999, True)
