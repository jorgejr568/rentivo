import logging

from rentivo.settings import settings
from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def get_storage() -> StorageBackend:
    backend = settings.storage_backend

    if backend == "local":
        from rentivo.storage.local import LocalStorage

        logger.info("Using storage backend: local")
        return LocalStorage(settings.storage_local_path)

    if backend == "s3":
        from rentivo.storage.s3 import S3Storage

        logger.info("Using storage backend: s3 bucket=%s", settings.s3_bucket)
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            endpoint_url=settings.s3_endpoint_url,
            presigned_expiry=settings.s3_presigned_expiry,
        )

    raise ValueError(f"Unsupported storage backend: {backend}")
