from rentivo.models.invite import Invite
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyInviteRepository,
    SQLAlchemyUserRepository,
)
from tests.web.conftest import create_org_in_db, get_test_user_id


def _setup_invite(test_engine):
    """Create a second user who owns an org, and invite the logged-in user."""
    user_id = get_test_user_id(test_engine)

    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        user2 = user_repo.create(User(username="invitee", email="inv@t.com", password_hash="h"))

    # user2 owns the org (auto-added as admin), then invites the logged-in user
    org = create_org_in_db(test_engine, "Test Org", user2.id)

    with test_engine.connect() as conn:
        invite_repo = SQLAlchemyInviteRepository(conn)
        invite = invite_repo.create(
            Invite(
                organization_id=org.id,
                invited_user_id=user_id,  # invite the logged-in user
                invited_by_user_id=user2.id,
                role="viewer",
                status="pending",
            )
        )
    return org, invite


class TestInviteList:
    def test_list_empty(self, auth_client):
        response = auth_client.get("/invites/")
        assert response.status_code == 200

    def test_list_with_pending(self, auth_client, test_engine):
        org, invite = _setup_invite(test_engine)
        response = auth_client.get("/invites/")
        assert response.status_code == 200
        assert "Test Org" in response.text


class TestInviteAccept:
    def test_accept(self, auth_client, test_engine, csrf_token):
        org, invite = _setup_invite(test_engine)
        response = auth_client.post(
            f"/invites/{invite.uuid}/accept",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_accept_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/invites/nonexistent/accept",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestInviteDecline:
    def test_decline(self, auth_client, test_engine, csrf_token):
        org, invite = _setup_invite(test_engine)
        response = auth_client.post(
            f"/invites/{invite.uuid}/decline",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_decline_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/invites/nonexistent/decline",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
