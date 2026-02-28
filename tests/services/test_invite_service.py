from unittest.mock import MagicMock

import pytest

from rentivo.models.invite import Invite
from rentivo.models.organization import OrganizationMember
from rentivo.models.user import User
from rentivo.services.invite_service import InviteService


class TestInviteService:
    def setup_method(self):
        self.mock_invite_repo = MagicMock()
        self.mock_org_repo = MagicMock()
        self.mock_user_repo = MagicMock()
        self.service = InviteService(self.mock_invite_repo, self.mock_org_repo, self.mock_user_repo)

    def test_send_invite_success(self):
        self.mock_user_repo.get_by_username.return_value = User(id=2, username="bob")
        self.mock_org_repo.get_member.return_value = None
        self.mock_invite_repo.has_pending_invite.return_value = False
        self.mock_invite_repo.create.return_value = Invite(id=1, organization_id=1, invited_user_id=2, role="viewer")
        result = self.service.send_invite(1, "bob", "viewer", 1)
        assert result.invited_user_id == 2

    def test_send_invite_user_not_found(self):
        self.mock_user_repo.get_by_username.return_value = None
        with pytest.raises(ValueError, match="not found"):
            self.service.send_invite(1, "nobody", "viewer", 1)

    def test_send_invite_already_member(self):
        self.mock_user_repo.get_by_username.return_value = User(id=2, username="bob")
        self.mock_org_repo.get_member.return_value = OrganizationMember(user_id=2)
        with pytest.raises(ValueError, match="already a member"):
            self.service.send_invite(1, "bob", "viewer", 1)

    def test_send_invite_duplicate_pending(self):
        self.mock_user_repo.get_by_username.return_value = User(id=2, username="bob")
        self.mock_org_repo.get_member.return_value = None
        self.mock_invite_repo.has_pending_invite.return_value = True
        with pytest.raises(ValueError, match="pending invite"):
            self.service.send_invite(1, "bob", "viewer", 1)

    def test_accept_invite(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        self.service.accept_invite("abc", 2)
        self.mock_org_repo.add_member.assert_called_once_with(1, 2, "viewer")
        self.mock_invite_repo.update_status.assert_called_once_with(1, "accepted")

    def test_accept_invite_wrong_user(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        with pytest.raises(ValueError, match="Not authorized"):
            self.service.accept_invite("abc", 999)

    def test_accept_invite_not_pending(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="accepted"
        )
        with pytest.raises(ValueError, match="no longer pending"):
            self.service.accept_invite("abc", 2)

    def test_accept_invite_not_found(self):
        self.mock_invite_repo.get_by_uuid.return_value = None
        with pytest.raises(ValueError, match="not found"):
            self.service.accept_invite("abc", 2)

    def test_decline_invite(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        self.service.decline_invite("abc", 2)
        self.mock_invite_repo.update_status.assert_called_once_with(1, "declined")

    def test_decline_invite_wrong_user(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        with pytest.raises(ValueError, match="Not authorized"):
            self.service.decline_invite("abc", 999)

    def test_decline_invite_not_pending(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="declined"
        )
        with pytest.raises(ValueError, match="no longer pending"):
            self.service.decline_invite("abc", 2)

    def test_list_pending(self):
        self.mock_invite_repo.list_pending_for_user.return_value = [Invite(id=1)]
        result = self.service.list_pending(1)
        assert len(result) == 1

    def test_list_org_invites(self):
        self.mock_invite_repo.list_by_organization.return_value = [Invite(id=1)]
        result = self.service.list_org_invites(1)
        assert len(result) == 1

    def test_count_pending(self):
        self.mock_invite_repo.count_pending_for_user.return_value = 3
        assert self.service.count_pending(1) == 3
