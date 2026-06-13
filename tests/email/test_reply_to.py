from __future__ import annotations

from email import message_from_bytes

from rentivo.email.base import EmailAttachment, EmailBackend, EmailMessage
from rentivo.email.local import LocalEmailBackend
from rentivo.email.mime import build_mime
from rentivo.services.email_service import EmailService


def _msg(reply_to=()):
    return EmailMessage(
        to="rodrigo@example.com",
        subject="Cobrança",
        text_body="corpo",
        html_body="<p>corpo</p>",
        from_address="cobranca@example.com",
        attachments=(EmailAttachment(filename="f.pdf", content=b"%PDF", content_type="application/pdf"),),
        reply_to=reply_to,
    )


def test_email_message_reply_to_defaults_empty():
    m = EmailMessage(to="a@x.com", subject="s", text_body="t", html_body="<p>t</p>", from_address="n@x.com")
    assert m.reply_to == ()


def test_build_mime_sets_reply_to_header():
    mime = build_mime(_msg(reply_to=("Ana <ana@x.com>", "bruno@x.com")))
    assert mime["Reply-To"] == "Ana <ana@x.com>, bruno@x.com"


def test_build_mime_omits_reply_to_when_empty():
    mime = build_mime(_msg())
    assert mime["Reply-To"] is None


def test_local_backend_eml_carries_reply_to(tmp_path):
    path = LocalEmailBackend(str(tmp_path)).send(_msg(reply_to=("ana@x.com",)))
    parsed = message_from_bytes(open(path, "rb").read())
    assert parsed["Reply-To"] == "ana@x.com"


class _CapturingBackend(EmailBackend):
    def __init__(self):
        self.sent = None

    def send(self, message):
        self.sent = message
        return "id-1"


def test_send_communication_passes_reply_to():
    backend = _CapturingBackend()
    service = EmailService(backend, from_address="cobranca@example.com")
    service.send_communication(
        "rodrigo@example.com", "Assunto", "<p>oi</p>", "oi", [], reply_to=["ana@x.com", "bruno@x.com"]
    )
    assert backend.sent.reply_to == ("ana@x.com", "bruno@x.com")
    assert backend.sent.from_address == "cobranca@example.com"
