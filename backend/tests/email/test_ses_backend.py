from email import message_from_bytes
from unittest.mock import MagicMock, patch

from rentivo.email.base import EmailAttachment, EmailMessage
from rentivo.email.ses import SESEmailBackend


@patch("rentivo.email.ses.boto3")
def test_send_calls_ses_with_expected_payload(boto3_mock):
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "amazon-msg-id"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="AKIA",
        secret_access_key="secret",
        from_address="noreply@rentivo.app",
        configuration_set="rentivo-prod",
    )
    msg = EmailMessage(
        to="alice@example.com",
        subject="Test",
        text_body="hello",
        html_body="<p>hello</p>",
        from_address="noreply@rentivo.app",
    )
    result = backend.send(msg)
    assert result == "amazon-msg-id"

    boto3_mock.client.assert_called_once_with(
        service_name="ses",
        region_name="us-east-1",
        aws_access_key_id="AKIA",
        aws_secret_access_key="secret",
    )
    sent_kwargs = client.send_email.call_args.kwargs
    assert sent_kwargs["Source"] == "noreply@rentivo.app"
    assert sent_kwargs["Destination"] == {"ToAddresses": ["alice@example.com"]}
    assert sent_kwargs["Message"]["Subject"]["Data"] == "Test"
    assert sent_kwargs["Message"]["Body"]["Text"]["Data"] == "hello"
    assert sent_kwargs["Message"]["Body"]["Html"]["Data"] == "<p>hello</p>"
    assert sent_kwargs["ConfigurationSetName"] == "rentivo-prod"


@patch("rentivo.email.ses.boto3")
def test_send_omits_configuration_set_when_empty(boto3_mock):
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "x"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="k",
        secret_access_key="s",
        from_address="from@x.com",
    )
    backend.send(EmailMessage(to="to@x.com", subject="s", text_body="t", html_body="<t/>", from_address="from@x.com"))
    assert "ConfigurationSetName" not in client.send_email.call_args.kwargs


@patch("rentivo.email.ses.boto3")
def test_send_email_includes_reply_to_addresses(boto3_mock):
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "reply-to-id"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="k",
        secret_access_key="s",
        from_address="from@x.com",
    )
    msg = EmailMessage(
        to="to@x.com",
        subject="s",
        text_body="t",
        html_body="<p>t</p>",
        from_address="from@x.com",
        reply_to=("ana@x.com", "bruno@x.com"),
    )
    result = backend.send(msg)
    assert result == "reply-to-id"
    assert client.send_email.call_args.kwargs["ReplyToAddresses"] == ["ana@x.com", "bruno@x.com"]


@patch("rentivo.email.ses.boto3", None)
def test_missing_boto3_raises():
    import pytest

    with pytest.raises(ImportError):
        SESEmailBackend(region="r", access_key_id="k", secret_access_key="s", from_address="f@x.com")


@patch("rentivo.email.ses.boto3")
def test_send_with_attachment_uses_send_raw_email(boto3_mock):
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "raw-msg-id"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="k",
        secret_access_key="s",
        from_address="from@x.com",
    )
    msg = EmailMessage(
        to="to@x.com",
        subject="Cobrança",
        text_body="t",
        html_body="<p>t</p>",
        from_address="from@x.com",
        attachments=(EmailAttachment(filename="fatura.pdf", content=b"%PDF", content_type="application/pdf"),),
    )
    result = backend.send(msg)
    assert result == "raw-msg-id"
    client.send_email.assert_not_called()
    raw_kwargs = client.send_raw_email.call_args.kwargs
    assert raw_kwargs["Source"] == "from@x.com"
    assert raw_kwargs["Destinations"] == ["to@x.com"]
    assert "ConfigurationSetName" not in raw_kwargs
    parsed = message_from_bytes(raw_kwargs["RawMessage"]["Data"])
    assert any(p.get_filename() == "fatura.pdf" for p in parsed.walk())


@patch("rentivo.email.ses.boto3")
def test_send_with_attachment_includes_configuration_set(boto3_mock):
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "raw-cfg-id"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="k",
        secret_access_key="s",
        from_address="from@x.com",
        configuration_set="rentivo-prod",
    )
    msg = EmailMessage(
        to="to@x.com",
        subject="Cobrança",
        text_body="t",
        html_body="<p>t</p>",
        from_address="from@x.com",
        attachments=(EmailAttachment(filename="fatura.pdf", content=b"%PDF", content_type="application/pdf"),),
    )
    result = backend.send(msg)
    assert result == "raw-cfg-id"
    raw_kwargs = client.send_raw_email.call_args.kwargs
    assert raw_kwargs["ConfigurationSetName"] == "rentivo-prod"


@patch("rentivo.email.ses.boto3")
def test_send_raw_email_carries_reply_to_header(boto3_mock):
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "raw-reply-to-id"}
    boto3_mock.client.return_value = client

    backend = SESEmailBackend(
        region="us-east-1",
        access_key_id="k",
        secret_access_key="s",
        from_address="from@x.com",
    )
    msg = EmailMessage(
        to="t@x.com",
        subject="s",
        text_body="t",
        html_body="<p>t</p>",
        from_address="from@x.com",
        attachments=(EmailAttachment(filename="f.pdf", content=b"%PDF", content_type="application/pdf"),),
        reply_to=("Ana <ana@x.com>", "bruno@x.com"),
    )
    backend.send(msg)
    raw = client.send_raw_email.call_args.kwargs["RawMessage"]["Data"]
    parsed = message_from_bytes(raw)
    assert parsed["Reply-To"] == "Ana <ana@x.com>, bruno@x.com"


@patch("rentivo.email.ses.boto3")
def test_send_passes_endpoint_url_when_provided(boto3_mock):
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "id"}
    boto3_mock.client.return_value = client
    SESEmailBackend(
        region="r",
        access_key_id="k",
        secret_access_key="s",
        from_address="f@x.com",
        endpoint_url="http://localstack:4566",
    )
    assert boto3_mock.client.call_args.kwargs["endpoint_url"] == "http://localstack:4566"
