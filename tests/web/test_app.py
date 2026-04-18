from unittest.mock import MagicMock, patch


class TestApp:
    def test_home_redirects_authenticated_user_to_billings(self, auth_client):
        response = auth_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"

    def test_unauthenticated_sees_landing_page(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 200
        assert "Rentivo" in response.text


class TestLifespan:
    def test_lifespan_skips_initialize_db_by_default(self, monkeypatch, test_engine):
        from starlette.testclient import TestClient

        import web.app as app_module

        calls: list[str] = []
        monkeypatch.setattr(app_module.settings, "web_run_migrations_on_startup", False)
        monkeypatch.setattr(app_module, "initialize_db", lambda: calls.append("init"))

        with TestClient(app_module.app):
            pass

        assert calls == []

    def test_lifespan_runs_initialize_db_when_enabled(self, monkeypatch, test_engine):
        from starlette.testclient import TestClient

        import web.app as app_module

        calls: list[str] = []
        monkeypatch.setattr(app_module.settings, "web_run_migrations_on_startup", True)
        monkeypatch.setattr(app_module, "initialize_db", lambda: calls.append("init"))

        with TestClient(app_module.app):
            pass

        assert calls == ["init"]


class TestExceptionHandler:
    def test_unhandled_exception_returns_500(self, test_engine):
        """Unhandled exceptions in routes should return 500."""
        from starlette.testclient import TestClient

        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService
        from web.app import app

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            UserService(user_repo).create_user("erruser", "errpass")

        client = TestClient(app, raise_server_exceptions=False)
        client.post("/login", data={"username": "erruser", "password": "errpass"})

        failing_repo = MagicMock()
        failing_repo.list_for_user.side_effect = RuntimeError("Unexpected DB crash")
        with patch("rentivo.services.container.get_billing_repository", return_value=failing_repo):
            response = client.get("/billings/")
        assert response.status_code == 500
        assert "Internal Server Error" in response.text
