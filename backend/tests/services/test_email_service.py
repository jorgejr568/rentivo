from unittest.mock import MagicMock

from rentivo.email.base import EmailMessage
from rentivo.services.email_service import EmailService


def test_send_raises_on_backend_failure():
    from rentivo.services.email_service import EmailService

    class BlowingBackend:
        def send(self, message):
            raise RuntimeError("ses down")

    service = EmailService(BlowingBackend(), from_address="noreply@x")
    import pytest

    with pytest.raises(RuntimeError, match="ses down"):
        service.send("alice@example.com", "welcome", {"email": "alice@example.com", "pix_setup_url": "http://x/pix"})


def test_send_returns_message_id_on_success_and_renders_subject():
    backend = MagicMock()
    backend.send.return_value = "id-7"
    service = EmailService(backend, from_address="noreply@x")
    result = service.send(
        "alice@example.com", "welcome", {"email": "alice@example.com", "pix_setup_url": "http://x/pix"}
    )
    assert result == "id-7"
    sent: EmailMessage = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert "Bem-vindo" in sent.subject
