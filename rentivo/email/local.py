from __future__ import annotations

from email.message import EmailMessage as MIMEMessage
from pathlib import Path

import structlog
from ulid import ULID

from rentivo.email.base import EmailBackend, EmailMessage

logger = structlog.get_logger(__name__)


class LocalEmailBackend(EmailBackend):
    def __init__(self, outbox_path: str) -> None:
        self.outbox = Path(outbox_path)

    def send(self, message: EmailMessage) -> str:
        self.outbox.mkdir(parents=True, exist_ok=True)
        mime = MIMEMessage()
        mime["From"] = message.from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")

        path = self.outbox / f"{ULID()}.eml"
        path.write_bytes(bytes(mime))
        logger.info("email_local_written", path=str(path), to=message.to, subject=message.subject)
        return str(path)
