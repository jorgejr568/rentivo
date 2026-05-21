import pytest
from fastapi.testclient import TestClient

from tests.web.conftest import (
    create_billing_in_db,
    create_org_in_db,
    get_test_user_id,
)
from web.app import templates


def test_post_login_lands_on_dashboard(client, test_engine):
    from rentivo.encryption.base64 import Base64Backend
    from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
    from rentivo.services.user_service import UserService

    with test_engine.connect() as conn:
        user_service = UserService(SQLAlchemyUserRepository(conn, Base64Backend()))
        user_service.create_user("dashboard_login@example.com", "secret")

    r = client.post(
        "/login",
        data={"email": "dashboard_login@example.com", "password": "secret"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"


def test_dashboard_redirects_unauth_to_login(client: TestClient):
    r = client.get("/dashboard", follow_redirects=False)
    # AuthMiddleware should redirect to /login or return 401
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert r.headers["location"].startswith("/login")


def test_dashboard_renders_for_authed_user(auth_client: TestClient):
    r = auth_client.get("/dashboard")
    assert r.status_code == 200
    assert "Faturado no mês" in r.text
    assert "Recebido no mês" in r.text
    assert "Em aberto" in r.text
    assert "Inadimplência" in r.text


@pytest.fixture
def enable_gtm(monkeypatch):
    monkeypatch.setattr("rentivo.settings.settings.gtm_container_id", "GTM-DASH")
    monkeypatch.setattr("rentivo.settings.settings.secret_key", "test-secret")
    monkeypatch.setitem(templates.env.globals, "gtm_container_id", "GTM-DASH")
    monkeypatch.setitem(templates.env.globals, "environment", "production")
    yield


def test_dashboard_view_pushes_analytics_event(enable_gtm, auth_client):
    """The /dashboard route emits the rentivo_dashboard_viewed event."""
    r = auth_client.get("/dashboard")
    assert r.status_code == 200
    assert "rentivo_dashboard_viewed" in r.text


def test_org_detail_renders_dashboard_partial(auth_client: TestClient, test_engine):
    """The dashboard partial is included on the org detail page."""
    user_id = get_test_user_id(test_engine)
    org = create_org_in_db(test_engine, "Dash Org", user_id)
    r = auth_client.get(f"/organizations/{org.uuid}")
    assert r.status_code == 200
    assert "Faturado no mês" in r.text
    assert "Recebido no mês" in r.text


def test_dashboard_renders_with_actual_chart_data(auth_client: TestClient, test_engine):
    """Regression: a render with non-empty monthly_series/status_counts must serialize cleanly.

    Previously, `_metrics.html` piped pydantic models through `|tojson`, which raised
    `TypeError: Object of type MonthlyPoint is not JSON serializable` once any bill existed.
    The empty-list rendering path hid the bug.
    """
    from datetime import date

    from sqlalchemy import text

    billing = create_billing_in_db(test_engine)
    current_month = date.today().strftime("%Y-%m")
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO bills (uuid, billing_id, reference_month, total_amount, "
                "due_date, status, status_updated_at, created_at) "
                "VALUES (:uuid, :bid, :rm, :amt, :due, :st, datetime('now'), datetime('now'))"
            ),
            {
                "uuid": "test-bill-regression",
                "bid": billing.id,
                "rm": current_month,
                "amt": 12345,
                "due": "2030-12-31",
                "st": "paid",
            },
        )
        conn.commit()

    r = auth_client.get("/dashboard")

    # The original bug raised TypeError → 500. A 200 response with both canvases is
    # the smoking-gun signal that serialization works.
    assert r.status_code == 200
    assert "dashboard-monthly-chart" in r.text
    assert "dashboard-status-chart" in r.text
    # And the current month's data must have flowed into the series payload.
    assert current_month in r.text
