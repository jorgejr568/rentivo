from dataclasses import asdict

from rentivo.email.base import EmailBackend, EmailMessage


def test_email_message_holds_fields():
    msg = EmailMessage(
        to="alice@example.com",
        subject="Recuperação de senha",
        text_body="link plain",
        html_body="<a href=''>link</a>",
        from_address="noreply@rentivo.com.br",
    )
    payload = asdict(msg)
    assert payload["to"] == "alice@example.com"
    assert payload["html_body"].startswith("<a")


def test_email_backend_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        EmailBackend()  # type: ignore[abstract]
