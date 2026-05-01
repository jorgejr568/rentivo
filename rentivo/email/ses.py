from __future__ import annotations

import structlog

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

from rentivo.email.base import EmailBackend, EmailMessage

logger = structlog.get_logger(__name__)


class SESEmailBackend(EmailBackend):
    def __init__(
        self,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        from_address: str,
        endpoint_url: str = "",
        configuration_set: str = "",
    ) -> None:
        if boto3 is None:
            raise ImportError("boto3 is required for SES email. Install it with: pip install rentivo[s3]")
        self.from_address = from_address
        self.configuration_set = configuration_set

        client_kwargs: dict = {
            "service_name": "ses",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self.client = boto3.client(**client_kwargs)

    def send(self, message: EmailMessage) -> str:
        kwargs = {
            "Source": message.from_address or self.from_address,
            "Destination": {"ToAddresses": [message.to]},
            "Message": {
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                    "Html": {"Data": message.html_body, "Charset": "UTF-8"},
                },
            },
        }
        if self.configuration_set:
            kwargs["ConfigurationSetName"] = self.configuration_set
        response = self.client.send_email(**kwargs)
        message_id = response.get("MessageId", "")
        logger.info("email_ses_sent", to=message.to, subject=message.subject, message_id=message_id)
        return message_id
