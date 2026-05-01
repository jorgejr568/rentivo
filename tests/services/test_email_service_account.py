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
