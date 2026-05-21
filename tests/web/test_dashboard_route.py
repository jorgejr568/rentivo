from fastapi.testclient import TestClient


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
