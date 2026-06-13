from __future__ import annotations

from email import message_from_bytes

from rentivo.email.base import EmailAttachment, EmailMessage
from rentivo.email.local import LocalEmailBackend
from rentivo.email.mime import build_mime


def _msg(**over):
    base = dict(
        to="joao@example.com",
        subject="Cobrança",
        text_body="corpo",
        html_body="<p>corpo</p>",
        from_address="noreply@localhost",
        attachments=(EmailAttachment(filename="fatura.pdf", content=b"%PDF-1.4 fake", content_type="application/pdf"),),
    )
    base.update(over)
    return EmailMessage(**base)


def test_build_mime_includes_pdf_attachment():
    mime = build_mime(_msg())
    parts = list(mime.walk())
    pdf_parts = [p for p in parts if p.get_filename() == "fatura.pdf"]
    assert len(pdf_parts) == 1
    assert pdf_parts[0].get_content_type() == "application/pdf"
    assert pdf_parts[0].get_payload(decode=True) == b"%PDF-1.4 fake"


def test_local_backend_writes_eml_with_attachment(tmp_path):
    backend = LocalEmailBackend(str(tmp_path))
    path = backend.send(_msg())
    raw = open(path, "rb").read()
    parsed = message_from_bytes(raw)
    assert any(p.get_filename() == "fatura.pdf" for p in parsed.walk())


def test_email_message_defaults_to_no_attachments():
    msg = EmailMessage(to="a@x.com", subject="s", text_body="t", html_body="<p>t</p>", from_address="n@x.com")
    assert msg.attachments == ()
