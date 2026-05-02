from __future__ import annotations

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


class EmailService:
    def __init__(self, backend: EmailBackend, from_address: str) -> None:
        self.backend = backend
        self.from_address = from_address

    def _render(self, template_stem: str, ctx: dict) -> tuple[str, str]:
        env = _jinja_env()
        html = env.get_template(f"{template_stem}.html").render(**ctx)
        text = env.get_template(f"{template_stem}.txt").render(**ctx)
        return html, text

    def _send(self, to_email: str, subject: str, template_stem: str, ctx: dict) -> str:
        html_body, text_body = self._render(template_stem, ctx)
        message = EmailMessage(
            to=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_address=self.from_address,
        )
        return self.backend.send(message)

    def safe_send(self, to_email: str, subject: str, template_stem: str, ctx: dict) -> str | None:
        """Dispatch and swallow exceptions so an email failure never blocks the caller."""
        try:
            result = self._send(to_email, subject, template_stem, ctx)
            logger.info("email_sent", to=to_email, template=template_stem)
            return result
        except Exception as exc:
            logger.warning("email_send_failed", to=to_email, template=template_stem, error=str(exc))
            return None

    def send_password_recovery(self, to_email: str, reset_url: str) -> str:
        result = self._send(
            to_email=to_email,
            subject="Redefinir senha — Rentivo",
            template_stem="password_reset",
            ctx={"email": to_email, "reset_url": reset_url},
        )
        logger.info("password_recovery_email_sent", to=to_email)
        return result

    def safe_send_welcome(self, to_email: str, pix_setup_url: str) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Bem-vindo à Rentivo",
            template_stem="welcome",
            ctx={"email": to_email, "pix_setup_url": pix_setup_url},
        )

    def safe_send_password_changed(
        self,
        to_email: str,
        changed_at: str,
        source_ip: str,
        reset_url: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Senha alterada — Rentivo",
            template_stem="password_changed",
            ctx={
                "email": to_email,
                "changed_at": changed_at,
                "source_ip": source_ip,
                "reset_url": reset_url,
            },
        )

    def safe_send_password_reset_completed(
        self,
        to_email: str,
        changed_at: str,
        source_ip: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Senha redefinida — Rentivo",
            template_stem="password_reset_completed",
            ctx={
                "email": to_email,
                "changed_at": changed_at,
                "source_ip": source_ip,
            },
        )

    def safe_send_mfa_changed(
        self,
        to_email: str,
        change_label: str,
        changed_at: str,
        source_ip: str,
        reset_url: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Alteração de MFA — Rentivo",
            template_stem="mfa_changed",
            ctx={
                "email": to_email,
                "change_label": change_label,
                "changed_at": changed_at,
                "source_ip": source_ip,
                "reset_url": reset_url,
            },
        )

    def safe_send_new_device_login(
        self,
        to_email: str,
        logged_in_at: str,
        source_ip: str,
        user_agent: str,
        reset_url: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Novo acesso detectado — Rentivo",
            template_stem="new_device_login",
            ctx={
                "email": to_email,
                "logged_in_at": logged_in_at,
                "source_ip": source_ip,
                "user_agent": user_agent,
                "reset_url": reset_url,
            },
        )

    def safe_send_invite_received(
        self,
        to_email: str,
        inviter_email: str,
        org_name: str,
        role_label: str,
        invites_url: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject=f'Convite para "{org_name}" — Rentivo',
            template_stem="invite_received",
            ctx={
                "inviter_email": inviter_email,
                "org_name": org_name,
                "role_label": role_label,
                "invites_url": invites_url,
            },
        )

    def safe_send_invite_responded(
        self,
        to_email: str,
        invitee_email: str,
        org_name: str,
        response_label: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Resposta ao convite — Rentivo",
            template_stem="invite_responded",
            ctx={
                "invitee_email": invitee_email,
                "org_name": org_name,
                "response_label": response_label,
            },
        )

    def safe_send_member_changed(
        self,
        to_email: str,
        change_message: str,
        org_name: str,
        actor_email: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject=f'Alteração em "{org_name}" — Rentivo',
            template_stem="member_changed",
            ctx={
                "change_message": change_message,
                "org_name": org_name,
                "actor_email": actor_email,
            },
        )

    def safe_send_billing_transferred(
        self,
        to_email: str,
        billing_name: str,
        recipient_role: str,
        actor_email: str,
    ) -> str | None:
        return self.safe_send(
            to_email=to_email,
            subject="Transferência de cobrança — Rentivo",
            template_stem="billing_transferred",
            ctx={
                "billing_name": billing_name,
                "recipient_role": recipient_role,
                "actor_email": actor_email,
            },
        )
