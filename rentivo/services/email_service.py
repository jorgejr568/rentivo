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

    def _render(self, template_stem: str, ctx: dict) -> tuple[str, str]:
        html = self._env.get_template(f"{template_stem}.html").render(**ctx)
        text = self._env.get_template(f"{template_stem}.txt").render(**ctx)
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
        return self._send(
            to_email=to_email,
            subject="Redefinir senha — Rentivo",
            template_stem="password_reset",
            ctx={"email": to_email, "reset_url": reset_url},
        )

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
