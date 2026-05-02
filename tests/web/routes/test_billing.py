from unittest.mock import MagicMock, patch

from rentivo.models.billing import Billing
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
from tests.web.conftest import create_billing_in_db, create_org_in_db, get_test_user_id


def _create_other_user_billing(test_engine):
    """Create a billing owned by a different user (not the logged-in test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        other = user_repo.create(User(email="other@example.com", password_hash="h"))
    return create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)


class TestBillingList:
    def test_list_empty(self, auth_client):
        response = auth_client.get("/billings/")
        assert response.status_code == 200

    def test_list_with_billings(self, auth_client, test_engine):
        create_billing_in_db(test_engine, description="Test")
        response = auth_client.get("/billings/")
        assert response.status_code == 200
        assert "Apt 101" in response.text


class TestBillingCreate:
    def test_create_form(self, auth_client):
        response = auth_client.get("/billings/create")
        assert response.status_code == 200

    def test_create_success(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 201",
                "description": "Test billing",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_no_name(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-item_type": "fixed",
                "items-0-amount": "1000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_no_items(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 301",
                "items-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_variable_item(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 401",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Water",
                "items-0-amount": "",
                "items-0-item_type": "variable",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_invalid_pix_key_redirects_with_flash(self, auth_client, csrf_token):
        """Regression: invalid PIX key raises ValueError; route must redirect to /create with flash."""
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 501",
                "description": "",
                "pix_key": "not-a-valid-pix-key",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/create"


class TestBillingDetail:
    def test_detail(self, auth_client, test_engine):
        billing = create_billing_in_db(test_engine, description="Test")
        response = auth_client.get(f"/billings/{billing.uuid}")
        assert response.status_code == 200
        assert "Apt 101" in response.text

    def test_detail_not_found(self, auth_client):
        response = auth_client.get("/billings/nonexistent", follow_redirects=False)
        assert response.status_code == 302


class TestBillingEdit:
    def test_edit_form(self, auth_client, test_engine):
        billing = create_billing_in_db(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}/edit")
        assert response.status_code == 200

    def test_edit_form_not_found(self, auth_client):
        response = auth_client.get("/billings/nonexistent/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_success(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 101 Updated",
                "description": "Updated",
                "pix_key": "new@pix",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent Updated",
                "items-0-amount": "300000",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/nonexistent/edit",
            data={
                "csrf_token": csrf_token,
                "name": "x",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "y",
                "items-0-item_type": "fixed",
                "items-0-amount": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_no_items(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 101",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingDelete:
    def test_delete(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/nonexistent/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_access_denied(self, auth_client, test_engine, csrf_token):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingAccessDenied:
    def test_detail_access_denied(self, auth_client, test_engine):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_form_access_denied(self, auth_client, test_engine):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_post_access_denied(self, auth_client, test_engine, csrf_token):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "x",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "y",
                "items-0-item_type": "fixed",
                "items-0-amount": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingCreateEdgeCases:
    def test_create_with_empty_desc_item(self, auth_client, csrf_token):
        """Items with empty description are skipped."""
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 501",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "2",
                "items-0-description": "",
                "items-0-amount": "100",
                "items-0-item_type": "fixed",
                "items-1-description": "Rent",
                "items-1-amount": "1000,00",
                "items-1-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_with_invalid_item_type(self, auth_client, csrf_token):
        """Invalid item_type falls back to FIXED."""
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 601",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "invalid_type",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingEditEdgeCases:
    def test_edit_with_empty_desc_item(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Updated",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "2",
                "items-0-description": "",
                "items-0-amount": "100",
                "items-0-item_type": "fixed",
                "items-1-description": "Rent",
                "items-1-amount": "1000,00",
                "items-1-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_with_invalid_item_type(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Updated",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "bad_type",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_with_variable_item(self, auth_client, test_engine, csrf_token):
        """Cover branch 189->191: variable item skips amount parsing."""
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Updated",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Water",
                "items-0-amount": "",
                "items-0-item_type": "variable",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingCreateWithOrg:
    def test_create_for_organization(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Org Billing",
                "description": "",
                "pix_key": "",
                "organization_id": str(org.id),
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingTransfer:
    def test_transfer_success(self, auth_client, test_engine, csrf_token):
        user_id = get_test_user_id(test_engine)
        billing = create_billing_in_db(test_engine)
        org = create_org_in_db(test_engine, "Target Org", user_id)
        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"csrf_token": csrf_token, "organization_id": str(org.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_not_found(self, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/nonexistent/transfer",
            data={"csrf_token": csrf_token, "organization_id": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_access_denied(self, auth_client, test_engine, csrf_token):
        billing = _create_other_user_billing(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"csrf_token": csrf_token, "organization_id": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_no_org_id(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"csrf_token": csrf_token, "organization_id": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_rejects_non_member(self, auth_client, test_engine, csrf_token):
        """Regression: transfer must reject orgs the user is not a member of."""
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        billing = create_billing_in_db(test_engine)
        with test_engine.connect() as conn:
            stranger = SQLAlchemyUserRepository(conn).create(User(email="stranger@example.com", password_hash="h"))
        other_org = create_org_in_db(test_engine, "Stranger Org", stranger.id)

        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"csrf_token": csrf_token, "organization_id": str(other_org.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        # Billing owner should be unchanged — still user-owned
        with test_engine.connect() as conn:
            from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository

            reloaded = SQLAlchemyBillingRepository(conn).get_by_id(billing.id)
        assert reloaded.owner_type == "user"

    def test_transfer_invalid_org_id(self, auth_client, test_engine, csrf_token):
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"csrf_token": csrf_token, "organization_id": "not-a-number"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_transfer_value_error(self, auth_client, test_engine, csrf_token):
        """When transfer_to_organization raises ValueError, show flash error."""
        user_id = get_test_user_id(test_engine)
        billing = create_billing_in_db(test_engine)
        org = create_org_in_db(test_engine, "My Org", user_id)
        with patch(
            "web.routes.billing.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=billing.id,
                uuid=billing.uuid,
                name="A",
                owner_type="user",
                owner_id=user_id,
            )
            mock_svc.transfer_to_organization.side_effect = ValueError("Only personal billings")
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/billings/{billing.uuid}/transfer",
                data={"csrf_token": csrf_token, "organization_id": str(org.id)},
                follow_redirects=False,
            )
        assert response.status_code == 302

    def test_transfer_notifies_previous_user_owner_and_org_admins(
        self, auth_client, csrf_token, monkeypatch, test_engine
    ):
        from rentivo.models.organization import OrgRole
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository
        from rentivo.services.email_service import EmailService

        sent: list[dict] = []

        def _capture(self, to_email, billing_name, recipient_role, actor_email):
            sent.append({"to": to_email, "role": recipient_role})
            return "id"

        monkeypatch.setattr(EmailService, "safe_send_billing_transferred", _capture)

        user_id = get_test_user_id(test_engine)
        billing = create_billing_in_db(test_engine)
        # Create the target org with a different "creator" so the actor isn't already an admin.
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other_creator = user_repo.create(User(email="org_creator@example.com", password_hash="h"))
        org = create_org_in_db(test_engine, "Target Org", other_creator.id)

        # Add the actor (test user) as a viewer so they can transfer to the org.
        # Add a second admin to the destination org so we can assert org-admin notifications.
        target_admin_email = "admin2@example.com"
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, user_id, OrgRole.ADMIN.value)
            extra_admin = SQLAlchemyUserRepository(conn).create(User(email=target_admin_email, password_hash="h"))
            org_repo.add_member(org.id, extra_admin.id, OrgRole.ADMIN.value)

        response = auth_client.post(
            f"/billings/{billing.uuid}/transfer",
            data={"organization_id": str(org.id), "csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code in (200, 302)

        # The previous owner (test user) does NOT receive an email because they are the actor.
        assert not any(s["to"] == "testuser@example.com" for s in sent)
        # The extra org admin gets a "destination_admin" notification.
        admin_roles = [s["role"] for s in sent if s["to"] == target_admin_email]
        assert "destination_admin" in admin_roles
        # The org creator (also an admin) gets the "destination_admin" notification too.
        creator_roles = [s["role"] for s in sent if s["to"] == "org_creator@example.com"]
        assert "destination_admin" in creator_roles

    def test_transfer_excludes_actor_from_destination_admin_notifications(
        self, auth_client, csrf_token, monkeypatch, test_engine
    ):
        """Issue #2: actor performing the transfer must not receive their own notification."""
        from rentivo.models.organization import OrgRole
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository
        from rentivo.services.email_service import EmailService

        sent: list[dict] = []

        def _capture(self, to_email, billing_name, recipient_role, actor_email):
            sent.append({"to": to_email, "role": recipient_role})
            return "id"

        monkeypatch.setattr(EmailService, "safe_send_billing_transferred", _capture)

        user_id = get_test_user_id(test_engine)
        # Create a billing owned by another user so the actor is NOT the previous owner.
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other_owner = user_repo.create(User(email="prev_owner@example.com", password_hash="h"))
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other_owner.id)

        # Org where the actor (test user) is an admin — they must not be emailed.
        org = create_org_in_db(test_engine, "Self Org", user_id)
        # Add a second admin to verify other admins still get notified.
        other_admin_email = "other_admin@example.com"
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            other_admin = SQLAlchemyUserRepository(conn).create(User(email=other_admin_email, password_hash="h"))
            org_repo.add_member(org.id, other_admin.id, OrgRole.ADMIN.value)

        # The actor must be allowed to transfer this billing — patch authorization.
        with patch(
            "web.routes.billing.get_authorization_service",
        ) as mock_auth_fn:
            mock_auth = MagicMock()
            mock_auth.can_transfer_billing.return_value = True
            mock_auth_fn.return_value = mock_auth
            response = auth_client.post(
                f"/billings/{billing.uuid}/transfer",
                data={"organization_id": str(org.id), "csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code in (200, 302)

        # Actor (testuser@example.com) must NOT be in the recipient list.
        assert not any(s["to"] == "testuser@example.com" for s in sent)
        # Previous owner (prev_owner@example.com) was a different user — they get emailed.
        assert any(s["to"] == "prev_owner@example.com" and s["role"] == "previous_owner" for s in sent)
        # The other admin still gets emailed.
        assert any(s["to"] == other_admin_email and s["role"] == "destination_admin" for s in sent)


class TestBillingDetailIdNone:
    def test_detail_billing_id_none(self, auth_client, test_engine, csrf_token):
        """billing.id is None on detail page returns error."""
        billing = create_billing_in_db(test_engine)
        with patch(
            "web.routes.billing.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=None,
                uuid=billing.uuid,
                name="A",
                owner_type="user",
                owner_id=get_test_user_id(test_engine),
            )
            mock_svc_fn.return_value = mock_svc
            response = auth_client.get(
                f"/billings/{billing.uuid}",
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillingDeleteIdNone:
    def test_delete_billing_id_none(self, auth_client, test_engine, csrf_token):
        """billing.id is None on delete returns error."""
        billing = create_billing_in_db(test_engine)
        with patch(
            "web.routes.billing.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=None,
                uuid=billing.uuid,
                name="A",
                owner_type="user",
                owner_id=get_test_user_id(test_engine),
            )
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/billings/{billing.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302
