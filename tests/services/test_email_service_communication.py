from __future__ import annotations

from rentivo.email.base import EmailAttachment, EmailBackend
from rentivo.services.email_service import EmailService


class _CapturingBackend(EmailBackend):
    def __init__(self):
        self.sent = None

    def send(self, message):
        self.sent = message
        return "id-123"


def test_send_communication_wraps_body_and_attaches():
    backend = _CapturingBackend()
    service = EmailService(backend, from_address="noreply@localhost")
    att = EmailAttachment(filename="fatura.pdf", content=b"%PDF", content_type="application/pdf")
    result = service.send_communication(
        "rodrigo@example.com",
        "Cobrança Joy 105",
        "<p>Prezado Rodrigo</p>",
        "Prezado Rodrigo",
        [att],
    )
    assert result == "id-123"
    assert backend.sent.to == "rodrigo@example.com"
    assert backend.sent.subject == "Cobrança Joy 105"
    assert "Prezado Rodrigo" in backend.sent.html_body  # rendered into the layout
    assert backend.sent.attachments == (att,)
