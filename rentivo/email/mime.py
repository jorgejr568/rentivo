from __future__ import annotations

from email.message import EmailMessage as MIMEMessage

from rentivo.email.base import EmailMessage


def build_mime(message: EmailMessage) -> MIMEMessage:
    """Build a stdlib MIME message (text + html alternative + attachments)."""
    mime = MIMEMessage()
    mime["From"] = message.from_address
    mime["To"] = message.to
    mime["Subject"] = message.subject
    if message.reply_to:
        mime["Reply-To"] = ", ".join(message.reply_to)
    mime.set_content(message.text_body)
    mime.add_alternative(message.html_body, subtype="html")
    for att in message.attachments:
        maintype, _, subtype = att.content_type.partition("/")
        mime.add_attachment(
            att.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.filename,
        )
    return mime
