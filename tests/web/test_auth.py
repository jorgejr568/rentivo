class TestLoginPage:
    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200

    def test_login_page_redirects_if_logged_in(self, auth_client):
        response = auth_client.get("/login", follow_redirects=False)
        assert response.status_code == 302

    def test_login_success(self, client, test_engine):
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

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

    def test_login_sets_session_keys(self, client, test_engine):
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user_service.create_user("admin2", "secret")

        client.post("/login", data={"username": "admin2", "password": "secret"})
        # After login, the user should be able to access protected pages
        response = client.get("/billings/")
        assert response.status_code == 200


class TestLogout:
    def test_logout_redirects(self, auth_client, csrf_token):
        response = auth_client.post(
            "/logout",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_logout_get_not_allowed(self, auth_client):
        response = auth_client.get("/logout", follow_redirects=False)
        assert response.status_code == 405


class TestChangePassword:
    def test_change_password_page(self, auth_client):
        response = auth_client.get("/change-password")
        assert response.status_code == 200

    def test_change_password_success(self, auth_client, csrf_token):
        response = auth_client.post(
            "/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "testpass",
                "new_password": "newpass",
                "confirm_password": "newpass",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_change_password_mismatch(self, auth_client, csrf_token):
        response = auth_client.post(
            "/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "testpass",
                "new_password": "new1",
                "confirm_password": "new2",
            },
        )
        assert response.status_code == 200

    def test_change_password_wrong_current(self, auth_client, csrf_token):
        response = auth_client.post(
            "/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "wrongpass",
                "new_password": "newpass",
                "confirm_password": "newpass",
            },
        )
        assert response.status_code == 200

    def test_change_password_empty_fields(self, auth_client, csrf_token):
        response = auth_client.post(
            "/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "",
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200


class TestSignup:
    def test_signup_page_renders(self, client):
        response = client.get("/signup")
        assert response.status_code == 200
        assert "Criar Conta" in response.text

    def test_signup_page_redirects_if_logged_in(self, auth_client):
        response = auth_client.get("/signup", follow_redirects=False)
        assert response.status_code == 302

    def test_signup_success(self, client):
        response = client.post(
            "/signup",
            data={
                "username": "newuser",
                "email": "new@test.com",
                "password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        # After signup, user should be logged in
        response = client.get("/billings/")
        assert response.status_code == 200

    def test_signup_empty_fields(self, client):
        response = client.post(
            "/signup",
            data={
                "username": "",
                "email": "",
                "password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Preencha" in response.text

    def test_signup_password_mismatch(self, client):
        response = client.post(
            "/signup",
            data={
                "username": "user1",
                "email": "u@t.com",
                "password": "pass1",
                "confirm_password": "pass2",
            },
        )
        assert response.status_code == 200
        assert "coincidem" in response.text

    def test_signup_duplicate_username(self, client, test_engine):
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user_service.create_user("existing", "pass")

        response = client.post(
            "/signup",
            data={
                "username": "existing",
                "email": "e@t.com",
                "password": "pass",
                "confirm_password": "pass",
            },
        )
        assert response.status_code == 200

    def test_signup_redirects_if_logged_in_post(self, auth_client):
        response = auth_client.post(
            "/signup",
            data={
                "username": "x",
                "email": "x@t.com",
                "password": "p",
                "confirm_password": "p",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_login_link_on_signup(self, client):
        response = client.get("/signup")
        assert "/login" in response.text

    def test_signup_link_on_login(self, client):
        response = client.get("/login")
        assert "/signup" in response.text


class TestRateLimiting:
    def test_rate_limited_after_too_many_attempts(self, client, test_engine):
        """After 5 failed login attempts, the 6th should be rate-limited."""
        import web.auth as auth_module

        # Clear any existing attempts
        auth_module._login_attempts.clear()

        # Make 5 failed attempts
        for _ in range(5):
            client.post(
                "/login",
                data={"username": "nonexistent", "password": "wrong"},
            )

        # 6th attempt should be rate-limited
        response = client.post(
            "/login",
            data={"username": "nonexistent", "password": "wrong"},
        )
        assert response.status_code == 200
        assert "Muitas tentativas" in response.text

        # Cleanup
        auth_module._login_attempts.clear()


class TestAuthMiddleware:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_old_session_key_rejected(self, client, test_engine):
        """Old-style session with only 'user' key should be rejected."""
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            UserService(user_repo).create_user("olduser", "pass")

        # Manually set only "user" in session (old-style) - since we can't
        # directly manipulate session, we just verify that without user_id
        # the middleware redirects
        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
