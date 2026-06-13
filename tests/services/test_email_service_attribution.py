from __future__ import annotations

from rentivo.email.base import EmailBackend
from rentivo.services.email_service import EmailService


class _CapturingBackend(EmailBackend):
    def __init__(self):
        self.sent = None

    def send(self, message):
        self.sent = message
        return "id-1"


def _send(sender_name):
    backend = _CapturingBackend()
    service = EmailService(backend, from_address="noreply@localhost")
    service.send_communication(
        "rodrigo@example.com", "Assunto", "<p>Prezado Rodrigo</p>", "Prezado Rodrigo", sender_name=sender_name
    )
    return backend.sent


def test_attribution_block_names_sender_in_html_and_text():
    msg = _send("Imobiliária Aurora")
    for part in (msg.html_body, msg.text_body):
        assert "Imobiliária Aurora" in part
        assert "através do Rentivo" in part
        assert "responsabilidade do remetente" in part


def test_attribution_falls_back_when_sender_name_empty():
    msg = _send("")
    assert "o responsável" in msg.html_body
    assert "o responsável" in msg.text_body


def test_attribution_default_param_is_empty_fallback():
    backend = _CapturingBackend()
    EmailService(backend, from_address="n@x.com").send_communication("a@x.com", "s", "<p>b</p>", "b")
    assert "o responsável" in backend.sent.html_body
