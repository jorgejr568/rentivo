from landlord.models.invite import Invite, InviteStatus


class TestInviteStatus:
    def test_values(self):
        assert InviteStatus.PENDING.value == "pending"
        assert InviteStatus.ACCEPTED.value == "accepted"
        assert InviteStatus.DECLINED.value == "declined"

    def test_from_string(self):
        assert InviteStatus("pending") is InviteStatus.PENDING


class TestInvite:
    def test_defaults(self):
        invite = Invite()
        assert invite.id is None
        assert invite.uuid == ""
        assert invite.organization_id == 0
        assert invite.organization_name == ""
        assert invite.invited_user_id == 0
        assert invite.invited_username == ""
        assert invite.invited_by_user_id == 0
        assert invite.invited_by_username == ""
        assert invite.role == "viewer"
        assert invite.status == "pending"
        assert invite.created_at is None
        assert invite.responded_at is None

    def test_with_values(self):
        invite = Invite(
            organization_id=1,
            invited_user_id=2,
            invited_by_user_id=3,
            role="manager",
            status="accepted",
        )
        assert invite.organization_id == 1
        assert invite.role == "manager"
        assert invite.status == "accepted"
