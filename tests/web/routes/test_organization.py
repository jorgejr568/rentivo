from unittest.mock import MagicMock, patch

from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
from tests.web.conftest import create_billing_in_db, create_org_in_db, get_test_user_id


def _create_org_as_other_user(test_engine, org_name="Other Org"):
    """Create an org owned by a different user (not the test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        other = user_repo.create(User(email=f"other_{org_name}@example.com", password_hash="h"))
    return create_org_in_db(test_engine, org_name, other.id)


class TestOrganizationList:
    def test_list_empty(self, auth_client):
        response = auth_client.get("/organizations/")
        assert response.status_code == 200

    def test_list_with_orgs(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        create_org_in_db(test_engine, "Test Org", user_id)
        response = auth_client.get("/organizations/")
        assert response.status_code == 200
        assert "Test Org" in response.text


class TestOrganizationCreate:
    def test_create_form(self, auth_client):
        response = auth_client.get("/organizations/create")
        assert response.status_code == 200

    def test_create_success(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/create",
            data={"csrf_token": csrf_token, "name": "My Org"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_no_name(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/create",
            data={"csrf_token": csrf_token, "name": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestOrganizationDetail:
    def test_detail(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.get(f"/organizations/{org.uuid}")
        assert response.status_code == 200
        assert "My Org" in response.text

    def test_detail_not_found(self, auth_client):
        response = auth_client.get("/organizations/nonexistent", follow_redirects=False)
        assert response.status_code == 302


class TestOrganizationEdit:
    def test_edit_form(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.get(f"/organizations/{org.uuid}/edit")
        assert response.status_code == 200

    def test_edit_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/edit",
            data={"csrf_token": csrf_token, "name": "Updated Org"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/edit",
            data={"csrf_token": csrf_token, "name": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_no_name(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/edit",
            data={"csrf_token": csrf_token, "name": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_invalid_pix_redirects_back(self, auth_client, test_engine, csrf_token):
        """An invalid PIX key bubbles up as ValueError from update_organization → flash + redirect."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "My Org",
                "pix_key": "not-a-valid-pix-key",
                "pix_merchant_name": "Merchant",
                "pix_merchant_city": "SP",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/organizations/{org.uuid}/edit"


