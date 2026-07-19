import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from jinja2 import Environment, PackageLoader, select_autoescape

from rentivo.email.base import EmailMessage
from rentivo.services.email_service import EMAIL_SUBJECTS, EmailService

_TEMPLATE_CONTEXT = {
    "actor_email": "actor@example.com",
    "bill_count": 1,
    "billing_name": "Cobrança",
    "body_html": "<p>Mensagem</p>",
    "body_text": "Mensagem",
    "change_label": "ativado",
    "change_message": "O membro foi atualizado.",
    "changed_at": "2026-07-19 10:00",
    "email": "member@example.com",
    "format_label": "CSV",
    "inviter_email": "inviter@example.com",
    "invitee_email": "invitee@example.com",
    "invites_url": "https://example.com/invites",
    "logged_in_at": "2026-07-19 10:00",
    "org_name": "Organização",
    "pix_setup_url": "https://example.com/pix",
    "recipient_name": "Pessoa",
    "recipient_role": "previous_owner",
    "reset_url": "https://example.com/reset",
    "response_label": "aceitou",
    "role_label": "Administrador",
    "sender_name": "Responsável",
    "source_ip": "127.0.0.1",
    "user_agent": "Test Browser",
}


def test_moved_templates_render_byte_for_byte_as_legacy():
    legacy = Environment(
        loader=PackageLoader("legacy_web", "templates/emails"),
        autoescape=select_autoescape(["html"]),
    )
    shared = Environment(
        loader=PackageLoader("rentivo.email", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    for stem in (*EMAIL_SUBJECTS, "communication"):
        for suffix in ("html", "txt"):
            template = f"{stem}.{suffix}"
            assert shared.get_template(template).render(**_TEMPLATE_CONTEXT) == legacy.get_template(template).render(
                **_TEMPLATE_CONTEXT
            )


def test_registered_templates_render_without_legacy_web_imports():
    script = """
import importlib.abc
import sys


class BlockLegacyWeb(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "legacy_web" or fullname.startswith("legacy_web."):
            raise ImportError(f"blocked legacy import: {fullname}")
        return None


sys.meta_path.insert(0, BlockLegacyWeb())

from rentivo.services.email_service import EMAIL_SUBJECTS, EmailService


class Backend:
    def send(self, message):
        assert message.html_body
        assert message.text_body
        return "message-id"


context = {
    "actor_email": "actor@example.com",
    "bill_count": 1,
    "billing_name": "Cobrança",
    "body_html": "<p>Mensagem</p>",
    "body_text": "Mensagem",
    "change_label": "ativado",
    "change_message": "O membro foi atualizado.",
    "changed_at": "2026-07-19 10:00",
    "email": "member@example.com",
    "format_label": "CSV",
    "inviter_email": "inviter@example.com",
    "invitee_email": "invitee@example.com",
    "invites_url": "https://example.com/invites",
    "logged_in_at": "2026-07-19 10:00",
    "org_name": "Organização",
    "pix_setup_url": "https://example.com/pix",
    "recipient_name": "Pessoa",
    "recipient_role": "previous_owner",
    "reset_url": "https://example.com/reset",
    "response_label": "aceitou",
    "role_label": "Administrador",
    "sender_name": "Responsável",
    "source_ip": "127.0.0.1",
    "user_agent": "Test Browser",
}
service = EmailService(Backend(), from_address="noreply@example.com")
for event in EMAIL_SUBJECTS:
    assert service.send("member@example.com", event, context) == "message-id"
assert service.send_communication(
    "member@example.com", "Assunto", context["body_html"], context["body_text"], sender_name=context["sender_name"]
) == "message-id"
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_send_raises_on_backend_failure():
    from rentivo.services.email_service import EmailService

    class BlowingBackend:
        def send(self, message):
            raise RuntimeError("ses down")

    service = EmailService(BlowingBackend(), from_address="noreply@x")
    import pytest

    with pytest.raises(RuntimeError, match="ses down"):
        service.send("alice@example.com", "welcome", {"email": "alice@example.com", "pix_setup_url": "http://x/pix"})


def test_send_returns_message_id_on_success_and_renders_subject():
    backend = MagicMock()
    backend.send.return_value = "id-7"
    service = EmailService(backend, from_address="noreply@x")
    result = service.send(
        "alice@example.com", "welcome", {"email": "alice@example.com", "pix_setup_url": "http://x/pix"}
    )
    assert result == "id-7"
    sent: EmailMessage = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert "Bem-vindo" in sent.subject
