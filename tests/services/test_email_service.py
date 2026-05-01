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


def test_safe_send_swallows_backend_exceptions():
    from rentivo.services.email_service import EmailService

    class BlowingBackend:
        def send(self, message):
            raise RuntimeError("network down")

    service = EmailService(BlowingBackend(), from_address="noreply@x")
    result = service.safe_send(
        to_email="alice@example.com",
        subject="t",
        template_stem="password_reset",
        ctx={"email": "alice@example.com", "reset_url": "http://x/y"},
    )
    assert result is None  # exception swallowed


def test_safe_send_returns_message_id_on_success():
    from unittest.mock import MagicMock

    from rentivo.services.email_service import EmailService

    backend = MagicMock()
    backend.send.return_value = "id-1"
    service = EmailService(backend, from_address="noreply@x")
    result = service.safe_send(
        to_email="alice@example.com",
        subject="t",
        template_stem="password_reset",
        ctx={"email": "alice@example.com", "reset_url": "http://x/y"},
    )
    assert result == "id-1"
