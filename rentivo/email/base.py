from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str
    from_address: str
    attachments: tuple[EmailAttachment, ...] = field(default_factory=tuple)
    reply_to: tuple[str, ...] = field(default_factory=tuple)


class EmailBackend(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> str:
        """Dispatch the message and return a backend-specific identifier (message id or path)."""
        ...
