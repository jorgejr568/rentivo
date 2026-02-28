from unittest.mock import patch

import pytest

from rentivo.models.invite import Invite
from rentivo.models.organization import Organization
from rentivo.models.user import User


def _setup(user_repo, org_repo):
    """Create two users and an org for testing."""
    user1 = user_repo.create(User(username="alice", password_hash="h"))
    user2 = user_repo.create(User(username="bob", password_hash="h"))
    org = org_repo.create(Organization(name="TestOrg", created_by=user1.id))
    return user1, user2, org


class TestInviteRepoCRUD:
    def test_create_and_get(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        invite = invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        assert invite.id is not None
        assert invite.uuid != ""
        assert invite.organization_name == "TestOrg"
        assert invite.invited_username == "bob"
        assert invite.invited_by_username == "alice"

    def test_get_by_uuid(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        created = invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        fetched = invite_repo.get_by_uuid(created.uuid)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_uuid_not_found(self, invite_repo):
        assert invite_repo.get_by_uuid("nonexistent") is None

    def test_list_pending_for_user(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        pending = invite_repo.list_pending_for_user(user2.id)
        assert len(pending) == 1
        assert pending[0].invited_user_id == user2.id

    def test_list_pending_excludes_accepted(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        inv = invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        invite_repo.update_status(inv.id, "accepted")
        pending = invite_repo.list_pending_for_user(user2.id)
        assert len(pending) == 0

    def test_list_by_organization(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        invites = invite_repo.list_by_organization(org.id)
        assert len(invites) == 1

    def test_update_status(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        inv = invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        invite_repo.update_status(inv.id, "accepted")
        fetched = invite_repo.get_by_uuid(inv.uuid)
        assert fetched.status == "accepted"
        assert fetched.responded_at is not None

    def test_count_pending_for_user(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        assert invite_repo.count_pending_for_user(user2.id) == 1
        assert invite_repo.count_pending_for_user(user1.id) == 0

    def test_has_pending_invite(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        assert invite_repo.has_pending_invite(org.id, user2.id) is False
        invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user2.id,
                invited_by_user_id=user1.id,
                role="viewer",
                status="pending",
            )
        )
        assert invite_repo.has_pending_invite(org.id, user2.id) is True


class TestInviteRepoEdgeCases:
    def test_create_runtime_error(self, invite_repo, user_repo, org_repo):
        user1, user2, org = _setup(user_repo, org_repo)
        with patch.object(invite_repo, "get_by_uuid", return_value=None):
            with pytest.raises(RuntimeError, match="Failed to retrieve invite after create"):
                invite_repo.create(
                    Invite(
                        organization_id=org.id,
                        invited_user_id=user2.id,
                        invited_by_user_id=user1.id,
                        role="viewer",
                        status="pending",
                    )
                )
