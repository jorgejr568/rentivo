"""Route tests for Google OAuth login (/auth/google/*)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from rentivo.encryption.base64 import Base64Backend
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
from rentivo.services.google_auth_service import GoogleAuthService, GoogleUserInfo
from rentivo.services.user_service import UserService
from tests.web.conftest import get_audit_logs


@pytest.fixture()
def google_enabled(monkeypatch):
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "google_auth_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")


def _stub_exchange(monkeypatch, info: GoogleUserInfo | None):
    async def _fake(self, code):
        return info

    monkeypatch.setattr(GoogleAuthService, "exchange_code", _fake)


def _start_flow(client) -> str:
    """GET /auth/google/login and return the state Google would echo back."""
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def _create_user(test_engine, email: str, password: str = "pass123"):
    with test_engine.connect() as conn:
        service = UserService(SQLAlchemyUserRepository(conn, Base64Backend()))
        return service.create_user(email, password)


class TestGoogleLoginRedirect:
    def test_returns_404_when_disabled(self, client):
        response = client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 404

    def test_redirects_to_google_when_enabled(self, client, google_enabled):
        response = client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        params = parse_qs(urlparse(location).query)
        assert params["client_id"] == ["test-client-id"]
        assert params["redirect_uri"] == ["http://localhost:8000/auth/google/callback"]
        assert params["state"][0]  # non-empty random state

    def test_redirects_home_when_already_logged_in(self, auth_client, google_enabled):
        response = auth_client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"


class TestGoogleCallbackRejections:
    def test_returns_404_when_disabled(self, client):
        response = client.get("/auth/google/callback?code=x&state=y", follow_redirects=False)
        assert response.status_code == 404

    def test_rejects_state_mismatch(self, client, google_enabled):
        _start_flow(client)
        response = client.get("/auth/google/callback?code=x&state=wrong", follow_redirects=False)
        assert response.status_code == 200
        assert "Não foi possível entrar com o Google" in response.text

    def test_rejects_when_no_pending_state_in_session(self, client, google_enabled):
        response = client.get("/auth/google/callback?code=x&state=y", follow_redirects=False)
        assert response.status_code == 200
        assert "Não foi possível entrar com o Google" in response.text

    def test_rejects_error_param(self, client, google_enabled):
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?error=access_denied&state={state}", follow_redirects=False)
        assert response.status_code == 200
        assert "Não foi possível entrar com o Google" in response.text

    def test_rejects_missing_code(self, client, google_enabled):
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?state={state}", follow_redirects=False)
        assert response.status_code == 200
        assert "Não foi possível entrar com o Google" in response.text

    def test_rejects_failed_exchange(self, client, google_enabled, monkeypatch):
        _stub_exchange(monkeypatch, None)
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 200
        assert "Não foi possível entrar com o Google" in response.text

    def test_rejects_unverified_email(self, client, google_enabled, monkeypatch):
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="u@e.com", email_verified=False))
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 200
        assert "não está verificado" in response.text

    def test_state_is_single_use(self, client, google_enabled, monkeypatch):
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="once@e.com", email_verified=True))
        state = _start_flow(client)
        first = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert first.status_code == 302
        # session was cleared on login; replaying the callback must fail
        second = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert second.status_code == 200
        assert "Não foi possível entrar com o Google" in second.text


class TestGoogleCallbackNewUser:
    def test_creates_user_and_logs_in(self, client, google_enabled, monkeypatch, test_engine):
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="newgoogle@example.com", email_verified=True))
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"

        # user exists, passwordless
        with test_engine.connect() as conn:
            repo = SQLAlchemyUserRepository(conn, Base64Backend())
            user = repo.get_by_email("newgoogle@example.com")
        assert user is not None
        assert user.password_hash == ""

        # session is fully authenticated
        assert client.get("/billings/", follow_redirects=False).status_code == 200

        # audit trail: signup + login, both attributed to google
        signups = get_audit_logs(test_engine, "user.signup")
        assert len(signups) == 1
        logins = get_audit_logs(test_engine, "user.login")
        assert len(logins) == 1

    def test_enqueues_welcome_email(self, client, google_enabled, monkeypatch):
        from rentivo.jobs.base import Job
        from rentivo.services.job_service import JobService

        sent: list[dict] = []

        def _capture(self, job_type, payload, **kwargs):
            if payload.get("event") == "welcome":
                sent.append({"to": payload["to_email"]})
            return Job(
                id=1,
                ulid="01HXYZ",
                job_type=job_type,
                payload=payload,
                attempts=0,
                max_attempts=5,
            )

        monkeypatch.setattr(JobService, "enqueue", _capture)
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="welcome@example.com", email_verified=True))
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 302
        assert sent == [{"to": "welcome@example.com"}]

    def test_google_user_cannot_login_with_password(self, client, google_enabled, monkeypatch):
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="nopass@example.com", email_verified=True))
        state = _start_flow(client)
        client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        client.post("/logout", follow_redirects=False)

        response = client.post(
            "/login",
            data={"email": "nopass@example.com", "password": "anything"},
            follow_redirects=False,
        )
        assert response.status_code == 200  # no 500 — guard in UserService.authenticate
        assert "E-mail ou senha inválidos" in response.text


class TestGoogleCallbackExistingUser:
    def test_logs_in_existing_user_without_signup(self, client, google_enabled, monkeypatch, test_engine):
        _create_user(test_engine, "existing@example.com")
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="existing@example.com", email_verified=True))
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"
        assert get_audit_logs(test_engine, "user.signup") == []
        assert len(get_audit_logs(test_engine, "user.login")) == 1

    def test_existing_user_keeps_password_login(self, client, google_enabled, monkeypatch, test_engine):
        _create_user(test_engine, "both@example.com", password="secret")
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="both@example.com", email_verified=True))
        state = _start_flow(client)
        client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        client.post("/logout", follow_redirects=False)

        response = client.post(
            "/login",
            data={"email": "both@example.com", "password": "secret"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/billings" in response.headers["location"]


class TestGoogleCallbackMFA:
    def _create_mfa_user(self, test_engine, email: str):
        import pyotp

        from rentivo.models.mfa import UserTOTP
        from rentivo.repositories.sqlalchemy import SQLAlchemyMFATOTPRepository

        user = _create_user(test_engine, email)
        secret = pyotp.random_base32()
        with test_engine.connect() as conn:
            totp_repo = SQLAlchemyMFATOTPRepository(conn, Base64Backend())
            totp_repo.create(UserTOTP(user_id=user.id, secret=secret, confirmed=False))
            totp_repo.confirm(user.id)
        return user, secret

    def test_redirects_to_mfa_verify_and_does_not_authenticate(self, client, google_enabled, monkeypatch, test_engine):
        self._create_mfa_user(test_engine, "mfa-google@example.com")
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="mfa-google@example.com", email_verified=True))
        state = _start_flow(client)
        response = client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/mfa-verify"

        # NOT logged in yet — protected pages still redirect to /login
        protected = client.get("/billings/", follow_redirects=False)
        assert protected.status_code == 302
        assert protected.headers["location"] == "/login"

        # a challenge was issued and audited
        assert len(get_audit_logs(test_engine, "mfa.challenge_issued")) == 1
        assert get_audit_logs(test_engine, "user.login") == []

    def test_totp_code_completes_google_login(self, client, google_enabled, monkeypatch, test_engine):
        import pyotp

        _, secret = self._create_mfa_user(test_engine, "mfa-flow@example.com")
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="mfa-flow@example.com", email_verified=True))
        state = _start_flow(client)
        client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)

        code = pyotp.TOTP(secret).now()
        response = client.post("/mfa-verify", data={"code": code, "method": "totp"}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"
        assert client.get("/billings/", follow_redirects=False).status_code == 200

    def test_org_mfa_enforcement_applies_to_google_login(self, client, google_enabled, monkeypatch, test_engine):
        from rentivo.services.mfa_service import MFAService

        _create_user(test_engine, "enforced@example.com")
        _stub_exchange(monkeypatch, GoogleUserInfo(sub="g-1", email="enforced@example.com", email_verified=True))
        monkeypatch.setattr(MFAService, "user_requires_mfa_setup", lambda self, user_id: True)
        state = _start_flow(client)
        client.get(f"/auth/google/callback?code=c&state={state}", follow_redirects=False)

        response = client.get("/billings/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/security/totp/setup"
