from unittest.mock import MagicMock, patch

from rentivo.email.base import EmailMessage
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


@patch("rentivo.email.ses.boto3", None)
def test_missing_boto3_raises():
    import pytest

    with pytest.raises(ImportError):
        SESEmailBackend(region="r", access_key_id="k", secret_access_key="s", from_address="f@x.com")


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
