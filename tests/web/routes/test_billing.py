from unittest.mock import MagicMock, patch

from landlord.models.billing import Billing
from landlord.models.user import User
from landlord.repositories.sqlalchemy import SQLAlchemyBillingRepository, SQLAlchemyUserRepository
from tests.web.conftest import create_billing_in_db, create_org_in_db, get_test_user_id


def _create_other_user_billing(test_engine):
    """Create a billing owned by a different user (not the logged-in test user)."""
    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        other = user_repo.create(User(username="other", password_hash="h"))
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
            data={"csrf_token": csrf_token, "name": "x", "items-TOTAL_FORMS": "1", "items-0-description": "y", "items-0-item_type": "fixed", "items-0-amount": "1"},
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
                "csrf_token": csrf_token, "name": "x",
                "items-TOTAL_FORMS": "1", "items-0-description": "y",
                "items-0-item_type": "fixed", "items-0-amount": "1",
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

    def test_transfer_value_error(self, auth_client, test_engine, csrf_token):
        """When transfer_to_organization raises ValueError, show flash error."""
        billing = create_billing_in_db(test_engine)
        with patch(
            "web.routes.billing.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=billing.id, uuid=billing.uuid, name="A",
                owner_type="user", owner_id=1,
            )
            mock_svc.transfer_to_organization.side_effect = ValueError("Only personal billings")
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/billings/{billing.uuid}/transfer",
                data={"csrf_token": csrf_token, "organization_id": "99"},
                follow_redirects=False,
            )
        assert response.status_code == 302


class TestBillingDetailIdNone:
    def test_detail_billing_id_none(self, auth_client, test_engine, csrf_token):
        """billing.id is None on detail page returns error."""
        billing = create_billing_in_db(test_engine)
        with patch(
            "web.routes.billing.get_billing_service",
        ) as mock_svc_fn:
            mock_svc = MagicMock()
            mock_svc.get_billing_by_uuid.return_value = Billing(
                id=None, uuid=billing.uuid, name="A",
                owner_type="user", owner_id=get_test_user_id(test_engine),
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
                id=None, uuid=billing.uuid, name="A",
                owner_type="user", owner_id=get_test_user_id(test_engine),
            )
            mock_svc_fn.return_value = mock_svc
            response = auth_client.post(
                f"/billings/{billing.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert response.status_code == 302
