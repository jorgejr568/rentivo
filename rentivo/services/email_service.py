from __future__ import annotations

import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

from rentivo.email.base import EmailBackend, EmailMessage

logger = structlog.get_logger(__name__)


class EmailService:
    def __init__(self, backend: EmailBackend, from_address: str) -> None:
        self.backend = backend
        self.from_address = from_address
        self._env = Environment(
            loader=PackageLoader("web", "templates/emails"),
            autoescape=select_autoescape(["html"]),
        )

    def send_password_recovery(self, to_email: str, reset_url: str) -> str:
        ctx = {"email": to_email, "reset_url": reset_url}
        html_body = self._env.get_template("password_reset.html").render(**ctx)
        text_body = self._env.get_template("password_reset.txt").render(**ctx)
        message = EmailMessage(
            to=to_email,
            subject="Redefinir senha — Rentivo",
            text_body=text_body,
            html_body=html_body,
            from_address=self.from_address,
        )
        result = self.backend.send(message)
        logger.info("password_recovery_email_sent", to=to_email)
        return result
