from __future__ import annotations

from pathlib import Path

import structlog
from ulid import ULID

from rentivo.email.base import EmailBackend, EmailMessage
from rentivo.email.mime import build_mime

logger = structlog.get_logger(__name__)


class LocalEmailBackend(EmailBackend):
    def __init__(self, outbox_path: str) -> None:
        self.outbox = Path(outbox_path)

    def send(self, message: EmailMessage) -> str:
        self.outbox.mkdir(parents=True, exist_ok=True)
        mime = build_mime(message)
        path = self.outbox / f"{ULID()}.eml"
        path.write_bytes(bytes(mime))
        logger.info("email_local_written", path=str(path), to=message.to, subject=message.subject)
        return str(path)
