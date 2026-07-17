from __future__ import annotations

from email.message import EmailMessage as MIMEMessage
from email.utils import make_msgid

from rentivo.email.base import EmailMessage


def build_mime(message: EmailMessage) -> MIMEMessage:
    """Build a stdlib MIME message (text + html alternative + attachments).

    Each message gets a unique Message-ID, and any extra ``message.headers`` are
    applied — e.g. a per-communication ``X-Entity-Ref-ID`` so Gmail does not
    thread distinct communications into a single conversation.

    ``message.headers`` is for custom (``X-``) headers only: the standard headers
    (From/To/Subject/Message-ID/Reply-To) are set above, and re-passing one here
    would append a duplicate rather than replace it.
    """
    mime = MIMEMessage()
    mime["From"] = message.from_address
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Message-ID"] = make_msgid()
    if message.reply_to:
        mime["Reply-To"] = ", ".join(message.reply_to)
    for key, value in message.headers:
        mime[key] = value
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
