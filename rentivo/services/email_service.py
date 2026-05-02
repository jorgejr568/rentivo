from __future__ import annotations

from typing import Callable

import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

from rentivo.email.base import EmailBackend, EmailMessage

logger = structlog.get_logger(__name__)

_env: Environment | None = None


def _jinja_env() -> Environment:
    """Lazy-initialized module-level Jinja Environment singleton.

    The Environment is expensive to build but cheap to share, and EmailService
    is constructed per request via web.deps.get_email_service. Hoisting the
    Environment out of __init__ keeps the per-request hot path tight.
    """
    global _env
    if _env is None:
        _env = Environment(
            loader=PackageLoader("web", "templates/emails"),
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
    "password_reset_completed": "Senha redefinida — Rentivo",
    "password_reset": "Redefinir senha — Rentivo",
    "mfa_changed": "Alteração de MFA — Rentivo",
    "new_device_login": "Novo acesso detectado — Rentivo",
    "invite_received": lambda ctx: f'Convite para "{ctx["org_name"]}" — Rentivo',
    "invite_responded": "Resposta ao convite — Rentivo",
    "member_changed": lambda ctx: f'Alteração em "{ctx["org_name"]}" — Rentivo',
    "billing_transferred": "Transferência de cobrança — Rentivo",
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

    def _build_message(self, to_email: str, subject: str, template_stem: str, ctx: dict) -> EmailMessage:
        html_body, text_body = self._render(template_stem, ctx)
        return EmailMessage(
            to=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_address=self.from_address,
        )

    def safe_send(self, to_email: str, event: str, ctx: dict) -> str | None:
        """Render and dispatch a transactional email, swallowing exceptions.

        ``event`` is a key into ``EMAIL_SUBJECTS`` and also the template stem
        (we render ``{event}.html`` / ``{event}.txt``). Failures never block
        the caller — a warning is logged and ``None`` is returned.
        """
        subject_spec = EMAIL_SUBJECTS[event]
        subject = subject_spec(ctx) if callable(subject_spec) else subject_spec
        try:
            message = self._build_message(to_email, subject, event, ctx)
            result = self.backend.send(message)
            logger.info("email_sent", to=to_email, email_event=event)
            return result
        except Exception as exc:
            logger.warning("email_send_failed", to=to_email, email_event=event, error=str(exc))
            return None

    def send_password_recovery(self, to_email: str, reset_url: str) -> str:
        """Raise-on-error variant used by the password-reset flow.

        Distinct from ``safe_send`` because the caller wants the exception to
        propagate so the request can surface a failure to the user.
        """
        subject_spec = EMAIL_SUBJECTS["password_reset"]
        assert isinstance(subject_spec, str)
        message = self._build_message(
            to_email=to_email,
            subject=subject_spec,
            template_stem="password_reset",
            ctx={"email": to_email, "reset_url": reset_url},
        )
        result = self.backend.send(message)
        logger.info("password_recovery_email_sent", to=to_email)
        return result
