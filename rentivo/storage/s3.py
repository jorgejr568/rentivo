from __future__ import annotations

import structlog

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

from rentivo.storage.base import StorageBackend

logger = structlog.get_logger(__name__)


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
            raise ImportError("boto3 is required for S3 storage. Install it with: pip install rentivo[s3]")
        self.client = boto3.client(**client_kwargs)

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("storage_saved", backend="s3", bucket=self.bucket, key=key, bytes=len(data))
        return key

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        data = response["Body"].read()
        logger.debug("storage_read", backend="s3", bucket=self.bucket, key=key, bytes=len(data))
        return data

    def get_url(self, key: str) -> str:
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presigned_expiry,
        )
        logger.debug("storage_url", backend="s3", bucket=self.bucket, key=key)
        return url

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.debug("storage_deleted", backend="s3", bucket=self.bucket, key=key)
        except Exception:
            logger.exception("storage_delete_failed", backend="s3", bucket=self.bucket, key=key)
