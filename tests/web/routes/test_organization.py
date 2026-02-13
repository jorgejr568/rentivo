from unittest.mock import MagicMock, patch

from landlord.models.user import User
from landlord.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
from tests.web.conftest import create_billing_in_db, create_org_in_db, get_test_user_id


def _create_org_as_other_user(test_engine, org_name="Other Org"):
    """Create an org owned by a different user (not the test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        other = user_repo.create(User(username=f"other_{org_name}", password_hash="h"))
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
        from landlord.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
        from landlord.models.user import User

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        # Create another user and add as member
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user2 = user_repo.create(User(username="member", password_hash="h"))
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user2.id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{user2.id}/role",
            data={"csrf_token": csrf_token, "role": "manager"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_remove_member(self, auth_client, test_engine, csrf_token):
        from landlord.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
        from landlord.models.user import User

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user2 = user_repo.create(User(username="member2", password_hash="h"))
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user2.id, "viewer")

        response = auth_client.post(
            f"/organizations/{org.uuid}/members/{user2.id}/remove",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

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
        from landlord.repositories.sqlalchemy import SQLAlchemyUserRepository
        from landlord.models.user import User

        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_repo.create(User(username="invitee", password_hash="h"))

        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "username": "invitee", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_nonexistent_user(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "username": "nobody", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_invite_empty_username(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/invite",
            data={"csrf_token": csrf_token, "username": "", "role": "viewer"},
            follow_redirects=False,
        )
        assert response.status_code == 302


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
            data={"csrf_token": csrf_token, "username": "x", "role": "viewer"},
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
            data={"csrf_token": csrf_token, "username": "x", "role": "viewer"},
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
            other = user_repo.create(User(username="other_transfer", password_hash="h"))
        other_billing = create_billing_in_db(test_engine, name="Other Billing", owner_type="user", owner_id=other.id)
        response = auth_client.post(
            f"/organizations/{org.uuid}/transfer-billing",
            data={"csrf_token": csrf_token, "billing_uuid": other_billing.uuid},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_billing_already_org_owned(self, auth_client, test_engine, csrf_token):
        """Transfer fails when billing already belongs to an org."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Org4", user_id)
        # Create billing already owned by an org
        billing = create_billing_in_db(
            test_engine, name="Org Billing",
            owner_type="organization", owner_id=org.id,
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
            from landlord.models.billing import Billing
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=billing.id, uuid=billing.uuid, name="A",
                owner_type="user", owner_id=user_id,
            )
            mock_svc.transfer_to_organization.side_effect = ValueError("Transfer failed")
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/organizations/{org.uuid}/transfer-billing",
                data={"csrf_token": csrf_token, "billing_uuid": billing.uuid},
                follow_redirects=False,
            )
        assert response.status_code == 302