class TestOrganizationDelete:
    def test_delete(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestMemberManagement:
    def test_change_role(self, auth_client, test_engine, csrf_token):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        # Create another user and add as member
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user2 = user_repo.create(User(email="member@example.com", password_hash="h"))
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user2.id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{user2.id}/role",
            data={"csrf_token": csrf_token, "role": "manager"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_remove_member(self, auth_client, test_engine, csrf_token):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user2 = user_repo.create(User(email="member2@example.com", password_hash="h"))
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user2.id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{user2.id}/remove",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_role_change_notifies_member(self, auth_client, test_engine, csrf_token, monkeypatch):
        from rentivo.services.email_service import EmailService

        sent: list[dict] = []

        def _capture(self, to_email, event, ctx):
            if event == "member_changed":
                sent.append(
                    {
                        "to": to_email,
                        "msg": ctx["change_message"],
                        "actor": ctx["actor_email"],
                        "org": ctx["org_name"],
                    }
                )
            return "id"

        monkeypatch.setattr(EmailService, "safe_send", _capture)

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "RoleNotifyOrg", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            target = user_repo.create(User(email="target@example.com", password_hash="h"))
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, target.id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{target.id}/role",
            data={"csrf_token": csrf_token, "role": "admin"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert sent and sent[0]["to"] == "target@example.com"
        assert "para Administrador" in sent[0]["msg"]
        assert sent[0]["org"] == "RoleNotifyOrg"

    def test_cannot_remove_self(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{user_id}/remove",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestOrganizationInvite:
    def test_invite_member(self, auth_client, test_engine, csrf_token):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_repo.create(User(email="invitee@example.com", password_hash="h"))

        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "email": "invitee@example.com", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_nonexistent_user(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "email": "nobody@example.com", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_empty_username(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "email": "", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_post_sends_invite_received_email(self, auth_client, test_engine, csrf_token, monkeypatch):
        from rentivo.services.email_service import EmailService

        sent: list[dict] = []

        def _capture(self, to_email, event, ctx):
            if event == "invite_received":
                sent.append(
                    {
                        "to": to_email,
                        "inviter": ctx["inviter_email"],
                        "org": ctx["org_name"],
                        "role": ctx["role_label"],
                        "url": ctx["invites_url"],
                    }
                )
            return "id"

        monkeypatch.setattr(EmailService, "safe_send", _capture)

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Acme", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_repo.create(User(email="invited@example.com", password_hash="h"))

        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "email": "invited@example.com", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert sent and sent[0]["to"] == "invited@example.com"
        assert sent[0]["org"] == "Acme"
        assert sent[0]["role"] == "Visualizador"
        assert sent[0]["url"].endswith("/invites/")


class TestOrganizationAccessDenied:
    """Test access denied paths for organizations."""

    def test_detail_not_member(self, auth_client, test_engine):
        org = _create_org_as_other_user(test_engine, "Other1")
        response = auth_client.get(f"/organizations/{org.uuid}", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_form_not_found(self, auth_client):
        response = auth_client.get("/organizations/nonexistent/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_form_not_admin(self, auth_client, test_engine):
        org = _create_org_as_other_user(test_engine, "Other2")
        # Add test user as viewer
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.get(f"/organizations/{org.uuid}/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_post_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other3")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/edit",
            data={"csrf_token": csrf_token, "name": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other4")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_change_role_not_found_org(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/members/1/role",
            data={"csrf_token": csrf_token, "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_change_role_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other5")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/members/1/role",
            data={"csrf_token": csrf_token, "role": "manager"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_change_role_invalid_role(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "MyOrg", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/members/1/role",
            data={"csrf_token": csrf_token, "role": "superadmin"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_remove_member_not_found_org(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/members/1/remove",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_remove_member_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other6")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/members/1/remove",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_not_found_org(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/invite",
            data={"csrf_token": csrf_token, "email": "x@example.com", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other7")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "email": "x@example.com", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestOrganizationTransferBilling:
    def test_transfer_billing_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Transfer Org", user_id)
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": billing.uuid},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_not_found_org(self, auth_client, csrf_token):
        response = auth_client.post(
            "/organizations/nonexistent/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_not_admin(self, auth_client, test_engine, csrf_token):
        org = _create_org_as_other_user(test_engine, "Other8")
        user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            repo = SQLAlchemyOrganizationRepository(conn)
            repo.add_member(org.id, user_id, "viewer")
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_no_uuid(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_not_found(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org2", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": "nonexistent"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_access_denied(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org3", user_id)
        # Create billing owned by another user
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(email="other_transfer@example.com", password_hash="h"))
        other_billing = create_billing_in_db(test_engine, name="Other Billing", owner_type="user", owner_id=other.id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": other_billing.uuid},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_notifies_and_audits(self, auth_client, test_engine, csrf_token, monkeypatch):
        """Issue #1: org-side transfer must email admins + previous owner AND audit-log BILLING_TRANSFER."""
        from rentivo.jobs.base import Job
        from rentivo.models.audit_log import AuditEventType
        from rentivo.models.organization import OrgRole
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository
        from rentivo.services.job_service import JobService
        from tests.web.conftest import get_audit_logs

        sent: list[dict] = []

        def _capture(self, job_type, payload, **kwargs):
            if payload.get("event") == "billing_transferred":
                sent.append({"to": payload["to_email"], "role": payload["ctx"]["recipient_role"]})
            return Job(
                id=1,
                ulid="01HXYZ",
                job_type=job_type,
                payload=payload,
                attempts=0,
                max_attempts=5,
            )

        monkeypatch.setattr(JobService, "enqueue", _capture)

        user_id = get_test_user_id(test_engine)
        # Billing previously owned by another user — so they should be notified.
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            prev_owner = user_repo.create(User(email="prev_owner_org@example.com", password_hash="h"))
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=prev_owner.id)

        # Actor is admin of the destination org. Add a second admin.
        org = create_org_in_db(test_engine, "Notif Org", user_id)
        other_admin_email = "second_admin@example.com"
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            other_admin = SQLAlchemyUserRepository(conn).create(User(email=other_admin_email, password_hash="h"))
            org_repo.add_member(org.id, other_admin.id, OrgRole.ADMIN.value)

        with patch(
            "web.routes.organization.get_authorization_service",
        ) as mock_auth_fn:
            mock_auth = MagicMock()
            mock_auth.can_transfer_billing.return_value = True
            mock_auth_fn.return_value = mock_auth
            response = auth_client.post(
                f"/organizations/{org.uuid}/transfer-billing",
                data={"csrf_token": csrf_token, "billing_uuid": billing.uuid},
                follow_redirects=False,
            )
        assert response.status_code == 302

        # Previous owner emailed with previous_owner role.
        assert any(s["to"] == "prev_owner_org@example.com" and s["role"] == "previous_owner" for s in sent)
        # Second admin emailed with destination_admin role.
        assert any(s["to"] == other_admin_email and s["role"] == "destination_admin" for s in sent)
        # Actor (test user) NOT emailed.
        assert not any(s["to"] == "testuser@example.com" for s in sent)

        # BILLING_TRANSFER audit logged.
        logs = get_audit_logs(test_engine, event_type=AuditEventType.BILLING_TRANSFER)
        assert len(logs) >= 1
        assert any(log.entity_uuid == billing.uuid for log in logs)


class TestInviteReturnsNone:
    """Cover branch 378->390: invite_service.send_invite returns None."""

    def test_invite_returns_none_skips_audit(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "InviteNoneOrg", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_repo.create(User(email="invite_target@example.com", password_hash="h"))

        with patch("web.routes.organization.get_invite_service") as mock_invite_svc_fn:
            mock_invite_svc = MagicMock()
            mock_invite_svc.send_invite.return_value = None
            mock_invite_svc_fn.return_value = mock_invite_svc
            response = auth_client.post(
                f"/organizations/{org.uuid}/invite",
                data={"csrf_token": csrf_token, "email": "invite_target@example.com", "role": "viewer"},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_transfer_billing_already_org_owned(self, auth_client, test_engine, csrf_token):
        """Transfer fails when billing already belongs to an org."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org4", user_id)
        # Create billing already owned by an org
        billing = create_billing_in_db(
            test_engine,
            name="Org Billing",
            owner_type="organization",
            owner_id=org.id,
        )
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": billing.uuid},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_value_error(self, auth_client, test_engine, csrf_token):
        """When transfer_to_organization raises ValueError, show flash error."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org5", user_id)
        billing = create_billing_in_db(test_engine, name="Transfer Billing")
        with patch(
            "web.routes.organization.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            from rentivo.models.billing import Billing

            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=billing.id,
                uuid=billing.uuid,
                name="A",
                owner_type="user",
                owner_id=user_id,
            )
            mock_svc.transfer_to_organization.side_effect = ValueError("Transfer failed")
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/organizations/{org.uuid}/transfer-billing",
                data={"csrf_token": csrf_token, "billing_uuid": billing.uuid},
                follow_redirects=False,
            )
        assert response.status_code == 302
