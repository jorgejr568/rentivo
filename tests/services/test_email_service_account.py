from unittest.mock import MagicMock

from rentivo.services.email_service import EmailService


def _service():
    backend = MagicMock()
    backend.send.return_value = "id"
    return EmailService(backend, from_address="noreply@rentivo.app"), backend


def test_send_welcome_renders_email_and_pix_url():
    service, backend = _service()
    service.safe_send_welcome(to_email="alice@example.com", pix_setup_url="http://x/security/pix")
    sent = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert "Bem-vindo" in sent.subject
    assert "alice@example.com" in sent.html_body
    assert "x/security/pix" in sent.html_body
    assert "x/security/pix" in sent.text_body


def test_send_password_changed_includes_metadata():
    service, backend = _service()
    service.safe_send_password_changed(
        to_email="alice@example.com",
        changed_at="01/05/2026 14:30",
        source_ip="203.0.113.5",
        reset_url="http://x/forgot-password",
    )
    sent = backend.send.call_args[0][0]
    assert "01/05/2026 14:30" in sent.html_body
    assert "203.0.113.5" in sent.text_body
    assert "Senha alterada" in sent.subject


def test_send_mfa_changed_renders_label_and_meta():
    service, backend = _service()
    service.safe_send_mfa_changed(
        to_email="alice@example.com",
        change_label="TOTP ativado",
        changed_at="01/05/2026 14:30",
        source_ip="203.0.113.5",
        reset_url="http://x/forgot-password",
    )
    sent = backend.send.call_args[0][0]
    assert "TOTP ativado" in sent.html_body
    assert "TOTP ativado" in sent.text_body
    assert "203.0.113.5" in sent.html_body


def test_send_new_device_login_renders_metadata():
    service, backend = _service()
    service.safe_send_new_device_login(
        to_email="alice@example.com",
        logged_in_at="01/05/2026 14:30",
        source_ip="203.0.113.5",
        user_agent="Mozilla/5.0 ...",
        reset_url="http://x/forgot-password",
    )
    sent = backend.send.call_args[0][0]
    assert "Novo acesso" in sent.subject
    assert "Mozilla/5.0" in sent.html_body
    assert "203.0.113.5" in sent.text_body
