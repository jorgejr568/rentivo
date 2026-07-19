from unittest.mock import MagicMock

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


def test_registered_templates_render_complete_messages():
    class Backend:
        def send(self, message):
            assert message.html_body
            assert message.text_body
            return "message-id"

    service = EmailService(Backend(), from_address="noreply@example.com")
    for event in EMAIL_SUBJECTS:
        assert service.send("member@example.com", event, _TEMPLATE_CONTEXT) == "message-id"
    assert (
        service.send_communication(
            "member@example.com",
            "Assunto",
            _TEMPLATE_CONTEXT["body_html"],
            _TEMPLATE_CONTEXT["body_text"],
            sender_name=_TEMPLATE_CONTEXT["sender_name"],
        )
        == "message-id"
    )


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
