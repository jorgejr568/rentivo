from __future__ import annotations

import logging

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

from landlord.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class S3Storage(StorageBackend):
    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str = "",
        presigned_expiry: int = 604800,
    ) -> None:
        self.bucket = bucket
        self.presigned_expiry = presigned_expiry

        client_kwargs: dict = {
            "service_name": "s3",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        if boto3 is None:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install it with: pip install landlord-cli[s3]"
            )
        self.client = boto3.client(**client_kwargs)

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="application/pdf",
        )
        logger.info("Uploaded %s to s3://%s/%s (%d bytes)", key, self.bucket, key, len(data))
        return key

    def get_url(self, key: str) -> str:
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presigned_expiry,
        )
        logger.debug("Generated presigned URL for %s", key)
        return url
