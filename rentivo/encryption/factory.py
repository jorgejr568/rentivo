import structlog

from rentivo.encryption.base import EncryptionBackend
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


def get_encryption() -> EncryptionBackend:
    backend = settings.encryption_backend

    if backend == "base64":
        from rentivo.encryption.base64 import Base64Backend

        logger.info("encryption_backend_selected", backend="base64")
        return Base64Backend()

    if backend == "kms":
        from rentivo.encryption.kms import KMSBackend

        logger.info("encryption_backend_selected", backend="kms", key_id=settings.kms_key_id)
        return KMSBackend(
            key_id=settings.kms_key_id,
            region=settings.kms_region,
            access_key_id=settings.kms_access_key_id,
            secret_access_key=settings.kms_secret_access_key,
            endpoint_url=settings.kms_endpoint_url,
        )

    raise ValueError(f"Unsupported encryption backend: {backend}")
