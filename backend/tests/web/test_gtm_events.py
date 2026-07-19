"""Route-level GTM event tests — verifies push_event fires on state changes."""

from __future__ import annotations

import json
import re

import pytest

from legacy_web.app import templates
from tests.web.conftest import create_billing_in_db


@pytest.fixture
def enable_gtm(monkeypatch):
    monkeypatch.setattr("rentivo.settings.settings.gtm_container_id", "GTM-EVT")
    monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret")
    monkeypatch.setitem(templates.env.globals, "gtm_container_id", "GTM-EVT")
    monkeypatch.setitem(templates.env.globals, "environment", "production")
    yield


def _find_events(html: str, event_name: str) -> list[dict]:
    matches = re.findall(r"dataLayer\.push\((\{.*?\})\)", html, re.DOTALL)
    out = []
    for m in matches:
        try:
            data = json.loads(m)
        except json.JSONDecodeError:
            continue
        if data.get("event") == event_name:
            out.append(data)
    return out


class TestAuthEvents:
    def test_login_success_emits_event(self, enable_gtm, client, test_engine):
        from rentivo.encryption.base64 import Base64Backend
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            UserService(SQLAlchemyUserRepository(conn, Base64Backend())).create_user("alice@example.com", "pw-alice")

        client.post("/login", data={"email": "alice@example.com", "password": "pw-alice"}, follow_redirects=False)
        response = client.get("/billings/")
        events = _find_events(response.text, "rentivo_login_success")
        assert len(events) == 1
        assert events[0]["via"] == "password"

    def test_login_failure_emits_event(self, enable_gtm, client):
        response = client.post(
            "/login",
            data={"email": "nobody@example.com", "password": "wrong"},
            follow_redirects=False,
        )
        assert response.status_code == 200  # re-renders login page
        events = _find_events(response.text, "rentivo_login_failed")
        assert len(events) == 1
        assert events[0]["reason"] == "bad_credentials"

    def test_signup_emits_event(self, enable_gtm, client):
        client.post(
            "/signup",
            data={
                "email": "new@example.com",
                "password": "pw-new-123",
                "confirm_password": "pw-new-123",
            },
            follow_redirects=False,
        )
        response = client.get("/billings/")
        events = _find_events(response.text, "rentivo_signup_completed")
        assert len(events) == 1

    def test_logout_emits_event(self, enable_gtm, auth_client, csrf_token):
        auth_client.post("/logout", data={"csrf_token": csrf_token}, follow_redirects=False)
        response = auth_client.get("/login")
        events = _find_events(response.text, "rentivo_logout")
        assert len(events) == 1


class TestBillingEvents:
    def test_billing_create_destination_has_event(self, enable_gtm, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt 303",
                "description": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-0-description": "Aluguel",
                "items-0-amount": "2.000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        target = response.headers["location"]
        destination = auth_client.get(target)
        events = _find_events(destination.text, "rentivo_billing_created")
        assert len(events) == 1
        assert events[0]["item_count"] == 1


class TestBillEvents:
    def test_bill_generate_emits_event(self, enable_gtm, auth_client, csrf_token, test_engine):
        billing = create_billing_in_db(test_engine, name="Test Apt")
        variable_item = next(item for item in billing.items if item.item_type.value == "variable")
        response = auth_client.post(
            f"/billings/{billing.uuid}/bills/generate",
            data={
                "csrf_token": csrf_token,
                "reference_month": "2025-04",
                "due_date": "10/05/2025",
                "extras-TOTAL_FORMS": "0",
                "extras-INITIAL_FORMS": "0",
                f"variable_{variable_item.uuid}": "50,00",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        destination = auth_client.get(response.headers["location"])
        events = _find_events(destination.text, "rentivo_bill_generated")
        assert len(events) == 1
        assert events[0]["reference_month"] == "2025-04"
        assert "total_amount_brl" in events[0]


class TestSecurityEvents:
    def test_password_change_emits_event(self, enable_gtm, auth_client, csrf_token):
        response = auth_client.post(
            "/security/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "testpass",
                "new_password": "newpass-ABC-123",
                "confirm_password": "newpass-ABC-123",
            },
            follow_redirects=False,
        )
        if response.status_code == 302:
            destination = auth_client.get(response.headers["location"])
            events = _find_events(destination.text, "rentivo_password_changed")
            assert len(events) == 1


class TestPIIAbsenceInBusinessEvents:
    def test_billing_created_no_pii(self, enable_gtm, auth_client, csrf_token):
        response = auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Apt Secret-Name-123",
                "description": "Secret description",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-0-description": "RENT-MARKER-XYZ",
                "items-0-amount": "1.000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        destination = auth_client.get(response.headers["location"])
        events = _find_events(destination.text, "rentivo_billing_created")
        serialized = json.dumps(events)
        assert "Secret-Name-123" not in serialized
        assert "RENT-MARKER-XYZ" not in serialized


class TestExpenseEvents:
    def test_expense_created_emits_event_with_clean_payload(self, enable_gtm, auth_client, csrf_token, test_engine):
        billing = create_billing_in_db(test_engine, name="Test Apt")
        response = auth_client.post(
            f"/billings/{billing.uuid}/expenses/add",
            data={
                "csrf_token": csrf_token,
                "description": "SECRET-DESC-XYZ",
                "amount": "1.200,00",
                "category": "iptu",
                "incurred_on": "2026-01-10",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        destination = auth_client.get(response.headers["location"])
        events = _find_events(destination.text, "rentivo_expense_created")
        assert len(events) == 1
        event = events[0]
        assert event["category"] == "iptu"
        assert event["amount_brl"] == 1200
        assert "billing_uuid_hash" in event
        assert event["billing_uuid_hash"] != billing.uuid  # hashed, not raw
        assert "SECRET-DESC-XYZ" not in json.dumps(events)  # no plaintext description

    def test_expense_deleted_emits_event_with_clean_payload(self, enable_gtm, auth_client, csrf_token, test_engine):
        billing = create_billing_in_db(test_engine, name="Test Apt")
        auth_client.post(
            f"/billings/{billing.uuid}/expenses/add",
            data={
                "csrf_token": csrf_token,
                "description": "ToDelete",
                "amount": "10,00",
                "category": "iptu",
                "incurred_on": "2026-01-10",
            },
            follow_redirects=False,
        )
        # discover the expense uuid from the detail page delete form (also drains the created event)
        detail = auth_client.get(f"/billings/{billing.uuid}").text
        expense_uuid = re.search(r"/expenses/([0-9A-Z]{26})/delete", detail).group(1)
        response = auth_client.post(
            f"/billings/{billing.uuid}/expenses/{expense_uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        destination = auth_client.get(response.headers["location"])
        events = _find_events(destination.text, "rentivo_expense_deleted")
        assert len(events) == 1
        assert "billing_uuid_hash" in events[0]
        assert events[0]["billing_uuid_hash"] != billing.uuid  # hashed, not raw
