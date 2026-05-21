from fastapi.testclient import TestClient


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
