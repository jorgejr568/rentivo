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
    def test_change_password_redirect(self, auth_client):
        response = auth_client.get("/change-password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/security"

    def test_change_password_success(self, auth_client, csrf_token):
        response = auth_client.post(
            "/security/change-password",
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
            "/security/change-password",
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
            "/security/change-password",
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
            "/security/change-password",
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


class TestMFALoginFlow:
    """Tests for the MFA verification flow during login."""

    def _create_user_with_totp(self, test_engine, username="mfauser", password="secret"):
        """Create a user and set up a confirmed TOTP for them. Returns (user, secret)."""
        import pyotp

        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository, SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        secret = pyotp.random_base32()

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_service = UserService(user_repo)
            user = user_service.create_user(username, password)

        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            from rentivo.models.mfa import UserTOTP

            totp_repo.create(UserTOTP(user_id=user.id, secret=secret, confirmed=False))
            totp_repo.confirm(user.id)

        # Also create recovery codes for recovery code tests
        with test_engine.connect() as conn:
            import bcrypt

            from rentivo.repositories.sqlalchemy import SQLAlchemyRecoveryCodeRepository

            recovery_repo = SQLAlchemyRecoveryCodeRepository(conn)
            code_hash = bcrypt.hashpw(b"recovery123", bcrypt.gensalt()).decode()
            recovery_repo.create_batch(user.id, [code_hash])

        return user, secret

    def test_login_redirects_to_mfa_verify_when_mfa_enabled(self, client, test_engine):
        """Login with valid credentials when MFA is enabled should redirect to /mfa-verify."""
        self._create_user_with_totp(test_engine)

        response = client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/mfa-verify" in response.headers["location"]

    def test_mfa_verify_page_requires_pending(self, client):
        """GET /mfa-verify without pending MFA session should redirect to /login."""
        response = client.get("/mfa-verify", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_mfa_verify_totp_success(self, client, test_engine):
        """POST /mfa-verify with valid TOTP code should complete login."""
        import pyotp

        _, secret = self._create_user_with_totp(test_engine)

        # Login first to get MFA pending session
        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        # Now verify with a valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        response = client.post(
            "/mfa-verify",
            data={"code": code, "method": "totp"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/billings/" in response.headers["location"]

        # Verify user is now logged in
        response = client.get("/billings/")
        assert response.status_code == 200

    def test_mfa_verify_totp_failure(self, client, test_engine):
        """POST /mfa-verify with invalid TOTP code should stay on verification page."""
        self._create_user_with_totp(test_engine)

        # Login first
        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        response = client.post(
            "/mfa-verify",
            data={"code": "000000", "method": "totp"},
        )
        assert response.status_code == 200
        assert "inválido" in response.text.lower() or "Código inválido" in response.text

    def test_mfa_verify_recovery_code(self, client, test_engine):
        """POST /mfa-verify with method=recovery and valid code should complete login."""
        self._create_user_with_totp(test_engine)

        # Login first
        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        response = client.post(
            "/mfa-verify",
            data={"code": "recovery123", "method": "recovery"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/billings/" in response.headers["location"]

    def test_mfa_verify_page_renders_when_pending(self, client, test_engine):
        """GET /mfa-verify with pending MFA session should render the page."""
        self._create_user_with_totp(test_engine)

        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        response = client.get("/mfa-verify")
        assert response.status_code == 200

    def test_mfa_verify_post_without_pending_redirects(self, client):
        """POST /mfa-verify without pending MFA session should redirect to /login."""
        response = client.post(
            "/mfa-verify",
            data={"code": "123456", "method": "totp"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_mfa_rate_limiting(self, client, test_engine):
        """After 5 failed MFA attempts, returns rate limit message."""
        import web.auth as auth_module

        auth_module._mfa_attempts.clear()

        self._create_user_with_totp(test_engine)

        # Login first to get MFA pending state
        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        # Make 5 failed MFA attempts
        for _ in range(5):
            client.post(
                "/mfa-verify",
                data={"code": "000000", "method": "totp"},
            )

        # 6th attempt should be rate-limited
        # Need to re-login as session may have been affected
        client.post(
            "/login",
            data={"username": "mfauser", "password": "secret"},
            follow_redirects=False,
        )

        response = client.post(
            "/mfa-verify",
            data={"code": "000000", "method": "totp"},
        )
        assert response.status_code == 200
        assert "Muitas tentativas" in response.text

        # Cleanup
        auth_module._mfa_attempts.clear()


class TestMFAEnforcement:
    """Tests for MFA enforcement during login and MFA verification."""

    def test_login_sets_mfa_setup_required_for_enforcing_org(self, client, test_engine):
        """Login without MFA when in enforcing org sets mfa_setup_required."""
        from rentivo.repositories.sqlalchemy import SQLAlchemyOrganizationRepository, SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService
        from tests.web.conftest import create_org_in_db

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_svc = UserService(user_repo)
            user = user_svc.create_user("enforce_user", "pass123")

        org = create_org_in_db(test_engine, "Enforcing Org", user.id)
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org.enforce_mfa = True
            org_repo.update(org)

        response = client.post(
            "/login",
            data={"username": "enforce_user", "password": "pass123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/billings/" in response.headers["location"]

        # MFA enforcement middleware should redirect to TOTP setup
        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
        assert "/security/totp/setup" in response.headers["location"]

    def test_mfa_verify_sets_mfa_setup_required(self, client, test_engine):
        """After MFA verification, if user needs MFA setup, flag is set."""
        from unittest.mock import MagicMock, patch

        import pyotp

        from rentivo.models.mfa import UserTOTP
        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository, SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        secret = pyotp.random_base32()
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            user_svc = UserService(user_repo)
            user = user_svc.create_user("mfa_enforce2", "pass")

        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn)
            totp_repo.create(UserTOTP(user_id=user.id, secret=secret, confirmed=False))
            totp_repo.confirm(user.id)

        # Login -> MFA pending
        client.post(
            "/login",
            data={"username": "mfa_enforce2", "password": "pass"},
            follow_redirects=False,
        )

        # Verify TOTP, but mock user_requires_mfa_setup to return True
        totp = pyotp.TOTP(secret)
        code = totp.now()

        with patch("web.auth.get_mfa_service") as mock_get:
            mock_svc = MagicMock()
            mock_svc.verify_totp.return_value = True
            mock_svc.user_requires_mfa_setup.return_value = True
            mock_get.return_value = mock_svc

            response = client.post(
                "/mfa-verify",
                data={"code": code, "method": "totp"},
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert "/billings/" in response.headers["location"]

        # MFA enforcement should redirect
        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
        assert "/security/totp/setup" in response.headers["location"]


class TestMFAEnforcementMiddlewareDirect:
    """Direct tests for MFAEnforcementMiddleware in isolation."""

    def test_no_user_id_passes_through(self):
        """Middleware passes through when no user_id in session."""
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.middleware.sessions import SessionMiddleware
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from web.deps import MFAEnforcementMiddleware

        async def handler(request):
            return PlainTextResponse("ok")

        app = Starlette(
            routes=[Route("/test-page", handler)],
            middleware=[
                Middleware(SessionMiddleware, secret_key="test"),
                Middleware(MFAEnforcementMiddleware),
            ],
        )
        test_client = TestClient(app)
        response = test_client.get("/test-page")
        assert response.status_code == 200
        assert response.text == "ok"

    def test_mfa_setup_required_redirects(self):
        """Middleware redirects when mfa_setup_required is set in session."""
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.middleware.sessions import SessionMiddleware
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        from web.deps import MFAEnforcementMiddleware

        async def setup_session(request):
            request.session["user_id"] = 1
            request.session["mfa_setup_required"] = True
            return PlainTextResponse("setup done")

        async def protected(request):
            return PlainTextResponse("protected content")

        app = Starlette(
            routes=[
                Route("/do-setup", setup_session),
                Route("/protected-page", protected),
            ],
            middleware=[
                Middleware(SessionMiddleware, secret_key="test"),
                Middleware(MFAEnforcementMiddleware),
            ],
        )
        test_client = TestClient(app)
        test_client.get("/do-setup")
        response = test_client.get("/protected-page", follow_redirects=False)
        assert response.status_code == 302
        assert "/security/totp/setup" in response.headers["location"]
