import structlog

from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.cache.base import DecryptCache
from rentivo.encryption.cache.null import NullDecryptCache
from rentivo.encryption.caching import CachingEncryptionBackend
from rentivo.settings import settings

logger = structlog.get_logger(__name__)

_backend: EncryptionBackend | None = None


def _build_inner_backend() -> EncryptionBackend:
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


def _build_decrypt_cache() -> DecryptCache:
    cache_backend = settings.encryption_cache_backend
    if cache_backend == "none":
        logger.info("decrypt_cache_selected", backend="none")
        return NullDecryptCache()
    if cache_backend == "memory":
        from rentivo.encryption.cache.memory import MemoryDecryptCache

        logger.info(
            "decrypt_cache_selected",
            backend="memory",
            ttl_seconds=settings.encryption_cache_ttl_seconds,
            max_entries=settings.encryption_cache_max_entries,
        )
        return MemoryDecryptCache(
            ttl_seconds=settings.encryption_cache_ttl_seconds,
            max_entries=settings.encryption_cache_max_entries,
        )
    if cache_backend == "redis":
        from rentivo.encryption.cache.redis import RedisDecryptCache

        logger.info(
            "decrypt_cache_selected",
            backend="redis",
            ttl_seconds=settings.encryption_cache_ttl_seconds,
        )
        return RedisDecryptCache.from_url(
            url=settings.redis_url,
            ttl_seconds=settings.encryption_cache_ttl_seconds,
        )
    raise ValueError(f"Unsupported decrypt cache backend: {cache_backend}")


def get_encryption() -> EncryptionBackend:
    """Return the active ``EncryptionBackend``, instantiating it on first call.

    The instance is cached at module level so subsequent calls in the same
    process return the same backend without re-instantiating. When
    ``RENTIVO_ENCRYPTION_CACHE_BACKEND=none`` (default), the bare inner
    backend is returned — no wrapper, no overhead. Otherwise the inner
    backend is wrapped in ``CachingEncryptionBackend`` with the configured
    ``DecryptCache`` implementation.
    """
    global _backend
    if _backend is not None:
        return _backend

    inner = _build_inner_backend()
    cache = _build_decrypt_cache()
    if isinstance(cache, NullDecryptCache):
        _backend = inner
    else:
        _backend = CachingEncryptionBackend(inner=inner, cache=cache)
    return _backend


def _reset_for_tests() -> None:
    """Clear the cached backend. Tests that monkeypatch ``settings`` or expect
    a fresh dispatch must call this before each invocation of ``get_encryption``.
    The encryption conftest also closes any cache resources held by a
    ``CachingEncryptionBackend`` before invoking this.
    """
    global _backend
    _backend = None
