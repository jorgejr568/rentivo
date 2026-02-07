from billing.settings import settings
from billing.storage.base import StorageBackend


def get_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        from billing.storage.local import LocalStorage

        return LocalStorage(settings.storage_local_path)

    if settings.storage_backend == "s3":
        from billing.storage.s3 import S3Storage

        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            endpoint_url=settings.s3_endpoint_url,
            presigned_expiry=settings.s3_presigned_expiry,
        )

    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
