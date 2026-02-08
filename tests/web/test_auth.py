class TestLoginPage:
    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200

    def test_login_page_redirects_if_logged_in(self, auth_client):
        response = auth_client.get("/login", follow_redirects=False)
        assert response.status_code == 302

    def test_login_success(self, client, test_engine):
        from landlord.repositories.sqlalchemy import SQLAlchemyUserRepository
        from landlord.services.user_service import UserService

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user_service.create_user("admin", "secret")

        response = client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_login_failure(self, client):
        response = client.post(
            "/login",
            data={"username": "wrong", "password": "wrong"},
        )
        assert response.status_code == 200


class TestLogout:
    def test_logout_redirects(self, auth_client):
        response = auth_client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]


class TestChangePassword:
    def test_change_password_page(self, auth_client):
        response = auth_client.get("/change-password")
        assert response.status_code == 200

    def test_change_password_success(self, auth_client):
        response = auth_client.post(
            "/change-password",
            data={
                "current_password": "testpass",
                "new_password": "newpass",
                "confirm_password": "newpass",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_change_password_mismatch(self, auth_client):
        response = auth_client.post(
            "/change-password",
            data={
                "current_password": "testpass",
                "new_password": "new1",
                "confirm_password": "new2",
            },
        )
        assert response.status_code == 200

    def test_change_password_wrong_current(self, auth_client):
        response = auth_client.post(
            "/change-password",
            data={
                "current_password": "wrongpass",
                "new_password": "newpass",
                "confirm_password": "newpass",
            },
        )
        assert response.status_code == 200

    def test_change_password_empty_fields(self, auth_client):
        response = auth_client.post(
            "/change-password",
            data={
                "current_password": "",
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
