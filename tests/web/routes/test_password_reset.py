from unittest.mock import patch


def test_forgot_password_get_renders(client):
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert "Informe o e-mail" in response.text or "Esqueci" in response.text


def test_forgot_password_post_silent_for_unknown_email(client, csrf_token):
    response = client.post(
        "/forgot-password",
        data={"email": "nobody@example.com", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302)


def test_forgot_password_post_sends_email_for_known_user(client, csrf_token, test_engine):
    from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
    from rentivo.services.user_service import UserService

    with test_engine.connect() as conn:
        UserService(SQLAlchemyUserRepository(conn)).register_user("known@example.com", "secret")
    with patch("rentivo.email.local.LocalEmailBackend.send", return_value="ok") as send:
        client.post(
            "/forgot-password",
            data={"email": "known@example.com", "csrf_token": csrf_token},
        )
        assert send.called


def test_reset_password_get_with_invalid_token_uses_invalid_template(client):
    # Without a token query param, the page renders the invalid state
    response = client.get("/reset-password")
    assert response.status_code == 200
    assert "inválido" in response.text.lower() or "expirado" in response.text.lower()


def test_reset_password_full_flow_changes_password(client, csrf_token, test_engine):
    from rentivo.email.local import LocalEmailBackend
    from rentivo.repositories.sqlalchemy import (
        SQLAlchemyPasswordResetTokenRepository,
        SQLAlchemyUserRepository,
    )
    from rentivo.services.email_service import EmailService
    from rentivo.services.password_reset_service import PasswordResetService
    from rentivo.services.user_service import UserService

    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        UserService(user_repo).register_user("flow@example.com", "old-password")
        token_repo = SQLAlchemyPasswordResetTokenRepository(conn)
        service = PasswordResetService(
            user_repo=user_repo,
            token_repo=token_repo,
            email_service=EmailService(LocalEmailBackend("/tmp/outbox-test"), "noreply@x"),
            user_service=UserService(user_repo),
            public_app_url="http://example.com",
        )
        raw = service.request_reset("flow@example.com")
    assert raw is not None

    response = client.post(
        "/reset-password",
        data={
            "token": raw,
            "password": "new-password",
            "confirm_password": "new-password",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/login" in response.headers["location"]

    login_resp = client.post(
        "/login",
        data={"email": "flow@example.com", "password": "new-password"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302
    assert "/billings" in login_resp.headers["location"]


def test_reset_password_rejects_mismatched_passwords(client, csrf_token):
    response = client.post(
        "/reset-password",
        data={
            "token": "anything",
            "password": "abc",
            "confirm_password": "xyz",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200
    assert "coincidem" in response.text.lower()


def test_forgot_password_get_redirects_when_logged_in(auth_client):
    response = auth_client.get("/forgot-password", follow_redirects=False)
    assert response.status_code == 302
    assert "/billings" in response.headers["location"]


def test_forgot_password_post_rejects_empty_email(client, csrf_token):
    response = client.post(
        "/forgot-password",
        data={"email": "  ", "csrf_token": csrf_token},
    )
    assert response.status_code == 200
    assert "Informe um e-mail" in response.text


def test_forgot_password_swallows_dispatch_exception(client, csrf_token):
    with patch(
        "rentivo.services.password_reset_service.PasswordResetService.request_reset",
        side_effect=RuntimeError("boom"),
    ):
        response = client.post(
            "/forgot-password",
            data={"email": "anyone@example.com", "csrf_token": csrf_token},
        )
    assert response.status_code == 200
    assert "instruções" in response.text.lower()


def test_reset_password_get_with_token_renders_form(client):
    response = client.get("/reset-password?token=abc")
    assert response.status_code == 200
    assert "Nova senha" in response.text
    assert 'value="abc"' in response.text


def test_reset_password_post_empty_token_renders_invalid(client, csrf_token):
    response = client.post(
        "/reset-password",
        data={
            "token": "",
            "password": "x",
            "confirm_password": "x",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200
    assert "inválido" in response.text.lower() or "expirado" in response.text.lower()


def test_reset_password_post_unknown_token_renders_invalid(client, csrf_token):
    response = client.post(
        "/reset-password",
        data={
            "token": "no-such-token",
            "password": "new-password",
            "confirm_password": "new-password",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 200
    assert "inválido" in response.text.lower() or "expirado" in response.text.lower()


def test_forgot_password_renders_widget_when_configured(client, monkeypatch):
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "turnstile_site_key", "sk-public-1")
    monkeypatch.setattr(settings, "turnstile_secret_key", "sk-secret-1")

    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert 'class="cf-turnstile"' in response.text
    assert 'data-sitekey="sk-public-1"' in response.text


def test_forgot_password_unconfigured_does_not_render_widget(client):
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert 'class="cf-turnstile"' not in response.text


def test_forgot_password_rejects_when_turnstile_fails(client, csrf_token, monkeypatch):
    from rentivo.services.turnstile_service import TurnstileService
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "turnstile_site_key", "sk")
    monkeypatch.setattr(settings, "turnstile_secret_key", "ss")

    async def _fail(self, token, remote_ip):
        return False

    monkeypatch.setattr(TurnstileService, "verify", _fail)

    response = client.post(
        "/forgot-password",
        data={"email": "x@example.com", "csrf_token": csrf_token, "cf-turnstile-response": "bad"},
    )
    assert response.status_code == 200
    assert "Verificação de segurança" in response.text


def test_forgot_password_succeeds_when_turnstile_passes(client, csrf_token, monkeypatch):
    from rentivo.services.turnstile_service import TurnstileService
    from rentivo.settings import settings

    monkeypatch.setattr(settings, "turnstile_site_key", "sk")
    monkeypatch.setattr(settings, "turnstile_secret_key", "ss")

    async def _pass(self, token, remote_ip):
        return True

    monkeypatch.setattr(TurnstileService, "verify", _pass)

    response = client.post(
        "/forgot-password",
        data={"email": "x@example.com", "csrf_token": csrf_token, "cf-turnstile-response": "good"},
    )
    # Silent success — same UI as "email sent".
    assert response.status_code == 200
    assert "instruções" in response.text.lower()


def test_reset_password_sends_completion_notification(client, csrf_token, test_engine, monkeypatch):
    from rentivo.email.local import LocalEmailBackend
    from rentivo.repositories.sqlalchemy import (
        SQLAlchemyPasswordResetTokenRepository,
        SQLAlchemyUserRepository,
    )
    from rentivo.services.email_service import EmailService
    from rentivo.services.password_reset_service import PasswordResetService
    from rentivo.services.user_service import UserService

    sent: list[dict] = []

    def _capture(self, to_email, event, ctx):
        if event == "password_reset_completed":
            sent.append({"to": to_email})
        return "id"

    monkeypatch.setattr(EmailService, "safe_send", _capture)

    with test_engine.connect() as conn:
        user_repo = SQLAlchemyUserRepository(conn)
        UserService(user_repo).register_user("flow2@example.com", "old-password")
        token_repo = SQLAlchemyPasswordResetTokenRepository(conn)
        svc = PasswordResetService(
            user_repo=user_repo,
            token_repo=token_repo,
            email_service=EmailService(LocalEmailBackend("/tmp/outbox-test"), "noreply@x"),
            user_service=UserService(user_repo),
            public_app_url="http://example.com",
        )
        raw = svc.request_reset("flow2@example.com")

    response = client.post(
        "/reset-password",
        data={
            "token": raw,
            "password": "new-password",
            "confirm_password": "new-password",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert sent == [{"to": "flow2@example.com"}]
