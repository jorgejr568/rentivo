from unittest.mock import MagicMock

from rentivo.services.email_service import EmailService


def _service():
    backend = MagicMock()
    backend.send.return_value = "id"
    return EmailService(backend, from_address="noreply@rentivo.app"), backend


def test_send_invite_received_renders_inviter_org_role_and_link():
    service, backend = _service()
    service.safe_send(
        to_email="alice@example.com",
        event="invite_received",
        ctx={
            "inviter_email": "bob@example.com",
            "org_name": "Acme",
            "role_label": "Administrador",
            "invites_url": "http://x/invites/",
        },
    )
    sent = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert sent.subject == 'Convite para "Acme" — Rentivo'
    assert "Acme" in sent.html_body
    assert "bob@example.com" in sent.html_body
    assert "Administrador" in sent.html_body
    assert "x/invites/" in sent.text_body


def test_send_invite_responded_renders_invitee_and_response():
    service, backend = _service()
    service.safe_send(
        to_email="bob@example.com",
        event="invite_responded",
        ctx={
            "invitee_email": "alice@example.com",
            "org_name": "Acme",
            "response_label": "aceitou",
        },
    )
    sent = backend.send.call_args[0][0]
    assert "alice@example.com" in sent.html_body
    assert "aceitou" in sent.html_body
    assert "Acme" in sent.text_body


def test_send_member_changed_renders_message_org_and_actor():
    service, backend = _service()
    service.safe_send(
        to_email="alice@example.com",
        event="member_changed",
        ctx={
            "change_message": "Sua função mudou de Visualizador para Administrador.",
            "org_name": "Acme",
            "actor_email": "bob@example.com",
        },
    )
    sent = backend.send.call_args[0][0]
    assert sent.subject == 'Alteração em "Acme" — Rentivo'
    assert "Sua função mudou" in sent.html_body
    assert "Acme" in sent.text_body
    assert "bob@example.com" in sent.html_body


def test_send_billing_transferred_renders_name_message_and_actor():
    service, backend = _service()
    service.safe_send(
        to_email="alice@example.com",
        event="billing_transferred",
        ctx={
            "billing_name": "Apto 301",
            "recipient_role": "destination_admin",
            "actor_email": "bob@example.com",
        },
    )
    sent = backend.send.call_args[0][0]
    assert "Apto 301" in sent.html_body
    assert "transferida para sua organização" in sent.html_body
    assert "bob@example.com" in sent.text_body
