from __future__ import annotations

from typing import Callable

import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

from rentivo.email.base import EmailAttachment, EmailBackend, EmailMessage
from rentivo.observability import traced

logger = structlog.get_logger(__name__)

_env: Environment | None = None


def _jinja_env() -> Environment:
    """Lazy-initialized module-level Jinja Environment singleton.

    The Environment is expensive to build but cheap to share, and EmailService
    is constructed per job by the worker. Hoisting the Environment out of
    __init__ keeps the dispatch hot path tight.
    """
    global _env
    if _env is None:
        _env = Environment(
            loader=PackageLoader("rentivo.email", "templates"),
            autoescape=select_autoescape(["html"]),
        )
    return _env


# Single source of truth for transactional email subjects.
# Each key is the template stem (we render `{event}.html` / `{event}.txt`).
# Values are either a literal subject string or a callable that receives the
# render ctx and returns the subject — used by events whose subject embeds
# ctx data (e.g. organization name).
EMAIL_SUBJECTS: dict[str, str | Callable[[dict], str]] = {
    "welcome": "Bem-vindo à Rentivo",
    "password_changed": "Senha alterada — Rentivo",
    "account_deleted": "Conta excluída — Rentivo",
    "password_reset_completed": "Senha redefinida — Rentivo",
    "password_reset": "Redefinir senha — Rentivo",
    "mfa_changed": "Alteração de MFA — Rentivo",
    "new_device_login": "Novo acesso detectado — Rentivo",
    "invite_received": lambda ctx: f'Convite para "{ctx["org_name"]}" — Rentivo',
    "invite_responded": "Resposta ao convite — Rentivo",
    "member_changed": lambda ctx: f'Alteração em "{ctx["org_name"]}" — Rentivo',
    "billing_transferred": "Transferência de cobrança — Rentivo",
    "export_ready": lambda ctx: f"Exportação de faturas — {ctx['billing_name']} — Rentivo",
}


class EmailService:
    def __init__(self, backend: EmailBackend, from_address: str) -> None:
        self.backend = backend
        self.from_address = from_address

    def _render(self, template_stem: str, ctx: dict) -> tuple[str, str]:
        env = _jinja_env()
        html = env.get_template(f"{template_stem}.html").render(**ctx)
        text = env.get_template(f"{template_stem}.txt").render(**ctx)
        return html, text

    def _build_message(
        self,
        to_email: str,
        subject: str,
        template_stem: str,
        ctx: dict,
        attachments: list[EmailAttachment] | tuple[EmailAttachment, ...] = (),
    ) -> EmailMessage:
        html_body, text_body = self._render(template_stem, ctx)
        return EmailMessage(
            to=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_address=self.from_address,
            attachments=tuple(attachments),
        )

    @traced("email.send")
    def send(
        self,
        to_email: str,
        event: str,
        ctx: dict,
        attachments: list[EmailAttachment] | tuple[EmailAttachment, ...] = (),
    ) -> str:
        """Render and dispatch a transactional email, raising on failure.

        Used inside the background worker so transient errors propagate and
        trigger retry. Web routes should not call this directly — they enqueue
        a job and let the worker run it. ``attachments`` lets events like
        ``export_ready`` carry a generated file (CSV/XLSX).
        """
        subject_spec = EMAIL_SUBJECTS[event]
        subject = subject_spec(ctx) if callable(subject_spec) else subject_spec
        message = self._build_message(to_email, subject, event, ctx, attachments)
        result = self.backend.send(message)
        logger.info("email_sent", to=to_email, email_event=event)
        return result

    @traced("email.send_communication")
    def send_communication(
        self,
        to_email: str,
        subject: str,
        body_html_inner: str,
        body_text: str,
        attachments: list[EmailAttachment] | tuple[EmailAttachment, ...] = (),
        reply_to: list[str] | tuple[str, ...] = (),
        sender_name: str = "",
        headers: tuple[tuple[str, str], ...] = (),
    ) -> str:
        """Send a dynamic (non-registry) communication: a Markdown-rendered body
        wrapped in the shared email layout, with optional attachments and Reply-To,
        plus a system-controlled sender-attribution block.

        ``headers`` carries extra per-message MIME headers (e.g. a unique
        ``X-Entity-Ref-ID``) so Gmail does not thread distinct communications.
        """
        html_body, text_body = self._render(
            "communication",
            {"body_html": body_html_inner, "body_text": body_text, "sender_name": sender_name},
        )
        message = EmailMessage(
            to=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_address=self.from_address,
            attachments=tuple(attachments),
            reply_to=tuple(reply_to),
            headers=tuple(headers),
        )
        result = self.backend.send(message)
        logger.info("email_communication_sent", to=to_email)
        return result
