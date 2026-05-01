from unittest.mock import MagicMock

from rentivo.services.email_service import EmailService


def _service():
    backend = MagicMock()
    backend.send.return_value = "id"
    return EmailService(backend, from_address="noreply@rentivo.app"), backend


def test_send_invite_received_renders_inviter_org_role_and_link():
    service, backend = _service()
    service.safe_send_invite_received(
        to_email="alice@example.com",
        inviter_email="bob@example.com",
        org_name="Acme",
        role_label="Administrador",
        invites_url="http://x/invites/",
    )
    sent = backend.send.call_args[0][0]
    assert sent.to == "alice@example.com"
    assert "Acme" in sent.html_body
    assert "bob@example.com" in sent.html_body
    assert "Administrador" in sent.html_body
    assert "x/invites/" in sent.text_body
    assert "Convite" in sent.subject


def test_send_invite_responded_renders_invitee_and_response():
    service, backend = _service()
    service.safe_send_invite_responded(
        to_email="bob@example.com",
        invitee_email="alice@example.com",
        org_name="Acme",
        response_label="aceitou",
    )
    sent = backend.send.call_args[0][0]
    assert "alice@example.com" in sent.html_body
    assert "aceitou" in sent.html_body
    assert "Acme" in sent.text_body


def test_send_member_changed_renders_message_org_and_actor():
    service, backend = _service()
    service.safe_send_member_changed(
        to_email="alice@example.com",
        change_message="Sua função mudou de Visualizador para Administrador.",
        org_name="Acme",
        actor_email="bob@example.com",
    )
    sent = backend.send.call_args[0][0]
    assert "Sua função mudou" in sent.html_body
    assert "Acme" in sent.text_body
    assert "bob@example.com" in sent.html_body
