from landlord.models.billing import Billing, BillingItem, ItemType
from landlord.repositories.sqlalchemy import SQLAlchemyBillingRepository


def _create_billing_in_db(engine):
    with engine.connect() as conn:
        repo = SQLAlchemyBillingRepository(conn)
        billing = repo.create(
            Billing(
                name="Apt 101",
                description="Test",
                pix_key="",
                items=[
                    BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED),
                ],
            )
        )
    return billing


class TestBillingList:
    def test_list_empty(self, auth_client):
        response = auth_client.get("/billings/")
        assert response.status_code == 200

    def test_list_with_billings(self, auth_client, test_engine):
        _create_billing_in_db(test_engine)
        response = auth_client.get("/billings/")
        assert response.status_code == 200
        assert "Apt 101" in response.text


class TestBillingCreate:
    def test_create_form(self, auth_client):
        response = auth_client.get("/billings/create")
        assert response.status_code == 200

    def test_create_success(self, auth_client):
        response = auth_client.post(
            "/billings/create",
            data={
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

    def test_create_no_name(self, auth_client):
        response = auth_client.post(
            "/billings/create",
            data={
                "name": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-item_type": "fixed",
                "items-0-amount": "1000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_no_items(self, auth_client):
        response = auth_client.post(
            "/billings/create",
            data={
                "name": "Apt 301",
                "items-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_variable_item(self, auth_client):
        response = auth_client.post(
            "/billings/create",
            data={
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
        billing = _create_billing_in_db(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}")
        assert response.status_code == 200
        assert "Apt 101" in response.text

    def test_detail_not_found(self, auth_client):
        response = auth_client.get("/billings/nonexistent", follow_redirects=False)
        assert response.status_code == 302


class TestBillingEdit:
    def test_edit_form(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.get(f"/billings/{billing.uuid}/edit")
        assert response.status_code == 200

    def test_edit_form_not_found(self, auth_client):
        response = auth_client.get("/billings/nonexistent/edit", follow_redirects=False)
        assert response.status_code == 302

    def test_edit_success(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
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

    def test_edit_not_found(self, auth_client):
        response = auth_client.post(
            "/billings/nonexistent/edit",
            data={"name": "x", "items-TOTAL_FORMS": "1", "items-0-description": "y", "items-0-item_type": "fixed", "items-0-amount": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_no_items(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "name": "Apt 101",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingDelete:
    def test_delete(self, auth_client, test_engine):
        billing = _create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/billings/{billing.uuid}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_delete_not_found(self, auth_client):
        response = auth_client.post(
            "/billings/nonexistent/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
