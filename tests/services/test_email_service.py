from unittest.mock import MagicMock

from rentivo.email.base import EmailMessage
from rentivo.services.email_service import EmailService


def test_send_password_recovery_renders_and_dispatches():
    backend = MagicMock()
    backend.send.return_value = "id-1"
    service = EmailService(backend, from_address="noreply@rentivo.app")
    result = service.send_password_recovery(
        to_email="alice@example.com",
        reset_url="http://example.com/reset?token=abc",
    )
    assert result == "id-1"
    sent: EmailMessage = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert sent.from_address == "noreply@rentivo.app"
    assert "Redefinir" in sent.subject
    assert "abc" in sent.text_body
    assert "abc" in sent.html_body
