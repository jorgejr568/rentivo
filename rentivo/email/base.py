from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str
    from_address: str


class EmailBackend(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> str:
        """Dispatch the message and return a backend-specific identifier (message id or path)."""
        ...
