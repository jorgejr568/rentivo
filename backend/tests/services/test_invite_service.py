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
        self.mock_user_repo.get_by_email.return_value = User(id=2, email="bob@example.com")
        self.mock_org_repo.get_member.return_value = None
        self.mock_invite_repo.has_pending_invite.return_value = False
        self.mock_invite_repo.create.return_value = Invite(id=1, organization_id=1, invited_user_id=2, role="viewer")
        result = self.service.send_invite(1, "bob@example.com", "viewer", 1)
        assert result.invited_user_id == 2

    def test_send_invite_user_not_found(self):
        self.mock_user_repo.get_by_email.return_value = None
        with pytest.raises(ValueError, match="not found"):
            self.service.send_invite(1, "nobody@example.com", "viewer", 1)

    def test_send_invite_already_member(self):
        self.mock_user_repo.get_by_email.return_value = User(id=2, email="bob@example.com")
        self.mock_org_repo.get_member.return_value = OrganizationMember(user_id=2)
        with pytest.raises(ValueError, match="already a member"):
            self.service.send_invite(1, "bob@example.com", "viewer", 1)

    def test_send_invite_duplicate_pending(self):
        self.mock_user_repo.get_by_email.return_value = User(id=2, email="bob@example.com")
        self.mock_org_repo.get_member.return_value = None
        self.mock_invite_repo.has_pending_invite.return_value = True
        with pytest.raises(ValueError, match="pending invite"):
            self.service.send_invite(1, "bob@example.com", "viewer", 1)

    def test_accept_invite(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.get_by_uuid.return_value = invite
        self.mock_invite_repo.accept_if_pending.return_value = True
        prepared = self.service.get_pending_invite("abc", 2, action="accept")
        result = self.service.accept_invite(prepared)
        assert result is invite
        self.mock_invite_repo.accept_if_pending.assert_called_once_with(1, 1, 2, "viewer")

    def test_accept_invite_preserves_legacy_uuid_call(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.get_by_uuid.return_value = invite
        self.mock_invite_repo.accept_if_pending.return_value = True

        assert self.service.accept_invite("abc", 2) is invite

    def test_accept_invite_wrong_user(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        with pytest.raises(ValueError, match="Not authorized"):
            self.service.get_pending_invite("abc", 999, action="accept")

    def test_accept_invite_not_pending(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="accepted"
        )
        with pytest.raises(ValueError, match="no longer pending"):
            self.service.get_pending_invite("abc", 2, action="accept")

    def test_accept_invite_not_found(self):
        self.mock_invite_repo.get_by_uuid.return_value = None
        with pytest.raises(ValueError, match="not found"):
            self.service.get_pending_invite("abc", 2, action="accept")

    def test_accept_invite_detects_atomic_transition_conflict(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.accept_if_pending.return_value = False

        with pytest.raises(ValueError, match="no longer pending"):
            self.service.accept_invite(invite)

    def test_decline_invite(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.get_by_uuid.return_value = invite
        self.mock_invite_repo.decline_if_pending.return_value = True
        prepared = self.service.get_pending_invite("abc", 2, action="decline")
        result = self.service.decline_invite(prepared)
        assert result is invite
        self.mock_invite_repo.decline_if_pending.assert_called_once_with(1, 1, 2)

    def test_decline_invite_preserves_legacy_uuid_call(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.get_by_uuid.return_value = invite
        self.mock_invite_repo.decline_if_pending.return_value = True

        assert self.service.decline_invite("abc", 2) is invite

    def test_decline_invite_wrong_user(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending"
        )
        with pytest.raises(ValueError, match="Not authorized"):
            self.service.get_pending_invite("abc", 999, action="decline")

    def test_decline_invite_not_pending(self):
        self.mock_invite_repo.get_by_uuid.return_value = Invite(
            id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="declined"
        )
        with pytest.raises(ValueError, match="no longer pending"):
            self.service.get_pending_invite("abc", 2, action="decline")

    def test_decline_invite_detects_atomic_transition_conflict(self):
        invite = Invite(id=1, uuid="abc", organization_id=1, invited_user_id=2, role="viewer", status="pending")
        self.mock_invite_repo.decline_if_pending.return_value = False

        with pytest.raises(ValueError, match="no longer pending"):
            self.service.decline_invite(invite)

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
