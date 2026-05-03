import structlog

from rentivo.encryption.base import EncryptionBackend
from rentivo.settings import settings

logger = structlog.get_logger(__name__)

_backend: EncryptionBackend | None = None


def get_encryption() -> EncryptionBackend:
    """Return the active ``EncryptionBackend``, instantiating it on first call.

    The instance is cached at module level so subsequent calls in the same
    process return the same backend without re-instantiating (and without
    re-emitting the ``encryption_backend_selected`` log line). Mirrors the
    ``_engine`` / ``_connection`` singleton pattern in ``rentivo/db.py``.
    """
    global _backend
    if _backend is not None:
        return _backend

    backend = settings.encryption_backend

    if backend == "base64":
        from rentivo.encryption.base64 import Base64Backend

        logger.info("encryption_backend_selected", backend="base64")
        _backend = Base64Backend()
        return _backend

    if backend == "kms":
        from rentivo.encryption.kms import KMSBackend

        logger.info("encryption_backend_selected", backend="kms", key_id=settings.kms_key_id)
        _backend = KMSBackend(
            key_id=settings.kms_key_id,
            region=settings.kms_region,
            access_key_id=settings.kms_access_key_id,
            secret_access_key=settings.kms_secret_access_key,
            endpoint_url=settings.kms_endpoint_url,
        )
        return _backend

    raise ValueError(f"Unsupported encryption backend: {backend}")


def _reset_for_tests() -> None:
    """Clear the cached backend. Tests that monkeypatch ``settings`` or expect
    a fresh dispatch must call this before each invocation of ``get_encryption``.
    """
    global _backend
    _backend = None
