from unittest.mock import patch

import pytest

from rentivo.models.organization import Organization
from rentivo.models.user import User


def _create_user(user_repo, username="admin"):
    return user_repo.create(User(username=username, password_hash="hash"))


class TestOrganizationRepoCRUD:
    def test_create_and_get(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test Org", created_by=user.id))
        assert org.id is not None
        assert org.uuid != ""
        assert org.name == "Test Org"
        assert org.created_by == user.id

    def test_get_by_id(self, org_repo, user_repo):
        user = _create_user(user_repo)
        created = org_repo.create(Organization(name="Test Org", created_by=user.id))
        fetched = org_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.name == "Test Org"

    def test_get_by_id_not_found(self, org_repo):
        assert org_repo.get_by_id(9999) is None

    def test_get_by_uuid(self, org_repo, user_repo):
        user = _create_user(user_repo)
        created = org_repo.create(Organization(name="Test Org", created_by=user.id))
        fetched = org_repo.get_by_uuid(created.uuid)
        assert fetched is not None
        assert fetched.uuid == created.uuid

    def test_get_by_uuid_not_found(self, org_repo):
        assert org_repo.get_by_uuid("nonexistent") is None

    def test_update(self, org_repo, user_repo):
        user = _create_user(user_repo)
        created = org_repo.create(Organization(name="Original", created_by=user.id))
        created.name = "Updated"
        updated = org_repo.update(created)
        assert updated.name == "Updated"

    def test_soft_delete(self, org_repo, user_repo):
        user = _create_user(user_repo)
        created = org_repo.create(Organization(name="Test", created_by=user.id))
        org_repo.delete(created.id)
        assert org_repo.get_by_id(created.id) is None

    def test_list_by_user(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Org1", created_by=user.id))
        org_repo.add_member(org.id, user.id, "admin")
        orgs = org_repo.list_by_user(user.id)
        assert len(orgs) == 1
        assert orgs[0].name == "Org1"

    def test_list_by_user_empty(self, org_repo, user_repo):
        user = _create_user(user_repo)
        assert org_repo.list_by_user(user.id) == []


class TestOrganizationMemberOps:
    def test_add_and_get_member(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test", created_by=user.id))
        member = org_repo.add_member(org.id, user.id, "admin")
        assert member.user_id == user.id
        assert member.role == "admin"

    def test_get_member_not_found(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test", created_by=user.id))
        assert org_repo.get_member(org.id, 9999) is None

    def test_remove_member(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test", created_by=user.id))
        org_repo.add_member(org.id, user.id, "admin")
        org_repo.remove_member(org.id, user.id)
        assert org_repo.get_member(org.id, user.id) is None

    def test_list_members(self, org_repo, user_repo):
        user1 = _create_user(user_repo, "user1")
        user2 = _create_user(user_repo, "user2")
        org = org_repo.create(Organization(name="Test", created_by=user1.id))
        org_repo.add_member(org.id, user1.id, "admin")
        org_repo.add_member(org.id, user2.id, "viewer")
        members = org_repo.list_members(org.id)
        assert len(members) == 2
        assert members[0].username == "user1"
        assert members[1].username == "user2"

    def test_update_member_role(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test", created_by=user.id))
        org_repo.add_member(org.id, user.id, "viewer")
        org_repo.update_member_role(org.id, user.id, "admin")
        member = org_repo.get_member(org.id, user.id)
        assert member.role == "admin"


class TestOrganizationRepoEdgeCases:
    def test_create_runtime_error(self, org_repo, user_repo):
        user = _create_user(user_repo)
        with patch.object(org_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve org after create"):
                org_repo.create(Organization(name="Test", created_by=user.id))

    def test_update_runtime_error(self, org_repo, user_repo):
        user = _create_user(user_repo)
        created = org_repo.create(Organization(name="Test", created_by=user.id))
        created.name = "Updated"
        with patch.object(org_repo, "get_by_id", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve org after update"):
                org_repo.update(created)

    def test_add_member_runtime_error(self, org_repo, user_repo):
        user = _create_user(user_repo)
        org = org_repo.create(Organization(name="Test", created_by=user.id))
        with patch.object(org_repo, "get_member", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve member after create"):
                org_repo.add_member(org.id, user.id, "admin")
